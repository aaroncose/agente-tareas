#!/usr/bin/env python3
import os

import aws_cdk as cdk

from agente_tareas.agente_tareas_stack import AgenteTareasStack


app = cdk.App()

# Mantengo "AdhdAgentStack" como identificador porque es el nombre con el que
# CloudFormation conoce mi stack desplegado. Cambiarlo crearía uno nuevo y
# dejaría huérfanos la tabla, las Lambdas y la máquina de estados actuales.
AgenteTareasStack(app, "AdhdAgentStack",
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.

    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.

    #env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),

    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */

    #env=cdk.Environment(account='123456789012', region='us-east-1'),

    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
    )

app.synth()
