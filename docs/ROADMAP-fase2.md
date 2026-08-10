# Roadmap fase 2 — de "denoiser" a "voz profesional de vídeo"

> Síntesis ejecutable de la estrategia revisada (2026-08-10). Pivot de producto:
> **no** construir una app de *denoising* → construir *"haz que mi voz grabada
> suene como una voz profesional de vídeo"*. Encaja con el tagline:
> **"Sound like you, only better."**

## Lo que el consejo pide y ya está hecho (no repetir)

| Consejo | Estado en repo |
|---|---|
| §3 probar DeepFilterNet3 | ✅ Ya evaluado: 3.268 pesq @ 0.225 rtf → **no gana** a DF2 (3.275 @ 0.084). En `.auto/log.jsonl`. |
| §19 mantener DF2 como default + backends modulares | ✅ Ya hecho (registry pluggable, `--backend/--model`). |
| §14 benchmark propio multi-métrica | ◐ Hecho parcial: PESQ/STOI/SI-SNR/RTF sobre testset ES+EN sintetizado (`.auto/`). Faltan: LUFS, True Peak, speaker similarity, artifact score. |
| §15/16 DNSMOS como métrica | ⚠️ **DNSMOS/UTMOS rotos en este Windows** (fairseq/speechmos — landmine #4). Alternativas factibles: speaker similarity (resemblyzer), LUFS/true-peak (pyloudnorm), heurísticas. |

## Arquitectura objetivo (4 etapas)

```
INPUT ──► ANALYZE ──► ENHANCE ──► VOICE DSP ──► MASTER ──► OUTPUT
 (wav/mp4)  VAD       DF2          EQ vocal     compresor     -14 LUFS
            SNR       dereverb?    de-esser    limiter
            LUFS      (futuro)     high-pass
            clipping  restoration  presence/air boost
```

## Tracks (orden sugerido — primero el pipeline, luego el "producto")

### 🟢 Track 1 — `ims master`: pipeline DSP alrededor de DF2 *(alto valor, bajo riesgo)*
1. `ims analyze in.wav` → JSON/TTY: duración, VAD (voz/silencio), LUFS integrado,
   true peak, clipping ratio, SNR estimado, frecuencias problemáticas (mud/boxiness).
2. Pipeline post-denoise en `src/improve_my_sound/dsp/` (pyloudnorm + pedalboard):
   high-pass (rumble <70 Hz) → EQ vocal (reduce mud 100–300, boxiness 300–600,
   presence 2–5k, air 8–14k) → compresor suave → limiter → loudness -14 LUFS.
3. Presets de voz: `--preset creator|youtube|podcast|social|bad-room`.
4. `ims enhance --preset youtube` → DF2 + pipeline completo.
- Libs: `pedalboard` (EQ/comp/limiter, wheels Windows), `pyloudnorm` (LUFS).

### 🟡 Track 2 — VAD + limpieza de silencio + boca/aire
- `webrtcvad-wheels` (VAD ligero) o silero-vad (torch ya está).
- `ims silence in.wav --level light|medium|aggressive` → recorta huecos.
- Detección de mouth-clicks/breaths (heurística de transitorios) → score en analyze.

### 🟡 Track 3 — Voice Score / "ready for publishing"
- Métricas post-pipeline: LUFS, true peak, clipping, SNR, **speaker similarity**
  (resemblyzer: cosine(embedding(original), embedding(enhanced)) → "voice preservation %").
- `ims score in.wav` → desglose 0–100 estilo "Noise/Clarity/Loudness/Room/Dynamics"
  + CVS compuesto. Validación subjetiva del usuario.

### 🟡 Track 4 — Vídeo directo (ffmpeg ya disponible)
- `ims enhance video.mp4 -o video_enhanced.mp4`: extraer audio → DF2 → reemplazar.
- Cero fricción para creadores ("drop your video").

### 🔴 Track 5 — Rename a `voxera`
- Paquete `improve_my_sound`→`voxera`, CLI `ims`→`voxera`, README, pyproject.
- **Decidir alcance con el usuario** (rompe compatibilidad del CLI actual).

### 🔴 Track 6 — Dereverb, declipping, VoiceFixer/ClearerVoice
- Solo después de Tracks 1–3 (el consejo: no buscar un 4º denoiser todavía).

### 🔴 Track 7 — UI Tauri (A/B player, waveform, sliders)
- El CLI genera todo (wavs A/B, métricas); Tauri = envoltura thin. Más adelante.

## Benchmark ampliado (.auto v2)
- Añadir al measure: LUFS-out, true-peak, clipping ratio, speaker-sim
  (cosine resemblyzer), "distancia espectral" como proxy de artefactos.
- Ideal: 30–100 grabaciones reales del usuario (mic/phone/webcam/room/fan/AC…)
  con degradaciones SNR 0–20 dB (consejo §14).

## Decisiones abiertas para Antonio
1. ¿Qué track ejecutar primero? (recomendado: Track 1 — es el corazón del pivot)
2. ¿Rename a voxera ya o al final de la fase 2?
3. ¿Instalar pedalboard/pyloudnorm/webrtcvad/resemblyzer en `.venv-ims`? (sí recomendado)
