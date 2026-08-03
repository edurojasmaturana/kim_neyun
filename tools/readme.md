# Kim_neyun — `tools/` (Pipeline anual HZF Hybrid + Lags)


---

## Estructura del proyecto

La estructura esperada al descomprimir el ZIP y empezar a trabajar es:

```
tu-proyecto/                  ← raíz (aquí corres `python -m tools ...`)
├── tools/                     ← el paquete Python (lo que viene en el ZIP)
│   ├── SINCA_DOWNLOAD.md      # ⚠️ instrucciones para bajar los 7 CSVs SINCA a mano
│   ├── config.yaml            # configuración operacional (todas las knobs)
│   ├── requirements.txt       # dependencias Python
│   ├── LICENSE_DATA.md        # estado de licenciamiento de cada fuente
│   ├── README.md              # este archivo
│   ├── __init__.py            # expone la API pública del paquete
│   ├── __main__.py            # permite `python -m tools <command>`
│   ├── deis.py                # Módulo 1: descarga + limpieza DEIS (salud)
│   ├── sinca.py               # Módulo 2a: SINCA en modo local_csv (7 CSVs manuales)
│   ├── open_meteo.py          # Módulo 2b: fallback Open-Meteo (opcional)
│   ├── features.py            # Módulo 3: merge + lags (réplica 1:1 notebook)
│   ├── hzf_trainer.py         # Módulo 4: Chronos + Scaler + PCA + ML competition
│   ├── champion_challenger.py # Módulo 5: drift policy + reporte Markdown
│   └── cli.py                 # CLI dispatcher (lo llama __main__.py)
│
├── data/raw/                  ← ⚠️ NO viene en el ZIP, se crea al correr
│   ├── sinca/                 #    Aquí depositas los 7 CSVs SINCA a mano
│   │   ├── Monoxido.csv
│   │   ├── PM25.csv            # (alias de PM2.5.csv)
│   │   ├── PM10.csv
│   │   ├── Temperatura.csv
│   │   ├── Vel.csv
│   │   ├── presion.csv
│   │   └── precipitaciones.csv
│   └── at_urg_respiratorio_semanal.parquet  # DEIS (se baja solo o con wget -c)
│
└── Estudio_Temuco_Padre_Las_Casas/    # se crea solo al correr (salidas)
    ├── Backend_Data/                  # CSVs intermedios (df_backend, df_ml, ...)
    ├── Modelos_Lags/                  # 39 .pkl entrenados
    ├── Resultados_Paper_Lags/         # PNGs + reporte drift
    └── Resultados_Paper_NoLags/       # sensitivity (opcional)
```


---

## Instalación

```bash
# 1. Clonar repo
git clone <repo-url>
cd <repo>/tools

# 2. Crear venv y activar
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. (Opcional) Instalar Chronos desde el repo oficial
pip install git+https://github.com/amazon-science/chronos-forecasting.git
```

---

## Uso

### Pipeline completo (una vez al año)

```bash
# 0. PRE-REQUISITO: descargar manualmente los 7 CSVs SINCA en data/raw/sinca/
#    Ver tools/SINCA_DOWNLOAD.md para instrucciones paso a paso.
#    (El endpoint apub.tsca de SINCA está caído desde 2026-07.)
#
#    Además, baja el parquet DEIS (67 MB) — puede hacerlo el script solo,
#    pero si tu conexión es inestable, usa wget -c:
#    wget -c -O data/raw/at_urg_respiratorio_semanal.parquet "<url en config.yaml>"

# 1. Descargar/procesar DEIS (salud) — ~30 s
python -m tools deis-fetch --config tools/config.yaml

# 2. Procesar SINCA (ambiente) — lee CSVs locales en data/raw/sinca/
python -m tools sinca-fetch --config tools/config.yaml

# 3. Construir features (merge + lags, réplica 1:1 del notebook)
python -m tools build-features --config tools/config.yaml

# 4. Entrenar HZF Hybrid (13 targets × Lags) — 1-3 horas la primera vez
python -m tools train --config tools/config.yaml --variant lags

# 5. Champion-challenger (comparar contra modelos existentes en Modelos_Lags/)
python -m tools retrain --config tools/config.yaml --policy drift_only
```

