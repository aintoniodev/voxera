---
name: short-form-editing-science
description: "Convierte la investigación científica operativa de Shorts, Reels y TikTok en planes de edición ejecutables: hooks, timeline, cortes, ritmo, estilos, efectos, subtítulos, volumen, música, SFX, CTA, variantes y QA. Usar cuando el agente deba planificar o dirigir la edición de un vídeo corto a partir de material bruto, una transcripción, métricas, un brief o una plataforma de destino, sin obligar al usuario a abrir un editor."
---

# Short Form Editing Science

## Propósito

Usar esta skill como capa de aplicación del informe científico. No resumir el informe de forma genérica: convertirlo en un edit spec que otro agente o herramienta pueda ejecutar, con decisiones por tiempo, función, audio, texto, efectos, variantes y criterios de aceptación.

Leer siempre references/informe-cientifico-operativo-shorts-reels-tiktok.md cuando haya que justificar una decisión o cuando el usuario pida profundidad científica. Mantener la skill ligera y usar el informe como referencia progresiva.

## Contrato de salida

Entregar un plan con:

1. objetivo primario y métrica;
2. plataforma, canvas y duración;
3. arquetipo editorial;
4. hook elegido y dos alternativas;
5. timeline por beats;
6. plan de cortes, B-roll, encuadres y efectos;
7. texto: headline, captions, callouts y CTA;
8. mezcla: voz, música, SFX, loudness y true peak;
9. variantes de test;
10. QA técnico, semántico, de accesibilidad y de derechos;
11. preguntas o assets que todavía faltan.

No presentar presets como leyes universales. Etiquetar como evidencia, guía de plataforma o preset experimental.

## Flujo de aplicación

### 1. Recoger el brief mínimo

Si falta información, pedir un bloque por turno:

- plataforma: TikTok, Instagram Reels, YouTube Shorts o varias;
- objetivo: retención, comprensión, emoción, shares/saves, follow o conversión;
- duración máxima y si se necesita loop;
- tipo de vídeo: talking head, tutorial, UGC/producto, reacción, música/danza o historia;
- idioma y audiencia;
- material: vídeo, transcripción, timecodes, B-roll, audio, imágenes y logo;
- derechos de música, voz, imagen y claims;
- CTA y métrica de éxito.

Si el usuario sólo dice “edita esto”, pedir primero plataforma, objetivo y material disponible. No pedir todo el cuestionario si el material ya contiene parte de la respuesta.

### 2. Auditar el material antes del montaje

Crear una tabla de inventario:

asset_id | tipo | timecode | contenido | calidad | función posible | derechos | conservar/descartar

Analizar:

- primer frame posible;
- frases con promesa, conflicto, prueba o payoff;
- silencios accidentales frente a pausas útiles;
- errores, repeticiones y cambios de energía;
- rostros, manos, producto, pantalla y dirección de mirada;
- B-roll que cubra cortes o demuestre algo;
- música y SFX disponibles;
- partes que requieren captions o callouts.

No inventar frases, claims, reacciones ni pruebas que no estén en el material.

### 3. Elegir estructura y hook

Seleccionar un solo objetivo y una sola promesa. Proponer tres hooks:

- resultado primero;
- pregunta/conflicto;
- demostración/transformación.

Elegir el hook que maximice claridad y relevancia. El primer frame debe empezar con acción, resultado, rostro, conflicto o texto útil. No usar una introducción de marca larga. No invocar una supuesta regla universal de 3 segundos.

Estructuras por arquetipo:

- talking head: tesis → explicación → ejemplo → payoff;
- tutorial: resultado → pasos → demostración → resumen;
- producto/UGC: problema → uso → prueba → objeción → CTA;
- reacción/comedia: setup mínimo → reacción → remate;
- música/danza: acción legible → progresión por beats → highlight;
- historia/suspense: conflicto → evidencia → giro → reveal.

### 4. Construir el timeline

Usar beats semánticos, no cortes automáticos por reloj:

- cambio de idea;
- cambio de acción;
- cambio emocional;
- nueva evidencia;
- cambio de foco;
- setup a payoff.

Presets iniciales, siempre marcados como E4:

- 0.0–0.7 s: detener el swipe con acción/resultado/rostro/texto;
- 0.7–2.5 s: promesa;
- 2.5–8 s: contexto o prueba;
- 8–20/30 s: progresión;
- final: payoff y una CTA.

Cadencia de prueba:

- talking head: cambio visual cada 1–3 s;
- tutorial: 1–3 s por acción;
- B-roll de acción: 0.5–1.5 s;
- montaje musical: 0.3–0.8 s sólo cuando el corte tenga sentido;
- historia/emoción: 2–5 s o más si la frase necesita respirar.

Alargar el plano cuando se necesita leer, observar un detalle, entender un paso o sentir una reacción. Cortar sobre acción y conservar dirección, posición o ancla visual.

### 5. Diseñar texto y audio

Texto:

- captions abiertos por defecto cuando hay voz;
- 1–2 líneas, alto contraste y safe zone;
- 12–17 caracteres por segundo como preset de comodidad;
- 18–20 sólo como test con frases simples;
- separar headline, subtítulo, callout y CTA;
- no tapar cara, boca, manos, producto o payoff;
- no poner información crítica sólo en audio.

Audio:

- voz > música > SFX;
- música congruente y de energía moderada por defecto;
- SFX sólo si orientan o enfatizan;
- ducking cuando la voz entra;
- preset experimental: −16 LUFS-I ±2 y true peak ≤ −1 dBTP;
- verificar en móvil, altavoz pequeño, auriculares y volumen bajo;
- comprobar licencia por plataforma.

### 6. Aplicar efectos con función

Asignar a cada efecto una función: orientar, explicar, enfatizar, ocultar una transición, crear emoción o reforzar identidad. Si no tiene función, eliminarlo.

Por defecto:

- cut como transición principal;
- punch-in para énfasis puntual;
- match de acción/dirección para continuidad;
- zoom, whip, flash, glitch, shake y speed ramp sólo cuando el beat los justifica;
- slow motion sólo para detalle, belleza, precisión o emoción;
- evitar un efecto por palabra o por corte.

### 7. Generar variantes y handoff

Crear variantes que cambien una sola variable:

- hook A/B/C;
- cadencia base vs 20–30 % más lenta;
- captions limpios vs captions + callouts;
- música congruente vs silencio/ambiente;
- final cerrado vs final con CTA;
- duración condensada vs completa.

El handoff debe permitir que otro agente edite sin interpretar intenciones ocultas. Para cada beat indicar:

start | end | source_asset | action | framing | cut_reason | text | audio | effect | acceptance_test

Si faltan assets o datos, cerrar con NEXT INPUT y pedir una única cosa concreta.

## QA de salida

Rechazar el edit spec si:

- la promesa no se paga;
- el primer frame es un preámbulo sin función;
- no hay una métrica primaria;
- el montaje corta por cronómetro aunque rompa comprensión;
- los captions contienen datos no verificados;
- la voz queda tapada;
- el audio tiene clipping o derechos inciertos;
- el texto o payoff queda bajo la UI;
- hay efectos sin función;
- la CTA llega antes del valor;
- se confunde un preset experimental con una conclusión científica.

## Uso del script

Para generar una primera especificación estructurada desde un brief:

python3 [plugin-root]/scripts/build_edit_spec.py --input brief.json --format markdown

Usar el script como punto de partida; añadir después decisiones basadas en la transcripción y los assets reales. Para trabajar en conversación, ejecutar con JSON y explicar qué campos faltan.

## Topics cubiertos

- hooks y primeros segundos;
- timing, duración y densidad;
- cortes, continuidad y ritmo;
- estilos por arquetipo;
- complejidad visual y efectos;
- captions, headlines y safe zone;
- voz, música, SFX, loudness y derechos;
- narrativa, suspense, emoción y CTA;
- variantes A/B;
- adaptación TikTok, Reels y Shorts;
- QA y handoff a un agente editor.
