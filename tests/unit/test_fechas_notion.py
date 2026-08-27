"""Tests de la conversión de fechas que me llegan desde Notion.

Notion manda la fecha en varios formatos según cómo se creó la tarea. Si aqui
hay error aquí desplaza la llamada un par de horas ya que el
sistema sigue funcionando y solo suena a destiempo.
"""

from datetime import timezone


def test_acepta_una_fecha_en_utc_con_z(programador):
    resultado = programador.a_utc("2026-08-27T10:30:00Z")

    assert resultado.hour == 10
    assert resultado.minute == 30
    assert resultado.tzinfo == timezone.utc


def test_convierte_una_fecha_con_desfase_horario(programador):
    # Las diez y media en Madrid durante el verano son las ocho y media UTC.
    resultado = programador.a_utc("2026-08-27T10:30:00+02:00")

    assert resultado.hour == 8
    assert resultado.minute == 30
    assert resultado.tzinfo == timezone.utc


def test_asume_utc_cuando_la_fecha_llega_sin_zona(programador):
    # Notion omite la zona horaria en algunos casos. Aquí la interpreto como
    # UTC para que el resto del cálculo tenga siempre una referencia.
    resultado = programador.a_utc("2026-08-27T10:30:00")

    assert resultado.hour == 10
    assert resultado.tzinfo == timezone.utc


def test_el_formato_de_salida_es_el_que_espera_la_maquina_de_estados(programador):
    # Step Functions compara estas marcas como texto, así que el formato tiene
    # que salir siempre igual.
    momento = programador.a_utc("2026-08-27T10:30:00+02:00")

    assert programador.fmt(momento) == "2026-08-27T08:30:00Z"


def test_una_fecha_de_madrugada_conserva_su_dia(programador):
    # Comprobación de un caso que se rompe con facilidad. La una y media de la
    # madrugada en Madrid pertenece al día anterior en UTC.
    resultado = programador.a_utc("2026-08-27T01:30:00+02:00")

    assert programador.fmt(resultado) == "2026-08-26T23:30:00Z"
