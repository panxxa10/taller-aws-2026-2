"""Punto 5 - Infraestructura de Redshift Serverless con Boto3.

    python deploy_redshift.py deploy    # crea bucket, rol IAM, namespace y workgroup
    python deploy_redshift.py destroy   # elimina todo

La contraseña de administración la crea y guarda Redshift en Secrets Manager
(manageAdminPassword=True). El ARN del secreto se escribe en ../.env.local (ignorado por git).
"""
import json
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "us-east-1")
TAGS = [{"key": "Proyecto", "value": "taller-aws"}]

session = boto3.Session(region_name=REGION)
account = session.client("sts").get_caller_identity()["Account"]
iam = session.client("iam")
s3 = session.client("s3")
ec2 = session.client("ec2")
rs = session.client("redshift-serverless")

BUCKET = f"taller-aws-redshift-{account}-{REGION}"
ROLE = "taller-redshift-s3-lectura"
NAMESPACE = "taller-ns"
WORKGROUP = "taller-wg"
ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env.local")

TRUST = {"Version": "2012-10-17", "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": ["redshift.amazonaws.com", "redshift-serverless.amazonaws.com"]},
    "Action": "sts:AssumeRole"}]}

READ_S3 = {"Version": "2012-10-17", "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"],
    "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"]}]}


def deploy():
    kwargs = {} if REGION == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": REGION}}
    s3.create_bucket(Bucket=BUCKET, **kwargs)
    s3.put_public_access_block(Bucket=BUCKET, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})

    role_arn = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(TRUST))["Role"]["Arn"]
    iam.put_role_policy(RoleName=ROLE, PolicyName="lectura-bucket-taller", PolicyDocument=json.dumps(READ_S3))
    time.sleep(10)  # propagación del rol

    ns = rs.create_namespace(
        namespaceName=NAMESPACE, dbName="dev", adminUsername="admin",
        manageAdminPassword=True,            # <- contraseña en Secrets Manager
        iamRoles=[role_arn], tags=TAGS)["namespace"]
    secret_arn = ns["adminPasswordSecretArn"]

    vpc = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]["VpcId"]
    subnets = [s["SubnetId"] for s in ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc]}])["Subnets"]]
    rs.create_workgroup(
        workgroupName=WORKGROUP, namespaceName=NAMESPACE,
        baseCapacity=4,                      # mínimo: 4 RPU (Serverless factura por segundo mientras hay actividad)
        maxCapacity=8,                       # tope de gasto
        publiclyAccessible=False, subnetIds=subnets, tags=TAGS)
    print("Esperando workgroup...")
    while True:
        st = rs.get_workgroup(workgroupName=WORKGROUP)["workgroup"]["status"]
        if st == "AVAILABLE":
            break
        time.sleep(15)

    with open(ENV_FILE, "w") as f:
        f.write(f"BUCKET={BUCKET}\nWORKGROUP={WORKGROUP}\nSECRET_ARN={secret_arn}\nROLE_ARN={role_arn}\nDATABASE=dev\n")
    print("Listo. Variables en", os.path.abspath(ENV_FILE))


def destroy():
    for fn, kw in ((rs.delete_workgroup, {"workgroupName": WORKGROUP}),):
        try:
            fn(**kw)
        except ClientError as e:
            print(e.response["Error"]["Code"])
    while True:
        try:
            rs.get_workgroup(workgroupName=WORKGROUP)
            time.sleep(15)
        except ClientError:
            break
    try:
        rs.delete_namespace(namespaceName=NAMESPACE)  # el secreto administrado se elimina con el namespace
    except ClientError as e:
        print(e.response["Error"]["Code"])

    try:
        iam.delete_role_policy(RoleName=ROLE, PolicyName="lectura-bucket-taller")
        iam.delete_role(RoleName=ROLE)
    except ClientError as e:
        print(e.response["Error"]["Code"])

    try:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET):
            for o in page.get("Contents", []):
                s3.delete_object(Bucket=BUCKET, Key=o["Key"])
        s3.delete_bucket(Bucket=BUCKET)
    except ClientError as e:
        print(e.response["Error"]["Code"])
    if os.path.exists(ENV_FILE):
        os.remove(ENV_FILE)
    print("Eliminado. Verifique: list-workgroups, list-namespaces, list-secrets, aws s3 ls.")


if __name__ == "__main__":
    {"deploy": deploy, "destroy": destroy}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
