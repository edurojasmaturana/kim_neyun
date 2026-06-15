import os
import torch
import joblib
import logging
import datetime
import glob
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from chronos import ChronosPipeline
import openmeteo_requests
import requests_cache
from retry_requests import retry
from epiweeks import Week  # LA NUEVA LIBRERÍA EPIDEMIOLÓGICA

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="KIM-NEYÜN - Motor Híbrido Respiratorio")

# --- DEFINICIÓN DE RUTEO INTELIGENTE ---
TARGETS_NOLAGS = [
    'Cause_Bronchial_Obstructive_Crisis',
    'Cause_COVID-19_(Confirmed)', 'Cause_COVID-19_(Suspected)',
    'Num5a14Anios', 'Num15a64Anios', 'Num65oMas'
]
TARGETS_LAGS = [
    'Cause_Pneumonia', 'Cause_Upper_Respiratory_Infection',
    'Cause_Acute_Bronchitis/Bronchiolitis', 'Cause_Influenza',
    'Cause_Other_Respiratory_Causes', 'NumMenor1Anio', 'Num1a4Anios'
]
TODOS_TARGETS = TARGETS_NOLAGS + TARGETS_LAGS

# --- CARGA DE RECURSOS ---
logger.info("Cargando Chronos T5...")
pipeline_chronos = ChronosPipeline.from_pretrained("amazon/chronos-t5-small", device_map="cpu", torch_dtype=torch.bfloat16)

logger.info("Cargando base epidemiológica histórica...")
df_historia = pd.read_csv("data/API_Epidemiologia_Temuco_Padre_Las_Casas.csv")

modelos_ml, scalers, pcas = {}, {}, {}

def cargar_artefactos(targets, carpeta):
    for t in targets:
        if t.startswith('Num') or t.startswith('Cause'):
            try:
                modelo_path = glob.glob(f'{carpeta}/*_Hybrid_{t}.pkl')[0]
                modelos_ml[t] = joblib.load(modelo_path)
                scalers[t] = joblib.load(f'{carpeta}/Scaler_{t}.pkl')
                pcas[t] = joblib.load(f'{carpeta}/PCA_{t}.pkl')
            except Exception as e:
                logger.warning(f"Artefactos faltantes para {t} en {carpeta}. Operará en modo Zero-Shot.")

logger.info("Cargando pesos de Machine Learning...")
cargar_artefactos(TARGETS_LAGS, "Modelos_Lags")
cargar_artefactos(TARGETS_NOLAGS, "Modelos_NoLags")

# --- FUNCIONES DE SEGURIDAD CLIMÁTICA ---
def safe_calc(arr, func):
    if len(arr) == 0: return 0.0
    if np.isnan(arr).all(): return 0.0
    val = func(arr)
    return float(val) if not np.isnan(val) else 0.0

def calcular_metricas_semanales(arr_horario, nombre_var):
    w0 = arr_horario[-168:]
    w1 = arr_horario[-336:-168]
    w2 = arr_horario[-504:-336]
    if nombre_var == 'precipitaciones':
        return {
            f"{nombre_var}_Total": safe_calc(w0, np.nansum),
            f"{nombre_var}_Total_Lag1": safe_calc(w1, np.nansum),
            f"{nombre_var}_Total_Lag2": safe_calc(w2, np.nansum),
        }
    else:
        return {
            f"{nombre_var}_Avg": safe_calc(w0, np.nanmean),
            f"{nombre_var}_Max": safe_calc(w0, np.nanmax),
            f"{nombre_var}_Avg_Lag1": safe_calc(w1, np.nanmean),
            f"{nombre_var}_Max_Lag1": safe_calc(w1, np.nanmax),
            f"{nombre_var}_Avg_Lag2": safe_calc(w2, np.nanmean),
            f"{nombre_var}_Max_Lag2": safe_calc(w2, np.nanmax),
        }

def extraer_clima_3_semanas(fecha_referencia):
    try:
        cache = requests_cache.CachedSession('.cache', expire_after=3600)
        openmeteo = openmeteo_requests.Client(session=retry(cache, retries=5))
        lat, lon = -38.7396, -72.5984
        fin = fecha_referencia.strftime('%Y-%m-%d')
        inicio = (fecha_referencia - datetime.timedelta(days=28)).strftime('%Y-%m-%d')
        weather_res = openmeteo.weather_api("https://api.open-meteo.com/v1/forecast", 
            params={"latitude": lat, "longitude": lon, "start_date": inicio, "end_date": fin,
                    "hourly": ["temperature_2m", "surface_pressure", "wind_speed_10m", "precipitation"],
                    "timezone": "America/Santiago"})[0]
        aq_res = openmeteo.weather_api("https://air-quality-api.open-meteo.com/v1/air-quality", 
            params={"latitude": lat, "longitude": lon, "start_date": inicio, "end_date": fin,
                    "hourly": ["pm10", "pm2_5", "carbon_monoxide"],
                    "timezone": "America/Santiago"})[0]
        
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
        
        features_esperadas = scalers[TARGETS_LAGS[0]].feature_names_in_ if hasattr(scalers[TARGETS_LAGS[0]], 'feature_names_in_') else []
        for f in features_esperadas:
            if f not in clima_dict: clima_dict[f] = 0.0
        return clima_dict
    except Exception as e:
        logger.error(f"Error extrayendo clima: {e}")
        return None

# --- MODELOS DE SOLICITUD ---
class SolicitudMicro(BaseModel):
    EstablecimientoGlosa: str
    fecha_referencia: str

class SolicitudMacro(BaseModel):
    EstablecimientoGlosa: str
    anio_proyeccion: int

# --- ENDPOINT 1: TÁCTICO (1 SEMANA HÍBRIDA) ---
@app.post("/predecir")
def predecir(solicitud: SolicitudMicro):
    try:
        hospital_input = solicitud.EstablecimientoGlosa
        fecha_ref = datetime.datetime.strptime(solicitud.fecha_referencia, '%Y-%m-%d').date()
        
        clima = extraer_clima_3_semanas(fecha_ref)
        if not clima: raise HTTPException(status_code=500, detail="Error de conexión con OpenMeteo.")
        
        df_env_completo = pd.DataFrame([clima]).fillna(0.0)
        df_hosp = df_historia[df_historia['EstablecimientoGlosa'] == hospital_input].sort_values(['Anio', 'SemanaEstadistica'])
        
        # --- SOLUCIÓN MINSAL: CÁLCULO ESTANDARIZADO DE SEMANA EPIDEMIOLÓGICA ---
        semana_epi = Week.fromdate(fecha_ref, system="cdc")
        year_ref = semana_epi.year
        week_ref = semana_epi.week
        
        df_hosp = df_hosp[(df_hosp['Anio'] < year_ref) | ((df_hosp['Anio'] == year_ref) & (df_hosp['SemanaEstadistica'] < week_ref))]
        
        if df_hosp.empty: 
            raise HTTPException(status_code=404, detail=f"Hospital '{hospital_input}' sin historial suficiente.")
        
        res = {"Causas": {}, "Edades": {}, "Total": 0}
        
        for t in TODOS_TARGETS:
            if t not in df_hosp.columns and f'Cause_{t}' not in df_hosp.columns: continue
            
            series = torch.tensor(df_hosp[t].values[-104:].astype(np.float32))
            forecast = pipeline_chronos.predict(series, 1, num_samples=50)
            pred_base = np.quantile(forecast[0].numpy(), 0.5, axis=0)[0]
            
            ajuste = 0
            if t in modelos_ml:
                try:
                    cols_requeridas = scalers[t].feature_names_in_
                    for col in cols_requeridas:
                        if col not in df_env_completo.columns: df_env_completo[col] = 0.0
                    df_env_filtrado = df_env_completo[cols_requeridas].fillna(0.0)
                    env_pca = pcas[t].transform(scalers[t].transform(df_env_filtrado))
                    ajuste = modelos_ml[t].predict(env_pca)[0]
                except Exception as e: 
                    pass
            
            val = max(0, int(round(pred_base + ajuste)))
            if t.startswith('Cause_'): res["Causas"][t.replace('Cause_', '')] = val
            elif t.startswith('Num'): res["Edades"][t.replace('Num', '')] = val

        # BOTTOM-UP FORECASTING
        total_causas = sum(res["Causas"].values())
        res["Total"] = total_causas
        suma_edades_cruda = sum(res["Edades"].values())
        
        if suma_edades_cruda > 0 and total_causas > 0:
            for edad_key, valor_crudo in res["Edades"].items():
                proporcion = valor_crudo / suma_edades_cruda
                res["Edades"][edad_key] = int(round(proporcion * total_causas))
            diferencia = total_causas - sum(res["Edades"].values())
            if diferencia != 0:
                clave_mayor = max(res["Edades"], key=res["Edades"].get)
                res["Edades"][clave_mayor] += diferencia

        return {
            "hospital": hospital_input, "semana_epi": week_ref, "año": year_ref,
            "estimaciones": res, "temperatura_referencia": clima.get("Temperatura_Avg", 0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- ENDPOINT 2: ESTRATÉGICO (52 SEMANAS MACRO) ---
@app.post("/proyeccion_anual")
def proyeccion_anual(solicitud: SolicitudMacro):
    try:
        hospital_input = solicitud.EstablecimientoGlosa
        anio_objetivo = solicitud.anio_proyeccion
        
        df_hosp = df_historia[df_historia['EstablecimientoGlosa'] == hospital_input].sort_values(['Anio', 'SemanaEstadistica'])
        df_contexto = df_hosp[df_hosp['Anio'] < anio_objetivo]
        if df_contexto.empty:
            raise HTTPException(status_code=404, detail="No hay datos históricos previos a este año.")
            
        df_real = df_hosp[df_hosp['Anio'] == anio_objetivo]
        causas_cols = [c for c in TODOS_TARGETS if c.startswith('Cause_')]
        predicciones_causas = []
        
        for t in causas_cols:
            if t not in df_contexto.columns: continue
            series = torch.tensor(df_contexto[t].values[-104:].astype(np.float32))
            forecast = pipeline_chronos.predict(series, 52, num_samples=20)
            pred_mediana = np.quantile(forecast[0].numpy(), 0.5, axis=0)
            predicciones_causas.append(np.maximum(0, pred_mediana))
            
        total_proyectado = np.sum(predicciones_causas, axis=0)
        curva_real = []
        semanas_totales = list(range(1, 53))
        
        if not df_real.empty:
            for sem in semanas_totales:
                row = df_real[df_real['SemanaEstadistica'] == sem]
                if not row.empty:
                    suma_real = int(row[[c for c in causas_cols if c in row.columns]].sum(axis=1).values[0])
                    curva_real.append(suma_real)
                else:
                    curva_real.append(None)
        else:
            curva_real = [None] * 52
            
        return {
            "hospital": hospital_input,
            "anio_proyectado": anio_objetivo,
            "semanas": semanas_totales,
            "curva_ia": [int(x) for x in total_proyectado],
            "curva_real": curva_real
        }
    except Exception as e:
        logger.error(f"Error Proyección Macro: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))