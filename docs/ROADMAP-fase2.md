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

### ✅ Track 0 — Rename a `voxera` *(hecho — PR #1 mergeado)*
`improve_my_sound`/`ims` → `voxera` (paquete, CLI, pyproject, features, tests, docs).
✅ Verificado en fase 2: editable de `.venv-ims` funcional (`voxera` importa desde `src/`), 150 tests.

### ✅ Track 1A — Fundaciones: audio I/O + format policy + device + determinismo + SLA *(hecho)*
Política de sample rates (16/22.05/44.1/48 kHz mono/stereo → interno 48 kHz mono, downmix
`0.5·(L+R)` energía, resample soxr), salida WAV **PCM 24-bit**, determinismo (JSON estable para
CI: claves ordenadas + floats fijos, única excepción `processing_time_s`; DSP byte-equivalente),
device policy `--device auto|cpu|cuda`, RTF separados (model/pipeline/e2e/master) medidos y
reportados en `--verbose`, bloque `system` de provenance (voxera_version, backend/model,
model_hash, device, seed, preset, sample_rate). Exit 20 `VOXERA_NO_SPEECH` implementado
(gate en `master` y `enhance` con pipeline; el `enhance` legacy sin preset queda sin gate —
back-compat explícito de la spec).

### ✅ Track 1 — `voxera analyze` + `voxera master`: pipeline DSP alrededor de DF2 *(hecho)*
1. `voxera analyze in.wav` → JSON/TTY con **confidence** (duración, LUFS-I/S/LRA/RMS/TP,
   clipping, VAD, SNR, rumble/hum 50/100/150/mud/boxiness/presence/air, RT60, DC, plosives,
   breaths, mouth_click_candidates, noise type heurístico). `--format tty|json`, `-o report.json`.
2. Pipeline post-denoise en `src/voxera/dsp/` (pyloudnorm + pedalboard + scipy/numpy),
   orden congelado: DC removal → high-pass 70 Hz (LR24) → [dehum] → EQ vocal (≤±4 dB)
   → de-esser (max 6 dB) → compresor → limiter -1 dBTP → loudnorm + guard TP.
3. Presets: `creator|youtube|podcast|social|bad-room` (parámetros congelados).
4. `voxera enhance --preset X` → **siempre** backend + pipeline; `--dsp-only` = master puro;
   `--dry-run` = plan `VOXERA PLAN` sin escribir ni cargar NN.
- Acceptance verificado: LUFS ±1, TP ≤ -1 dBTP, duración ±0.1 s, DC < -60 dBFS, mud ≥2 dB,
  byte-equivalente, de-esser no-daño 2-5 kHz ≤5%, features Gherkin (28 escenarios APS verdes).

### ✅ Track 1B — Spec DSP vocal *(hecho, dentro de Track 1)*
De-esser con criterio de no-daño (≤5% energía 2-5 kHz en CI), breath detection por envolvente
(quiet 100-800 ms, nivel -55..-30 dBFS, 1-8k ≫ 100-1k, junto a frontera de voz; preservar por
defecto), plosives candidates (burst <150 Hz en onset), hum 50/100/150 vs rumble, DC offset,
noise-type taxonomy (11 tipos heurísticos, schema preparado para IA). **Heurísticas primero,
medibles y sustituibles** — nada de ML por ahora.

### ✅ Track 2 — VAD + limpieza de silencio + boca/aire *(hecho)*
`voxera silence --level light|medium|aggressive [--breaths preserve|attenuate|remove]
[--declick]`: recorta huecos (1.5→0.8 / 0.8→0.5 / 0.4→0.25 s) **nunca cortando
respiraciones** (margen 200 ms + fades 2 ms en cortes); breaths preservados por
defecto (byte-iguales verificado); `--breaths attenuate` (-6 dB) / `remove`;
`--declick` (transitorios 2-6k, -6 dB). Segmentación por envolvente relativa
(el VAD es poco fiable a nivel de gap). Reporte `original → cleaned · speech % → %`.

### ✅ Track 3 — Voice Score / "ready for publishing" *(hecho)*
`voxera score [--ref original]` → desglose 0–100 (Noise/Clarity/Loudness/Room/
Dynamics) + CVS ponderado + veredicto (≥80 "ready for publishing"). Con `--ref`:
**Voice Preservation %** (cosine resemblyzer, stdout suprimido para JSON limpio).
**Métricas de producto separadas de las de research** (PESQ/STOI/ESTOI/SI-SDR/RTF
→ solo benchmark). También `voxera inspect` (analyze + recomendación).

### ✅ Track 4 — Vídeo directo (ffmpeg) *(hecho)*
`voxera enhance video.mp4 -o out.mp4 --preset X` / `voxera master video.mp4`:
ffprobe detecta vídeo → extrae audio 48k mono → pipeline → mux (`-c:v copy` +
AAC 192 kbps, `--audio-bitrate` override). Criterios verificados en test: vídeo
**bit-identical**, drift ≤ 10 ms, duración de contenedor preservada. Vídeo sin
`--preset`/`--dsp-only` → error de uso (exit 2).

### ✅ Track 5 — Declipping, deplosive, dehum (restoration heurística) *(hecho)*
`voxera restore [--declip] [--deplosive] [--dehum N] [--preset X]`: declip
(reconstrucción de flat-tops por interpolación cúbica, techo adaptativo, audio
limpio bit-idéntico), deplosive (burst <150 Hz en onsets), dehum (notch).
VoiceFixer/ClearerVoice: candidatos ML a evaluar en benchmark v2 (instalación
pesada diferida); la decisión #11 (de-plosive/dehum en Track 5) queda cerrada.

### ✅ Track 6 — Benchmark `.auto/v2`: **sintético y real separados** *(hecho)*
- **A. Synthetic** (`build_synthetic.py`: clean + noise SNR 0/10/20 + reverb IR +
  clipping; ground truth): PESQ · STOI · ESTOI · SI-SDR (+ LUFS/TP/clipping) +
  RTFₘ/RTFₚ/RTFₑ. Ejecutado: DF2 pesq 3.07 · DF3 2.98 · dpdfnet 2.71 · DF2+master
  baja métricas de referencia (esperado: el master es para loudness/consistencia).
- **B. Real-world** (`.auto/v2/real/*.wav` — clips de Antonio, decisión #3):
  SNR est · speaker-sim (resemblyzer) · LUFS · TP · crest · RTFₑ.
- Entregable: `.auto/v2/reports/{synthetic,real}.md`, **nunca fusionados**.

### ✅ Track 8 — Evaluación humana *(infraestructura hecha; escucha pendiente de Antonio)*
`ui/ab-player.html` (waveform, **división arrastrable** ORIGINAL|ENHANCED, blind,
match loudness RMS, pairwise + MOS 1-5) + `ui/server.py` (POST /vote →
`.auto/human/votes.csv`). Protocolo en `.auto/human/README.md`: 5–10 oyentes,
10–20 clips reales, A=original/B=DF2/C=DF2+master/D=DF3, LUFS normalizado,
umbral ≥60% para DF2+master vs DF2 (decisión #12 pendiente de confirmar).

### ✅ Track 7 — UI thin (Tauri pendiente de toolchain Rust) *(HTML hecho)*
Sin cargo/rustc en esta máquina → UI thin en `ui/`: `index.html` (upload →
preset → enhance → Voice Score con barras) + `ab-player.html` + `server.py`
(wraps el CLI: /enhance, /score, /vote, /media). **El CLI sigue generando todo**
(wavs A/B, JSON). Tauri completo queda documentado como pendiente: instalar
rustup + `cargo tauri init` reutilizando `ui/`.

## Orden de implementación

```
**Todos los tracks implementados** (0, 1A, 1, 1B, 2, 3, 4, 5, 6, 8, 7-UI):
pendiente solo la parte humana (escucha Track 8 con clips reales) y el shell Tauri
(toolchain Rust). El orden seguido: 0 → 1A → 1(+1B) → 3 → 2 → 4 → 5 → 6 → 8 → 7-UI.
```

**Justificación:** explotar el pipeline alrededor de DF2 antes que nada; 1A congela
formatos/determinismo que afectan a todo lo demás; score tras master da el loop de
validación "escucha + métrica" desde el día 1; la evaluación humana necesita a 6
(clips + métricas) y al player de 7.

## Decisiones abiertas para Antonio

Resumen (12 en total — **7 resueltas**, 5 abiertas; detalle en `docs/SPECS-fase2.md`):

1. ✅ ~~¿`creator` como preset por defecto de `enhance --preset`?~~ **sí, -16 LUFS** (implementado)
2. ¿Target LUFS de `social` = -14 confirmado? (TikTok/IG reales) — implementado a -14 a falta de confirmar
3. ¿Puedes grabar 10–30 clips reales para benchmark v2 (mic/phone/room/fan/AC)?
4. ~~¿Renombrar el repo a `voxera` o mantener `improve-my-sound` como repo y `voxera`
   como paquete/marca?~~ ✅ **resuelta** — el repo ya es `aintoniodev/voxera`.
5. ✅ ~~De-esser: max att 6 dB, ¿tolerancia 5% en energía 2–5 kHz?~~ **5% implementado** (test en CI)
6. ✅ ~~¿Exit code `VOXERA_NO_SPEECH = 20`?~~ **20 implementado** (gate en master + enhance con pipeline)
7. ¿SLA RTF: CPU <0.5 / CUDA <0.1 / master <0.01? — **medido y reportado** en `--verbose`; umbrales sin enforce
8. ✅ ~~¿WAV 24-bit + AAC 192 kbps (o 256)?~~ **24-bit + 192 confirmado** (AAC se aplica en Track 4)
9. ✅ ~~¿Breaths preservados por defecto?~~ **sí** — el reporte los cuenta; el flag `--breaths` llega con Track 2
10. ✅ ~~¿Taxonomía noise type de 11 tipos heurísticos OK?~~ **implementada** (`analyze` → artifacts.noise_type)
11. ¿De-plosive y dehum en Track 5 o postergar más?
12. Evaluación humana: ¿quiénes (5–10 personas), cuántos clips (10–20), umbral ≥60%?
