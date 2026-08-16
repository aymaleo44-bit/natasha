import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'natasha_jarvis'))

"""
NATASHA — punto de entrada.

Arquitectura modular estilo JARVIS:
  1. Motor (Gemini)                          -> motor_gemini.py
  2. Memoria (bóveda Markdown estilo Obsidian) -> memoria_boveda.py
  3. Voz local (STT/TTS)                     -> voz_local.py
  4. Gestos por cámara (opcional)            -> gestos.py
  5. HUD cyberpunk (panel único)             -> hud.py

Ejecutar:  python natasha.py
"""
import tkinter as tk

from configuracion import cargar_configuracion
import memoria_boveda as boveda
from motor_gemini import MotorNatasha
from voz_local import VozLocal
from gestos import NatashaGestos
from hud import NatashaHUD


def main():
    cargar_configuracion()
    boveda.asegurar_estructura()
    motor = MotorNatasha()
    voz = VozLocal(idioma="es")
    gestos = NatashaGestos(callback_gesto=None)  # callback real se conecta abajo

    root = tk.Tk()
    hud = NatashaHUD(root, motor, voz, gestos)
    gestos.callback_gesto = hud.on_gesto_detectado

    root.mainloop()


if __name__ == "__main__":
    main()
