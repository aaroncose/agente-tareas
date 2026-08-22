from aws_cdk import (
    Stack, Duration, RemovalPolicy, CfnOutput,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_secretsmanager as secretsmanager,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_apigateway as apigw,
    aws_sqs as sqs,
    aws_iam as iam,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct


class AdhdAgentStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- TABLA DE ESTADO ---
        tabla = dynamodb.Table(
            self, "Estado",
            table_name="adhd-agent-estado",
            partition_key=dynamodb.Attribute(
                name="task_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # --- SECRETO ---
        secreto = secretsmanager.Secret.from_secret_name_v2(
            self, "Config", "adhd-agent/config")

        # --- COLA DE ERRORES ---
        dlq = sqs.Queue(
            self, "DLQ",
            queue_name="adhd-agent-dlq",
            retention_period=Duration.days(14),
        )

        entorno = {
            "TABLE_NAME": tabla.table_name,
            "SECRET_NAME": "adhd-agent/config",
        }

        def fn(nombre, carpeta, segundos=30):
            f = lambda_.Function(
                self, nombre,
                function_name=f"adhd-agent-{carpeta}",
                runtime=lambda_.Runtime.PYTHON_3_13,
                handler="handler.handler",
                code=lambda_.Code.from_asset(f"lambdas/{carpeta}"),
                environment=entorno,
                timeout=Duration.seconds(segundos),
                memory_size=256,
            )
            secreto.grant_read(f)
            tabla.grant_read_write_data(f)
            return f

        programador = fn("Programador", "programador", 60)
        notificador = fn("Notificador", "notificador")
        verificador = fn("Verificador", "verificador")
        voz = fn("Voz", "voz")

        notificador.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["connect:StartOutboundVoiceContact"],
                resources=["*"],
            )
        )

        # --- PASOS REUTILIZABLES ---
        def avisar(id_, accion, nivel=None):
            datos = {
                "task_id": sfn.JsonPath.string_at("$.task_id"),
                "titulo": sfn.JsonPath.string_at("$.titulo"),
                "tipo": sfn.JsonPath.string_at("$.tipo"),
                "hora_utc": sfn.JsonPath.string_at("$.hora_utc"),
                "tarde": sfn.JsonPath.string_at("$.tarde"),
                "accion": accion,
            }
            if nivel is not None:
                datos["nivel"] = nivel
            return tasks.LambdaInvoke(
                self, id_,
                lambda_function=notificador,
                payload=sfn.TaskInput.from_object(datos),
                payload_response_only=True,
                result_path=sfn.JsonPath.DISCARD,
            )

        def comprobar(id_):
            return tasks.LambdaInvoke(
                self, id_,
                lambda_function=verificador,
                payload=sfn.TaskInput.from_object({
                    "task_id": sfn.JsonPath.string_at("$.task_id"),
                }),
                payload_response_only=True,
                result_path="$.check",
            )

        def esperar(id_, campo):
            return sfn.Wait(
                self, id_,
                time=sfn.WaitTime.timestamp_path(f"$.{campo}"))

        fin = sfn.Succeed(self, "Fin")

        # --- TRAMO COMUN ---
        inicio = (
            esperar("EsperaPush", "push_at")
            .next(avisar("Push", "push"))
            .next(esperar("EsperaLlamada1", "call1_at"))
            .next(avisar("Llamada1", "llamada", 1))
        )

        # --- RAMA IMPORTANTE ---
        rama_importante = (
            esperar("ImpEspera15", "call2_at")
            .next(comprobar("ImpCheck"))
            .next(
                sfn.Choice(self, "ImpDecidir")
                .when(sfn.Condition.boolean_equals("$.check.parar", True), fin)
                .otherwise(avisar("ImpLlamada2", "llamada", 2).next(fin))
            )
        )

        # --- RAMA URGENTE ---
        rama_urgente = (
            esperar("UrgEspera5", "call2_at")
            .next(comprobar("UrgCheck1"))
            .next(
                sfn.Choice(self, "UrgDecidir1")
                .when(sfn.Condition.boolean_equals("$.check.parar", True), fin)
                .otherwise(
                    avisar("UrgLlamada2", "llamada", 2)
                    .next(esperar("UrgEspera15", "call3_at"))
                    .next(comprobar("UrgCheck2"))
                    .next(
                        sfn.Choice(self, "UrgDecidir2")
                        .when(sfn.Condition.boolean_equals("$.check.parar", True), fin)
                        .otherwise(avisar("UrgLlamada3", "llamada", 3).next(fin))
                    )
                )
            )
        )

        # --- BIFURCACION POR TIPO ---
        definicion = inicio.next(
            sfn.Choice(self, "QueTipo")
            .when(sfn.Condition.string_equals("$.tipo", "Importante"), rama_importante)
            .when(sfn.Condition.string_equals("$.tipo", "Urgente"), rama_urgente)
            .otherwise(fin)
        )

        maquina = sfn.StateMachine(
            self, "Escalada",
            state_machine_name="adhd-agent-escalada",
            definition_body=sfn.DefinitionBody.from_chainable(definicion),
            timeout=Duration.hours(48),
        )

        maquina.grant_start_execution(programador)
        programador.add_environment("STATE_MACHINE_ARN", maquina.state_machine_arn)