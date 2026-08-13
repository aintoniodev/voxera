# Skill: voxera-audio-lowpass

> Mirror del skill del agente (canonical en el skill store local de pi,
> fuera del repo). Los ficheros de `tmp/` mencionados son artefactos
> locales (gitignored).

## When to Use
Aplicar el efecto "Pase Bajo" (low-pass) de audio estilo Premiere (voxera audio lowpass), editar src/voxera/audio_lowpass.py, diagnosticar renders donde el filtro no suena como el tutorial, o replicar el efecto del tutorial de @serri.mp4 (cutoff 800 Hz + transición suave en los cortes).

EL EFECTO ES GENÉRICO — los auriculares son SOLO el ejemplo del tutorial. El Pase Bajo es una herramienta narrativa: le dice al oyente "este sonido está en otro espacio / otra realidad". Contextos comunes donde se usa (todos válidos para --auto):
- Auriculares/casco puestos (el tutorial) — momento de acción
- Llamada telefónica / radio / walkie / intercom — espacio lejano
- Flashback / memoria / sueño / recuerdo — otra realidad
- "Detrás de una puerta" / habitación contigua / fuera de plano
- Submarino / bajo el agua / dentro de un casco o pasamontañas
- Voz en off distante, locutor de otra sala
- Énfasis creativo: la palabra/instante que quieres destacar (estilo zoom del mismo creador)

DECISIÓN DE AUTO-APLICACIÓN (cuándo aplicar sin --start/--end a mano):
1º Identificar la INTENCIÓN NARRATIVA del pedido, no el contexto técnico:
- "todo este clip suena distante" (llamada, flashback, radio) → modo FULL (sin bordes): el clip entero es el otro espacio
- "un momento pasa a otro espacio y vuelve" (auriculares, puerta que se cierra) → BLIP con --start/--end alrededor del momento
- "entra en el espacio distante y se queda" (entra en la sala, empieza la llamada) → ON (solo --start)
- "sale del espacio distante" (cuelga, sale de la sala) → OFF (solo --end)
2º Si la región NO es derivable del pedido (material limpio y sin momento marcado), elegir heurística por contexto o preguntar (ask_user_question con las 3 opciones):
- Replicar una referencia ya editada → OSCURIDAD ESPECTRAL: banda 4-10 kHz con mediana 1 s (mata sibilantes), normalizada p10-p90, regiones < 0.35 con min_dur 1.5 s. Validado sobre el tutorial real: detecta 1.42-3.77 s vs 1.8-3.6 s medido a mano (±0.4 s; se pierde la región de 1 s por el min_dur). OJO falsos positivos en material limpio: sobre el audio del tutorial de zoom (sin efecto) dispara 9.17-10.72 y 11.52-13.17 (secciones naturalmente oscuras).
- Énfasis creativo estilo zoom (consistente con --auto-emphasis de voxera video zoom) → picos de energía de la voz (RMS 50/25 ms, regiones > max(1.2*media, 0.35*pico), centroide, min_gap 6 s, top N) y blip lowpass en cada momento.
- Transiciones imperceptibles → pausas/silencios del material (VAD/gaps): el filtro entra en una pausa y sale en la siguiente; el cambio ocurre donde nadie lo nota.
- Intención ambigua o material que no encaja → preguntar al usuario antes de decidir.
NOTA: ningún criterio de audio deduce una acción visual (ponerse auriculares); cuando el momento lo define el vídeo, el agente debe pedir el timestamp o proponer el detector de oscuridad como aproximación.
## Procedure
1. Comando: `.venv-ims/Scripts/voxera audio lowpass IN -o OUT [--cutoff 800] [--start S] [--end E] [--transition 1] [--curve 62] [--easing smooth|out|in|linear] [--order 1|2|4] [--dry-run]`
2. Defaults medidos del tutorial (2026-08-13, audio del TikTok de @serri.mp4 extraído vía CDP + whisper + espectro): cutoff 800 Hz declarado ('ajustaremos el valor a 800 hercios'), transición predeterminada de Premiere (Constant Power, 1 s) en los cortes, pendiente ~12 dB/oct (2º orden). La rampa medida en el audio real es ~0.5-1.5 s (envolvente 4-10 kHz con mediana 1 s para quitar sibilantes de la voz).
3. Semántica de región (derivada de qué bordes se dan, y las rampas van SOLO en los bordes explícitos): sin --start/--end = todo el clip con rampa en ambos bordes (el clip ya cortado del tutorial); con ambos = 'blip' (el caso del tutorial: rampa de entrada, mantener, rampa de salida); solo --start = 'on' (entra y se queda — sin rampa de salida al final del archivo); solo --end = 'off' (empieza filtrado — sin rampa de entrada en t=0).
4. Motor: wet = scipy butter(order, cutoff) con sosfilt sobre TODO el clip; out = dry + (wet - dry) * env (crossfade seco/húmedo). Fuera de la región env=0 → salida bit-exacta al original. Envolvente con rampas S (ease p^a/(p^a+(1-p)^a), a=1+curve/25, misma convención que voxera video zoom); si la región es más corta que 2*transition las rampas se cruzan con min() (pico < 1, sin sobresaltos).
5. Verificar SIEMPRE numéricamente: bit-exactitud fuera de la región (np.array_equal), caída de banda aguda dentro (butter2@800 → ~-28 dB @ 3-9 kHz; -26 dB umbral test), bajo preservado (< 1.5 dB), y forma de rampa con el MÉTODO RATIO (env_out/env_in sigue 1-ease) — la correlación directa sobre material con voz da ~0.5 por los sibilantes; con ratio da 0.999.
## Pitfalls
- build_envelope DEBE ser vectorizado (np.minimum + ease vectorizada, float32): la versión con loop Python por muestra tardaba 25.8 s y 623 MB para un clip de 3 min; la vectorizada 1.4 s. ease() acepta array (float32 in → float32 out) y devuelve float para escalar.
- Semántica de rampas (corregida en review, 2026-08-13): con solo --start (on) o solo --end (off) los bordes de archivo NO rampean — el filtro se queda / empieza filtrado; las rampas solo en los bordes de región explícitos. Solo el modo full (sin bordes) rampea en los bordes del archivo.
- El fixture de test escrito con sf.write sin subtype es PCM_16 (cuantización ~1e-5) — comparar contra la entrada LEÍDA, no contra el array original; a nivel de módulo (apply_lowpass) el contrato es bit-exacto de verdad.
- Ruido blanco con |x|>1 → clipping al escribir WAV: escalar fixtures a 0.8/max.
- La banda 6-22 kHz de los audios de TikTok está casi vacía en TODOS sus vídeos (codec/upload): el ratio hi/total no discrimina el filtro; usar el espectro comparado (brillante vs oscuro) o la banda 3-9 kHz.
- El espectro del 'dark segment' individual está contaminado por la voz; la transferencia directa brillante/oscuro NO es fiable (la música no es idéntica entre tramos) — la verdad de tierra es el cutoff declarado (800 Hz) + la pendiente medida ~12 dB/oct.
- Los tutoriales de @serri.mp4 se descargan vía CDP Network capture (anti-bot TikTok): el script local (tmp/tt_capture.mjs, gitignored) + skill web-browser (Chrome :9222); yt-dlp directo falla con 'Unexpected response from webpage request'.
- TikTok: la transcripción con faster-whisper 'small' + vad_filter en es da 1.00 confianza — la receta del tutorial salió de ahí (no hay texto OCR-able en los frames, 1080x1920).
## Verification
1. tests: `.venv-ims/Scripts/python.exe -m pytest tests/test_audio_lowpass.py -q` (32 tests: ease escalar+vectorizada, opciones, envolvente full/blip/on/off, región fuera de archivo, atenuación por orden, plan, e2e bit-exacto + rampa S).
2. Demo real: `media/audio/lowpass/demo_blip.wav` (blip 4-12 s sobre el audio del tutorial de zoom) — verificado bit-exacto fuera, -27.8 dB en 3-9 kHz dentro (teoría butter2@800: -28 dB), bajo -0.1 dB, rampas ratio corr 0.999.
2b. Demo combinado voz+zoom: `media/videos/zoomed/long1_growzoom_lowpass.mp4` — growzoom de long1 con dos frases filtradas (30.1-35.6 y 38.2-43.4 s, transition 0.5 s) coincidiendo con pulsos de zoom (t=30.76 y 38.63 s, env=0.998 en el pulso); verificado bit-exacto fuera y -26 dB en 3-9 kHz dentro. Dos blips = aplicar el CLI dos veces encadenadas (regiones disjuntas, crossfade lineal → idéntico al resultado directo).
3. Detector de oscuridad (si se usa para replicar): sobre el audio capturado del tutorial de lowpass encuentra las regiones reales ±0.4 s; sobre material limpio (audio del tutorial de zoom) NO — esperar falsos positivos y filtrar por contexto.
4. Suite completa: pytest tests/ (273 + 32 pasan, sin CI en el repo — verificación local).
