# AWS CDK Deployment for Nova Canvas Gradio App

This directory contains AWS CDK code to deploy the Nova Canvas Gradio application to AWS App Runner.

## Prerequisites

- AWS CLI configured with appropriate credentials
- AWS CDK v2 installed
- Python 3.12 or later
- Node.js 14.x or later (required by CDK)

## Setup

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

2. Bootstrap your AWS environment (if not already done):

```bash
cdk bootstrap
```

## Deployment

To deploy the application:

```bash
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
cdk deploy
```

## Clean Up

To destroy the deployed resources:

```bash
cdk destroy
```
