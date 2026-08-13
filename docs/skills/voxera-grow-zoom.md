# Skill: voxera-grow-zoom

> Mirror del skill del agente (canonical en el skill store local de pi,
> fuera del repo).

## When to Use
Aplicar zooms programáticos a vídeos (voxera video zoom), editar src/voxera/video_zoom.py, diagnosticar renders de zoom que no animan, o replicar el efecto "Grow" del tutorial de @serri.mp4 (zoom con curva de easing + ancla, ampliar y reducir).

## Procedure
1. Comando: `.venv-ims/Scripts/voxera video zoom IN -o OUT [--pct 30] [--anchor 0.5,0.33] [--curve 62] [--dir grow|shrink|pulse] [--hold F] [--auto-emphasis] [--pulse-dur 3] [--max-pulses 4] [--start/--end] [--dry-run]`
2. Defaults medidos del tutorial (2026-08-13, ECC frame a frame sobre el TikTok de @serri.mp4): la demo real es zoom-in 1.0→1.40 en ~4s con curva S (pico de velocidad ~60% de la duración = curva 62), ancla en el sujeto (~0.58,0.24); también demuestra shrink 1.0→0.77. Un 12% en 55s es invisible — usar 30-40% en pulsos de 2-4s.
3. Criterio de aplicación (elegido por el usuario): --auto-emphasis = picos de energía de la voz (envolvente RMS 50ms/25ms suavizada, regiones > max(1.2*media, 0.35*pico), centroide de energía, separación mínima 6s, top max_pulses).
4. Arquitectura del filtro: scale supersampled (2x) → zoompan (z/x/y por frame con 'time', d=1, fps=input, s=canvas) → scale a resolución original → setsar/format. Shrink: pre-scale a zmin + pad negro centrado + zoompan con zpan = 1/zmin - (pct/zmin)*pulse.
5. Pulso: E_in*E_rev (producto de rampas de easing con la reversa vía time*(-1)), unión de pulsos por SUMA (no se solapan por min_gap). Curva: pow(P,a)/(pow(P,a)+pow(1-P,a)), a=1+curve/25.
6. Verificar SIEMPRE numéricamente (SSIM window-ancla vs frame en picos y baseline; o gradiente gris [16,235] midiendo luma de ambos bordes en la fila central — NUNCA fila 0 con shrink, NUNCA umbral >20 con grow: la fila 0 del shrink es negra y el umbral es ciego sin bordes negros).

## Pitfalls
- ffmpeg 7.1 (build gyan.dev) — filtro crop: w/h se evalúan UNA vez al config (t=NaN → clamp01(NaN)=1 → zoom congelado en el pico); solo x/y animan. NO usar crop para zoom animado — usar zoompan.
- zoompan NO expone 't' ni 'n': usar 'time' (= out_time = frame_count/fps) y 'zoom' en x/y.
- Formas de expresión que CONGELAN la eval por-frame de zoompan (medido): empezar con '1-0.X*...' (p.ej. 1-0.2*min(...)); menos unario '1+-0.2*...'. Formas que animan: '1+0.3*...', '1.25-0.25*...', restas con operandos atómicos.
- Mediciones trampa: con grow (sin bordes negros) el umbral >20 da span completo siempre; con shrink la fila 0 es negra (el rect sale por arriba) — medir la fila central con luma exacta (v-16)/219*W.
- zoompan clampa z a [1,10]; el shrink debe expresarse como zpan>=1 (pre-escala a zmin + pad) para no depender del clamp.
- fps del probe del input: pasarla a build_zoom_filter (out_fps) o los timestamps del zoompan no cuadran con los pulsos.

## Verification
1. tests: `.venv-ims/Scripts/python.exe -m pytest tests/test_video_zoom.py -q` (38 tests: curva, fases, validación, plan, e2e grow/shrink/pulse/auto-emphasis)
2. Render + SSIM window-ancla: en picos del pulso SSIM(window 1.3 anclado) > 0.99 y en baseline SSIM(sin-zoom) > 0.99 (método validado en el demo long1_growzoom.mp4: 0.997 picos / 1.000 baseline).
3. Gradiente gris [16,235]: z medido por luma en fila central debe seguir el perfil esperado (1.0 → pico → 1.0).
