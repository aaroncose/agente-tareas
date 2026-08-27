import aws_cdk as core
import aws_cdk.assertions as assertions

from adhd_agent.adhd_agent_stack import AdhdAgentStack

# example tests. To run these tests, uncomment this file along with the example
# resource in adhd_agent/adhd_agent_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = AdhdAgentStack(app, "adhd-agent")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
