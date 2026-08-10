# Roadmap fase 2 — de "denoiser" a "voz profesional de vídeo"

> Síntesis ejecutable de la estrategia revisada (2026-08-10, actualizada tras la
> revisión de la spec v2). Pivot de producto: **no** construir una app de
> *denoising* → construir *"haz que mi voz grabada suene como una voz profesional
> de vídeo"*. Encaja con el tagline: **"Sound like you, only better."**
>
> Detalle completo por track, criterios de aceptación y decisiones abiertas:
> **`docs/SPECS-fase2.md`** (v2: fundaciones de audio engineering + evaluación).

## Lo que el consejo pide y ya está hecho (no repetir)

| Consejo | Estado en repo |
|---|---|
| §3 probar DeepFilterNet3 | ✅ Ya evaluado: 3.268 pesq @ 0.225 rtf → **no gana** a DF2 (3.275 @ 0.084). En `.auto/log.jsonl`. |
| §19 mantener DF2 como default + backends modulares | ✅ Ya hecho (registry pluggable, `--backend/--model`). |
| §14 benchmark propio multi-métrica | ◐ Hecho parcial: PESQ/STOI/SI-SNR/RTF sobre testset ES+EN sintetizado (`.auto/`). Faltan: STOI/ESTOI, LUFS, True Peak, speaker similarity, artifact score, **split sintético vs real**. |
| §15/16 DNSMOS como métrica | ⚠️ **DNSMOS/UTMOS rotos en este Windows** (fairseq/speechmos — landmine #4). Alternativas factibles: speaker similarity (resemblyzer), LUFS/true-peak (pyloudnorm), heurísticas, **evaluación humana (Track 8)**. |

## Arquitectura objetivo

```
INPUT ──► ANALYZE ──► ENHANCE ──► VOICE DSP ──► MASTER ──► OUTPUT
 (wav/mp4)  VAD         DF2          DC removal    comp      WAV 48k/24-bit
            SNR         dereverb*    high-pass     de-esser  MP4: vídeo copy
            LUFS        declip*      dehum*        limiter   + AAC 192 kbps
            RT60        (*track 5)   EQ vocal      loudnorm
            noise type               presence/air  (-14 LUFS)
            breaths/clicks           (* = opcional)
```

Fundaciones congeladas en la spec (Track 1A): input 16/22.05/44.1/48 kHz mono/stereo
→ **interno 48 kHz mono** → WAV PCM 24-bit / AAC 192 kbps · determinismo
(byte-equivalent DSP, seed para NN) · `--device auto|cpu|cuda` · SLA RTF
(CPU <0.5, CUDA <0.1, master <0.01 — propuesta) · provenance en todo report.

## Tracks (orden de implementación)

### 🟢 Track 0 — Rename a `voxera` *(en curso, PR → master)*
`improve_my_sound`/`ims` → `voxera` (paquete, CLI, pyproject, features, tests, docs).
Tras merge: reinstalar `pip install -e .` desde master.

### 🟢 Track 1A — Fundaciones: audio I/O + format policy + device + determinismo + SLA
Política de sample rates / bit depth / stereo→mono (energía promedio, sin clipping),
A/V sync ≤ 10 ms, determinismo (JSON estable para CI), device policy, **tres RTF
separados** (model / pipeline / e2e), metadata/provenance en reports.

### 🟢 Track 1 — `voxera analyze` + `voxera master`: pipeline DSP alrededor de DF2 *(alto valor, bajo riesgo)*
1. `voxera analyze in.wav` → JSON/TTY con **confidence** en estimaciones: duración, VAD
   (voz/silencio), LUFS-I/LUFS-S/LRA/RMS/true peak, clipping, SNR, rumble/hum/mud/
   boxiness/presence/air, RT60, DC offset, plosives, breaths, mouth_click_candidates,
   **noise type** (heurístico).
2. Pipeline post-denoise en `src/improve_my_sound/dsp/` (pyloudnorm + pedalboard),
   orden congelado: DC removal → high-pass 70 Hz (LR24) → dehum* → EQ vocal (mud
   100–300, boxiness 300–600, presence 2–5k, air 8–14k, ≤±4 dB) → de-esser (max 6 dB)
   → compresor suave → limiter -1 dBTP → loudnorm -14 LUFS.
3. Presets de voz: `--preset creator|youtube|podcast|social|bad-room`.
4. `voxera enhance --preset X` → **siempre** DF2 + pipeline completo; `--dsp-only` =
   master puro; `--dry-run` = plan sin procesar.
- Libs: `pedalboard` (EQ/comp/limiter, wheels Windows), `pyloudnorm` (LUFS).

### 📋 Track 1B — Spec DSP vocal (se implementa dentro de Track 1)
De-esser con criterios de no-daño (no degradar >5% energía 2–5 kHz), breath detection
(no es transitorio: low-energy/broadband/1–8 kHz/100–800 ms, preservar por defecto),
plosives candidates, hum 50/100/150 Hz vs rumble, DC offset, noise-type taxonomy
(11 tipos heurísticos, schema preparado para IA). **Heurísticas primero, medibles y
sustituibles** — nada de ML por ahora.

### 🟡 Track 2 — VAD + limpieza de silencio + boca/aire
`voxera silence --level light|medium|aggressive [--breaths preserve|attenuate|remove]`:
recorta huecos **nunca cortando respiraciones** (margen 200 ms); breaths preservados
por defecto; `mouth_click_candidates` + confidence en analyze; `--declick` opcional.

### 🟡 Track 3 — Voice Score / "ready for publishing"
`voxera score [--ref original]` → desglose 0–100 (Noise/Clarity/Loudness/Room/
Dynamics con LRA+RMS) + CVS + veredicto. Con `--ref`: **Voice Preservation %**
(cosine resemblyzer). **Métricas de producto separadas de las de research**
(PESQ/STOI/ESTOI/SI-SDR/RTF/DNSMOS → solo benchmark).

### 🟡 Track 4 — Vídeo directo (ffmpeg ya disponible)
`voxera enhance video.mp4`: extraer audio → pipeline → reemplazar (`-c:v copy`,
AAC 192 kbps). Criterios A/V: drift ≤ 10 ms, vídeo bit-identical, timestamps y
duración de contenedor preservadas.

### 🔴 Track 5 — Dereverb, declipping, restoration (postergado)
Solo tras Tracks 1–3. VoiceFixer/ClearerVoice como candidatos; **de-plosive y
dehum** entran aquí si se aprueban (decisión abierta #11).

### 🟡 Track 6 — Benchmark `.auto` v2: **sintético y real separados**
- **A. Synthetic** (clean + ruido/reverb/clipping controlados, hay ground truth):
  PESQ · STOI · ESTOI · SI-SDR (+ LUFS/TP/clipping de control).
- **B. Real-world** (mic/phone/webcam/fan/AC/room/street, sin ground truth):
  DNSMOS (cuando funcione) · speaker-sim · LUFS · RTFₘ/RTFₚ/RTFₑ · artifact proxy ·
  human preference (Track 8).
- Entregable: tabla `model × métricas` por suite, nunca fusionada. Candidatos:
  DF2 baseline · DF3 · **DF2 + master presets** · DP-DPNet · VoiceFixer.

### 🆕 Track 8 — Evaluación humana *(nuevo)*
**La métrica definitiva: que alguien prefiera la voz B.** 5–10 oyentes, 10–20 clips
real-world, condiciones A=original / B=DF2 / C=DF2+master / D=otro modelo,
pairwise preference + MOS 1–5, blind + orden aleatorio + **LUFS normalizado** entre
condiciones. Umbral propuesto: DF2+master ≥ DF2 en ≥60% de escuchas.

### 🔴 Track 7 — Tauri desktop (UI thin, al final)
El CLI genera todo (wavs A/B, JSON); A/B player standalone se reutiliza en Track 8
(puede adelantarse en versión mínima HTML).

## Orden de implementación

```
Track 0 (rename, en curso) → Track 1A (fundaciones) → Track 1 (analyze+master, +1B)
→ Track 3 (score) → Track 2 (silence/boca) → Track 4 (vídeo) → Track 6 (benchmark v2)
→ Track 8 (humano) → Track 5 (restoration) → Track 7 (Tauri)
```

**Justificación:** explotar el pipeline alrededor de DF2 antes que nada; 1A congela
formatos/determinismo que afectan a todo lo demás; score tras master da el loop de
validación "escucha + métrica" desde el día 1; la evaluación humana necesita a 6
(clips + métricas) y al player de 7.

## Decisiones abiertas para Antonio

Resumen (12 en total, detalle en `docs/SPECS-fase2.md`):

1. ¿`creator` como preset por defecto de `enhance --preset`? (propuesto: sí, -16 LUFS)
2. ¿Target LUFS de `social` = -14 confirmado? (TikTok/IG reales)
3. ¿Puedes grabar 10–30 clips reales para benchmark v2 (mic/phone/room/fan/AC)?
4. ¿Renombrar el repo a `voxera` o mantener `improve-my-sound` como repo y `voxera`
   como paquete/marca?
5. De-esser: max att 6 dB, ¿tolerancia 5% en energía 2–5 kHz?
6. ¿Exit code `VOXERA_NO_SPEECH = 20`?
7. ¿SLA RTF: CPU <0.5 / CUDA <0.1 / master <0.01?
8. ¿WAV 24-bit + AAC 192 kbps (o 256)?
9. ¿Breaths preservados por defecto (`--breaths` explícito para atenuar/eliminar)?
10. ¿Taxonomía noise type de 11 tipos heurísticos OK?
11. ¿De-plosive y dehum en Track 5 o postergar más?
12. Evaluación humana: ¿quiénes (5–10 personas), cuántos clips (10–20), umbral ≥60%?
