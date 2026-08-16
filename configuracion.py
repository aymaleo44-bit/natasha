"""
Utilidades de configuración para Natasha.

Carga variables desde un archivo .env en la raíz del proyecto sin depender
de librerías externas. Las variables ya presentes en el entorno no se
sobrescriben.
"""
import os


_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")


def ruta_proyecto(*partes: str) -> str:
    """Construye rutas absolutas dentro de la raíz del proyecto."""
    return os.path.join(_BASE_DIR, *partes)


def cargar_configuracion(sobrescribir: bool = True) -> bool:
    """Carga variables desde .env si existe.

    Formato soportado:
      CLAVE=valor
      CLAVE="valor con espacios"
      # comentario
    """
    if not os.path.exists(_ENV_PATH):
        return False

    cargado = False
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            clave = clave.strip()
            valor = valor.strip()
            if not clave:
                continue
            if ((valor.startswith('"') and valor.endswith('"')) or
                    (valor.startswith("'") and valor.endswith("'"))):
                valor = valor[1:-1]
            if sobrescribir or (clave not in os.environ or not os.environ[clave]):
                os.environ[clave] = valor
                cargado = True
    return cargado
