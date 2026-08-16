"""
Funciones de acción de Natasha.

Cada función de este archivo se pasa como 'tool' al motor Gemini
(google-genai inspecciona automáticamente el nombre, los type hints y el
docstring para construir el function-calling schema), y las mismas
funciones se reutilizan en el enrutador local sin conexión.
"""
from datetime import datetime

import memoria_boveda as boveda
import skills_loader
import workspace_google
from sistema_control import NatashaSystemControl

_sistema = NatashaSystemControl()


def abrir(objetivo: str) -> str:
    """Abre una aplicación de la lista blanca (ej. calculadora, bloc de notas,
    chrome) o un sitio web conocido (ej. google, youtube, gmail). Si no coincide
    con ninguno, hace una búsqueda en Google con el texto recibido."""
    _, mensaje = _sistema.resolver_apertura(objetivo)
    return mensaje


def cerrar_aplicacion(nombre: str) -> str:
    """Cierra una aplicación de la lista blanca que esté abierta (ej. bloc de
    notas, word, chrome)."""
    _, mensaje = _sistema.cerrar_aplicacion(nombre)
    return mensaje


def crear_carpeta_escritorio(nombre: str) -> str:
    """Crea una carpeta nueva en el escritorio de Windows con el nombre indicado."""
    _, mensaje = _sistema.crear_carpeta(nombre)
    return mensaje


def guardar_nota_boveda(subcarpeta: str, titulo: str, contenido: str) -> str:
    """Guarda una nota en Markdown dentro de la bóveda de conocimiento de Natasha.
    subcarpeta debe ser 'raw', 'wiki' u 'outputs'."""
    ruta = boveda.guardar_nota(subcarpeta, titulo, contenido)
    return f"Nota guardada en {ruta}"


def buscar_en_boveda(consulta: str) -> str:
    """Busca por palabras clave dentro de todas las notas de la bóveda de
    conocimiento y devuelve los fragmentos más relevantes."""
    resultados = boveda.buscar(consulta)
    if not resultados:
        return "No encontré notas relacionadas en la bóveda."
    lineas = [f"- ({puntaje} coincidencias) {ruta}: {frag}" for puntaje, ruta, frag in resultados]
    return "Encontré esto en la bóveda:\n" + "\n".join(lineas)


def ejecutar_habilidad(nombre_habilidad: str) -> str:
    """Ejecuta una habilidad definida en /skills (ej. plan_hoy,
    escanear_tendencias), usando el motor Gemini para generar el
    resultado y guardándolo en la bóveda."""
    prompt_habilidad = skills_loader.leer_habilidad(nombre_habilidad)
    if not prompt_habilidad:
        return f"No encontré la habilidad '{nombre_habilidad}'. Revisa la carpeta /skills."

    nombre_normalizado = nombre_habilidad.strip().lower()
    contexto_extra = ""

    if "plan" in nombre_normalizado:
        eventos = workspace_google.obtener_eventos_hoy()
        bloque_eventos = "\n".join(eventos) if eventos else "[Calendar no conectado.]"
        recientes = boveda.notas_recientes("outputs", limite=3)
        bloque_notas = "\n\n".join(boveda.leer_nota(r) for r in recientes) if recientes else \
            "[Sin notas recientes en bóveda/outputs.]"
        contexto_extra = f"Eventos de hoy:\n{bloque_eventos}\n\nNotas recientes:\n{bloque_notas}"

    elif "tendencia" in nombre_normalizado:
        recientes = boveda.notas_recientes("raw", limite=8)
        contexto_extra = "\n\n".join(boveda.leer_nota(r) for r in recientes) if recientes else \
            "[Sin notas en bóveda/raw todavía.]"

    elif "wiki" in nombre_normalizado or "conocimiento" in nombre_normalizado:
        recientes = boveda.notas_recientes("wiki", limite=6)
        contexto_extra = "\n\n".join(boveda.leer_nota(r) for r in recientes) if recientes else \
            "[Sin notas en bóveda/wiki todavía.]"

    elif "semanal" in nombre_normalizado or "resumen" in nombre_normalizado:
        recientes_out = boveda.notas_recientes("outputs", limite=5)
        recientes_raw = boveda.notas_recientes("raw", limite=5)
        todas = recientes_out + recientes_raw
        contexto_extra = "\n\n".join(boveda.leer_nota(r) for r in todas) if todas else \
            "[Sin notas recientes en la bóveda.]"

    else:
        # Contexto general por defecto para cualquier habilidad personalizada
        recientes_out = boveda.notas_recientes("outputs", limite=3)
        recientes_wiki = boveda.notas_recientes("wiki", limite=3)
        todas = recientes_out + recientes_wiki
        if todas:
            contexto_extra = "Notas recientes en la bóveda:\n\n" + "\n\n".join(boveda.leer_nota(r) for r in todas[:4])

    # Import diferido: evita import circular (motor_gemini importa este módulo).
    from motor_gemini import MotorNatasha
    motor = MotorNatasha()
    resultado = motor.generar_libre(prompt_habilidad, contexto_extra)

    titulo = f"{nombre_habilidad} {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    boveda.guardar_nota("outputs", titulo, resultado)

    primera_linea = next((l for l in resultado.strip().splitlines() if l.strip()), "Listo.")
    return f"Habilidad '{nombre_habilidad}' ejecutada y guardada en la bóveda. {primera_linea[:180]}"
