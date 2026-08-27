"""Tests de la firma que protege mi webhook de Notion.

Es la única barrera entre mi URL pública de API Gateway y el sistema que llama
por teléfono. Quien consiga falsear esta firma puede provocar llamadas a mi
número, así que aquí compruebo que solo pasa lo firmado con mi secreto.
"""

import hashlib
import hmac

SECRETO = "mi-secreto-de-notion"
CUERPO = '{"page_ids":["abc-123"]}'


def firmar(secreto, cuerpo):
    """Genero una cabecera igual que la que manda Notion."""
    return "sha256=" + hmac.new(
        secreto.encode(), cuerpo.encode(), hashlib.sha256
    ).hexdigest()


def test_acepta_una_peticion_firmada_con_mi_secreto(receptor):
    # El caso bueno. Notion firma el cuerpo con el secreto que compartimos.
    cabecera = firmar(SECRETO, CUERPO)

    assert receptor.firma_valida(SECRETO, CUERPO, cabecera) is True


def test_rechaza_una_firma_manipulada(receptor):
    # Alguien cambia un carácter de la firma para probar suerte.
    cabecera = firmar(SECRETO, CUERPO)
    manipulada = cabecera[:-1] + ("0" if cabecera[-1] != "0" else "1")

    assert receptor.firma_valida(SECRETO, CUERPO, manipulada) is False


def test_rechaza_un_cuerpo_alterado_con_la_firma_original(receptor):
    # El ataque que de verdad importa. Interceptan una petición legítima y
    # cambian el contenido conservando la firma que venía.
    cabecera = firmar(SECRETO, CUERPO)
    otro_cuerpo = '{"page_ids":["pagina-que-no-es-mia"]}'

    assert receptor.firma_valida(SECRETO, otro_cuerpo, cabecera) is False


def test_rechaza_una_firma_hecha_con_otro_secreto(receptor):
    # La firma tiene el formato correcto y sale de otro secreto.
    cabecera = firmar("secreto-de-otra-persona", CUERPO)

    assert receptor.firma_valida(SECRETO, CUERPO, cabecera) is False


def test_rechaza_cuando_falta_la_cabecera(receptor):
    # Una petición directa a mi URL llega sin firma ninguna.
    assert receptor.firma_valida(SECRETO, CUERPO, None) is False
    assert receptor.firma_valida(SECRETO, CUERPO, "") is False


def test_rechaza_cuando_mi_secreto_esta_vacio(receptor):
    # Si el secreto llegara vacío por un fallo de configuración, prefiero
    # rechazar todo antes que dejar pasar cualquier cosa.
    cabecera = firmar("", CUERPO)

    assert receptor.firma_valida("", CUERPO, cabecera) is False
    assert receptor.firma_valida(None, CUERPO, cabecera) is False


def test_la_comparacion_resiste_ataques_de_tiempo(receptor):
    # Compruebo que uso compare_digest, que tarda lo mismo con una firma
    # equivocada al principio que al final.
    import inspect

    codigo = inspect.getsource(receptor.firma_valida)
    assert "compare_digest" in codigo
