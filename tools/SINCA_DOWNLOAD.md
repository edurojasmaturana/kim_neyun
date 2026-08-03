# Datos ambientales SINCA — descarga manual

> **Por qué hay que descargar a mano**: el endpoint `apub.tsca` de SINCA está
> caído desde julio de 2026 (HTTP 404). El CGI actual solo renderiza GIFs
> server-side, no entrega CSV programáticamente. Por eso `tools/sinca.py`
> trabaja en modo `local_csv`: el usuario descarga los 7 CSVs a mano desde la
> ficha de la estación y los deja en este directorio. Es además el modo más
> fiel al notebook original, que también usaba CSVs locales en Drive.

---

## Estación

**Las Encinas — Temuco** — `station_id = 186`

Ficha oficial:
<https://sinca.mma.gob.cl/index.php/estacion/index/id/186>

---

## Parámetros a descargar (7 archivos)

| # | Parámetro SINCA | Código interno | Nombre de archivo esperado | Agregación |
|---|---|---|---|---|
| 1 | Monóxido de Carbono (CO)        | `CO`     | `Monoxido.csv`         | mean + max |
| 2 | Material Particulado fino 2.5   | `PM2.5`  | `PM25.csv`             | mean + max |
| 3 | Material Particulado 10         | `PM10`   | `PM10.csv`             | mean + max |
| 4 | Temperatura                     | `TEMP`   | `Temperatura.csv`      | mean + max (corrección sensor > 60 → /100) |
| 5 | Velocidad del Viento            | `WSPEED` | `Vel.csv`              | mean + max |
| 6 | Presión                         | `PRESS`  | `presion.csv`          | mean + max |
| 7 | Precipitación                   | `PP`     | `precipitaciones.csv`  | **sum**    |

**Nota sobre el nombre**: el `sinca.py` es tolerante a mayúsculas
(`Monoxido.csv` o `Monoxido.CSV`) y, para PM25, también acepta el histórico
`PM2.5.csv`. En lo posible, sin embargo, usar los nombres de la columna
"Nombre de archivo esperado".

---

## Pasos de descarga (por cada parámetro)

1. Abrir la ficha de la estación:
   <https://sinca.mma.gob.cl/index.php/estacion/index/id/186>

2. En la tabla de parámetros, hacer clic en el ícono de descarga (CSV) del
   parámetro correspondiente. Se abre la página de descarga con un selector
   de rango de fechas.

3. Configurar el rango:
   - **Desde**: `01-01-2021`
   - **Hasta**: `31-12-2025`
   - **Tipo de registros**: validar la opción "Todos" (incluye Registros
     validados, preliminares y no validados — el `sinca.py` prioriza los
     validados vía `bfill(axis=1)`).

4. Descargar. El archivo vendrá con un nombre tipo
   `datos_186_CO_01-01-2021_31-12-2025.csv` (varía según SINCA).

5. Renombrar al nombre esperado (columna 4 de la tabla de arriba) y moverlo
   a este directorio (`data/raw/sinca/`).

6. Repetir para los 7 parámetros.

---

## Verificación rápida

Después de descargar los 7 archivos, ejecutar:

```bash
python -m tools sinca-fetch --config config.yaml
```

Salida esperada (en logs):

```
SINCA: modo=local_csv, local_dir=data/raw/sinca, station_id=186
SINCA: leyendo CSV local data/raw/sinca/Monoxido.csv
SINCA: Monoxido procesado. NNN semanas, cols=['Anio', 'SemanaEstadistica', 'Monoxido_Avg', 'Monoxido_Max']
SINCA: leyendo CSV local data/raw/sinca/PM25.csv
...
SINCA: df_env_final shape=(NNN, 14), cols=[...]
```

Si algún CSV falta, el log lo reportará:

```
SINCA: no se encontró CSV local para 'Monoxido' en data/raw/sinca (buscado: ['Monoxido.csv', 'Monoxido.CSV'])
```

---

## Formato esperado del CSV

El `sinca.py` replica el parser del notebook (celda 46). Acepta dos variantes
de columnas:

### Contaminantes (CO, PM2.5, PM10)

```
FECHA (YYMMDD), HORA, Registros validados, Registros preliminares, Registros no validados
```

- `FECHA` se parsea con `format='%y%m%d'` (ej. `210105` → 2021-01-05).
- Se prioriza `Registros validados > preliminares > no validados` vía
  `df[valid_cols].bfill(axis=1).iloc[:, 0]`.
- Los valores pueden venir como string con coma decimal y puntos de miles
  (ej. `"12.345,67"`). `limpiar_valor()` lo maneja.

### Meteorológicas (TEMP, WSPEED, PRESS, PP)

```
FECHA (YYMMDD), HORA, valor
```

- La columna de valor es la primera cuyo nombre no contiene `FECHA`, `HORA`
  ni `fecha_dt`.
- Para Temperatura: si `valor > 60`, se divide por 100 (corrección de sensor
  en grados decicelsius → grados Celsius).

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| `no se encontró CSV local` | Falta un archivo o el nombre no coincide | Renombrar según la tabla de arriba |
| `valor` todo NaN | El CSV vino con otro separador o encoding | Abrir en editor de texto y verificar; si es `;`, re-guardar como `,` |
| `fecha_dt` todo NaT | El formato de fecha no es YYMMDD | Revisar la columna `FECHA` del CSV — SINCA a veces entrega `DD/MM/YYYY`; en tal caso, editar el CSV para que quede como YYMMDD o ajustar `procesar_sinca_df` en `sinca.py` |
| Fechas fuera de rango | El rango elegido en la web no fue 2021-2025 | Re-descargar con el rango correcto |

---

## Modo alternativo (API, actualmente caído)

Si en el futuro SINCA reactiva el endpoint `apub.tsca`, se puede cambiar el
modo en `config.yaml`:

```yaml
sinca:
  mode: api
```

En ese modo, `sinca.py` intenta primero el endpoint HTTPS y, si falla,
recurre a los CSVs locales de este directorio. Hoy (2026-07) el endpoint
sigue caído, así que el modo por defecto es `local_csv`.
