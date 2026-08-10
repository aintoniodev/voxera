# Specs fase 2 — voxera: todos los tracks/features definidos

> Definición funcional completa de la fase 2 (pivot: *denoiser* → **"voz
> profesional de vídeo"**). Cada track especifica comandos CLI, flags,
> presets, métricas, criterios de aceptación y riesgos. Convertible a
> Gherkin (`features/*.feature`) cuando se implemente cada track.
>
> Regla de oro del proyecto: **todo drivable desde terminal** (CLI = héroe).
> `ims` → `voxera` (rename hecho — Track 0).
>
> **v2 de la spec (2026-08):** se añaden las *fundaciones* que faltaban —
> políticas de audio I/O (sample rate / bit depth / sync), determinismo,
> device policy, SLA de rendimiento, provenance, de-esser especificado,
> breaths/plosives/hum/DC, confidence en estimaciones, noise-type
> classification, benchmark sintético vs real separados y **evaluación
> humana** (Track 8). La métrica definitiva del producto es que alguien
> **prefiera la voz B**.

## Arquitectura diana

```
INPUT ──► ANALYZE ──► ENHANCE ──► VOICE DSP ──► MASTER ──► OUTPUT
(wav/mp4)  VAD          DF2          DC removal    comp      WAV 48 kHz/24-bit
           LUFS         dereverb*    high-pass     de-esser  MP4: vídeo copy
           clipping     declip*      dehum*        limiter   + AAC 192 kbps
           RT60         (*track 5)   EQ vocal      loudnorm
           noise type                presence/air  (-14 LUFS)
           breaths/clicks            (* = opcional)
```

## Semántica de comandos (contrato, sin ambigüedad)

| Comando | Qué hace exactamente |
|---|---|
| `voxera enhance IN -o OUT [--preset X]` | **Restoration + voice mastering**: backend NN (DF2) + pipeline DSP completo. Con `--preset` **siempre** ejecuta el pipeline tras el backend — nunca "solo NN" silenciosamente. Sin `--preset` = solo backend (back-compat). |
| `voxera master IN -o OUT [--preset X]` | **Voice mastering ONLY**: pipeline DSP, sin red neuronal. |
| `voxera analyze IN` | **Analysis ONLY**: no modifica audio, nunca. |
| `voxera score IN [--ref ...]` | **Evaluation ONLY**: métricas, no modifica audio. |
| `voxera silence IN -o OUT` | **Editing ONLY**: silencios/respiraciones/boca. |
| `voxera inspect IN` | Análisis + **recomendación** (pretty wrapper de `analyze`). |

## Convenciones CLI globales

| Flag | Alcance | Comportamiento |
|---|---|---|
| `--device auto\|cpu\|cuda` | analyze/enhance/master/score | Default `auto`: CUDA si disponible, si no CPU. |
| `--seed N` | enhance (NN) | Fija semilla de inferencia (determinismo). |
| `--dry-run` | enhance/master | Imprime el **plan** (análisis + pipeline + esperado) y sale 0 **sin escribir OUT ni cargar la NN**. |
| `--verbose` | todos | Bloque de sistema (ver Track 1A): backend, model, device, torch, RTF. |

### Exit codes

| Código | Significado |
|---|---|
| `0` | OK |
| `1` | Error de procesamiento (EnhancementError) |
| `2` | Error de uso / backend desconocido |
| `20` | **`VOXERA_NO_SPEECH`**: VAD speech ratio < 5% → "No speech detected". `enhance`/`master` abortan sin intentar masterizar como voz; `analyze`/`inspect` siguen funcionando (solo análisis). |

---

## Track 0 — Rename `improve_my_sound`/`ims` → `voxera`

**Estado: hecho** (PR #1 mergeado en master).

| Ámbito | Cambio |
|---|---|
| paquete | `src/improve_my_sound/` → `src/voxera/` (imports, egg-info) |
| CLI | `ims` → `voxera` (PROG, entry point) |
| pyproject | `name = "voxera"`, script `voxera = "voxera.cli:main"` |
| features Gherkin | `ims enhance` → `voxera enhance` |
| tests / acceptance | imports y nombres de comando |
| README + docs | comandos y nombres |

**Criterios:** 70/70 tests con el nombre nuevo; `voxera enhance` exit 0; `ims` ya no existe en `.venv-ims/Scripts`; PR #1 mergeado.
**Riesgo (pendiente):** el editable de `.venv-ims` apuntaba al worktree de rename (ya borrado) → reinstalar `pip install -e .` desde master.

---

## Track 1A — Audio I/O, format policy, device, determinismo, SLA *(nuevo)*

Fundación de audio engineering que congelamos **antes** de tocar el pipeline (evita casos raros con 44.1 kHz, estéreo, bit depths, etc.).

### Sample-rate policy

| Etapa | Política |
|---|---|
| **Input** | WAV 16 / 22.05 / 44.1 / 48 kHz · mono/stereo. Fuera de rango → error claro con el valor leído. |
| **Input vídeo** | Cualquier sample rate del audio extraído — se resamplea a 48 kHz (Track 4). |
| **Internal** | **48 kHz, mono** para enhancement (resample con calidad soxr). |
| **Output WAV** | 48 kHz. |
| **Output vídeo** | Stream de vídeo original + audio 48 kHz (Track 4). |

### Stereo → mono

- Downmix preservando **energía promedio**: `mono = 0.5·(L + R)` (sin clipping por construcción).
- Nunca sumar crudo (puede duplicar amplitud → clipping).

### Bit depth / encoding policy

| Medio | Formato |
|---|---|
| WAV intermedio (temp) | PCM 24-bit o float32 |
| WAV salida | **PCM 24-bit** |
| MP4 salida | **AAC 192 kbps** stereo (`--audio-bitrate` para override) *(propuesta, confirmar)* |

### A/V sync (criterios de vídeo, ver Track 4)

- Drift A/V **≤ 10 ms**.
- Stream de vídeo **bit-identical** (`-c:v copy`).
- El audio empieza en el **timestamp original**; duración de contenedor preservada.

### Determinismo

```
Same input + same backend + same parameters
→ sample-equivalent output (NN) / byte-equivalent (DSP + WAV PCM)
```

- **DSP (master)**: byte-equivalent — pipeline sin NN debe ser reproducible al byte.
- **NN (enhance)**: `--seed` fijo; en CPU objetivo sample-equivalent; en CUDA fijar seed y **documentar** si hay non-determinism (no prometer byte-equivalent donde no lo hay).
- **JSON de analyze/score**: estable para CI — claves ordenadas, floats redondeados a precisión fija, sin UUIDs ni timestamps variables. Única excepción: `processing_time_s` (bloque `system`), que se reporta pero se excluye del diff de estabilidad.

### GPU/CPU device policy

- `--device auto|cpu|cuda`, default `auto` (CUDA disponible → CUDA; si no → CPU).
- En `--verbose`:

```
Backend: DeepFilterNet2
Device: CUDA
Torch:  CUDA 13.x
RTF:    0.071 (model)
```

### Performance budget (SLA)

Se miden y reportan **cuatro RTF separados** — el RTF del modelo solo engaña:

| Nivel | Qué mide | SLA propuesto *(confirmar)* |
|---|---|---|
| model RTF | solo inferencia NN | — |
| pipeline RTF | DSP + I/O + resample | — |
| **end-to-end RTF** | CLI completo | CPU `< 0.5` · CUDA `< 0.1` |
| master RTF | DSP puro, sin NN | `< 0.01` |

### Metadata / provenance (reproducibilidad)

Cada report JSON (`analyze`, `score`) incluye el bloque `system`:

```json
{
  "voxera_version": "0.2.0",
  "backend": "deepfilternet",
  "model": "DeepFilterNet2",
  "model_version": "0.7.0",
  "model_hash": "sha256:ab12…",
  "pipeline_version": "1.3.0",
  "device": "cuda",
  "seed": 0,
  "preset": "youtube",
  "sample_rate": 48000,
  "processing_time_s": 0.72
}
```

**Criterios de aceptación:** política de formatos aplicada en todos los comandos; resample 44.1→48 validado en fixture; JSON byte-estable entre dos ejecuciones con mismo input (excepto `processing_time_s`); `--dry-run` no escribe OUT; exit 20 en fixture sin voz; bloque `system` presente en todo report.

**Riesgo:** determinismo CUDA no garantizable al 100% → documentar en vez de prometer.

---

## Track 1 — `voxera analyze` + `voxera master` (pipeline DSP + presets)

**Objetivo:** el corazón del pivot — la voz sale con calidad de vídeo, no solo sin ruido.

### `voxera analyze IN [-o report.json] [--format tty|json] [--device ...]`

Contrato completo del report (las estimaciones llevan **confidence** — un RT60 sin confidence es engañoso):

```json
{
  "input": {
    "format": "WAV PCM 24-bit", "sample_rate": 48000,
    "channels": 2, "bit_depth": 24, "duration_s": 8.42
  },
  "loudness": {
    "integrated_lufs": -18.2, "short_term_lufs": -15.7,
    "lra": 5.2, "true_peak_db": -2.1, "rms_db": -19.4,
    "clipping_ratio": 0.0002
  },
  "voice": {
    "speech_ratio": 0.71,
    "snr_db": { "value": 13.2, "confidence": 0.83 },
    "intelligibility_proxy": { "value": 0.86, "note": "presence/mud band-ratio — proxy, no STOI" }
  },
  "spectral": {
    "rumble_db": -38,
    "hum_db": { "h50": -32, "h100": -41, "h150": -50, "dominant": "50 Hz" },
    "mud_db": -22, "boxiness_db": -25,
    "presence_db": -18, "air_db": -30
  },
  "room": {
    "rt60_s": 0.42, "confidence": 0.71, "reverb": "medium"
  },
  "artifacts": {
    "dc_offset_db": -70,
    "plosives": { "candidates": 4, "confidence": 0.6 },
    "breaths": { "count": 12, "note": "se preservan por defecto" },
    "mouth_click_candidates": { "count": 17, "confidence": 0.64 },
    "noise_type": {
      "type": "fan", "confidence": 0.82,
      "stationary": true, "broadband": false, "tonal": true
    }
  },
  "system": { "…": "bloque provenance (Track 1A)" }
}
```

| Bloque | Métricas | Cómo |
|---|---|---|
| input | duración, sr, canales, bit depth | headers (soundfile) |
| loudness | LUFS-I / LUFS-S / LRA / RMS / True Peak | EBU R128, pyloudnorm (LRA y RMS también — ver Track 3) |
| loudness | clipping ratio | % muestras ≈ full-scale (numpy) |
| voice | speech ratio | VAD webrtcvad-wheels (30 ms frames) |
| voice | SNR estimado + confidence | energía speech vs silencio (VAD-segmentado) |
| spectral | rumble / mud / boxiness / presence / air | energía por banda (FFT): <70 / 100–300 / 300–600 / 2–5k / 8–14k Hz |
| spectral | **hum 50/100/150 Hz** (separado del rumble) | picos tonales en FFT (numpy) |
| room | RT60 estimado + confidence | decaimiento en silencios post-speech |
| artifacts | **DC offset** | mean(samples) en dBFS |
| artifacts | **plosives candidates** | burst <150 Hz, 10–50 ms, en onset de palabra (P/B/T) |
| artifacts | **breaths** | ver Track 1B (no son transitorios) |
| artifacts | **mouth_click_candidates** (no "mouth_clicks": un transitorio 5–40 ms a 2–6 kHz puede ser consonante/ruido/golpe) | transitorios 5–40 ms, 2–6 kHz, en no-voz |
| artifacts | **noise type** | heurística primero, sin IA (ver Track 1B) |

### `voxera master IN -o OUT [--preset X] [--lufs N] [--no-eq|--no-comp|--no-limit|--no-loudnorm]`

Pipeline determinista (sin NN, ~instantáneo), **orden congelado**:

```
DC removal → high-pass 70 Hz (LR24) → [dehum 50/100/150 Hz opcional]
→ EQ vocal → de-esser → compresor → limiter (-1 dBTP) → loudnorm (target LUFS)
```

- DC removal: bloqueador DC de un polo (o HP 20 Hz) — trivial y evita offsets que rompen métricas.
- `bad-room` usa high-pass 90 Hz (como hoy).
- De-esser: spec completa en Track 1B.
- Con `--dry-run`: imprime el plan (ver abajo) y sale 0.

### Presets (parámetros congelados por preset)

| Preset | LUFS | EQ | Comp | De-ess | Uso |
|---|---|---|---|---|---|
| `creator` | -16 | suave (mud -2) | 2:1, -24 dB | off | Natural + clear (default) |
| `youtube` | -14 | presence +2, air +1 | 2.5:1 | on | Warm + present |
| `podcast` | -16 | mud -3, presence +1 | 3:1 | on | Rich + consistent |
| `social` | -14 | air +2 | 3.5:1, -22 dB | on | Loud + punchy (TT/IG) |
| `bad-room` | -16 | mud -4, boxiness -2 | 2:1 | off | Ruido+eco: DF2 + high-pass 90 Hz |

### `voxera enhance` (extensión)

- `--preset X` → **siempre** backend NN + pipeline DSP completo (default: `creator` si se pasa flag; sin flag = solo backend, back-compat).
- `--dsp-only` → pipeline sin red neuronal (master puro).
- `--dry-run` → plan sin procesar:

```
VOXERA PLAN

Input:
  SNR:       9.2 dB
  LUFS:    -23.4
  Reverb:    high
  Clipping: 0.0%

Pipeline:
  ✓ DeepFilterNet2
  ✓ High-pass 70 Hz
  ✓ Vocal EQ
  ✓ Compressor 2.5:1
  ✓ De-esser
  ✓ Limiter
  ✓ Loudness → -14 LUFS

Expected:
  Noise       ↓↓↓
  Clarity     ↑↑
  Loudness    ↑↑
```

- **auto-select backend** (futuro, con `analyze` + `noise_type`): heavy noise → DF2 (default); clipping+low-BW → aviso "usa restoration (track 5)"; reverb alto → aviso dereverb.

**Criterios de aceptación:** exit 0; out WAV válido (48 kHz / 24-bit); `LUFS_out ∈ target ±1`; `true peak ≤ -1 dBTP`; duración conservada ±0.1 s; banda 100–300 Hz atenuada ≥2 dB en mud-heavy fixture; `|mean(samples)| < -60 dBFS` (DC); determinismo byte-equivalent en DSP; tests unitarios por etapa DSP (filtro, comp, límite, loudnorm, de-esser); JSON estable entre ejecuciones (excepto `processing_time_s`).
**Libs:** `pedalboard` (EQ/comp/limiter), `pyloudnorm` (LUFS), `webrtcvad-wheels` (VAD). Instalar en `.venv-ims`.
**Riesgos:** pedalboard en Windows 3.11 (wheels OK); no destruir la voz (compresión suave, EQ ≤±4 dB, de-esser max 6 dB); validación subjetiva con voz real del usuario (media/test1.wav).

---

## Track 1B — Vocal DSP specification *(nuevo)*

Especificación detallada de las etapas de voz. **Heurísticas primero, medibles y sustituibles** — luego se pueden reemplazar por modelos (RT60 proxy, noise_type, mouth_click_candidates, plosives) sin romper la arquitectura.

### De-esser (spec real, no solo on/off)

| Parámetro | Valor |
|---|---|
| Detection band | **4–10 kHz** |
| Detection | short-term spectral energy (frames ~10 ms) |
| Threshold | por preset (off en `creator`/`bad-room`, on en `youtube`/`podcast`/`social`) |
| Max attenuation | **6 dB** |
| Attack | ~1 ms |
| Release | 50–100 ms |
| Preservación | solo actúa en frames sibilantes; **no toca no-sibilantes HF** (aire/8–14k se mantiene) |

Criterios de no-daño:

```
No degradar > X% la energía 2–5 kHz        (X = 5% propuesto, confirmar)
No introducir artefactos audibles en /s/, /sh/, /ch/  (escucha + fixture)
```

Un de-esser demasiado agresivo hace la voz apagada → el criterio 2–5 kHz es obligatorio en CI.

### Breath detection (separado de transitorios — un breath NO es un transitorio)

```
breath detection:
  low-energy
  broadband
  1–8 kHz
  100–800 ms
  occurs near speech boundaries
```

Handling (flag `--breaths preserve|attenuate|remove` en `silence`):
- **preserve** = default (nunca eliminar respiraciones por defecto — son naturales).
- attenuate = ganancia suave (-6 dB propuesto) · remove = solo con flag explícito.

### Plosives (P/B/T)

- `analyze` → `plosives.candidates + confidence` (burst LF <150 Hz, 10–50 ms, onset de palabra).
- Futuro: **de-plosive** (track 5). Con plosives + de-esser el pipeline vocal queda completo:
  `de-noise → de-reverb → de-plosive → de-esser → EQ → compression → limiting → loudness`.

### Hum / electrical noise (Europa: 50 Hz)

- Hum y rumble son **problemas distintos**: rumble <70 Hz (movimiento/viento) vs hum 50/100/150 Hz (mains/electrical).
- `analyze` detecta los tres armónicos; `master` gana `--dehum` opcional (notch Q estrecho en el/los pico(s) dominantes).
- Si `hum_db` dominante > umbral → sugerencia "usa --dehum" en inspect/dry-run.

### DC offset

- `analyze` → `dc_offset` (mean en dBFS).
- `master`/`enhance` → etapa DC removal (siempre, al inicio del pipeline).
- Aceptación: `abs(mean(samples)) < -60 dBFS` *(umbral propuesto)*.

### Noise type classification (sin IA, heurística inicial)

| Campo | Cómo (heurístico) |
|---|---|
| `tonal` | pico espectral dominante (hum, fan tonal) |
| `stationary` | varianza de energía por frame baja |
| `broadband` | energía plana en banda ancha |
| `type` | `fan · ac · hiss · hum · keyboard · traffic · people · music · stationary · non-stationary · unknown` |

El schema queda **preparado** para IA futura; hoy se clasifica heurísticamente y alimenta el futuro auto-select.

---

## Track 2 — VAD + limpieza de silencio + boca/aire

### `voxera silence IN -o OUT --level light|medium|aggressive [--breaths preserve|attenuate|remove]`
- light: huecos >1.5 s → 0.8 s · medium: >0.8 s → 0.5 s · aggressive: >0.4 s → 0.25 s.
- **Nunca cortar respiraciones**: protección de 200 ms antes/después de speech; los breaths cortos (≤300 ms) no se tocan.
- `--breaths preserve` (default) / `attenuate` / `remove` — según spec 1B.
- Reporta `original 8:42 → cleaned 7:58` en stderr/TTY.

### `voxera analyze` (extensión)
- `breaths: N` (detección por spec 1B, no por transitorios), `mouth_click_candidates: N + confidence`.
- Si `mouth_click_candidates > umbral` → sugerencia "usa de-click (futuro)" o atenuación suave opcional `--declick` en master (band-stop 2–6 kHz en transitorio, ganancia 6 dB).

**Criterios:** duración se reduce en fixture con silencios; voz íntegra (fixture speech continua: duración ±0.1 s, sin cortes); ratio voz/silencio sube; breaths preservados por defecto (fixture con breaths: byte-iguales en la zona de breath).
**Riesgo:** VAD agresivo come inicios suaves de palabra → margen de seguridad obligatorio.

---

## Track 3 — `voxera score` + Voice Score / CVS

### `voxera score IN [-o report.json] [--ref ORIGINAL.wav] [--device ...]`
Desglose 0–100 (el "vende el producto"):

| Dimensión | Proxy factible (DNSMOS roto en este Windows) |
|---|---|
| Noise | SNR estimado vía VAD (0 dB→30, 20 dB→90) |
| Clarity | presence/mud band-ratio (proxy de claridad, **no** inteligibilidad) |
| Loudness | distancia a -14 LUFS (usa LUFS-I + LRA) |
| Room Echo | RT60 estimado (+confidence) |
| Dynamics | crest factor / LRA (loudness range) |

Total = media ponderada → **CVS 0–100** + veredicto `"Your voice is ready for publishing"` (≥80).
Con `--ref`: además **Voice Preservation %** = cosine(speaker_embedding(IN), speaker_embedding(REF)) con resemblyzer → "la voz sigue siendo la misma persona".

### Métricas de producto vs métricas de research (no mezclar)

```
Product metrics (→ Voice Score, UI, Tauri)
    ├── Voice Score / CVS
    ├── Loudness (LUFS-I, LRA, RMS, True Peak)
    ├── SNR
    └── Speaker preservation (solo con --ref)

Research metrics (→ benchmark track 6, nunca en el score de producto)
    ├── PESQ
    ├── STOI
    ├── ESTOI
    ├── SI-SDR
    ├── RTF (model / pipeline / e2e)
    └── DNSMOS (cuando funcione en este Windows; proxy mientras)
```

### Uso clave
`voxera enhance in.wav -o out.wav --preset youtube && voxera score out.wav --ref in.wav`
→ demo vendible: `Voice quality: 74 → 91 · Voice preservation: 98.2%`.

**Criterios:** score sube tras master en fixture ruidosa (test determinista con fixture sintetizada); cosine-sim > 0.95 en voz sin alterar (control); LRA/RMS presentes en el report.
**Libs:** `resemblyzer` (torch ya está).
**Riesgo:** proxies heurísticos ≠ DNSMOS real → documentar; validar subjetivamente con Antonio.

---

## Track 4 — Vídeo directo (ffmpeg ya disponible ✅)

### `voxera enhance video.mp4 -o video_enhanced.mp4`
`ffprobe` detecta vídeo → extraer audio (48 kHz mono WAV temp) → pipeline → reemplazar audio (`-c:v copy` + AAC 192 kbps, Track 1A).

**Criterios (incluye política A/V):**
- out MP4 válido; stream vídeo **bit-identical** (bitstream copy).
- **Drift A/V ≤ 10 ms**; audio empieza en el timestamp original; duración de contenedor preservada.
- Audio = salida del pipeline (48 kHz / AAC 192 kbps).

**Riesgo:** ffmpeg en PATH de Cygwin (ya verificado `/c/ffmpeg/bin/ffmpeg`); paths relativos al proyecto (landmine #6); timestamps de contenedor según input (validar drift siempre, no solo duración).

---

## Track 5 — Dereverb + declipping + restoration (POSTERGA a tracks 1–3)

- **No buscar un 4º denoiser** (consejo explícito). Evaluar: **VoiceFixer** (ruido+reverb+clipping+BW en un modelo), dereverb dedicado.
- `analyze` ya detecta clipping ratio, RT60, plosives y hum → en v2, `enhance` sugiere/usa restoration automáticamente; **de-plosive** y **dehum** entran aquí si se aprueban.
- Evaluación en `.auto` v2 con métricas nuevas ANTES de tocar el producto.

---

## Track 6 — Benchmark `.auto` v2 *(sintético y real SEPARADOS)*

No mezclar "clean artificial + degradación artificial" con audio real como si fueran equivalentes. Dos suites independientes, dos reportes.

### A. Synthetic benchmark (hay ground truth → métricas objetivas)

```text
clean
 + ruido controlado (SNR 0–20 dB)
 + reverb controlado
 + clipping controlado
```

Métricas: **PESQ · STOI · ESTOI · SI-SDR** (+ LUFS-out, true peak, clipping ratio como control).

### B. Real-world benchmark (sin ground truth → métricas de calidad)

```text
mic · phone · webcam · fan · AC · room · street
```

Métricas: **DNSMOS** (cuando funcione en este Windows; proxy mientras) · **speaker-sim** (resemblyzer) · LUFS · RTF (model/pipeline/e2e) · artifact proxy (discontinuidades espectrales / crest anómalo) · **human preference** (Track 8).

### Entregable

Tabla `model × [PESQ, STOI, ESTOI, SI-SDR, DNSMOS-proxy, RTFₘ/RTFₚ/RTFₑ, LUFS, TP, clipping, speaker-sim]` — un reporte por suite, nunca fusionado.

Candidatos: DF2 (baseline) · DF3 · **DF2 + master presets** · DP-DPNet · VoiceFixer (cuando esté).
Dataset: clips reales del usuario (mic/phone/webcam/room/fan/AC…); 30–100 clips ideales.

---

## Track 7 — Tauri desktop (UI thin)

- Sidecar del CLI; **todo lo que renderiza lo genera el CLI** (wavs A/B, JSON de analyze/score).
- Pantalla 1: upload (audio/vídeo) + preset + enhance.
- Pantalla 2: **A/B player** (waveform + división arrastrable ORIGINAL|ENHANCED) — el feature que vende solo.
- Pantalla 3: Voice Score (barras antes/después + "ready for publishing").
- El A/B player standalone (HTML) se reutiliza para la evaluación humana (Track 8) — se puede adelantar en versión mínima.
- Postergado hasta tener Tracks 1–4 sólidos.

---

## Track 8 — Evaluación humana *(nuevo)*

> La métrica definitiva de Voxera: **que alguien prefiera la voz B**.

### Protocolo
- **5–10 oyentes** (Antonio + conocidos; no hace falta ser audiófilos).
- **10–20 clips** de la suite real-world del benchmark (Track 6B).
- Condiciones por clip:
  - A = original
  - B = DF2
  - C = DF2 + master (preset adecuado)
  - D = otro modelo (DF3 / DP-DPNet / comercial tipo Resemble si se evalúa)

### Votación
- **Pairwise preference**: "¿cuál suena mejor?" (A/B/C/D por pares).
- **MOS 1–5** por condición.
- Pares clave: `DF2 vs DF2+master` (¿aporta el master?), `DF2 vs otro modelo`, `DF2+master vs DF3`.
- **Blind + orden aleatorio** (sesgo de orden); auriculares; **todas las condiciones normalizadas al mismo LUFS** antes de escuchar (que no gane "la más fuerte").

### Mecánica
- Player A/B standalone (HTML) del Track 7 o formulario simple; votos a fichero CSV en `.auto/human/`.

### Criterio de aceptación (propuesto)
- `DF2+master` preferido sobre `DF2` en **≥ 60%** de las escuchas *(umbral a confirmar)* → justifica el pipeline de mastering como diferencial.
- Entregable: `% preferencia por par` + `MOS medio por condición` + comentarios libres.

---

## Orden de implementación

```
Track 0 (rename) → Track 1A (fundaciones I/O + determinismo + device)
→ Track 1 (analyze + master, con refinamientos 1B) → Track 3 (score)
→ Track 2 (silence/boca) → Track 4 (vídeo) → Track 6 (benchmark v2)
→ Track 8 (humano) → Track 5 (restoration) → Track 7 (Tauri)
```

**Justificación:** el consejo dice explotar el pipeline alrededor de DF2 antes que nada; score tras master da el loop de validación "escucha + métrica" desde el día 1. 1A se hace antes de 1 porque congela formatos/determinismo que afectan a todo lo demás; 8 necesita a 6 (clips + métricas) y al player de 7. Nota: 1A y 1B son *fundaciones*, no tracks independientes de producto — se implementan dentro de Track 1.

## Decisiones abiertas (para Antonio)

| # | Decisión | Propuesta | Estado |
|---|---|---|---|
| 1 | ¿`creator` como preset por defecto de `enhance --preset`? | `creator`, -16 LUFS | abierta |
| 2 | ¿Target LUFS de `social`: -14 (TikTok/IG reales) confirmado? | -14 | abierta |
| 3 | ¿Voz real para benchmark v2: puede grabar 10–30 clips (mic, phone, room, fan, AC)? | sí | abierta |
| 4 | ~~¿Renombrar el repo a `voxera` o mantener `improve-my-sound` como repo?~~ | repo ya renombrado (`aintoniodev/voxera`) | ✅ resuelta |
| 5 | De-esser: umbral por preset, max att **6 dB**, tolerancia energía 2–5 kHz (**X = 5%**?) | 5% | abierta |
| 6 | Exit codes: rango estable — ¿`VOXERA_NO_SPEECH = 20`? | 20 | abierta |
| 7 | SLA RTF: CPU **< 0.5**, CUDA **< 0.1**, master **< 0.01** | sí | abierta |
| 8 | Salidas: WAV **PCM 24-bit**, MP4 **AAC 192 kbps** (¿o 256?) | 192 | abierta |
| 9 | Breaths: **preservar por defecto**; `--breaths attenuate\|remove` explícito | preservar | abierta |
| 10 | Taxonomía noise type (11 tipos heurísticos) ¿OK? | sí | abierta |
| 11 | ¿De-plosive y dehum en Track 5 o postergar más? | track 5 | abierta |
| 12 | Evaluación humana: ¿quiénes (5–10 personas), cuántos clips (10–20), umbral ≥60%? | sí | abierta |
