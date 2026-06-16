"""Catálogo de dominio: hospitales, targets y traducciones.

Estas constantes se extraen tal cual del PoC (`poc/api_motor (poc).py` y
`poc/app (poc).py`) para mantener consistencia entre el motor, la API y el
dashboard.
"""

# --- Ruteo inteligente de targets (idéntico al PoC) ---
TARGETS_NOLAGS = [
    "Cause_Bronchial_Obstructive_Crisis",
    "Cause_COVID-19_(Confirmed)",
    "Cause_COVID-19_(Suspected)",
    "Num5a14Anios",
    "Num15a64Anios",
    "Num65oMas",
]

TARGETS_LAGS = [
    "Cause_Pneumonia",
    "Cause_Upper_Respiratory_Infection",
    "Cause_Acute_Bronchitis/Bronchiolitis",
    "Cause_Influenza",
    "Cause_Other_Respiratory_Causes",
    "NumMenor1Anio",
    "Num1a4Anios",
]

TODOS_TARGETS = TARGETS_NOLAGS + TARGETS_LAGS

# --- Centros de salud de Temuco / Padre Las Casas (idéntico al PoC) ---
HOSPITALES = [
    "Complejo Asistencial Padre las Casas",
    "Hospital Dr. Hernán Henríquez Aravena (Temuco)",
    "Hospital Makewe",
    "SAPU Amanecer",
    "SAPU Padre Las Casas",
    "SAPU Pueblo Nuevo",
    "SAPU Santa Rosa",
    "SAPU Villa Alegre",
    "SAR Conun Huenu",
    "SAR Labranza",
    "SAR Miraflores",
    "SAR Pedro de Valdivia",
]

# --- Traducciones para el dashboard (idéntico al PoC) ---
TRADUCCION_CAUSAS = {
    "Bronchial_Obstructive_Crisis": "Crisis Obstructiva Bronquial",
    "Pneumonia": "Neumonía",
    "Upper_Respiratory_Infection": "Infección Respiratoria Alta (IRA)",
    "Acute_Bronchitis_Bronchiolitis": "Bronquitis / Bronquiolitis Aguda",
    "Acute_Bronchitis/Bronchiolitis": "Bronquitis / Bronquiolitis Aguda",
    "Influenza": "Influenza",
    "COVID-19_(Confirmed)": "COVID-19 (Confirmado)",
    "COVID-19_(Suspected)": "COVID-19 (Sospecha)",
    "Other_Respiratory_Causes": "Otras Causas Respiratorias",
}

TRADUCCION_EDADES = {
    "Menor1Anio": "< 1 Año",
    "1a4Anios": "1 a 4 Años",
    "5a14Anios": "5 a 14 Años",
    "15a64Anios": "15 a 64 Años",
    "65oMas": "65 y Más Años",
}
