"""
HUD de Natasha — estilo cyberpunk, panel único (sin pestañas):
  - Modelo 3D (esfera de red amarilla girando) que "respira" (crece y
    encoge) con el volumen del micrófono mientras se escucha.
  - Estado del canal de audio: Inactivo / Escuchando / Ejecutando / Hablando
  - Estado del canal de gestos (cámara): Inactivo / Detectando
  - Métricas en vivo (hora, uptime, comandos procesados, última habilidad)
  - Agenda / plan del día (leído directamente de la bóveda)
  - Registro de comandos, con tipografía monoespaciada y acentos neón

Interacción:
  - Mantener presionada la barra espaciadora: push-to-talk (STT local).
  - Botón de cámara: activa el reconocimiento de gestos.
      Mano abierta  -> pantalla completa.
      Mano cerrada  -> minimizar.
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

# ---------------------------------------------------------------------
# Paleta cyberpunk
# ---------------------------------------------------------------------
NEGRO = "#050208"
PANEL = "#0b0714"
MAGENTA = "#ff2bd6"
MAGENTA_OSC = "#7a0f66"
CIAN = "#00fff2"
CIAN_OSC = "#0a5a56"
AMARILLO = "#ffcc33"
AMARILLO_OSC = "#4d3d00"
TEXTO = "#d9d3ff"
TEXTO_TENUE = "#6f6a8a"
ROJO = "#ff3366"
VERDE = "#39ff88"

FUENTE_MONO = "Consolas"


def interpolar_hex(c1, c2, t):
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


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
        self.escala_base = 100
        self.gestos_activos = False
        self._pantalla_completa = False

        ventana.title("NATASHA // HUD_v9")
        ventana.geometry("1040x740")
        ventana.configure(bg=NEGRO)
        ventana.resizable(False, False)

        self._construir_layout()

        self.puntos_base = self._generar_esfera(40)
        self.aristas = self._generar_aristas(self.puntos_base, vecinos=3, extra_diagonales=8)
        self._animar_esfera()
        self._actualizar_metricas()

        ventana.bind("<KeyPress-space>", self._on_tecla_abajo)
        ventana.bind("<KeyRelease-space>", self._on_tecla_arriba)
        ventana.bind("<Escape>", self._salir_pantalla_completa)
        ventana.focus_set()

    # =================================================================
    # LAYOUT
    # =================================================================
    def _titulo_seccion(self, texto):
        return {"text": f" {texto} ", "bg": PANEL, "fg": CIAN, "font": (FUENTE_MONO, 9, "bold")}

    def _construir_layout(self):
        borde = tk.Frame(self.ventana, bg=MAGENTA, height=2)
        borde.pack(fill="x", side="top")

        # ---- Columna izquierda: identidad + canales ----
        self.panel_izq = tk.Frame(self.ventana, bg=NEGRO, width=370,
                                   highlightbackground=MAGENTA_OSC, highlightthickness=1)
        self.panel_izq.pack(side="left", fill="y", padx=(15, 8), pady=15)
        self.panel_izq.pack_propagate(False)

        self.ancho_canvas = 340
        self.alto_canvas = 330
        self.canvas = tk.Canvas(self.panel_izq, width=self.ancho_canvas, height=self.alto_canvas,
                                 bg=NEGRO, highlightthickness=0)
        self.canvas.pack(pady=(10, 4))
        self._dibujar_nombre_fijo()

        self.lbl_estado_canal = tk.Label(self.panel_izq, text="◇ INACTIVO", font=(FUENTE_MONO, 14, "bold"),
                                          bg=NEGRO, fg=TEXTO_TENUE)
        self.lbl_estado_canal.pack(pady=(4, 2))

        tk.Label(self.panel_izq,
                 text="[ MANTÉN ESPACIO PARA HABLAR ]",
                 font=(FUENTE_MONO, 8, "bold"), bg=NEGRO, fg=MAGENTA, justify="center").pack(pady=(0, 10))

        self.lbl_modo = tk.Label(self.panel_izq, text="MOTOR: —", font=(FUENTE_MONO, 9, "bold"),
                                  bg=NEGRO, fg=CIAN)
        self.lbl_modo.pack(pady=(0, 2))
        self.lbl_modo.config(
            text=f"MOTOR: {'●GEMINI' if self.motor.modo_gemini else '○LOCAL (sin API key)'}"
        )

        self.lbl_voz = tk.Label(self.panel_izq, text="VOZ: —", font=(FUENTE_MONO, 9, "bold"),
                                 bg=NEGRO, fg=CIAN)
        self.lbl_voz.pack(pady=(0, 2))
        self.lbl_voz.config(
            text=f"VOZ: {'●LOCAL OK' if self.voz.disponible() else '○NO DISPONIBLE'}"
        )

        self.lbl_gestos = tk.Label(self.panel_izq, text="GESTOS: —", font=(FUENTE_MONO, 9, "bold"),
                                    bg=NEGRO, fg=CIAN)
        self.lbl_gestos.pack(pady=(0, 10))
        gestos_ok = bool(self.gestos and self.gestos.disponible())
        self.lbl_gestos.config(text=f"GESTOS: {'●CÁMARA OK' if gestos_ok else '○NO DISPONIBLE'}")

        self.boton_gestos = tk.Button(
            self.panel_izq, text="◉  ACTIVAR CÁMARA DE GESTOS", takefocus=0,
            command=self._alternar_gestos,
            bg=PANEL, fg=MAGENTA, activebackground="#1a0f1f", activeforeground=MAGENTA,
            relief="flat", font=(FUENTE_MONO, 9, "bold"),
            highlightbackground=MAGENTA_OSC, highlightthickness=1, padx=10, pady=8
        )
        self.boton_gestos.pack(fill="x", pady=(0, 4))

        tk.Label(self.panel_izq,
                 text="Mano abierta = pantalla completa\nPuño cerrado = minimizar\n(video 100% local, nunca se guarda)",
                 font=(FUENTE_MONO, 7), bg=NEGRO, fg=TEXTO_TENUE, justify="center").pack(pady=(0, 10))

        tk.Label(self.panel_izq, text="// ACCIONES RÁPIDAS", font=(FUENTE_MONO, 9, "bold"),
                 bg=NEGRO, fg=TEXTO_TENUE).pack(pady=(4, 2), anchor="w")

        frame_botones = tk.Frame(self.panel_izq, bg=NEGRO)
        frame_botones.pack(fill="x")
        for etiqueta, habilidad in [
            ("🗓  PLAN DE HOY", "plan_hoy"),
            ("📈  ESCANEAR TENDENCIAS", "escanear_tendencias"),
            ("📊  RESUMEN SEMANAL", "resumen_semanal"),
        ]:
            tk.Button(
                frame_botones, text=etiqueta, takefocus=0,
                command=lambda h=habilidad, e=etiqueta: self._ejecutar_desde_boton(h, e),
                bg=PANEL, fg=CIAN, activebackground="#0f1a1f", activeforeground=CIAN,
                relief="flat", font=(FUENTE_MONO, 9, "bold"), anchor="w", padx=10, pady=7,
                highlightbackground=CIAN_OSC, highlightthickness=1
            ).pack(fill="x", pady=3)

        # ---- Columna derecha: métricas, agenda, log ----
        self.panel_der = tk.Frame(self.ventana, bg=NEGRO)
        self.panel_der.pack(side="right", fill="both", expand=True, padx=(8, 15), pady=15)

        frame_metricas = tk.LabelFrame(self.panel_der, **self._titulo_seccion("MÉTRICAS EN VIVO"),
                                        highlightbackground=CIAN_OSC, highlightthickness=1,
                                        padx=10, pady=8)
        frame_metricas.pack(fill="x", pady=(0, 8))

        self.lbl_hora = tk.Label(frame_metricas, text="--:--:--", font=(FUENTE_MONO, 12, "bold"),
                                  bg=PANEL, fg=MAGENTA)
        self.lbl_hora.pack(side="left", padx=10)
        self.lbl_uptime = tk.Label(frame_metricas, text="UPTIME 0m", font=(FUENTE_MONO, 10),
                                    bg=PANEL, fg=TEXTO)
        self.lbl_uptime.pack(side="left", padx=10)
        self.lbl_comandos = tk.Label(frame_metricas, text="COMANDOS 0", font=(FUENTE_MONO, 10),
                                      bg=PANEL, fg=TEXTO)
        self.lbl_comandos.pack(side="left", padx=10)
        self.lbl_ultima_habilidad = tk.Label(frame_metricas, text="ÚLTIMA HABILIDAD: —", font=(FUENTE_MONO, 10),
                                              bg=PANEL, fg=TEXTO)
        self.lbl_ultima_habilidad.pack(side="left", padx=10)

        frame_agenda = tk.LabelFrame(self.panel_der, **self._titulo_seccion("AGENDA // PLAN DE HOY"),
                                      highlightbackground=CIAN_OSC, highlightthickness=1,
                                      padx=10, pady=8)
        frame_agenda.pack(fill="both", expand=True, pady=(0, 8))
        self.texto_agenda = scrolledtext.ScrolledText(frame_agenda, height=9, font=(FUENTE_MONO, 9),
                                                        bg=PANEL, fg=TEXTO, relief="flat",
                                                        insertbackground=TEXTO)
        self.texto_agenda.pack(fill="both", expand=True)
        self.texto_agenda.configure(state="disabled")
        self._cargar_plan_hoy()

        frame_log = tk.LabelFrame(self.panel_der, **self._titulo_seccion("REGISTRO DE COMANDOS"),
                                   highlightbackground=MAGENTA_OSC, highlightthickness=1,
                                   padx=10, pady=8)
        frame_log.pack(fill="both", expand=True)
        self.texto_log = scrolledtext.ScrolledText(frame_log, height=11, font=(FUENTE_MONO, 9),
                                                     bg=PANEL, fg=AMARILLO, relief="flat",
                                                     insertbackground=AMARILLO)
        self.texto_log.pack(fill="both", expand=True)
        self.texto_log.configure(state="disabled")
        self._log(">> Natasha lista. ESPACIO para hablar. Cámara opcional para gestos.")

    # =================================================================
    # ESFERA 3D (identidad visual) — amarilla, gira sobre su eje y
    # "respira" con el volumen del micrófono mientras escucha.
    # =================================================================
    def _generar_esfera(self, n_puntos):
        puntos = []
        angulo_dorado = math.pi * (3 - math.sqrt(5))
        for i in range(n_puntos):
            y = 1 - (i / float(n_puntos - 1)) * 2
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
            i, j = rnd.sample(range(n), 2)
            aristas.add(tuple(sorted((i, j))))
        return list(aristas)

    def _dibujar_nombre_fijo(self):
        cx = self.ancho_canvas / 2
        y_nombre = self.alto_canvas * 0.92
        # Efecto de "aberración cromática" cyberpunk: capas magenta/cian
        # ligeramente desplazadas detrás del texto amarillo principal.
        self.canvas.create_text(cx - 2, y_nombre, text="NATASHA",
                                 font=("Arial Black", 22, "bold"), fill=CIAN)
        self.canvas.create_text(cx + 2, y_nombre, text="NATASHA",
                                 font=("Arial Black", 22, "bold"), fill=MAGENTA)
        self.canvas.create_text(cx, y_nombre, text="NATASHA",
                                 font=("Arial Black", 22, "bold"), fill=AMARILLO)

    def _animar_esfera(self):
        self.angulo += 0.018

        # Nivel de mic en vivo (0..1), suavizado para que el crecimiento
        # de la esfera no salte bruscamente entre cuadros.
        nivel = self.voz.nivel_actual if (self.grabando and self.voz.disponible()) else 0.0
        self.nivel_suavizado += (nivel - self.nivel_suavizado) * 0.25

        self._dibujar_esfera()
        self.ventana.after(33, self._animar_esfera)

    def _dibujar_esfera(self):
        self.canvas.delete("esfera")
        cx = self.ancho_canvas / 2
        cy = self.alto_canvas * 0.40
        # La esfera crece hasta ~65% más grande al hablar fuerte con el
        # micrófono activo, y vuelve a su tamaño base en silencio.
        escala = self.escala_base * (1.0 + min(self.nivel_suavizado, 1.0) * 0.65)
        distancia_camara = 3.4
        tilt = math.radians(18)

        proyectados = []
        for (x, y, z) in self.puntos_base:
            y1 = y * math.cos(tilt) - z * math.sin(tilt)
            z1 = y * math.sin(tilt) + z * math.cos(tilt)
            x1 = x

            xr = x1 * math.cos(self.angulo) + z1 * math.sin(self.angulo)
            zr = -x1 * math.sin(self.angulo) + z1 * math.cos(self.angulo)
            yr = y1

            factor = escala * 2.0 / (distancia_camara - zr)
            proyectados.append((cx + xr * factor, cy + yr * factor, zr))

        for i, j in sorted(self.aristas, key=lambda par: proyectados[par[0]][2] + proyectados[par[1]][2]):
            x1, y1, z1 = proyectados[i]
            x2, y2, z2 = proyectados[j]
            t = (((z1 + z2) / 2) + 1) / 2
            color = interpolar_hex(AMARILLO_OSC, AMARILLO, t)
            self.canvas.create_line(x1, y1, x2, y2, fill=color, width=1, tags="esfera")

        for idx in sorted(range(len(proyectados)), key=lambda k: proyectados[k][2]):
            px, py, pz = proyectados[idx]
            t = (pz + 1) / 2
            radio = 2.5 + t * 3.5
            color_halo = interpolar_hex(AMARILLO_OSC, "#ffb300", t)
            color_nucleo = interpolar_hex(AMARILLO, "#fffbe6", t)
            self.canvas.create_oval(px - radio - 2.5, py - radio - 2.5, px + radio + 2.5, py + radio + 2.5,
                                     fill=color_halo, outline="", tags="esfera")
            self.canvas.create_oval(px - radio, py - radio, px + radio, py + radio,
                                     fill=color_nucleo, outline="", tags="esfera")

    # =================================================================
    # MÉTRICAS EN VIVO
    # =================================================================
    def _actualizar_metricas(self):
        self.lbl_hora.config(text=datetime.now().strftime("%H:%M:%S"))
        minutos = int((time.time() - self.hora_inicio) / 60)
        self.lbl_uptime.config(text=f"UPTIME {minutos}m")
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
                "// Aún no hay un plan para hoy.\n"
                "Pulsa 'PLAN DE HOY' o dilo por voz: \"Natasha, plan de hoy\"."
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
        self.lbl_estado_canal.config(text="● ESCUCHANDO", fg=ROJO)
        if self.voz.disponible():
            self.voz.iniciar_grabacion()
        else:
            self._log("!! STT local no disponible (revisa sounddevice / faster-whisper en el README).")

    def _on_tecla_arriba(self, event):
        if not self.grabando:
            return
        self.grabando = False
        if not self.voz.disponible():
            self.lbl_estado_canal.config(text="◇ INACTIVO", fg=TEXTO_TENUE)
            return
        self.lbl_estado_canal.config(text="◈ TRANSCRIBIENDO", fg=AMARILLO)
        threading.Thread(target=self._transcribir_y_procesar, daemon=True).start()

    def _transcribir_y_procesar(self):
        texto = self.voz.detener_grabacion_y_transcribir()
        self.ventana.after(0, lambda: self._procesar_texto(texto))

    # =================================================================
    # PROCESAMIENTO DE COMANDOS
    # =================================================================
    def _procesar_texto(self, texto):
        if not texto:
            self.lbl_estado_canal.config(text="◇ INACTIVO", fg=TEXTO_TENUE)
            return

        self._log(f"> TÚ: {texto}")
        self.lbl_estado_canal.config(text="◆ EJECUTANDO", fg=AMARILLO)
        self.ventana.update_idletasks()

        respuesta = self.motor.consultar(texto)

        self.contador_comandos += 1
        self.lbl_comandos.config(text=f"COMANDOS {self.contador_comandos}")
        self._log(f"> NATASHA: {respuesta}")

        self.lbl_estado_canal.config(text="◈ HABLANDO", fg=CIAN)
        self.voz.hablar(respuesta)
        self.ventana.after(1500, lambda: self.lbl_estado_canal.config(text="◇ INACTIVO", fg=TEXTO_TENUE))

        if any(p in texto.lower() for p in ["plan", "habilidad", "tendencia"]):
            self._cargar_plan_hoy()

    def _ejecutar_desde_boton(self, nombre_habilidad, etiqueta):
        self._log(f">> Ejecutando habilidad '{nombre_habilidad}'…")
        self.lbl_estado_canal.config(text="◆ EJECUTANDO", fg=AMARILLO)
        self.ventana.update_idletasks()

        def _tarea():
            resultado = ejecutar_habilidad(nombre_habilidad)

            def _actualizar():
                self._log(f"> NATASHA: {resultado}")
                self.lbl_ultima_habilidad.config(text=f"ÚLTIMA HABILIDAD: {etiqueta}")
                self.lbl_estado_canal.config(text="◇ INACTIVO", fg=TEXTO_TENUE)
                self._cargar_plan_hoy()
                self.voz.hablar(resultado)

            self.ventana.after(0, _actualizar)

        threading.Thread(target=_tarea, daemon=True).start()

    # =================================================================
    # GESTOS POR CÁMARA
    # =================================================================
    def _alternar_gestos(self):
        if not self.gestos or not self.gestos.disponible():
            self._log("!! Gestos no disponibles: instala opencv-python y mediapipe (ver README).")
            return

        if not self.gestos_activos:
            iniciado = self.gestos.iniciar()
            if iniciado:
                self.gestos_activos = True
                self.boton_gestos.config(text="◉  DESACTIVAR CÁMARA DE GESTOS", fg=ROJO,
                                          highlightbackground=ROJO)
                self._log(">> Reconocimiento de gestos activado (mano abierta = pantalla completa, puño = minimizar).")
        else:
            self.gestos.detener()
            self.gestos_activos = False
            self.boton_gestos.config(text="◉  ACTIVAR CÁMARA DE GESTOS", fg=MAGENTA,
                                      highlightbackground=MAGENTA_OSC)
            self._log(">> Reconocimiento de gestos desactivado.")

    def on_gesto_detectado(self, nombre_gesto):
        """Llamado desde el hilo de la cámara (gestos.py). Reenvía el
        evento al hilo principal de Tkinter antes de tocar la ventana."""
        self.ventana.after(0, lambda: self._aplicar_gesto(nombre_gesto))

    def _aplicar_gesto(self, nombre_gesto):
        if nombre_gesto == "abierta":
            self._log("✋ Gesto detectado: mano abierta -> pantalla completa.")
            self._pantalla_completa = True
            self.ventana.attributes("-fullscreen", True)
        elif nombre_gesto == "cerrada":
            self._log("✊ Gesto detectado: puño -> minimizando ventana.")
            self._pantalla_completa = False
            self.ventana.attributes("-fullscreen", False)
            self.ventana.iconify()

    def _salir_pantalla_completa(self, event=None):
        if self._pantalla_completa:
            self._pantalla_completa = False
            self.ventana.attributes("-fullscreen", False)
