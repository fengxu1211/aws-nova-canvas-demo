from aws_cdk import (
    Stack,
    aws_apprunner as apprunner,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
    SecretValue,
    CfnOutput,
    Duration,
    RemovalPolicy
)
from constructs import Construct

class NovaCanvasAppRunnerStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a Docker image asset from the Dockerfile in the parent directory
        image_asset = ecr_assets.DockerImageAsset(self, "NovaCanvasImage",
            directory="../app/",  # Path to the directory containing Dockerfile
            file="Dockerfile"
        )

        # Create IAM role for App Runner service with required permissions
        app_runner_role = iam.Role(self, "AppRunnerServiceRole",
            assumed_by=iam.ServicePrincipal("tasks.apprunner.amazonaws.com")
        )

        # Add required policies for AWS Bedrock, S3, and other services
        app_runner_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess")
        )
        
        # Add S3 access for the Nova image bucket
        app_runner_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:ListBucket",
                    "s3:DeleteObject"
                ],
                resources=[
                    "arn:aws:s3:::${NOVA_IMAGE_BUCKET}",
                    "arn:aws:s3:::${NOVA_IMAGE_BUCKET}/*"
                ]
            )
        )

        # Create App Runner service
        app_runner_service = apprunner.CfnService(self, "NovaCanvasAppRunnerService",
            service_name="nova-canvas-app",
            source_configuration=apprunner.CfnService.SourceConfigurationProperty(
                authentication_configuration=apprunner.CfnService.AuthenticationConfigurationProperty(
                    access_role_arn=app_runner_role.role_arn
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
                            }
                        ]
                    )
                )
            ),
            instance_configuration=apprunner.CfnService.InstanceConfigurationProperty(
                cpu="2 vCPU",
                memory="4 GB",
                instance_role_arn=app_runner_role.role_arn
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

    def _create_auto_scaling_config(self):
        # Create auto scaling configuration for the App Runner service
        return apprunner.CfnAutoScalingConfiguration(self, "NovaCanvasAutoScalingConfig",
            auto_scaling_configuration_name="nova-canvas-auto-scaling",
            max_concurrency=100,
            max_size=10,
            min_size=1
        )
