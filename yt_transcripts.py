#!/usr/bin/env python3
"""youtube-transcript-analyzer

Download YouTube captions (auto-subs) as VTT and convert to clean text.

Works for:
- Single video URLs
- Channel/video feeds (yt-dlp supports many URL types)

Key 2026-03 findings:
- Some videos require yt-dlp's EJS challenge solver:
    --remote-components ejs:github
- Subtitles endpoints may return HTTP 429; reduce scope (1 language), sleep, and retry.

Examples:
  # Single video (preferred)
  python3 yt_transcripts.py "https://youtu.be/2EMoF4gsscI" \
    --cookies cookies.txt --langs en

  # Channel (last 365 days)
  python3 yt_transcripts.py "https://www.youtube.com/@InvestingSimplified/videos" \
    --days 365 --langs en

Outputs:
  transcripts/*.vtt     (raw captions)
  transcripts/*.txt     (clean text)
  transcripts/*.json    (per-video metadata)
  transcripts/summary.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

OUTPUT_DIR = Path("transcripts")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download YouTube captions and convert to text")
    p.add_argument("url", help="YouTube video or channel URL")

    # Channel mode filtering (only applies when URL yields multiple videos)
    p.add_argument("--days", type=int, default=30, help="Only include videos uploaded in last N days (yt-dlp --dateafter). Default: 30")

    # Captions
    p.add_argument("--langs", default="en", help="Subtitle languages to request (yt-dlp --sub-langs). Default: en. Example: 'en,en-orig,ru' or 'ru.*,en.*'")
    p.add_argument("--format", default="vtt", help="Subtitle format. Default: vtt")

    # YouTube anti-bot / EJS
    p.add_argument("--remote-components", default="ejs:github", help="Enable yt-dlp EJS solver components. Default: ejs:github")

    # Auth
    p.add_argument("--cookies", default=None, help="Path to cookies.txt (optional). If omitted, tries --cookies-from-browser chrome")
    p.add_argument("--no-browser-cookies", action="store_true", help="Do not attempt --cookies-from-browser chrome")

    # Throttling / retries
    p.add_argument("--sleep-requests", type=float, default=5.0, help="yt-dlp --sleep-requests seconds. Default: 5")
    p.add_argument("--sleep-interval", type=float, default=0.0, help="yt-dlp --sleep-interval seconds. Default: 0")
    p.add_argument("--max-sleep-interval", type=float, default=0.0, help="yt-dlp --max-sleep-interval seconds. Default: 0")
    p.add_argument("--retries", type=int, default=3, help="yt-dlp --retries. Default: 3")
    p.add_argument("--fragment-retries", type=int, default=3, help="yt-dlp --fragment-retries. Default: 3")

    # Output
    p.add_argument("--out", default=str(OUTPUT_DIR), help="Output directory. Default: ./transcripts")

    return p.parse_args()


def parse_vtt(vtt_text: str) -> str:
    """Convert VTT to clean, de-duplicated text.

    Removes:
    - WEBVTT header
    - timestamps / cue numbers
    - tags, including inline <c> and <00:00:..> chunks

    Also de-duplicates consecutive repeated lines (rolling captions).
    """
    # Drop header
    vtt_text = re.sub(r"^WEBVTT.*?\n\n", "", vtt_text, flags=re.DOTALL)

    lines = vtt_text.splitlines()
    clean: List[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if re.search(r"\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}", line):
            continue
        # strip all tags
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line:
            continue
        clean.append(line)

    # Deduplicate consecutive identical lines
    deduped: List[str] = []
    prev: Optional[str] = None
    for line in clean:
        if line != prev:
            deduped.append(line)
            prev = line

    return " ".join(deduped)


def run(cmd: List[str]) -> int:
    # Print the command in a copy/paste friendly way
    print("\n$ " + " ".join(cmd) + "\n")
    proc = subprocess.run(cmd)
    return proc.returncode


def main() -> int:
    args = parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    dateafter = (datetime.now() - timedelta(days=args.days)).strftime("%Y%m%d")

    print(f"📡 URL: {args.url}")
    print(f"📁 Output: {out_dir.resolve()}")
    print(f"🗓️  Channel filtering: last {args.days} days (since {dateafter})")
    print(f"🌐 Languages: {args.langs}")
    print(f"🧩 remote-components: {args.remote_components}")

    # Output template: include upload_date when available; yt-dlp will fill it for playlists/channels.
    out_tmpl = str(out_dir / "%(upload_date)s_%(id)s_%(title).60s.%(ext)s")

    base_cmd = [
        "yt-dlp",
        "--remote-components", args.remote_components,
        "--skip-download",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs", args.langs,
        "--sub-format", args.format,
        "--sleep-requests", str(args.sleep_requests),
        "--retries", str(args.retries),
        "--fragment-retries", str(args.fragment_retries),
        "--output", out_tmpl,
    ]

    # Optional sleeps
    if args.sleep_interval and args.max_sleep_interval:
        base_cmd += [
            "--sleep-interval", str(args.sleep_interval),
            "--max-sleep-interval", str(args.max_sleep_interval),
        ]

    # Date filter is harmless for single videos (ignored if no upload_date?), but keep it for channels.
    base_cmd += ["--dateafter", dateafter]

    # Cookies: prefer explicit cookies.txt if provided; else try browser cookies unless disabled.
    if args.cookies:
        base_cmd += ["--cookies", args.cookies]
    elif not args.no_browser_cookies:
        # This frequently helps with availability; may still be rate-limited.
        base_cmd += ["--cookies-from-browser", "chrome"]

    cmd = base_cmd + [args.url]

    print("⬇️  Downloading caption files...")
    rc = run(cmd)
    if rc != 0:
        print("\n⚠️  yt-dlp failed. Common fixes:")
        print("- Ensure you used: --remote-components ejs:github")
        print("- Try cookies.txt from a logged-in browser")
        print("- If you see HTTP 429: stop retrying, wait 30–120 minutes, then run again")
        return rc

    # Convert VTT -> TXT + metadata
    vtt_files = sorted(out_dir.glob("*.vtt"))
    print(f"\n✅ Found {len(vtt_files)} .vtt files. Converting to text...\n")

    results = []
    for vtt_path in vtt_files:
        vtt_text = vtt_path.read_text(encoding="utf-8", errors="ignore")
        transcript = parse_vtt(vtt_text)

        txt_path = vtt_path.with_suffix(".txt")
        txt_path.write_text(transcript, encoding="utf-8")

        # Try to parse filename: upload_date_id_title
        filename = vtt_path.stem
        parts = filename.split("_", 2)
        if len(parts) >= 3 and re.fullmatch(r"\d{8}", parts[0]):
            upload_date, video_id, title = parts[0], parts[1], parts[2]
        else:
            upload_date, video_id, title = "unknown", parts[0], parts[-1]

        word_count = len(transcript.split())

        meta = {
            "upload_date": upload_date,
            "video_id": video_id,
            "title": title,
            "word_count": word_count,
            "vtt_file": vtt_path.name,
            "transcript_file": txt_path.name,
            "source_url": args.url,
            "generated_at": datetime.now().isoformat(),
            "langs": args.langs,
        }
        meta_path = vtt_path.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        print(f"  ✓ {video_id} — {title[:60]} — {word_count:,} words")
        results.append(meta)

    summary = {
        "url": args.url,
        "days": args.days,
        "dateafter": dateafter,
        "date_ran": datetime.now().isoformat(),
        "total_vtt": len(vtt_files),
        "total_transcripts": len(results),
        "total_words": sum(r["word_count"] for r in results),
        "transcripts": results,
        "notes": {
            "ejs_required": "Some videos require --remote-components ejs:github (YouTube JS challenge).",
            "rate_limit": "If you hit HTTP 429, wait 30–120 minutes, reduce languages, and retry once.",
        },
    }

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\n🎉 Done! Saved {len(results)} transcripts")
    print(f"📊 Total words: {summary['total_words']:,}")
    print(f"📋 Summary: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
