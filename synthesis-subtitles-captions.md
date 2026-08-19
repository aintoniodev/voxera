# Subtítulos para short-form: velocidad de lectura, segmentación, estilo cinético y hooks de texto — Síntesis científica (DEEP)

> **Resumen ejecutivo (ES):** Síntesis de ~30 fuentes (16 revisadas por pares + 3 guías oficiales de plataforma + norma española UNE 153010 + 2 corpus/gris) sobre cómo hacer subtítulos que no sean "básicos" en vídeo vertical hablado (TikTok/Reels/Shorts, español). Consenso fuerte [C1]: los subtítulos son el lever mejor documentado (mute 38–52%) y su lectura tiene límites medibles — 15 cps (norma española) a 20 cps (Netflix EE. UU.; los espectadores leen hasta 20 cps sin pérdida, estudio eye-tracking N=74); 160–180 palabras/minuto (BBC); cues de ≥0.5 s y sincronía con el audio a ±1–2 frames; cortes de línea SIEMPRE en unidades sintácticas (nunca partir artículo+nombre); en vertical 9:16: máx. 3 líneas y ~25–34 caracteres/línea (90% del ancho). La evidencia refuta parcialmente la intuición: en vídeo vertical las subtítulos de 2 líneas capturan MÁS atención que las de 1 (N=211, 2026) — el formato importa más que el nº de caracteres; y los subtítulos lentos causan más re-lectura y frustración que los rápidos [C1]. Los captions cinéticos palabra-a-palabra siguen SIN evidencia directa de retención [gap]: el \k de relleno que ya usa voxera es defensible (marca el ritmo de lectura), pero el "pop/bounce" por palabra es lore no medido [C0]. Los hooks de texto arriba no tienen experimento aislado en la literatura [gap]: la evidencia más cercana es (a) la ventana de hook de ~1.9 s [C2, del repo], (b) las convenciones de texto en pantalla de Netflix (MAYÚSCULAS, precedencia del mensaje más relevante, nunca mezclar FN con diálogo) [C1], (c) un estudio QoMEX 2026: los overlays no degradan la calidad percibida pero el 62% los encuentra molestos [C2] — usar con moderación, ≤4 palabras, transitorios y sincronizados. Nada publicado sobre subtítulos en español en short-form [gap]. Conclusión práctica: el pipeline actual (18 cps, 3 líneas, 72 px, safe box 900×1160, karaoke + highlight naranja, playful) ya está en el rango científicamente defendible; los upgrades de mayor ROI son (1) auditoría CPS por cue y segmentación sintáctica, (2) un primitivo de "hook de texto arriba" disciplinado (≤4 palabras, ≤2 s, MAYÚSCULAS, dentro de safe zone, nunca sobre la cara), y (3) A/B con métricas propias antes de confiar en cualquier estilo cinético.

---

## 1. Structured Abstract

- **Background/Objective**: ¿Qué dice la evidencia científica y normativa sobre cómo deben ser los subtítulos (velocidad de lectura, segmentación, estilo tipográfico, movimiento) y el texto en pantalla ("hooks de texto arriba") en vídeo vertical corto hablado, con el español como lengua de contenido?
- **Methods**: ~30 fuentes únicas: 16 peer-reviewed (PLOS ONE, Applied Cognitive Psychology, Perspectives, JEMR, QoMEX/IEEE, HCII/LNCS, JAT, Applied Psycholinguistics), 3 guías oficiales de plataforma (BBC, Netflix ×3), 1 norma nacional (UNE 153010:2012 vía literatura secundaria española), 2 tesis (Qiu 2023, Uutela 2026), más la investigación interna previa del repo (R1–R3, 2026). Búsquedas web del 2026-08-19 en español/inglés; web_search y Bing degradados durante la sesión → Google Scholar, Crossref, Semantic Scholar y Zendesk API como canales principales.
- **Results**: Cinco temas sintetizados: (1) la velocidad de lectura tiene un rango científicamente validado de 15–20 cps / 160–180 WPM, con duraciones mínimas de cue (0.3–0.5 s/palabra) y sincronía estricta con el audio; (2) la segmentación en unidades sintácticas mejora lectura y comprensión, y en vertical las 2 líneas capturan más atención que 1; (3) el estilo (blanco sobre negro, contraste, tamaño ~4% de altura en 9:16, minúsculas "playful") tiene base parcial; (4) el captions cinético palabra-a-palabra carece de evidencia directa — es una capa de estilo, no de retención probada; (5) los hooks de texto arriba son una convención de diseño sin experimento aislado, con datos indirectos de solapamiento/atención y normas de "texto en pantalla" (MAYÚSCULAS, precedencia, no mezclar con diálogo).
- **Conclusions**: El núcleo científico es estable: subtítulos siempre [C1], velocidad 16–18 cps para español intralingual [C2], cortes sintácticos [C1], cues sincronizados y con tiempo mínimo [C1], ≤3 líneas en vertical [C1], texto en pantalla breve y con precedencia al mensaje principal [C1]. Lo "no básico" no viene del movimiento ni de los overlays, sino de la disciplina de segmentación/timing y del uso medido del texto en pantalla como capa semántica — no decorativa.

---

## 2. Introduction

El proyecto produce vídeo vertical corto hablado (podcast/talking-head, español) con un pipeline automatizado (voxera: ASR word-level → ASS karaoke → burn-in ffmpeg). La práctica actual — subtítulos cinéticos palabra-a-palabra con keyword highlight, 18 cps, hasta 3 líneas, 72 px, safe box 900×1160, texto "playful" (minúsculas sin puntuación) y stickers de emoji — es funcional y visualmente moderna, pero se apoya en convenciones de creadores, no en una base documentada. Paralelamente existe una literatura académica madura sobre subtitulado (velocidad de lectura, segmentación, eye-tracking, recepción) y unas guías normativas exigentes (BBC, Netflix, UNE) que rara vez se aplican al formato vertical de redes. El usuario pide: mejores prácticas científicamente probadas para subtítulos y para los "hooks de texto" que a veces aparecen arriba.

**Pregunta organizadora:** *¿Qué dice la evidencia (2008–2026, con énfasis 2024–2026) sobre velocidad de lectura, segmentación, estilo y texto en pantalla para subtítulos de vídeo vertical corto, y qué cambios concretos debería adoptar el pipeline voxera para dejar de ser "básico" sin renunciar a lo que ya está probado?*

**Condiciones de frontera:** Inclusión: estudios peer-reviewed sobre recepción/lectura de subtítulos (cualquier soporte, priorizando móvil/vertical), guías normativas oficiales (BBC, Netflix), norma española UNE 153010, corpus/estudios descriptivos de subtítulos en redes. Exclusión: blogs de herramientas de captions como evidencia (tratados como clúster SEO correlacionado, no corroboración), claims no verificables de vendors ("+40% retención con captions cinéticos"), y literatura de danmaku/bullet-comments como evidencia de retención (función social distinta; solo como analogía de atención dividida). Rango temporal 2008–2026; todo el corpus es inglés/chino/polaco/finlandés — nada peer-reviewed en español para short-form [gap declarado]. Escala de confianza: C1 = 3+ fuentes independientes incl. ≥1 peer-reviewed o guía oficial; C2 = 2 fuentes o 1 fuerte; C3 = fuente única; C0 = conflicto sin resolver.

---

## 3. Methodology

**Estrategia de búsqueda** (2026-08-19). El buscador primario (web_search) y Bing devolvieron resultados vacíos/irrelevantes durante toda la sesión; se usaron canales alternativos reproducibles:

1. **Google Scholar** (scholar.google.com) — 10 queries: "kinetic captions short-form video TikTok word highlighting"; "subtitle reading speed Szarkowska characters per second estimation"; "TikTok subtitles subtitle style engagement"; "vertical video subtitles eye-tracking TikTok"; "Szarkowska 2025 vertical video subtitles"; "Huang 2025 subtitles vertical video"; "word-by-word OR karaoke captions experimental study"; "on-screen text overlay video advertising attention"; "subtitle position top bottom eye tracking vertical video"; "danmaku bullet comments attention engagement"; "subtitulado español norma UNE 153010 caracteres por segundo".
2. **Crossref API** (api.crossref.org/works?query.bibliographic=…) — 4 queries para localizar DOIs/abstracts (Li 2026; Amir et al. 2026; Huang et al. 2025; Fresno et al. 2026).
3. **Semantic Scholar API** — abstracts de Li 2026 (vía Crossref DOI corregido), Amir et al. 2026, Huang et al. 2025 (elidido por el publisher).
4. **Zendesk API de Netflix** (partnerhelp.netflixstudios.com/api/v2/help_center/articles/search.json) — recuperación íntegra de: Subtitle Timing Guidelines (id 360051554394), General Requirements (215758617), English (USA) guide (217350977), Spanish (Latin America & Spain) guide (217349997), FAQ reading-speed (115001349591).
5. **Lectura directa de páginas** — BBC Subtitle Guidelines (bbc.co.uk, edición 2026, secciones Presentation/Timing/Matching shots/Typography).

**Conteo por tipo:** 16 peer-reviewed (PLOS ONE 2018; Applied Cognitive Psychology 2026; Perspectives 2013, 2019, 2026 ×2; JEMR 2018; QoMEX/IEEE 2026; HCII/LNCS 2025; JAT 2025; Applied Psycholinguistics 2022; JDSDE 2016; ACM TVX 2016; +2 tesis), 4 documentos oficiales de plataforma (BBC, Netflix ×3), 1 norma nacional (UNE 153010:2012, vía 5 tesis/artículos académicos españoles que la citan), 2 trabajos descriptivos de bajo peso (corpus TikTok finlandés, análisis computacional de telops), más la investigación interna previa del repo (R1–R3). No se contaron como corroboración los blogs de vendors.

**Criterios de calidad/sesgo:** (a) peer-reviewed — peso máximo, se registró N cuando estaba disponible; (b) guías oficiales — autoritativas en convención, no son benchmarks de retención; (c) tesis — peso bajo, solo direccional; (d) fuentes grises (blogs, vendors) — excluidas de agregación C1. Limitación declarada: 5 abstracts (Huang, Jia, Fresno, Amir, Li) se usaron a nivel de abstract; la BBC y Netflix se leyeron íntegros salvo la sección de posicionamiento BBC (truncada por el extractor) — los claims de posicionamiento BBC se limitan a lo verificado.

---

## 4. Thematic Results

### Theme 1 — Velocidad de lectura y tiempo en pantalla: hay un rango validado, no un número único

La literatura y las normas convergen en que la lectura de subtítulos es una tarea serial con límite medible, pero ese límite es más alto de lo que sugiere la práctica tradicional. El estudio eye-tracking de referencia (74 espectadores inglés/polaco/español; clips subtitulados a 12, 16 y 20 cps) muestra que la mayoría lee sin problemas hasta 20 cps y que los subtítulos lentos provocan **más re-lectura, frustración y menos disfrute** [C1 — Szarkowska & Gerber-Morón 2018, PLOS ONE]. Esta línea la corroboran estudios posteriores: lectores mantienen comprensión a 20 cps en intralingual vs interlingual [C2 — Liao et al. 2022, Applied Psycholinguistics], y análisis de plataformas de streaming concluyen que las velocidades reales superan las guías y los espectadores las toleran [C3 — Fresno et al. 2026, Perspectives, abstract]. En el otro extremo, el estándar tradicional chino de ~5 cps se muestra conservador frente a velocidades mayores [C3 — Jia et al. 2026, Perspectives, abstract].

Las guías oficiales sitúan el rango de trabajo: BBC recomienda **160–180 palabras/minuto** (0.33–0.375 s por palabra; mínimo ~0.3 s/palabra, p. ej. 1.2 s para 4 palabras) [C1 — BBC Subtitle Guidelines]; Netflix fija topes por idioma — **inglés EE. UU. 20 cps adultos / 17 cps niños** [C1 — Netflix English USA guide], **español 17 cps adultos / 13 cps niños** [C1 — Netflix Spanish guide]; la norma española de accesibilidad UNE 153010:2012 recomienda **máx. 15 cps** para subtitulado para sordos [C2 — norma citada por 5 fuentes académicas españolas, López Rodríguez & Tercedor Sánchez 2023]. El matiz relevante: las guías de accesibilidad (15–17 cps) son más conservadoras que la capacidad lectora medida (20 cps), y el subtitulado intralingual (mismo idioma, el caso de voxera) tolera más velocidad que el interlingual [C2].

La disciplina temporal es el otro pilar: Netflix exige in-time en el primer frame del audio (±1–2 frames), out-time ~0.5 s después del final del habla para dar tiempo de lectura, duración mínima de cue de **20 frames (0.83 s)** para 1–2 palabras, huecos entre cues de 2 frames o ≥0.5 s ("chaining": cerrar huecos de 3–11 frames), y sincronía con cortes de plano dentro de ±0.5 s [C1 — Netflix Timing Guidelines]; la BBC pide no adelantar el subtítulo más de 1.5 s ni mantenerlo más de 1.5 s tras el final del habla, y huecos de ≥1 s si hay pausa [C1 — BBC]. Para karaoke palabra-a-palabra, esto se traduce en una regla de oro: el **cue completo** (frase) permanece en pantalla mientras dura el \k reveal, así que el límite de lectura se aplica al cue, no a la palabra individual [C2 — inferencia directa de Theme 1].

**→ voxera:** el default de 18 cps está dentro del rango (15–20) pero en el extremo alto para español (Netflix ES: 17; UNE: 15); añadir una **auditoría CPS por cue** en QA (rechazar cues >20 cps; objetivo 16–18) y respetar las duraciones mínimas (≥0.83 s por cue; out-time +0.1–0.5 s tras la última palabra) es lo primero que sube la calidad percibida.

### Theme 2 — Segmentación: el corte sintáctico es el mayor "upgrade" científico disponible

La evidencia más sólida y más infrautilizada es la segmentación. Hay "evidencia considerable de la literatura psicolingüística de que la lectura normal se organiza en grupos de palabras correspondientes a cláusulas y frases sintácticas, y que la segmentación lingüísticamente coherente mejora significativamente la legibilidad" [C1 — BBC, que cita la literatura; corroborado por Rajendran et al. 2013 y Gerber-Morón & Szarkowska 2018]. El estudio de chunking (eye-tracking, subtítulos respoken) muestra que **el chunking reduce el tiempo de lectura** y que los chunk semánticos se procesan mejor [C2 — Rajendran et al. 2013, Perspectives]. Los cortes de línea preferidos por los espectadores son los que mantienen "sintaxis y forma en equilibrio", leyéndose como pensamientos naturales [C2 — Gerber-Morón & Szarkowska 2018, JEMR]. Regla concreta compartida por BBC y Netflix: romper **después de puntuación, antes de conjunciones, antes de preposiciones**; nunca separar artículo+nombre, nombre+adjetivo, nombre+apellido, verbo+pronombre sujeto, verbo+auxiliar/negación [C1 — BBC + Netflix US + Netflix ES].

El número de líneas tiene un matiz nuevo y relevante para vertical: el estudio más reciente (2026, N=211, eye-tracking con webcam sobre un vídeo TikTok) encuentra que **los subtítulos de 2 líneas capturan más atención que los de 1 línea** — mayor tiempo total de fijación, más revisitas, menor probabilidad de salto, y el efecto persiste controlando por número de caracteres [C2 — Li 2026, Applied Cognitive Psychology, abstract]. Esto **complica** la norma clásica de "preferir 1 línea" [C0: la norma BBC/Netflix optimiza comprensión y discreción visual; el dato 2026 indica que en vertical el formato de 2 líneas es más potente para captar atención]. El estudio previo de 3 vs 2 líneas concluía que 2 líneas se procesan mejor que 3 [C2 — Szarkowska & Gerber-Morón 2019, Perspectives], y la BBC permite **hasta 3 líneas solo en 9:16** [C1 — BBC]. La síntesis: en vertical, 2 líneas son el punto dulce para engagement; 3 solo excepcional; 1 línea es suficiente solo para cues muy cortos [C2].

Longitud de línea: BBC limita a 37 caracteres (Teletext) y, en vertical 9:16, al 90% del ancho ≈ **25 caracteres** con tipografía proporcionada [C1 — BBC]; Netflix permite 42 [C1]; voxera ya usa ~34, un buen compromiso [C2].

**→ voxera:** el packing actual rompe "tras puntuación" pero es greedy por longitud; añadir las **reglas negativas** de Netflix/BBC (no separar artículo+nombre, nombre+apellido, verbo+auxiliar) y **preferir 2 líneas** sobre 1 para cues medianos (con 3 solo si el ritmo lo exige) alineará el pipeline con lo probado.

### Theme 3 — Estilo tipográfico: contraste y tamaño primero; el "playful" tiene base parcial

El estilo importa pero la evidencia es más fina que el lore. Los estándares: **blanco sobre negro** (BBC: "la mayoría de los subtítulos se escriben en texto blanco sobre fondo negro para una legibilidad óptima"; colores de hablante en blanco/amarillo/cian/verde limitados) [C1 — BBC], blanco genérico sans-serif (Netflix) [C1], y en vertical la BBC fija **altura de línea del 3.9–4.5% de la altura del vídeo para 9:16** (frente a 7–8% en 16:9) — sobre un canvas de 1920 px, altura de línea ≈ 75–86 px [C1 — BBC]; el 72 px actual de voxera cae dentro de ese rango [C2]. Tipografías anchas recomendadas (Reith Sans, Verdana, Tiresias) porque determinan el reflow [C1 — BBC].

El único estudio experimental de estilo en plataforma social muestra que **emojis + tipografía no estándar (minúsculas, sin puntuación final) superan a los subtítulos tradicionales** en engagement en TikTok (encuesta N=171 + métricas) [C2 — Duraj & Szarkowska 2025, JAT] — esto valida el estilo "playful" que ya usa voxera, pero con la advertencia de que es un estudio único y que la omisión de puntuación debe ser deliberada, no accidental (la puntuación incompleta es un criterio de calidad en las guías) [C2]. El énfasis por color (keyword highlight) no tiene estudio aislado, pero es coherente con la evidencia de que los content words concentran más fijaciones que los function words [C2 — Krejtz et al. 2016, JDSDE] — destacar conceptos portadores de mensaje, no palabras gramaticales [C2].

**→ voxera:** mantener white + stroke/outline (3 px ya), 68–80 px, DejaVu Sans Bold (o cambiar a una fuente ancha como Verdana si el reflow lo permite), y **una sola keyword en color por cue** como regla (hoy permite varias). El highlight naranja es defendible; añadir contraste ≥4.5:1 contra fondos claros [C2].

### Theme 4 — Cinético palabra-a-palabra: sin evidencia directa, pero con un uso defensible

El estilo dominante en redes (karaoke/word-by-word) sigue **sin un solo experimento controlado** que mida retención o comprensión en short-form [gap — confirmado por búsquedas 2026-08-19; coincide con la síntesis previa del repo]. Lo que existe es indirecto y matizado: (a) el movimiento es un atractor de atención saliente [C2 — Carmi & Itti, vía síntesis previa], pero el texto en movimiento es una tarea de lectura serial que compite con la escena [C2 — eye-tracking de subtítulos, Kruger & Steyn 2014]; (b) los estudios de "modos no estándar" de subtitulado muestran efectos de recepción mixtos [C3 — Qiu 2023, tesis]; (c) los análisis de telops (texto en pantalla coreano/japonés) muestran que el texto cinético es una **capa semiótica diseñada**, no un sustituto de subtítulos [C3 — KO & LEE 2026, análisis computacional]. La recomendación práctica que se sigue: el relleno progresivo tipo \k es defendible como **marcador de ritmo de lectura** (indica qué palabra toca ahora, reduce el salto de línea), pero el "pop/rebote/escala por palabra" añade carga visual sin beneficio medido [C0 — lore vs ausencia de evidencia].

**→ voxera:** mantener el \k reveal actual (es el uso más conservador del cinético), NO añadir animaciones por palabra (pop, bounce, shake) sin un A/B propio, y considerar **estático + highlight por keyword** como variante B en el A/B de estilo.

### Theme 5 — Hooks de texto arriba: texto en pantalla como capa semántica, no decorativa

No existe un experimento que aísle "hook de texto arriba" en short-form [gap — ninguna fuente]. La evidencia más cercana viene de tres lados:

1. **Convenciones de "texto en pantalla" (forced narratives)**: Netflix prescribe MAYÚSCULAS sin punto final, duración que imita al texto en pantalla, y — clave — **cuando el texto en pantalla y el diálogo coinciden, el mensaje de mayor relevancia tiene precedencia; nunca combinar FN con diálogo en el mismo subtítulo** [C1 — Netflix US + ES]. Esto sugiere que el hook arriba debe ser informativo (promesa, pregunta, dato) y NO duplicar el diálogo [C1].
2. **Overlays y calidad percibida**: un estudio QoMEX 2026 (2 estudios crowdsourced, contenido vertical real) encuentra que los overlays (captions, info del creador) **no degradan la calidad percibida** pero **el 62% de los participantes los reporta molestos** [C2 — Amir et al. 2026, IEEE QoMEX]. La lectura operativa: el texto sobre el vídeo se tolera — siempre que sea relevante y no tape contenido — pero su abuso genera fricción [C2].
3. **Atención dividida**: el texto superpuesto divide la atención entre región de texto y escena [C2 — Yang 2023, danmaku/Translation Studies; Akahori et al. 2016: el posicionamiento de subtítulos basado en ROI reduce el movimiento ocular]. Con subtítulos abajo + hook arriba hay **dos regiones de lectura activas simultáneas**; la carga es aceptable solo si el hook es breve y transitorio [C2].

Se integra con la ventana de hook ya documentada en el repo: scroll-stop mediano de ~1.9 s y la recomendación de que el valor/promesa aterrice ≤1.5 s [C2 — R3]. El "hook de texto" en el primer segundo es la extensión natural de esa ventana al canal visual [C2], pero debe respetar las safe zones (la franja superior de la UI de las plataformas ocupa la zona superior; el contenido debe quedar dentro del safe box central 900×1160) [C2 — R1]. Preferencias de posicionamiento verificadas: Netflix permite arriba o abajo, "donde sea más fácil de leer" [C1]; la convención universal de subtítulos es abajo; el hook arriba es una capa separada [C2].

**→ voxera:** añadir un primitivo `hook` al pipeline con contrato: texto ≤4 palabras (opcional MAYÚSCULAS), posición superior dentro del safe box (margen ~10–15% desde arriba, por debajo de la franja de UI), duración 0.8–2 s, entrada/salida con fade, sincronizado a la palabra ancla (el ritmo audio-first ya da el ancla), y regla de negocio: nunca simultáneo a un cue de 2+ líneas abajo [C2]. El primer hook (t=0–1.5 s) debe portar la promesa/curiosidad; los siguientes solo en puntos de quiebre (pattern interrupt) [C2].

### Theme 6 — Español: la norma existe y el pipeline debería cumplirla

Hay una laguna total de estudios peer-reviewed sobre subtítulos en español en short-form [gap], pero sí hay normativa aplicable: **UNE 153010:2012** (subtitulado para personas sordas): máx. **37 caracteres/línea**, máx. **15 cps**, 2 líneas por regla general [C2 — norma vía 5 fuentes académicas españolas]; **Netflix español**: 42 caracteres/línea, 17 cps adultos, 2 líneas, pirámide invertida si el subtítulo va arriba (línea 1 más larga que línea 2), puntuación RAE (¡¿?! correctos, sin punto y coma, sin "?!" combinados), números 1–10 en letra, hora 24h (España) vs a. m./p. m. (LatAm), decimales con coma (España) vs punto (LatAm) [C1 — Netflix ES]. Para contenido intralingual hablado en español, el límite práctico de lectura es 17–18 cps (Netflix ES + capacidad medida de 20), más alto que el 15 de accesibilidad — pero el estándar de accesibilidad es el suelo de calidad, no el techo creativo [C2].

**→ voxera:** parametrizar por variante de español (España vs LatAm) para puntuación/números/hora; auditar que el texto "playful" no elimine signos de interrogación/exclamación iniciales (¿/¡) que son obligatorios en español [C1 — RAE/Netflix ES].

---

## 5. Conflicts, Gaps & Limitations

**Conflictos (C0).** (1) *1 vs 2 líneas*: la norma (BBC/Netflix) optimiza discreción y comprensión con 1 línea preferida, pero el único estudio en vertical (Li 2026, N=211) muestra que 2 líneas capturan más atención incluso controlando caracteres — no hay reconciliación publicada; la respuesta operativa es KPI-dependiente (comprensión → corto; atención → 2 líneas en momentos clave). (2) *Velocidad*: 15 cps (UNE) vs 17 (Netflix ES) vs 20 (capacidad medida y Netflix US) — no es contradicción sino tres preguntas distintas (accesibilidad vs convención vs capacidad); el pipeline debe elegir un objetivo y auditarse. (3) *Cinético*: el lore de creadores/vendors lo da por probado; la academia no tiene ni un estudio — el conflicto es evidencia vs práctica, y la resolución recomendada es no agregar más movimiento sin A/B propio. (4) *Overlays*: "no afectan a la calidad percibida" pero "62% molestos" — la fricción existe aunque no se refleje en ratings; implica moderación en frecuencia y contenido, no prohibición.

**Gaps (ausencia de evidencia en todo el corpus).** Cinético palabra-a-palabra sin RCT en short-form [gap]; hooks de texto arriba sin estudio aislado [gap]; nada peer-reviewed en español para short-form [gap]; sin comparación de subtítulos nativos de plataforma vs quemados [gap]; sin datos de retención on-platform para ninguna variante de estilo [gap]; el "playful" (minúsculas/sin puntuación) descansa en un único estudio (N=171) [gap]; sin medición del coste de dos regiones de texto simultáneas en vertical [gap].

**Limitaciones de las fuentes.** 5 papers usados solo a nivel de abstract (Li 2026, Huang 2025, Jia 2026, Fresno 2026, Amir 2026) — los números concretos (efectos, N exactos) provienen de los abstracts; la sección de posicionamiento de la BBC no se pudo extraer (página truncada) y los claims de posicionamiento se limitan a Netflix; los estudios de eye-tracking son de laboratorio/webcam, no de consumo real con thumb-scroll; las guías oficiales definen convención de calidad, no benchmarks de retención; el corpus finlandés (Uutela 2026) es una tesis de bajo peso y solo se usó como señal descriptiva; los vendors de captions no se contaron como evidencia.

---

## 6. Conclusion

**Respuesta directa a la pregunta organizadora.** Los subtítulos "no básicos" no se consiguen añadiendo efectos, sino aplicando disciplina donde la ciencia ya es contundente: (1) **siempre subtítulos** [C1]; (2) **velocidad 16–18 cps para español intralingual** (dentro del rango validado 15–20; auditar por cue; duración mínima 0.83 s; out-time +0.5 s tras el habla; sync a ±1–2 frames) [C2]; (3) **segmentación sintáctica** — romper tras puntuación, antes de conjunciones/preposiciones, nunca partir artículo+nombre ni nombre+apellido; 2 líneas preferidas en vertical (3 máximo) [C1/C2]; (4) **estilo**: blanco con contorno (o caja), 68–80 px (~4% de altura), una keyword en color por cue, playful solo como decisión deliberada [C2]; (5) **cinético**: mantener \k reveal, no añadir pop/bounce por palabra sin A/B [C0]; (6) **hooks de texto arriba**: breve (≤4 palabras), transitorio (0.8–2 s), MAYÚSCULAS o bold, dentro del safe box, sincronizado a la palabra ancla, con precedencia al mensaje principal y nunca duplicando el diálogo [C1/C2]; (7) **español**: cumplir UNE/Netflix ES (¿¡, números, variante regional) [C1].

**Evolución temporal.** La comprensión ha cambiado en una dirección clara: de reglas conservadoras de accesibilidad (15 cps, 37 caracteres) hacia un reconocimiento de que la capacidad lectora real es mayor (20 cps validados en 2018; streaming supera las guías en 2026) y de que el formato vertical tiene su propia física (2 líneas > 1 línea en atención, 2026). El cinético y los hooks siguen sin base experimental — la brecha entre práctica y ciencia no se ha cerrado en 2024–2026.

**Implicaciones prácticas (orden de ROI).** (1) Auditoría CPS por cue + duraciones mínimas en QA (cambio de código pequeño, impacto inmediato); (2) reglas negativas de segmentación en el packing (línea); (3) primitivo `hook` de texto arriba con contrato estricto; (4) variante B de estilo (estático + highlight) para el A/B con métricas propias; (5) parametrización ES (España/LatAm). Lo único que la bibliografía no puede decidir es si el cinético o los hooks ganan retención en el feed real — eso es una medición del proyecto, no una pregunta de investigación abierta.

---

## 7. Blueprint mínimo para voxera (cambios concretos sobre lo que ya existe)

```
ESTADO ACTUAL (verificado en skills): karaoke \k, 18 cps, max_lines=3,
font_size=72, outline=3, safe_box=(900,1160), margin_v=380, playful=minúsculas
sin puntuación trailing, highlight naranja, emojis como stickers PNG.
CAMBIO 1 — QA de lectura (captions.py):
  - auditar cps por cue: warn >18, fail >20 (ES intralingual);
  - duración mínima por cue: 0.83 s (20 frames @24fps; 25 @30fps);
  - out-time de cue: última palabra + 0.1–0.5 s (no cortar en seco).
CAMBIO 2 — Segmentación (words_to_cues):
  - reglas negativas: no separar {artículo+nombre, nombre+apellido,
    verbo+auxiliar/negación, preposición+frase};
  - preferir 2 líneas para cues medianos; 1 línea solo cues cortos;
    3 líneas solo excepción (ya es el máximo).
CAMBIO 3 — Primitivo hook (nuevo, estilo "título":
  - contrato: {text ≤4 palabras, pos=top, y ≈12–16% del canvas (bajo UI),
    dur 0.8–2.0 s, fade 80 ms, style=bold|ALL-CAPS, anchor_word, anchor=after};
  - reglas: 1 hook máximo simultáneo; nunca con cue de 2+ líneas abajo;
    primer hook t≈0–1.5 s con promesa/curiosidad (ventana de scroll-stop);
    siguientes solo en puntos de quiebre (pattern interrupt);
    nunca sobre la cara del hablante (mantener dentro del safe box 900×1160).
CAMBIO 4 — Estilo ES (parámetro):
  - variante es-ES / es-LATAM: puntuación ¿¡, hora 24h vs a. m./p. m.,
    decimales, números 1–10 en letra;
  - regla: el modo playful NO elimina ¿/¡.
CAMBIO 5 — A/B de estilo (baseline):
  - variante A = karaoke + 1 keyword en color (actual);
  - variante B = estático + highlight;
  - gate: métricas propias (medianas, 7–14 días) + Track-8 humano ≥60%.
```

**Fuentes principales citadas (fechas de acceso 2026-08-19):** BBC Subtitle Guidelines (bbc.co.uk); Netflix Timed Text Style Guides — General Requirements, Subtitle Timing Guidelines, English (USA), Spanish (Latin America & Spain) (partnerhelp.netflixstudios.com); Szarkowska & Gerber-Morón (2018) PLOS ONE; Szarkowska & Gerber-Morón (2019) Perspectives; Gerber-Morón & Szarkowska (2018) JEMR; Rajendran et al. (2013) Perspectives; Li (2026) Applied Cognitive Psychology; Amir et al. (2026) IEEE QoMEX; Huang et al. (2025) HCII/LNCS; Duraj & Szarkowska (2025) JAT; Liao et al. (2022) Applied Psycholinguistics; Krejtz et al. (2016) JDSDE; Jia et al. (2026) Perspectives; Fresno et al. (2026) Perspectives; Akahori et al. (2016) ACM TVX; KO & Lee (2026) telop; Qiu (2023) tesis Melbourne; Uutela (2026) tesis Turku; UNE 153010:2012 vía López Rodríguez & Tercedor Sánchez (2023) y 4 tesis españolas; síntesis interna previa (R1–R3, 2026).
