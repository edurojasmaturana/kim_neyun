# Artefactos del modelo (no versionar binarios pesados)

Coloca aquí los pesos entrenados que produce tu pipeline de laboratorio, con la
misma convención de nombres que espera el motor (`inference/engine.py`):

```
models/
  Modelos_Lags/
    <algo>_Hybrid_Cause_Pneumonia.pkl
    Scaler_Cause_Pneumonia.pkl
    PCA_Cause_Pneumonia.pkl
    ... (un trío por cada target con lag)
  Modelos_NoLags/
    <algo>_Hybrid_Cause_Bronchial_Obstructive_Crisis.pkl
    Scaler_Cause_Bronchial_Obstructive_Crisis.pkl
    PCA_Cause_Bronchial_Obstructive_Crisis.pkl
    ... (un trío por cada target sin lag)
```

- En **local** el job los lee desde esta carpeta (montada en el contenedor).
- En **AWS** súbelos a S3 y define `MODELS_S3_URI=s3://<bucket>/models/`; el job
  los sincroniza al arrancar.
- Si falta el trío de un target, ese target opera en modo **Zero-Shot** (solo
  Chronos, sin corrección ambiental), igual que en el PoC.
