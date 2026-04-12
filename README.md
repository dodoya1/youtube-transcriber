[English](README.en.md)

# youtube-transcriber

YouTube の動画 URL またはプレイリスト URL を渡すと、各動画の文字起こしを Markdown ファイルとして `outputs/` 配下に生成する Python CLI ツールです。英語動画の場合は DeepL API で日本語訳も同時に出力し、後からの検索や情報収集を容易にすることを目的としています。また、既存の Markdown を後追いで日本語化する `translate` サブコマンドも提供します。

## 主な機能

- **ハイブリッド文字起こし**: まず `youtube-transcript-api` で字幕取得、無ければ `yt-dlp` で音声を取得し `faster-whisper` (ローカル実行) にフォールバック
- **Whisper 専用モード**: `--whisper-only` で字幕取得をスキップし、常に Whisper で文字起こし (正確性重視)
- **モデル選択**: `--model` で Whisper モデルサイズを指定可能 (`tiny` / `base` / `small` / `medium` / `large-v3`)
- **プレイリスト対応**: 動画 URL とプレイリスト URL を自動判別して一括処理
- **日本語翻訳 (DeepL)**: 英語本文は `-ja.md` を追加出力。日本語本文はスキップ
- **翻訳専用モード**: `translate` サブコマンドで既存の `.md` を後から日本語化可能
- **失敗レポート**: 1 動画の失敗で全体は止まらず、処理終了時に失敗一覧 (タイトル + URL + 理由) を必ず出力
- **既存ファイル保護**: 既定でスキップ、`--force` で明示的に上書き

## 前提条件

- Python 3.11 以上
- [uv](https://docs.astral.sh/uv/) (依存同期 & 実行)
- `ffmpeg` (音声抽出に必須)
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

### 文字起こし (`transcribe`)

```bash
# 単一動画
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# プレイリスト
uv run python -m transcriber transcribe "https://www.youtube.com/playlist?list=PLxxxxxxxx"

# 複数 URL を一括指定
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=aaa" "https://www.youtube.com/watch?v=bbb"

# 翻訳をスキップして原文だけ出力
uv run python -m transcriber transcribe --no-translate "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# 既存の出力を上書き
uv run python -m transcriber transcribe --force "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# 出力先とモデルサイズを指定
uv run python -m transcriber transcribe --output-dir ./my-outputs --model small "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# 字幕を使わず常に Whisper で文字起こし (正確性重視)
uv run python -m transcriber transcribe --whisper-only "https://www.youtube.com/watch?v=xxxxxxxxxxx"

# Whisper 専用 + 大きいモデルで高精度に
uv run python -m transcriber transcribe --whisper-only --model large-v3 "https://www.youtube.com/watch?v=xxxxxxxxxxx"
```

> **NOTE:** URL にはクエリパラメータ (`&`) が含まれるため、シェルで正しく扱うには必ずダブルクォート (`"..."`) で囲んでください。

共通オプション:

| オプション            | 説明                                                |
| --------------------- | --------------------------------------------------- |
| `--output-dir <path>` | 出力ディレクトリ (既定: `outputs`)                  |
| `--model <size>`      | Whisper モデルサイズ (既定: `medium`)               |
| `--force`             | 既存ファイルを上書きする                            |
| `--whisper-only`      | 字幕取得をスキップし、常に Whisper で文字起こしする |
| `--no-translate`      | 英語動画でも DeepL 翻訳をスキップする               |

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
---

# Sample Talk

Hello world, this is the transcript body...
```

翻訳版 (`-ja.md`) では `language: ja` と `translated_from: en` が追加されます。

## ディレクトリ構成

```
youtube-transcriber/
├── src/
│   └── transcriber/
│       ├── __init__.py
│       ├── __main__.py              # `python -m transcriber` エントリ
│       ├── cli.py                   # argparse サブコマンド + オーケストレーション
│       ├── types.py                 # 全 dataclass (frozen)
│       ├── url_parser.py            # URL 判別・ID 抽出 (純粋関数)
│       ├── youtube_client.py        # yt-dlp ラッパ (メタ/プレイリスト/音声DL)
│       ├── captions.py              # youtube-transcript-api 呼び出し
│       ├── whisper_transcribe.py    # faster-whisper フォールバック
│       ├── translator.py            # DeepL 翻訳コア
│       ├── translate_file.py        # translate サブコマンド実装
│       ├── markdown_writer.py       # Markdown 生成・filename サニタイズ
│       ├── language.py              # 言語検出/正規化
│       └── run_report.py            # 成功/スキップ/失敗の集計と最終レポート
├── tests/
│   ├── test_url_parser.py
│   ├── test_markdown_writer.py
│   ├── test_language.py
│   ├── test_run_report.py
│   └── test_translate_file.py
├── outputs/                         # 生成物置き場 (git 管理対象外)
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

## 仕組み (概要)

1. 入力 URL を動画 / プレイリストに判別し、プレイリストは全動画に展開
2. 各動画でまず `youtube-transcript-api` で字幕取得 (`ja` → `en` → 利用可能な最初の言語)
3. 字幕が得られなければ (または `--whisper-only` 時は常に) `yt-dlp` で音声を一時ファイルにダウンロードし `faster-whisper` (既定 `medium`、`--model` で変更可) で文字起こし
4. 本文の言語をヒューリスティック (ひらがな/カタカナ/CJK の比率) で確定
5. Markdown を出力。英語なら DeepL で日本語訳を追加出力
6. 1 動画単位で例外を捕捉し、最後に成功/スキップ/失敗を `RunReport` として整形して出力

## テスト実行

```bash
uv run pytest
```

ネットワークや Whisper モデルに依存するモジュール (`youtube_client`, `whisper_transcribe`, `translator`, `captions`) はユニットテストから除外し、純粋関数と整形ロジックに絞って検証しています。

## トラブルシューティング

| 症状                                     | 対処                                                                    |
| ---------------------------------------- | ----------------------------------------------------------------------- |
| `ffmpeg が見つかりません` と出て中断する | `brew install ffmpeg` などでインストールしてください                    |
| Whisper 初回実行が非常に遅い             | `medium` モデル (約 1.5GB) の自動ダウンロードで数分かかります           |
| DeepL 月間文字数上限に達した             | その動画は翻訳失敗として記録されます。上限解消後に `translate` で再実行 |
| 翻訳だけやり直したい                     | `translate` サブコマンドに原文 `.md` を渡してください                   |
| 同じ URL を再実行しても何も起きない      | 既定でスキップされます。`--force` を付けると上書きします                |
| `DEEPL_API_KEY` 未設定                   | 翻訳が自動スキップされ、原文 Markdown のみ出力されます                  |

## ライセンス

MIT License
