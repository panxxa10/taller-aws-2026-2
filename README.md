# Taller AWS – Ingeniería de Datos 2026-2 (Universidad EIA)

Repositorio con código, consultas, instrucciones, resultados, estimaciones de costo y evidencias de los 6 puntos del taller. Cada carpeta tiene su propio `README.md` con los pasos para **reproducir** ese punto y las respuestas a las preguntas del enunciado.

| Punto | Tema | Qué se desplegó | Carpeta |
|---|---|---|---|
| 1 | AWS Secrets Manager | 1 secreto de prueba + usuario de solo lectura (todo eliminado) | [punto1-secrets-manager](punto1-secrets-manager) |
| 2 | Terraform vs Boto3 vs AWS CLI | S3 + EC2 + RDS PostgreSQL, 3 veces en secuencia | [punto2-terraform-sdk-cli](punto2-terraform-sdk-cli) |
| 3 | Amazon DocumentDB | Cluster Serverless (0,5–1 DCU) + EC2 puente + túnel SSH | [punto3-documentdb](punto3-documentdb) |
| 4 | Amazon Neptune | Cluster provisionado `db.t4g.medium` + EC2 puente + túnel SSH | [punto4-neptune](punto4-neptune) |
| 5 | Amazon Redshift | Redshift Serverless (4 RPU base) + rol IAM para S3 | [punto5-redshift](punto5-redshift) |
| 6 | AWS Glue Data Catalog + Athena | Base de datos, crawler, tablas y consultas Athena | [punto6-glue-catalog](punto6-glue-catalog) |

## Convenciones

- **Región única:** `us-east-1` (variable `AWS_REGION`).
- **Cero contraseñas en código:** toda credencial de base de datos vive en Secrets Manager. Donde el servicio lo permite se usa la administración integrada (`manage_master_user_password` en RDS y DocumentDB, `manageAdminPassword` en Redshift) y los programas leen el secreto en ejecución.
- **Autenticación en AWS:** usuario IAM `user_cli` (nunca la cuenta raíz). En la ejecución real sus claves se configuraron como perfil `default` del AWS CLI; el repositorio no depende del nombre del perfil (`AWS_PROFILE` o `TF_VAR_profile`).
- **Recursos etiquetados** con `Proyecto=taller-aws` para poder verificar que no quede nada facturable.
- Cada carpeta tiene `evidencias/` con capturas de creación, resultados y eliminación, **sin credenciales visibles**.

## Preparación

```bash
python3 -m venv .venv && source .venv/bin/activate      # Python 3.10+ (se usó 3.12)
pip install -r requirements.txt
aws configure                                            # claves de user_cli
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
aws sts get-caller-identity                              # debe mostrar user_cli, no root
```

Herramientas: AWS CLI v2, Terraform ≥ 1.5, Python 3.10+. Para el punto 3 además MongoDB Compass.

## Permisos de `user_cli` por punto

El punto 2 documenta la política mínima (S3, EC2, RDS y red) en [punto2-terraform-sdk-cli/iam/user_cli_policy.json](punto2-terraform-sdk-cli/iam/user_cli_policy.json). Al avanzar, cada servicio necesitó permisos adicionales; se añadieron **solo mientras se usaban** y se retiran al finalizar el taller:

| Punto | Política adicional adjunta a `user_cli` | Motivo |
|---|---|---|
| 1 | Usuario separado `app_lectora_punto1` con política de solo lectura sobre un secreto | El programa no debe poder leer otros secretos |
| 3 y 4 | `AmazonRDSFullAccess` (DocumentDB y Neptune se administran con acciones del espacio `rds:*`) | `terraform apply` falló con `AccessDenied: rds:DescribeGlobalClusters`; `AmazonDocDBFullAccess` por sí sola no basta |
| 5 | `AmazonRedshiftFullAccess`, `AmazonRedshiftDataFullAccess`, `IAMFullAccess` (crear el rol que lee S3), `SecretsManagerReadWrite` | `CreateNamespace` con contraseña administrada falló con *"Amazon Redshift can't access the secret"* hasta añadir permisos de Secrets Manager |
| 6 | `AWSGlueConsoleFullAccess`, `AmazonAthenaFullAccess` (+ `IAMFullAccess` para el rol del crawler) | Crawler, catálogo y Athena |

`IAMFullAccess` y las políticas `*FullAccess` son más amplias de lo que exige *least privilege*; se usaron de forma temporal para el taller. En producción se acotarían por recurso.

## Costos (estimación de lo realmente consumido)

| Punto | Tiempo encendido aprox. | Costo aprox. |
|---|---|---|
| 1 | ~1 h | < US$0,01 |
| 2 | Terraform y Boto3: minutos por versión; la versión CLI quedó ~2 días (ver incidentes) | ≈ US$1,5–2 |
| 3 | ~1,5 h | ≈ US$0,15–0,30 |
| 4 | ~2 días (ver incidentes) | ≈ US$3–4 |
| 5 | ~15 min (Serverless: se factura solo la actividad) | ≈ US$0,15–0,30 |
| 6 | 2 ejecuciones del crawler | ≈ US$0,15–0,20 |

Cada README detalla el cálculo por componente. Son estimaciones con precios de referencia de `us-east-1`; el gasto real se confirma en **Billing → Cost Explorer**.

## Incidentes y lecciones

| Qué pasó | Causa | Solución / lección |
|---|---|---|
| `put-user-policy` rechazó la política de `user_cli` | Las políticas en línea de un usuario admiten 2.048 caracteres y la nuestra los supera | Política administrada por el cliente (límite 6.144): `create-policy` + `attach-user-policy` |
| `UnauthorizedOperation ec2:DescribeVpcs` | Terminal nueva sin región y la política condiciona `aws:RequestedRegion` | Exportar `AWS_REGION`/`AWS_DEFAULT_REGION` en cada terminal |
| `AccessDenied rds:DescribeGlobalClusters` (DocumentDB) | Faltaba el espacio de acciones `rds:*` | `AmazonRDSFullAccess` y reintento (`terraform apply` es idempotente) |
| `Unable to find Traversal steps for the graph operator: discard` (Neptune) | `gremlinpython` ≥ 3.7 envía el paso `discard` en `.iterate()`, que Neptune no soporta | Usar `.toList()` en lugar de `.iterate()` |
| *"Amazon Redshift can't access the secret"* | Faltaban permisos de Secrets Manager para `manageAdminPassword` | `SecretsManagerReadWrite`; el deploy fallido se limpió con `destroy` antes de reintentar |
| `destroy_cli.sh` dejó EC2, RDS, bucket y security groups | El script no confirmó todas las eliminaciones | Se eliminaron manualmente y se verificó con `describe-*`. **Lección: verificar siempre tras cada destroy, antes de pasar al siguiente punto** |
| Neptune permaneció encendido ~2 días | El clúster no se destruyó justo después del despliegue | Mayor costo (≈ US$3–4). **Lección: destruir apenas se tiene la evidencia** |

## Lo que NO se sube a GitHub (ya está en `.gitignore`)

`*.tfstate*`, `tfplan`, `.terraform/`, `*.tfvars`, `*.pem`, `.env*`, claves de IAM, contraseñas y capturas que muestren credenciales. El archivo de estado de Terraform guarda atributos en texto plano, por eso nunca se versiona (ver punto 2). El certificado `global-bundle.pem` es público, pero se descarga con `scripts/tunel.sh` en lugar de versionarlo.

## Checklist final de limpieza (verificar tras cada punto)

```bash
export AWS_PAGER=""
aws ec2 describe-instances --filters Name=instance-state-name,Values=pending,running,stopping,stopped --query "Reservations[].Instances[].InstanceId"
aws ec2 describe-volumes --query "Volumes[].VolumeId"
aws ec2 describe-addresses
aws rds describe-db-instances --query "DBInstances[].DBInstanceIdentifier"
aws rds describe-db-clusters --query "DBClusters[].DBClusterIdentifier"            # RDS, DocumentDB y Neptune
aws rds describe-db-snapshots --snapshot-type manual --query "DBSnapshots[].DBSnapshotIdentifier"
aws rds describe-db-cluster-snapshots --snapshot-type manual --query "DBClusterSnapshots[].DBClusterSnapshotIdentifier"
aws redshift-serverless list-workgroups --query "workgroups[].workgroupName"
aws redshift-serverless list-namespaces --query "namespaces[].namespaceName"
aws secretsmanager list-secrets --query "SecretList[].Name"
aws s3 ls
aws glue get-databases --query "DatabaseList[].Name"
aws glue get-crawlers --query "Crawlers[].Name"
aws iam list-roles --query "Roles[?starts_with(RoleName,'taller')].RoleName"
aws ec2 describe-key-pairs --query "KeyPairs[?starts_with(KeyName,'taller')].KeyName"
aws ec2 describe-security-groups --query "SecurityGroups[?starts_with(GroupName,'taller')].GroupName"
```

**Resultado final** ([evidencias/verificacion_global_final.png](evidencias/verificacion_global_final.png)): todas las salidas vacías para recursos del taller. Lo que aparece (bucket `maq-2805-de`, snapshot `maq-db-snapshot`, base de Glue `db` y `default`, llaves `maq-kp`/`kp`) **son recursos preexistentes de otros proyectos, no del taller**, y no se tocaron.

Revisar además **Billing → Cost Explorer** al día siguiente.

> Los precios citados en cada README son estimaciones de referencia para `us-east-1` (tarifas consultadas en las páginas de precios de AWS en octubre de 2026) y pueden cambiar: confirmar en <https://calculator.aws>.
