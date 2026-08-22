# SPECS fase 3 — mejora de vídeo vertical (9:16)

**Estado:** implementado y validado (2026-08-12) · **CLI:** `voxera video` · **UI:** `ui/video.html`

## 1. Decisión de modelo (registro)

AB humano en vídeo a 30 fps (2 contenidos: talking-head 720p `long1` y walking/animación 1080p `mid`):

| Modelo | Veredicto usuario | Velocidad 720p | Velocidad 1080p |
|---|---|---|---|
| **`animevideov3`** | ✅ **DEFAULT** (ganador) | 0.85 fps | 0.39 fps |
| `x4plus` | descartado (sobre-afilado en AB rápido) | 0.12 fps | 0.04 fps |

El "embellecimiento/halo" inicial de animevideov3 (filtro de belleza típico de modelos anime) fue
**aceptado por el usuario en vídeo** — en movimiento gana a x4plus en calidad percibida, y es
~7-10× más rápido. `x4plus` queda como escape `--model x4plus` (más textura, batch largo).

## 2. Contrato de pipeline

```
input (9:16 vertical) → ffprobe → frames PNG (ffmpeg, fps objetivo)
                       → RealESRGANer CUDA (tile=512, fp16, outscale=2 interno x4)
                       → scale lanczos a 1080×1920 → x264 CRF18 yuv420p
                       → audio: original remux (AAC 192k) | --master-audio: voxera master PRESET
                       → + still comparativo OUT.compare.png (izq fuente escalada · der mejorado)
```

- **Hardware:** CUDA obligatoria (CPU = ~67× realtime, `EnhancementError` explícito).
- **Salida por defecto:** 1080×1920 @30 fps (los 60 fps de origen se convierten a 30 — estándar
  de redes; `--fps 60` duplica el tiempo).
- **Un solo default, sin menú de presets** (decisión usuario): flags de escape `--model`,
  `--fps`, `--master-audio [PRESET]`, `--crf`, `--tile`, `--no-half`, `--keep-frames`.
- **`--dry-run`** → `VOXERA PLAN (video)` con estimación de tiempo (tabla medida RTX 2060),
  sin cargar NN ni escribir nada.
- **`voxera video compare A B -o OUT [--source ORIG]`** → AB de 2/3 paneles (herramienta de
  evaluación, mismo flujo que los AB usados para la decisión).

## 3. Medidas (RTX 2060 6 GB, esta máquina)

| Caso | Modelo | fps medido | Tiempo |
|---|---|---|---|
| long1 55 s @720p→1080p | animevideov3 | 0.85 | 33 min |
| long2 60 s @720p→1080p | animevideov3 | 0.63 (throttling térmico) | 48 min |
| mid 26 s @1080p | animevideov3 | 0.39 | 43 min |
| x4plus @720p / @1080p | x4plus | 0.12 / 0.04 | ~10× |

Throttling: tras ~1 h de GPU continua la 2060 cae ~25% (long2 0.63 vs long1 0.85). Batch asumible
(≈1 h de cómputo por minuto de vídeo con el default).

## 4. CLI contract

```
voxera video info IN                                → JSON: width/height/fps/duration/codec/bitrate/has_audio
voxera video enhance IN -o OUT [flags]              → exit 0 + ✓ OUT; 1 error; 2 uso
voxera video compare A B -o OUT [--source S] [...]  → AB 2/3 paneles
```

Exit codes consistentes con fase 2 (0/1/2). Líneas `[tag]` en stdout (machine-parseable para la UI).

## 5. Web UI

`ui/server.py` (stdlib, sin deps) + `ui/video.html`:

- `POST /api/video/jobs` (multipart: file, model, fps, master) → job asíncrono
  (`voxera video enhance` en thread, subprocess, stdout parseado: `[extract] N` y `[enhance] i/n`).
- `GET /api/video/jobs/<id>` → status/progress/log/output_url.
- `GET /media/<file>` → outputs (content-type por extensión; bug binario multipart corregido:
  `rsplit(\r\n,2)` cortaba mp4 con CRLF internos → `_file_body()` corta en `\r\n--boundary`).

## 6. Env y pesos

- Venv: `.venv-video` (torch 2.3.1+cu121, realesrgan, gfpgan no usado aún, opencv, numpy<2,
  voxera editable `-e ".[video]"`).
- Pesos en `models/video/` (gitignored): `realesr-animevideov3.pth` (2.5 MB) +
  `RealESRGAN_x4plus.pth` (67 MB) — URLs en README. Override: `VOXERA_VIDEO_MODELS`.
- Pitfall documentado: desinstalar `webrtcvad` (fuente, roto en Windows) tras el editable install.

## 7. Pendientes (roadmap)

- Restauración facial temporal (GFPGAN + suavizado tipo TCN) para talking-heads — añade flicker,
  requiere suavizado (evidencia RFV-LQ).
- Protección de regiones de texto (`--text-safe`) para tutoriales/captions.
- Conversión 16:9→9:16 (outpainting difusivo) — descartada por decisión de producto (entrada 9:16 nativa).
- Tauri desktop con `voxera video` (toolchain Rust pendiente).
