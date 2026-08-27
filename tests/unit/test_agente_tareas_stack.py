"""Tests de la infraestructura que sintetizo con CDK.

Comprueban la plantilla de CloudFormation antes de desplegarla, así
detectan un recurso que desaparece o cambia sin que yo lo pretenda.
"""

import aws_cdk as core
import aws_cdk.assertions as assertions

from agente_tareas.agente_tareas_stack import AgenteTareasStack


def crear_template():
    app = core.App()
    stack = AgenteTareasStack(app, "agente-tareas")
    return assertions.Template.from_stack(stack)


def test_la_tabla_de_estado_usa_el_identificador_de_tarea_como_clave():
    template = crear_template()

    # Guardo el estado de cada tarea indexado por su página de Notion.
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "adhd-agent-estado",
            "KeySchema": [{"AttributeName": "task_id", "KeyType": "HASH"}],
        },
    )


def test_la_cola_de_fallidos_guarda_los_mensajes_dos_semanas():
    template = crear_template()

    # Con 14 días tengo margen para revisar un fallo del fin de semana.
    template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": "adhd-agent-dlq",
            "MessageRetentionPeriod": 1209600,
        },
    )


def test_existe_la_maquina_que_escala_las_llamadas():
    template = crear_template()

    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)
    template.has_resource_properties(
        "AWS::StepFunctions::StateMachine",
        {"StateMachineName": "adhd-agent-escalada"},
    )


def test_el_webhook_de_notion_entra_por_un_post():
    template = crear_template()

    # Notion publica sus avisos contra esta ruta.
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {
            "HttpMethod": "POST",
            "Integration": assertions.Match.object_like(
                {"Type": "AWS_PROXY"}
            ),
        },
    )


def test_despliego_las_cinco_lambdas_del_circuito():
    template = crear_template()

    template.resource_count_is("AWS::Lambda::Function", 5)

    for carpeta in ("receptor", "programador", "notificador", "verificador", "voz"):
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": f"adhd-agent-{carpeta}",
                "Runtime": "python3.13",
                "Handler": "handler.handler",
            },
        )


def test_todas_mis_lambdas_leen_el_mismo_secreto():
    template = crear_template()

    # Las credenciales de Notion y Connect viven en un único secreto.
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": assertions.Match.object_like(
                {
                    "Variables": assertions.Match.object_like(
                        {"SECRET_NAME": "adhd-agent/config"}
                    )
                }
            )
        },
    )
