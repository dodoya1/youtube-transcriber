[日本語](README.md)

# youtube-transcriber

A Python CLI tool that transcribes YouTube videos and playlists into Markdown files under `outputs/`. For English videos, it also generates a Japanese translation via the DeepL API. A separate `translate` subcommand lets you translate existing Markdown files after the fact.

## Key Features

- **Hybrid transcription**: Fetches captions via `youtube-transcript-api` first; falls back to downloading audio with `yt-dlp` and running `faster-whisper` locally
- **Whisper-only mode**: `--whisper-only` skips caption fetching and always uses Whisper (for accuracy over speed)
- **Model selection**: `--model` lets you choose the Whisper model size (`tiny` / `base` / `small` / `medium` / `large-v3`)
- **Playlist support**: Automatically detects video URLs vs. playlist URLs and batch-processes all videos
- **Japanese translation (DeepL)**: Adds a `-ja.md` file for English transcripts; skips Japanese content
- **Translate-only mode**: The `translate` subcommand converts existing `.md` files to Japanese
- **Failure report**: One video's failure never stops the rest; a summary of successes/skips/failures is printed at the end
- **Existing file protection**: Skips by default; use `--force` to overwrite

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (dependency management & execution)
- `ffmpeg` (required for audio extraction)
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

### Transcription (`transcribe`)

```bash
# Single video
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Playlist
uv run python -m transcriber transcribe "https://www.youtube.com/playlist?list=PLxxxxxxxx"

# Multiple URLs
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=aaa" "https://www.youtube.com/watch?v=bbb"

# Skip translation, output original text only
uv run python -m transcriber transcribe --no-translate "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Overwrite existing output
uv run python -m transcriber transcribe --force "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Specify output directory and model size
uv run python -m transcriber transcribe --output-dir ./my-outputs --model small "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Always use Whisper (skip caption fetching)
uv run python -m transcriber transcribe --whisper-only "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Whisper-only with a larger model for higher accuracy
uv run python -m transcriber transcribe --whisper-only --model large-v3 "https://www.youtube.com/watch?v=xxxxxxxxxxx"
```

> **NOTE:** URLs contain query parameters (`&`) that are special in most shells. Always wrap URLs in double quotes (`"..."`) to prevent unexpected behavior.

Options:

| Option                | Description                                           |
| --------------------- | ----------------------------------------------------- |
| `--output-dir <path>` | Output directory (default: `outputs`)                 |
| `--model <size>`      | Whisper model size (default: `medium`)                |
| `--force`             | Overwrite existing files                              |
| `--whisper-only`      | Skip caption fetching; always transcribe with Whisper |
| `--no-translate`      | Skip DeepL translation even for English videos        |

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
---

# Sample Talk

Hello world, this is the transcript body...
```

Translated files (`-ja.md`) additionally include `language: ja` and `translated_from: en`.

## Directory Structure

```
youtube-transcriber/
├── src/
│   └── transcriber/
│       ├── __init__.py
│       ├── __main__.py              # `python -m transcriber` entry point
│       ├── cli.py                   # argparse subcommands + orchestration
│       ├── types.py                 # All dataclasses (frozen)
│       ├── url_parser.py            # URL classification & ID extraction
│       ├── youtube_client.py        # yt-dlp wrapper (metadata/playlist/audio)
│       ├── captions.py              # youtube-transcript-api fetcher
│       ├── whisper_transcribe.py    # faster-whisper fallback
│       ├── translator.py            # DeepL translation core
│       ├── translate_file.py        # translate subcommand implementation
│       ├── markdown_writer.py       # Markdown generation & filename sanitization
│       ├── language.py              # Language detection / normalization
│       └── run_report.py            # Success/skip/failure aggregation & report
├── tests/
│   ├── test_url_parser.py
│   ├── test_markdown_writer.py
│   ├── test_language.py
│   ├── test_run_report.py
│   └── test_translate_file.py
├── outputs/                         # Generated files (git-ignored)
│   └── .gitkeep
├── pyproject.toml
├── uv.lock
├── .env.example                     # DEEPL_API_KEY=
├── .gitignore
├── README.md
├── README.en.md
├── CLAUDE.md
└── plan.md
```

## How It Works

1. Classify each input URL as a video or playlist; expand playlists into individual videos
2. For each video, try fetching captions via `youtube-transcript-api` (`ja` → `en` → first available)
3. If captions are unavailable (or `--whisper-only` is set), download audio with `yt-dlp` and transcribe locally with `faster-whisper` (default `medium`; changeable via `--model`)
4. Determine the final language heuristically (ratio of Hiragana/Katakana/CJK characters)
5. Write Markdown output; if the language is English, also generate a Japanese translation via DeepL
6. Catch exceptions per video and print a `RunReport` summary at the end

## Running Tests

```bash
uv run pytest
```

Network- and model-dependent modules (`youtube_client`, `whisper_transcribe`, `translator`, `captions`) are excluded from unit tests. Only pure functions and formatting logic are covered.

## Troubleshooting

| Symptom                               | Solution                                                                       |
| ------------------------------------- | ------------------------------------------------------------------------------ |
| `ffmpeg が見つかりません` on startup  | Install ffmpeg (e.g., `brew install ffmpeg`)                                   |
| First Whisper run is very slow        | The `medium` model (~1.5 GB) is downloaded automatically on first use          |
| DeepL monthly character limit reached | The video is recorded as a failure; re-run with `translate` after quota resets |
| Want to re-translate only             | Use the `translate` subcommand with the original `.md` file                    |
| Re-running the same URL does nothing  | Files are skipped by default; use `--force` to overwrite                       |
| `DEEPL_API_KEY` not set               | Translation is silently skipped; only the original Markdown is generated       |

## License

MIT License
