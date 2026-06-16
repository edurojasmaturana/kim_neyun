# Datos históricos (DEIS)

Coloca aquí la base epidemiológica consolidada que usa el PoC:

```
data/API_Epidemiologia_Temuco_Padre_Las_Casas.csv
```

Columnas esperadas (según `poc/api_motor (poc).py`): `EstablecimientoGlosa`,
`Anio`, `SemanaEstadistica` y una columna por cada target (`Cause_*`, `Num*`).

- En **local** el job lo lee desde aquí (montado en el contenedor).
- En **AWS** súbelo a S3 y define `HISTORIA_S3_URI=s3://<bucket>/data/API_Epidemiologia_Temuco_Padre_Las_Casas.csv`.
