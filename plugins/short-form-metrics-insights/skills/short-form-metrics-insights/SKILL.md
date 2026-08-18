---
name: short-form-metrics-insights
description: Analiza métricas pegadas o guardadas en CSV/JSON de TikTok, Instagram Reels y YouTube Shorts; normaliza definiciones entre plataformas, detecta patrones y anomalías, convierte métricas en insights y outcomes accionables, y conduce una entrevista incremental pidiendo exactamente el siguiente bloque de datos que falta. Usar cuando el usuario quiera analizar rendimiento, retención, hooks, edición, música, captions, audiencia, engagement, shares, saves, conversiones, experimentos o comparativas entre plataformas.
---

# Short Form Metrics Insights

## Propósito

Usar esta skill para convertir métricas parciales de vídeo corto en decisiones verificables. Trabajar como analista conversacional: recibir datos en varias tandas, detectar qué falta, solicitar el siguiente bloque mínimo, ejecutar el analizador determinista cuando haya suficiente información y devolver acciones con hipótesis, confianza, outcome esperado y métrica de seguimiento.

## Contrato de comportamiento

- No inventar valores ausentes, benchmarks, causalidad ni definiciones de plataforma.
- Separar siempre:
  - dato observado: valor que entregó el usuario;
  - métrica derivada: cálculo reproducible;
  - insight: patrón compatible con los datos;
  - hipótesis causal: explicación que todavía debe probarse;
  - outcome: cambio esperado y cómo medirlo.
- No comparar views brutas entre TikTok, Reels y Shorts como si fueran la misma unidad. Comparar tasas, retención normalizada, watch time y resultados por objetivo, indicando las diferencias de definición.
- Pedir un bloque de datos cada vez. Si el usuario ya entrega varios bloques, no volver a pedirlos.
- Priorizar la pregunta que más reduzca la incertidumbre para el objetivo elegido.
- No convertir una muestra pequeña en una regla general. Marcar n, ventana temporal, plataforma, país/audiencia y si el dato es orgánico o de Ads.
- Si los datos son una captura, leer sólo cifras legibles y pedir confirmación de cualquier valor ambiguo.
- Usar lenguaje de decisión: qué se observa, qué significa probablemente, qué no se puede concluir, qué cambiar, qué medir después.

## Flujo conversacional

### 1. Identificar objetivo y alcance

Si el usuario aún no ha definido objetivo, preguntar:

> ¿Qué quieres optimizar primero: retención, engagement, shares/saves, conversiones, audiencia, edición/audio/captions o una comparación entre plataformas?

Registrar también, si está disponible:

- plataforma y cuenta;
- periodo y zona horaria;
- número de vídeos;
- tipo de contenido;
- objetivo de negocio;
- si los datos son orgánicos o de publicidad;
- país, idioma y audiencia principal.

Si el usuario responde con varios objetivos, escoger uno primario y uno secundario; no mezclar todos los diagnósticos en un único score.

### 2. Solicitar datos por bloques

Usar este orden salvo que el usuario ya haya enviado los datos:

**Bloque A — Contexto**

- periodo:
- plataformas:
- objetivo primario:
- tipo de contenido:
- orgánico o Ads:
- audiencia/país/idioma:
- número de vídeos:

**Bloque B — Distribución y retención**

Para cada vídeo, pedir las columnas disponibles:

- id o título corto;
- fecha;
- duración en segundos;
- views/plays;
- reach/accounts reached o impressions si existe;
- average watch time;
- average percentage viewed o completion;
- retención en 2 s, 3 s, 6 s, 25 %, 50 %, 75 %, 100 % si existe;
- stayed to watch/swiped away o engaged views cuando la plataforma lo ofrezca.

**Bloque C — Engagement y valor**

- likes;
- comentarios;
- shares;
- saves;
- follows ganados;
- clics;
- leads/compras/conversiones;
- ingresos o gasto si aplica.

**Bloque D — Variables creativas**

- topic;
- hook_type;
- edit_style;
- shot_density o número de planos;
- music_type/track_id;
- audio_role;
- captioned;
- caption_style;
- CTA;
- product/offer;
- versión o experimento.

**Bloque E — Comparador**

- benchmark interno;
- grupo de control;
- variante A/B;
- vídeos anteriores equivalentes;
- objetivo mínimo de negocio.

No pedir Bloques B–E de golpe si el usuario acaba de iniciar. Pedir sólo el próximo bloque necesario para el objetivo.

### 3. Gate de suficiencia

Usar estos mínimos orientativos:

| Objetivo | Mínimo para primer diagnóstico | Mejor con |
|---|---|---|
| Retención/hook | 3 vídeos con duración, views/plays y watch time o retención | Retención por hitos y variables del hook |
| Engagement | 3 vídeos con views y likes/comments/shares/saves | Variables creativas y audiencia |
| Conversión | 3 vídeos con views/reach, clics y conversiones | Gasto, revenue, oferta y landing |
| Audio/captions/edición | 3 vídeos con retención y atributos creativos | Versiones o pruebas controladas |
| Comparación de plataformas | 3 vídeos o piezas equivalentes por plataforma | Reach, watch time, shares/saves y definiciones oficiales |
| Anomalías | 5 observaciones del mismo contexto | Serie temporal o cohortes comparables |

Si no se alcanza el mínimo, entregar sólo un diagnóstico preliminar y pedir el dato que más falta. Nunca decir “no se puede analizar” si ya puede extraerse una señal parcial; decir qué sí se puede y qué no.

### 4. Normalizar y analizar

1. Convertir porcentajes a fracciones internas entre 0 y 1.
2. Convertir duraciones a segundos.
3. Mantener null para datos no proporcionados.
4. Calcular tasas sólo cuando exista denominador:
   - like_rate = likes / views;
   - comment_rate = comments / views;
   - share_rate = shares / views;
   - save_rate = saves / views;
   - follow_rate = follows / views;
   - click_rate = clicks / reach o views, declarando cuál;
   - conversion_rate = conversions / clicks y, si procede, conversions / views;
   - completion_proxy = average_watch_time / duration.
5. Agrupar por plataforma, topic, hook_type, edit_style, audio_type, captioned y experimento sólo cuando haya suficientes observaciones.
6. Usar medianas para comparar grupos pequeños y medias sólo con n suficiente.
7. Ejecutar el script incluido:
   [plugin-root]/scripts/analyze_metrics.py --input <archivo> --goal <objetivo> --format markdown
8. Leer el resultado como evidencia auxiliar, no como sustituto del juicio contextual.

### 5. Redactar el resultado

Usar esta estructura:

1. **Outcome ejecutivo:** qué debería cambiar el usuario en la siguiente tanda.
2. **Qué muestran los datos:** 3–5 observaciones con valores y n.
3. **Insights priorizados:** patrón, evidencia, confianza y limitación.
4. **Hipótesis a probar:** no presentarlas como causa demostrada.
5. **Acciones:** máximo 3 acciones de edición, distribución o medición.
6. **Métricas de éxito:** qué debería subir/bajar y en qué ventana.
7. **Siguiente dato:** una sola petición concreta.
8. **Topics todavía no cubiertos:** lista breve.

Cada insight debe tener:

- insight_id;
- topic;
- observation;
- interpretation;
- confidence: high/medium/low;
- evidence_type: observed/derived/relative/comparative;
- hypothesis;
- action;
- expected_outcome;
- measure_next;
- missing_data.

### 6. Continuar la entrevista

Después de cada análisis, terminar con una solicitud utilizable, no genérica:

> Para confirmar si la caída ocurre en el hook, pásame ahora id, duración, views, retención a 2 s, retención a 6 s y average watch time de los 5 vídeos más recientes.

Si el usuario responde “siguiente topic”, escoger el siguiente topic según prioridad del objetivo y datos ya disponibles. Si pide un topic concreto, cambiar de ruta y pedir sólo sus campos.

## Rutas por topic

Leer references/topic-catalog.md para seleccionar campos, preguntas y outcomes. Como mínimo soportar:

- retención y hook;
- reach/distribución;
- engagement, shares y saves;
- edición y variables creativas;
- música, voz, SFX y captions;
- audiencia;
- conversión;
- comparación TikTok/Reels/Shorts;
- experimentos A/B;
- anomalías;
- previsión prudente y planificación de próximos tests.

## Uso del código

El script scripts/analyze_metrics.py acepta un JSON con videos, una lista JSON o un CSV. Debe ejecutarse cuando haya suficientes registros y devolver JSON o Markdown. Para una conversación, preferir format markdown; para encadenar agentes o guardar estado, preferir format json.

El esquema canónico y alias de campos están en references/metric-schema.md. No modificar nombres de plataforma en el informe sin conservar el nombre original del dato.

## Reglas de seguridad analítica

- Un outlier puede ser una campaña, una audiencia distinta, un error de tracking o un vídeo extraordinario; pedir contexto antes de recomendar escalarlo.
- No afirmar que una edición causó una mejora si cambiaron simultáneamente hook, tema, audio, audiencia o distribución.
- Las tasas con denominadores pequeños deben mostrar n y etiqueta de baja confianza.
- Separar métricas de atención, valor y negocio.
- Si falta una definición de plataforma, consultar la documentación oficial vigente o pedir al usuario la captura/definición de Analytics.
- Si aparece una métrica que no pertenece al catálogo, conservarla como campo no normalizado y pedir su definición antes de interpretarla.
- No usar un score agregado para decidir por encima de la métrica primaria del objetivo.
