"""
Memoria de Natasha: una bóveda local de archivos Markdown, compatible
con Obsidian (texto plano, enlazable, sin base de datos).

Estructura:
  boveda/raw/      -> capturas e insumos sin procesar
  boveda/wiki/      -> conocimiento depurado y notas vinculadas
  boveda/outputs/   -> tareas y reportes generados por Natasha
"""
import os
import re
import glob
from datetime import datetime

RAIZ_BOVEDA = os.environ.get(
    "NATASHA_BOVEDA",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "boveda")
)
CARPETAS = ["raw", "wiki", "outputs"]


def asegurar_estructura():
    for carpeta in CARPETAS:
        os.makedirs(os.path.join(RAIZ_BOVEDA, carpeta), exist_ok=True)


def _slug(texto):
    texto = texto.strip().lower()
    texto = re.sub(r"[^a-z0-9áéíóúñ\s_-]", "", texto)
    texto = re.sub(r"\s+", "-", texto)
    return texto[:60] or "nota"


def guardar_nota(subcarpeta, titulo, contenido):
    """Guarda una nota Markdown con frontmatter en la bóveda y devuelve su ruta."""
    if subcarpeta not in CARPETAS:
        subcarpeta = "outputs"
    asegurar_estructura()
    fecha = datetime.now().strftime("%Y-%m-%d")
    nombre_archivo = f"{fecha}-{_slug(titulo)}.md"
    ruta = os.path.join(RAIZ_BOVEDA, subcarpeta, nombre_archivo)
    frontmatter = f"---\ntitulo: {titulo}\nfecha: {fecha}\norigen: natasha\n---\n\n"
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(frontmatter + contenido.strip() + "\n")
    return ruta


def buscar(consulta, max_resultados=5):
    """Búsqueda simple por palabras clave en toda la bóveda (RAG local ligero)."""
    asegurar_estructura()
    tokens = [t for t in re.findall(r"[a-záéíóúñ0-9]+", consulta.lower()) if len(t) > 2]
    if not tokens:
        return []
    resultados = []
    for ruta in glob.glob(os.path.join(RAIZ_BOVEDA, "**", "*.md"), recursive=True):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                texto = f.read()
        except Exception:
            continue
        texto_lower = texto.lower()
        puntaje = sum(texto_lower.count(t) for t in tokens)
        if puntaje > 0:
            fragmento = texto.strip().replace("\n", " ")[:220]
            resultados.append((puntaje, ruta, fragmento))
    resultados.sort(key=lambda r: r[0], reverse=True)
    return resultados[:max_resultados]


def leer_nota(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return f.read()


def notas_recientes(subcarpeta="outputs", limite=5):
    asegurar_estructura()
    carpeta = os.path.join(RAIZ_BOVEDA, subcarpeta)
    archivos = sorted(glob.glob(os.path.join(carpeta, "*.md")), key=os.path.getmtime, reverse=True)
    return archivos[:limite]
