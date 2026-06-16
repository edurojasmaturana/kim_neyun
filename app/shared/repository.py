"""Repositorio de predicciones sobre DynamoDB (tabla única).

Modelo de clave (accesos por clave, sin scans):
- Predicción semanal: pk=<hospital>, sk="SEM#<anio>#<semana>"
- Proyección anual:   pk=<hospital>, sk="PROY#<anio>"

El payload variable se guarda como JSON en el atributo `data` para evitar
problemas de tipos (Decimal/float) y mantener el mismo shape del PoC.
"""

import json

from botocore.exceptions import ClientError

from . import config
from .db import get_client, get_table


def _sk_semana(anio: int, semana: int) -> str:
    return f"SEM#{anio}#{int(semana):02d}"


def _sk_proy(anio: int) -> str:
    return f"PROY#{anio}"


def ensure_table() -> None:
    """Crea la tabla on-demand si no existe (idempotente).

    En AWS la tabla la crea Terraform; esto es útil en local (DynamoDB Local) y
    como red de seguridad.
    """
    client = get_client()
    try:
        client.describe_table(TableName=config.DYNAMODB_TABLE)
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    client.create_table(
        TableName=config.DYNAMODB_TABLE,
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
    )
    client.get_waiter("table_exists").wait(TableName=config.DYNAMODB_TABLE)


def _get_item(key: dict) -> dict | None:
    try:
        return get_table().get_item(Key=key).get("Item")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return None  # tabla aún no creada -> tratar como "sin datos"
        raise


# --- Predicción semanal (táctico) ---

def upsert_prediccion_semana(
    hospital: str,
    anio: int,
    semana_epi: int,
    total: int,
    nivel_alerta: str,
    temp_ref: float,
    estimaciones: dict,
) -> None:
    get_table().put_item(
        Item={
            "pk": hospital,
            "sk": _sk_semana(anio, semana_epi),
            "tipo": "semana",
            "anio": anio,
            "semana_epi": int(semana_epi),
            "data": json.dumps(
                {
                    "total": total,
                    "nivel_alerta": nivel_alerta,
                    "temp_ref": temp_ref,
                    "estimaciones": estimaciones,
                }
            ),
        }
    )


def get_prediccion_semana(hospital: str, anio: int, semana_epi: int) -> dict | None:
    item = _get_item({"pk": hospital, "sk": _sk_semana(anio, semana_epi)})
    if not item:
        return None
    d = json.loads(item["data"])
    return {
        "hospital": hospital,
        "anio": anio,
        "semana_epi": int(semana_epi),
        "total": d["total"],
        "nivel_alerta": d["nivel_alerta"],
        "temp_ref": d["temp_ref"],
        "estimaciones": d["estimaciones"],
    }


# --- Proyección anual (macro) ---

def upsert_proyeccion_anual(
    hospital: str,
    anio: int,
    semanas: list[int],
    curva_ia: list[int],
    curva_real: list,
    total_ia: int,
) -> None:
    get_table().put_item(
        Item={
            "pk": hospital,
            "sk": _sk_proy(anio),
            "tipo": "proyeccion",
            "anio": anio,
            "data": json.dumps(
                {
                    "semanas": semanas,
                    "curva_ia": curva_ia,
                    "curva_real": curva_real,
                    "total_ia": total_ia,
                }
            ),
        }
    )


def get_proyeccion_anual(hospital: str, anio: int) -> dict | None:
    item = _get_item({"pk": hospital, "sk": _sk_proy(anio)})
    if not item:
        return None
    d = json.loads(item["data"])
    return {"hospital": hospital, "anio": anio, **d}
