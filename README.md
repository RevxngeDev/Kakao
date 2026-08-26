# Kakao

**Real-time translated subtitles for any audio playing on your PC.**

Kakao captures whatever your computer is playing — YouTube, a lecture, a video call,
a film — and shows translated subtitles on a transparent overlay floating above it.
It works whether or not the source has subtitles available.

🇬🇧 English · [🇪🇸 Español](#kakao-español)

> **Status:** working MVP, in daily use by its author. Windows only. Not packaged as
> an `.exe` yet, so it is launched from a terminal. Single user — not distributed.

---

## What it does

- Captures the **system output** (what you hear) and translates it live.
- Renders subtitles on a **transparent, always-on-top, click-through** overlay —
  you can still click, pause and scrub the video *through* the subtitles.
- Runs **fully offline** on your own GPU. No API keys, no cloud, no account.
- Controlled from a **system-tray icon**: start/stop, device, model, sync, font.

## What it does NOT do

- **It never opens the microphone.** Only the system output endpoint. This is a
  hard guarantee, enforced in the design and by an automated test — not a setting.
- No recording, no history, no `.srt` export, no speaker identification.
- Not a transcriber: same-language captions are not the product (Windows and
  YouTube already do that).
- Windows only for now. macOS is anticipated in the design but not implemented.

## Requirements

| | |
|---|---|
| OS | Windows 10/11 |
| GPU | NVIDIA with CUDA — developed and measured on a **GTX 1650 (4 GB)** |
| Python | 3.11+ |
| Tooling | [uv](https://docs.astral.sh/uv/) |

Model weights (Whisper + Silero VAD) download automatically on first use and are
cached by HuggingFace.

## Install

```bash
uv sync
```

## Usage

```bash
uv run python -m kakao.app
```

A tray icon appears in about a third of a second, and the models load in the
background. When the "Listo para traducir" notification shows, **right-click the
tray icon → Iniciar** and play your video.

| Tray action | What it does |
|---|---|
| **Iniciar / Detener** | Start or stop translating |
| **Editar posición** | Move/resize the subtitle box — drag or arrow keys, `Esc` to finish |
| **Ajustes…** | Output device, model, sync preset, font size |
| **Salir** | Quit |

**Ctrl+Alt+K** toggles start/stop from anywhere, without going to the tray. If
another app already owns that combination, Kakao says so at startup instead of
silently losing the shortcut.

Settings persist in `%APPDATA%/Kakao/settings.json`.

### Models

`Ajustes…` offers `small`, `medium` (default) and `large-v3`. Bigger is **not**
reliably better here: on the clips measured, `large-v3` cost ~1 GB more VRAM and
did not translate better than `medium`. It is offered so you can judge it on your
own content.

### Sync presets

Live *translation* is never instant — a phrase must be heard in full before it can
be translated. The preset controls that trade-off:

| Preset | Cut at | Effect |
|---|---|---|
| Más rápido | 4 s | Subtitles sooner, long sentences split more |
| **Equilibrado** (default) | 6 s | Balanced |
| Más preciso | 15 s | Best phrasing, more delay on long sentences |

### Headless mode

```bash
uv run python -m kakao.console 10
```

Same pipeline, subtitles printed to the console with their lag — useful for testing.

## How it works

```
System audio (output endpoint)
        │
  ┌─────▼─────┐
  │AudioSource│  WASAPI loopback — the only OS-specific layer.
  └─────┬─────┘  Resamples + downmixes; emits device-change events.
        │  PCM float32, 16 kHz, mono, timestamped
  ┌─────▼─────┐
  │  Buffer   │  Bounded queue. Under pressure it DROPS the oldest chunk —
  └─────┬─────┘  a subtitle 30 s late is worse than no subtitle.
        │
  ┌─────▼─────┐
  │    VAD    │  Silero. Cuts on silence with overlap, so a chunk boundary
  └─────┬─────┘  never splits a word.
        │
  ┌─────▼─────┐
  │    ASR    │  faster-whisper / CTranslate2, int8. ONE hop: audio → English.
  └─────┬─────┘  Rolling context, repetition + hallucination filtering.
        │
  ┌─────▼─────┐
  │  Overlay  │  PySide6. Transparent, always on top, no focus steal,
  └───────────┘  click-through.
```

Inference runs in its own thread and never blocks capture. Audio and inference
never touch the GUI directly — everything crosses into Qt through signals.

## Measured performance

All figures measured on the actual **GTX 1650 (4 GB)**, not quoted from benchmarks.

| | |
|---|---|
| Model | `medium`, int8, `beam_size=1` |
| Real-time factor | **0.10** (~10× faster than real time) |
| VRAM | ~1510 MB peak, leaving ~2.5 GB headroom |
| Tray ready after launch | **0.32 s** |
| First *Iniciar* (after preload) | **0.02 s** |
| Subtitle lag (phrase end → screen) | **0.1–0.3 s**, stable over a 10-minute run |

## Known limitations

Stated plainly rather than hidden:

- **Output is English only.** Whisper's translation task produces English and
  nothing else; another target language requires a second translation stage.
- **The source language is currently pinned to Spanish** for stability. It is a
  config value, not a redesign.
- **Whispered or very quiet speech is missed** by the VAD, and neither threshold
  nor gain recovers it.
- **Sung music gets garbled** — it passes the VAD as speech and the model mangles it.
- **~0.5 s of dead air** when you switch audio device mid-playback. Most of it is
  Windows re-routing the endpoint; capture recovers automatically.
- **Individual words are still mistranslated** sometimes, and occasionally a whole
  phrase is invented. This is the main open problem. Importantly, these are
  **confident** errors — the model reports normal confidence while being wrong — so
  filtering by confidence does not catch them (measured, not assumed). Five
  approaches have been tried against it and four made things worse; see
  `docs/research/` and DECISIONS.md.
- **No `.exe` yet** — launching needs a terminal.

## Development

```bash
uv run pytest          # 58 tests
uvx ruff check src tests
```

```
src/kakao/
├── config.py      single source of truth for defaults
├── audio/         AudioSource contract + WASAPI impl (only OS-specific code)
├── vad.py         Silero segmentation
├── buffer.py      bounded drop-oldest queue
├── asr.py         translation engine
├── pipeline.py    wiring + lag instrumentation
├── overlay.py     transparent subtitle window
├── hotkey.py      system-wide Ctrl+Alt+K (Win32, platform-guarded)
├── settings.py    JSON settings
├── ui.py          tray + settings dialog
├── app.py         entry point
└── console.py     headless runner
```

A test enforces the portability rule: **nothing outside `src/kakao/audio/` may
import a Windows-specific library**, so the macOS port stays a one-class job.

## License

Private project, not distributed.

---
---

# Kakao (Español)

**Subtítulos traducidos en tiempo real para cualquier audio que suene en tu PC.**

Kakao captura lo que esté reproduciendo tu ordenador — YouTube, una clase, una
videollamada, una película — y muestra subtítulos traducidos en una superposición
transparente que flota encima. Funciona tenga o no subtítulos el original.

[🇬🇧 English](#kakao) · 🇪🇸 Español

> **Estado:** MVP funcional, en uso diario por su autor. Solo Windows. Todavía no
> está empaquetado como `.exe`, así que se lanza desde una terminal. Un solo
> usuario — no se distribuye.

---

## Qué hace

- Captura la **salida de audio del sistema** (lo que oyes) y lo traduce en vivo.
- Dibuja los subtítulos en una superposición **transparente, siempre encima y
  atravesable por el ratón** — puedes hacer clic, pausar y mover el vídeo *a través*
  de los subtítulos.
- Funciona **totalmente sin conexión**, en tu propia GPU. Sin claves de API, sin
  nube, sin cuentas.
- Se controla desde un **icono en la bandeja del sistema**: iniciar/detener,
  dispositivo, modelo, sincronización y tamaño de letra.

## Qué NO hace

- **Nunca abre el micrófono.** Solo el punto de salida del sistema. Es una garantía
  férrea, respaldada por el diseño y por un test automático — no es una casilla.
- No graba, no guarda historial, no exporta `.srt`, no identifica hablantes.
- No es un transcriptor: los subtítulos en el mismo idioma no son el producto
  (Windows y YouTube ya hacen eso).
- Solo Windows por ahora. macOS está previsto en el diseño, pero no implementado.

## Requisitos

| | |
|---|---|
| Sistema | Windows 10/11 |
| GPU | NVIDIA con CUDA — desarrollado y medido en una **GTX 1650 (4 GB)** |
| Python | 3.11+ |
| Herramientas | [uv](https://docs.astral.sh/uv/) |

Los pesos de los modelos (Whisper + Silero VAD) se descargan solos la primera vez y
quedan en la caché de HuggingFace.

## Instalación

```bash
uv sync
```

## Uso

```bash
uv run python -m kakao.app
```

El icono de la bandeja aparece en unas décimas de segundo y los modelos se cargan en
segundo plano. Cuando salga el aviso «Listo para traducir», **clic derecho en el
icono → Iniciar** y pon tu vídeo.

| Acción de la bandeja | Qué hace |
|---|---|
| **Iniciar / Detener** | Empezar o parar la traducción |
| **Editar posición** | Mover/redimensionar la caja de subtítulos — arrastra o usa las flechas, `Esc` para terminar |
| **Ajustes…** | Dispositivo de salida, modelo, sincronización, tamaño de letra |
| **Salir** | Cerrar la aplicación |

**Ctrl+Alt+K** inicia y detiene desde cualquier sitio, sin ir a la bandeja. Si otra
aplicación ya usa esa combinación, Kakao te avisa al arrancar en vez de quedarse sin
atajo en silencio.

Los ajustes se guardan en `%APPDATA%/Kakao/settings.json`.

### Modelos

En `Ajustes…` puedes elegir `small`, `medium` (por defecto) y `large-v3`. Más grande
**no** es fiablemente mejor aquí: en los clips medidos, `large-v3` costó ~1 GB más de
VRAM y no tradujo mejor que `medium`. Se ofrece para que lo juzgues con tu contenido.

### Modos de sincronización

La *traducción* en vivo nunca es instantánea: hay que oír la frase entera antes de
poder traducirla. El modo controla ese equilibrio:

| Modo | Corta a los | Efecto |
|---|---|---|
| Más rápido | 4 s | Subtítulos antes, parte más las frases largas |
| **Equilibrado** (por defecto) | 6 s | Equilibrio |
| Más preciso | 15 s | Mejor redacción, más retraso en frases largas |

### Modo consola

```bash
uv run python -m kakao.console 10
```

El mismo pipeline, con los subtítulos impresos en consola junto a su retraso — útil
para hacer pruebas.

## Cómo funciona

```
Audio del sistema (salida)
        │
  ┌─────▼─────┐
  │AudioSource│  Loopback WASAPI — la única capa específica del sistema.
  └─────┬─────┘  Remuestrea y mezcla a mono; avisa de cambios de dispositivo.
        │  PCM float32, 16 kHz, mono, con marca de tiempo
  ┌─────▼─────┐
  │  Búfer    │  Cola acotada. Bajo presión DESCARTA lo más viejo: un subtítulo
  └─────┬─────┘  con 30 s de retraso es peor que ningún subtítulo.
        │
  ┌─────▼─────┐
  │    VAD    │  Silero. Corta en los silencios con solape, para que ninguna
  └─────┬─────┘  frontera parta una palabra por la mitad.
        │
  ┌─────▼─────┐
  │    ASR    │  faster-whisper / CTranslate2, int8. UN solo salto: audio → inglés.
  └─────┬─────┘  Contexto entre frases, filtro de repeticiones y alucinaciones.
        │
  ┌─────▼─────┐
  │ Overlay   │  PySide6. Transparente, siempre encima, sin robar el foco,
  └───────────┘  atravesable por el ratón.
```

La inferencia corre en su propio hilo y nunca bloquea la captura. Ni el audio ni la
inferencia tocan la interfaz directamente: todo cruza hacia Qt mediante señales.

## Rendimiento medido

Todas las cifras están **medidas en la GTX 1650 (4 GB) real**, no copiadas de tablas
de referencia.

| | |
|---|---|
| Modelo | `medium`, int8, `beam_size=1` |
| Factor de tiempo real | **0.10** (~10× más rápido que el tiempo real) |
| VRAM | ~1510 MB de pico, dejando ~2.5 GB libres |
| Bandeja lista tras abrir | **0.32 s** |
| Primer *Iniciar* (tras la precarga) | **0.02 s** |
| Retraso del subtítulo (fin de frase → pantalla) | **0.1–0.3 s**, estable durante 10 minutos |

## Limitaciones conocidas

Dichas claramente, en vez de escondidas:

- **La salida es solo en inglés.** La tarea de traducción de Whisper produce inglés
  y nada más; cualquier otro idioma de destino exige una segunda etapa de traducción.
- **El idioma de origen está fijado a español** por estabilidad. Es un valor de
  configuración, no un rediseño.
- **La voz susurrada o muy baja se pierde** en el VAD, y ni bajar el umbral ni subir
  la ganancia la recuperan.
- **La música cantada sale destrozada**: el VAD la deja pasar como voz y el modelo la
  interpreta mal.
- **~0.5 s de silencio** al cambiar de dispositivo de audio a mitad de reproducción.
  La mayor parte es Windows redirigiendo la salida; la captura se recupera sola.
- **Algunas palabras sueltas todavía se traducen mal**, y de vez en cuando se inventa
  una frase entera. Es el problema abierto principal. Y algo importante: son errores
  **confiados** — el modelo reporta confianza normal mientras se equivoca —, así que
  filtrar por confianza no los detecta (medido, no supuesto). Se han probado cinco
  enfoques y cuatro empeoraron las cosas; ver `docs/research/` y DECISIONS.md.
- **Aún no hay `.exe`**: hay que lanzarlo desde una terminal.

## Desarrollo

```bash
uv run pytest          # 58 tests
uvx ruff check src tests
```

```
src/kakao/
├── config.py      única fuente de verdad de los valores por defecto
├── audio/         contrato AudioSource + implementación WASAPI (único código del SO)
├── vad.py         segmentación con Silero
├── buffer.py      cola acotada que descarta lo más viejo
├── asr.py         motor de traducción
├── pipeline.py    orquestación + medición del retraso
├── overlay.py     ventana transparente de subtítulos
├── hotkey.py      atajo global Ctrl+Alt+K (Win32, con guarda de plataforma)
├── settings.py    ajustes en JSON
├── ui.py          bandeja + ventana de ajustes
├── app.py         punto de entrada
└── console.py     ejecución sin interfaz
```

Un test hace cumplir la regla de portabilidad: **nada fuera de `src/kakao/audio/`
puede importar una librería específica de Windows**, para que llevarlo a macOS siga
siendo cuestión de escribir una sola clase.

## Licencia

Proyecto privado, no distribuido.
