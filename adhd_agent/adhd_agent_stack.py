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