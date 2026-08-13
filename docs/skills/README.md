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
| [voxera-teleport.md](voxera-teleport.md) | `src/voxera/video_teleport.py` | Efecto "Teletransportación" (silueta blanca 2-2-2 + desaparición), inpaint espacial con fondo mediano, morfología por radio EDT, verificación numérica por fases |
| [voxera-cutsilence.md](voxera-cutsilence.md) | `src/voxera/video_silence.py` | Eliminación automática de silencios en vídeo (jump-cuts estilo TikTok), sync A/V frame-accurate (select/aselect + setpts), verificación numérica (frames exactos, sync < 20 ms) |

Nota: las referencias a ficheros de `tmp/` (capturas de TikTok, scripts de
análisis) son artefactos locales — `tmp/` está gitignored.
