"""Tests de cómo planifico las llamadas según la importancia de la tarea.

Aquí decido cuántas veces insisto y con cuánto margen. Un fallo en esta pieza
se traduce en llamadas de más a deshora o en una tarea urgente que suena una
sola vez.
"""

from datetime import datetime, timedelta, timezone


def dentro_de(minutos):
    """Devuelvo una marca ISO relativa a ahora, como la que manda Notion."""
    momento = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ")


def tarea(tipo, cuando):
    return {"task_id": "abc-123", "titulo": "Llamar al banco", "tipo": tipo,
            "cuando": cuando}


def minutos_entre(plan, clave_a, clave_b):
    """Diferencia en minutos entre dos marcas del plan."""
    a = datetime.strptime(plan[clave_a], "%Y-%m-%dT%H:%M:%SZ")
    b = datetime.strptime(plan[clave_b], "%Y-%m-%dT%H:%M:%SZ")
    return round((b - a).total_seconds() / 60)


# ---------- aviso previo ----------

def test_el_aviso_llega_cinco_minutos_antes_de_la_hora(programador):
    plan = programador.calcular(tarea("Normal", dentro_de(60)))

    assert minutos_entre(plan, "push_at", "hora_utc") == 5


def test_la_primera_llamada_coincide_con_la_hora_de_la_tarea(programador):
    plan = programador.calcular(tarea("Normal", dentro_de(60)))

    assert plan["call1_at"] == plan["hora_utc"]


# ---------- escalada segun el tipo ----------

def test_una_tarea_normal_suena_una_sola_vez(programador):
    # Sin insistencia. Si la persona pasa, se queda ahí.
    plan = programador.calcular(tarea("Normal", dentro_de(60)))

    assert "call2_at" not in plan
    assert "call3_at" not in plan


def test_una_tarea_importante_reintenta_una_vez_a_los_quince_minutos(programador):
    plan = programador.calcular(tarea("Importante", dentro_de(60)))

    assert minutos_entre(plan, "call1_at", "call2_at") == 15
    assert "call3_at" not in plan


def test_una_tarea_urgente_reintenta_dos_veces(programador):
    # La urgente insiste a los 5 y a los 15 minutos.
    plan = programador.calcular(tarea("Urgente", dentro_de(60)))

    assert minutos_entre(plan, "call1_at", "call2_at") == 5
    assert minutos_entre(plan, "call1_at", "call3_at") == 15


def test_la_urgente_insiste_antes_que_la_importante(programador):
    # Comprobación cruzada. El primer reintento de una urgente cae antes que el
    # de una importante, que es lo que distingue los dos niveles.
    urgente = programador.calcular(tarea("Urgente", dentro_de(60)))
    importante = programador.calcular(tarea("Importante", dentro_de(60)))

    assert minutos_entre(urgente, "call1_at", "call2_at") < \
        minutos_entre(importante, "call1_at", "call2_at")


# ---------- tareas cuya hora ya paso ----------

def test_marco_como_tarde_una_tarea_con_la_hora_pasada(programador):
    # El agente de voz usa esta marca para preguntar si ya la hizo, en lugar de
    # ofrecerle empezar.
    plan = programador.calcular(tarea("Normal", dentro_de(-120)))

    assert plan["tarde"] is True


def test_una_tarea_futura_queda_como_pendiente(programador):
    plan = programador.calcular(tarea("Normal", dentro_de(120)))

    assert plan["tarde"] is False


# ---------- datos que conservo ----------

def test_el_plan_conserva_los_datos_de_la_tarea(programador):
    # El identificador viaja por toda la máquina de estados, así que compruebo
    # que sobrevive al cálculo.
    plan = programador.calcular(tarea("Urgente", dentro_de(30)))

    assert plan["task_id"] == "abc-123"
    assert plan["titulo"] == "Llamar al banco"
    assert plan["tipo"] == "Urgente"
