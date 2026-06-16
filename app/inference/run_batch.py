"""Punto de entrada del job batch.

Precomputa, para los 12 centros: (1) la predicción de la semana epidemiológica
actual (más, opcionalmente, semanas anteriores vía backfill) y (2) la
proyección anual (52 semanas) para los años configurados. Persiste todo en
DynamoDB vía el repositorio compartido.

La proyección de años ya cerrados se computa una sola vez (es fija) y luego se
omite en los runs siguientes; solo el año en curso se recalcula cada semana.
KIM_BACKFILL_FULL=1 fuerza el recálculo de todos los años.

La predicción táctica (SEM#<año>#<semana>) siempre recalcula la semana actual.
KIM_BACKFILL_WEEKS=N (default 1) además precomputa las N-1 semanas anteriores
si hay historial suficiente, saltando las que ya existan salvo
KIM_BACKFILL_WEEKS_FORCE=1.

Uso: python -m inference.run_batch
"""

import datetime
import logging

from epiweeks import Week

from shared import alertas, config, repository
from shared.catalog import HOSPITALES

from . import ingest
from .engine import MotorHibrido

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("kim.batch")


def _domingo_de(d: datetime.date) -> datetime.date:
    """Retrocede al domingo de la semana de `d` (inicio de semana epi., como el PoC)."""
    dias_a_restar = (d.weekday() + 1) % 7
    return d - datetime.timedelta(days=dias_a_restar)


def main() -> None:
    logger.info("== KIM-NEYÜN batch ==")
    ingest.sync_models_from_s3()  # no-op si no hay MODELS_S3_URI
    ingest.validar_manifest()  # integridad + versiones antes de cargar artefactos
    repository.ensure_table()

    motor = MotorHibrido()
    df_historia = ingest.cargar_historia()

    fecha_ref = _domingo_de(datetime.date.today())

    # --- Táctico: semana actual + backfill de semanas anteriores ---
    # La semana actual (offset 0) siempre se recalcula, igual que antes. Si
    # KIM_BACKFILL_WEEKS=N > 1, además se recorren las N-1 semanas previas;
    # cada una se salta si ya existe su SEM# en DynamoDB, salvo
    # KIM_BACKFILL_WEEKS_FORCE=1.
    n_semanas = max(1, config.BACKFILL_WEEKS)
    ok = 0
    omitidos_sem = 0
    for offset in range(n_semanas):
        fecha_ref_semana = fecha_ref - datetime.timedelta(weeks=offset)
        es_semana_actual = offset == 0

        # El clima es por ubicación (Temuco), idéntico para todos los centros,
        # pero depende de la ventana de 28 días anterior a `fecha_ref_semana`:
        # se descarga una vez por semana procesada.
        clima = ingest.extraer_clima_3_semanas(fecha_ref_semana) or {}
        if not clima:
            logger.warning(
                "Sin datos de clima para semana de %s; las predicciones usarán "
                "solo la base Zero-Shot.", fecha_ref_semana,
            )

        for hosp in HOSPITALES:
            if not es_semana_actual and not config.BACKFILL_WEEKS_FORCE:
                semana_epi = Week.fromdate(fecha_ref_semana, system="cdc")
                if repository.get_prediccion_semana(hosp, semana_epi.year, semana_epi.week) is not None:
                    omitidos_sem += 1
                    continue
            try:
                pred = motor.predecir_semana(df_historia, hosp, fecha_ref_semana, clima)
            except Exception as e:  # noqa: BLE001
                logger.exception("Fallo prediciendo %s (semana de %s): %s", hosp, fecha_ref_semana, e)
                continue
            if pred is None:
                logger.warning("Sin historial suficiente para %s en semana de %s; se omite.", hosp, fecha_ref_semana)
                continue
            total = pred["estimaciones"]["Total"]
            umbrales = alertas.umbrales_centro(
                df_historia, hosp, pred["año"], pred["semana_epi"]
            )
            nivel = alertas.clasificar(total, umbrales)
            repository.upsert_prediccion_semana(
                hospital=hosp,
                anio=pred["año"],
                semana_epi=pred["semana_epi"],
                total=total,
                nivel_alerta=nivel,
                temp_ref=pred["temperatura_referencia"],
                estimaciones=pred["estimaciones"],
            )
            ok += 1
            logger.info(
                "OK semana %02d-%d: %s -> total=%d (%s)",
                pred["semana_epi"], pred["año"], hosp, total, nivel,
            )

    # --- Macro: proyección anual ---
    # Los años ya cerrados (anteriores al actual) producen siempre la misma curva:
    # su contexto histórico (`Anio < anio_objetivo`) no cambia. Se computan una sola
    # vez —el primer run, o cuando aún no existen en la BD— y luego se omiten, para
    # no repetir cada semana los forecasts caros de Chronos de 52 pasos y dejar
    # margen frente al límite de 15 min de la Lambda. El año en curso SÍ se recalcula
    # siempre (su `curva_real` crece semana a semana). KIM_BACKFILL_FULL=1 fuerza todo.
    anio_actual = fecha_ref.year
    ok_macro = 0
    omitidos = 0
    for hosp in HOSPITALES:
        for anio in config.ANIOS_PROYECCION:
            anio_cerrado = anio < anio_actual
            if anio_cerrado and not config.BACKFILL_FULL:
                if repository.get_proyeccion_anual(hosp, anio) is not None:
                    omitidos += 1
                    continue
            try:
                proy = motor.proyeccion_anual(df_historia, hosp, anio)
            except Exception as e:  # noqa: BLE001
                logger.exception("Fallo proyección %s/%s: %s", hosp, anio, e)
                continue
            if proy is None:
                continue
            repository.upsert_proyeccion_anual(
                hospital=hosp,
                anio=anio,
                semanas=proy["semanas"],
                curva_ia=proy["curva_ia"],
                curva_real=proy["curva_real"],
                total_ia=sum(proy["curva_ia"]),
            )
            ok_macro += 1
        logger.info("OK macro: %s", hosp)

    logger.info(
        "Batch terminado: %d predicciones semanales (%d semanas procesadas, "
        "%d omitidas por ya existir), %d proyecciones anuales "
        "(%d años cerrados omitidos por ya existir).",
        ok, n_semanas, omitidos_sem, ok_macro, omitidos,
    )


if __name__ == "__main__":
    main()
