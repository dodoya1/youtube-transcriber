[日本語](README.md)

# youtube-transcriber

A Python CLI tool that transcribes YouTube / X(Twitter) videos and local media files into Markdown files under `outputs/`. For English audio, it also generates a Japanese translation via the DeepL API. A separate `translate` subcommand lets you translate existing Markdown files after the fact.

## Key Features

- **Multi-source input**: YouTube videos/playlists, X(Twitter) tweets with video, and local video/audio files all flow through the same pipeline
- **Hybrid transcription**: For YouTube, fetches captions via `youtube-transcript-api` first; falls back to downloading audio with `yt-dlp` and running `faster-whisper` locally. X and local files always use Whisper
- **Whisper-only mode**: `--whisper-only` skips caption fetching and always uses Whisper (for accuracy over speed)
- **Model selection**: `--model` lets you choose the Whisper model size (`tiny` / `base` / `small` / `medium` / `large-v3`)
- **Playlist support**: Automatically detects YouTube video vs. playlist URLs and batch-processes all videos
- **Local file support**: The `local` subcommand batch-processes video/audio files under `inputs/` (mp4, mov, mkv, webm, avi, mp3, wav, m4a, flac, ogg, opus, aac, etc.)
- **Japanese translation (DeepL)**: Adds a `-ja.md` file for English transcripts; skips Japanese content
- **Translate-only mode**: The `translate` subcommand converts existing `.md` files to Japanese
- **Failure report**: One item's failure never stops the rest; a summary of successes/skips/failures is printed at the end
- **Existing file protection**: Skips by default; use `--force` to overwrite

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (dependency management & execution)
- `ffmpeg` (required for YouTube/X audio extraction; not required for the `local` subcommand)
- (Optional) DeepL API Key — only needed for English-to-Japanese translation

On macOS: `brew install ffmpeg uv`

## Installation

```bash
git clone <repo-url>
cd youtube-transcriber
uv venv
uv sync --extra dev
cp .env.example .env   # Set DEEPL_API_KEY= (optional)
```

## Usage

### Transcription (`transcribe`) — YouTube / X(Twitter)

```bash
# YouTube single video
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# YouTube playlist
uv run python -m transcriber transcribe "https://www.youtube.com/playlist?list=PLxxxxxxxx"

# X(Twitter) tweet video
uv run python -m transcriber transcribe "https://x.com/<user>/status/<tweet_id>"

# twitter.com domain also works
uv run python -m transcriber transcribe "https://twitter.com/<user>/status/<tweet_id>"

# Mix YouTube and X URLs freely
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=aaa" "https://x.com/u/status/123"

# Skip translation, output original text only
uv run python -m transcriber transcribe --no-translate "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Overwrite existing output
uv run python -m transcriber transcribe --force "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Specify output directory and model size
uv run python -m transcriber transcribe --output-dir ./my-outputs --model small "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Always use Whisper (skip caption fetching) for YouTube
uv run python -m transcriber transcribe --whisper-only "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Whisper-only with a larger model for higher accuracy
uv run python -m transcriber transcribe --whisper-only --model large-v3 "https://www.youtube.com/watch?v=xxxxxxxxxxx"
```

> **NOTE:** URLs contain query parameters (`&`) that are special in most shells. Always wrap URLs in double quotes (`"..."`) to prevent unexpected behavior.
>
> **NOTE (X):** Tweets rarely have captions, so X URLs always go directly to Whisper (same behavior as `--whisper-only`). Private or deleted tweets are recorded in the failure list and processing continues for the rest.

Options:

| Option                | Description                                           |
| --------------------- | ----------------------------------------------------- |
| `--output-dir <path>` | Output directory (default: `outputs`)                 |
| `--model <size>`      | Whisper model size (default: `medium`)                |
| `--force`             | Overwrite existing files                              |
| `--whisper-only`      | Skip caption fetching; always transcribe with Whisper |
| `--no-translate`      | Skip DeepL translation even for English videos        |

### Local files (`local`) — video / audio files

Drop video/audio files into the `inputs/` folder (or point `--inputs-dir` elsewhere) and run the `local` subcommand to transcribe them all with Whisper. You can also list explicit paths.

```bash
# Recursively scan inputs/ (default)
uv run python -m transcriber local

# Explicit file paths
uv run python -m transcriber local inputs/sample.mp4 /path/to/another.mp3

# Scan a different directory
uv run python -m transcriber local --inputs-dir ./my-media

# Specify the Whisper model and output directory
uv run python -m transcriber local --model large-v3 --output-dir ./my-outputs

# Overwrite existing output and skip translation
uv run python -m transcriber local --force --no-translate
```

Supported extensions:

- **Video**: `.mp4` / `.mov` / `.mkv` / `.webm` / `.avi` / `.m4v` / `.mpg` / `.mpeg` / `.ts` / `.3gp` / `.wmv`
- **Audio**: `.mp3` / `.wav` / `.m4a` / `.flac` / `.ogg` / `.opus` / `.aac` / `.wma`

> **NOTE:** The `local` subcommand does **not** require `ffmpeg` to be installed. `faster-whisper` ships with PyAV (bundled FFmpeg libraries) which decodes video and audio directly. Unsupported extensions or missing paths are recorded in the failure list.

### Translation only (`translate`)

Translates existing `.md` files to Japanese via DeepL and writes `<filename>-ja.md` in the **same folder**. Input files are never modified or moved.

```bash
# Single file
uv run python -m transcriber translate outputs/foo-abc123/foo-abc123.md

# Multiple files
uv run python -m transcriber translate outputs/a.md outputs/b.md outputs/c.md

# Overwrite existing -ja.md
uv run python -m transcriber translate --force outputs/foo.md
```

Use cases:

- Re-translate videos that failed due to DeepL monthly quota during `transcribe`
- Translate Markdown files originally created with `--no-translate`
- Batch-translate hand-written English Markdown files

Files with `language: ja` in their frontmatter or filenames ending in `-ja` are silently skipped (no error).

## Output Examples

### English video (with translation) — subfolder layout

```
outputs/
└── Sample Talk-abcdef/
    ├── Sample Talk-abcdef.md      # Original
    └── Sample Talk-abcdef-ja.md   # Japanese translation
```

### Japanese video (no translation) — flat layout

```
outputs/
└── サンプル動画-abcdef.md
```

Each Markdown file uses YAML frontmatter + H1 heading + plain body (no timestamps):

```markdown
---
title: "Sample Talk"
url: https://www.youtube.com/watch?v=abcdefghijk
channel: "Sample Channel"
upload_date: 2025-01-15
duration: "00:12:34"
language: en
source: captions
origin: youtube
---

# Sample Talk

Hello world, this is the transcript body...
```

The `origin` key indicates the input source type (`youtube` / `x` / `local`). For local files, `url`, `channel`, and `duration` are omitted. Translated files (`-ja.md`) additionally include `language: ja` and `translated_from: en`.

## Directory Structure

```
youtube-transcriber/
├── src/
│   └── transcriber/
│       ├── __init__.py
│       ├── __main__.py              # `python -m transcriber` entry point
│       ├── cli.py                   # argparse subcommands + orchestration
│       ├── types.py                 # All dataclasses (frozen)
│       ├── url_parser.py            # URL classification & ID extraction (YouTube / X)
│       ├── youtube_client.py        # yt-dlp wrapper (YouTube / X)
│       ├── captions.py              # youtube-transcript-api fetcher
│       ├── whisper_transcribe.py    # faster-whisper transcription
│       ├── translator.py            # DeepL translation core
│       ├── translate_file.py        # translate subcommand implementation
│       ├── local_source.py          # Local media file scanning & synthetic metadata
│       ├── markdown_writer.py       # Markdown generation & filename sanitization
│       ├── language.py              # Language detection / normalization
│       └── run_report.py            # Success/skip/failure aggregation & report
├── tests/
│   ├── test_url_parser.py
│   ├── test_markdown_writer.py
│   ├── test_language.py
│   ├── test_run_report.py
│   ├── test_translate_file.py
│   └── test_local_source.py
├── inputs/                          # Local input drop zone (git-ignored)
│   └── .gitkeep
├── outputs/                         # Generated files (git-ignored)
│   └── .gitkeep
├── plan/                            # Implementation plans
├── pyproject.toml
├── uv.lock
├── .env.example                     # DEEPL_API_KEY=
├── .gitignore
├── README.md
├── README.en.md
└── CLAUDE.md
```

## How It Works

1. Classify each input: YouTube URL (video/playlist), X(Twitter) URL, or local file
2. YouTube: fetch captions (`ja` → `en` → first available). If unavailable, download audio with `yt-dlp` and transcribe with Whisper
3. X(Twitter): skip captions and always download audio with `yt-dlp` → Whisper
4. Local files: hand the file path directly to `faster-whisper`; PyAV decodes video/audio without a separate ffmpeg step
5. Determine the final language heuristically (ratio of Hiragana/Katakana/CJK characters)
6. Write Markdown output; if English, also generate a Japanese translation via DeepL
7. Catch exceptions per item and print a `RunReport` summary at the end

## Running Tests

```bash
uv run pytest
```

Network- and model-dependent modules (`youtube_client`, `whisper_transcribe`, `translator`, `captions`) are excluded from unit tests. Only pure functions and formatting logic are covered.

## Troubleshooting

| Symptom                                     | Solution                                                                       |
| ------------------------------------------- | ------------------------------------------------------------------------------ |
| `ffmpeg が見つかりません` on startup        | Install ffmpeg (e.g., `brew install ffmpeg`). Not needed for `local` subcommand |
| First Whisper run is very slow              | The `medium` model (~1.5 GB) is downloaded automatically on first use          |
| Large local files take a long time          | Trade off with `--model small`/`tiny` for speed or `large-v3` for accuracy    |
| DeepL monthly character limit reached       | The item is recorded as a failure; re-run with `translate` after quota resets  |
| Want to re-translate only                   | Use the `translate` subcommand with the original `.md` file                    |
| Re-running the same URL / file does nothing | Files are skipped by default; use `--force` to overwrite                       |
| `DEEPL_API_KEY` not set                     | Translation is silently skipped; only the original Markdown is generated       |
| Want to process private X tweets            | Not supported yet; they are recorded as failures                               |

## License

MIT License
