# Catálogo extensible de topics

## Registro

| topic_id | Pregunta principal | Datos mínimos | Outcome |
|---|---|---|---|
| retention | ¿Dónde se pierde la atención? | duración, views, average watch time o retención | Cambiar hook, pacing o payoff y definir el punto de medición. |
| hook | ¿Qué apertura detiene mejor el scroll? | hook_type, retención 2/3/6 s, stayed to watch | Elegir una familia de hooks para el siguiente test. |
| reach_distribution | ¿Se está distribuyendo la pieza? | views, reach/impressions, fecha, fuente si existe | Separar packaging/distribución de calidad de contenido. |
| engagement | ¿Qué genera conversación o valor? | likes, comments, shares, saves, follows y views/reach | Priorizar share/save/comment según objetivo. |
| creative_editing | ¿Qué técnica de edición se asocia con mejor resultado? | edit_style, shot_density, duración, retención y engagement | Proponer una variante de montaje, no una ley universal. |
| audio_captions | ¿Voz, música, SFX o captions ayudan o interfieren? | audio_type, captioned, watch time, retención y shares/saves | Testear mezcla, música, captions o silencio. |
| audience | ¿Qué segmentos responden? | país, idioma, edad/segmento, retención y valor | Crear hipótesis de adaptación, respetando tamaño de muestra. |
| conversion | ¿El vídeo produce negocio? | reach/views, clicks, conversions, revenue, spend | Diagnosticar gap atención → acción → conversión. |
| cross_platform | ¿Qué cambia entre TikTok, Reels y Shorts? | piezas comparables, plataforma, tasas y watch time | Adaptar montaje y métrica por plataforma, no copiar views. |
| experiments | ¿Qué variante ganó? | experiment_id, variable cambiada, métrica primaria | Documentar ganador y siguiente prueba controlada. |
| anomalies | ¿Qué observación rompe el patrón? | ≥5 filas comparables, fecha, tracking y cohortes | Confirmar error/contexto antes de escalar. |
| forecasting | ¿Qué outcome es razonable esperar? | serie temporal, n, estacionalidad, objetivo | Rango prudente, supuestos y datos que reducirían incertidumbre. |
| content_pipeline | ¿Qué pieza producir después? | topics, outcomes, recursos y rendimiento histórico | Backlog priorizado por impacto esperado y esfuerzo. |

## Campos creativos recomendados

- hook_type: result_first, question, conflict, transformation, proof, direct_address, other.
- edit_style: talking_head, tutorial, ugc, reaction, dance_music, story, montage, screen_recording, other.
- audio_type: voice_only, voice_music, music_only, ambient, sound_effects, other.
- captioned: true/false/unknown.
- cta: save, share, comment, follow, click, purchase, none.
- experiment_id: identificador compartido por variantes.
- variable_changed: hook, duration, pacing, captions, music, mix, ending, framing, other.

## Prioridad por defecto

1. retention/hook;
2. engagement/value;
3. creative_editing/audio_captions;
4. conversion;
5. cross_platform;
6. forecasting/content_pipeline.

Cambiar este orden si el usuario declara un objetivo de negocio diferente.
