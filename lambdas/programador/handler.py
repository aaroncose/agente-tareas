import json
import os
import time
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

from common import get_config, http, notion_headers, log

ddb = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
sfn = boto3.client("stepfunctions")

# Los tres unicos numeros del sistema, todos definidos por el usuario
MIN_ANTES_PUSH = 5
REINTENTO_IMPORTANTE = 15
REINTENTO_URGENTE_1 = 5
REINTENTO_URGENTE_2 = 15


def a_utc(iso):
    """Convierte una fecha ISO de Notion a formato UTC con Z."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def leer_tarea(config, page_id):
    status, text = http(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=notion_headers(config["NOTION_TOKEN"]),
    )
    if status != 200:
        log("ERROR", "notion_page_error", status=status, page_id=page_id)
        return None

    props = json.loads(text).get("properties", {})

    titulos = props.get("Tarea", {}).get("title", [])
    titulo = titulos[0]["plain_text"] if titulos else None

    fecha = props.get("Cuando", {}).get("date")
    cuando = fecha["start"] if fecha else None

    tsel = props.get("Tipo", {}).get("select")
    tipo = tsel["name"] if tsel else "Normal"

    esel = props.get("Estado", {}).get("select")
    estado = esel["name"] if esel else "Pendiente"

    if not titulo or not cuando:
        log("INFO", "tarea_incompleta", page_id=page_id)
        return None
    if estado != "Pendiente":
        log("INFO", "tarea_no_pendiente", page_id=page_id, estado=estado)
        return None
    if "T" not in cuando:
        log("INFO", "tarea_sin_hora", page_id=page_id)
        return None

    return {"task_id": page_id, "titulo": titulo, "tipo": tipo, "cuando": cuando}


def calcular(tarea):
    h = a_utc(tarea["cuando"])
    ahora = datetime.now(timezone.utc)

    plan = {
        **tarea,
        "hora_utc": fmt(h),
        "push_at": fmt(h - timedelta(minutes=MIN_ANTES_PUSH)),
        "call1_at": fmt(h),
        "tarde": h < ahora,
    }

    if tarea["tipo"] == "Importante":
        plan["call2_at"] = fmt(h + timedelta(minutes=REINTENTO_IMPORTANTE))
    elif tarea["tipo"] == "Urgente":
        plan["call2_at"] = fmt(h + timedelta(minutes=REINTENTO_URGENTE_1))
        plan["call3_at"] = fmt(h + timedelta(minutes=REINTENTO_URGENTE_2))

    return plan


def reclamar(plan):
    """Escribe solo si no existe. Devuelve True si la reclamamos nosotros."""
    try:
        ddb.put_item(
            Item={
                "task_id": plan["task_id"],
                "titulo": plan["titulo"],
                "tipo": plan["tipo"],
                "hora_utc": plan["hora_utc"],
                "atendida": False,
                "creado": int(time.time()),
                "ttl": int(time.time()) + 7 * 24 * 3600,
            },
            ConditionExpression="attribute_not_exists(task_id)",
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def arrancar(plan):
    nombre = f"{plan['task_id'].replace('-','')[:24]}{int(time.time())}"
    sfn.start_execution(
        stateMachineArn=os.environ["STATE_MACHINE_ARN"],
        name=nombre[:80],
        input=json.dumps(plan),
    )
    log("INFO", "escalada_arrancada",
        task_id=plan["task_id"], tipo=plan["tipo"], hora=plan["hora_utc"])


def procesar(page_id):
    config = get_config()
    tarea = leer_tarea(config, page_id)
    if not tarea:
        return False
    plan = calcular(tarea)
    if not reclamar(plan):
        log("INFO", "ya_programada", task_id=page_id)
        return False
    arrancar(plan)
    return True


def handler(event, context):
    """Recibe {"page_id": "..."} o una lista de ellos."""
    ids = event.get("page_ids") or ([event["page_id"]] if event.get("page_id") else [])
    programadas = sum(1 for pid in ids if procesar(pid))
    return {"programadas": programadas, "recibidas": len(ids)}
