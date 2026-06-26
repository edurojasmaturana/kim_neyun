# KIM-NEYÜN — Frontend (Streamlit)

Aplicación de página única que consume la API real (`/auth/login`,
`/hospitales`, `/predecir`) vía JWT. No duplica el catálogo de hospitales
ni las traducciones de causas/edades: los importa desde
`app/shared/catalog.py`.

## Estructura

```
app/frontend/
├── app.py                          ← entry point: redirige a login o a la página principal
├── config.py                        ← URLs, tema visual, importa shared.catalog
├── utils.py                          ← sesión, semana epidemiológica, traducciones, fecha máxima
├── components/
│   ├── api_client.py                   ← cliente HTTP con reintentos (cold-start Aurora)
│   └── charts.py                         ← configuración de Plotly
├── pages/
│   ├── login.py                            ← autenticación OAuth2
│   └── 1_Estimacion_Demanda.py               ← página principal: Tab Urgencias + Tab Manual de usuario
└── assets/
    └── logo.png                                ← logo UC Temuco
```

> **Nota histórica:** este frontend tuvo originalmente un Dashboard general
> (`1_Dashboard.py`) y un Panel Clínico (`2_Panel_Clinico.py`) como páginas
> separadas. Por decisión de Eduardo Rojas, el Dashboard general se eliminó
> y todo se consolidó en una única página, renombrada de "Panel Clínico" a
> "Estimación de Demanda de Urgencias". La palabra "táctico" se retiró de
> botones y mensajes (quedaba redundante al ser ya la única vista).

## Correr localmente

### Con el backend en AWS (sin Docker)

El frontend necesita la variable de entorno `API_BASE_URL` apuntando a la
API real. Si no se define, usa `http://localhost:8000` como fallback
(pensado para cuando el backend corre localmente con `make up`, ver
README raíz del repo).

**PowerShell:**
```powershell
$env:API_BASE_URL = "https://ahhkkmhuuk.execute-api.us-east-1.amazonaws.com"
streamlit run app/frontend/app.py
```

**Para que persista entre sesiones de terminal** (no es necesario
repetirlo cada vez):
```powershell
[System.Environment]::SetEnvironmentVariable("API_BASE_URL", "https://ahhkkmhuuk.execute-api.us-east-1.amazonaws.com", "User")
```
(Cierra y abre una terminal nueva para que tome el cambio.)

**Git Bash / Linux / Mac:**
```bash
export API_BASE_URL="https://ahhkkmhuuk.execute-api.us-east-1.amazonaws.com"
streamlit run app/frontend/app.py
```

> La URL del API Gateway puede cambiar si el backend se redeploya desde
> cero (no solo con actualizaciones). Si el login da "No se pudo conectar",
> confirma la URL vigente en el Swagger del backend o con el equipo.

### Con el backend local (Docker — ver README raíz, `make up`)

No es necesario definir `API_BASE_URL`; el default (`http://localhost:8000`)
ya apunta al backend local levantado con `make up`.

```powershell
streamlit run app/frontend/app.py
```

## Variables de entorno disponibles

| Variable | Default | Descripción |
|----------|---------|-------------|
| `API_BASE_URL` | `http://localhost:8000` | URL base de la API |
| `KIM_API_TIMEOUT` | `15` | Timeout por request (segundos) |
| `KIM_API_RETRIES` | `3` | Reintentos ante cold-start de Aurora |
| `KIM_CACHE_TTL` | `300` | TTL de caché de Streamlit (segundos) |

## Notas de diseño

- **Página única**: tras autenticarse, el login redirige directo a
  `pages/1_Estimacion_Demanda.py`. No hay vista general/macro — el equipo
  decidió mantener solo la vista táctica semanal por establecimiento.
- **Semana epidemiológica**: se calcula con inicio en **domingo**
  (estándar CDC/MINSAL), no con `isocalendar()` de Python (que usa lunes).
  Ver `utils.get_semana_epi()`.
- **Fecha máxima seleccionable**: el batch de inferencia solo precomputa
  hacia atrás desde hoy, nunca el futuro. Por eso el selector de fecha usa
  `utils.fecha_maxima_consultable()` (= `date.today()`) como `max_value`.
- **Sesión expirada**: `utils.handle_api_error_and_maybe_logout()` detecta
  el error "Token expirado o inválido" devuelto por el cliente API, limpia
  `st.session_state` y redirige al login automáticamente.
- **Botón de logout**: disponible en la sidebar de la página principal,
  vía `utils.render_logout_button()`.
- **Vista de proyección anual** (52 semanas): el endpoint
  `fetch_proyeccion_anual()` existe en `api_client.py` pero no se usa en
  ninguna página — decisión consciente del equipo, no una omisión.
