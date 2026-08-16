"""
Control de sistema de Natasha.
Lista blanca de acciones seguras sobre Windows: abrir/cerrar apps y
sitios conocidos, crear carpetas. Nunca ejecuta texto arbitrario.
"""
import os
import re
import subprocess
import webbrowser
import platform


class NatashaSystemControl:

    SITIOS_WEB = {
        "google": "https://www.google.com",
        "youtube": "https://www.youtube.com",
        "gmail": "https://mail.google.com",
        "correo": "https://mail.google.com",
        "whatsapp": "https://web.whatsapp.com",
        "facebook": "https://www.facebook.com",
        "wikipedia": "https://www.wikipedia.org",
        "outlook": "https://outlook.com",
        "drive": "https://drive.google.com",
        "maps": "https://maps.google.com",
        "traductor": "https://translate.google.com",
        "github": "https://github.com",
        "chatgpt": "https://chatgpt.com",
        "claude": "https://claude.ai",
        "gemini": "https://gemini.google.com",
        "reddit": "https://www.reddit.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "netflix": "https://www.netflix.com",
        "notion": "https://www.notion.so",
        "spotify": "https://open.spotify.com",
    }

    # "proceso": None => Natasha nunca la cierra (procesos críticos del sistema)
    APLICACIONES = {
        "bloc de notas": {"comando": "notepad", "proceso": "notepad.exe"},
        "notas": {"comando": "notepad", "proceso": "notepad.exe"},
        "notepad": {"comando": "notepad", "proceso": "notepad.exe"},
        "calculadora": {"comando": "calc", "proceso": "CalculatorApp.exe"},
        "paint": {"comando": "mspaint", "proceso": "mspaint.exe"},
        "cmd": {"comando": "cmd", "proceso": "cmd.exe"},
        "terminal": {"comando": "cmd", "proceso": "cmd.exe"},
        "consola": {"comando": "cmd", "proceso": "cmd.exe"},
        "panel de control": {"comando": "control", "proceso": None},
        "word": {"comando": "winword", "proceso": "WINWORD.EXE"},
        "excel": {"comando": "excel", "proceso": "EXCEL.EXE"},
        "explorador": {"comando": "explorer", "proceso": None},
        "explorador de archivos": {"comando": "explorer", "proceso": None},
        "chrome": {"comando": "chrome", "proceso": "chrome.exe"},
        "edge": {"comando": "msedge", "proceso": "msedge.exe"},
        "spotify": {"comando": "spotify", "proceso": "Spotify.exe"},
        "code": {"comando": "code", "proceso": "Code.exe"},
        "vs code": {"comando": "code", "proceso": "Code.exe"},
        "visual studio code": {"comando": "code", "proceso": "Code.exe"},
        "brave": {"comando": "brave", "proceso": "brave.exe"},
        "firefox": {"comando": "firefox", "proceso": "firefox.exe"},
        "administrador de tareas": {"comando": "taskmgr", "proceso": "Taskmgr.exe"},
        "task manager": {"comando": "taskmgr", "proceso": "Taskmgr.exe"},
        "discord": {"comando": "discord", "proceso": "Discord.exe"},
        "telegram": {"comando": "telegram", "proceso": "Telegram.exe"},
        "steam": {"comando": "steam", "proceso": "steam.exe"},
    }

    def __init__(self):
        self.es_windows = platform.system() == "Windows"
        self.ruta_escritorio = self._detectar_escritorio()

    def _detectar_escritorio(self):
        userprofile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        candidatos = [
            os.path.join(userprofile, "OneDrive", "Desktop"),
            os.path.join(userprofile, "OneDrive", "Escritorio"),
            os.path.join(userprofile, "Desktop"),
            os.path.join(userprofile, "Escritorio"),
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.path.expanduser("~"), "Escritorio"),
        ]
        for ruta in candidatos:
            if os.path.isdir(ruta):
                return ruta
        return candidatos[2] if len(candidatos) > 2 else os.path.expanduser("~")

    # --- Apertura ---------------------------------------------------
    def abrir_sitio_web(self, nombre_o_url):
        objetivo = nombre_o_url.strip().lower()
        url = self.SITIOS_WEB.get(objetivo)
        if not url:
            if re.match(r"^[\w\-]+\.(com|org|net|es|io|dev|gob|edu)", objetivo):
                url = "https://" + objetivo
            else:
                consulta = nombre_o_url.strip().replace(" ", "+")
                url = f"https://www.google.com/search?q={consulta}"
        try:
            webbrowser.open(url)
            return True, f"Abriendo {objetivo if objetivo in self.SITIOS_WEB else url}."
        except Exception as e:
            return False, f"No pude abrir el navegador: {e}"

    def abrir_aplicacion(self, nombre_app):
        objetivo = nombre_app.strip().lower()
        entrada = self.APLICACIONES.get(objetivo)
        if not entrada:
            return False, f"No tengo registrada la app '{nombre_app}' en mi lista segura."
        if not self.es_windows:
            return False, "Abrir aplicaciones nativas solo está soportado en Windows."
        try:
            subprocess.Popen(entrada["comando"], shell=True)
            return True, f"Abriendo {nombre_app}."
        except Exception as e:
            return False, f"No pude abrir {nombre_app}: {e}"

    def resolver_apertura(self, objetivo):
        objetivo_normalizado = objetivo.strip().lower()
        if objetivo_normalizado in self.APLICACIONES:
            return self.abrir_aplicacion(objetivo_normalizado)
        return self.abrir_sitio_web(objetivo_normalizado)

    # --- Cierre -------------------------------------------------------
    def cerrar_aplicacion(self, nombre_app):
        objetivo = nombre_app.strip().lower()
        entrada = self.APLICACIONES.get(objetivo)
        if not entrada:
            return False, f"No tengo registrada la app '{nombre_app}' para poder cerrarla."
        proceso = entrada.get("proceso")
        if not proceso:
            return False, f"Por seguridad, no cierro '{nombre_app}' (es parte del sistema)."
        if not self.es_windows:
            return False, "Cerrar aplicaciones solo está soportado en Windows."
        try:
            resultado = subprocess.run(
                ["taskkill", "/IM", proceso, "/F"],
                capture_output=True, text=True, timeout=5
            )
            if resultado.returncode == 0:
                return True, f"{nombre_app} cerrado."
            return False, f"{nombre_app} no estaba abierto."
        except Exception as e:
            return False, f"No pude cerrar {nombre_app}: {e}"

    # --- Carpetas -------------------------------------------------------
    def crear_carpeta(self, nombre_carpeta):
        nombre_limpio = re.sub(r'[<>:"/\\|?*]', '', nombre_carpeta).strip()
        if not nombre_limpio:
            return False, "No entendí qué nombre debe llevar la carpeta."
        ruta_final = os.path.join(self.ruta_escritorio, nombre_limpio)
        try:
            if os.path.exists(ruta_final):
                return False, f"La carpeta '{nombre_limpio}' ya existe en el escritorio."
            os.makedirs(ruta_final)
            return True, f"Carpeta '{nombre_limpio}' creada en el escritorio."
        except Exception as e:
            return False, f"No pude crear la carpeta: {e}"
