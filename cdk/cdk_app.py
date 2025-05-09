#!/usr/bin/env python3
import os
from aws_cdk import App
from stacks.app_runner_stack import NovaCanvasAppRunnerStack

app = App()

NovaCanvasAppRunnerStack(app, "NovaCanvasAppRunnerStack",
    env={
        "account": os.environ.get("CDK_DEFAULT_ACCOUNT"),
        "region": os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
    }
)

app.synth()
