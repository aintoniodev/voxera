#!/usr/bin/env python3
"""Deterministic analysis for short-form video metrics.

Accepts JSON or CSV and emits JSON or Markdown. It deliberately avoids
platform-specific causal claims: the output reports observations, derived
rates, relative comparisons, confidence and next data requests.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


VERSION = "0.1.0"

CANONICAL_FIELDS = [
    "id", "platform", "date", "period", "organic_or_ads", "country",
    "language", "audience", "topic", "hook_type", "edit_style",
    "audio_type", "captioned", "cta", "experiment_id", "variable_changed",
    "duration_s", "views", "reach", "impressions", "watch_time_s",
    "average_watch_time_s", "average_percentage_viewed", "completion_rate",
    "engaged_views", "stayed_to_watch_rate", "retention_2s",
    "retention_3s", "retention_6s", "retention_25", "retention_50",
    "retention_75", "retention_100", "likes", "comments", "shares",
    "saves", "follows", "clicks", "conversions", "revenue", "spend",
]

NUMERIC_FIELDS = {
    "duration_s", "views", "reach", "impressions", "watch_time_s",
    "average_watch_time_s", "engaged_views", "likes", "comments",
    "shares", "saves", "follows", "clicks", "conversions", "revenue",
    "spend",
}

RATE_FIELDS = {
    "average_percentage_viewed", "completion_rate",
    "stayed_to_watch_rate", "retention_2s", "retention_3s", "retention_6s",
    "retention_25", "retention_50", "retention_75", "retention_100",
}

TEXT_FIELDS = {
    "id", "platform", "date", "period", "organic_or_ads", "country",
    "language", "audience", "topic", "hook_type", "edit_style",
    "audio_type", "cta", "experiment_id", "variable_changed",
}

ALIASES: Dict[str, Sequence[str]] = {
    "id": ("id", "video_id", "content_id", "video", "title", "nombre"),
    "platform": ("platform", "plataforma", "source_platform", "network"),
    "date": ("date", "fecha", "published_at", "publish_date"),
    "period": ("period", "periodo", "date_range", "window"),
    "organic_or_ads": ("organic_or_ads", "organic_ads", "traffic_type", "source_type"),
    "country": ("country", "pais", "country_code"),
    "language": ("language", "idioma", "lang"),
    "audience": ("audience", "segment", "audience_segment"),
    "topic": ("topic", "tema", "content_topic", "category"),
    "hook_type": ("hook_type", "hook", "tipo_hook", "opening_type"),
    "edit_style": ("edit_style", "editing_style", "estilo_edicion", "format"),
    "audio_type": ("audio_type", "music_type", "audio_role", "sound_type"),
    "captioned": ("captioned", "captions", "subtitles", "subtitulado"),
    "cta": ("cta", "call_to_action", "action"),
    "experiment_id": ("experiment_id", "experiment", "test_id", "variant_group"),
    "variable_changed": ("variable_changed", "changed_variable", "test_variable"),
    "duration_s": ("duration_s", "duration", "duration_seconds", "video_length", "duracion"),
    "views": ("views", "view", "plays", "play_count", "video_views", "reproducciones"),
    "reach": ("reach", "accounts_reached", "unique_reach", "alcance"),
    "impressions": ("impressions", "impression", "impresiones"),
    "watch_time_s": ("watch_time_s", "watch_time", "total_watch_time", "watch_time_seconds"),
    "average_watch_time_s": (
        "average_watch_time_s", "average_watch_time", "avg_watch_time",
        "average_view_duration", "avg_view_duration", "tiempo_medio",
    ),
    "average_percentage_viewed": (
        "average_percentage_viewed", "avg_percentage_viewed", "average_viewed",
        "apv", "porcentaje_medio_visto",
    ),
    "completion_rate": (
        "completion_rate", "completion", "completion_percentage",
        "full_watch_rate", "finalizacion",
    ),
    "engaged_views": ("engaged_views", "engaged_view", "vistas_con_interaccion"),
    "stayed_to_watch_rate": (
        "stayed_to_watch_rate", "stayed_to_watch", "chose_to_view",
        "viewed_rate", "stayed_rate",
    ),
    "retention_2s": ("retention_2s", "retention_2_sec", "2s", "2_sec", "view_2s"),
    "retention_3s": ("retention_3s", "retention_3_sec", "3s", "3_sec", "view_3s"),
    "retention_6s": ("retention_6s", "retention_6_sec", "6s", "6_sec", "view_6s"),
    "retention_25": ("retention_25", "retention_25pct", "25_percent", "25%"),
    "retention_50": ("retention_50", "retention_50pct", "50_percent", "50%"),
    "retention_75": ("retention_75", "retention_75pct", "75_percent", "75%"),
    "retention_100": ("retention_100", "retention_100pct", "100_percent", "100%"),
    "likes": ("likes", "like_count", "me_gusta", "me_gusta_count"),
    "comments": ("comments", "comment_count", "comentarios"),
    "shares": ("shares", "share_count", "compartidos"),
    "saves": ("saves", "save_count", "guardados"),
    "follows": ("follows", "followers_gained", "new_followers", "seguidores_ganados"),
    "clicks": ("clicks", "link_clicks", "outbound_clicks", "clics"),
    "conversions": ("conversions", "conversion_count", "purchases", "leads", "conversiones"),
    "revenue": ("revenue", "sales", "income", "ingresos"),
    "spend": ("spend", "cost", "ad_spend", "gasto"),
}

GOAL_KEYS: Dict[str, Sequence[str]] = {
    "retention": (
        "completion_proxy", "completion_rate", "average_percentage_viewed",
        "stayed_to_watch_rate", "retention_2s", "retention_6s",
    ),
    "engagement": ("share_rate", "save_rate", "comment_rate", "follow_rate", "like_rate"),
    "conversion": ("conversion_rate_click", "conversion_rate_view", "click_rate"),
    "creative": ("completion_proxy", "share_rate", "save_rate", "engagement_rate"),
    "all": (
        "completion_proxy", "retention_2s", "share_rate", "save_rate",
        "follow_rate", "conversion_rate_click",
    ),
}

DIMENSIONS = (
    "platform", "topic", "hook_type", "edit_style", "audio_type",
    "captioned", "experiment_id",
)

SUMMARY_METRICS = (
    "goal_score", "views", "average_watch_time_s", "completion_proxy",
    "completion_rate", "retention_2s", "retention_6s", "like_rate",
    "comment_rate", "share_rate", "save_rate", "follow_rate",
    "engagement_rate", "click_rate", "conversion_rate_click",
    "conversion_rate_view",
)


def normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[%/\\-]+", "_", text)
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, aliases in ALIASES.items():
    for alias in (canonical, *aliases):
        ALIAS_TO_CANONICAL[normalize_key(alias)] = canonical


def parse_number(value: Any) -> Tuple[Optional[float], bool]:
    """Return (number, was_percent)."""
    if value is None or isinstance(value, bool):
        return None, False
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None, False
        return float(value), False
    text = str(value).strip()
    if not text or text.lower() in {"na", "n/a", "null", "-", "—", "none"}:
        return None, False
    percent = text.endswith("%")
    if percent:
        text = text[:-1].strip()
    text = text.replace("\u00a0", "").replace(" ", "")
    if "," in text and "." not in text:
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0].lstrip("-").isdigit():
            text = "".join(parts)
        else:
            text = text.replace(",", ".")
    elif "," in text and "." in text:
        text = text.replace(",", "")
    text = re.sub(r"[^0-9eE+.\-]", "", text)
    try:
        return float(text), percent
    except ValueError:
        return None, percent


def parse_rate(value: Any) -> Optional[float]:
    number, was_percent = parse_number(value)
    if number is None:
        return None
    if was_percent or number > 1:
        number /= 100.0
    return number


def parse_duration(value: Any) -> Optional[float]:
    if isinstance(value, str) and ":" in value:
        parts = value.strip().split(":")
        try:
            values = [float(part) for part in parts]
        except ValueError:
            values = []
        if len(values) == 3:
            return values[0] * 3600 + values[1] * 60 + values[2]
        if len(values) == 2:
            return values[0] * 60 + values[1]
    number, _ = parse_number(value)
    return number


def parse_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "si", "sí", "1", "on"}:
        return True
    if text in {"false", "no", "0", "off"}:
        return False
    return None


def normalize_platform(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = normalize_key(value)
    if "tiktok" in text or text == "douyin":
        return "tiktok"
    if "instagram" in text or "reels" in text:
        return "instagram_reels"
    if "youtube" in text or "shorts" in text:
        return "youtube_shorts"
    return str(value).strip().lower() or None


def flatten_record(record: Dict[str, Any]) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in record.items():
        normalized = normalize_key(key)
        if normalized in {"metrics", "data", "analytics"} and isinstance(value, dict):
            for child_key, child_value in value.items():
                flat[normalize_key(child_key)] = child_value
            continue
        if normalized in {"metadata", "creative", "attributes"} and isinstance(value, dict):
            for child_key, child_value in value.items():
                flat[normalize_key(child_key)] = child_value
            continue
        if normalized in {"retention", "retention_curve"} and isinstance(value, dict):
            for child_key, child_value in value.items():
                child_norm = normalize_key(child_key)
                flat[child_norm] = child_value
            continue
        flat[normalized] = value
    return flat


def raw_for(flat: Dict[str, Any], canonical: str) -> Any:
    for alias in (canonical, *ALIASES.get(canonical, ())):
        key = normalize_key(alias)
        if key in flat:
            return flat[key]
    return None


def canonicalize(record: Dict[str, Any], index: int) -> Dict[str, Any]:
    flat = flatten_record(record)
    row: Dict[str, Any] = {"row_number": index + 1}
    for field in CANONICAL_FIELDS:
        value = raw_for(flat, field)
        if field == "platform":
            row[field] = normalize_platform(value)
        elif field == "captioned":
            row[field] = parse_bool(value)
        elif field in RATE_FIELDS:
            row[field] = parse_rate(value)
        elif field == "duration_s":
            row[field] = parse_duration(value)
        elif field in NUMERIC_FIELDS:
            number, _ = parse_number(value)
            row[field] = number
        elif field in TEXT_FIELDS:
            row[field] = None if value is None else str(value).strip()
        else:
            row[field] = value
    row["raw"] = record
    row.update(derive_metrics(row))
    return row


def safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def derive_metrics(row: Dict[str, Any]) -> Dict[str, Optional[float]]:
    views = row.get("views")
    interaction_base = views or row.get("reach") or row.get("impressions")
    click_base = row.get("reach") or views or row.get("impressions")
    derived: Dict[str, Optional[float]] = {}
    derived["average_watch_time_from_total"] = safe_div(row.get("watch_time_s"), views)
    avg_watch = row.get("average_watch_time_s") or derived["average_watch_time_from_total"]
    derived["completion_proxy"] = safe_div(avg_watch, row.get("duration_s"))
    for field, source in (
        ("like_rate", "likes"),
        ("comment_rate", "comments"),
        ("share_rate", "shares"),
        ("save_rate", "saves"),
        ("follow_rate", "follows"),
    ):
        derived[field] = safe_div(row.get(source), interaction_base)
    interactions = sum((row.get(name) or 0) for name in ("likes", "comments", "shares", "saves"))
    derived["engagement_rate"] = safe_div(interactions, interaction_base)
    derived["value_rate"] = safe_div((row.get("shares") or 0) + (row.get("saves") or 0), interaction_base)
    derived["click_rate"] = safe_div(row.get("clicks"), click_base)
    derived["conversion_rate_click"] = safe_div(row.get("conversions"), row.get("clicks"))
    derived["conversion_rate_view"] = safe_div(row.get("conversions"), views)
    derived["revenue_per_view"] = safe_div(row.get("revenue"), views)
    derived["revenue_per_conversion"] = safe_div(row.get("revenue"), row.get("conversions"))
    return derived


def load_input(path: str) -> List[Dict[str, Any]]:
    if path == "-":
        text = sys.stdin.read()
        suffix = ""
    else:
        file_path = Path(path)
        text = file_path.read_text(encoding="utf-8")
        suffix = file_path.suffix.lower()
    if suffix == ".csv" or (text.lstrip() and not text.lstrip().startswith(("{", "["))):
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]
    payload = json.loads(text)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("videos", "items", "data", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("Input must be a JSON list, a JSON object with videos/items/data/records, or CSV.")


def finite_values(rows: Iterable[Dict[str, Any]], metric: str) -> List[float]:
    values: List[float] = []
    for row in rows:
        value = row.get(metric)
        if isinstance(value, (int, float)) and math.isfinite(value):
            values.append(float(value))
    return values


def mean_or_none(values: Sequence[float]) -> Optional[float]:
    return statistics.mean(values) if values else None


def median_or_none(values: Sequence[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def round_value(value: Any, digits: int = 4) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, digits)
    if isinstance(value, dict):
        return {key: round_value(item, digits) for key, item in value.items()}
    if isinstance(value, list):
        return [round_value(item, digits) for item in value]
    return value


def goal_score(row: Dict[str, Any], goal: str) -> Optional[float]:
    values = [row.get(key) for key in GOAL_KEYS.get(goal, GOAL_KEYS["all"])]
    values = [float(value) for value in values if isinstance(value, (int, float)) and math.isfinite(value)]
    return mean_or_none(values)


def summarize_rows(rows: Sequence[Dict[str, Any]], goal: str) -> Dict[str, Any]:
    scores = []
    for row in rows:
        score = goal_score(row, goal)
        if score is not None:
            scores.append(score)
    result: Dict[str, Any] = {"n": len(rows), "goal": goal}
    medians: Dict[str, Any] = {}
    means: Dict[str, Any] = {}
    for metric in SUMMARY_METRICS:
        values = [goal_score(row, goal) if metric == "goal_score" else row.get(metric) for row in rows]
        numeric = [float(value) for value in values if isinstance(value, (int, float)) and math.isfinite(value)]
        medians[metric] = median_or_none(numeric)
        means[metric] = mean_or_none(numeric)
    result["median"] = medians
    result["mean"] = means
    result["score_observations"] = len(scores)
    return result


def group_summaries(rows: Sequence[Dict[str, Any]], goal: str) -> Dict[str, List[Dict[str, Any]]]:
    output: Dict[str, List[Dict[str, Any]]] = {}
    for dimension in DIMENSIONS:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            value = row.get(dimension)
            label = "unknown" if value in (None, "") else str(value)
            grouped[label].append(row)
        output[dimension] = []
        for label, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
            summary = summarize_rows(members, goal)
            summary["value"] = label
            output[dimension].append(summary)
    return output


def confidence_for(n: int, relative: bool = False) -> str:
    if n >= 20:
        return "high"
    if n >= 8:
        return "medium"
    return "low" if relative else "preliminary"


def pct(value: Optional[float]) -> Optional[float]:
    return None if value is None else value * 100.0


def format_pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def format_num(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.3f}"


def missing_fields(rows: Sequence[Dict[str, Any]], goal: str) -> List[Dict[str, Any]]:
    required_by_goal = {
        "retention": ("views", "duration_s", "average_watch_time_s", "completion_rate", "retention_2s"),
        "engagement": ("views", "likes", "comments", "shares", "saves"),
        "conversion": ("views", "reach", "clicks", "conversions"),
        "creative": ("views", "duration_s", "topic", "hook_type", "edit_style", "audio_type"),
        "cross-platform": ("platform", "views", "reach", "average_watch_time_s"),
        "all": ("platform", "views", "duration_s", "average_watch_time_s", "shares", "saves"),
    }
    fields = required_by_goal.get(goal, required_by_goal["all"])
    result = []
    for field in fields:
        present = sum(row.get(field) not in (None, "") for row in rows)
        if present < max(2, math.ceil(len(rows) * 0.5)):
            result.append({"field": field, "present": present, "total": len(rows)})
    return result


def data_quality(rows: Sequence[Dict[str, Any]], goal: str) -> Dict[str, Any]:
    missing: Dict[str, int] = {}
    for field in CANONICAL_FIELDS:
        count = sum(row.get(field) in (None, "") for row in rows)
        if count:
            missing[field] = count
    ids = [row.get("id") for row in rows if row.get("id")]
    duplicates = [item for item, count in Counter(ids).items() if count > 1]
    platforms = sorted({row.get("platform") or "unknown" for row in rows})
    warnings: List[str] = []
    if len(rows) < 3:
        warnings.append("Muestra pequeña: tratar cualquier patrón como preliminar.")
    if duplicates:
        warnings.append("Hay IDs duplicados; comprobar si son variantes o duplicaciones de carga.")
    if len(platforms) > 1:
        warnings.append("Hay varias plataformas; comparar tasas y definiciones, no views brutas.")
    if all(row.get("views") is None for row in rows):
        warnings.append("Faltan views/plays en todas las filas; no se pueden calcular tasas de engagement.")
    if all(row.get("average_watch_time_s") is None and row.get("completion_rate") is None for row in rows):
        warnings.append("Faltan métricas de watch time/completion; no se puede diagnosticar retención.")
    if all(row.get("topic") in (None, "") for row in rows):
        warnings.append("Faltan topics; no se puede comparar contenido por tema.")
    return {
        "rows": len(rows),
        "platforms": platforms,
        "duplicate_ids": duplicates,
        "missing_counts": missing,
        "missing_for_goal": missing_fields(rows, goal),
        "warnings": warnings,
    }


def make_insight(
    insight_id: str,
    topic: str,
    observation: str,
    interpretation: str,
    confidence: str,
    hypothesis: str,
    action: str,
    expected_outcome: str,
    measure_next: str,
    missing_data: Sequence[str] = (),
) -> Dict[str, Any]:
    return {
        "insight_id": insight_id,
        "topic": topic,
        "observation": observation,
        "interpretation": interpretation,
        "confidence": confidence,
        "evidence_type": "observed_or_derived",
        "hypothesis": hypothesis,
        "action": action,
        "expected_outcome": expected_outcome,
        "measure_next": measure_next,
        "missing_data": list(missing_data),
    }


def build_insights(rows: Sequence[Dict[str, Any]], goal: str, groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    scored = []
    for row in rows:
        score = goal_score(row, goal)
        if score is not None:
            scored.append((score, row))
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best = scored[0]
        worst_score, worst = scored[-1]
        if len(scored) >= 3:
            delta = best_score - worst_score
            insights.append(make_insight(
                "ranking_001",
                goal,
                f"El mejor registro para el objetivo tiene score relativo {format_pct(best_score)} y el menor {format_pct(worst_score)}; delta {format_pct(delta)}.",
                "Existe dispersión suficiente para priorizar una comparación de formatos o variables, pero el score no prueba una causa.",
                confidence_for(len(scored), relative=True),
                "La diferencia puede estar asociada a hook, topic, audiencia, distribución, audio, edición o azar.",
                "Comparar los metadatos del mejor y peor registro y crear una prueba que cambie una sola variable.",
                "La siguiente variante debería mejorar la métrica primaria del objetivo sin empeorar shares/saves o conversiones.",
                "Retención y métrica primaria por variante, con mismo periodo y audiencia comparable.",
                ["hook_type", "topic", "edit_style", "audio_type"],
            ))
    platform_groups = [item for item in groups.get("platform", []) if item["value"] != "unknown"]
    if len(platform_groups) >= 2:
        ranked = sorted(platform_groups, key=lambda item: item["median"].get("goal_score") or -1, reverse=True)
        top = ranked[0]
        bottom = ranked[-1]
        top_score = top["median"].get("goal_score")
        bottom_score = bottom["median"].get("goal_score")
        if top_score is not None and bottom_score is not None:
            insights.append(make_insight(
                "platform_001",
                "cross_platform",
                f"{top['value']} tiene score mediano {format_pct(top_score)} frente a {format_pct(bottom_score)} en {bottom['value']}.",
                "Hay una diferencia relativa por plataforma; las definiciones de views, watch time y distribución pueden explicar parte del resultado.",
                confidence_for(top["n"] + bottom["n"], relative=True),
                "El packaging, la audiencia, el audio o la métrica de cada plataforma podrían requerir adaptación.",
                "Comparar piezas equivalentes por tasas y adaptar el primer frame, caption y mezcla a cada plataforma.",
                "Mejorar la métrica primaria por plataforma, no sólo la cantidad de views.",
                "Métrica primaria normalizada por plataforma y retención inicial.",
                ["reach", "platform_specific_retention", "audience"],
            ))
    retention_2 = finite_values(rows, "retention_2s")
    retention_6 = finite_values(rows, "retention_6s")
    if retention_2 and retention_6:
        early_drop = median_or_none(retention_2) - median_or_none(retention_6)
        if early_drop is not None and early_drop > 0:
            insights.append(make_insight(
                "retention_001",
                "retention",
                f"La mediana cae {format_pct(early_drop)} entre 2 s y 6 s.",
                "La pérdida ocurre antes de que el vídeo desarrolle su contenido; conviene revisar hook, promesa y contexto inicial.",
                confidence_for(len(retention_2), relative=False),
                "El primer frame o la primera frase pueden no estar pagando la promesa con suficiente rapidez.",
                "Probar una apertura con resultado, conflicto o demostración antes del contexto.",
                "Subir retención a 6 s y reducir la pendiente 2 s → 6 s.",
                "Retención a 2 s y 6 s de dos hooks con el cuerpo constante.",
            ))
    if retention_2 and all(value is not None for value in retention_2):
        if median_or_none(retention_2) is not None:
            insights.append(make_insight(
                "retention_002",
                "hook",
                f"La retención a 2 s mediana es {format_pct(median_or_none(retention_2))}.",
                "Es una lectura de la apertura, no una medida completa de calidad ni de conversión.",
                confidence_for(len(retention_2)),
                "Una apertura más específica puede mejorar la continuación, pero debe mantener la promesa del vídeo.",
                "Crear una variante del primer segundo y mantener igual el resto del montaje.",
                "Subir stayed to watch o retención inicial sin reducir completion.",
                "Retención inicial, average watch time y completion de las variantes.",
            ))
    missing = [item["field"] for item in missing_fields(rows, goal)]
    if missing:
        insights.append(make_insight(
            "data_001",
            "data_quality",
            f"Faltan campos relevantes para el objetivo: {', '.join(missing[:6])}.",
            "El diagnóstico actual puede orientar, pero no distinguir algunas explicaciones alternativas.",
            "preliminary",
            "El patrón podría cambiar al añadir variables creativas, retención por hitos o conversiones.",
            "Pedir el bloque mínimo faltante antes de tomar una decisión irreversible.",
            "Reducir incertidumbre y convertir el siguiente análisis en una comparación más causalmente útil.",
            "Completeness de los campos solicitados y resultado de la siguiente variante.",
            missing,
        ))
    return insights[:8]


def next_questions(rows: Sequence[Dict[str, Any]], goal: str) -> List[str]:
    missing = missing_fields(rows, goal)
    if not missing:
        return [
            "Pásame la variable que cambió en cada variante y la métrica primaria del objetivo para validar el siguiente test.",
            "Si quieres abrir otro topic, elige retention, hook, engagement, creative_editing, audio_captions, conversion o cross_platform.",
        ]
    labels = [item["field"] for item in missing[:5]]
    return [
        f"Para avanzar en {goal}, pásame ahora estas columnas de los vídeos comparables: {', '.join(labels)}.",
        "Indica también si hubo cambios simultáneos de audiencia, fecha, audio, hook o inversión.",
    ]


def analyze(rows: Sequence[Dict[str, Any]], goal: str) -> Dict[str, Any]:
    canonical = [canonicalize(row, index) for index, row in enumerate(rows)]
    for row in canonical:
        row["goal_score"] = goal_score(row, goal)
    quality = data_quality(canonical, goal)
    groups = group_summaries(canonical, goal)
    insights = build_insights(canonical, goal, groups)
    primary = insights[0] if insights else None
    rankings = sorted(
        [
            {
                "id": row.get("id") or f"row_{row['row_number']}",
                "platform": row.get("platform"),
                "score": goal_score(row, goal),
                "views": row.get("views"),
                "average_watch_time_s": row.get("average_watch_time_s"),
                "completion_proxy": row.get("completion_proxy"),
                "topic": row.get("topic"),
                "hook_type": row.get("hook_type"),
            }
            for row in canonical
            if goal_score(row, goal) is not None
        ],
        key=lambda item: item["score"],
        reverse=True,
    )
    return round_value({
        "schema_version": VERSION,
        "goal": goal,
        "input_summary": {
            "rows": len(canonical),
            "platforms": quality["platforms"],
            "date_min": min((row["date"] for row in canonical if row.get("date")), default=None),
            "date_max": max((row["date"] for row in canonical if row.get("date")), default=None),
        },
        "data_quality": quality,
        "group_summaries": groups,
        "rankings": {
            "top": rankings[:5],
            "bottom": list(reversed(rankings[-5:])) if rankings else [],
        },
        "outcome": {
            "priority_action": primary["action"] if primary else None,
            "expected_outcome": primary["expected_outcome"] if primary else None,
            "measure_next": primary["measure_next"] if primary else None,
            "confidence": primary["confidence"] if primary else "insufficient_data",
        },
        "insights": insights,
        "next_questions": next_questions(canonical, goal),
    })


def markdown_report(report: Dict[str, Any]) -> str:
    quality = report["data_quality"]
    lines = [
        "# Short-form metrics analysis",
        "",
        f"**Goal:** {report['goal']}  ",
        f"**Rows:** {report['input_summary']['rows']}  ",
        f"**Platforms:** {', '.join(report['input_summary']['platforms'])}",
        "",
        "## Outcome ejecutivo",
        "",
    ]
    if report["insights"]:
        first = report["insights"][0]
        lines.append(f"- Prioridad: {first['action']}")
        lines.append(f"- Outcome esperado: {first['expected_outcome']}")
        lines.append(f"- Confianza: {first['confidence']}")
    else:
        lines.append("- No hay suficientes señales para un outcome; completar los datos solicitados.")
    lines += ["", "## Calidad de datos", ""]
    for warning in quality["warnings"]:
        lines.append(f"- Aviso: {warning}")
    if not quality["warnings"]:
        lines.append("- No se detectaron avisos básicos.")
    lines += ["", "## Insights", ""]
    for insight in report["insights"]:
        lines += [
            f"### {insight['insight_id']} · {insight['topic']}",
            "",
            f"- Observación: {insight['observation']}",
            f"- Interpretación: {insight['interpretation']}",
            f"- Hipótesis: {insight['hypothesis']}",
            f"- Acción: {insight['action']}",
            f"- Outcome: {insight['expected_outcome']}",
            f"- Medir después: {insight['measure_next']}",
            f"- Confianza: {insight['confidence']}",
            "",
        ]
    lines += ["## Top registros", ""]
    for item in report["rankings"]["top"]:
        lines.append(f"- {item['id']} · score {format_pct(item['score'])} · views {format_num(item['views'])} · completion proxy {format_pct(item['completion_proxy'])}")
    lines += ["", "## Siguiente dato", ""]
    for question in report["next_questions"]:
        lines.append(f"- {question}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze TikTok, Reels and Shorts metrics.")
    parser.add_argument("--input", "-i", required=True, help="JSON/CSV path, or - for stdin.")
    parser.add_argument(
        "--goal",
        choices=("retention", "engagement", "conversion", "creative", "cross-platform", "all"),
        default="all",
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", "-o", help="Optional output path.")
    parser.add_argument("--version", action="version", version=VERSION)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        raw_rows = load_input(args.input)
        if not raw_rows:
            raise ValueError("No records found.")
        report = analyze(raw_rows, args.goal)
        output = markdown_report(report) if args.format == "markdown" else json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            print(output)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
