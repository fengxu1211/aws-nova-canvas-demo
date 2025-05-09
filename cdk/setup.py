import setuptools

with open("README.md") as fp:
    long_description = fp.read()

setuptools.setup(
    name="nova_canvas_cdk",
    version="0.1.0",
    description="AWS CDK app to deploy Nova Canvas Gradio application to AWS App Runner",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="AWS",
    package_dir={"": "."},
    packages=setuptools.find_packages(),
    install_requires=[
        "aws-cdk-lib>=2.100.0",
        "constructs>=10.0.0",
        "aws-cdk.aws-apprunner-alpha>=2.100.0-alpha.0",
    ],
    python_requires=">=3.12",
)
