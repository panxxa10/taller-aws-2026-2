"""Punto 4 - Grafo en Neptune con Gremlin (gremlinpython).

Acceso desde local mediante túnel SSH:
    ssh -i ~/.ssh/taller-neptune -N -L 8182:<ENDPOINT>:8182 ec2-user@<IP_EC2>
y en /etc/hosts (Windows: C:\\Windows\\System32\\drivers\\etc\\hosts):
    127.0.0.1  <ENDPOINT>
Así el nombre del endpoint resuelve al túnel y el certificado TLS de Neptune se valida con normalidad.

    export NEPTUNE_ENDPOINT=taller-neptune.cluster-xxxx.us-east-1.neptune.amazonaws.com
    python neptune_graph.py
"""
import os

from gremlin_python.driver.client import Client
from gremlin_python.driver.serializer import GraphSONSerializersV3d0
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T, Order, P

ENDPOINT = os.environ["NEPTUNE_ENDPOINT"]
URL = f"wss://{ENDPOINT}:8182/gremlin"

conn = DriverRemoteConnection(URL, "g")
g = traversal().withRemote(conn)

# --- Modelo: 10 personas (vértices) y 15 relaciones (aristas) ---
personas = {
    "ana": ("Ana", "Medellin", 29), "bruno": ("Bruno", "Bogota", 34),
    "carla": ("Carla", "Medellin", 27), "diego": ("Diego", "Cali", 41),
    "elena": ("Elena", "Bogota", 31), "felipe": ("Felipe", "Medellin", 38),
    "gina": ("Gina", "Cali", 26), "hugo": ("Hugo", "Bogota", 45),
    "irene": ("Irene", "Medellin", 33), "jorge": ("Jorge", "Cali", 30),
}
relaciones = [
    ("ana", "bruno", "CONOCE", 2018), ("ana", "carla", "CONOCE", 2015), ("ana", "diego", "TRABAJA_CON", 2020),
    ("bruno", "elena", "CONOCE", 2019), ("bruno", "hugo", "TRABAJA_CON", 2017), ("carla", "felipe", "CONOCE", 2016),
    ("carla", "irene", "CONOCE", 2021), ("diego", "gina", "CONOCE", 2022), ("diego", "jorge", "TRABAJA_CON", 2019),
    ("elena", "hugo", "CONOCE", 2014), ("felipe", "irene", "TRABAJA_CON", 2018), ("gina", "jorge", "CONOCE", 2023),
    ("hugo", "jorge", "CONOCE", 2020), ("irene", "ana", "CONOCE", 2017), ("felipe", "hugo", "TRABAJA_CON", 2021),
]

g.V().drop().toList()  # empezar limpio
for pid, (nombre, ciudad, edad) in personas.items():
    g.addV("persona").property(T.id, pid).property("nombre", nombre).property("ciudad", ciudad).property("edad", edad).toList()
for i, (a, b, tipo, desde) in enumerate(relaciones, 1):
    g.V(a).addE(tipo).to(__.V(b)).property("desde", desde).toList()

print(f"Vértices: {g.V().count().next()}  Aristas: {g.E().count().next()}")

# --- Consulta 1: amigos de amigos de Ana (2 saltos, sin repetir ni incluir a Ana ni a sus conocidos directos) ---
print("\n1) Amigos de amigos de Ana (CONOCE x2):")
directos = g.V("ana").out("CONOCE").id_().toList()
fof = (g.V("ana").out("CONOCE").out("CONOCE").dedup()
        .has(T.id, P.without(directos + ["ana"])).values("nombre").toList())
print("  ", fof)

# --- Consulta 2: camino más corto de Ana a Jorge (cualquier tipo de relación, sin importar dirección) ---
print("\n2) Camino más corto Ana -> Jorge:")
camino = (g.V("ana").repeat(__.both().simplePath()).until(__.hasId("jorge")).path().by("nombre").limit(1).next())
print("  ", " -> ".join(camino), f"({len(camino) - 1} saltos)")

# --- Consulta 3: personas más conectadas (grado de entrada+salida) y su ciudad ---
print("\n3) Top 3 más conectados:")
top = (g.V().project("nombre", "ciudad", "conexiones").by("nombre").by("ciudad").by(__.bothE().count())
        .order().by("conexiones", Order.desc).limit(3).toList())
for fila in top:
    print("  ", fila)

# --- Consulta extra: colegas de trabajo de los que viven en Cali ---
print("\n4) Quién TRABAJA_CON alguien de Cali:")
res = g.V().has("persona", "ciudad", "Cali").in_("TRABAJA_CON").dedup().values("nombre").toList()
print("  ", res)

conn.close()
