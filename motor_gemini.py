"""
Motor lógico de Natasha.

Usa Gemini (paquete oficial 'google-genai') como cerebro principal con
function calling automático para decidir qué habilidad o acción ejecutar.
Si no hay GEMINI_API_KEY configurada, o falta el SDK, cae a un enrutador
local por patrones (modo offline) para que Natasha nunca deje de
responder a las órdenes básicas de escritorio.
"""
import os
import re

from configuracion import cargar_configuracion
from acciones import (
    abrir, cerrar_aplicacion, crear_carpeta_escritorio,
    guardar_nota_boveda, buscar_en_boveda, ejecutar_habilidad,
)
from skills_loader import listar_habilidades, leer_habilidad

cargar_configuracion()

# El nombre de modelo puede cambiar con el tiempo: revisa
# https://ai.google.dev/gemini-api/docs/models y ajusta vía variable
# de entorno si hace falta, sin tocar el código.
GEMINI_MODEL = os.environ.get("NATASHA_GEMINI_MODEL", "gemini-flash-lite-latest")

MODELOS_CANDIDATOS = [
    GEMINI_MODEL,
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
]

try:
    from google import genai
    from google.genai import types
    GEMINI_SDK_DISPONIBLE = True
except Exception:
    GEMINI_SDK_DISPONIBLE = False


class MotorNatasha:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.cliente = None
        self.historial = []  # [{"role": "user"/"model", "parts": [{"text": ...}]}]
        self.modo_gemini = False
        self.motivo_error_auth = None

        if GEMINI_SDK_DISPONIBLE:
            # 1. Comprobar si se especificó un archivo JSON de cuenta de servicio (Service Account)
            ruta_sa = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
            if not ruta_sa and self.api_key.endswith(".json") and os.path.exists(self.api_key):
                ruta_sa = self.api_key
            
            if ruta_sa and os.path.exists(ruta_sa):
                try:
                    from google.oauth2 import service_account
                    creds = service_account.Credentials.from_service_account_file(
                        ruta_sa,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                    proyecto = creds.project_id or os.environ.get("NATASHA_VERTEX_PROJECT")
                    ubicacion = os.environ.get("NATASHA_VERTEX_LOCATION", "us-central1")
                    self.cliente = genai.Client(
                        vertexai=True,
                        project=proyecto,
                        location=ubicacion,
                        credentials=creds
                    )
                    self.modo_gemini = True
                except Exception as e:
                    self.motivo_error_auth = f"Error al cargar archivo de credenciales Service Account ({e})"
            
            # 2. Comprobar si se introdujo un correo de cuenta de servicio en lugar de una API Key
            elif "@" in self.api_key and "gserviceaccount.com" in self.api_key:
                self.motivo_error_auth = (
                    "El valor en GEMINI_API_KEY es un correo de cuenta de servicio "
                    f"({self.api_key}). Un correo no es una clave secreta. "
                    "Para usar esta cuenta de servicio, descarga su archivo JSON de clave y pon la ruta "
                    "del archivo .json en GEMINI_API_KEY, o copia la clave API alfanumérica desde Google AI Studio."
                )

            # 3. Comprobar clave API alfanumérica directa
            elif bool(self.api_key) and "pega_aqui" not in self.api_key.lower():
                try:
                    self.cliente = genai.Client(api_key=self.api_key)
                    self.modo_gemini = True
                except Exception as e:
                    self.motivo_error_auth = f"Error al iniciar cliente Gemini con API Key ({e})"

        self.herramientas = [
            abrir, cerrar_aplicacion, crear_carpeta_escritorio,
            guardar_nota_boveda, buscar_en_boveda, ejecutar_habilidad,
        ]

    def _system_instruction(self):
        habilidades = listar_habilidades()
        lista_habilidades = "\n".join(
            f"- {h['nombre']}: {h['descripcion']}" for h in habilidades
        ) or "(no hay habilidades cargadas en /skills)"
        return (
            "Eres Natasha, un asistente de escritorio local estilo JARVIS que "
            "habla español. Eres directa, breve, y ejecutas acciones reales "
            "sobre el equipo del usuario usando las funciones disponibles: "
            "abrir apps/sitios, cerrar apps, crear carpetas, guardar notas en "
            "la bóveda de conocimiento, buscar en la bóveda, y ejecutar "
            "habilidades.\n\n"
            f"Habilidades disponibles (usa ejecutar_habilidad con el nombre exacto):\n{lista_habilidades}\n\n"
            "Si el usuario solo quiere conversar, responde en 1-2 frases, sin "
            "tecnicismos. Si pide una acción, ejecútala con la función "
            "correspondiente y confirma el resultado de forma breve, apta "
            "para ser leída en voz alta."
        )

    def consultar(self, texto_usuario: str) -> str:
        """Punto de entrada principal: decide y ejecuta usando Gemini, o el
        enrutador local si Gemini no está disponible."""
        if self.modo_gemini:
            return self._consultar_gemini(texto_usuario)
        return self._consultar_offline(texto_usuario)

    def generar_libre(self, prompt_sistema: str, contexto: str = "") -> str:
        """Generación de texto sin function calling, usada por las habilidades
        (ejecutar_habilidad) para producir el contenido final."""
        if not self.modo_gemini:
            return (
                "[Modo local sin Gemini] No puedo redactar contenido elaborado "
                "sin una API key de Gemini. Configura GEMINI_API_KEY para usar "
                "esta habilidad por completo.\n\n"
                f"Prompt de la habilidad:\n{prompt_sistema}\n\n"
                f"Contexto disponible:\n{contexto[:500]}"
            )
        try:
            entrada = prompt_sistema
            if contexto.strip():
                entrada += "\n\n---\nContexto relevante:\n" + contexto
            respuesta = self.cliente.models.generate_content(
                model=GEMINI_MODEL,
                contents=entrada,
            )
            return (respuesta.text or "").strip() or "Sin resultado."
        except Exception as e:
            return f"No pude ejecutar la habilidad con Gemini: {e}"

    # ------------------------------------------------------------------
    def _consultar_gemini(self, texto_usuario: str) -> str:
        self.historial.append({"role": "user", "parts": [{"text": texto_usuario}]})
        try:
            respuesta = self.cliente.models.generate_content(
                model=GEMINI_MODEL,
                contents=self.historial,
                config=types.GenerateContentConfig(
                    tools=self.herramientas,
                    system_instruction=self._system_instruction(),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        maximum_remote_calls=4
                    ),
                ),
            )
            texto = (respuesta.text or "").strip() or "Listo."
            self.historial.append({"role": "model", "parts": [{"text": texto}]})
            if len(self.historial) > 40:
                self.historial = self.historial[-40:]
            return texto
        except Exception as e:
            err_str = str(e)
            if "API_KEY_INVALID" in err_str or "API key not valid" in err_str:
                respuesta_local = self._consultar_offline(texto_usuario)
                if not respuesta_local.startswith("No tengo GEMINI_API_KEY"):
                    return f"[Aviso: Clave API inválida, ejecutando en modo local] {respuesta_local}"
                return ("La clave API de Gemini no es válida. Asegúrate de obtenerla en "
                        "https://aistudio.google.com/apikey (debe empezar por 'AIzaSy...') "
                        "y colocarla en tu archivo .env.")
            return f"Tuve un problema hablando con Gemini ({e}). Revisa tu API key o intenta de nuevo."

    # --- Enrutador local: cubre las acciones de escritorio sin Gemini ---
    def _consultar_offline(self, texto_usuario: str) -> str:
        texto = texto_usuario.lower().strip()
        texto = re.sub(r"^(oye\s+|hey\s+)?natasha[,\s]*", "", texto).strip()

        m = re.search(
            r"(?:crea|crear|haz|hacer)\s+(?:una\s+)?carpeta\s+"
            r"(?:llamada\s+|con\s+el\s+nombre\s+|de\s+nombre\s+|nombrada\s+)?"
            r"[\"']?([a-záéíóúñ0-9_\-\s]+?)[\"']?\s*(?:en\s+el\s+escritorio|en\s+escritorio)?$",
            texto
        )
        if m and m.group(1).strip():
            return crear_carpeta_escritorio(m.group(1).strip())

        m = re.search(r"^cierra(?:r)?\s+(?:el\s+|la\s+|los\s+|las\s+)?(.+)$", texto)
        if m and m.group(1).strip():
            return cerrar_aplicacion(m.group(1).strip())

        m = re.search(r"^abr(?:e|ir)\s+(?:el\s+|la\s+|los\s+|las\s+)?(.+)$", texto)
        if m and m.group(1).strip():
            objetivo = re.sub(r"\s+(en el navegador|por favor)$", "", m.group(1).strip())
            return abrir(objetivo)

        m = re.search(r"^(ejecuta|corre|realiza)\s+(?:la\s+habilidad\s+)?(.+)$", texto)
        if m and m.group(2).strip():
            return ejecutar_habilidad(m.group(2).strip())

        # Si el mensaje completo coincide con el nombre de una habilidad
        # (ej. "plan de hoy", "escanear tendencias"), la ejecuta directo,
        # sin necesitar el verbo "ejecuta" — más natural para voz.
        if leer_habilidad(texto):
            return ejecutar_habilidad(texto)

        m = re.search(r"^(?:guardar?|anota|agrega(?:r)?)\s+(?:una\s+)?nota\s+(?:en\s+la\s+b[oó]veda\s+)?(?:que\s+diga|titulada|sobre|con)?\s*(.+)$", texto)
        if m and m.group(1).strip():
            contenido = m.group(1).strip()
            return guardar_nota_boveda("raw", f"Nota {contenido[:20]}", contenido)

        m = re.search(r"^(?:buscar?|encuentra|consulta)\s+(?:en\s+la\s+b[oó]veda\s+|en\s+notas\s+)?(.+)$", texto)
        if m and m.group(1).strip():
            return buscar_en_boveda(m.group(1).strip())

        if any(t in texto for t in ["habilidades", "que puedes hacer", "que sabes hacer", "listar habilidades"]):
            habs = listar_habilidades()
            if not habs:
                return "No tengo habilidades registradas en la carpeta /skills."
            nombres = ", ".join(h['nombre'] for h in habs)
            return f"Mis habilidades disponibles son: {nombres}."

        if any(t in texto for t in ["hola", "buenos dias", "buenas tardes", "que tal"]):
            if self.motivo_error_auth:
                return f"Hola, soy Natasha. Estoy en modo local ({self.motivo_error_auth})."
            return "Hola, soy Natasha. Estoy en modo local porque no hay una API key de Gemini configurada."
        if any(t in texto for t in ["quien eres"]):
            if self.motivo_error_auth:
                return f"Soy Natasha, en modo local debido a: {self.motivo_error_auth}."
            return ("Soy Natasha, corriendo en modo local sin Gemini. Configura GEMINI_API_KEY "
                    "para desbloquear conversación completa y habilidades avanzadas.")

        if self.motivo_error_auth:
            return (f"Estoy en modo local ({self.motivo_error_auth}). "
                    "Puedo ejecutar órdenes directas: abrir o cerrar apps/sitios, crear carpetas, o consultar la bóveda.")

        return ("No tengo GEMINI_API_KEY configurada, así que solo entiendo órdenes directas: "
                "abrir algo, cerrar algo, crear una carpeta, guardar o buscar notas, o ejecutar una habilidad.")
