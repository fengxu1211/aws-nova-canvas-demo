from aws_cdk import (
    Stack,
    aws_apprunner as apprunner,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
    aws_secretsmanager as secretsmanager,
    aws_s3 as s3,
    SecretValue,
    CfnOutput,
    Duration,
    RemovalPolicy
)
from constructs import Construct

class NovaCanvasAppRunnerStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create an S3 bucket for the application
        bucket = s3.Bucket(self, "ImageBucket",
            removal_policy=RemovalPolicy.RETAIN,  # Keep the bucket when the stack is deleted
            auto_delete_objects=False,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )

        # Create a secret with a random password for the app
        app_password = secretsmanager.Secret(self, "NovaCanvasAppPassword",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                password_length=16,
                exclude_punctuation=True
            ),
            removal_policy=RemovalPolicy.DESTROY  # For development; use RETAIN for production
        )

        # Create a Docker image asset from the Dockerfile in the parent directory
        image_asset = ecr_assets.DockerImageAsset(self, "NovaCanvasImage",
            directory="../app/",  # Path to the directory containing Dockerfile
            file="Dockerfile"
        )

        # Create IAM role for App Runner instance with required permissions
        instance_role = iam.Role(self, "AppRunnerInstanceRole",
            assumed_by=iam.ServicePrincipal("tasks.apprunner.amazonaws.com")
        )

        # Add required policies for AWS Bedrock, S3, and other services
        instance_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess")
        )
        
        # Add S3 access for the Nova image bucket
        instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:ListBucket",
                    "s3:DeleteObject"
                ],
                resources=[
                    f"arn:aws:s3:::{bucket.bucket_name}",
                    f"arn:aws:s3:::{bucket.bucket_name}/*"
                ]
            )
        )
        
        # Add Secrets Manager access for the password secret
        instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:GetSecretValue",
                ],
                resources=[app_password.secret_arn]
            )
        )
        
        # Create a separate IAM role for App Runner service (access role)
        access_role = iam.Role(self, "AppRunnerAccessRole",
            assumed_by=iam.ServicePrincipal("build.apprunner.amazonaws.com")
        )
        
        # Add ECR access permissions to the access role
        access_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetAuthorizationToken",
                    "ecr:DescribeImages"
                ],
                resources=["*"]
            )
        )

        # Create App Runner service
        app_runner_service = apprunner.CfnService(self, "NovaCanvasAppRunnerService",
            service_name="nova-canvas-app",
            source_configuration=apprunner.CfnService.SourceConfigurationProperty(
                authentication_configuration=apprunner.CfnService.AuthenticationConfigurationProperty(
                    access_role_arn=access_role.role_arn
                ),
                auto_deployments_enabled=False,
                image_repository=apprunner.CfnService.ImageRepositoryProperty(
                    image_identifier=image_asset.image_uri,
                    image_repository_type="ECR",
                    image_configuration=apprunner.CfnService.ImageConfigurationProperty(
                        port="7860",  # Default Gradio port
                        runtime_environment_variables=[
                            # Environment variables will be set through the console or CI/CD pipeline
                            # as they contain sensitive information
                            {
                                "name": "AWS_REGION",
                                "value": self.region
                            },
                            {
                                "name": "PASSWORD_SECRET_NAME",
                                "value": app_password.secret_name
                            },
                            {
                                "name": "NOVA_IMAGE_BUCKET",
                                "value": bucket.bucket_name
                            }
                        ]
                    )
                )
            ),
            instance_configuration=apprunner.CfnService.InstanceConfigurationProperty(
                cpu="2 vCPU",
                memory="4 GB",
                instance_role_arn=instance_role.role_arn
            ),
            health_check_configuration=apprunner.CfnService.HealthCheckConfigurationProperty(
                protocol="TCP",
                path="/",
                interval=20,
                timeout=5,
                healthy_threshold=1,
                unhealthy_threshold=5
            ),
            auto_scaling_configuration_arn=self._create_auto_scaling_config().attr_auto_scaling_configuration_arn
        )

        # Output the App Runner service URL
        CfnOutput(self, "AppRunnerServiceURL",
            value=f"https://{app_runner_service.attr_service_url}",
            description="URL of the App Runner service"
        )
        
        # Output the Secret name where the password is stored
        CfnOutput(self, "AppPasswordSecretName",
            value=app_password.secret_name,
            description="Name of the Secret Manager secret containing the app password"
        )
        
        # Output the S3 bucket name
        CfnOutput(self, "S3BucketName",
            value=bucket.bucket_name,
            description="Name of the S3 bucket for Nova Canvas application"
        )

    def _create_auto_scaling_config(self):
        # Create auto scaling configuration for the App Runner service
        return apprunner.CfnAutoScalingConfiguration(self, "NovaCanvasAutoScalingConfig",
            auto_scaling_configuration_name="nova-canvas-auto-scaling",
            max_concurrency=100,
            max_size=5,
            min_size=1
        )
