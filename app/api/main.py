"""API de KIM-NEYÜN.

Mantiene la firma de los endpoints del PoC (`/predecir`, `/proyeccion_anual`)
pero, en lugar de correr el modelo, devuelve las predicciones precomputadas por
el job batch y almacenadas en DynamoDB. Esto la hace liviana y apta para
Lambda (sin torch).

Documentación interactiva (autogenerada por FastAPI):
- Swagger UI:  GET /docs
- ReDoc:       GET /redoc
- Spec OpenAPI: GET /openapi.json  (el front puede importarlo para generar su cliente)
"""

import datetime
import logging
import os

from epiweeks import Week
from fastapi import Depends, FastAPI, HTTPException
from mangum import Mangum
from pydantic import BaseModel, Field

from api import auth
from api.auth import get_current_user
from shared import repository
from shared.catalog import HOSPITALES
from shared.users_db import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kim.api")

# Detrás de API Gateway la API cuelga de un stage (p.ej. /prod), por lo que
# Swagger UI necesita saber ese prefijo para construir bien las URLs y el link a
# openapi.json. En local queda vacío. Mangum además recorta el base path.
ROOT_PATH = os.environ.get("API_ROOT_PATH", "")

DESCRIPCION = """
API de **KIM-NEYÜN**: pronóstico de demanda de urgencias respiratorias por
semana epidemiológica para los centros de salud de Temuco y Padre Las Casas.

Las predicciones las precomputa un job batch (Chronos-T5 + corrección ML) y se
almacenan en DynamoDB; esta API solo las lee, por lo que es liviana y rápida.

### Flujo típico para el front
1. `GET /hospitales` para poblar el selector de centros.
2. `POST /predecir` para la predicción táctica de una semana concreta.
3. `POST /proyeccion_anual` para la curva estratégica de 52 semanas.
"""

TAGS_METADATA = [
    {"name": "Salud", "description": "Estado del servicio."},
    {"name": "Auth", "description": "Login y gestión de usuarios. Los endpoints de datos requieren un token Bearer."},
    {"name": "Catálogo", "description": "Datos de dominio para poblar el dashboard."},
    {"name": "Predicciones", "description": "Pronósticos táctico (semanal) y estratégico (anual)."},
]

app = FastAPI(
    title="KIM-NEYÜN - API",
    version="1.0.0",
    description=DESCRIPCION,
    openapi_tags=TAGS_METADATA,
    contact={"name": "Equipo Backend/Infra KIM-NEYÜN"},
    license_info={"name": "Uso interno UCTemuco"},
    root_path=ROOT_PATH,
)

# Router de autenticación (login, /me, alta de usuarios).
app.include_router(auth.router)


# --- Modelos de entrada -----------------------------------------------------

class SolicitudMicro(BaseModel):
    EstablecimientoGlosa: str = Field(
        ...,
        description="Nombre exacto del centro de salud (ver GET /hospitales).",
        examples=["Hospital Dr. Hernán Henríquez Aravena (Temuco)"],
    )
    fecha_referencia: str = Field(
        ...,
        description="Fecha dentro de la semana epidemiológica a consultar (YYYY-MM-DD).",
        examples=["2026-06-10"],
    )


class SolicitudMacro(BaseModel):
    EstablecimientoGlosa: str = Field(
        ...,
        description="Nombre exacto del centro de salud (ver GET /hospitales).",
        examples=["Hospital Dr. Hernán Henríquez Aravena (Temuco)"],
    )
    anio_proyeccion: int = Field(
        ...,
        description="Año para el que se solicita la proyección de 52 semanas.",
        examples=[2026],
    )


# --- Modelos de salida ------------------------------------------------------

class HealthResp(BaseModel):
    status: str = Field(examples=["ok"])


class HospitalesResp(BaseModel):
    hospitales: list[str] = Field(description="Centros de salud disponibles.")


class EstimacionesResp(BaseModel):
    Causas: dict[str, float] = Field(description="Estimación por causa respiratoria.")
    Edades: dict[str, float] = Field(description="Estimación por grupo etario.")
    Total: float = Field(description="Suma de las estimaciones por causa.")


class PrediccionSemanaResp(BaseModel):
    hospital: str
    semana_epi: int = Field(description="Número de semana epidemiológica (sistema CDC).")
    # El PoC entrega la clave con tilde; se mantiene por compatibilidad con el front.
    anio: int = Field(serialization_alias="año", description="Año de la semana epidemiológica.")
    estimaciones: EstimacionesResp = Field(
        description="Estimación por target, agrupada en causas y grupos etarios.",
    )
    temperatura_referencia: float = Field(description="Temperatura usada como estresor ambiental.")
    nivel_alerta: str = Field(
        description="Semáforo de alerta por centro: NORMAL, MODERADO o CRITICO.",
    )

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "hospital": "Hospital Dr. Hernán Henríquez Aravena (Temuco)",
                    "semana_epi": 24,
                    "año": 2026,
                    "estimaciones": {
                        "Causas": {"Pneumonia": 42.0, "Influenza": 18.0},
                        "Edades": {"65oMas": 73.0},
                        "Total": 60.0,
                    },
                    "temperatura_referencia": 8.4,
                    "nivel_alerta": "CRITICO",
                }
            ]
        },
    }


class ProyeccionAnualResp(BaseModel):
    hospital: str
    anio_proyectado: int
    semanas: list[int] = Field(description="Semanas epidemiológicas (1..52).")
    curva_ia: list[float] = Field(description="Curva proyectada por el modelo.")
    curva_real: list = Field(description="Curva histórica real (puede tener nulos a futuro).")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "hospital": "Hospital Dr. Hernán Henríquez Aravena (Temuco)",
                    "anio_proyectado": 2026,
                    "semanas": [1, 2, 3],
                    "curva_ia": [120.0, 135.0, 150.0],
                    "curva_real": [118, 130, None],
                }
            ]
        }
    }


# --- Endpoints --------------------------------------------------------------

@app.get("/health", response_model=HealthResp, tags=["Salud"], summary="Estado del servicio")
def health():
    return {"status": "ok"}


@app.get("/hospitales", response_model=HospitalesResp, tags=["Catálogo"],
         summary="Catálogo de centros disponibles")
def hospitales(current: User = Depends(get_current_user)):
    """Catálogo de centros disponibles (útil para poblar el dashboard)."""
    return {"hospitales": HOSPITALES}


@app.post(
    "/predecir",
    response_model=PrediccionSemanaResp,
    response_model_by_alias=True,
    tags=["Predicciones"],
    summary="Predicción táctica (semanal)",
    responses={
        404: {"description": "No hay predicción precomputada para esos parámetros."},
        422: {"description": "Formato de fecha inválido."},
    },
)
def predecir(solicitud: SolicitudMicro, current: User = Depends(get_current_user)):
    """Predicción táctica de la semana epidemiológica de `fecha_referencia`."""
    try:
        fecha_ref = datetime.datetime.strptime(solicitud.fecha_referencia, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="fecha_referencia debe tener formato YYYY-MM-DD")

    semana_epi = Week.fromdate(fecha_ref, system="cdc")
    row = repository.get_prediccion_semana(
        solicitud.EstablecimientoGlosa, semana_epi.year, semana_epi.week
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No hay predicción precomputada para '{solicitud.EstablecimientoGlosa}' "
                f"en la semana {semana_epi.week}-{semana_epi.year}. "
                "El job batch precomputa la semana en curso."
            ),
        )

    # El modelo serializa 'anio' como 'año' (alias) para mantener la forma del PoC.
    return {
        "hospital": row["hospital"],
        "semana_epi": row["semana_epi"],
        "anio": row["anio"],
        "estimaciones": row["estimaciones"],
        "temperatura_referencia": row["temp_ref"],
        "nivel_alerta": row["nivel_alerta"],
    }


@app.post(
    "/proyeccion_anual",
    response_model=ProyeccionAnualResp,
    tags=["Predicciones"],
    summary="Proyección estratégica (anual, 52 semanas)",
    responses={404: {"description": "No hay proyección precomputada para esos parámetros."}},
)
def proyeccion_anual(solicitud: SolicitudMacro, current: User = Depends(get_current_user)):
    """Proyección estratégica de 52 semanas para el año indicado."""
    row = repository.get_proyeccion_anual(
        solicitud.EstablecimientoGlosa, solicitud.anio_proyeccion
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No hay proyección precomputada para '{solicitud.EstablecimientoGlosa}' "
                f"en {solicitud.anio_proyeccion}."
            ),
        )
    return {
        "hospital": row["hospital"],
        "anio_proyectado": row["anio"],
        "semanas": row["semanas"],
        "curva_ia": row["curva_ia"],
        "curva_real": row["curva_real"],
    }


# Adaptador ASGI -> Lambda (API Gateway HTTP API). En local se usa uvicorn.
handler = Mangum(app)
