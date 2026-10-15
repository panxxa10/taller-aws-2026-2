# Punto 1 – AWS Secrets Manager

## 1. Investigación

**Qué es.** Servicio administrado para almacenar, controlar el acceso y rotar secretos (credenciales de bases de datos, API keys, tokens, certificados en texto) cifrados con AWS KMS. Evita dejar contraseñas en código, variables de entorno o repositorios.

**Qué permite guardar.** Texto o binario de hasta 64 KB: normalmente un JSON (`{"username": "...", "password": "..."}`), claves de API, tokens OAuth, cadenas de conexión. Cada cambio crea una **versión** identificada por etiquetas de etapa: `AWSCURRENT` (vigente), `AWSPREVIOUS`, `AWSPENDING` (durante rotación).

**Quién puede leerlo.** Se controla con:
1. **Políticas IAM** (identidad): `secretsmanager:GetSecretValue` sobre el ARN del secreto. Ver [policy_lectura_secreto.json](policy_lectura_secreto.json).
2. **Política de recurso** adjunta al secreto (útil entre cuentas).
3. **KMS**: con la clave administrada `aws/secretsmanager` basta el permiso del secreto; con una clave propia también se requiere `kms:Decrypt`.

**Crear, recuperar y rotar – son operaciones distintas**

| Operación | Quién/qué | API típica |
|---|---|---|
| Crear | Administrador / IaC | `CreateSecret`, `PutSecretValue` |
| Recuperar | Aplicación en ejecución | `GetSecretValue` (por defecto `AWSCURRENT`) |
| Rotar | Lambda programada por Secrets Manager (o rotación administrada para algunos servicios) que cambia la contraseña **en la base de datos y en el secreto** | `RotateSecret` |

Crear/actualizar cambia el valor guardado; recuperar solo lo lee; rotar además cambia la credencial real en el sistema destino y promueve la nueva versión a `AWSCURRENT`.

## 2. Práctica

Archivos: [secrets_demo.py](secrets_demo.py), [policy_lectura_secreto.json](policy_lectura_secreto.json), [comandos.sh](comandos.sh).

1. Se crea el secreto `taller/punto1/credenciales-prueba` con usuario/contraseña ficticios.
2. Se crea un usuario `app_lectora_punto1` cuya única política permite `GetSecretValue` sobre ese ARN (sufijo `-*` porque AWS agrega 6 caracteres aleatorios).
3. `python secrets_demo.py --watch 5` lee el secreto con Boto3 y muestra versión, usuario y contraseña enmascarada.
4. Con `put-secret-value` se cambia la contraseña. En la siguiente iteración el programa muestra **otro `VersionId`** sin reiniciarse ni modificarse.
5. Prueba negativa: leer cualquier otro secreto con ese usuario devuelve `AccessDeniedException`.

### Por qué se actualiza sin cambiar el código
El programa no guarda el valor: pide `SecretId` por nombre y Secrets Manager devuelve la versión con etiqueta `AWSCURRENT`. Cambiar el valor mueve esa etiqueta a la versión nueva; el nombre (y el código) siguen iguales. Si se usa caché, el cambio se ve cuando expira el TTL (`secret_refresh_interval`).

## 3. Preguntas de costos (precios de referencia us-east-1)

- **Cobro.** ~**US$0,40 por secreto al mes** (prorrateado por hora; los secretos eliminados dejan de cobrar) + ~**US$0,05 por cada 10.000 llamadas a la API**. KMS con clave propia añade ~US$1/mes por clave y sus llamadas; con `aws/secretsmanager` no hay costo extra de clave.
- **Consultar repetidamente el mismo secreto.** Cada `GetSecretValue` cuenta como llamada: 1 millón de lecturas ≈ US$5. Además añade latencia y riesgo de *throttling* (límite de solicitudes por segundo).
- **Cuándo cachear en memoria.** Casi siempre en servicios de larga vida o con muchas solicitudes (pools de conexión, APIs, Lambdas con contenedores reutilizados): se usa un TTL de minutos (`aws-secretsmanager-caching`, ya incluido con `--cached`). **No** conviene cachear de forma indefinida si se usa rotación frecuente (se usaría una credencial vencida) ni para scripts de una sola ejecución (no hay beneficio).

**Estimación del taller:** 1 secreto × ~1 hora ≈ US$0,001 + <100 llamadas ≈ US$0,0005 → **menos de US$0,01**.

**Ejemplo del efecto del caché.** Un programa que consulta cada 5 s hace 720 llamadas/h (≈ 17.280/día ≈ US$0,09/día); con caché de TTL 300 s hace 12 llamadas/h (≈ 288/día ≈ US$0,0014/día), y el cambio de valor se refleja con un retraso máximo de 5 min.

## 4. Evidencias (carpeta [evidencias](evidencias))

- [funcionamiento.png](evidencias/funcionamiento.png): ejecución de `secrets_demo.py --watch` (recorte sin claves de acceso).
- [cambio_version.png](evidencias/cambio_version.png): tras `put-secret-value` el programa muestra otro `VersionId` sin cambiar el código.
- [list_secrets_vacio.png](evidencias/list_secrets_vacio.png): `delete-secret --force-delete-without-recovery` y `list-secrets` sin el secreto de prueba.

La política de lectura está en [policy_lectura_secreto.json](policy_lectura_secreto.json); los comandos exactos en [comandos.sh](comandos.sh).
