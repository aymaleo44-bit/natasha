"""
Cargador de habilidades de Natasha.
Cada habilidad es un archivo Markdown de un solo propósito en /skills,
con frontmatter (nombre, descripcion) y un prompt detallado en el cuerpo.
"""
import os
import re

RUTA_SKILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")


def listar_habilidades():
    habilidades = []
    if not os.path.isdir(RUTA_SKILLS):
        return habilidades
    for archivo in sorted(os.listdir(RUTA_SKILLS)):
        if not archivo.endswith(".md"):
            continue
        ruta = os.path.join(RUTA_SKILLS, archivo)
        nombre, descripcion = _leer_frontmatter(ruta)
        habilidades.append({
            "nombre": nombre or archivo[:-3],
            "descripcion": descripcion,
            "archivo": ruta,
        })
    return habilidades


def _leer_frontmatter(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        contenido = f.read()
    m = re.search(r"^---\s*\n(.*?)\n---\s*\n", contenido, re.DOTALL)
    nombre, descripcion = None, ""
    if m:
        bloque = m.group(1)
        mn = re.search(r"nombre:\s*(.+)", bloque)
        md = re.search(r"descripcion:\s*(.+)", bloque)
        if mn:
            nombre = mn.group(1).strip()
        if md:
            descripcion = md.group(1).strip()
    return nombre, descripcion


_RELLENO = {"de", "la", "el", "los", "las", "una", "un"}


def _normalizar(texto):
    """Unifica espacios y guiones para que 'escanear tendencias' y
    'escanear_tendencias' se reconozcan como la misma habilidad."""
    return re.sub(r"[\s_\-]+", " ", texto.strip().lower())


def _palabras_clave(texto):
    return {p for p in _normalizar(texto).split(" ") if p and p not in _RELLENO}


def leer_habilidad(nombre_habilidad):
    """Devuelve el contenido completo (prompt) de una habilidad, tolerando
    variaciones como 'plan de hoy' / 'plan_hoy' o 'resumen de bandeja' /
    'resumen_bandeja'."""
    objetivo = _normalizar(nombre_habilidad)
    palabras_objetivo = _palabras_clave(nombre_habilidad)
    if not palabras_objetivo:
        return None

    habilidades = listar_habilidades()

    for h in habilidades:
        if _normalizar(h["nombre"]) == objetivo:
            with open(h["archivo"], "r", encoding="utf-8") as f:
                return f.read()

    for h in habilidades:
        palabras_nombre = _palabras_clave(h["nombre"])
        if palabras_nombre and (palabras_nombre <= palabras_objetivo or palabras_objetivo <= palabras_nombre):
            with open(h["archivo"], "r", encoding="utf-8") as f:
                return f.read()

    return None
