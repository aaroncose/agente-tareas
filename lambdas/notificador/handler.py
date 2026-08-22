import hashlib
import os
from datetime import datetime, timezone

import boto3

from common import get_config, http, log

ddb = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
connect = boto3.client("connect")


def push(config, titulo, cuando_texto):
    status, text = http(
        f"https://ntfy.sh/{config['NTFY_TOPIC']}",
        method="POST",
        headers={"Title": titulo, "Priority": "high", "Tags": "alarm_clock"},
        body=cuando_texto,
    )
    return 200 <= status < 300, text


def llamada(config, plan):
    if not config.get("CONNECT_INSTANCE_ID"):
        log("WARN", "connect_sin_configurar")
        return False, "connect no configurado"

    # Idempotencia nativa de Connect
    semilla = f"{plan['task_id']}-{plan.get('nivel',1)}-{plan['hora_utc']}"
    token = hashlib.sha256(semilla.encode()).hexdigest()[:32]

    # El mensaje cambia si llegamos tarde
    if plan.get("tarde"):
        texto = f"Tenias {plan['titulo']}."
    else:
        texto = f"Toca {plan['titulo']}."

    try:
        r = connect.start_outbound_voice_contact(
            DestinationPhoneNumber=config["CONNECT_TO"],
            ContactFlowId=config["CONNECT_FLOW_ID"],
            InstanceId=config["CONNECT_INSTANCE_ID"],
            SourcePhoneNumber=config["CONNECT_FROM"],
            ClientToken=token,
            Attributes={
                "tarea": texto[:200],
                "task_id": plan["task_id"],
            },
        )
        return True, r["ContactId"]
    except Exception as e:
        return False, str(e)


def handler(event, context):
    config = get_config()
    accion = event.get("accion", "llamada")

    if accion == "push":
        ok, detalle = push(config, event["titulo"], "En 5 minutos.")
        canal = "push"
    else:
        ok, detalle = llamada(config, event)
        canal = "llamada"

    log("INFO" if ok else "ERROR", "enviado",
        task_id=event["task_id"], canal=canal,
        nivel=event.get("nivel"), detalle=str(detalle)[:200])

    if not ok:
        raise Exception(f"Fallo en {canal}: {detalle}")

    return event
