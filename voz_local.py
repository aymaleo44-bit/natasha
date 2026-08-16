"""
Capa de voz de Natasha — 100% local.

Entrada (STT): faster-whisper corriendo en el equipo, activado al
mantener presionada una tecla (push-to-talk). El audio nunca sale de
la máquina ni pasa por ninguna API externa.

Salida (TTS): pyttsx3, motor de voz local del sistema operativo.

Sin latencias de red, sin costo por minuto de audio, sin telemetría.
"""
import os
import re
import threading

# Nota: se captura Exception (no solo ImportError) porque algunas de
# estas librerías fallan con OSError u otros errores cuando falta una
# dependencia nativa del sistema (ej. PortAudio para sounddevice), y
# Natasha debe seguir arrancando igual, solo sin voz.
try:
    import numpy as np
    NUMPY_DISPONIBLE = True
except Exception:
    NUMPY_DISPONIBLE = False

try:
    import sounddevice as sd
    SOUNDDEVICE_DISPONIBLE = True
except Exception:
    SOUNDDEVICE_DISPONIBLE = False

try:
    from faster_whisper import WhisperModel
    WHISPER_DISPONIBLE = True
except Exception:
    WHISPER_DISPONIBLE = False

try:
    import pyttsx3
    TTS_DISPONIBLE = True
except Exception:
    TTS_DISPONIBLE = False

SAMPLE_RATE = 16000

PROMPT_CONTEXTO_ES = (
    "Natasha, asistente de escritorio inteligente en español. "
    "Comandos comunes: abre, cierra, calculadora, bloc de notas, "
    "chrome, word, excel, crear carpeta en el escritorio, "
    "plan de hoy, escanear tendencias, resumen semanal, "
    "guardar nota, buscar en la bóveda, qué puedes hacer."
)


class VozLocal:
    def __init__(self, modelo_whisper=None, idioma="es"):
        self.idioma = idioma
        self._nombre_modelo = modelo_whisper or os.environ.get("NATASHA_WHISPER_MODEL", "small")
        self._modelo = None
        self._grabando = False
        self._buffer = []
        self._stream = None

        # Nivel de volumen (0.0-1.0) actualizado en vivo mientras se graba,
        # usado por el HUD para hacer "respirar" la esfera con la voz.
        self.nivel_actual = 0.0

        self.motor_tts = None
        if TTS_DISPONIBLE:
            try:
                self.motor_tts = pyttsx3.init()
                self.motor_tts.setProperty("rate", 175)
                # Seleccionar automáticamente la voz en español disponible
                voces = self.motor_tts.getProperty("voices") or []
                for v in voces:
                    nombre = (getattr(v, "name", "") or "").lower()
                    vid = (getattr(v, "id", "") or "").lower()
                    langs = [str(l).lower() for l in getattr(v, "languages", [])]
                    if (
                        any("es" in l for l in langs) or
                        "spanish" in nombre or
                        "helena" in nombre or
                        "sabina" in nombre or
                        "es-es" in vid or
                        "es_es" in vid or
                        "es-mx" in vid or
                        "es_mx" in vid
                    ):
                        self.motor_tts.setProperty("voice", v.id)
                        break
            except Exception:
                self.motor_tts = None

    def disponible(self):
        """True si el equipo puede grabar y transcribir localmente."""
        return SOUNDDEVICE_DISPONIBLE and WHISPER_DISPONIBLE and NUMPY_DISPONIBLE

    def _cargar_modelo(self):
        # Carga perezosa: el modelo Whisper solo se descarga/carga la
        # primera vez que se usa, para no ralentizar el arranque del HUD.
        if self._modelo is None and WHISPER_DISPONIBLE:
            self._modelo = WhisperModel(self._nombre_modelo, device="cpu", compute_type="int8")
        return self._modelo

    # --- Grabación mientras se mantiene presionada una tecla ---
    def iniciar_grabacion(self):
        if not self.disponible() or self._grabando:
            return
        self._buffer = []
        self._grabando = True
        self.nivel_actual = 0.0

        def _callback(indata, frames, time_info, status):
            if self._grabando:
                self._buffer.append(indata.copy())
                # RMS del bloque actual, normalizado a un rango 0-1 aproximado
                # para que el HUD pueda usarlo como "volumen" en tiempo real.
                rms = float(np.sqrt(np.mean(np.square(indata))))
                self.nivel_actual = min(1.0, rms * 9.0)

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=_callback
        )
        self._stream.start()

    def detener_grabacion_y_transcribir(self):
        if not self.disponible() or not self._grabando:
            return ""
        self._grabando = False
        self.nivel_actual = 0.0
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if not self._buffer:
            return ""
        audio = np.concatenate(self._buffer, axis=0).flatten()
        self._buffer = []

        # Ignorar grabaciones accidentales de menos de 0.2 segundos
        if len(audio) < SAMPLE_RATE * 0.2:
            return ""

        # Normalización de amplitud para máxima claridad en la transcripción
        max_val = np.max(np.abs(audio))
        if max_val > 0.01:
            audio = (audio / max_val) * 0.9

        modelo = self._cargar_modelo()
        if modelo is None:
            return ""

        try:
            segmentos, _info = modelo.transcribe(
                audio,
                language=self.idioma,
                task="transcribe",
                beam_size=5,
                temperature=0.0,
                vad_filter=True,
                initial_prompt=PROMPT_CONTEXTO_ES,
                condition_on_previous_text=False,
            )
            texto = " ".join(s.text for s in segmentos).strip()
            # Limpiar caracteres parásitos al inicio o fin
            texto = re.sub(r"^[\s.,;¡!¿?]+|[\s.,;¡!¿?]+$", "", texto).strip()
            return texto
        except Exception as e:
            print(f"!! Error en transcripción: {e}")
            return ""

    # --- Texto a voz ---
    def hablar(self, texto):
        if not self.motor_tts or not texto:
            return

        def _run():
            try:
                self.motor_tts.say(texto)
                self.motor_tts.runAndWait()
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()
