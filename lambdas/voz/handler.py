import os
from datetime import datetime, timezone

import boto3
from botocore.config import Config

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

def cerrar(intent, mensaje, estado="Fulfilled", atributos=None):
    """Termina la sesion de Lex. Connect recupera el control y cuelga."""
    return {
        "sessionState": {
            "dialogAction": {"type": "Close"},
            "intent": {"name": intent or "FallbackIntent", "state": estado},
            "sessionAttributes": atributos or {},
        },
        "messages": [{"contentType": "PlainText", "content": mensaje}],
    }


def seguir(mensaje, atributos):
    """Habla y se queda escuchando. Es lo que convierte esto en conversacion."""
    return {
        "sessionState": {
            "dialogAction": {"type": "ElicitIntent"},
            "sessionAttributes": atributos,
        },
        "messages": [{"contentType": "PlainText", "content": mensaje}],
    }


# ---------- conversacion ----------

bedrock = boto3.client(
    "bedrock-runtime",
    config=Config(retries={"max_attempts": 3, "mode": "adaptive"}),
)
MODELO = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
MAX_TURNOS = 80

SISTEMA = (
    "Hablas por telefono con una persona sobre una tarea suya pendiente. "
    "Le cuesta arrancar y se distrae con facilidad.\n"
    "La tarea es: {titulo}.\n"
    "{contexto}\n"
    "Cada turno tuyo tiene que hacer avanzar la tarea. Aportas tu el "
    "conocimiento que hace falta, con sitios, apartados y datos reales. Cuando "
    "desconozcas un dato exacto, di lo que sepas y sigue adelante.\n"
    "Preguntas solo cuando te falte un dato que bloquea el paso siguiente. "
    "Lo que ya te han dicho en la conversacion lo usas sin volver a "
    "preguntarlo.\n"
    "Hablas como habla una persona. Una o dos frases por turno, lenguaje "
    "hablado, sin listas ni numeracion, sin emojis, sin markdown.\n"
    "Marcadores: si la persona dice que ya la ha hecho, responde breve y añade "
    "[HECHA] al final. Si se despide o da la conversacion por terminada, "
    "despidete en una frase y añade [FIN] al final."
)

CTX_TARDE = (
    "La hora de la tarea ya paso. Empieza preguntando si la hizo. Cuando te "
    "diga que sigue pendiente, dale el primer paso para hacerla ahora."
)
CTX_FUTURO = (
    "Es la hora de la tarea. La persona acaba de descolgar y ya ha oido el "
    "saludo, asi que ve directo al primer paso."
)


def leer_historial(task_id):
    fila = ddb.get_item(Key={"task_id": task_id}).get("Item") or {}
    return fila.get("conversacion") or []


def guardar_historial(task_id, historial):
    ddb.update_item(
        Key={"task_id": task_id},
        UpdateExpression="SET conversacion = :c",
        ExpressionAttributeValues={":c": historial[-(MAX_TURNOS * 2):]},
    )


def hablar(historial, titulo, tarde):
    """Un turno del modelo. Converse mantiene el hilo con el historial completo."""
    sistema = SISTEMA.format(
        titulo=titulo or "una tarea",
        contexto=CTX_TARDE if tarde else CTX_FUTURO,
    )
    mensajes = [
        {"role": m["r"], "content": [{"text": m["t"]}]} for m in historial
    ]
    r = bedrock.converse(
        modelId=MODELO,
        system=[{"text": sistema}],
        messages=mensajes,
        inferenceConfig={"maxTokens": 200, "temperature": 0.6},
    )
    return r["output"]["message"]["content"][0]["text"].strip()


def conversar(config, task_id, titulo, tarde, dicho, atributos):
    historial = leer_historial(task_id) if task_id else []
    historial.append({"r": "user", "t": dicho})

    try:
        texto = hablar(historial, titulo, tarde)
    except Exception as e:
        log("ERROR", "bedrock_fallo", error=str(e))
        return cerrar(None, "Ahora mismo no puedo seguir. Lo dejamos aqui.",
                      atributos=atributos)

    hecha = "[HECHA]" in texto
    fin = "[FIN]" in texto or len(historial) >= MAX_TURNOS * 2 - 1
    texto = texto.replace("[HECHA]", "").replace("[FIN]", "").strip()

    historial.append({"r": "assistant", "t": texto})
    if task_id:
        guardar_historial(task_id, historial)

    if hecha and task_id:
        marcar_hecha(config, task_id)
        log("INFO", "marcada_hecha_en_conversacion", task_id=task_id)

    log("INFO", "turno", task_id=task_id, fin=fin or hecha, dicho=dicho[:100])

    if hecha or fin:
        return cerrar(None, texto, atributos=atributos)
    return seguir(texto, atributos)


# ---------- entrada ----------

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
    atributos = sesion.get("sessionAttributes") or {}
    task_id = atributos.get("task_id", "")
    titulo = atributos.get("titulo", "")
    tarde = atributos.get("tarde") == "si"

    if task_id:
        marcar_atendida(task_id)

    # Atajos rapidos: cierran la llamada sin pasar por el modelo
    if nombre == "HechaIntent":
        marcar_hecha(config, task_id)
        log("INFO", "marcada_hecha", task_id=task_id)
        return cerrar(nombre, "Hecho. La marco como terminada.", atributos=atributos)

    if nombre == "AplazarIntent":
        valor = None
        s = slots.get("NuevaHora")
        if s and s.get("value"):
            valor = s["value"].get("interpretedValue")
        if not valor:
            return cerrar(nombre, "No he entendido la hora. Lo dejamos como esta.",
                          atributos=atributos)
        hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        nueva = f"{hoy}T{valor}:00"
        mover_hora(config, task_id, nueva)
        ddb.update_item(
            Key={"task_id": task_id},
            UpdateExpression="REMOVE atendida, conversacion",
        )
        log("INFO", "aplazada", task_id=task_id, nueva=nueva)
        return cerrar(nombre, f"Vale, te llamo a las {valor}.", atributos=atributos)

    # Todo lo demas es conversacion
    dicho = event.get("inputTranscript") or ""
    if not dicho.strip():
        return seguir("Te escucho.", atributos)

    return conversar(config, task_id, titulo, tarde, dicho, atributos)
