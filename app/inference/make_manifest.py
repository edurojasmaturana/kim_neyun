"""CLI: genera el manifiesto de integridad de los artefactos del modelo.

Crea `<MODELS_DIR>/manifest.json` con el sha256 + tamaño de cada `.pkl` y las
versiones de sklearn/numpy del entorno. Correr en LOCAL tras entrenar o copiar
los `.pkl` a `models/`, ANTES de subirlos a S3:

    python -m inference.make_manifest

Luego subir `models/` completo (incluido `manifest.json`) al bucket. En cada
batch, `ingest.validar_manifest()` verifica los artefactos contra este manifiesto
y aborta si hay descargas truncadas, punteros LFS sin resolver o desajuste de
versiones.
"""

import logging

from shared import config

from . import ingest

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

if __name__ == "__main__":
    ingest.generar_manifest(config.MODELS_DIR)
