import boto3
import os
from dotenv import load_dotenv
# Load AWS Academy session credentials from the .env file
load_dotenv()
session = boto3.Session (
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
)
ec2 = session.resource('ec2')
# Bash script to configure Amazon Linux 2023 (Python multiline string)
user_data_script = '''#!/bin/bash
# 1. Update the system and install Docker
dnf update -y
dnf install docker -y
# 2. Start the Docker service and enable it on boot
systemctl start docker
systemctl enable docker
usermod -aG docker ec2-user
# 3. Download and run the Grafana container
docker run -d --name=grafana_server --restart unless-stopped -p 3000:3000 grafana/grafana:latest
'''
print("Provisioning EC2 infrastructure and Docker container...")
# >>> COMPLETE THESE TWO VALUES BEFORE EXECUTING <<<
KEYPAIR_NAME = 'cloud-docker-key' # Your KeyPair name (without .pem)
SG_IDS = ['sg-0df24b6bf7f42eadf'] # Security Group ID from Step 1
#ssm = session.client('ssm')
#AMI_ID = ssm.get_parameter(
#    Name='/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64'
#)['Parameter']['Value']
instances = ec2.create_instances(
    ImageId="ami-081b0a6eac00b4f53", # Amazon Linux 2023 AMI (validate currency)
    MinCount=1,
    MaxCount=1,
    InstanceType='t2.micro',
    KeyName=KEYPAIR_NAME,
    UserData=user_data_script,
    SecurityGroupIds=SG_IDS,
)
# create_instances returns a list; access the first element
print(f"✅ Instance successfully created. ID: {instances[0].id}")