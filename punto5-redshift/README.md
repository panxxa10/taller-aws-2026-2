# Punto 5 – Amazon Redshift

## 1. Qué es, para qué sirve y componentes
**Amazon Redshift** es un *data warehouse* en la nube: almacena datos en **columnas** y los procesa con **MPP** (procesamiento masivamente paralelo) para ejecutar consultas SQL analíticas (OLAP) sobre millones/miles de millones de filas: reportes, BI, agregaciones históricas.

**Componentes principales:** *cluster* (nodo líder + nodos de cómputo, con *slices*) o **workgroup + namespace** en Serverless; almacenamiento columnar (Redshift Managed Storage); **COPY** (carga masiva desde S3); **Spectrum** (consultar S3 sin cargar); **Data API** (SQL por HTTPS sin conexiones persistentes); **Query Editor v2**; claves de distribución/ordenamiento; WLM/escalado de concurrencia.

## 2. Redshift vs RDS

| | Redshift | RDS |
|---|---|---|
| Carga | **OLAP**: pocas consultas pesadas, lecturas masivas | **OLTP**: muchas transacciones pequeñas |
| Almacenamiento | Columnar | Por filas |
| Escala | TB–PB | GB–pocos TB |
| Caso | Dashboard de ventas de 5 años agrupado por región/producto | Backend de una tienda: crear pedido, descontar stock |

## 3. Despliegue de menor costo: Serverless vs aprovisionada

| (us-east-1, ref.) | Serverless | Aprovisionada (dc2.large / ra3) |
|---|---|---|
| Unidad | RPU-hora; mínimo 4 RPU ≈ 0,375 US$/RPU-h → **1,50 US$/h solo mientras ejecuta consultas** (facturación por segundo, mínimo 60 s) | Nodo `dc2.large` ≈ 0,25 US$/h (según disponibilidad en la región) o `ra3.xlplus` ≈ 1,09 US$/h, **encendido 24/7** |
| Inactividad | No cobra cómputo | Cobra todo el tiempo |
| Almacenamiento | ~0,024 US$/GB-mes (RMS) | dc2: incluido en el nodo; ra3: ~0,024 US$/GB-mes |

**Elección: Redshift Serverless** (4 RPU base, tope 8). El taller son ~3 consultas de segundos con datos diminutos: Serverless cobra solo esos segundos (≈ 5 min de actividad → ≈ US$0,13), mientras que una aprovisionada cobra la hora completa desde que está disponible (≥ US$0,25 y ~5 min de creación). Si el cluster se dejara encendido más de ~1 h o hubiera carga continua, la aprovisionada resultaría más barata. *Verificar tarifas actuales y la prueba gratuita en calculator.aws.*

La contraseña del administrador la gestiona Secrets Manager (`manageAdminPassword=True`).

## 4. Programa (Boto3 + Data API)
- [infra/deploy_redshift.py](infra/deploy_redshift.py): bucket S3, **rol IAM** que Redshift asume para leer S3 (permisos `s3:GetObject`, `s3:ListBucket` del bucket del taller), namespace con admin en Secrets Manager y workgroup privado.
- [python/redshift_pipeline.py](python/redshift_pipeline.py): sube los CSV a S3 → crea tablas → `COPY` → consultas, enviando todo por la **Data API** (`execute_statement` → `describe_statement` hasta `FINISHED` → `get_statement_result`) autenticado con `SecretArn`.
- Datos: [clientes.csv](data/clientes.csv) (8) y [pedidos.csv](data/pedidos.csv) (30) relacionados por `cliente_id`.

```bash
export AWS_REGION=us-east-1   # con las claves de user_cli configuradas
python infra/deploy_redshift.py deploy       # ~3-5 min
python python/redshift_pipeline.py
python infra/deploy_redshift.py destroy
```

## 5. Consultas y su interpretación

| # | Pregunta de negocio | Tipo |
|---|---|---|
| Q1 | ¿Qué pedidos superan 200 USD y de qué producto son? | Filtro |
| Q2 | ¿Cuánto vende cada ciudad y cuántos pedidos tiene? | Unión + agregación |
| Q3 | ¿Cuál es el ticket medio por segmento en el primer trimestre? | Filtro + unión + agregación |

**Datos cargados con `COPY`:** `clientes` 8 filas, `pedidos` 30 filas (captura [02](evidencias/02_pipeline_resultados.png)).

**Resultados e interpretación**

- **Q1 (filtro):** 12 pedidos superan 200 USD: 5 Laptop, 3 Monitor, 3 Silla y 1 Disco SSD. Pocos productos (laptops y monitores sobre todo) concentran los pedidos de valor alto.
- **Q2 (unión + agregación):**

| Ciudad | Pedidos | Ventas (USD) | Ticket medio (USD) |
|---|---|---|---|
| Medellín | 11 | 3.088,50 | ≈ 280,77 |
| Bogotá | 12 | 2.931,50 | ≈ 244,29 |
| Cali | 7 | 2.025,00 | ≈ 289,29 |

  Medellín lidera en ventas totales; Bogotá en número de pedidos; Cali tiene pocos pedidos pero el ticket medio más alto.
- **Q3 (filtro + unión + agregación, 1.er trimestre):**

| Segmento | Pedidos | Ticket medio (USD) |
|---|---|---|
| Premium | 9 | 324,33 |
| Estándar | 9 | 189,05 |

  Con el mismo número de pedidos, el ticket de los clientes Premium es ≈ 1,7 veces el de Estándar: el segmento Premium aporta mucho más ingreso por pedido.

**Cliente SQL desde el computador (opcional):** hay que poner el workgroup con `publiclyAccessible=True`, abrir el SG del workgroup en TCP **5439** solo a *mi IP/32*, tener una tabla de rutas con Internet Gateway en las subredes y conectar con el endpoint y el usuario/contraseña del secreto. Más seguro: Query Editor v2 (sin abrir puertos).

## 6. Preguntas de costos
- **Modalidad más barata para esta práctica:** Serverless (paga por segundos de consulta).
- **Cómo se cobran:** cómputo = RPU-horas por segundo (Serverless) u horas-nodo (aprovisionada); almacenamiento = GB-mes de datos (ínfimo aquí); backups/snapshots por encima del tamaño del cluster; Data API sin costo adicional (se paga el cómputo).
- **Pueden seguir cobrando:** el workgroup (si hay consultas), el almacenamiento del namespace, **snapshots/recovery points** (se eliminan con el namespace o aparte), el bucket S3 con datos, el secreto administrado (~0,40 US$/mes, se borra con el namespace) y, si se usó acceso público, la IPv4/Elastic IP.
- **Estimación del taller:** ≈ US$0,15–0,30 en total.

## 7. Incidente
El primer `deploy` falló con `ConflictException ... Amazon Redshift can't access the secret`: faltaba el permiso `SecretsManagerReadWrite` para `user_cli` (necesario con `manageAdminPassword`). Se destruyó el despliegue parcial, se añadió la política y se repitió.

## 8. Evidencias ([evidencias](evidencias))
- [01_deploy_redshift.png](evidencias/01_deploy_redshift.png): creación de bucket, rol IAM, namespace y workgroup.
- [02_pipeline_resultados.png](evidencias/02_pipeline_resultados.png): subida a S3, `COPY`, conteos y las 3 consultas por Data API.
- [03_destroy_y_verificacion.png](evidencias/03_destroy_y_verificacion.png): `destroy` y listados vacíos.
- Precios verificados (oct-2026): Serverless 0,375 US$/RPU-h, mínimo 4 RPU, mínimo 60 s; RMS 0,024 US$/GB-mes.
