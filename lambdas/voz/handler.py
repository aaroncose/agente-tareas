import json
import os
from datetime import datetime, timezone

import boto3

from common import get_config, http, notion_headers, log

ddb = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
lam = boto3.client("lambda")


# ---------- acciones sobre Notion ----------

def marcar_hecha(config, task_id):
    return http(
        f"https://api.notion.com/v1/pages/{task_id}",
        method="PATCH",
        headers=notion_headers(config["NOTION_TOKEN"]),
        body={"properties": {"Estado": {"select": {"name": "Hecho"}}}},
    )


def mover_hora(config, task_id, nueva_iso):
    return http(
        f"https://api.notion.com/v1/pages/{task_id}",
        method="PATCH",
        headers=notion_headers(config["NOTION_TOKEN"]),
        body={"properties": {"Cuando": {"date": {"start": nueva_iso}}}},
    )


def marcar_atendida(task_id):
    ddb.update_item(
        Key={"task_id": task_id},
        UpdateExpression="SET atendida = :v, atendida_en = :t",
        ExpressionAttributeValues={
            ":v": True,
            ":t": datetime.now(timezone.utc).isoformat(),
        },
    )


# ---------- respuesta a Lex ----------

def responder(intent, mensaje, estado="Fulfilled"):
    return {
        "sessionState": {
            "dialogAction": {"type": "Close"},
            "intent": {"name": intent, "state": estado},
        },
        "messages": [{"contentType": "PlainText", "content": mensaje}],
    }


def handler(event, context):
    config = get_config()

    # Llamada directa desde el contact flow, al descolgar
    if event.get("Details", {}).get("Parameters", {}).get("accion") == "atendida":
        task_id = event["Details"]["Parameters"]["task_id"]
        marcar_atendida(task_id)
        log("INFO", "descolgada", task_id=task_id)
        return {"ok": "true"}

    # Invocacion desde Lex
    sesion = event.get("sessionState", {})
    intent = sesion.get("intent", {})
    nombre = intent.get("name", "")
    slots = intent.get("slots") or {}
    atributos = event.get("sessionState", {}).get("sessionAttributes", {}) or {}
    task_id = atributos.get("task_id", "")

    if task_id:
        marcar_atendida(task_id)

    if nombre == "HechaIntent":
        marcar_hecha(config, task_id)
        log("INFO", "marcada_hecha", task_id=task_id)
        return responder(nombre, "Hecho. La marco como terminada.")

    if nombre == "AplazarIntent":
        valor = None
        s = slots.get("NuevaHora")
        if s and s.get("value"):
            valor = s["value"].get("interpretedValue")
        if not valor:
            return responder(nombre, "No he entendido la hora. Lo dejamos como esta.")
        hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        nueva = f"{hoy}T{valor}:00"
        mover_hora(config, task_id, nueva)
        ddb.update_item(
            Key={"task_id": task_id},
            UpdateExpression="REMOVE atendida",
        )
        log("INFO", "aplazada", task_id=task_id, nueva=nueva)
        return responder(nombre, f"Vale, te llamo a las {valor}.")

    if nombre == "AyudaIntent":
        plan = generar_plan(atributos.get("titulo", "la tarea"))
        return responder(nombre, plan)

    return responder(nombre or "Fallback", "No te he entendido.")


def generar_plan(titulo):
    """Se completa en la Fase 11. De momento, respuesta fija."""
    return ("Empieza por lo mas pequeno. Abre el archivo, "
            "escribe el titulo, y haz solo el primer punto.")
