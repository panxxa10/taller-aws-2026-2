# Punto 2 – Terraform, SDK (Boto3) y AWS CLI

Recursos: **bucket S3 + instancia EC2 + instancia RDS (PostgreSQL)** + red (security groups sobre la VPC por defecto).
Se despliega **tres veces, una a la vez**, y se elimina todo antes de la siguiente.

## 1. ¿Qué es Terraform?
Herramienta de *Infraestructura como Código* (declarativa). Se describe el estado deseado en archivos `.tf` y Terraform compara con el estado real:
- `terraform init` → descarga proveedores (AWS).
- `terraform plan` → muestra qué creará/cambiará/destruirá (sin tocar nada).
- `terraform apply` → crea o modifica para igualar lo declarado.
- `terraform destroy` → elimina todo lo que gestiona.

Guarda lo que creó en el **archivo de estado** (`terraform.tfstate`).

## 2. Usuario IAM `user_cli`
```bash
aws iam create-user --user-name user_cli
# La política supera los 2.048 caracteres que admite una política EN LÍNEA de usuario,
# por eso se crea como política administrada por el cliente (límite 6.144):
aws iam create-policy --policy-name PoliticaTallerPunto2 --policy-document file://iam/user_cli_policy.json
aws iam attach-user-policy --user-name user_cli \
  --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/PoliticaTallerPunto2   # ejecutar con un admin (no raíz) la primera vez
aws iam create-access-key --user-name user_cli          # NO publicar la salida
aws configure                                           # (o --profile user_cli)
aws sts get-caller-identity                                      # verificación: debe mostrar user_cli
```
Política: [iam/user_cli_policy.json](iam/user_cli_policy.json). Permisos documentados por servicio:

| Servicio | Permisos necesarios (mínimos) |
|---|---|
| S3 | `CreateBucket`, `DeleteBucket`, `ListBucket`, `Get/PutBucketTagging`, `Get/PutBucketPublicAccessBlock` y los `Get*` de configuración que Terraform consulta al refrescar el bucket |
| EC2 | `RunInstances`, `TerminateInstances`, `Describe*`, `CreateTags` |
| Red | `CreateSecurityGroup`, `DeleteSecurityGroup`, `Authorize/RevokeSecurityGroupIngress/Egress` (los subnets/VPC por defecto solo se leen con `Describe*`) |
| RDS | `CreateDBInstance`, `DeleteDBInstance`, `Create/DeleteDBSubnetGroup`, `Describe*`, `AddTagsToResource`; `iam:CreateServiceLinkedRole` (rol vinculado de RDS, solo la primera vez) |
| Secreto de RDS | `secretsmanager:CreateSecret/DeleteSecret/TagResource/DescribeSecret/GetSecretValue` y `kms:DescribeKey/CreateGrant/Decrypt/GenerateDataKey` (RDS crea el secreto en nombre del usuario) |
| AMI | `ssm:GetParameter` sobre `/aws/service/ami-amazon-linux-latest/*` |

Se acota con `aws:RequestedRegion = us-east-1`. Si algún `apply` falla con `AccessDenied`, el error nombra la acción faltante: se agrega y se documenta (es la forma práctica de afinar *least privilege*).

## 3. Ejecución secuencial

**Terraform** (obligatorio)
```bash
cd terraform
# (claves de user_cli ya configuradas; con otro perfil: export AWS_PROFILE=<perfil>)
terraform init
terraform plan -out tfplan
terraform apply tfplan
terraform output
terraform destroy          # evidencia de eliminación
```

**Boto3**
```bash
cd boto3 && python deploy_boto3.py deploy && python deploy_boto3.py destroy
```

**AWS CLI**
```bash
cd cli && bash deploy_cli.sh && bash destroy_cli.sh
```

Tras cada versión se corre el checklist de limpieza del README raíz antes de iniciar la siguiente.

## 4. Autenticación de `user_cli`
CLI, Boto3 y Terraform usan la **misma cadena de credenciales** del SDK: variables de entorno → `~/.aws/credentials` (perfil `user_cli`, access key + secret key) → rol/SSO. Cada llamada a la API se firma con **SigV4** usando esas claves; IAM valida la firma y evalúa las políticas del usuario.

**Por qué las claves NO van en Secrets Manager:** para leer un secreto primero hay que autenticarse en AWS. Si las claves estuvieran dentro de Secrets Manager nadie podría llegar a ellas (problema del huevo y la gallina). Las claves viven en el equipo, fuera del repositorio; en producción se prefieren credenciales temporales (SSO / rol / IAM Identity Center).

**Estado de Terraform.** `terraform.tfstate` guarda atributos de todos los recursos **en texto plano** (IDs, endpoints y, si se declarara una contraseña, la contraseña). Por eso:
- RDS usa `manage_master_user_password = true`: la contraseña la genera RDS, vive en Secrets Manager y en el estado solo aparece el **ARN** del secreto.
- El estado y `.terraform/` están en `.gitignore`; no se publican.

## 5. Comparación de métodos

| | Terraform | Boto3 | AWS CLI |
|---|---|---|---|
| Estilo | Declarativo | Imperativo (Python) | Imperativo (shell) |
| Plan previo (`plan`) | Sí | No | No (solo `--dry-run` en algunos EC2) |
| Estado / idempotencia | Sí, con tfstate | Hay que programarla | Hay que programarla |
| Eliminación | `destroy` en un comando, orden de dependencias automático | Hay que codificar el orden y las esperas | Ídem, con `wait` |
| Esperas (RDS disponible) | Automático | `waiters` | `aws rds wait` |
| Líneas de código | ~100 de HCL | ~130 | ~50 |
| Mejor para | Infra reproducible/equipo | Lógica de aplicación | Scripts rápidos, exploración |

## 6. Preguntas de costos (estimación us-east-1, a verificar en calculator.aws)

| Componente | Precio ref. | 1 hora | 1 semana (168 h) |
|---|---|---|---|
| EC2 t3.micro | ~0,0104 US$/h | 0,010 | 1,75 |
| EBS gp3 8 GB | ~0,08 US$/GB-mes | 0,001 | 0,15 |
| IPv4 pública (si la EC2 la tiene) | 0,005 US$/h | 0,005 | 0,84 |
| RDS db.t4g.micro (PostgreSQL) | ~0,016 US$/h | 0,016 | 2,69 |
| RDS almacenamiento gp3 20 GB | ~0,115 US$/GB-mes | 0,003 | 0,53 |
| Secreto de RDS | 0,40 US$/mes | 0,001 | 0,09 |
| S3 vacío | ~0 | 0 | 0 |
| **Total aprox.** | | **≈ US$0,04** | **≈ US$6** |

- **Siguen cobrando sin recibir tráfico:** la EC2 encendida y su disco, la IPv4 pública, la instancia RDS y su almacenamiento, los snapshots/backups, y el secreto.
- **Costo que añade el secreto de RDS:** ~US$0,40/mes (+ US$0,05 por 10.000 llamadas; RDS no genera llamadas continuas salvo la rotación automática cada 7 días). Para un taller de horas, centavos.

## 7. Incidentes durante la ejecución
- `put-user-policy` falló por tamaño (2.048 caracteres) → política administrada (ver sección 2).
- `ec2:DescribeVpcs` denegado en una terminal nueva: faltaba exportar `AWS_REGION`/`AWS_DEFAULT_REGION` (la política exige `aws:RequestedRegion`).
- `destroy_cli.sh` dejó EC2, RDS, bucket y security groups al continuar sin confirmar: se eliminaron a mano en orden de dependencias (bucket vacío → instancia terminada → RDS eliminada → SG de RDS → SG de EC2) y se verificó con `describe-*`. La versión CLI estuvo encendida ~2 días (≈ US$1,5–2 en total para este punto).

## 8. Evidencias ([evidencias](evidencias))
- Terraform: [plan](evidencias/01_terraform_plan.png), [apply y outputs](evidencias/02_terraform_apply_outputs.png), [destroy y verificación vacía](evidencias/03_terraform_destroy_y_verificacion.png).
- Boto3: [deploy](evidencias/04_boto3_deploy.png).
- AWS CLI: [bucket](evidencias/05_cli_s3_crear_bucket.png), [EC2](evidencias/06_cli_ec2_instance_id.png), [security group y regla 5432](evidencias/07_cli_red_security_group_regla_5432.png), [subnet group](evidencias/08_cli_rds_subnet_group.png), [RDS creándose](evidencias/09_cli_rds_instance_creating.png).
- La verificación de que `user_cli` (y no la raíz) opera se hizo con `aws sts get-caller-identity`; el resultado se puede reproducir con el comando de la sección 2 (la captura no se incluye porque muestra el ID de cuenta).
- Verificación global final de recursos: [../evidencias/verificacion_global_final.png](../evidencias/verificacion_global_final.png).
