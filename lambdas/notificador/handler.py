import hashlib
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import boto3

from common import get_config, http, log

ddb = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
connect = boto3.client("connect")

LOCAL = "Europe/Madrid"


def hora_local(iso):
    """Pasa una marca UTC del plan a hora de pared, para decirla en voz alta."""
    try:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(LOCAL)).strftime("%H:%M")
    except Exception:
        return iso[11:16]


def saludo(plan):
    """Lo primero que oyes al descolgar. Lo lee Polly, no el modelo."""
    if plan.get("tarde"):
        return (f"A las {hora_local(plan['hora_utc'])} tenias pendiente "
                f"{plan['titulo']}. Lo has hecho ya?")
    return (f"Tienes pendiente {plan['titulo']}. Si quieres te voy guiando "
            f"paso a paso, o dime como puedo ayudarte.")


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

    # El saludo cambia si llegamos tarde
    texto = saludo(plan)

    try:
        r = connect.start_outbound_voice_contact(
            DestinationPhoneNumber=config["CONNECT_TO"],
            ContactFlowId=config["CONNECT_FLOW_ID"],
            InstanceId=config["CONNECT_INSTANCE_ID"],
            SourcePhoneNumber=config["CONNECT_FROM"],
            ClientToken=token,
            Attributes={
                "tarea": texto[:400],
                "task_id": plan["task_id"],
                "titulo": plan["titulo"][:200],
                "tarde": "si" if plan.get("tarde") else "no",
                "hora": hora_local(plan["hora_utc"]),
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
