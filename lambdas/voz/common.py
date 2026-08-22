import json
import os
import urllib.request
import urllib.error
import boto3

NOTION_VERSION = "2026-03-11"
_cache = None


def get_config():
    """Lee el secreto. Cachea entre invocaciones cercanas."""
    global _cache
    if _cache is None:
        c = boto3.client("secretsmanager")
        r = c.get_secret_value(SecretId=os.environ["SECRET_NAME"])
        _cache = json.loads(r["SecretString"])
    return _cache


def http(url, method="GET", headers=None, body=None, timeout=15):
    """Peticion HTTP con libreria estandar. Devuelve (status, texto)."""
    data = None
    if body is not None:
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def notion_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def log(level, event, **kw):
    """Log JSON. CloudWatch puede filtrar dentro de JSON, no dentro de texto plano."""
    print(json.dumps({"level": level, "event": event, **kw}))
