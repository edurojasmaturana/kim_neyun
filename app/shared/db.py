"""Acceso a DynamoDB.

Construye el recurso/cliente boto3 apuntando a AWS o a DynamoDB Local
(`DYNAMODB_ENDPOINT`). El engine se cachea para reutilizarse entre invocaciones
tibias de Lambda.
"""

import functools

import boto3

from . import config


def _kwargs() -> dict:
    kw = {"region_name": config.AWS_REGION}
    if config.DYNAMODB_ENDPOINT:
        kw["endpoint_url"] = config.DYNAMODB_ENDPOINT
    return kw


@functools.lru_cache(maxsize=1)
def get_table():
    return boto3.resource("dynamodb", **_kwargs()).Table(config.DYNAMODB_TABLE)


@functools.lru_cache(maxsize=1)
def get_client():
    return boto3.client("dynamodb", **_kwargs())
