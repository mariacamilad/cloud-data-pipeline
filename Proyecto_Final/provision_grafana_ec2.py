import boto3
import os
from dotenv import load_dotenv


# ============================================================
# AWS CONFIGURATION
# ============================================================

load_dotenv()

session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
)

# Test AWS connection
sts = session.client("sts")

identity = sts.get_caller_identity()

print("AWS connection successful")
print("Account:", identity["Account"])
print("ARN:", identity["Arn"])

# ============================================================
# CREATE / VERIFY EC2 KEY PAIR
# ============================================================

ec2_client = session.client("ec2")

KEY_NAME = "final-project-grafana-key"

try:
    ec2_client.describe_key_pairs(KeyNames=[KEY_NAME])
    print(f"Key Pair already exists: {KEY_NAME}")

except ec2_client.exceptions.ClientError as e:
    if e.response["Error"]["Code"] == "InvalidKeyPair.NotFound":

        key_pair = ec2_client.create_key_pair(KeyName=KEY_NAME)

        pem_path = os.path.join(
            os.path.dirname(__file__),
            f"{KEY_NAME}.pem"
        )

        with open(pem_path, "w") as pem_file:
            pem_file.write(key_pair["KeyMaterial"])

        print(f"Key Pair created: {KEY_NAME}")
        print(f"PEM saved at: {pem_path}")

    else:
        raise

# ============================================================
# CREATE / VERIFY SECURITY GROUP
# ============================================================

import urllib.request

SG_NAME = "final-project-grafana-sg"

# Get default VPC
vpcs = ec2_client.describe_vpcs(
    Filters=[{"Name": "isDefault", "Values": ["true"]}]
)

VPC_ID = vpcs["Vpcs"][0]["VpcId"]

# Get current public IP
MY_IP = urllib.request.urlopen(
    "https://checkip.amazonaws.com"
).read().decode().strip()

MY_CIDR = f"{MY_IP}/32"

# Check if Security Group already exists
existing_sg = ec2_client.describe_security_groups(
    Filters=[
        {"Name": "group-name", "Values": [SG_NAME]},
        {"Name": "vpc-id", "Values": [VPC_ID]}
    ]
)

if existing_sg["SecurityGroups"]:
    SG_ID = existing_sg["SecurityGroups"][0]["GroupId"]
    print(f"Security Group already exists: {SG_ID}")

else:
    response = ec2_client.create_security_group(
        GroupName=SG_NAME,
        Description="Security Group for Final Project Grafana EC2",
        VpcId=VPC_ID
    )

    SG_ID = response["GroupId"]

    ec2_client.authorize_security_group_ingress(
        GroupId=SG_ID,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [
                    {
                        "CidrIp": MY_CIDR,
                        "Description": "SSH from my IP"
                    }
                ]
            },
            {
                "IpProtocol": "tcp",
                "FromPort": 30000,
                "ToPort": 30000,
                "IpRanges": [
                    {
                        "CidrIp": MY_CIDR,
                        "Description": "Grafana Kubernetes NodePort"
                    }
                ]
            }
        ]
    )

    print(f"Security Group created: {SG_ID}")

# ============================================================
# ENSURE GRAFANA NODEPORT RULE
# ============================================================

try:
    ec2_client.authorize_security_group_ingress(
        GroupId=SG_ID,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 30000,
                "ToPort": 30000,
                "IpRanges": [
                    {
                        "CidrIp": MY_CIDR,
                        "Description": "Grafana Kubernetes NodePort"
                    }
                ]
            }
        ]
    )

    print("Port 30000 added to Security Group")

except ec2_client.exceptions.ClientError as e:
    if e.response["Error"]["Code"] == "InvalidPermission.Duplicate":
        print("Port 30000 already configured")
    else:
        raise

# ============================================================
# CREATE FINAL EC2 - UBUNTU + MICROK8S
# ============================================================

INSTANCE_NAME = "Final-Project-MicroK8s"

# Check whether the final instance already exists
existing_instances = ec2_client.describe_instances(
    Filters=[
        {
            "Name": "tag:Name",
            "Values": [INSTANCE_NAME]
        },
        {
            "Name": "instance-state-name",
            "Values": ["pending", "running", "stopping", "stopped"]
        }
    ]
)

found_instances = []

for reservation in existing_instances["Reservations"]:
    found_instances.extend(reservation["Instances"])


if found_instances:

    INSTANCE_ID = found_instances[0]["InstanceId"]

    print(f"Final EC2 already exists: {INSTANCE_ID}")

else:

    # --------------------------------------------------------
    # Find latest Ubuntu Server 24.04 LTS x86_64 AMI
    # --------------------------------------------------------

    images = ec2_client.describe_images(
        Owners=["099720109477"],  # Canonical
        Filters=[
            {
                "Name": "name",
                "Values": [
                    "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"
                ]
            },
            {
                "Name": "state",
                "Values": ["available"]
            },
            {
                "Name": "architecture",
                "Values": ["x86_64"]
            }
        ]
    )["Images"]

    latest_image = sorted(
        images,
        key=lambda image: image["CreationDate"],
        reverse=True
    )[0]

    AMI_ID = latest_image["ImageId"]

    print(f"Ubuntu 24.04 AMI selected: {AMI_ID}")


    # --------------------------------------------------------
    # EC2 startup automation
    # --------------------------------------------------------

    user_data_script = """#!/bin/bash
set -e

apt-get update -y

# Install MicroK8s
snap install microk8s --classic

# Allow ubuntu user to use MicroK8s
usermod -a -G microk8s ubuntu

mkdir -p /home/ubuntu/.kube
chown -R ubuntu:ubuntu /home/ubuntu/.kube

# Wait for the Kubernetes cluster
microk8s status --wait-ready

# Enable required Kubernetes services
microk8s enable dns
microk8s enable hostpath-storage
microk8s enable helm3

echo "MicroK8s installation completed"
"""


    # --------------------------------------------------------
    # Launch EC2
    # --------------------------------------------------------

    response = ec2_client.run_instances(
        ImageId=AMI_ID,
        MinCount=1,
        MaxCount=1,

        InstanceType="t3.medium",

        KeyName=KEY_NAME,

        SecurityGroupIds=[SG_ID],

        UserData=user_data_script,

        IamInstanceProfile={
            "Name": "LabInstanceProfile"
        },

        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": 30,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True
                }
            }
        ],

        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {
                        "Key": "Name",
                        "Value": INSTANCE_NAME
                    }
                ]
            }
        ]
    )

    INSTANCE_ID = response["Instances"][0]["InstanceId"]

    print(f"Final EC2 created: {INSTANCE_ID}")