from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "plugins/short-form-metrics-insights/scripts/analyze_metrics.py"
EDIT_SPEC = ROOT / "plugins/short-form-editing-science/scripts/build_edit_spec.py"


def run_json(script: Path, payload: object, *args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(script), "--input", "-", *args],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_metrics_plugin_emits_outcome_and_next_questions() -> None:
    payload = {
        "videos": [
            {
                "id": "a",
                "platform": "tiktok",
                "duration_s": 20,
                "views": 1000,
                "average_watch_time_s": 8,
                "retention_2s": "70%",
                "retention_6s": "50%",
                "shares": 20,
                "saves": 10,
            },
            {
                "id": "b",
                "platform": "tiktok",
                "duration_s": 20,
                "views": 900,
                "average_watch_time_s": 4,
                "retention_2s": "45%",
                "retention_6s": "20%",
                "shares": 5,
                "saves": 2,
            },
            {
                "id": "c",
                "platform": "tiktok",
                "duration_s": 20,
                "views": 1200,
                "average_watch_time_s": 9,
                "retention_2s": "75%",
                "retention_6s": "60%",
                "shares": 30,
                "saves": 18,
            },
        ]
    }
    report = run_json(METRICS, payload, "--goal", "retention", "--format", "json")
    assert report["input_summary"]["rows"] == 3
    assert report["outcome"]["priority_action"]
    assert report["insights"]
    assert report["next_questions"]


def test_metrics_plugin_accepts_csv() -> None:
    csv_text = (
        "id,platform,duration_s,views,average_watch_time_s,retention_2s,shares\n"
        "a,tiktok,15,1000,6,70%,30\n"
        "b,tiktok,15,800,3,40%,5\n"
        "c,tiktok,15,1200,7,75%,40\n"
    )
    result = subprocess.run(
        [sys.executable, str(METRICS), "--input", "-", "--goal", "retention", "--format", "json"],
        input=csv_text,
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["input_summary"]["rows"] == 3
    assert report["data_quality"]["platforms"] == ["tiktok"]


def test_edit_spec_contains_timeline_variants_and_qa() -> None:
    brief = {
        "platform": "instagram_reels",
        "objective": "retention",
        "archetype": "talking_head",
        "duration_s": 20,
        "speech": True,
        "captions": True,
        "music": True,
        "cta": "follow",
        "source_assets": ["clip_01"],
    }
    spec = run_json(EDIT_SPEC, brief, "--format", "json")
    beats = [item["beat"] for item in spec["timeline"]]
    assert beats[0] == "hook"
    assert "promise" in beats
    assert "payoff_cta" in beats
    assert len(spec["variants"]) >= 3
    assert spec["audio"]["true_peak"] == "<= -1 dBTP"
    assert spec["qa"]
    assert "transcript_or_timecodes" in spec["next_input"]
