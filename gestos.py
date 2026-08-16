"""
Reconocimiento de gestos de Natasha — 100% local.

Usa la cámara de la laptop con MediaPipe Hands para detectar dos gestos
simples:
  - Mano ABIERTA  -> la ventana de Natasha pasa a pantalla completa.
  - Mano CERRADA (puño) -> la ventana de Natasha se minimiza.

El video se procesa en memoria, cuadro a cuadro, y nunca se guarda ni
se envía a ningún servidor. Todo corre en un hilo aparte para no
bloquear el HUD.
"""
import threading
import time
import os
import urllib.request
from typing import Any, Callable, Optional

cv2 = None
mp = None
HandLandmarker = None
HandLandmarkerOptions = None
BaseOptions = None
VisionRunningMode = None
Image = None

try:
    import cv2
    CV2_DISPONIBLE = True
except Exception:
    CV2_DISPONIBLE = False

try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    HandLandmarker = vision.HandLandmarker
    HandLandmarkerOptions = vision.HandLandmarkerOptions
    BaseOptions = python.BaseOptions
    VisionRunningMode = vision.RunningMode
    Image = mp.Image
    MEDIAPIPE_DISPONIBLE = True
except Exception:
    MEDIAPIPE_DISPONIBLE = False

# Modelo necesario para la nueva API
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

# Puntas de dedo y su articulación de referencia (índice, medio, anular, meñique)
_PUNTAS = [8, 12, 16, 20]
_BASES = [6, 10, 14, 18]

# Tiempo mínimo entre gestos consecutivos, para evitar que la ventana
# parpadee entre maximizar/minimizar por detecciones inestables.
_ENFRIAMIENTO_SEGUNDOS = 1.2
_RESET_SIN_MANO_SEGUNDOS = 2.0


class NatashaGestos:
    def __init__(self, callback_gesto: Optional[Callable[[str], None]], camara_index: int = 0):
        """callback_gesto(nombre) se llama con 'abierta' o 'cerrada' cuando
        se reconoce un gesto nuevo y estable."""
        self.callback_gesto = callback_gesto
        self.camara_index = camara_index
        self.activo = False
        self._hilo = None
        self._ultimo_gesto = None
        self._ultimo_cambio = 0.0

    def disponible(self) -> bool:
        return CV2_DISPONIBLE and MEDIAPIPE_DISPONIBLE

    def iniciar(self) -> bool:
        if not self.disponible() or self.activo:
            return False
        
        # Asegurar que el modelo existe
        if not os.path.exists(MODEL_PATH):
            print(f">> Descargando modelo de gestos (MediaPipe)...")
            try:
                urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            except Exception as e:
                print(f"!! No se pudo descargar el modelo: {e}")
                return False

        self.activo = True
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        return True

    def detener(self) -> None:
        self.activo = False

    # ------------------------------------------------------------------
    def _bucle(self) -> None:
        if cv2 is None or mp is None or HandLandmarker is None:
            self.activo = False
            return

        captura = cv2.VideoCapture(self.camara_index)
        
        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=VisionRunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5
        )

        try:
            with HandLandmarker.create_from_options(options) as landmarker:
                while self.activo:
                    ok, frame = captura.read()
                    if not ok:
                        time.sleep(0.05)
                        continue

                    frame = cv2.flip(frame, 1)
                    # Convertir a RGB para MediaPipe
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    # Crear objeto Image de MediaPipe
                    mp_image = Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    
                    # Timestamp en milisegundos
                    timestamp_ms = int(time.time() * 1000)
                    
                    # Detección
                    resultado = landmarker.detect_for_video(mp_image, timestamp_ms)

                    gesto = None
                    if resultado.hand_landmarks:
                        gesto = self._clasificar_gesto(resultado.hand_landmarks[0])

                    self._procesar_gesto(gesto)
                    time.sleep(0.03)
        except Exception as e:
            print(f"!! Error en el bucle de gestos: {e}")
        finally:
            captura.release()

    def _clasificar_gesto(self, landmarks: Any) -> Optional[str]:
        # landmarks es una lista de objetos Landmark (x, y, z)
        puntos = landmarks
        dedos_extendidos = 0
        for punta, base in zip(_PUNTAS, _BASES):
            # En la nueva API, los landmarks son objetos con atributos x, y, z
            if puntos[punta].y < puntos[base].y:
                dedos_extendidos += 1
        
        # Pulgar: aproximación por posición horizontal respecto a su base
        # Usamos los mismos índices: 4 (punta), 2 (base), 17 (base meñique), 0 (muñeca)
        if abs(puntos[4].x - puntos[2].x) > abs(puntos[17].x - puntos[0].x) * 0.35:
            dedos_extendidos += 1

        if dedos_extendidos >= 4:
            return "abierta"
        if dedos_extendidos <= 1:
            return "cerrada"
        return None

    def _procesar_gesto(self, gesto: Optional[str]) -> None:
        ahora = time.time()
        if gesto and gesto != self._ultimo_gesto and (ahora - self._ultimo_cambio) > _ENFRIAMIENTO_SEGUNDOS:
            self._ultimo_gesto = gesto
            self._ultimo_cambio = ahora
            if self.callback_gesto:
                self.callback_gesto(gesto)
        elif not gesto and (ahora - self._ultimo_cambio) > _RESET_SIN_MANO_SEGUNDOS:
            self._ultimo_gesto = None
