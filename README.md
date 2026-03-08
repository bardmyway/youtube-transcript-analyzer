# youtube-transcript-analyzer

A small tool to download YouTube captions (auto-subs) and convert them to clean text.

This repo exists because in 2026 YouTube frequently:
- blocks transcript extraction unless you solve a JS challenge (yt-dlp EJS), and
- rate-limits subtitle downloads (HTTP 429).

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Single video
python3 yt_transcripts.py "https://youtu.be/2EMoF4gsscI" --langs en

# Channel (last 365 days)
python3 yt_transcripts.py "https://www.youtube.com/@InvestingSimplified/videos" --days 365 --langs en
```

Outputs are written to `./transcripts/`:
- `*.vtt` raw captions
- `*.txt` cleaned transcript text
- `*.json` per-video metadata
- `summary.json`

## The 2026 Fix: EJS (YouTube JS Challenge)

If you see errors like:
- `This video is not available`
- `challenge solving failed`

…you probably need to enable yt-dlp EJS remote components.

This tool defaults to:

- `--remote-components ejs:github`

You can override:

```bash
python3 yt_transcripts.py "<url>" --remote-components ejs:github
```

## Cookies (optional, but often helps)

If the video is age/region/login gated or you keep seeing missing formats, export cookies and pass them in:

```bash
python3 yt_transcripts.py "<url>" --cookies cookies.txt
```

If you don’t provide `--cookies`, the script attempts `--cookies-from-browser chrome` (can be disabled with `--no-browser-cookies`).

## HTTP 429 Too Many Requests

If you hit:

- `HTTP Error 429: Too Many Requests`

Do this:
1) Stop hammering. Wait 30–120 minutes.
2) Retry with fewer langs (start with just `--langs en`).
3) Use cookies.

The script already sets:
- `--sleep-requests 5`
- `--retries 3`

## Notes

- This tool downloads captions only; it does not scrape comments.
- Auto captions are imperfect: treat the transcript as a rough input, not ground truth.
