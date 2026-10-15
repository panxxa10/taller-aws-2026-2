"""Punto 2 - Mismo despliegue (S3 + EC2 + RDS) con Boto3.

    python deploy_boto3.py deploy
    python deploy_boto3.py destroy

Usa el perfil del entorno (AWS_PROFILE=user_cli). No contiene contraseñas:
RDS genera y guarda la contraseña en Secrets Manager (ManageMasterUserPassword).
"""
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "us-east-1")
TAG = [{"Key": "Proyecto", "Value": "taller-aws"}, {"Key": "Metodo", "Value": "boto3"}]

session = boto3.Session(region_name=REGION)
account = session.client("sts").get_caller_identity()["Account"]
s3 = session.client("s3")
ec2 = session.client("ec2")
rds = session.client("rds")
ssm = session.client("ssm")

BUCKET = f"taller-aws-sdk-{account}-{REGION}"
SG_EC2 = "taller-aws-sdk-ec2"
SG_RDS = "taller-aws-sdk-rds"
SUBNET_GROUP = "taller-aws-sdk"
DB_ID = "taller-aws-sdk"


def default_vpc():
    vpc = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]["VpcId"]
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc]}])["Subnets"]
    return vpc, [s["SubnetId"] for s in subnets]


def deploy():
    vpc, subnets = default_vpc()

    # 1) S3 (us-east-1 no admite LocationConstraint)
    kwargs = {} if REGION == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": REGION}}
    s3.create_bucket(Bucket=BUCKET, **kwargs)
    s3.put_public_access_block(Bucket=BUCKET, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True,
        "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_tagging(Bucket=BUCKET, Tagging={"TagSet": TAG})
    print("S3 listo:", BUCKET)

    # Red
    sg_ec2 = ec2.create_security_group(GroupName=SG_EC2, Description="EC2 taller", VpcId=vpc)["GroupId"]
    sg_rds = ec2.create_security_group(GroupName=SG_RDS, Description="RDS taller", VpcId=vpc)["GroupId"]
    ec2.authorize_security_group_ingress(GroupId=sg_rds, IpPermissions=[{
        "IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
        "UserIdGroupPairs": [{"GroupId": sg_ec2}]}])

    # 2) EC2
    ami = ssm.get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")["Parameter"]["Value"]
    inst = ec2.run_instances(
        ImageId=ami, InstanceType="t3.micro", MinCount=1, MaxCount=1,
        SubnetId=subnets[0], SecurityGroupIds=[sg_ec2],
        BlockDeviceMappings=[{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 8, "VolumeType": "gp3", "DeleteOnTermination": True}}],
        TagSpecifications=[{"ResourceType": "instance", "Tags": TAG + [{"Key": "Name", "Value": "taller-aws-sdk"}]}],
    )["Instances"][0]["InstanceId"]
    print("EC2 creada:", inst)

    # 3) RDS con contraseña administrada en Secrets Manager
    rds.create_db_subnet_group(DBSubnetGroupName=SUBNET_GROUP, DBSubnetGroupDescription="taller",
                               SubnetIds=subnets, Tags=TAG)
    rds.create_db_instance(
        DBInstanceIdentifier=DB_ID, Engine="postgres", DBInstanceClass="db.t4g.micro",
        AllocatedStorage=20, StorageType="gp3", DBName="taller",
        MasterUsername="taller_admin", ManageMasterUserPassword=True,
        DBSubnetGroupName=SUBNET_GROUP, VpcSecurityGroupIds=[sg_rds],
        PubliclyAccessible=False, MultiAZ=False, BackupRetentionPeriod=0, Tags=TAG)
    print("Esperando a RDS (5-10 min)...")
    rds.get_waiter("db_instance_available").wait(DBInstanceIdentifier=DB_ID)
    db = rds.describe_db_instances(DBInstanceIdentifier=DB_ID)["DBInstances"][0]
    print("RDS:", db["Endpoint"]["Address"])
    print("Secreto:", db["MasterUserSecret"]["SecretArn"])


def destroy():
    # RDS primero (tarda más) -> luego EC2 -> luego SG -> S3
    try:
        rds.delete_db_instance(DBInstanceIdentifier=DB_ID, SkipFinalSnapshot=True, DeleteAutomatedBackups=True)
        print("Esperando eliminación de RDS...")
        rds.get_waiter("db_instance_deleted").wait(DBInstanceIdentifier=DB_ID)
    except ClientError as e:
        print("RDS:", e.response["Error"]["Code"])
    try:
        rds.delete_db_subnet_group(DBSubnetGroupName=SUBNET_GROUP)
    except ClientError as e:
        print("Subnet group:", e.response["Error"]["Code"])

    ids = [i["InstanceId"] for r in ec2.describe_instances(Filters=[
        {"Name": "tag:Name", "Values": ["taller-aws-sdk"]},
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}])["Reservations"]
        for i in r["Instances"]]
    if ids:
        ec2.terminate_instances(InstanceIds=ids)
        ec2.get_waiter("instance_terminated").wait(InstanceIds=ids)
    for name in (SG_RDS, SG_EC2):
        for _ in range(10):
            try:
                gid = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [name]}])["SecurityGroups"]
                if gid:
                    ec2.delete_security_group(GroupId=gid[0]["GroupId"])
                break
            except ClientError as e:
                print(name, e.response["Error"]["Code"], "- reintentando")
                time.sleep(10)
    try:
        s3.delete_bucket(Bucket=BUCKET)
    except ClientError as e:
        print("S3:", e.response["Error"]["Code"])
    print("Eliminación terminada. Verifique con el checklist del README raíz.")


if __name__ == "__main__":
    {"deploy": deploy, "destroy": destroy}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
