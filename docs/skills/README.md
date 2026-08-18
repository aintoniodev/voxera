# Skills del agente (mirror en repo)

Estos archivos son copias versionadas de los skills procedimentales del
agente (canonical en el skill store local de pi, fuera del repo).
El agente lee su skill store propio; este directorio versiona el
conocimiento en el repo para que viaje con el proyecto.

| Skill | Módulo | Qué cubre |
|---|---|---|
| [voxera-grow-zoom.md](voxera-grow-zoom.md) | `src/voxera/video_zoom.py` | Zoom "Grow" (curva de easing + ancla), quirks de ffmpeg 7.1 (crop/zoompan), verificación numérica por SSIM |
| [voxera-magnify.md](voxera-magnify.md) | `src/voxera/video_magnify.py` | Lente "Magnify" (lupa circular, pluma + aro), máscaras PNG con numpy, verificación numérica por FFT con senoide |
| [voxera-audio-lowpass.md](voxera-audio-lowpass.md) | `src/voxera/audio_lowpass.py` | Efecto "Pase Bajo" (cutoff 800 Hz + rampas S), decisión de auto-aplicación por intención narrativa, verificación numérica (bit-exacto, bandas, método ratio) |
| [voxera-teleport.md](voxera-teleport.md) | `src/voxera/video_teleport.py` | Efecto "Teletransportación" (silueta blanca 2-2-2 como transición), segmentación de persona DeepLabV3, verificación numérica por fases |
| [voxera-cutsilence.md](voxera-cutsilence.md) | `src/voxera/video_silence.py` | Eliminación automática de silencios en vídeo (jump-cuts estilo TikTok), sync A/V frame-accurate (select/aselect + setpts), verificación numérica (frames exactos, sync < 20 ms) |
| [voxera-video-stabilize.md](voxera-video-stabilize.md) | `src/voxera/video_stabilize.py` | Estabilización anti-temblor (Warp Stabilizer Smooth Motion), álgebra de similitudes W_t = D_t⁻¹·C_t, verificación con phase correlation |
| [voxera-audio-tonal.md](voxera-audio-tonal.md) | `src/voxera/audio_tonal.py` | Musicalidad tonal ("tell the people how to feel"): transición de emoción A→B, riser que acaba exacto en el corte, melodía generada bajo la voz; tabla de 8 moods (modo/raíz/timbre), verificación numérica (FFT de triadas, RMS cuartil del riser, notas ∈ escala, mix bit-exacto) |
| [vertical-video/](vertical-video/) | `scripts/*.py` (propios, no en `src/`) | Producción de vídeo vertical 9:16 producto-final desde crudo (color, corte de silencios audio-first, subs kinéticos, stickers contextuales, punch-ins, tarjetas). Pipeline completo con scripts propios, glosario ASR persistente por serie, y validación numérica (validate.py). Incluye SKILL.md + scripts + references |

Todas incluyen una sección **Reference Implementation** con el código
núcleo (expresiones ffmpeg exactas, easing, máscaras, álgebra) para que
un agente autónomo pueda replicar el efecto sin acceso al módulo fuente.

Nota: las referencias a ficheros de `tmp/` (capturas de TikTok, scripts de
análisis) son artefactos locales — `tmp/` está gitignored.
