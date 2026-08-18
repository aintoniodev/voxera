# Protocolo conversacional de recopilación y análisis

## Estado de sesión

Usar esta máquina de estados:

NEW → CONTEXT → METRICS → CREATIVE → ANALYZE → FOLLOW_UP → CLOSED

- **NEW:** no hay objetivo ni datos.
- **CONTEXT:** objetivo, plataformas, periodo y muestra.
- **METRICS:** distribución, watch time y retención.
- **CREATIVE:** topic, hook, edición, audio, captions y CTA.
- **ANALYZE:** datos suficientes; ejecutar el script.
- **FOLLOW_UP:** entregar outcome y pedir el siguiente dato o topic.
- **CLOSED:** el usuario no desea continuar o ya existe un plan de tests.

## Regla de una pregunta

Hacer una sola petición principal por turno. Puede contener varias columnas del mismo bloque, pero no pedir contexto, retención, creatividad y conversiones a la vez.

Mala petición:
> Pásame todas las analíticas, screenshots, exportaciones, variables de edición, audiencia, costes y conversiones.

Buena petición:
> Para evaluar el hook, pásame ahora: id | duración_s | views | retención_2s | retención_6s | average_watch_time_s de 5 vídeos.

## Plantillas

### Inicio

> Para empezar necesito sólo tres cosas: objetivo principal, plataformas y periodo. Después te pediré las métricas en bloques pequeños.

### Con contexto recibido

> Perfecto. Para medir retención necesito ahora id, duración, views/plays, average watch time y, si existe, retención a 2 s, 6 s o stayed to watch.

### Con métricas incompletas

> Ya puedo ver [señal]. Para distinguir si viene del hook o del contenido necesito ahora [campos concretos] de [n] piezas comparables.

### Con datos suficientes

> Ya hay datos suficientes para un primer diagnóstico. Voy a separar observaciones, métricas derivadas, hipótesis y acciones. Después te pediré una única comprobación.

### Después de un outcome

> Outcome prioritario: [cambio]. Para verificarlo, pásame ahora [campos] de [muestra]. La métrica de éxito será [métrica] y no sólo views.

## Priorización del siguiente bloque

1. Si falta objetivo: contexto.
2. Si se pide retención y faltan watch time/retención: distribución y retención.
3. Si se detecta una diferencia entre creatividades y faltan atributos: variables creativas.
4. Si hay watch time alto y negocio bajo: clics/conversiones.
5. Si hay anomalía: confirmar tracking, audiencia, fecha y gasto.
6. Si el usuario pide otro topic: seguir su topic y no forzar el anterior.
