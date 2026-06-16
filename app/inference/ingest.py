"""Ingesta de datos: clima/calidad del aire (Open-Meteo) e histórico DEIS.

`extraer_clima_3_semanas`, `safe_calc` y `calcular_metricas_semanales` se portan
tal cual del PoC. Se agregan utilidades para cargar el histórico y sincronizar
artefactos desde S3 cuando corre en AWS.

Nota: el PoC obtiene MP2.5/MP10/CO desde la API de calidad de aire de
Open-Meteo. SINCA puede integrarse aquí a futuro como fuente alternativa.
"""

import datetime
import hashlib
import json
import logging
import os

import numpy as np
import openmeteo_requests
import pandas as pd
from retry_requests import retry

from shared import config

logger = logging.getLogger(__name__)


# --- Funciones de seguridad climática (idénticas al PoC) ---

def safe_calc(arr, func):
    if len(arr) == 0:
        return 0.0
    if np.isnan(arr).all():
        return 0.0
    val = func(arr)
    return float(val) if not np.isnan(val) else 0.0


def calcular_metricas_semanales(arr_horario, nombre_var):
    w0 = arr_horario[-168:]
    w1 = arr_horario[-336:-168]
    w2 = arr_horario[-504:-336]
    if nombre_var == "precipitaciones":
        return {
            f"{nombre_var}_Total": safe_calc(w0, np.nansum),
            f"{nombre_var}_Total_Lag1": safe_calc(w1, np.nansum),
            f"{nombre_var}_Total_Lag2": safe_calc(w2, np.nansum),
        }
    return {
        f"{nombre_var}_Avg": safe_calc(w0, np.nanmean),
        f"{nombre_var}_Max": safe_calc(w0, np.nanmax),
        f"{nombre_var}_Avg_Lag1": safe_calc(w1, np.nanmean),
        f"{nombre_var}_Max_Lag1": safe_calc(w1, np.nanmax),
        f"{nombre_var}_Avg_Lag2": safe_calc(w2, np.nanmean),
        f"{nombre_var}_Max_Lag2": safe_calc(w2, np.nanmax),
    }


def extraer_clima_3_semanas(fecha_referencia, lat=None, lon=None):
    """Descarga 28 días de clima + calidad de aire y agrega métricas/lags."""
    lat = config.LAT if lat is None else lat
    lon = config.LON if lon is None else lon
    try:
        # Sesión con reintentos, sin requests_cache: su serializador (cattrs)
        # rompe al cachear con `NameError: RequestsCookieJar` y degradaba todo a
        # Zero-Shot. En un batch semanal el caché en disco no aporta.
        openmeteo = openmeteo_requests.Client(session=retry(retries=5))
        fin = fecha_referencia.strftime("%Y-%m-%d")
        inicio = (fecha_referencia - datetime.timedelta(days=28)).strftime("%Y-%m-%d")

        weather_res = openmeteo.weather_api(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": inicio,
                "end_date": fin,
                "hourly": ["temperature_2m", "surface_pressure", "wind_speed_10m", "precipitation"],
                "timezone": "America/Santiago",
            },
        )[0]
        aq_res = openmeteo.weather_api(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": inicio,
                "end_date": fin,
                "hourly": ["pm10", "pm2_5", "carbon_monoxide"],
                "timezone": "America/Santiago",
            },
        )[0]

        wh_hourly = weather_res.Hourly()
        temp = wh_hourly.Variables(0).ValuesAsNumpy()
        pres = wh_hourly.Variables(1).ValuesAsNumpy()
        vel = wh_hourly.Variables(2).ValuesAsNumpy()
        precip = wh_hourly.Variables(3).ValuesAsNumpy()

        aq_hourly = aq_res.Hourly()
        pm10 = aq_hourly.Variables(0).ValuesAsNumpy()
        pm25 = aq_hourly.Variables(1).ValuesAsNumpy()
        co = aq_hourly.Variables(2).ValuesAsNumpy() / 1000.0

        clima_dict = {}
        clima_dict.update(calcular_metricas_semanales(temp, "Temperatura"))
        clima_dict.update(calcular_metricas_semanales(pres, "presion"))
        clima_dict.update(calcular_metricas_semanales(vel, "Vel"))
        clima_dict.update(calcular_metricas_semanales(precip, "precipitaciones"))
        clima_dict.update(calcular_metricas_semanales(pm10, "PM10"))
        clima_dict.update(calcular_metricas_semanales(pm25, "PM25"))
        clima_dict.update(calcular_metricas_semanales(co, "Monoxido"))
        return clima_dict
    except Exception as e:  # noqa: BLE001 - degradación controlada como en el PoC
        logger.error("Error extrayendo clima: %s", e)
        return None


# --- Carga del histórico y sincronización desde S3 ---

def _parse_s3_uri(uri: str):
    assert uri.startswith("s3://"), f"URI S3 inválida: {uri}"
    bucket, _, key = uri[5:].partition("/")
    return bucket, key


def sync_models_from_s3() -> None:
    """Descarga recursivamente los .pkl desde MODELS_S3_URI a MODELS_DIR."""
    if not config.MODELS_S3_URI:
        return
    import boto3

    bucket, prefix = _parse_s3_uri(config.MODELS_S3_URI)
    s3 = boto3.client("s3", region_name=config.AWS_REGION)
    paginator = s3.get_paginator("list_objects_v2")
    n = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len(prefix):].lstrip("/")
            if not rel:
                continue
            dest = os.path.join(config.MODELS_DIR, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            s3.download_file(bucket, key, dest)
            n += 1
    logger.info("Sincronizados %d artefactos desde %s", n, config.MODELS_S3_URI)


# --- Manifiesto de integridad de artefactos ---

def _sha256(path: str, _chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(_chunk), b""):
            h.update(blk)
    return h.hexdigest()


def generar_manifest(models_dir: str | None = None) -> str:
    """Genera <models_dir>/manifest.json con sha256+bytes de cada .pkl y las
    versiones de sklearn/numpy del entorno.

    Correr en local tras entrenar/copiar los .pkl, ANTES de subirlos a S3:
        python -m inference.make_manifest
    Luego subir models/ completo (incluido manifest.json) al bucket.
    """
    import sklearn  # import perezoso: solo necesario al generar, no en cada batch

    models_dir = models_dir or config.MODELS_DIR
    files: dict = {}
    for root, _dirs, names in os.walk(models_dir):
        for name in sorted(names):
            if not name.endswith(".pkl"):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, models_dir)
            files[rel] = {"sha256": _sha256(full), "bytes": os.path.getsize(full)}

    manifest = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "versions": {"scikit-learn": sklearn.__version__, "numpy": np.__version__},
        "files": files,
    }
    dest = os.path.join(models_dir, config.MODELS_MANIFEST)
    with open(dest, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    logger.info("Manifest escrito: %s (%d artefactos)", dest, len(files))
    return dest


def validar_manifest(models_dir: str | None = None) -> None:
    """Valida los .pkl de <models_dir> contra el manifest.json: versiones de
    librerías + tamaño y sha256 por archivo.

    Detecta descargas truncadas desde S3, punteros de Git LFS sin resolver y .pkl
    entrenados con otra versión, ANTES de cargarlos. Sin manifest = warning (no
    rompe el flujo local previo a esta mejora). Override: KIM_SKIP_VERSION_GUARD=1.
    """
    import sklearn

    models_dir = models_dir or config.MODELS_DIR
    ruta = os.path.join(models_dir, config.MODELS_MANIFEST)
    if not os.path.exists(ruta):
        logger.warning(
            "Sin %s en %s; se omite la validación de integridad de artefactos.",
            config.MODELS_MANIFEST, models_dir,
        )
        return

    with open(ruta) as f:
        manifest = json.load(f)

    problemas: list[str] = []

    # 1) Versiones declaradas en el manifest vs entorno actual.
    runtime = {"scikit-learn": sklearn.__version__, "numpy": np.__version__}
    for lib, esperado in manifest.get("versions", {}).items():
        actual = runtime.get(lib)
        if actual and actual != esperado:
            problemas.append(f"{lib}: artefactos creados con {esperado}, entorno tiene {actual}")

    # 2) Integridad archivo por archivo.
    archivos = manifest.get("files", {})
    for rel, meta in archivos.items():
        full = os.path.join(models_dir, rel)
        if not os.path.exists(full):
            problemas.append(f"falta {rel}")
            continue
        size = os.path.getsize(full)
        if size != meta.get("bytes"):
            problemas.append(
                f"{rel}: {size} bytes (esperado {meta.get('bytes')}) "
                "— ¿descarga truncada o puntero LFS sin resolver?"
            )
            continue  # sha redundante si el tamaño ya difiere
        if _sha256(full) != meta.get("sha256"):
            problemas.append(f"{rel}: sha256 no coincide — archivo corrupto o alterado")

    if not problemas:
        logger.info(
            "Integridad OK: %d artefactos validados contra %s", len(archivos), config.MODELS_MANIFEST
        )
        return

    detalle = "; ".join(problemas[:10])
    if len(problemas) > 10:
        detalle += f" (+{len(problemas) - 10} más)"
    msg = f"Validación de artefactos fallida: {detalle}"
    if config.SKIP_VERSION_GUARD:
        logger.warning("[INTEGRITY GUARD OMITIDO] %s", msg)
    else:
        raise RuntimeError(msg)


def cargar_historia() -> pd.DataFrame:
    """Carga la base epidemiológica histórica (DEIS) desde S3 o disco."""
    if config.HISTORIA_S3_URI:
        import boto3

        bucket, key = _parse_s3_uri(config.HISTORIA_S3_URI)
        os.makedirs("/tmp/kim", exist_ok=True)
        local = "/tmp/kim/historia.csv"
        boto3.client("s3", region_name=config.AWS_REGION).download_file(bucket, key, local)
        logger.info("Histórico descargado desde %s", config.HISTORIA_S3_URI)
        return pd.read_csv(local)
    logger.info("Cargando histórico local: %s", config.HISTORIA_CSV)
    return pd.read_csv(config.HISTORIA_CSV)
