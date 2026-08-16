# Natasha — HUD cyberpunk estilo JARVIS con Gemini

Arquitectura modular en 4 partes + gestos por cámara:

| Parte | Archivo | Rol |
|---|---|---|
| Motor | `motor_gemini.py` | Gemini + function calling decide qué acción/habilidad ejecutar |
| Memoria | `memoria_boveda.py`, carpeta `boveda/` | Bóveda local de Markdown estilo Obsidian |
| Voz | `voz_local.py` | STT local (faster-whisper) + TTS local (pyttsx3), con nivel de volumen en vivo |
| Gestos | `gestos.py` | Cámara + MediaPipe: mano abierta = pantalla completa, puño = minimizar |
| HUD | `hud.py` | Panel único cyberpunk: esfera 3D amarilla, estado del canal, métricas, agenda, log |

`natasha.py` es el punto de entrada que conecta todas las partes.
`sistema_control.py` y `acciones.py` son las funciones reales que Gemini
puede invocar (abrir/cerrar apps, crear carpetas, leer/escribir la bóveda,
ejecutar habilidades). `skills/*.md` son las habilidades de un solo
propósito.

## 1. Instalación

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env
```

`sounddevice` necesita PortAudio (suele venir en el wheel de pip en
Windows). `mediapipe`/`opencv-python` son opcionales: si no los
instalas, todo lo demás sigue funcionando y solo se desactiva el
reconocimiento de gestos (el HUD lo indica con "GESTOS: ○NO DISPONIBLE").

Natasha ahora carga automáticamente un archivo `.env` en la raíz del
proyecto, así que no necesitas exportar variables manualmente en cada
sesión.

## 2. Conectar Gemini (Motor)

1. Crea una API key gratuita en https://aistudio.google.com/apikey
2. Copia `.env.example` a `.env` y pega tu clave:

```bash
GEMINI_API_KEY=tu_clave_aqui
NATASHA_GEMINI_MODEL=gemini-2.5-flash
```

Sin `GEMINI_API_KEY`, Natasha sigue funcionando en modo local: reconoce
órdenes directas de abrir/cerrar apps, crear carpetas y ejecutar
habilidades por nombre, pero sin conversación libre.

Si prefieres usar variables del sistema, también funciona:

```bash
setx GEMINI_API_KEY "tu_clave_aqui"
setx NATASHA_GEMINI_MODEL "gemini-2.5-pro"
```

## 3. Conectar Google Calendar (opcional, para `plan_hoy`)

1. Crea un proyecto en https://console.cloud.google.com/ y habilita la
   API de **Calendar**.
2. Genera credenciales OAuth de tipo "Aplicación de escritorio" y
   descarga el archivo como `credentials.json` en esta misma carpeta.
3. La primera vez que ejecutes `plan_hoy`, Natasha abrirá el navegador
   para que autorices el acceso. Después reutiliza `token.pickle`.

Opcionalmente, puedes definir rutas personalizadas en `.env`:

```bash
NATASHA_GOOGLE_CREDENTIALS=C:\ruta\hacia\credentials.json
NATASHA_GOOGLE_TOKEN=C:\ruta\hacia\token.pickle
```

Sin esto, `plan_hoy` arma el plan solo con las notas de la bóveda y lo
avisa explícitamente.

## 4. Ejecutar

```bash
python natasha.py
```

**Voz:** mantén presionada la **barra espaciadora** para hablar
(push-to-talk); suéltala para que Natasha transcriba y ejecute la
orden. La esfera amarilla crece y se encoge en tiempo real según el
volumen de tu voz mientras el micrófono está activo.

Ejemplos:
- "Abre Google" / "Abre la calculadora"
- "Cierra el bloc de notas"
- "Crea una carpeta llamada Proyectos en el escritorio"
- "Natasha, plan de hoy"
- "Escanea tendencias"

**Gestos:** pulsa "◉ ACTIVAR CÁMARA DE GESTOS" en el HUD.
- ✋ Mano abierta → la ventana pasa a pantalla completa.
- ✊ Puño cerrado → la ventana se minimiza.
- `Esc` sale de pantalla completa manualmente.

El video de la cámara se procesa cuadro a cuadro en memoria y nunca se
guarda ni se envía a ningún servidor — todo el reconocimiento ocurre en
tu equipo.

## 5. La bóveda (Memoria)

```
boveda/
  raw/       -> capturas e insumos sin procesar
  wiki/      -> conocimiento depurado y notas vinculadas
  outputs/   -> lo que Natasha genera (planes, reportes)
```

Carpeta de Markdown plano: puedes abrirla directamente como bóveda en
Obsidian para navegar los enlaces `[[...]]` y el grafo de notas.

## 6. Agregar nuevas habilidades

Crea `skills/mi_habilidad.md`:

```markdown
---
nombre: mi_habilidad
descripcion: Qué hace, en una frase.
---

# Instrucciones para Gemini sobre cómo ejecutar esta habilidad...
```

Natasha la detecta sola al reiniciar. Si necesita datos de la bóveda o
de Calendar, agrega la lógica de contexto en `acciones.py` →
`ejecutar_habilidad()`.

## 7. Comprobación rápida

Con `.env` configurado y dependencias instaladas:

```bash
python natasha.py
```

Si `GEMINI_API_KEY` está bien cargada, Natasha dejará el modo local y
podrá ejecutar habilidades con generación completa. Si `plan_hoy`
sigue diciendo que Calendar no está conectado, revisa la ubicación de
`credentials.json` o configura `NATASHA_GOOGLE_CREDENTIALS` en `.env`.

## Próximos pasos sugeridos

1. **Más gestos** (ej. mano señalando = ejecutar última habilidad,
   palma hacia abajo = silenciar TTS).
2. **Palabra de activación** para evitar procesar diálogo de fondo por
   error mientras se mantiene ESPACIO.
3. **Confirmación antes de cerrar apps** con posible trabajo sin
   guardar (Word, Excel).
4. **Indicador visual del canal de gestos** en el HUD (mini vista de
   cámara o solo un punto de estado) para saber si te está viendo bien.
