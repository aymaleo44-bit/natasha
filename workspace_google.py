"""
Integración opcional de Natasha con Google Calendar (usada por la
habilidad plan_hoy).

Para activarla:
  1. Crea un proyecto en https://console.cloud.google.com/ y habilita
     la API de Calendar.
  2. Genera credenciales OAuth de "Aplicación de escritorio" y descarga
     el archivo como 'credentials.json' junto a este script.
  3. La primera vez que se use, Natasha abrirá el navegador para que
     autorices el acceso; luego reutiliza 'token.pickle' automáticamente.

Si no configuras esto, plan_hoy simplemente avisa que Calendar no está
conectado y arma el plan solo con las notas de la bóveda.
"""
import os
import pickle
import datetime as dt

from configuracion import cargar_configuracion, ruta_proyecto

cargar_configuracion()

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

RUTA_CREDENCIALES = os.environ.get(
    "NATASHA_GOOGLE_CREDENTIALS",
    ruta_proyecto("credentials.json"),
)
RUTA_TOKEN = os.environ.get(
    "NATASHA_GOOGLE_TOKEN",
    ruta_proyecto("token.pickle"),
)

try:
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    WORKSPACE_SDK_DISPONIBLE = True
except Exception:
    WORKSPACE_SDK_DISPONIBLE = False


def _obtener_credenciales():
    if not WORKSPACE_SDK_DISPONIBLE or not os.path.exists(RUTA_CREDENCIALES):
        return None
    creds = None
    if os.path.exists(RUTA_TOKEN):
        with open(RUTA_TOKEN, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(RUTA_CREDENCIALES, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(RUTA_TOKEN, "wb") as f:
            pickle.dump(creds, f)
    return creds


def obtener_eventos_hoy():
    """Devuelve una lista de eventos de hoy ('hora — título') o None si no está conectado."""
    creds = _obtener_credenciales()
    if not creds:
        return None
    try:
        servicio = build("calendar", "v3", credentials=creds)
        ahora = dt.datetime.now(dt.timezone.utc)
        inicio = dt.datetime(ahora.year, ahora.month, ahora.day, tzinfo=dt.timezone.utc).isoformat()
        fin = (dt.datetime(ahora.year, ahora.month, ahora.day, tzinfo=dt.timezone.utc) + dt.timedelta(days=1)).isoformat()
        resultados = servicio.events().list(
            calendarId="primary", timeMin=inicio, timeMax=fin,
            singleEvents=True, orderBy="startTime"
        ).execute()
        eventos = resultados.get("items", [])
        return [
            f"{e.get('start', {}).get('dateTime', e.get('start', {}).get('date', '?'))} — {e.get('summary', '(sin título)')}"
            for e in eventos
        ]
    except Exception:
        return None
