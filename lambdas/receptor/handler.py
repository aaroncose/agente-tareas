import hashlib
import hmac
import json
import os

import boto3

from common import get_config, log

lam = boto3.client("lambda")


def ok(cuerpo):
    return {"statusCode": 200, "body": json.dumps(cuerpo)}


def firma_valida(secreto, cuerpo, cabecera):
    """Comprueba la firma HMAC-SHA256 de Notion."""
    if not secreto or not cabecera:
        return False
    esperada = "sha256=" + hmac.new(
        secreto.encode(), cuerpo.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperada, cabecera)


def lanzar(page_ids):
    lam.invoke(
        FunctionName=os.environ["PROGRAMADOR_ARN"],
        InvocationType="Event",
        Payload=json.dumps({"page_ids": page_ids}),
    )


def handler(event, context):
    config = get_config()
    cuerpo_txt = event.get("body") or "{}"
    cabeceras = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    try:
        cuerpo = json.loads(cuerpo_txt)
    except Exception:
        return ok({"error": "json invalido"})

    # 1. Verificacion inicial de Notion
    if "verification_token" in cuerpo:
        log("WARN", "TOKEN_DE_VERIFICACION", token=cuerpo["verification_token"])
        return ok({"recibido": True})

    # 2. Boton manual desde el Atajo de iOS
    if cabeceras.get("x-shortcut-key"):
        if cabeceras["x-shortcut-key"] != config.get("SHORTCUT_KEY"):
            log("WARN", "atajo_clave_incorrecta")
            return {"statusCode": 403, "body": "no"}
        ids = cuerpo.get("page_ids") or []
        if ids:
            lanzar(ids)
        log("INFO", "atajo_ok", n=len(ids))
        return ok({"lanzadas": len(ids)})

    # 3. Evento normal de Notion
    firma = cabeceras.get("x-notion-signature")
    verif = config.get("NOTION_VERIFICATION_TOKEN")
    if verif and not firma_valida(verif, cuerpo_txt, firma):
        log("WARN", "firma_invalida")
        return {"statusCode": 401, "body": "no"}

    tipo = cuerpo.get("type", "")
    entidad = cuerpo.get("entity", {})

    if tipo in ("page.created", "page.properties_updated") and entidad.get("type") == "page":
        lanzar([entidad["id"]])
        log("INFO", "evento_procesado", tipo=tipo, page_id=entidad["id"])

    return ok({"recibido": True})
