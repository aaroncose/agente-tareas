import json
import os

import boto3

from common import get_config, http, notion_headers, log

ddb = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def handler(event, context):
    task_id = event["task_id"]

    # 1. Contestaste alguna llamada
    fila = ddb.get_item(Key={"task_id": task_id}).get("Item") or {}
    if fila.get("atendida"):
        log("INFO", "atendida", task_id=task_id)
        return {**event, "parar": True}

    # 2. La marcaste Hecho en Notion
    config = get_config()
    status, text = http(
        f"https://api.notion.com/v1/pages/{task_id}",
        headers=notion_headers(config["NOTION_TOKEN"]),
    )
    if status == 200:
        sel = json.loads(text).get("properties", {}).get("Estado", {}).get("select")
        if sel and sel["name"] == "Hecho":
            log("INFO", "ya_hecha_en_notion", task_id=task_id)
            return {**event, "parar": True}

    log("INFO", "sigue_pendiente", task_id=task_id)
    return {**event, "parar": False}
