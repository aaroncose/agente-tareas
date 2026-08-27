"""Utilidades que comparten mis tests de handlers.

Cada lambda vive en su propia carpeta con un common.py al lado, así que las
cargo por ruta de archivo y añado su carpeta al path para que el import de
common resuelva.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def cargar_lambda(nombre, entorno=None):
    """Cargo el handler de una lambda por su ruta y devuelvo el módulo."""
    carpeta = RAIZ / "lambdas" / nombre

    # Los handlers crean sus clientes al importarse, así que defino las
    # variables que leen antes de ejecutar el módulo.
    for clave, valor in (entorno or {}).items():
        os.environ.setdefault(clave, valor)
    os.environ.setdefault("AWS_DEFAULT_REGION", "eu-central-1")

    # La carpeta de la lambda entra en el path para que `import common` funcione
    # igual que dentro del paquete desplegado.
    sys.path.insert(0, str(carpeta))
    try:
        spec = importlib.util.spec_from_file_location(
            f"lambda_{nombre}", carpeta / "handler.py"
        )
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo
    finally:
        sys.path.remove(str(carpeta))


@pytest.fixture(scope="module")
def receptor():
    return cargar_lambda("receptor", {
        "TABLE_NAME": "tabla-de-prueba",
        "SECRET_NAME": "secreto-de-prueba",
        "PROGRAMADOR_ARN": "arn:aws:lambda:eu-central-1:000000000000:function:prueba",
    })


@pytest.fixture(scope="module")
def programador():
    return cargar_lambda("programador", {
        "TABLE_NAME": "tabla-de-prueba",
        "SECRET_NAME": "secreto-de-prueba",
        "STATE_MACHINE_ARN": "arn:aws:states:eu-central-1:000000000000:stateMachine:prueba",
    })
