#!/usr/bin/env python3
"""Cut silences from a graded video (jump-cut) → shorter, tighter video.

AUDIO-FIRST (recomendado, ver SKILL.md paso 2):
  El timing de cortes es FUENTE DE VERDAD y se calcula UNA sola vez sobre el WAV:
    compress_silences.py --input out/audio.wav --timing-only --save-timing out/silence_timing.json
  Después se aplica a CUALQUIER encode del vídeo sin re-detectar:
    compress_silences.py --input 02_graded.mp4 --output 02c_compressed.mp4 --load-timing out/silence_timing.json
  Así un cambio de calidad (--quality) o de resolución NUNCA mueve los cortes:
  nada de re-transcribir ni regenerar subs/títulos/overlays.
"""

import argparse
import datetime
import json
import re
import subprocess
import sys

FFMPEG = r"C:/ffmpeg/bin/ffmpeg.exe"
FFPROBE = r"C:/ffmpeg/bin/ffprobe.exe"

QUALITY = {
    "fast": {"preset": "medium", "crf": 19, "abitrate": "160k"},
    "max":  {"preset": "slow", "crf": 15, "abitrate": "320k"},
}


def _probe_rms(path, start, end):
    """Probe RMS dB of audio in [start, end]."""
    cmd = [
        FFMPEG, "-i", path,
        "-ss", str(start), "-to", str(end),
        "-af", "astats=metadata=1:reset=0,ametadata=print:key=lavfi.astats.Overall.RMS_level",
        "-f", "null", "-"
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    vals = re.findall(r"lavfi.astats.Overall.RMS_level=([-\d.]+)", r.stderr)
    if vals:
        return float(vals[-1])
    return 0.0


def _find_speech_start(path, duration):
    """Find where speech starts using silencedetect with aggressive threshold."""
    cmd = [
        FFMPEG, "-i", path,
        "-af", "silencedetect=noise=-40dB:d=0.1",
        "-t", str(min(5.0, duration)),
        "-f", "null", "-"
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", r.stderr)]
    if ends:
        return ends[-1]
    return None


def get_duration(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error",
         "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True
    )
    return float(r.stdout.strip())


def detect_silences(path, noise_db, min_dur):
    """Run ffmpeg silencedetect and return list of (silence_start, silence_end)."""
    print(f"  Running silencedetect with noise={noise_db}dB, min_duration={min_dur}s")
    cmd = [
        FFMPEG, "-i", path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
        "-f", "null", "-"
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    stderr = r.stderr

    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", stderr)]

    silences = []
    for s, e in zip(starts, ends):
        silences.append((s, e))
    if len(starts) > len(ends):
        silences.append((starts[-1], get_duration(path)))
    return silences


def build_keep_segments(silences, duration, pad, keep, min_silence):
    """
    Given silences, compute the segments of audio/video to KEEP.
    - Initial silence: keep at most `pad` seconds from the end of initial silence.
    - Internal silence (>= min_silence): keep `keep` seconds split half before/after.
    - Final silence: keep at most `pad` seconds from the start of final silence.
    """
    keep_half = keep / 2.0
    segments = []
    current = 0.0

    has_initial = len(silences) > 0 and silences[0][0] < 0.1

    for i, (s_start, s_end) in enumerate(silences):
        is_initial = (i == 0 and has_initial)
        is_final = (i == len(silences) - 1 and s_end >= duration - 0.2)

        if is_initial:
            current = s_end - pad
            print(f"    (initial: skipping 0.000 to {current:.3f})")
        elif is_final:
            keep_until = min(s_end, s_start + pad)
            segments.append((current, keep_until))
            current = keep_until
        else:
            segments.append((current, s_start + keep_half))
            current = s_end - keep_half

    if current < duration - 0.01:
        segments.append((current, duration))

    merged = []
    for seg in segments:
        if merged and seg[0] - merged[-1][1] < 0.05:
            merged[-1] = (merged[-1][0], seg[1])
        else:
            merged.append(seg)

    return merged


def run_timing(input_path, min_silence, keep, pad, noise_db, trim_start):
    """Detect silences and compute keep segments. Returns timing dict."""
    duration = get_duration(input_path)
    print(f"Input duration: {duration:.3f}s")

    silences = detect_silences(input_path, noise_db=noise_db, min_dur=min_silence)
    print(f"Detected {len(silences)} silence regions:")
    for i, (s, e) in enumerate(silences):
        print(f"  [{i}] {s:.3f} - {e:.3f}  ({e - s:.3f}s)")

    # Try auto-detect initial silence
    if not silences or silences[0][0] > 0.5:
        probe_rms = _probe_rms(input_path, 0.0, min(2.0, duration * 0.3))
        print(f"  Initial 2s RMS: {probe_rms:.1f} dB")
        if probe_rms < -32:
            initial_end = _find_speech_start(input_path, duration)
            if initial_end and initial_end > 0.3:
                silences.insert(0, (0.0, initial_end))
                print(f"  [auto] initial silence 0.000 - {initial_end:.3f}")
        else:
            print(f"  Note: initial RMS too high for auto-detection")

    # Manual initial silence trim (for noisy environments)
    if trim_start is not None and trim_start > 0.3:
        trim_end = trim_start - pad
        if trim_end > 0:
            if silences and silences[0][0] < 0.1:
                silences.pop(0)
            silences.insert(0, (0.0, trim_end))
            print(f"  [manual] initial silence 0.000 - {trim_end:.3f} (speech at {trim_start:.3f})")

    # Filter out very short internal silences unless initial/final
    filtered = []
    for i, (s, e) in enumerate(silences):
        is_initial = (i == 0)
        is_final = (i == len(silences) - 1 and e >= duration - 0.2)
        if (e - s) >= min_silence or is_initial or is_final:
            filtered.append((s, e))
    silences = filtered

    segments = build_keep_segments(silences, duration, pad, keep, min_silence) if silences else []
    print(f"\nKeep segments ({len(segments)}):")
    total_keep = 0.0
    for i, (s, e) in enumerate(segments):
        total_keep += e - s
        print(f"  [{i}] {s:.3f} - {e:.3f}  ({e - s:.3f}s)")
    print(f"\nTotal kept: {total_keep:.3f}s | Removed: {duration - total_keep:.3f}s")

    return {
        "duration": round(duration, 6),
        "params": {"noise_db": noise_db, "min_silence": min_silence,
                   "keep": keep, "pad": pad, "trim_start": trim_start},
        "silences": [[round(s, 6), round(e, 6)] for s, e in silences],
        "segments": [[round(s, 6), round(e, 6)] for s, e in segments],
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def load_timing(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    p = data.get("params", {})
    print(f"  Loaded timing from {path}: {len(data['silences'])} silences, "
          f"{len(data['segments'])} segments (noise={p.get('noise_db')}dB, "
          f"keep={p.get('keep')}, pad={p.get('pad')})")
    # Rebuild segments from silences using the stored params (keeps merge logic identical)
    segs = build_keep_segments(
        [tuple(s) for s in data["silences"]], data["duration"],
        p.get("pad", 0.20), p.get("keep", 0.18), p.get("min_silence", 0.35))
    data["segments"] = [[round(s, 6), round(e, 6)] for s, e in segs]
    return data


def encode_cuts(input_path, output_path, segments, quality):
    """Trim/concat keep segments into output_path (A/V siempre en par)."""
    if not segments:
        print("No segments to keep, copying input as-is.")
        subprocess.run([
            FFMPEG, "-y", "-i", input_path,
            "-c", "copy", "-movflags", "+faststart", output_path
        ], check=True)
        print(f"Output duration: {get_duration(output_path):.3f}s (unchanged)")
        return

    q = QUALITY[quality]
    filter_parts = []
    v_labels, a_labels = [], []
    for i, (s, e) in enumerate(segments):
        filter_parts.append(
            f"[0:v]trim=start={s:.6f}:end={e:.6f},setpts=PTS-STARTPTS[v{i}]"
        )
        filter_parts.append(
            f"[0:a]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[a{i}]"
        )
        v_labels.append(f"[v{i}]")
        a_labels.append(f"[a{i}]")

    n = len(segments)
    concat_chain = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_parts.append(
        f"{concat_chain}concat=n={n}:v=1:a=1[vout][aout]"
    )
    fc = ";\n".join(filter_parts)

    cmd = [
        FFMPEG, "-y", "-i", input_path,
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", q["preset"], "-crf", str(q["crf"]),
        "-c:a", "aac", "-b:a", q["abitrate"],
        "-movflags", "+faststart",
        "-shortest",
        output_path
    ]

    print(f"\nRunning ffmpeg compress ({quality})...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFMPEG STDERR:\n{result.stderr[-5000:]}")
        sys.exit(f"FAIL: ffmpeg exited with {result.returncode}")

    out_dur = get_duration(output_path)
    dur = get_duration(input_path)
    print(f"\nOutput duration: {out_dur:.3f}s")
    print(f"Saved: {dur - out_dur:.3f}s ({(dur - out_dur) / dur * 100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description="Silence timing (audio-first) + jump-cut compress",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Audio-first:\n"
            "  1) compress_silences.py --input out/audio.wav --timing-only "
            "--save-timing out/silence_timing.json\n"
            "  2) compress_silences.py --input 02_graded.mp4 --output 02c_compressed.mp4 "
            "--load-timing out/silence_timing.json\n"
            "Re-encodes re-use the same timing: cuts never move."
        ))
    parser.add_argument("--input", required=True, help="Input video (o WAV con --timing-only)")
    parser.add_argument("--output", default=None, help="Output video path")
    parser.add_argument("--min-silence", type=float, default=0.35, help="Minimum silence duration (s)")
    parser.add_argument("--keep", type=float, default=0.18, help="Silence to keep (s, split half/half)")
    parser.add_argument("--pad", type=float, default=0.20, help="Max pad for initial/final silence (s)")
    parser.add_argument("--noise", type=float, default=-25, help="Noise threshold in dB (default: -25)")
    parser.add_argument("--trim-start", type=float, default=None,
                        help="Manually set initial speech start (trims silence before this point)")
    parser.add_argument("--timing-only", action="store_true",
                        help="Only compute/save timing, do not encode video")
    parser.add_argument("--save-timing", default=None,
                        help="Write timing JSON (silences+segments) to this path")
    parser.add_argument("--load-timing", default=None,
                        help="Use timing JSON instead of re-detecting (stable cuts)")
    parser.add_argument("--quality", default="max", choices=["fast", "max"],
                        help="Encode quality (default: max = slow crf15 aac320k)")
    args = parser.parse_args()

    if args.timing_only and not args.save_timing and not args.load_timing:
        sys.exit("ERROR: --timing-only requiere --save-timing <path> (o --load-timing <path>)")
    if not args.timing_only and not args.output:
        sys.exit("ERROR: --output required (o usa --timing-only)")

    if args.load_timing:
        timing = load_timing(args.load_timing)
    else:
        timing = run_timing(args.input, args.min_silence, args.keep, args.pad,
                            args.noise, args.trim_start)
        if args.save_timing:
            with open(args.save_timing, "w", encoding="utf-8") as f:
                json.dump(timing, f, indent=2)
            print(f"\nTiming saved to {args.save_timing}")

    if args.timing_only:
        print(f"Timing-only: {len(timing['segments'])} keep segments. Done.")
        return

    encode_cuts(args.input, args.output, [tuple(s) for s in timing["segments"]], args.quality)


if __name__ == "__main__":
    main()
