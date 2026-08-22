#!/usr/bin/env python3
"""Create a deterministic first-pass edit specification from a short-form brief."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


ARCHETYPE_DEFAULTS = {
    "talking_head": {
        "cut_policy": "Cut on idea or reaction; add B-roll or punch-in only when it clarifies.",
        "hook_source": "Strong direct address, result or thesis.",
        "audio_priority": "Dialogue first; music low and ducked.",
    },
    "tutorial": {
        "cut_policy": "Show result first; cut between observable steps and pause after each result.",
        "hook_source": "Visible result, problem or before/after.",
        "audio_priority": "Clear voice; subtle action SFX; music never masks steps.",
    },
    "product_ugc": {
        "cut_policy": "Problem → use → proof → objection → CTA; keep natural creator performance.",
        "hook_source": "Product in use or visible problem/result.",
        "audio_priority": "Natural creator voice; verify music rights and claims.",
    },
    "reaction": {
        "cut_policy": "Protect setup and reaction timing; cut on emotional change.",
        "hook_source": "Readable face/reaction or conflict.",
        "audio_priority": "Preserve reaction audio; use sparse semantic SFX.",
    },
    "dance_music": {
        "cut_policy": "Cut on meaningful movement/beat; preserve body and choreography readability.",
        "hook_source": "Action already in progress or strongest movement.",
        "audio_priority": "Music leads; keep transients clean and text minimal.",
    },
    "story": {
        "cut_policy": "Continuity of gaze/direction; escalation to reveal; clear payoff.",
        "hook_source": "Conflict, question, consequence or intriguing result.",
        "audio_priority": "Voice and sound design support suspense; silence before reveal is allowed.",
    },
}

PLATFORM_NOTES = {
    "tiktok": "Check native preview, safe zone and commercial music rights.",
    "instagram_reels": "Check full-screen preview, safe zone, captions and licensed-audio status.",
    "youtube_shorts": "Check engaged views/stayed-to-watch interpretation and Content ID status.",
    "multi": "Create a master plus platform previews; do not assume one audio or UI treatment fits all.",
}


def as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def load_brief(path: str) -> Dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Brief must be a JSON object.")
    return data


def bounded_duration(value: Any) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        duration = 20.0
    if duration <= 0:
        raise ValueError("duration_s must be greater than zero.")
    return round(duration, 3)


def end_card_start(duration: float) -> float:
    if duration <= 10:
        return max(0.0, duration - 0.8)
    if duration <= 30:
        return max(0.0, duration - 1.5)
    return max(0.0, duration - 2.0)


def build_timeline(brief: Dict[str, Any], duration: float, archetype: str) -> List[Dict[str, Any]]:
    defaults = ARCHETYPE_DEFAULTS.get(archetype, ARCHETYPE_DEFAULTS["talking_head"])
    hook_type = brief.get("hook_type", "result_first")
    cta = brief.get("cta", "none")
    beats: List[Dict[str, Any]] = []

    def add(start: float, end: float, beat: str, source: str, edit: str, text: str, audio: str, effect: str, test: str) -> None:
        if end <= start:
            return
        beats.append({
            "start_s": round(start, 3),
            "end_s": round(end, 3),
            "beat": beat,
            "source_request": source,
            "edit": edit,
            "text": text,
            "audio": audio,
            "effect": effect,
            "acceptance_test": test,
        })

    hook_end = min(0.7, duration)
    add(
        0.0,
        hook_end,
        "hook",
        f"Find the strongest {hook_type} visual, line, face or action.",
        "Start in motion or at the result; remove greeting, logo-only frame and dead air.",
        "One clear promise or tension line.",
        "Use the natural first sound or a restrained accent; do not let music hide the first words.",
        "No effect by default; use motion already present.",
        "A viewer can identify the reason to continue from frame one.",
    )

    if duration <= 1.0:
        return beats

    promise_end = min(2.5, max(hook_end + 0.1, duration * 0.18))
    add(
        hook_end,
        promise_end,
        "promise",
        "Use the shortest line that states the benefit, question or conflict.",
        "Tighten pauses only when they are accidental; preserve a natural performance.",
        "Headline or caption that clarifies the promise.",
        "Voice dominant; music ducked when dialogue enters.",
        "Optional subtle punch-in if it improves focus.",
        "The promise matches the payoff later in the video.",
    )

    if duration <= 8:
        proof_end = max(promise_end, duration - 1.0)
        add(
            promise_end,
            proof_end,
            "proof_progress",
            "Show the demonstration, transformation or reaction.",
            defaults["cut_policy"],
            "Only the callout needed to understand the proof.",
            defaults["audio_priority"],
            "Use one semantic SFX or beat accent only if it confirms the action.",
            "The proof is readable without replaying.",
        )
        add(
            proof_end,
            duration,
            "payoff",
            "Show the result or punchline.",
            "Let the payoff breathe; loop only if natural.",
            f"One CTA only: {cta}.",
            "Resolve music/SFX so the final meaning remains clear.",
            "No end card unless essential.",
            "The payoff answers the opening promise.",
        )
        return beats

    proof_end = min(8.0, max(promise_end + 0.5, duration * 0.38))
    add(
        promise_end,
        proof_end,
        "proof",
        "Show the first evidence, result, before/after or key action.",
        defaults["cut_policy"],
        "Label a step or fact only when it improves comprehension.",
        defaults["audio_priority"],
        "Use B-roll, match cut or punch-in only when it directs attention.",
        "The viewer sees concrete evidence, not only an assertion.",
    )

    payoff_start = end_card_start(duration)
    progression_end = max(proof_end, payoff_start)
    add(
        proof_end,
        progression_end,
        "progression",
        "Select steps, turns, reactions or examples that advance the promise.",
        "Change visual state every 1–3 s as a test, but cut on semantic beats.",
        "Captions remain 1–2 lines; add short callouts, not paragraphs.",
        "Maintain voice intelligibility; use moderate, congruent music.",
        "Effects must orient, explain, emphasize, hide a cut or reinforce identity.",
        "Each 2–4 s contains progress by information, action, emotion or contrast.",
    )
    add(
        progression_end,
        duration,
        "payoff_cta",
        "Select the strongest result, reveal, summary or next action.",
        "Do not add a long end card; keep one clear action after value.",
        f"Payoff plus one CTA: {cta}.",
        "Resolve the mix; keep the final words intelligible.",
        "No ornament that covers the payoff.",
        "The promise is paid before the CTA.",
    )
    return beats


def build_spec(brief: Dict[str, Any]) -> Dict[str, Any]:
    platform = str(brief.get("platform", "tiktok")).lower()
    objective = str(brief.get("objective", "retention"))
    archetype = str(brief.get("archetype", "talking_head"))
    duration = bounded_duration(brief.get("duration_s", 20))
    speech = as_bool(brief.get("speech"), True)
    captions = as_bool(brief.get("captions"), speech)
    music = as_bool(brief.get("music"), True)
    cta = brief.get("cta", "none")
    defaults = ARCHETYPE_DEFAULTS.get(archetype, ARCHETYPE_DEFAULTS["talking_head"])
    missing = []
    for field in ("source_assets", "transcript_or_timecodes"):
        if not brief.get(field):
            missing.append(field)

    return {
        "schema_version": "0.1.0",
        "brief": {
            "platform": platform,
            "objective": objective,
            "archetype": archetype,
            "duration_s": duration,
            "hook_type": brief.get("hook_type", "result_first"),
            "cta": cta,
        },
        "canvas": {
            "aspect_ratio": "9:16",
            "resolution_preset": "1080x1920",
            "safe_zone": "Keep face, product, headline, captions and payoff in the central UI-safe area.",
            "frame_rate": "Preserve source when possible; verify platform preview.",
        },
        "editorial_strategy": {
            "cut_policy": defaults["cut_policy"],
            "hook_alternatives": ["result_first", "question_or_conflict", "proof_or_transformation"],
            "audio_priority": defaults["audio_priority"],
            "evidence_status": "Timeline seconds and mix values are starting presets to test, not universal optima.",
        },
        "timeline": build_timeline(brief, duration, archetype),
        "captions": {
            "enabled": captions,
            "rules": [
                "Accurate and word/sense synchronized.",
                "1–2 lines, high contrast and safe zone.",
                "12–17 characters per second as comfort preset; test 18–20 only for simple phrases.",
                "Separate headline, subtitles, callouts and CTA.",
            ],
            "sound_off_test": "Meaning must remain usable without sound; do not compensate with dense text.",
        },
        "audio": {
            "speech_present": speech,
            "music_present": music,
            "priority": "voice > music > SFX" if speech else "music/ambience > semantic SFX",
            "loudness_preset": "-16 LUFS-I +/- 2, experimental starting point",
            "true_peak": "<= -1 dBTP",
            "music_ducking": "Start 12–18 dB below dialogue when speech is present, then verify by ear.",
            "checks": ["mobile speaker", "low playback volume", "headphones", "mono compatibility", "rights per platform"],
        },
        "effects": {
            "default_transition": "cut",
            "allowed_roles": ["orient", "explain", "emphasize", "hide_cut", "emotion", "brand"],
            "rule": "Remove any effect with no assigned role.",
        },
        "variants": [
            {"id": "hook_A", "change": "result_first hook", "hold_constant": "body, audio mix and CTA"},
            {"id": "hook_B", "change": "question_or_conflict hook", "hold_constant": "body, audio mix and CTA"},
            {"id": "pace_slow", "change": "20–30% slower visual cadence", "hold_constant": "hook, words and payoff"},
            {"id": "audio_clean", "change": "lower music or silence", "hold_constant": "image, hook and captions"},
        ],
        "qa": [
            "The first frame gives a reason to continue.",
            "The promise is paid before the CTA.",
            "Cuts follow semantic beats and do not break comprehension.",
            "Captions are accurate, legible and not under platform UI.",
            "Voice is intelligible on a small speaker.",
            "No clipping; loudness and true peak are measured after export.",
            "Music, footage, voice and claims are cleared for the destination.",
            "Every effect has a function.",
        ],
        "platform_note": PLATFORM_NOTES.get(platform, "Check current platform preview, UI safe zone, rights and metric definitions."),
        "next_input": missing or ["Transcription/timecodes and the selected source assets are ready for execution."],
    }


def markdown(spec: Dict[str, Any]) -> str:
    brief = spec["brief"]
    lines = [
        "# Edit specification",
        "",
        f"**Platform:** {brief['platform']}  ",
        f"**Objective:** {brief['objective']}  ",
        f"**Archetype:** {brief['archetype']}  ",
        f"**Duration:** {brief['duration_s']} s",
        "",
        "## Strategy",
        "",
        f"- Cut policy: {spec['editorial_strategy']['cut_policy']}",
        f"- Audio: {spec['editorial_strategy']['audio_priority']}",
        f"- Platform: {spec['platform_note']}",
        "",
        "## Timeline",
        "",
        "| Start | End | Beat | Source request | Edit | Text | Audio | Acceptance test |",
        "|---:|---:|---|---|---|---|---|---|",
    ]
    for beat in spec["timeline"]:
        lines.append(
            f"| {beat['start_s']:.3f} | {beat['end_s']:.3f} | {beat['beat']} | "
            f"{beat['source_request']} | {beat['edit']} | {beat['text']} | "
            f"{beat['audio']} | {beat['acceptance_test']} |"
        )
    lines += [
        "",
        "## Audio",
        "",
        f"- Loudness: {spec['audio']['loudness_preset']}",
        f"- True peak: {spec['audio']['true_peak']}",
        f"- Ducking: {spec['audio']['music_ducking']}",
        "",
        "## Variants",
        "",
    ]
    for variant in spec["variants"]:
        lines.append(f"- {variant['id']}: change {variant['change']}; hold constant {variant['hold_constant']}.")
    lines += ["", "## QA", ""]
    lines.extend(f"- [ ] {item}" for item in spec["qa"])
    lines += ["", "## NEXT INPUT", ""]
    lines.extend(f"- {item}" for item in spec["next_input"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a short-form edit specification.")
    parser.add_argument("--input", "-i", required=True, help="Brief JSON path, or - for stdin.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", "-o")
    args = parser.parse_args()
    try:
        spec = build_spec(load_brief(args.input))
        output = markdown(spec) if args.format == "markdown" else json.dumps(spec, ensure_ascii=False, indent=2)
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
