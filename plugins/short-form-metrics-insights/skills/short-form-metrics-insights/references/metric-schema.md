# Esquema canónico de métricas

## Entrada aceptada

El analizador acepta:

1. Objeto JSON con videos.
2. Lista JSON de objetos.
3. CSV con una fila por vídeo.

Los nombres pueden ser aliases; conservar el nombre original en raw si existe.

## Registro canónico

Campos de contexto:

- id: identificador único o título corto.
- platform: tiktok, instagram_reels, youtube_shorts u other.
- date: fecha ISO si existe.
- period: ventana de Analytics si se entrega.
- organic_or_ads: organic, ads, unknown.
- country, language, audience.
- topic, hook_type, edit_style, audio_type, captioned, cta, experiment_id.

Campos de vídeo:

- duration_s.
- views.
- reach.
- impressions.
- watch_time_s.
- average_watch_time_s.
- average_percentage_viewed.
- completion_rate.
- engaged_views.
- stayed_to_watch_rate.
- retention_2s, retention_3s, retention_6s.
- retention_25, retention_50, retention_75, retention_100.

Campos de interacción:

- likes.
- comments.
- shares.
- saves.
- follows.
- clicks.
- conversions.
- revenue.
- spend.

## Unidades

- Duraciones: segundos.
- Counts: números absolutos.
- Tasas: internamente como fracción 0–1; aceptar 0.42 y 42%.
- Dinero: conservar valor y currency si existe.
- Ausencia: null, vacío o NA; no convertir ausencia en cero.
- views y plays se mapean a views, pero el informe debe conservar que el nombre original era plays cuando sea relevante.
- average_watch_time sin unidad se interpreta como segundos sólo si el contexto lo confirma; si no, pedir aclaración.
- Las métricas de Shorts engaged_views y stayed_to_watch_rate no se mezclan automáticamente con views históricas sin indicar la definición.
- En Reels, average_watch_time puede incluir replays según la definición de Analytics; conservar el nombre de plataforma.

## Ejemplo JSON mínimo

{
  "videos": [
    {
      "id": "reel_001",
      "platform": "instagram_reels",
      "date": "2026-08-01",
      "duration_s": 22,
      "views": 18000,
      "reach": 15000,
      "watch_time_s": 66000,
      "average_watch_time_s": 3.67,
      "completion_rate": "14%",
      "likes": 900,
      "comments": 44,
      "shares": 130,
      "saves": 210,
      "follows": 52,
      "topic": "tutorial",
      "hook_type": "result_first",
      "edit_style": "talking_head_broll",
      "audio_type": "voice_music",
      "captioned": true
    }
  ]
}
