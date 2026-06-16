# CHECKPOINT — KIM-NEYÜN (productivización en AWS)

> Documento vivo de continuidad. Cualquier agente/persona puede retomar el
> trabajo leyendo esto. **Mantener actualizado** al avanzar.
> Última actualización: 2026-06-16 (✅ **backfill táctico completado: semanas
> 17–24 de 2026 consultables vía API/dashboard**, cuenta `kim-dev` 033216807288
> — ver §4 "Backfill táctico de semanas pasadas"). Actualización anterior:
> 2026-06-15 (frontend migrado de App Runner a EC2+Caddy; deploy inicial E2E).

## 1. Qué es esto

KIM-NEYÜN predice consultas de urgencia respiratoria por **semana epidemiológica**
para 12 centros de Temuco / Padre Las Casas (Chile). Arquitectura **HZF**:
Chronos-T5 (serie de tiempo, zero-shot) + corrección de residuos con ML
(XGBoost/Ridge + PCA) usando estresores ambientales (PM2.5, PM10, CO, temp) con
rezago biológico. Postulación a concurso interno UCTemuco (MVP, TRL4→TRL5).

- **`poc/`** = prototipo del **investigador**, pensado para **Hugging Face**
  (FastAPI + Streamlit, inferencia en vivo). Referencia, no se despliega.
  **Completo y autocontenido** (descargado de
  `https://huggingface.co/spaces/edurojas95/Kim_Neyun`, 2026-06-13): código
  (`app.py`, `api_motor.py`, `api_motor_v.1.0`, `Dockerfile`, `requirements.txt`)
  + **artefactos** `Modelos_Lags/` y `Modelos_NoLags/` (78 `.pkl`: XGBoost_Hybrid,
  Ridge_Hybrid, PCA, Scaler — verificado 2026-06-14, antes decía 76) +
  `data/API_Epidemiologia_Temuco_Padre_Las_Casas.csv`.
  El código es byte-idéntico al que estaba en `poc/` antes; ahora trae además
  los `.pkl` y el CSV que faltaban. **Fuente de los artefactos para AWS** (ver §6).
  Ya copiados a `./models/` y `./data/` (2026-06-13). El `.gitignore` excluye
  los binarios tanto en `models/`/`data/` como en `poc/`.
- **`app/` + `infra/`** = la **versión productiva** en AWS (este trabajo).

Relacionados: plan aprobado en
`/Users/Personal/.claude/plans/users-personal-downloads-formulario-pos-snuggly-cupcake.md`;
formulario en `~/Downloads/Formulario postulacion OK (1).docx`.

## 2. Decisiones validadas (NO re-litigar)

| Tema | Decisión |
|---|---|
| Patrón de inferencia | **Batch precomputado** (job escribe en DynamoDB; API/dashboard solo leen) |
| Framework backend | **FastAPI** (del PoC; NO migrar a Flask) |
| API | **Lambda + API Gateway** (delgada, lee DynamoDB) |
| Modelo/inferencia | **Lambda (contenedor)** disparada por **EventBridge Scheduler** (pago por uso) |
| Base de datos | **DynamoDB** PAY_PER_REQUEST (accesos por clave; ~US$0 a este volumen) |
| Frontend | **Streamlit en EC2 t4g.micro + Caddy** (no App Runner, ver §4 — App Runner no soporta WebSocket) |
| Región | **us-east-1** (la más barata de América) |
| Red | **Sin VPC / sin NAT** (todo serverless con endpoints públicos de AWS) |
| IaC | **Terraform** |
| Limpieza deps | Sin **tensorflow**/**shap**; Chronos vía PyPI (`chronos-forecasting`) |

> **Evolución (2026-06-13):** la arquitectura inicial usaba Fargate + RDS + VPC.
> A pedido del usuario se simplificó a **full serverless** (Lambda + DynamoDB,
> sin VPC/ECS/RDS/NAT) — más simple y barato. DynamoDB encaja porque los accesos
> son lookups por clave (`hospital+semana`, `hospital+año`).

Razón de fondo: presupuesto cloud chico (~US$1.800 total del proyecto) + uso
semanal → serverless/pago-por-uso. Costo estimado **~US$10–35/mes**.

> **🚧 En curso (otra sesión, detectado 2026-06-14):** se está agregando un
> backend de **usuarios/autenticación** (JWT + bcrypt + SQLAlchemy/Alembic) que
> respalda en **Aurora Serverless v2 PostgreSQL** (acceso via RDS Data API, sin
> VPC para el Lambda — `infra/auth_db.tf`, nueva VPC mínima `10.20.0.0/16` solo
> para el cluster). Archivos nuevos: `app/api/auth.py`, `app/shared/users_db.py`,
> `app/alembic/` + `app/alembic.ini`, `app/scripts/seed_admin.py`,
> `infra/auth_db.tf`; `docker-compose.yml` ahora incluye un servicio `postgres`.
> Todos los endpoints de datos (`/hospitales`, `/predecir`, `/proyeccion_anual`)
> ahora exigen `Depends(get_current_user)`. **No reflejado todavía** en la tabla
> de decisiones ni en el diagrama de §3 — actualizar cuando esa sesión cierre.
> No re-litigar ni revertir estos archivos sin coordinar.
>
> **✅ Auth local inicializada (2026-06-14)**: se corrió `alembic upgrade head`
> (tabla `users` + índice único `email` creados en el Postgres local) y se
> sembró el admin inicial con `python -m scripts.seed_admin`. Verificado
> end-to-end: `POST /auth/login` → 200 + JWT, `GET /auth/me` → 200, `GET
> /hospitales` sin token → 401 y con token → 200. Nuevos targets `make migrate`
> / `make seed-admin` / `make auth-init` (idempotentes) y mención en
> `README.md`. Detalle y credenciales del admin de dev en §4 "Re-verificado".
> ✅ **Bug `EmailStr` en `/auth/me`/`/auth/users` — RESUELTO (2026-06-14)**:
> `UserResp.email` usaba `EmailStr`, que rechaza TLDs de uso especial (`.local`,
> `.test`, etc.) y rompía con 500 (`ResponseValidationError`) si el usuario
> tenía un email así (p.ej. un admin sembrado con `@...local`). Arreglado en
> `app/api/auth.py`: `UserResp.email` ahora es `str` (se valida al crear el
> usuario vía `CrearUsuarioReq.email: EmailStr`, no al serializar la
> respuesta — patrón "validar en el borde, no en la salida"). `CrearUsuarioReq`
> sigue usando `EmailStr` sin cambios (alta vía `/auth/users` sigue exigiendo
> un email con TLD válido; `.local`/`.test` dan 422 controlado, no 500).
> Verificado E2E con un admin `admin@kim-neyun.local` (creado vía
> `scripts.seed_admin`, que no pasa por `CrearUsuarioReq`): `POST /auth/login`
> → 200+JWT, `GET /auth/me` → 200 (antes 500), `POST /auth/users` con email
> válido → 201 (antes también afectado por el mismo bug en la respuesta).
> Cuentas de prueba (`admin@kim-neyun.local`, `viewer@kim-neyun.cl`) eliminadas
> tras verificar; queda solo el admin de dev `admin@kim-neyun.cl`. Contrato del
> frontend sin cambios (el campo `email` sigue siendo un string en el JSON).

## 3. Arquitectura

```
EventBridge Scheduler (semanal)
   └─> Lambda batch (contenedor arm64, SIN VPC -> tiene internet)
        ├─ ingesta Open-Meteo (clima + calidad aire)   [SINCA = futuro]
        ├─ carga histórico DEIS (S3) + artefactos .pkl (S3)
        ├─ inferencia Chronos-T5 + XGBoost/PCA
        └─ PutItem -> DynamoDB
DynamoDB <- GetItem - Lambda API (FastAPI) <- API Gateway (HTTP) <- EC2 t4g.micro (Caddy -> Streamlit, arm64)
S3 (artefactos modelo + CSV DEIS)
```
Tabla DynamoDB única: `pk=<hospital>`, `sk="SEM#<anio>#<semana>"` o `"PROY#<anio>"`,
payload variable en atributo `data` (JSON).

## 4. Estado actual

### ✅ Hecho (aplicación + infra + local), validado
```
app/
  shared/      __init__.py, catalog.py, config.py, db.py (DynamoDB), repository.py
  inference/   __init__.py, ingest.py, engine.py, run_batch.py, handler.py (Lambda),
               requirements.txt, Dockerfile (Lambda), Dockerfile.local
  api/         __init__.py, main.py, requirements.txt, Dockerfile (Lambda), Dockerfile.local
  frontend/    app.py, requirements.txt, Dockerfile
  .dockerignore
docker-compose.yml      # dynamodb-local + api + frontend; perfiles "batch" y "localstack"
Makefile                # up, batch, ddb-scan, lint, tf-*, localstack-*, tf-local-*
models/README.md · data/README.md · .gitignore · README.md · CHECKPOINT.md
infra/                  versions, variables, main, data (DynamoDB+S3), ecr,
                        api (Lambda+API GW), inference (Lambda batch+Scheduler),
                        frontend (App Runner), outputs, terraform.tfvars.example, README.md
```
Diseño: la lógica pesada del PoC se movió **idéntica** a `inference/engine.py` +
`inference/ingest.py`. La API conserva la firma del PoC (`/predecir`,
`/proyeccion_anual`, clave `"año"` con tilde) pero hace `GetItem` a DynamoDB.

Validaciones de esta sesión:
- ✅ `python -m compileall app`
- ✅ `terraform validate` (config válida; `fmt` aplicado)
- ✅ `docker compose config`
- ✅ **Batch local end-to-end (2026-06-13/14)**: `make up` + `make batch` corrió
  con artefactos reales; los 12 hospitales semanales + proyecciones se
  persistieron en DynamoDB Local (estructura `SEM#<a>#<sem>` / `PROY#<a>` OK).

Re-verificado 2026-06-14 (auditoría de checkpoint, sin tocar código salvo lo
indicado más abajo):
- ✅ `python3 -m compileall -q app` → OK.
- ✅ `terraform validate` (incluyendo el nuevo `infra/auth_db.tf`) → "Success!".
- ✅ `docker compose config --services` → `dynamodb, postgres, api, frontend`
  (`postgres` es nuevo, ver recuadro "En curso" en §2).
- ✅ DynamoDB Local sigue poblada: `aws dynamodb scan --select COUNT` → 48 items
  (12 hospitales × (1 semanal + 3 proyecciones anuales 2024/2025/2026)) — el
  batch end-to-end de §4/§7 sigue verificado.
- ✅ Fix de `/predecir` (submodelo `EstimacionesResp` anidado en
  `app/api/main.py`) y limpieza del provider `random` muerto en
  `infra/versions.tf` — ambos siguen aplicados y verificados.
- ✅ `.pkl`: 78 en `models/` (39 Lags + 39 NoLags), idénticos a `poc/` (`diff`
  sin diferencias). El recuento "76" de §1 era una imprecisión menor.
- ✅ **Auth local inicializada (2026-06-14)**:
  - `docker compose exec api sh -c "cd /srv && alembic upgrade head"` →
    crea `users` + `alembic_version` (revisión `0001`) en el Postgres local.
  - `python -m scripts.seed_admin` (vía `make seed-admin`) → admin de dev:
    **email `admin@kim-neyun.cl`, password `KimNeyun2026Dev!`**
    (overrideable con `ADMIN_EMAIL`/`ADMIN_PASSWORD`; solo para desarrollo local).
  - E2E: `POST /auth/login` (form `username`/`password`) → 200 + JWT;
    `GET /auth/me` con `Authorization: Bearer <token>` → 200
    (`{"email":"admin@kim-neyun.cl","role":"admin",...}`);
    `GET /hospitales` sin token → 401, con token → 200 (12 hospitales).
  - Nuevos targets `make migrate` / `make seed-admin` / `make auth-init`
    (idempotentes, probados dos veces) + nota en `README.md`.

Bugs encontrados y corregidos en este run (ver detalle abajo):
- **Clima**: `requests_cache` rompía al serializar (cattrs → `NameError:
  RequestsCookieJar`) y degradaba TODO a Zero-Shot. Quitado `requests_cache` en
  `inference/ingest.py` + `requirements.txt`; ahora trae temp/PM2.5/PM10/CO reales.
- **Nombres de `.pkl`**: targets con `/` y `()` (columnas del CSV) no matcheaban
  los archivos sanitizados → `Acute_Bronchitis/Bronchiolitis` y `COVID-19
  (Confirmed)` caían a Zero-Shot. `MotorHibrido._nombre_archivo()` sanitiza la
  ruta. Solo `COVID-19 (Suspected)` queda en Zero-Shot (no hay `.pkl` en el Space).
- ✅ Verificado que las claves del clima coinciden 100% con `feature_names_in_`
  de los scalers (39/39, 13/13): el salto de magnitud al activar la corrección
  (p.ej. NORMAL→PREEMERGENCIA en invierno) es comportamiento real del modelo,
  no un desajuste de features.

### ✅ Desplegado en AWS (kim-dev, 2026-06-15)

**Cuenta**: `kim-dev` (`033216807288`), vía perfil `kim-dev` (AssumeRole desde
`admin`/cuenta gestora `598456800229`). Existe también `kim-prod`
(`657082817366`) — **nunca tocada**, reservada para el despliegue final.
El §6/§7 de este documento (cuenta `598456800229` como destino del `apply`)
quedó superado por esta estructura de cuentas; no re-litigar.

**Cambio de arquitectura — inference Lambda ahora x86_64 con Dockerfile
propio**: `torch==2.10.0`/`xgboost==3.2.0` (versiones con las que se
entrenaron los 78 `.pkl`) no publican wheels compatibles con la base oficial
`public.ecr.aws/lambda/python:3.11` en NINGUNA arquitectura. Se reescribió
`app/inference/Dockerfile` sobre `python:3.11-slim` + Lambda Runtime
Interface Client (`awslambdaric`), patrón soportado por AWS para "Lambda con
imagen base propia". `torch` se instala primero desde el índice CPU de
PyTorch (`https://download.pytorch.org/whl/cpu`) para evitar ~5-6GB de
paquetes `nvidia-*-cu12` (CUDA) inútiles en Lambda — imagen final 2.39GB.
`infra/inference.tf`: `architectures = ["x86_64"]`. **La API sigue en arm64**
(no usa estas deps), sin cambios.

**Apply**: `terraform apply` completo (38 recursos) OK en `kim-dev`. Fix
adicional aplicado: faltaba `dynamodb:GetItem` en la policy del rol del batch
(`infra/inference.tf`, `data.aws_iam_policy_document.batch`, sid
`ReadWritePredicciones`) — sin él, `run_batch.py` fallaba con
`AccessDeniedException` al chequear idempotencia de proyecciones anuales.

**Auth**: `alembic upgrade head` + `seed_admin` corridos contra Aurora
Serverless v2 (Data API, vía contenedor `python:3.11-slim` desechable con
`app/` montado). Admin de dev: **`admin@kim-neyun.cl` / `KimNeyun2026Dev!`**.

**S3**: 79 objetos (`models/*.pkl` + `manifest.json`) + CSV histórico DEIS
subidos a `s3://kim-neyun-artifacts-033216807288/`.

**Batch — funciona pero excede el límite duro de Lambda (900s/15min) para el
backfill completo**: cada invocación calcula la predicción táctica (semana
actual) de los 12 hospitales (~rápido) y luego va avanzando en las
proyecciones anuales (`PROY#2024/2025/2026` × 12 hospitales = 36), pero el
cómputo Chronos-T5+XGBoost/PCA de las 36 proyecciones no cabe en 900s
(timeout confirmado con solo 1159/3008MB usados → **CPU/tiempo, no memoria**).
Como `run_batch.py` hace `PutItem` incremental, cada invocación (aunque
termine en timeout) deja progreso: tras 2 invocaciones manuales + 1 disparo
automático de EventBridge Scheduler (cron semanal, coincidió con esta
sesión) + sus reintentos automáticos, DynamoDB quedó con **12/12 hospitales
con `SEM#2026#24` (semana actual)** + proyección anual completa para varios
hospitales, y creciendo (~5 items nuevos por invocación de 900s). Suficiente
para servir el dashboard de la semana actual; el backfill completo de
2024-2026 sigue en curso (ver TODO en §8).

**Verificación E2E (todo OK)**:
- `GET /health` → `200 {"status":"ok"}`.
- `POST /auth/login` (admin@kim-neyun.cl) → `200` + JWT (tras el cold-start de
  Aurora: primer intento dio `DatabaseResumingException`, normal con
  `min_capacity=0`, reintento OK).
- `GET /auth/me` con Bearer token → `200`.
- `GET /hospitales` con Bearer token → `200`, 12 hospitales.
- `POST /predecir` (Hospital Dr. Hernán Henríquez Aravena, 2026-06-15) →
  `200` con datos reales del batch (semana 24-2026, `nivel_alerta:
  PREEMERGENCIA`).
- Frontend (App Runner, URL ya retirada) → `200`. **Reemplazado por EC2+Caddy
  el mismo día** — ver subsección siguiente para la URL vigente.

**URLs finales (App Runner, retirado el mismo día — ver subsección
siguiente)**:
- API: `https://u5xrtplhif.execute-api.us-east-1.amazonaws.com`
- Frontend (App Runner, YA NO EXISTE): `https://vt3dy3ciqz.us-east-1.awsapprunner.com`

### ✅ Frontend: migración App Runner → EC2+Caddy (kim-dev, 2026-06-15)

**Motivo**: el dashboard reportó en consola `WebSocket connection to
'wss://vt3dy3ciqz.us-east-1.awsapprunner.com/_stcore/stream' failed`.
Diagnóstico: `curl` con headers `Upgrade: websocket` contra la URL de App
Runner devolvió `403 Forbidden` (`server: envoy`). **AWS App Runner no
soporta WebSocket** (limitación de su proxy Envoy, confirmado también por
varios hilos de AWS re:Post) — y Streamlit usa WebSocket (`_stcore/stream`)
como **único** canal cliente-servidor (sin esto, la app carga pero queda
no-interactiva).

**Solución implementada**: reemplazar `aws_apprunner_service.frontend` (+ su
IAM role/policy) por un **EC2 `t4g.micro`** (arm64, Amazon Linux 2023) con
Docker, corriendo dos contenedores en una red `kimnet`:
- `frontend`: la misma imagen Streamlit (reconstruida para **arm64**, antes
  era amd64 para App Runner).
- `caddy:2`: reverse proxy en :443 con **TLS autofirmado** (`tls internal`,
  el navegador mostrará advertencia de certificado no confiable — aceptada
  por el usuario, no hay dominio propio).

Archivos: `infra/frontend.tf` (reescrito completo), `infra/frontend_user_data.sh.tpl`
(nuevo, cloud-init), `infra/outputs.tf` (`frontend_url` ahora usa la Elastic
IP), `infra/README.md` y `app/frontend/Dockerfile` (comentarios + build arm64).
Rol EC2: `AmazonEC2ContainerRegistryReadOnly` (pull de ECR) +
`AmazonSSMManagedInstanceCore` (Session Manager, sin SSH/puerto 22).

**Dos problemas de TLS encontrados y resueltos durante el `apply`** (ambos ya
reflejados en `infra/frontend_user_data.sh.tpl`):
1. **Caddyfile `:443 { tls internal ... }` (catch-all sin host)**: al no saber
   para qué nombre emitir el certificado, el handshake TLS fallaba con
   `tlsv1 alert internal error` para cualquier cliente. Fix: especificar la
   IP explícita como dirección del sitio (`https://<EIP> { tls internal ...
   }`), para que Caddy emita el cert con esa IP como SAN al arrancar. Esto
   requirió romper la dependencia circular EIP↔instancia: ahora `aws_eip.frontend`
   se crea **antes** que `aws_instance.frontend` (sin el atributo `instance=`),
   su `public_ip` se pasa al `user_data` vía `templatefile()`, y
   `aws_eip_association.frontend` asocia la IP a la instancia después.
2. **SNI ausente para hosts-IP**: incluso con el cert correcto (SAN
   `IP Address:52.207.130.22`), `curl`/navegadores no envían SNI cuando el
   host es una IP literal, y Caddy no sabe qué certificado servir sin SNI
   (mismo error `internal error`). Fix: bloque global
   `{ default_sni 52.207.130.22 }` en el Caddyfile, para que Caddy use ese
   certificado cuando no llega SNI.

**Nota operativa — error transitorio de `cloud-init`**: en uno de los
reintentos, `dnf install -y docker` falló con `SSL connect error ... Recv
failure: Connection reset by peer` contra el mirror S3 de paquetes AL2023
(error transitorio de red AWS, no de configuración). Recuperado reinstalando
Docker manualmente vía SSM (Session Manager) y re-ejecutando el resto del
script de `user_data`. Si una futura instancia queda sin contenedores
corriendo, revisar `cloud-init status` / `/var/log/cloud-init-output.log` vía
SSM y reintentar `dnf install -y docker` — suele resolverse solo.

**Verificación final (instancia `i-08da8ee7070e6f873`, converge con
`terraform apply` — sin drift)**:
- `curl -k https://52.207.130.22/` → `200`.
- Handshake WebSocket (`curl --http1.1 -H "Upgrade: websocket" ...
  /_stcore/stream`) → **`101 Switching Protocols`** (vs `403` en App Runner).
- Certificado: `Subject Alternative Name: IP Address:52.207.130.22` (autofirmado,
  emitido por la CA local de Caddy — el navegador mostrará advertencia, aceptar
  para continuar).

**URLs finales (vigentes)**:
- API: `https://u5xrtplhif.execute-api.us-east-1.amazonaws.com`
- Frontend: `https://52.207.130.22` (cert autofirmado — aceptar advertencia del navegador)
- Login admin: `admin@kim-neyun.cl` / `KimNeyun2026Dev!`

**Bug post-migración — `ModuleNotFoundError: No module named 'shared'` —
RESUELTO (2026-06-15)**: con el WebSocket ya funcionando, el navegador mostró
este traceback al ejecutar `frontend/app.py` (`from shared.catalog import
...`). Causa: `streamlit run frontend/app.py` solo agrega el directorio del
script (`/srv/frontend`) a `sys.path`, no `/srv` (`WORKDIR`, donde vive
`shared/`) — con App Runner esto nunca se vio porque el WebSocket (403) jamás
llegaba a ejecutar el script en el navegador. Fix: `ENV PYTHONPATH=/srv` en
`app/frontend/Dockerfile`. Reconstruida la imagen arm64, repushed a ECR
(`:latest`, digest `sha256:b71ff416c...`), y recreado el contenedor
`frontend` en la instancia EC2 (`i-08da8ee7070e6f873`) vía SSM — sin
recrear la instancia. Verificado: WebSocket sigue en `101`, `docker logs
frontend` ya sin traceback.

### ✅ Backfill táctico de semanas pasadas (kim-dev, 2026-06-16)

**Diagnóstico previo**: el batch cron solo escribía `SEM#<año>#<semana>` para
`_domingo_de(today())` (semana en curso). Sin historial previo en esta
instancia, el frontend mostraba `st.error("No hay predicción precomputada...")` al
seleccionar cualquier semana anterior.

**Solución implementada**: nuevo flag `KIM_BACKFILL_WEEKS=N` en `run_batch.py`
(y `config.py`). Cuando N>1 el batch itera sobre los N-1 domingos anteriores y
llama `motor.predecir_semana(df_historia, hosp, <domingo>, clima)` por cada
hospital, escribiendo el correspondiente `SEM#<año>#<sem>` en DynamoDB. Skip-
logic: semanas pasadas ya existentes se omiten salvo `KIM_BACKFILL_WEEKS_FORCE=1`;
la semana actual (offset 0) se recalcula siempre (comportamiento cron
preservado). Cambios localizados en **`app/inference/run_batch.py`** y
**`app/shared/config.py`** únicamente — `repository.py`, `engine.py`,
`api/main.py` y el frontend sin tocar.

**Prueba local (docker-compose)**: ejecutado `KIM_BACKFILL_WEEKS=2` contra
DynamoDB Local — 24 predicciones (12 h × 2 sem) escritas; re-ejecución con
mismo flag → 12 predicciones (semana pasada omitida, semana actual
recomputada) → skip-logic verificada.

**Backfill contra kim-dev (DynamoDB real, 2026-06-15 22:58 → 2026-06-16 00:21
UTC)**: corrido como `docker run --rm` con credenciales `kim-dev` apuntando
a `s3://kim-neyun-artifacts-033216807288/` y DynamoDB real (sin
`DYNAMODB_ENDPOINT` → AWS real). Flags: `KIM_BACKFILL_WEEKS=8`,
`ANIOS_PROYECCION=""` (solo táctico, macro ya estaba poblado).
Duración: **83 min** · **96 forecasts** (8 semanas × 12 hospitales) · **0
omitidos** (primera vez, ninguna SEM# preexistía en esas semanas).

**Resultado DynamoDB** — todos 12/12 hospitales por semana:
| `sk` | Domingo de inicio | Semana epi. |
|---|---|---|
| `SEM#2026#17` | 2026-04-27 | Semana 27 abr – 3 may |
| `SEM#2026#18` | 2026-05-04 | Semana 4–10 may |
| `SEM#2026#19` | 2026-05-11 | Semana 11–17 may |
| `SEM#2026#20` | 2026-05-18 | Semana 18–24 may |
| `SEM#2026#21` | 2026-05-25 | Semana 25–31 may |
| `SEM#2026#22` | 2026-06-01 | Semana 1–6 jun |
| `SEM#2026#23` | 2026-06-08 | Semana 7–13 jun |
| `SEM#2026#24` | 2026-06-15 | Semana 14–20 jun (actual) |

**Total `SEM#` items en tabla: 96** (+ 33 `PROY#` y otras previas = 129 total).

**Verificación E2E `/predecir` contra API real**:
- `SEM17` Complejo Asistencial (`fecha: 2026-04-26`) → `200` semana 17, total=68, NORMAL ✅
- `SEM17` SAR Miraflores (`fecha: 2026-04-26`) → `200` semana 17, total=144, NORMAL ✅
- `SEM18` Hospital Dr. Hernán Henríquez (`fecha: 2026-05-03`) → `200` semana 18, total=84, NORMAL ✅
- `SEM19` SAPU Amanecer (`fecha: 2026-05-10`) → `200` semana 19, total=81, NORMAL ✅
- `SEM20` SAR Labranza (`fecha: 2026-05-17`) → `200` semana 20, total=42, NORMAL ✅
- `SEM22` Hospital Makewe (`fecha: 2026-05-31`) → `200` semana 22, total=93, NORMAL ✅
- `SEM23` SAR Pedro de Valdivia (`fecha: 2026-06-07`) → `200` semana 23, total=120, NORMAL ✅
- `SEM24` Complejo Asistencial (`fecha: 2026-06-14`) → `200` semana 24, total=198, PREEMERGENCIA ✅
- `SEM16` (no backfilleada) → `404` "No hay predicción precomputada..." ✅

**Rango consultable en dashboard a partir de 2026-06-16**: semanas **17–24 de
2026** (cualquier día 27 abr – hoy). El cron semanal (EventBridge, lunes
09:00 Chile) añade 1 semana nueva automáticamente cada semana desde aquí en
adelante, acumulando historial progresivamente.

**Nota operativa**: la Lambda batch tiene límite duro de 900s; 8 semanas × 12
hospitales = ~83 min → excede Lambda. Para futuras siembras históricas
adicionales (ampliar a 12-16 semanas, etc.), usar el mismo patrón:
`docker run` local con credenciales `kim-dev`, `KIM_BACKFILL_WEEKS=N`,
`ANIOS_PROYECCION=""`, apuntando a la cuenta 033216807288. Las semanas ya
existentes se saltan automáticamente (skip-logic); solo se computan las nuevas.

### ⏳ Pendiente
- ✅ Artefactos (`.pkl`, CSV DEIS) ya disponibles en `poc/` **y copiados a
  `./models/` (`Modelos_Lags/`+`Modelos_NoLags/`, 78 `.pkl`) + `./data/`**
  (`API_Epidemiologia_Temuco_Padre_Las_Casas.csv`). Listo para batch local.
- ✅ **Batch local end-to-end ya corrido** (ver §4 "Re-verificado 2026-06-14");
  falta **desplegar en AWS** (subir `models/`+`data/`+`manifest.json` a S3,
  ver §5–§6). `terraform apply` aún NO se ha ejecutado (`infra/*.tfstate`
  no existe).
- ✅ **`models/manifest.json` generado (2026-06-14)**: `python -m inference.make_manifest`
  corrido dentro de la imagen `kim_neyun_batch` (sklearn 1.6.1, numpy 2.0.2) →
  `models/manifest.json` con **78 artefactos** (39 Lags + 39 NoLags, igual a los
  `.pkl` presentes). Validado: `ingest.validar_manifest()` corre **sin abortar**
  ("Integridad OK: 78 artefactos validados contra manifest.json") y, probado de
  forma no destructiva con una copia del manifiesto con un sha256 alterado,
  **sí aborta** con `RuntimeError: Validación de artefactos fallida: ... sha256
  no coincide`. Guard de integridad funcionando en ambos sentidos.
- (Opcional) tabs "Manual"/"Metodología" del dashboard son placeholder (como el PoC).
- ✅ **Hornear pesos de Chronos en la imagen**: ya HECHO — `app/inference/Dockerfile`
  tiene la línea `RUN python -c "...ChronosPipeline.from_pretrained(...)"` +
  `ENV HF_HOME=/opt/hf` activas (ya no está comentada). Ver §8 (actualizado).
- (Opcional) SINCA; alerta por baseline por hospital (ver §8, ambos siguen pendientes).
- 🚧 **Backend de usuarios/auth (Aurora Serverless v2 + JWT)**: en curso por otra
  sesión, ver recuadro en §2. Localmente ya está **inicializado y funcional**
  (migración + admin seed + login/me/endpoint protegido verificados, ver §2/§4
  "Auth local inicializada"). Sigue **sin completar/documentar** en §2/§3 a nivel
  de decisiones/arquitectura, y **sin aplicar en AWS** (Aurora aún no existe).

## 5. Cómo continuar

### Local (sin AWS)
1. Dejar artefactos en `./models/` y `./data/` (ver READMEs). ✅ Ya están.
2. ✅ **Hecho (2026-06-14)** — Manifiesto de integridad generado:
   `python -m inference.make_manifest` → `models/manifest.json` (78 artefactos,
   sklearn 1.6.1 / numpy 2.0.2). Regenerarlo cada vez que cambien los `.pkl`.
3. `make up` → API en :8000/docs, dashboard en :8501 (DynamoDB Local en :8001).
4. `make batch` → corre el job, puebla DynamoDB. `make ddb-scan` para ver datos.
   El batch valida los `.pkl` contra el manifiesto y verifica versiones antes de
   cargar nada (aborta si hay mismatch; override `KIM_SKIP_VERSION_GUARD=1`).

### AWS (orden por dependencia de imágenes) — detalle en `infra/README.md`
1. `cd infra && terraform init`
2. Crear ECR + bucket: `terraform apply -target=aws_ecr_repository.api -target=aws_ecr_repository.inference -target=aws_ecr_repository.frontend -target=aws_s3_bucket.artifacts`
3. Build & push: API e inference `--platform linux/arm64`; frontend `--platform linux/amd64`.
4. Generar manifiesto (`python -m inference.make_manifest`) y subir artefactos a
   S3 (`models/` **incluido `manifest.json`**, y `data/`). Si los `.pkl` están en
   Git LFS, hacer `git lfs pull` antes de subir o se suben los punteros (el manifest
   lo detecta en runtime, pero mejor evitarlo).
5. `terraform apply`.
6. Probar el job: `aws lambda invoke --function-name kim-neyun-batch /dev/stdout` y abrir `frontend_url`.

## 6. Lo que debe aportar el humano
- ✅ Los `.pkl` entrenados y el CSV histórico DEIS **ya están** en
  `poc/Modelos_Lags/`, `poc/Modelos_NoLags/` y
  `poc/data/API_Epidemiologia_Temuco_Padre_Las_Casas.csv` (descargados de HF,
  2026-06-13) **y copiados a `./models/` + `./data/`**. Para AWS: subir a S3.
  **Producción usa AMBAS variantes** (no es "una u otra"): `poc/api_motor.py`
  reparte targets — `Modelos_Lags/` para `Cause_Pneumonia,
  Cause_Upper_Respiratory_Infection, Cause_Acute_Bronchitis/Bronchiolitis,
  Cause_Influenza, Cause_Other_Respiratory_Causes, NumMenor1Anio, Num1a4Anios`;
  `Modelos_NoLags/` para `Cause_Bronchial_Obstructive_Crisis,
  Cause_COVID-19_(Confirmed/Suspected), Num5a14Anios, Num15a64Anios, Num65oMas`.
  Carga trío `*_Hybrid_{t}.pkl`+`Scaler_{t}.pkl`+`PCA_{t}.pkl`; si falta, ese
  target cae a Zero-Shot (solo Chronos).
- ✅ Credenciales AWS con permisos para crear la infra — **disponibles desde
  2026-06-14** (perfil `admin`, cuenta `598456800229`,
  `arn:aws:iam::598456800229:user/admin`, verificado con
  `aws sts get-caller-identity`). Lo que falta de §6 es solo: subir
  `models/` (incluido el `manifest.json` ya generado, ver §4/§5) + `data/` a S3
  y correr `terraform apply`.

## 7. Límites de verificación de esta sesión
- ✅ Python compila; `shared.config`/`shared.catalog` importan.
- ✅ `terraform validate` pasa; `docker compose config` pasa.
- ✅ **Batch end-to-end corrido con artefactos reales** (DynamoDB Local poblado).
- ⚠️ **`terraform apply` aún no se ha ejecutado** (no probado en AWS;
  `infra/*.tfstate` no existe). La razón ya **no es** "sin credenciales AWS"
  (✅ disponibles desde 2026-06-14, ver §6) ni "falta `manifest.json`"
  (✅ generado 2026-06-14, ver §4/§5) — el motivo real pendiente es: hay una
  feature de auth/Aurora en curso por otra sesión que añade recursos nuevos a
  `infra/`. El límite de 15 min de Lambda (§8) ya **no bloquea** el deploy —
  solo exige correr la siembra inicial antes de activar el Scheduler.

## 8. Riesgos / TODO técnicos conocidos
- 🆕 **TODO `batch_memory` temporal (kim-dev, 2026-06-15)**: `infra/variables.tf`
  tiene `batch_memory = 3008` (era 8192) porque las cuentas AWS nuevas (<24h)
  tienen un límite antifraude de 3008MB para memoria de Lambda. Subir a 8192
  (o hasta 10240) cuando la cuenta `kim-dev` (033216807288) tenga >24h y
  re-aplicar (`terraform apply -target=aws_lambda_function.batch`). Más
  memoria = más CPU, lo que además ayuda con el siguiente punto.
- ✅ **Backfill táctico SEM# completado (kim-dev, 2026-06-16)**: semanas 17–24
  de 2026 (8 semanas × 12 hospitales = 96 items) pobladas vía `docker run`
  local con `KIM_BACKFILL_WEEKS=8` — ver §4 "Backfill táctico". Para ampliar a
  más semanas: re-ejecutar con `KIM_BACKFILL_WEEKS=N` mayor; skip-logic omite
  automáticamente las ya existentes.
- ℹ️ **Backfill de proyecciones anuales `PROY#` (kim-dev, 2026-06-15)**:
  el job batch no completa las 36 proyecciones anuales (12 hospitales × 2024-
  2026) en una sola invocación porque excede el límite duro de Lambda de 900s.
  Las proyecciones actuales están parcialmente pobladas y la vista macro del
  dashboard funciona para la mayoría de hospitales. Para completar: (a) re-
  invocar `kim-neyun-batch` manualmente varias veces (cada invocación añade
  ~5 items vía `PutItem` incremental con skip-logic para años cerrados); (b)
  subir `batch_memory` a 8192+ (ver TODO `batch_memory` arriba); (c) rediseño
  con Step Functions o Fargate para evitar el límite de 15 min.
- ℹ️ **Límite de 15 min de Lambda — aclarado (2026-06-14, indicación del
  usuario)**: el ~50 min medido en local corresponde a la **siembra inicial**
  (proyección anual para los años de `config.ANIOS_PROYECCION`, ej.
  2024/2025/2026 × 12 hospitales), que se corre **una sola vez, fuera del cron**
  (local o one-off, sin el límite de Lambda). El **cron semanal** (`run_batch.py`)
  ya tiene lógica de skip (verificada en `app/inference/run_batch.py` líneas
  ~76-92): los años cerrados (`anio < anio_actual`) se omiten si ya existen en
  DynamoDB; cada semana solo se recalculan la táctica de 12 hospitales (~12 min)
  + la proyección anual del **año en curso** (52 semanas), lo que cabe en los
  15 min. **Ya no es un riesgo crítico bloqueante.** Queda como nota operativa:
  correr la siembra inicial (con `KIM_BACKFILL_FULL=1` si hace falta recomputar
  años cerrados) **antes** de activar el EventBridge Scheduler, para que el
  primer disparo del cron no caiga con la BD vacía.
- `requirements (poc).txt` pinea versiones altas (torch==2.10.0, etc.); si no
  resuelven en el destino, ajustar pines en `app/inference/requirements.txt`.
  Verificado 2026-06-14: sigue sin cambios.
- ✅ **Hornear pesos de Chronos en la imagen — HECHO** (verificado 2026-06-14,
  ya NO es "línea comentada"): `app/inference/Dockerfile` tiene activas
  `RUN python -c "...ChronosPipeline.from_pretrained(...)"` + `ENV HF_HOME=/opt/hf`.
- ✅ **App Runner corre x86_64 / frontend en amd64 — RESUELTO (2026-06-14)**:
  el encabezado de `app/frontend/Dockerfile` decía "...para App Runner, arm64"
  (contradecía `infra/README.md`/`infra/frontend.tf`, que ya documentaban
  amd64/x86_64 correctamente). Corregido el comentario para reflejar que App
  Runner usa amd64/x86_64 (api/inference en arm64) y para referenciar el build
  con `--platform linux/amd64` (`infra/README.md`, paso "Build & push"). El
  build local via docker-compose sigue sin pin de plataforma (usa la arch
  nativa del host). Verificado: `docker buildx build --platform linux/amd64
  -f app/frontend/Dockerfile app` construye OK; imagen resultante confirmada
  `amd64/linux` con `docker inspect`. No se tocaron Makefile/docker-compose:
  no tienen targets de build/push para AWS, solo `infra/README.md` los documenta
  y ya estaba correcto.
- ⚠️ `nivel_alerta` usa umbral global 150 (del PoC); debería ser baseline por
  hospital. Verificado 2026-06-14: sin cambios, sigue pendiente.
- ⚠️ SINCA aún no integrado: la calidad del aire viene de Open-Meteo (como el
  PoC). Verificado 2026-06-14: sin cambios, solo un comentario a futuro en
  `ingest.py`.
- DynamoDB en vez de PostgreSQL (el formulario menciona PostgreSQL); para el MVP
  es mejor fit (accesos por clave) y más barato; documentarlo si el concurso lo
  exige. Nota 2026-06-14: la nueva feature de auth (ver §2) sí agrega Postgres
  (Aurora Serverless v2), pero **solo para la tabla de usuarios**, no para los
  datos de predicción — DynamoDB sigue siendo el store de predicciones.
- 🆕 **`infra/versions.tf` / provider `random`** (2026-06-14): en esta sesión se
  quitó la declaración del provider `random` de `required_providers` por
  parecer muerta. Ahora `infra/auth_db.tf` (de la feature de auth, en curso)
  usa `random_password.db_master` y `random_password.jwt`. `terraform validate`
  sigue pasando (Terraform resuelve `random` implícitamente al ser un provider
  del namespace `hashicorp/*`), pero sería buena práctica re-declararlo
  explícitamente en `required_providers` cuando esa feature se consolide.
