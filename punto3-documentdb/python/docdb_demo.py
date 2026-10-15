"""Punto 3 - DocumentDB desde Python (a través del túnel SSH en localhost:27017).

La contraseña se recupera de Secrets Manager en tiempo de ejecución.

    export DOCDB_SECRET_ARN=arn:aws:secretsmanager:...   # salida de terraform output
    export CA_FILE=../scripts/global-bundle.pem
    python docdb_demo.py
"""
import json
import os
import pprint

import boto3
from pymongo import MongoClient

REGION = os.environ.get("AWS_REGION", "us-east-1")
SECRET_ARN = os.environ["DOCDB_SECRET_ARN"]
CA_FILE = os.environ.get("CA_FILE", "global-bundle.pem")
HOST = os.environ.get("DOCDB_HOST", "localhost")  # localhost = extremo del túnel SSH
PORT = int(os.environ.get("DOCDB_PORT", "27017"))

# 1) Credenciales desde Secrets Manager (nada en el código)
secret = json.loads(
    boto3.client("secretsmanager", region_name=REGION).get_secret_value(SecretId=SECRET_ARN)["SecretString"]
)

# 2) Conexión TLS. Con el túnel el nombre del host (localhost) no coincide con el
#    certificado del cluster, por eso tlsAllowInvalidHostnames; la cadena SÍ se valida con el CA bundle.
client = MongoClient(
    host=HOST, port=PORT,
    username=secret["username"], password=secret["password"],
    tls=True, tlsCAFile=CA_FILE, tlsAllowInvalidHostnames=True,
    directConnection=True,   # DocumentDB: hablar con el endpoint, no descubrir réplicas internas
    retryWrites=False,       # DocumentDB no soporta retryable writes
    authSource="admin",
)
print("Versión del servidor:", client.server_info()["version"])

db = client["taller"]
col = db["productos"]
col.drop()

# 3) Al menos diez documentos
productos = [
    {"sku": "P01", "nombre": "Teclado mecánico", "categoria": "perifericos", "precio": 85.0, "stock": 40},
    {"sku": "P02", "nombre": "Mouse inalámbrico", "categoria": "perifericos", "precio": 25.5, "stock": 120},
    {"sku": "P03", "nombre": "Monitor 24\"", "categoria": "pantallas", "precio": 150.0, "stock": 15},
    {"sku": "P04", "nombre": "Monitor 27\"", "categoria": "pantallas", "precio": 230.0, "stock": 9},
    {"sku": "P05", "nombre": "Laptop 14\"", "categoria": "computadores", "precio": 780.0, "stock": 7},
    {"sku": "P06", "nombre": "Laptop 16\"", "categoria": "computadores", "precio": 1150.0, "stock": 4},
    {"sku": "P07", "nombre": "Webcam HD", "categoria": "perifericos", "precio": 45.0, "stock": 60},
    {"sku": "P08", "nombre": "Disco SSD 1TB", "categoria": "almacenamiento", "precio": 70.0, "stock": 85},
    {"sku": "P09", "nombre": "Disco duro 2TB", "categoria": "almacenamiento", "precio": 60.0, "stock": 50},
    {"sku": "P10", "nombre": "Hub USB-C", "categoria": "accesorios", "precio": 32.0, "stock": 200},
    {"sku": "P11", "nombre": "Audífonos", "categoria": "accesorios", "precio": 55.0, "stock": 75},
    {"sku": "P12", "nombre": "Silla ergonómica", "categoria": "mobiliario", "precio": 210.0, "stock": 12},
]
res = col.insert_many(productos)
print(f"\nInsertados: {len(res.inserted_ids)} documentos")

# 4) Búsqueda con filtro
print("\n--- Filtro: precio > 100 y stock >= 5 ---")
for d in col.find({"precio": {"$gt": 100}, "stock": {"$gte": 5}}, {"_id": 0, "nombre": 1, "precio": 1, "stock": 1}):
    print(d)

# 5) Ordenación
print("\n--- Orden: 5 productos más baratos ---")
for d in col.find({}, {"_id": 0, "nombre": 1, "precio": 1}).sort("precio", 1).limit(5):
    print(d)

# 6) Agregación: valor de inventario y precio medio por categoría
print("\n--- Agregación por categoría ---")
pipeline = [
    {"$group": {
        "_id": "$categoria",
        "productos": {"$sum": 1},
        "precio_medio": {"$avg": "$precio"},
        "valor_inventario": {"$sum": {"$multiply": ["$precio", "$stock"]}},
    }},
    {"$sort": {"valor_inventario": -1}},
]
for d in col.aggregate(pipeline):
    d["precio_medio"] = round(d["precio_medio"], 2)
    pprint.pprint(d)

client.close()
