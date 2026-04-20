[English](README.en.md)

# youtube-transcriber

YouTube / X(Twitter) の動画 URL、またはローカルの動画・音声ファイルを渡すと、文字起こしを Markdown ファイルとして `outputs/` 配下に生成する Python CLI ツールです。英語音声の場合は DeepL API で日本語訳も同時に出力し、後からの検索や情報収集を容易にすることを目的としています。また、既存の Markdown を後追いで日本語化する `translate` サブコマンドも提供します。

## 主な機能

- **マルチソース対応**: YouTube の動画・プレイリスト / X(Twitter) の投稿動画 / ローカルの動画・音声ファイルをすべて同じパイプラインで処理
- **ハイブリッド文字起こし**: YouTube はまず `youtube-transcript-api` で字幕取得、無ければ `yt-dlp` で音声を取得し `faster-whisper` (ローカル実行) にフォールバック。X とローカルは常に Whisper
- **Whisper 専用モード**: `--whisper-only` で字幕取得をスキップし、常に Whisper で文字起こし (正確性重視)
- **モデル選択**: `--model` で Whisper モデルサイズを指定可能 (`tiny` / `base` / `small` / `medium` / `large-v3`)
- **プレイリスト対応**: YouTube の動画 URL とプレイリスト URL を自動判別して一括処理
- **ローカルファイル対応**: `local` サブコマンドで `inputs/` フォルダ配下の動画・音声ファイル (mp4/mov/mkv/webm/avi/mp3/wav/m4a/flac/ogg/opus/aac 等) を一括処理
- **日本語翻訳 (DeepL)**: 英語本文は `-ja.md` を追加出力。日本語本文はスキップ
- **翻訳専用モード**: `translate` サブコマンドで既存の `.md` を後から日本語化可能
- **失敗レポート**: 1 件の失敗で全体は止まらず、処理終了時に失敗一覧 (タイトル + URL + 理由) を必ず出力
- **既存ファイル保護**: 既定でスキップ、`--force` で明示的に上書き

## 前提条件

- Python 3.11 以上
- [uv](https://docs.astral.sh/uv/) (依存同期 & 実行)
- `ffmpeg` (YouTube / X 音声抽出に必須。`local` サブコマンドでは不要)
- (任意) DeepL API Key — 英語→日本語翻訳を使う場合のみ

macOS なら `brew install ffmpeg uv` で一括導入できます。

## インストール

```bash
git clone <repo-url>
cd youtube-transcriber
uv venv
uv sync --extra dev
cp .env.example .env   # DEEPL_API_KEY= を記入 (任意)
```

## 使い方

### 文字起こし (`transcribe`) — YouTube / X(Twitter)

```bash
# YouTube 単一動画
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# YouTube プレイリスト
uv run python -m transcriber transcribe "https://www.youtube.com/playlist?list=PLxxxxxxxx"

# X(Twitter) 投稿動画
uv run python -m transcriber transcribe "https://x.com/<user>/status/<tweet_id>"

# twitter.com ドメインも同じく通る
uv run python -m transcriber transcribe "https://twitter.com/<user>/status/<tweet_id>"

# YouTube と X の URL を混在させても OK
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=aaa" "https://x.com/u/status/123"

# 翻訳をスキップして原文だけ出力
uv run python -m transcriber transcribe --no-translate "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# 既存の出力を上書き
uv run python -m transcriber transcribe --force "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# 出力先とモデルサイズを指定
uv run python -m transcriber transcribe --output-dir ./my-outputs --model small "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# 字幕を使わず常に Whisper で文字起こし (YouTube で正確性重視)
uv run python -m transcriber transcribe --whisper-only "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Whisper 専用 + 大きいモデルで高精度に
uv run python -m transcriber transcribe --whisper-only --model large-v3 "https://www.youtube.com/watch?v=xxxxxxxxxxx"
```

> **NOTE:** URL にはクエリパラメータ (`&`) が含まれるため、シェルで正しく扱うには必ずダブルクォート (`"..."`) で囲んでください。
>
> **NOTE (X):** X(Twitter) には字幕が基本付かないため、X URL に対しては常に Whisper で文字起こしします (`--whisper-only` と同等挙動)。非公開ツイート・削除済みツイートは失敗一覧に記録され、他の処理は継続します。

共通オプション:

| オプション            | 説明                                                |
| --------------------- | --------------------------------------------------- |
| `--output-dir <path>` | 出力ディレクトリ (既定: `outputs`)                  |
| `--model <size>`      | Whisper モデルサイズ (既定: `medium`)               |
| `--force`             | 既存ファイルを上書きする                            |
| `--whisper-only`      | 字幕取得をスキップし、常に Whisper で文字起こしする |
| `--no-translate`      | 英語動画でも DeepL 翻訳をスキップする               |

### ローカルファイル (`local`) — 動画・音声ファイル

プロジェクト直下の `inputs/` フォルダに動画・音声ファイルを置いて `local` サブコマンドを実行すると、すべてのファイルを Whisper で文字起こしします。`--inputs-dir` で別のフォルダを指定したり、引数にパスを列挙して個別指定することもできます。

```bash
# inputs/ フォルダを再帰的にスキャン (既定)
uv run python -m transcriber local

# 個別ファイル指定
uv run python -m transcriber local inputs/sample.mp4 /path/to/another.mp3

# スキャン対象ディレクトリを変更
uv run python -m transcriber local --inputs-dir ./my-media

# Whisper モデル・出力先を指定
uv run python -m transcriber local --model large-v3 --output-dir ./my-outputs

# 既存の出力を上書き、翻訳をスキップ
uv run python -m transcriber local --force --no-translate
```

対応拡張子:

- **動画**: `.mp4` / `.mov` / `.mkv` / `.webm` / `.avi` / `.m4v` / `.mpg` / `.mpeg` / `.ts` / `.3gp` / `.wmv`
- **音声**: `.mp3` / `.wav` / `.m4a` / `.flac` / `.ogg` / `.opus` / `.aac` / `.wma`

> **NOTE:** `local` サブコマンドは `faster-whisper` にバンドルされる PyAV が動画から音声ストリームを直接抽出してデコードするため、別途 `ffmpeg` のインストールは不要です。対応拡張子外のファイルや存在しないパスは失敗一覧に記録されます。

### 翻訳のみ (`translate`)

既に存在する `.md` ファイルを DeepL で日本語訳し、**同じフォルダ**に `<ファイル名>-ja.md` を追加出力します。入力ファイルは一切変更・移動しません。

```bash
# 単一ファイル
uv run python -m transcriber translate outputs/foo-abc123/foo-abc123.md

# 複数ファイル
uv run python -m transcriber translate outputs/a.md outputs/b.md outputs/c.md

# 既存 -ja.md を上書き
uv run python -m transcriber translate --force outputs/foo.md
```

想定ユースケース:

- `transcribe` 時に DeepL 月間上限で翻訳だけ失敗した動画を後から再翻訳する
- `--no-translate` で原文だけ残しておいた Markdown を後追いで日本語化する
- 手書きの英語 Markdown をまとめて日本語化する

frontmatter の `language` が `ja` のファイルや、ファイル名が `-ja` で終わっているファイルはスキップされます (エラーにはなりません)。

## 出力例

### 英語動画 (翻訳あり) の場合 — サブフォルダ配置

```
outputs/
└── Sample Talk-abcdef/
    ├── Sample Talk-abcdef.md      # 原文
    └── Sample Talk-abcdef-ja.md   # 日本語訳
```

### 日本語動画 (翻訳なし) の場合 — フラット配置

```
outputs/
└── サンプル動画-abcdef.md
```

Markdown 本体は YAML frontmatter + H1 見出し + プレーン本文という構成です (タイムスタンプは含まれません)。

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

`origin` キーは入力ソース種別 (`youtube` / `x` / `local`) を示します。ローカルファイルの場合は `url` / `channel` / `duration` が省略されます。翻訳版 (`-ja.md`) では `language: ja` と `translated_from: en` が追加されます。

## ディレクトリ構成

```
youtube-transcriber/
├── src/
│   └── transcriber/
│       ├── __init__.py
│       ├── __main__.py              # `python -m transcriber` エントリ
│       ├── cli.py                   # argparse サブコマンド + オーケストレーション
│       ├── types.py                 # 全 dataclass (frozen)
│       ├── url_parser.py            # URL 判別・ID 抽出 (YouTube / X 対応, 純粋関数)
│       ├── youtube_client.py        # yt-dlp ラッパ (YouTube / X 共通)
│       ├── captions.py              # youtube-transcript-api 呼び出し
│       ├── whisper_transcribe.py    # faster-whisper 文字起こし
│       ├── translator.py            # DeepL 翻訳コア
│       ├── translate_file.py        # translate サブコマンド実装
│       ├── local_source.py          # ローカル媒体ファイルのスキャン + 擬似メタ生成
│       ├── markdown_writer.py       # Markdown 生成・filename サニタイズ
│       ├── language.py              # 言語検出/正規化
│       └── run_report.py            # 成功/スキップ/失敗の集計と最終レポート
├── tests/
│   ├── test_url_parser.py
│   ├── test_markdown_writer.py
│   ├── test_language.py
│   ├── test_run_report.py
│   ├── test_translate_file.py
│   └── test_local_source.py
├── inputs/                          # ローカル入力置き場 (git 管理対象外)
│   └── .gitkeep
├── outputs/                         # 生成物置き場 (git 管理対象外)
│   └── .gitkeep
├── plan/                            # 実装計画書の置き場
├── pyproject.toml
├── uv.lock
├── .env.example                     # DEEPL_API_KEY=
├── .gitignore
├── README.md
├── README.en.md
└── CLAUDE.md
```

## 仕組み (概要)

1. 入力を種別判定: YouTube URL (動画/プレイリスト) / X(Twitter) URL / ローカルファイル
2. YouTube: 字幕 (`ja` → `en` → 利用可能な最初の言語) を取得、得られなければ `yt-dlp` で音声 DL → Whisper
3. X(Twitter): 字幕は使わず `yt-dlp` で音声 DL → Whisper
4. ローカル: `faster-whisper` が PyAV でファイルを直接デコードして文字起こし (ffmpeg 不要)
5. 本文の言語をヒューリスティック (ひらがな/カタカナ/CJK の比率) で確定
6. Markdown を出力。英語なら DeepL で日本語訳を追加出力
7. 1 件単位で例外を捕捉し、最後に成功/スキップ/失敗を `RunReport` として整形して出力

## テスト実行

```bash
uv run pytest
```

ネットワークや Whisper モデルに依存するモジュール (`youtube_client`, `whisper_transcribe`, `translator`, `captions`) はユニットテストから除外し、純粋関数と整形ロジックに絞って検証しています。

## トラブルシューティング

| 症状                                     | 対処                                                                    |
| ---------------------------------------- | ----------------------------------------------------------------------- |
| `ffmpeg が見つかりません` と出て中断する | `brew install ffmpeg` などでインストールしてください (`local` サブコマンドでは不要) |
| Whisper 初回実行が非常に遅い             | `medium` モデル (約 1.5GB) の自動ダウンロードで数分かかります           |
| 大きなローカルファイルの処理が遅い       | `--model small` / `tiny` で高速化するか、`large-v3` で高精度化などトレードオフあり |
| DeepL 月間文字数上限に達した             | その動画は翻訳失敗として記録されます。上限解消後に `translate` で再実行 |
| 翻訳だけやり直したい                     | `translate` サブコマンドに原文 `.md` を渡してください                   |
| 同じ URL / ファイルを再実行しても何も起きない | 既定でスキップされます。`--force` を付けると上書きします             |
| `DEEPL_API_KEY` 未設定                   | 翻訳が自動スキップされ、原文 Markdown のみ出力されます                  |
| X の非公開ツイートを処理したい            | 現状未対応。失敗一覧に記録されます                                       |

## ライセンス

MIT License
