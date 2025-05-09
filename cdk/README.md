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
cdk deploy
```

## Environment Variables

The following environment variables need to be configured in the AWS App Runner console after deployment:

- `AWS_ID`: AWS Access Key ID
- `AWS_SECRET`: AWS Secret Access Key
- `NOVA_IMAGE_BUCKET`: S3 bucket name for storing images
- `BUCKET_REGION`: AWS region for the S3 bucket
- `HF_TOKEN`: HuggingFace token for input image check
- `RATE_LIMIT`: Rate limit configuration

## Clean Up

To destroy the deployed resources:

```bash
cdk destroy
```
