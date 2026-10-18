"""
HUD de Natasha — estilo WidgetClub aesthetic, panel único:
  - Modelo 3D (esfera dorada orgánica girando) que "respira" con el
    volumen del micrófono mientras se escucha.
  - Estado del canal de audio / gestos, métricas en vivo, agenda,
    registro de comandos — todo dentro de "widgets" con bordes
    redondeados y sombras suaves sobre un fondo pastel cálido.

Optimizaciones de rendimiento:
  - Tabla trigonométrica pre-calculada (sin math.cos/sin en cada frame).
  - Caché de colores interpolados (evita recálculo por frame).
  - Esfera dibujada solo con líneas (sin halos de óvalo por nodo).
  - Frecuencia de animación adaptativa.

Interacción:
  - Mantener presionada la barra espaciadora: push-to-talk (STT local).
  - Botón de cámara: activa el reconocimiento de gestos.
"""
import glob
import math
import os
import random
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext

import memoria_boveda as boveda
from acciones import ejecutar_habilidad

# =====================================================================
# Paleta WidgetClub — pastel cálido, widgets card-style
# =====================================================================
FONDO       = "#f5efe6"   # fondo general — pergamino claro
CARD        = "#ffffff"   # superficie de widget/card — blanco puro
CARD_BORDE  = "#e8ddd0"   # borde suave de cards
SOMBRA      = "#ddd3c4"   # sombra de card
ACENTO_1    = "#c4a882"   # acento principal — latte dorado
ACENTO_2    = "#a68b6b"   # acento secundario — caramelo oscuro
ACENTO_SOFT = "#e6d5c3"   # acento suave — beige rosado
TEXTO_PRIM  = "#3d3229"   # texto principal — marrón cacao oscuro
TEXTO_SEC   = "#8a7e72"   # texto secundario — gris cálido
ALERTA      = "#d4856b"   # estado alerta — coral/terracota suave
EXITO       = "#8fae78"   # estado ok — verde sage
SPHERE_DARK = "#b89b7a"   # esfera lado oscuro
SPHERE_LITE = "#e8d5b8"   # esfera lado claro
SPHERE_GLOW = "#f7eadb"   # glow de nodo cercano

FUENTE_TITULO = "Georgia"
FUENTE_CUERPO = "Segoe UI"
FUENTE_ACCENT = "Segoe UI Light"

# =====================================================================
# Utilidades — caché de colores y trig pre-calculado
# =====================================================================
_COLOR_CACHE = {}

def interpolar_hex(c1: str, c2: str, t: float) -> str:
    """Interpolación lineal entre dos colores hex, con caché."""
    t = max(0.0, min(1.0, t))
    clave = (c1, c2, round(t, 2))
    if clave in _COLOR_CACHE:
        return _COLOR_CACHE[clave]
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    resultado = f"#{r:02x}{g:02x}{b:02x}"
    _COLOR_CACHE[clave] = resultado
    return resultado

# Tabla trigonométrica pre-calculada (720 pasos = 0.5° resolución)
_TRIG_STEPS = 720
_TRIG_TABLE_COS = [math.cos(2 * math.pi * i / _TRIG_STEPS) for i in range(_TRIG_STEPS)]
_TRIG_TABLE_SIN = [math.sin(2 * math.pi * i / _TRIG_STEPS) for i in range(_TRIG_STEPS)]

def _fast_cos(angle: float) -> float:
    idx = int((angle % (2 * math.pi)) / (2 * math.pi) * _TRIG_STEPS) % _TRIG_STEPS
    return _TRIG_TABLE_COS[idx]

def _fast_sin(angle: float) -> float:
    idx = int((angle % (2 * math.pi)) / (2 * math.pi) * _TRIG_STEPS) % _TRIG_STEPS
    return _TRIG_TABLE_SIN[idx]


# =====================================================================
# Widget "card" redondeado — simulado con un Canvas interno
# =====================================================================
def crear_card(parent, ancho=None, alto=None, **pack_kw):
    """Crea un frame que simula una card WidgetClub con borde suave."""
    outer = tk.Frame(parent, bg=FONDO)
    outer.pack(**pack_kw)

    # Sombra sutil (un frame ligeramente más grande detrás)
    sombra = tk.Frame(outer, bg=SOMBRA, padx=1, pady=1)
    sombra.pack(fill="both", expand=True)

    card = tk.Frame(sombra, bg=CARD, padx=14, pady=10,
                    highlightbackground=CARD_BORDE, highlightthickness=1)
    card.pack(fill="both", expand=True)

    return card


class NatashaHUD:
    def __init__(self, ventana, motor, voz, gestos=None):
        self.ventana = ventana
        self.motor = motor
        self.voz = voz
        self.gestos = gestos

        self.contador_comandos = 0
        self.hora_inicio = time.time()
        self.grabando = False
        self.angulo = 0.0
        self.nivel_suavizado = 0.0
        self.escala_base = 90
        self.gestos_activos = False
        self._pantalla_completa = False

        # Pre-cálculos para tilt
        self._tilt = math.radians(18)
        self._cos_tilt = math.cos(self._tilt)
        self._sin_tilt = math.sin(self._tilt)

        ventana.title("Natasha")
        ventana.geometry("1060x750")
        ventana.configure(bg=FONDO)
        ventana.resizable(False, False)

        self._construir_layout()

        self.puntos_base = self._generar_esfera(36)
        self.aristas = self._generar_aristas(self.puntos_base, vecinos=3, extra_diagonales=6)
        # Pre-calcular colores de profundidad (10 niveles)
        self._colores_linea = [interpolar_hex(SPHERE_DARK, SPHERE_LITE, i / 9) for i in range(10)]
        self._colores_nodo = [interpolar_hex(SPHERE_LITE, SPHERE_GLOW, i / 9) for i in range(10)]

        self._animar_esfera()
        self._actualizar_metricas()

        ventana.bind("<KeyPress-space>", self._on_tecla_abajo)
        ventana.bind("<KeyRelease-space>", self._on_tecla_arriba)
        ventana.bind("<Escape>", self._salir_pantalla_completa)
        ventana.focus_set()

    # =================================================================
    # LAYOUT — estilo WidgetClub: cards flotantes sobre fondo pastel
    # =================================================================
    def _construir_layout(self):
        # Barra superior decorativa — degradado suave simulado
        barra = tk.Frame(self.ventana, bg=ACENTO_1, height=3)
        barra.pack(fill="x", side="top")

        # ---- Columna izquierda: identidad + canales ----
        self.panel_izq = tk.Frame(self.ventana, bg=FONDO, width=380)
        self.panel_izq.pack(side="left", fill="y", padx=(16, 8), pady=12)
        self.panel_izq.pack_propagate(False)

        # Card de identidad (esfera + nombre)
        card_id = crear_card(self.panel_izq, fill="x", pady=(0, 8))

        self.ancho_canvas = 340
        self.alto_canvas = 300
        self.canvas = tk.Canvas(card_id, width=self.ancho_canvas, height=self.alto_canvas,
                                 bg=CARD, highlightthickness=0)
        self.canvas.pack(pady=(4, 0))
        self._dibujar_nombre_fijo()

        # Estado canal — dentro de la card de identidad
        self.lbl_estado_canal = tk.Label(card_id, text="◇  Inactivo", font=(FUENTE_ACCENT, 14),
                                          bg=CARD, fg=TEXTO_SEC)
        self.lbl_estado_canal.pack(pady=(2, 4))

        tk.Label(card_id, text="mantén espacio para hablar",
                 font=(FUENTE_ACCENT, 9), bg=CARD, fg=ACENTO_1).pack(pady=(0, 8))

        # Card de estado del sistema
        card_sys = crear_card(self.panel_izq, fill="x", pady=(0, 8))

        tk.Label(card_sys, text="Sistema", font=(FUENTE_CUERPO, 11, "bold"),
                 bg=CARD, fg=TEXTO_PRIM).pack(anchor="w", pady=(0, 6))

        self.lbl_modo = tk.Label(card_sys, text="Motor: —", font=(FUENTE_CUERPO, 10),
                                  bg=CARD, fg=TEXTO_SEC)
        self.lbl_modo.pack(anchor="w", pady=1)
        self.lbl_modo.config(
            text=f"Motor: {'● Gemini' if self.motor.modo_gemini else '○ Local'}",
            fg=EXITO if self.motor.modo_gemini else TEXTO_SEC
        )

        self.lbl_voz = tk.Label(card_sys, text="Voz: —", font=(FUENTE_CUERPO, 10),
                                 bg=CARD, fg=TEXTO_SEC)
        self.lbl_voz.pack(anchor="w", pady=1)
        self.lbl_voz.config(
            text=f"Voz: {'● Activa' if self.voz.disponible() else '○ No disponible'}",
            fg=EXITO if self.voz.disponible() else TEXTO_SEC
        )

        self.lbl_gestos = tk.Label(card_sys, text="Gestos: —", font=(FUENTE_CUERPO, 10),
                                    bg=CARD, fg=TEXTO_SEC)
        self.lbl_gestos.pack(anchor="w", pady=1)
        gestos_ok = bool(self.gestos and self.gestos.disponible())
        self.lbl_gestos.config(
            text=f"Gestos: {'● Cámara OK' if gestos_ok else '○ No disponible'}",
            fg=EXITO if gestos_ok else TEXTO_SEC
        )

        # Botón de gestos — estilo card button
        self.boton_gestos = tk.Button(
            card_sys, text="📷  Activar cámara", takefocus=0,
            command=self._alternar_gestos,
            bg=ACENTO_SOFT, fg=ACENTO_2, activebackground=CARD_BORDE, activeforeground=ACENTO_2,
            relief="flat", font=(FUENTE_CUERPO, 10), cursor="hand2",
            padx=12, pady=6
        )
        self.boton_gestos.pack(fill="x", pady=(8, 4))

        tk.Label(card_sys,
                 text="mano abierta → pantalla completa  ·  puño → minimizar",
                 font=(FUENTE_ACCENT, 8), bg=CARD, fg=TEXTO_SEC, wraplength=320).pack(pady=(0, 2))

        # Card de acciones rápidas
        card_acciones = crear_card(self.panel_izq, fill="x", pady=(0, 0))

        tk.Label(card_acciones, text="Acciones rápidas", font=(FUENTE_CUERPO, 11, "bold"),
                 bg=CARD, fg=TEXTO_PRIM).pack(anchor="w", pady=(0, 6))

        for etiqueta, habilidad in [
            ("🗓  Plan de hoy", "plan_hoy"),
            ("📈  Escanear tendencias", "escanear_tendencias"),
            ("📊  Resumen semanal", "resumen_semanal"),
        ]:
            btn = tk.Button(
                card_acciones, text=etiqueta, takefocus=0,
                command=lambda h=habilidad, e=etiqueta: self._ejecutar_desde_boton(h, e),
                bg=ACENTO_SOFT, fg=TEXTO_PRIM, activebackground=CARD_BORDE,
                activeforeground=TEXTO_PRIM,
                relief="flat", font=(FUENTE_CUERPO, 10), anchor="w",
                padx=12, pady=6, cursor="hand2"
            )
            btn.pack(fill="x", pady=2)

        # ---- Columna derecha: métricas, agenda, log ----
        self.panel_der = tk.Frame(self.ventana, bg=FONDO)
        self.panel_der.pack(side="right", fill="both", expand=True, padx=(8, 16), pady=12)

        # Card de métricas
        card_metricas = crear_card(self.panel_der, fill="x", pady=(0, 8))

        tk.Label(card_metricas, text="Métricas", font=(FUENTE_CUERPO, 11, "bold"),
                 bg=CARD, fg=TEXTO_PRIM).pack(anchor="w", pady=(0, 6))

        fila_metricas = tk.Frame(card_metricas, bg=CARD)
        fila_metricas.pack(fill="x")

        self.lbl_hora = tk.Label(fila_metricas, text="--:--:--", font=(FUENTE_TITULO, 14),
                                  bg=CARD, fg=ACENTO_2)
        self.lbl_hora.pack(side="left", padx=(0, 16))

        self.lbl_uptime = tk.Label(fila_metricas, text="Uptime 0m", font=(FUENTE_CUERPO, 10),
                                    bg=CARD, fg=TEXTO_SEC)
        self.lbl_uptime.pack(side="left", padx=(0, 16))

        self.lbl_comandos = tk.Label(fila_metricas, text="Comandos 0", font=(FUENTE_CUERPO, 10),
                                      bg=CARD, fg=TEXTO_SEC)
        self.lbl_comandos.pack(side="left", padx=(0, 16))

        self.lbl_ultima_habilidad = tk.Label(fila_metricas, text="Última: —",
                                              font=(FUENTE_CUERPO, 10), bg=CARD, fg=TEXTO_SEC)
        self.lbl_ultima_habilidad.pack(side="left")

        # Card de agenda
        card_agenda = crear_card(self.panel_der, fill="both", expand=True, pady=(0, 8))

        tk.Label(card_agenda, text="Agenda · Plan de hoy", font=(FUENTE_CUERPO, 11, "bold"),
                 bg=CARD, fg=TEXTO_PRIM).pack(anchor="w", pady=(0, 6))

        self.texto_agenda = scrolledtext.ScrolledText(
            card_agenda, height=8, font=(FUENTE_CUERPO, 10),
            bg="#faf7f2", fg=TEXTO_PRIM, relief="flat", insertbackground=TEXTO_PRIM,
            borderwidth=0, highlightthickness=0
        )
        self.texto_agenda.pack(fill="both", expand=True)
        self.texto_agenda.configure(state="disabled")
        self._cargar_plan_hoy()

        # Card de log
        card_log = crear_card(self.panel_der, fill="both", expand=True, pady=(0, 0))

        tk.Label(card_log, text="Registro", font=(FUENTE_CUERPO, 11, "bold"),
                 bg=CARD, fg=TEXTO_PRIM).pack(anchor="w", pady=(0, 6))

        self.texto_log = scrolledtext.ScrolledText(
            card_log, height=10, font=(FUENTE_CUERPO, 10),
            bg="#faf7f2", fg=ACENTO_2, relief="flat", insertbackground=ACENTO_2,
            borderwidth=0, highlightthickness=0
        )
        self.texto_log.pack(fill="both", expand=True)
        self.texto_log.configure(state="disabled")
        self._log("Natasha lista. Mantén espacio para hablar.")

    # =================================================================
    # ESFERA 3D — optimizada: trig pre-calculado, colores cacheados,
    # solo líneas + puntos pequeños (sin halos pesados)
    # =================================================================
    def _generar_esfera(self, n_puntos):
        puntos = []
        angulo_dorado = math.pi * (3 - math.sqrt(5))
        inv = 1.0 / float(n_puntos - 1)
        for i in range(n_puntos):
            y = 1 - i * inv * 2
            radio = math.sqrt(max(0.0, 1 - y * y))
            theta = angulo_dorado * i
            x = math.cos(theta) * radio
            z = math.sin(theta) * radio
            puntos.append((x, y, z))
        return puntos

    def _generar_aristas(self, puntos, vecinos, extra_diagonales):
        aristas = set()
        n = len(puntos)
        for i in range(n):
            distancias = []
            for j in range(n):
                if i == j:
                    continue
                dx = puntos[i][0] - puntos[j][0]
                dy = puntos[i][1] - puntos[j][1]
                dz = puntos[i][2] - puntos[j][2]
                distancias.append((dx * dx + dy * dy + dz * dz, j))
            distancias.sort(key=lambda par: par[0])
            for _, j in distancias[:vecinos]:
                aristas.add(tuple(sorted((i, j))))
        rnd = random.Random(7)
        for _ in range(extra_diagonales):
            a, b = rnd.sample(range(n), 2)
            aristas.add(tuple(sorted((a, b))))
        return list(aristas)

    def _dibujar_nombre_fijo(self):
        cx = self.ancho_canvas / 2
        y_nombre = self.alto_canvas * 0.93
        # Sombra cálida suave
        self.canvas.create_text(cx + 1, y_nombre + 1, text="natasha",
                                 font=(FUENTE_TITULO, 22, "italic"), fill=CARD_BORDE)
        self.canvas.create_text(cx, y_nombre, text="natasha",
                                 font=(FUENTE_TITULO, 22, "italic"), fill=ACENTO_2)

    def _animar_esfera(self):
        self.angulo += 0.015

        nivel = self.voz.nivel_actual if (self.grabando and self.voz.disponible()) else 0.0
        self.nivel_suavizado += (nivel - self.nivel_suavizado) * 0.2

        self._dibujar_esfera()
        self.ventana.after(40, self._animar_esfera)  # ~25 FPS en vez de ~30

    def _dibujar_esfera(self):
        self.canvas.delete("esfera")
        cx = self.ancho_canvas / 2
        cy = self.alto_canvas * 0.40
        escala = self.escala_base * (1.0 + min(self.nivel_suavizado, 1.0) * 0.55)
        distancia_camara = 3.4

        cos_a = _fast_cos(self.angulo)
        sin_a = _fast_sin(self.angulo)
        cos_t = self._cos_tilt
        sin_t = self._sin_tilt

        proyectados = []
        for (x, y, z) in self.puntos_base:
            y1 = y * cos_t - z * sin_t
            z1 = y * sin_t + z * cos_t

            xr = x * cos_a + z1 * sin_a
            zr = -x * sin_a + z1 * cos_a

            factor = escala * 2.0 / (distancia_camara - zr)
            proyectados.append((cx + xr * factor, cy + y1 * factor, zr))

        # Dibujar aristas — color basado en profundidad (10 niveles cacheados)
        for i, j in self.aristas:
            x1, y1, z1 = proyectados[i]
            x2, y2, z2 = proyectados[j]
            t_idx = min(9, max(0, int((((z1 + z2) / 2) + 1) / 2 * 9)))
            self.canvas.create_line(x1, y1, x2, y2,
                                     fill=self._colores_linea[t_idx], width=1, tags="esfera")

        # Dibujar nodos — solo círculos pequeños, sin halos pesados
        for idx in range(len(proyectados)):
            px, py, pz = proyectados[idx]
            t_idx = min(9, max(0, int(((pz + 1) / 2) * 9)))
            r = 2.0 + t_idx * 0.3
            self.canvas.create_oval(px - r, py - r, px + r, py + r,
                                     fill=self._colores_nodo[t_idx], outline="", tags="esfera")

    # =================================================================
    # MÉTRICAS EN VIVO
    # =================================================================
    def _actualizar_metricas(self):
        self.lbl_hora.config(text=datetime.now().strftime("%H:%M:%S"))
        minutos = int((time.time() - self.hora_inicio) / 60)
        self.lbl_uptime.config(text=f"Uptime {minutos}m")
        self.ventana.after(1000, self._actualizar_metricas)

    # =================================================================
    # AGENDA / PLAN DEL DÍA
    # =================================================================
    def _cargar_plan_hoy(self):
        patrones = ["*plan_hoy*.md", "*plan-hoy*.md"]
        candidatos = []
        for patron in patrones:
            candidatos += glob.glob(os.path.join(boveda.RAIZ_BOVEDA, "outputs", patron))
        candidatos = sorted(set(candidatos), key=os.path.getmtime, reverse=True)

        self.texto_agenda.configure(state="normal")
        self.texto_agenda.delete("1.0", tk.END)
        if candidatos:
            with open(candidatos[0], "r", encoding="utf-8") as f:
                self.texto_agenda.insert(tk.END, f.read())
        else:
            self.texto_agenda.insert(
                tk.END,
                "Aún no hay un plan para hoy.\n"
                "Pulsa 'Plan de hoy' o dilo por voz."
            )
        self.texto_agenda.configure(state="disabled")

    # =================================================================
    # LOG
    # =================================================================
    def _log(self, texto):
        self.texto_log.configure(state="normal")
        self.texto_log.insert(tk.END, texto + "\n")
        self.texto_log.see(tk.END)
        self.texto_log.configure(state="disabled")

    # =================================================================
    # PUSH-TO-TALK (barra espaciadora)
    # =================================================================
    def _on_tecla_abajo(self, event):
        if self.grabando:
            return
        self.grabando = True
        self.lbl_estado_canal.config(text="●  Escuchando…", fg=ALERTA)
        if self.voz.disponible():
            self.voz.iniciar_grabacion()
        else:
            self._log("STT local no disponible.")

    def _on_tecla_arriba(self, event):
        if not self.grabando:
            return
        self.grabando = False
        if not self.voz.disponible():
            self.lbl_estado_canal.config(text="◇  Inactivo", fg=TEXTO_SEC)
            return
        self.lbl_estado_canal.config(text="◈  Transcribiendo…", fg=ACENTO_1)
        threading.Thread(target=self._transcribir_y_procesar, daemon=True).start()

    def _transcribir_y_procesar(self):
        texto = self.voz.detener_grabacion_y_transcribir()
        self.ventana.after(0, lambda: self._procesar_texto(texto))

    # =================================================================
    # PROCESAMIENTO DE COMANDOS
    # =================================================================
    def _procesar_texto(self, texto):
        if not texto:
            self.lbl_estado_canal.config(text="◇  Inactivo", fg=TEXTO_SEC)
            return

        self._log(f"> Tú: {texto}")
        self.lbl_estado_canal.config(text="◆  Ejecutando…", fg=ACENTO_1)
        self.ventana.update_idletasks()

        respuesta = self.motor.consultar(texto)

        self.contador_comandos += 1
        self.lbl_comandos.config(text=f"Comandos {self.contador_comandos}")
        self._log(f"> Natasha: {respuesta}")

        self.lbl_estado_canal.config(text="◈  Hablando…", fg=EXITO)
        self.voz.hablar(respuesta)
        self.ventana.after(1500, lambda: self.lbl_estado_canal.config(text="◇  Inactivo", fg=TEXTO_SEC))

        if any(p in texto.lower() for p in ["plan", "habilidad", "tendencia"]):
            self._cargar_plan_hoy()

    def _ejecutar_desde_boton(self, nombre_habilidad, etiqueta):
        self._log(f"Ejecutando '{nombre_habilidad}'…")
        self.lbl_estado_canal.config(text="◆  Ejecutando…", fg=ACENTO_1)
        self.ventana.update_idletasks()

        def _tarea():
            resultado = ejecutar_habilidad(nombre_habilidad)

            def _actualizar():
                self._log(f"> Natasha: {resultado}")
                self.lbl_ultima_habilidad.config(text=f"Última: {etiqueta}")
                self.lbl_estado_canal.config(text="◇  Inactivo", fg=TEXTO_SEC)
                self._cargar_plan_hoy()
                self.voz.hablar(resultado)

            self.ventana.after(0, _actualizar)

        threading.Thread(target=_tarea, daemon=True).start()

    # =================================================================
    # GESTOS POR CÁMARA
    # =================================================================
    def _alternar_gestos(self):
        if not self.gestos or not self.gestos.disponible():
            self._log("Gestos no disponibles (ver README).")
            return

        if not self.gestos_activos:
            iniciado = self.gestos.iniciar()
            if iniciado:
                self.gestos_activos = True
                self.boton_gestos.config(text="📷  Desactivar cámara", fg=ALERTA,
                                          bg="#fae8e0")
                self._log("Cámara de gestos activada.")
        else:
            self.gestos.detener()
            self.gestos_activos = False
            self.boton_gestos.config(text="📷  Activar cámara", fg=ACENTO_2,
                                      bg=ACENTO_SOFT)
            self._log("Cámara de gestos desactivada.")

    def on_gesto_detectado(self, nombre_gesto):
        """Llamado desde el hilo de la cámara (gestos.py). Reenvía el
        evento al hilo principal de Tkinter antes de tocar la ventana."""
        self.ventana.after(0, lambda: self._aplicar_gesto(nombre_gesto))

    def _aplicar_gesto(self, nombre_gesto):
        if nombre_gesto == "abierta":
            self._log("✋ Mano abierta → pantalla completa.")
            self._pantalla_completa = True
            self.ventana.attributes("-fullscreen", True)
        elif nombre_gesto == "cerrada":
            self._log("✊ Puño → minimizar.")
            self._pantalla_completa = False
            self.ventana.attributes("-fullscreen", False)
            self.ventana.iconify()

    def _salir_pantalla_completa(self, event=None):
        if self._pantalla_completa:
            self._pantalla_completa = False
            self.ventana.attributes("-fullscreen", False)
