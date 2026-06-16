"""Configuración por variables de entorno.

Permite correr el mismo código en local (DynamoDB Local + rutas locales) y en
AWS (DynamoDB + artefactos en S3) sin cambios de código.
"""

import os

# --- AWS ---
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# --- DynamoDB ---
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "kim-neyun-predicciones")
# Endpoint para DynamoDB Local (p.ej. http://dynamodb:8000). Vacío en AWS.
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT") or None

# --- Artefactos del modelo y datos históricos ---
# Carpeta local con Modelos_Lags/ y Modelos_NoLags/ (en Lambda debe ir bajo /tmp).
MODELS_DIR = os.environ.get("MODELS_DIR", "models")
# Opcional: prefijo S3 desde donde sincronizar los .pkl al arrancar el job.
MODELS_S3_URI = os.environ.get("MODELS_S3_URI")

# Base epidemiológica histórica (DEIS) consolidada.
HISTORIA_CSV = os.environ.get(
    "HISTORIA_CSV", "data/API_Epidemiologia_Temuco_Padre_Las_Casas.csv"
)
HISTORIA_S3_URI = os.environ.get("HISTORIA_S3_URI")

# Modelo fundacional: id de HF o ruta local horneada en la imagen.
CHRONOS_MODEL = os.environ.get("CHRONOS_MODEL", "amazon/chronos-t5-small")

# --- Integridad y versiones de artefactos ---
# Versiones con las que se serializaron los .pkl (Scaler/PCA de sklearn, arrays de
# numpy). Cargarlos con otra versión puede fallar el import de la clase o, peor,
# cargar bien y PREDECIR DISTINTO en silencio. El motor lo verifica al arrancar.
ARTIFACT_SKLEARN_VERSION = os.environ.get("ARTIFACT_SKLEARN_VERSION", "1.6.1")
ARTIFACT_NUMPY_VERSION = os.environ.get("ARTIFACT_NUMPY_VERSION", "2.0.2")
# Manifiesto de integridad (sha256 + bytes por archivo) dentro de MODELS_DIR.
MODELS_MANIFEST = os.environ.get("MODELS_MANIFEST", "manifest.json")
# Escotilla de emergencia: degrada los errores de versión/integridad a warning.
SKIP_VERSION_GUARD = os.environ.get("KIM_SKIP_VERSION_GUARD") == "1"

# --- Backend de usuarios (Postgres / Aurora Serverless v2) ---
# Local: cadena directa a Postgres, p.ej.
#   postgresql+psycopg2://kim:kim@postgres:5432/kim_users
# AWS:   se deja vacía y se usan los ARN del Data API de Aurora (sin VPC en Lambda).
USERS_DATABASE_URL = os.environ.get("USERS_DATABASE_URL") or None
# ARN del cluster Aurora SLSv2 y del secreto (Secrets Manager). Si AURORA_CLUSTER_ARN
# está presente, el acceso se hace por Data API (postgresql+auroradataapi://).
AURORA_CLUSTER_ARN = os.environ.get("AURORA_CLUSTER_ARN") or None
AURORA_SECRET_ARN = os.environ.get("AURORA_SECRET_ARN") or None
AURORA_DATABASE = os.environ.get("AURORA_DATABASE", "kim_users")

# --- JWT ---
# Secreto de firma. En AWS se inyecta desde Secrets Manager; en local hay un default
# SOLO para desarrollo (nunca usar en producción).
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-change-me")
JWT_ALG = os.environ.get("JWT_ALG", "HS256")
ACCESS_TOKEN_TTL_MIN = int(os.environ.get("ACCESS_TOKEN_TTL_MIN", "480"))  # 8 h

# --- Parámetros de negocio ---
# Semáforo de alerta de 3 niveles (NORMAL/MODERADO/CRITICO). Los umbrales se
# derivan del histórico semanal de CADA centro vía percentiles (un volumen
# "crítico" en un SAPU chico no es comparable al de un hospital de alta
# complejidad): P_MODERADO entra en MODERADO, P_CRITICO entra en CRITICO.
ALERTA_PCT_MODERADO = float(os.environ.get("ALERTA_PCT_MODERADO", "75"))
ALERTA_PCT_CRITICO = float(os.environ.get("ALERTA_PCT_CRITICO", "90"))
# Mínimo de semanas históricas para confiar en los percentiles por centro; por
# debajo de esto se usa ALERTA_THRESHOLD como respaldo global.
ALERTA_MIN_SEMANAS = int(os.environ.get("ALERTA_MIN_SEMANAS", "12"))
# Umbral global de respaldo, usado solo cuando un centro no tiene historia
# suficiente para calcular sus percentiles (el PoC usaba 150 en el frontend).
ALERTA_THRESHOLD = int(os.environ.get("ALERTA_THRESHOLD", "150"))

# Coordenadas de referencia (Temuco) para Open-Meteo.
LAT = float(os.environ.get("LAT", "-38.7396"))
LON = float(os.environ.get("LON", "-72.5984"))

# Años para los que se precomputa la proyección anual (macro).
ANIOS_PROYECCION = [
    int(x) for x in os.environ.get("ANIOS_PROYECCION", "2024,2025,2026").split(",") if x.strip()
]

# Los años ya cerrados (anteriores al actual) producen siempre la misma curva:
# su contexto histórico no cambia. El batch los computa una sola vez y luego los
# omite. Activa esta escotilla (KIM_BACKFILL_FULL=1) para forzar el recálculo de
# TODOS los años —p.ej. tras corregir o ampliar el CSV histórico.
BACKFILL_FULL = os.environ.get("KIM_BACKFILL_FULL") == "1"

# Backfill táctico: cuántas semanas (incluyendo la actual) precomputa el batch
# en SEM#<año>#<semana> por corrida. 1 (default) = solo la semana actual, igual
# que antes. N>1 además recalcula las N-1 semanas anteriores (si hay historial
# suficiente), saltando las que ya existan en DynamoDB salvo
# KIM_BACKFILL_WEEKS_FORCE=1.
BACKFILL_WEEKS = int(os.environ.get("KIM_BACKFILL_WEEKS", "1"))
BACKFILL_WEEKS_FORCE = os.environ.get("KIM_BACKFILL_WEEKS_FORCE") == "1"
