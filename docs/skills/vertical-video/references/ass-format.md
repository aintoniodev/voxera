# Formato ASS para subtítulos kinéticos — técnicas exactas

Cabecera mínima (lienzo 9:16):

```
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
```

## Estilo base "TikTok bold"

```
Style: Kinetic,Arial Black,84,&H0000FFFF,&H00DCDCDC,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,7,2,2,60,60,430,1
```

Colores ASS = `&HAABBGGRR` (¡azul-verde-rojo, no RGB!):
- Amarillo `&H0000FFFF` · Verde TikTok #00FF7F `&H007FFF00` · Blanco `&H00FFFFFF`
- Karaoke: SecondaryColour = color de palabra AÚN no pronunciada (gris claro DCDCDC);
  PrimaryColour = color de palabra ya pronunciada (amarillo). El `{k}` va "rellenando".

## Karaoke palabra a palabra

`{k N}` con N en CENTÉSIMAS de segundo, desde el inicio del evento hasta el fin de la
palabra 1; cada `{k}` siguiente cubre hasta el final de SU palabra (absorbe el gap):

```
Dialogue: 0,0:00:05.67,0:00:07.36,Kinetic,,0,0,0,,{ANIM}{k56}Voxera {k44}analiza {k20}tu {k24}audio
```

Tarjetas: máx 4 palabras; cortar en pausa > 0.45 s o tras . ! ? , ; duración mínima 0.7 s.

## ANIM = pop-in con rebote (para tarjetas y títulos)

```
{fad(60,80)\fscx70\fscy70\t(0,120,\fscx105\fscy105)\t(120,220,\fscx100\fscy100)}
```
70% → 105% (overshoot) → 100%: lee como "pop" con settling. Para títulos usar entrada
más lenta (0-160-300 ms) y `{fad(150,180)}`.

## Keyword de énfasis

Envolver la palabra (no escalarla — el escalado por palabra DESPLAZA la línea):

```
{c&H007FFF00&}herramienta{c&H00FFFFFF&}
```

## Tipografía combinada en títulos

Inline, sin segundo estilo: base Arial Black + acento Georgia itálica:

```
escucha la {fnGeorgia\fs58\i1\c&H007FFF00&}diferencia{r}
```
`{r}` devuelve al estilo. Título: Alignment 2, MarginV 640 (queda SOBRE las captions,
que van a 430 — no solapar).

## Quemado en ffmpeg (Windows)

Desde el dir de trabajo con rutas relativas (el `:` de `C:` rompe el filtro; si necesitas
ruta absoluta, escápala como `C\:/...`):

```
-vf "subtitles=out/subs.ass,subtitles=out/titles.ass"
```

Dos `subtitles=` encadenados = dos pistas (subs + títulos), el segundo queda encima.
NO meter emojis en el texto (tofu en libass): stickers como PNG overlay.

## Timing de overlays de sticker

TS = inicio palabra − 0.10 s, TE = fin palabra + 0.70 s, clavado a [0, duración].
Overlay ffmpeg con drift de entrada (pop vertical):

```
overlay=x=760:y='1150-25*min(1,(t-TS)/0.3)':enable='between(t,TS,TE)'
```
(input PNG con `-loop 1 -framerate 30 -i emoji.png`, y `-shortest` al final)
