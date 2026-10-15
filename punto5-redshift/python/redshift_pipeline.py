"""Punto 5 - Pipeline S3 -> Redshift (COPY) -> consultas, todo vía Redshift Data API.

Lee la configuración de ../.env.local (generado por infra/deploy_redshift.py).
Autenticación: el SecretArn de Secrets Manager; no hay contraseña en el código.
"""
import os
import time

import boto3

HERE = os.path.dirname(__file__)
cfg = dict(l.strip().split("=", 1) for l in open(os.path.join(HERE, "..", ".env.local")) if "=" in l)
REGION = os.environ.get("AWS_REGION", "us-east-1")

s3 = boto3.client("s3", region_name=REGION)
data = boto3.client("redshift-data", region_name=REGION)

COMMON = dict(WorkgroupName=cfg["WORKGROUP"], Database=cfg["DATABASE"], SecretArn=cfg["SECRET_ARN"])


def run(sql: str, show: bool = True):
    """Envía SQL, espera a que termine y devuelve las filas (si hay)."""
    stmt_id = data.execute_statement(Sql=sql, **COMMON)["Id"]
    while True:
        d = data.describe_statement(Id=stmt_id)
        if d["Status"] in ("FINISHED", "FAILED", "ABORTED"):
            break
        time.sleep(1)
    if d["Status"] != "FINISHED":
        raise RuntimeError(f"{d['Status']}: {d.get('Error')}\nSQL: {sql}")
    if not d.get("HasResultSet"):
        return []
    res = data.get_statement_result(Id=stmt_id)
    cols = [c["name"] for c in res["ColumnMetadata"]]
    rows = [[list(v.values())[0] if v else None for v in r] for r in res["Records"]]
    if show:
        print(" | ".join(cols))
        for r in rows:
            print(" | ".join(str(x) for x in r))
    return rows


# 1) Subir archivos a S3
for name in ("clientes.csv", "pedidos.csv"):
    s3.upload_file(os.path.join(HERE, "..", "data", name), cfg["BUCKET"], f"datos/{name}")
print("Archivos subidos a s3://%s/datos/" % cfg["BUCKET"])

# 2) Crear tablas (relacionadas por cliente_id)
run("DROP TABLE IF EXISTS pedidos; DROP TABLE IF EXISTS clientes;", show=False)
run("""CREATE TABLE clientes (
         cliente_id INT PRIMARY KEY, nombre VARCHAR(60), ciudad VARCHAR(40), segmento VARCHAR(20))""", show=False)
run("""CREATE TABLE pedidos (
         pedido_id INT PRIMARY KEY, cliente_id INT REFERENCES clientes(cliente_id),
         fecha DATE, producto VARCHAR(40), cantidad INT, valor DECIMAL(10,2))""", show=False)

# 3) COPY desde S3 usando el rol IAM asociado al namespace
for tabla in ("clientes", "pedidos"):
    run(f"""COPY {tabla} FROM 's3://{cfg['BUCKET']}/datos/{tabla}.csv'
            IAM_ROLE '{cfg['ROLE_ARN']}' FORMAT AS CSV IGNOREHEADER 1 DATEFORMAT 'YYYY-MM-DD'""", show=False)
    print(tabla, "->", run(f"SELECT COUNT(*) FROM {tabla}", show=False)[0][0], "filas")

# 4) Consultas
print("\nQ1 (filtro): ¿Qué pedidos superan los 200 USD y de qué producto son?")
run("SELECT pedido_id, producto, valor FROM pedidos WHERE valor > 200 ORDER BY valor DESC")

print("\nQ2 (unión): ¿Cuánto vende cada ciudad y cuántos pedidos tiene?")
run("""SELECT c.ciudad, COUNT(*) AS pedidos, SUM(p.valor) AS total
       FROM pedidos p JOIN clientes c ON c.cliente_id = p.cliente_id
       GROUP BY c.ciudad ORDER BY total DESC""")

print("\nQ3 (filtro + unión + agregación): ¿Cuál es el ticket medio por segmento en el primer trimestre?")
run("""SELECT c.segmento, COUNT(*) AS pedidos, ROUND(AVG(p.valor), 2) AS ticket_medio
       FROM pedidos p JOIN clientes c ON c.cliente_id = p.cliente_id
       WHERE p.fecha BETWEEN '2026-01-01' AND '2026-03-31'
       GROUP BY c.segmento ORDER BY ticket_medio DESC""")
