# Punto 6 – AWS Glue Data Catalog + Athena

## 1. Qué almacena Glue Data Catalog

Un **catálogo de metadatos** (no datos): para cada conjunto de datos guarda _dónde está_ (ruta S3), _cómo se lee_ (formato/SerDe: CSV, JSON, Parquet) y _qué forma tiene_ (columnas, tipos, particiones). Es un metastore compatible con Hive que usan Athena, EMR, Redshift Spectrum y Glue ETL.

| Concepto                     | Qué es                                                                                                                                            |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Datos en S3**              | Los archivos reales (`ventas.csv`). Siguen siendo solo archivos.                                                                                  |
| **Metadatos en el catálogo** | La definición de tabla que apunta a esos archivos. Borrar la tabla **no** borra los archivos; borrar los archivos deja la tabla apuntando a nada. |
| **Base de datos**            | Contenedor lógico de tablas (un esquema/namespace).                                                                                               |
| **Tabla**                    | Esquema + ubicación + formato de un conjunto de archivos.                                                                                         |
| **Crawler**                  | Proceso que explora una ruta, **infiere** el esquema/formato y crea o actualiza tablas en el catálogo.                                            |

## 2. Práctica

Código: [python/glue_athena.py](python/glue_athena.py). Datos: [ventas.csv](data/ventas.csv) (**25 registros**) y [ventas_nuevas.csv](data/ventas_nuevas.csv) (5).

```bash
export AWS_REGION=us-east-1   # con las claves de user_cli configuradas
cd python
python glue_athena.py setup       # bucket + rol del crawler + subida + base de datos + crawler
python glue_athena.py crawl       # descubre el esquema (revisar la salida)
python glue_athena.py fixschema   # corrige tipos inferidos
python glue_athena.py query       # Athena: filtro + agrupación
python glue_athena.py add         # sube 5 registros nuevos, re-ejecuta el crawler, cuenta 25 -> 30
python glue_athena.py manual      # tabla creada a mano para comparar
python glue_athena.py cleanup
```

**Resultado real del crawler (15-oct-2026)** sobre `ventas.csv` (25 registros): detectó el encabezado y el formato `LazySimpleSerDe` (CSV), y clasificó así las columnas:

| Columna              | Tipo inferido | ¿Correcto?                                                       |
| -------------------- | ------------- | ---------------------------------------------------------------- |
| `id_venta`           | `bigint`      | Sí                                                               |
| `fecha`              | **`string`**  | **No**: debería ser `date` (el crawler no infiere `date` en CSV) |
| `ciudad`, `producto` | `string`      | Sí                                                               |
| `cantidad`           | `bigint`      | Sí                                                               |
| `precio_unitario`    | `double`      | Sí                                                               |

**Corrección:** `fixschema` cambia `fecha` a `date` en el catálogo (`update_table`); alternativa sin tocar el catálogo: `DATE(fecha)` en cada consulta.

**Hallazgo al agregar datos:** tras subir `ventas_nuevas.csv` y re-ejecutar el crawler (`UpdateBehavior: UPDATE_IN_DATABASE`), el esquema volvió a mostrar `fecha` como `string`: **el crawler sobrescribe las correcciones manuales del catálogo**. Opciones: reaplicar `fixschema` tras cada crawl, configurar `UpdateBehavior: LOG` (el crawler solo registra cambios) o usar una tabla definida a mano (`ventas_manual`).
**Consultas Athena**

1. Filtro: ventas de Medellín con más de 10 unidades.
2. Agrupación: ventas, unidades e ingresos por ciudad.
3. Conteo (25 antes de agregar; **30** tras `add`).

**Agregar registros y actualizar el catálogo:** al subir `ventas_nuevas.csv` al mismo prefijo, Athena ya lo lee (los datos son archivos); el crawler solo es necesario si cambian esquema o particiones, pero se re-ejecuta para verificar que el catálogo queda consistente.

### Crawler vs tabla manual

|                       | Crawler                                  | Tabla manual                      |
| --------------------- | ---------------------------------------- | --------------------------------- |
| Esfuerzo              | Bajo, automático                         | Hay que escribir columnas y SerDe |
| Precisión de tipos    | Puede inferir mal (fecha → string)       | Total                             |
| Costo                 | Se cobra por tiempo de ejecución (DPU-h) | Sin costo de cómputo              |
| Evolución del esquema | Detecta columnas nuevas y particiones    | Hay que actualizar a mano         |
| Ideal                 | Datos desconocidos / cambiantes          | Esquema estable y conocido        |

## 3. ¿Requiere credenciales de aplicación?

**No.** Todo se hace con **permisos IAM**: el _crawler_ asume un rol (`taller-glue-crawler-role`) con `AWSGlueServiceRole` + lectura del prefijo S3, y Athena usa el usuario IAM que ejecuta la consulta (con acceso a Glue, al bucket de datos y al de resultados). No hay ninguna contraseña de base de datos ni cadena de conexión JDBC, así que **no hace falta crear otro secreto en Secrets Manager**. Solo si se agregara una _conexión_ a una fuente con usuario/contraseña (p. ej. un crawler JDBC contra RDS) esa credencial se guardaría en Secrets Manager.

## 4. Preguntas de costos (us-east-1, ref.)

| Servicio     | Cobro                                                                            | Aquí                                      |
| ------------ | -------------------------------------------------------------------------------- | ----------------------------------------- |
| Crawler      | ~0,44 US$/DPU-hora, por segundo, **mínimo 10 min por ejecución**                 | 2 ejecuciones ≈ 0,15 US$ (2 DPU × 10 min) |
| Data Catalog | Gratis hasta 1 M de objetos y 1 M de solicitudes/mes; luego ~1 US$/100 k objetos | 2 tablas → 0                              |
| S3           | ~0,023 US$/GB-mes + solicitudes                                                  | KB → ~0                                   |
| Athena       | **~5 US$ por TB escaneado**, mínimo **10 MB por consulta**                       | ~6 consultas × 10 MB = 60 MB ≈ 0,0003 US$ |

**Efecto del volumen escaneado:** Athena cobra por bytes leídos, no por filas devueltas. `SELECT *` sobre CSV lee todo; usar **Parquet/ORC** (columnar y comprimido), **particionar** (p. ej. por fecha) y seleccionar solo las columnas necesarias reduce el costo hasta 90–99 %. Con datos diminutos el mínimo de 10 MB domina.

**Total estimado: ≈ US$0,15–0,20**, casi todo del crawler.

## 5. Incidente / hallazgos
- El permiso del crawler requiere crear un rol (`IAMFullAccess` temporal para `user_cli`) además de Glue y Athena.
- El crawler infirió `fecha` como `string` y **sobrescribió** la corrección manual al re-ejecutarse (ver sección 2).

## 6. Evidencias ([evidencias](evidencias))
- [01_crawler_esquema_inferido.png](evidencias/01_crawler_esquema_inferido.png): archivo en S3, base de datos/tabla y esquema inferido por el crawler.
- [02_fixschema_y_consultas_athena.png](evidencias/02_fixschema_y_consultas_athena.png): esquema corregido y consultas de filtro y agrupación en Athena.
- [03_add_registros_y_recrawl.png](evidencias/03_add_registros_y_recrawl.png): nuevos registros, re-ejecución del crawler y conteo 25 → 30.
- [04_tabla_manual.png](evidencias/04_tabla_manual.png): tabla creada a mano y su consulta.
- [05_verificacion_global_final.png](evidencias/05_verificacion_global_final.png): `cleanup` y listados vacíos.
