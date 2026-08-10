# Specs fase 2 — voxera: todos los tracks/features definidos

> Definición funcional completa de la fase 2 (pivot: *denoiser* → **"voz
> profesional de vídeo"**). Cada track especifica comandos CLI, flags,
> presets, métricas, criterios de aceptación y riesgos. Convertible a
> Gherkin (`features/*.feature`) cuando se implemente cada track.
>
> Regla de oro del proyecto: **todo drivable desde terminal** (CLI = héroe).
> `ims` → `voxera` tras el rename (Track 0).

## Arquitectura diana

```
INPUT ──► ANALYZE ──► ENHANCE ──► VOICE DSP ──► MASTER ──► OUTPUT
(wav/mp4)  VAD       DF2          high-pass     comp      -14 LUFS
           LUFS      dereverb*    EQ vocal      de-esser  limiter
           clipping  declip*      presence/air  *
           RT60      (*track 5)
```

- `enhance` = backend NN + pipeline DSP completo (orquestador).
- `master`/`analyze`/`score`/`silence` = subcomandos especializados.
- Todo backend sigue el registry pluggable existente.

---

## Track 0 — Rename `improve_my_sound`/`ims` → `voxera`

**Estado: en curso** (delegado a subagente en worktree `.worktrees/voxera-rename`, PR → master).

| Ámbito | Cambio |
|---|---|
| paquete | `src/improve_my_sound/` → `src/voxera/` (imports, egg-info) |
| CLI | `ims` → `voxera` (PROG, entry point) |
| pyproject | `name = "voxera"`, script `voxera = "voxera.cli:main"` |
| features Gherkin | `ims enhance` → `voxera enhance` |
| tests / acceptance | imports y nombres de comando |
| README + docs | comandos y nombres |

**Criterios:** 70/70 tests con el nombre nuevo; `voxera enhance` exit 0; `ims` ya no existe en `.venv-ims/Scripts`; PR abierto.
**Riesgo:** el venv editable apunta al worktree hasta el merge → tras merge, reinstalar `pip install -e .` desde master.

---

## Track 1 — `voxera analyze` + `voxera master` (pipeline DSP + presets)

**Objetivo:** el corazón del pivot — la voz sale con calidad de vídeo, no solo sin ruido.

### `voxera analyze IN [-o report.json] [--format tty|json]`

Análisis del audio (toda la información que la "IA" usa para decidir):

| Métrica | Cómo | Fuente |
|---|---|---|
| duración, sr, canales | headers | soundfile |
| LUFS integrado / short-term | EBU R128 | pyloudnorm |
| true peak (dBTP) | oversampling | pyloudnorm |
| clipping ratio | % muestras ≈ full-scale | numpy |
| voice ratio (voz/silencio) | VAD | webrtcvad-wheels (30 ms frames) |
| SNR estimado | energia speech vs silencio (VAD-segmentado) | numpy |
| rumble / mud / boxiness / presence / air | energía por banda (FFT): <70 / 100–300 / 300–600 / 2–5k / 8–14k Hz | numpy |
| RT60 estimado (proxy reverb) | decaimiento en silencios post-speech | numpy |
| breaths / mouth-clicks | transitorios 5–40 ms, 2–6 kHz, en no-voz | numpy |

Salida TTY: tabla humana. Salida JSON: consumible por Tauri/scripts.

### `voxera master IN -o OUT [--preset X] [--lufs N] [--no-eq|--no-comp|--no-limit|--no-loudnorm]`

Pipeline determinista (sin NN, ~instantáneo):
`high-pass 70 Hz (LR24)` → `EQ vocal` → `compresor` → `de-esser` → `limiter (-1 dBTP)` → `loudnorm (target LUFS)`.

### Presets (parámetros congelados por preset)

| Preset | LUFS | EQ | Comp | De-ess | Uso |
|---|---|---|---|---|---|
| `creator` | -16 | suave (mud -2) | 2:1, -24 dB | off | Natural + clear (default) |
| `youtube` | -14 | presence +2, air +1 | 2.5:1 | on | Warm + present |
| `podcast` | -16 | mud -3, presence +1 | 3:1 | on | Rich + consistent |
| `social` | -14 | air +2 | 3.5:1, -22 dB | on | Loud + punchy (TT/IG) |
| `bad-room` | -16 | mud -4, boxiness -2 | 2:1 | off | Ruido+eco: DF2 + high-pass 90 Hz |

### `voxera enhance` (extensión)
- `--preset X` → aplica pipeline DSP tras el backend (default: `creator` si se pasa flag; sin flag = solo backend, back-compat).
- `--dsp-only` → pipeline sin red neuronal (master puro).
- **auto-select backend** (futuro, con `analyze`): heavy noise → DF2 (default); clipping+low-BW → aviso "usa restoration (track 5)"; reverb alto → aviso dereverb.

**Criterios de aceptación:** exit 0; out WAV válido; `LUFS_out ∈ target ±1`; `true peak ≤ -1 dBTP`; duración conservada ±0.1 s; banda de 100–300 Hz atenuada ≥2 dB en mud-heavy fixture; tests unitarios por etapa DSP (filtro, comp, límite, loudnorm).
**Libs:** `pedalboard` (EQ/comp/limiter), `pyloudnorm` (LUFS), `webrtcvad-wheels` (VAD). Instalar en `.venv-ims`.
**Riesgos:** pedalboard en Windows 3.11 (wheels OK); no destruir la voz (compresión suave, EQ ≤±4 dB); validación subjetiva con voz real del usuario (media/test1.wav).

---

## Track 2 — VAD + limpieza de silencio + boca/aire

### `voxera silence IN -o OUT --level light|medium|aggressive`
- light: huecos >1.5 s → 0.8 s · medium: >0.8 s → 0.5 s · aggressive: >0.4 s → 0.25 s.
- **Nunca cortar respiraciones**: protección de 200 ms antes/después de speech; los breaths cortos (≤300 ms) no se tocan.
- Reporta `original 8:42 → cleaned 7:58` en stderr/TTY.

### `voxera analyze` (extensión)
- `breaths: N`, `mouth_clicks: N` (heurística de transitorios, sin modelo).
- Si `mouth_clicks > umbral` → sugerencia "usa de-click (futuro)" o atenuación suave opcional `--declick` en master (band-stop 2–6 kHz en transitorio, ganancia 6 dB).

**Criterios:** duración se reduce en fixture con silencios; voz íntegra (fixture speech continua: duración ±0.1 s, sin cortes); ratio voz/silencio sube.
**Riesgo:** VAD agresivo come inicios suaves de palabra → margen de seguridad obligatorio.

---

## Track 3 — `voxera score` + Voice Score / CVS

### `voxera score IN [-o report.json] [--ref ORIGINAL.wav]`
Desglose 0–100 (el "vende el producto"):

| Dimensión | Proxy factible (DNSMOS roto en este Windows) |
|---|---|
| Noise | SNR estimado vía VAD (0 dB→30, 20 dB→90) |
| Clarity | presence/mud band-ratio |
| Loudness | distancia a -14 LUFS |
| Room Echo | RT60 estimado |
| Dynamics | crest factor / LRA (loudness range) |

Total = media ponderada → **CVS 0–100** + veredicto `"Your voice is ready for publishing"` (≥80).
Con `--ref`: además **Voice Preservation %** = cosine(speaker_embedding(IN), speaker_embedding(REF)) con resemblyzer → "la voz sigue siendo la misma persona".

### Uso clave
`voxera enhance in.wav -o out.wav --preset youtube && voxera score out.wav --ref in.wav`
→ demo vendible: `Voice quality: 74 → 91 · Voice preservation: 98.2%`.

**Criterios:** score sube tras master en fixture ruidosa (test determinista con fixture sintetizada); cosine-sim > 0.95 en voz sin alterar (control).
**Libs:** `resemblyzer` (torch ya está).
**Riesgo:** proxies heurísticos ≠ DNSMOS real → documentar; validar subjetivamente con Antonio.

---

## Track 4 — Vídeo directo (ffmpeg ya disponible ✅)

### `voxera enhance video.mp4 -o video_enhanced.mp4`
`ffprobe` detecta vídeo → extraer audio (48 kHz mono WAV temp) → pipeline → reemplazar audio (`-c:v copy`, sin re-encode de vídeo).

**Criterios:** out MP4 válido; stream vídeo idéntico (bitstream copy); duración igual; audio = salida del pipeline.
**Riesgo:** ffmpeg en PATH de Cygwin (ya verificado `/c/ffmpeg/bin/ffmpeg`); paths relativos al proyecto (landmine #6).

---

## Track 5 — Dereverb + declipping + restoration (POSTERGA a tracks 1–3)

- **No buscar un 4º denoiser** (consejo explícito). Evaluar: **VoiceFixer** (ruido+reverb+clipping+BW en un modelo), dereverb dedicado.
- `analyze` ya detecta clipping ratio y RT60 → en v2, `enhance` sugiere/usa restoration automáticamente.
- Evaluación en `.auto` v2 con métricas nuevas ANTES de tocar el producto.

---

## Track 6 — Benchmark `.auto` v2 (métricas del consejo §14/15)

Extender `measure.py` con: **LUFS-out, true peak, clipping ratio, speaker-sim (resemblyzer), artifact proxy** (discontinuidades espectrales / crest anómalo).
Candidatos: DF2 (baseline) · DF3 · **DF2 + master presets** · DP-DPNet · VoiceFixer (cuando esté).
Dataset: clips reales del usuario (mic/phone/webcam/room/fan/AC…) × SNR 0–20 dB sintéticos; 30–100 clips ideales.
Entregable: tabla `model × PESQ/STOI/SI-SNR/DNSMOS-proxy/RTF/LUFS/TP/speaker-sim` + decisión empírica.

---

## Track 7 — Tauri desktop (UI thin)

- Sidecar del CLI; **todo lo que renderiza lo genera el CLI** (wavs A/B, JSON de analyze/score).
- Pantalla 1: upload (audio/vídeo) + preset + enhance.
- Pantalla 2: **A/B player** (waveform + división arrastrable ORIGINAL|ENHANCED) — el feature que vende solo.
- Pantalla 3: Voice Score (barras antes/después + "ready for publishing").
- Postergado hasta tener Tracks 1–4 sólidos.

---

## Orden de implementación

```
Track 0 (rename, en curso vía PR) → Track 1 (analyze+master) → Track 3 (score)
→ Track 2 (silence/boca) → Track 4 (vídeo) → Track 6 (benchmark v2) → Track 5 → Track 7
```

**Justificación:** el consejo dice explotar el pipeline alrededor de DF2 antes que nada; score tras master da el loop de validación "escucha + métrica" desde el día 1.

## Decisiones abiertas (para Antonio)

1. ¿`creator` como preset por defecto de `enhance --preset`? (default propuesto: `creator`, -16 LUFS)
2. ¿Target LUFS de `social`: -14 (TikTok/IG reales) confirmado?
3. ¿Voz real para benchmark v2: puede grabar 10–30 clips (mic, phone, room, fan, AC)?
4. ¿Renombrar el repo a `voxera` o mantener `improve-my-sound` como repo y `voxera` como paquete/marca?
