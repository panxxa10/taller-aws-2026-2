"""Punto 6 - S3 + Glue Data Catalog (crawler) + Athena, con Boto3.

    python glue_athena.py setup      # bucket, rol IAM, sube ventas.csv, crea DB y crawler
    python glue_athena.py crawl      # ejecuta el crawler y muestra el esquema inferido
    python glue_athena.py fixschema  # corrige tipos (fecha -> date) editando la tabla del catálogo
    python glue_athena.py query      # consultas con filtro y agrupación en Athena
    python glue_athena.py add        # sube ventas_nuevas.csv, re-ejecuta el crawler y verifica
    python glue_athena.py manual     # crea una tabla equivalente a mano (sin crawler) para comparar
    python glue_athena.py cleanup    # elimina todo

No hay credenciales de aplicación: el crawler usa un rol IAM y Athena el usuario IAM del que llama.
"""
import json
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "us-east-1")
HERE = os.path.dirname(__file__)
session = boto3.Session(region_name=REGION)
account = session.client("sts").get_caller_identity()["Account"]
s3, iam, glue, athena = (session.client(x) for x in ("s3", "iam", "glue", "athena"))

BUCKET = f"taller-aws-glue-{account}-{REGION}"
PREFIX = "ventas/"
DB = "taller_ventas"
CRAWLER = "taller-ventas-crawler"
ROLE = "taller-glue-crawler-role"
TABLE = "ventas"            # el crawler nombra la tabla según la carpeta (prefijo)
TABLE_MANUAL = "ventas_manual"
OUT = f"s3://{BUCKET}/athena-results/"

TRUST = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
         "Principal": {"Service": "glue.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
S3_READ = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
           "Action": ["s3:GetObject", "s3:ListBucket"],
           "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/{PREFIX}*"]}]}


def setup():
    kw = {} if REGION == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": REGION}}
    s3.create_bucket(Bucket=BUCKET, **kw)
    s3.upload_file(os.path.join(HERE, "..", "data", "ventas.csv"), BUCKET, PREFIX + "ventas.csv")

    arn = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(TRUST))["Role"]["Arn"]
    iam.attach_role_policy(RoleName=ROLE, PolicyArn="arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole")
    iam.put_role_policy(RoleName=ROLE, PolicyName="lectura-datos", PolicyDocument=json.dumps(S3_READ))
    time.sleep(10)

    glue.create_database(DatabaseInput={"Name": DB, "Description": "Taller AWS punto 6"})
    glue.create_crawler(Name=CRAWLER, Role=arn, DatabaseName=DB,
                        Targets={"S3Targets": [{"Path": f"s3://{BUCKET}/{PREFIX}"}]},
                        SchemaChangePolicy={"UpdateBehavior": "UPDATE_IN_DATABASE", "DeleteBehavior": "LOG"})
    print("Listo:", BUCKET, DB, CRAWLER)


def crawl():
    try:
        glue.start_crawler(Name=CRAWLER)
    except ClientError as e:
        if e.response["Error"]["Code"] != "CrawlerRunningException":
            raise
    while glue.get_crawler(Name=CRAWLER)["Crawler"]["State"] != "READY":
        time.sleep(10)
    last = glue.get_crawler(Name=CRAWLER)["Crawler"]["LastCrawl"]
    print("Crawler:", last["Status"])
    show_schema(TABLE)


def show_schema(table):
    t = glue.get_table(DatabaseName=DB, Name=table)["Table"]
    print(f"Tabla {table} | formato: {t['StorageDescriptor']['SerdeInfo']['SerializationLibrary']}")
    for c in t["StorageDescriptor"]["Columns"]:
        print(f"  {c['Name']:<18} {c['Type']}")


def fixschema():
    """El crawler infiere 'fecha' como string; se corrige a date en el catálogo."""
    t = glue.get_table(DatabaseName=DB, Name=TABLE)["Table"]
    sd = t["StorageDescriptor"]
    for c in sd["Columns"]:
        if c["Name"] == "fecha":
            c["Type"] = "date"
    keys = ("Name", "Description", "Owner", "Retention", "StorageDescriptor", "PartitionKeys",
            "TableType", "Parameters")
    glue.update_table(DatabaseName=DB, TableInput={k: t[k] for k in keys if k in t})
    show_schema(TABLE)


def run_query(sql, db=DB):
    qid = athena.start_query_execution(QueryString=sql, QueryExecutionContext={"Database": db},
                                       ResultConfiguration={"OutputLocation": OUT})["QueryExecutionId"]
    while True:
        st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        if st["Status"]["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
    if st["Status"]["State"] != "SUCCEEDED":
        raise RuntimeError(st["Status"].get("StateChangeReason"))
    scanned = st["Statistics"]["DataScannedInBytes"]
    rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
    for r in rows:
        print(" | ".join(c.get("VarCharValue", "") for c in r["Data"]))
    print(f"-- datos escaneados: {scanned} bytes (Athena factura mínimo 10 MB por consulta)\n")


def query(table=TABLE):
    print("Filtro: ventas de Medellin con más de 10 unidades")
    run_query(f"SELECT id_venta, producto, cantidad FROM {table} WHERE ciudad = 'Medellin' AND cantidad > 10 ORDER BY cantidad DESC")
    print("Agrupación: ingresos y unidades por ciudad")
    run_query(f"SELECT ciudad, COUNT(*) AS ventas, SUM(cantidad) AS unidades, ROUND(SUM(cantidad*precio_unitario),2) AS ingresos FROM {table} GROUP BY ciudad ORDER BY ingresos DESC")
    print("Total de registros")
    run_query(f"SELECT COUNT(*) AS registros FROM {table}")


def add():
    print("Antes:")
    run_query(f"SELECT COUNT(*) AS registros FROM {TABLE}")
    s3.upload_file(os.path.join(HERE, "..", "data", "ventas_nuevas.csv"), BUCKET, PREFIX + "ventas_nuevas.csv")
    crawl()   # actualiza el catálogo
    print("Después:")
    run_query(f"SELECT COUNT(*) AS registros FROM {TABLE}")


def manual():
    """Tabla equivalente creada a mano: control total del esquema, sin crawler."""
    glue.create_table(DatabaseName=DB, TableInput={
        "Name": TABLE_MANUAL, "TableType": "EXTERNAL_TABLE",
        "Parameters": {"classification": "csv", "skip.header.line.count": "1"},
        "StorageDescriptor": {
            "Columns": [{"Name": "id_venta", "Type": "int"}, {"Name": "fecha", "Type": "date"},
                        {"Name": "ciudad", "Type": "string"}, {"Name": "producto", "Type": "string"},
                        {"Name": "cantidad", "Type": "int"}, {"Name": "precio_unitario", "Type": "double"}],
            "Location": f"s3://{BUCKET}/{PREFIX}",
            "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
            "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe",
                          "Parameters": {"field.delim": ",", "skip.header.line.count": "1"}}}})
    show_schema(TABLE_MANUAL)
    query(TABLE_MANUAL)


def cleanup():
    for fn in (lambda: glue.delete_crawler(Name=CRAWLER),
               lambda: glue.delete_database(Name=DB),     # borra también sus tablas del catálogo
               lambda: iam.detach_role_policy(RoleName=ROLE, PolicyArn="arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"),
               lambda: iam.delete_role_policy(RoleName=ROLE, PolicyName="lectura-datos"),
               lambda: iam.delete_role(RoleName=ROLE)):
        try:
            fn()
        except ClientError as e:
            print(e.response["Error"]["Code"])
    try:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET):
            for o in page.get("Contents", []):
                s3.delete_object(Bucket=BUCKET, Key=o["Key"])
        s3.delete_bucket(Bucket=BUCKET)
    except ClientError as e:
        print(e.response["Error"]["Code"])
    print("Eliminado. Verifique: glue get-databases, glue get-crawlers, aws s3 ls.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"setup": setup, "crawl": crawl, "fixschema": fixschema, "query": query,
     "add": add, "manual": manual, "cleanup": cleanup}.get(cmd, lambda: print(__doc__))()
