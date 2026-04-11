# YouTube Transcriber 実装計画

## 1. 概要

YouTube の動画 URL またはプレイリスト URL を渡すと、各動画の文字起こしを Markdown ファイルとして `outputs/` 配下に生成する Python CLI ツールを新規開発する。英語動画の場合は日本語訳も同時に出力し、情報収集や後からの検索を容易にすることを目的とする。

また、文字起こしはできたが翻訳に失敗した・あるいは後から別の既存 Markdown を翻訳したい、というユースケースにも対応するため、**既存の Markdown ファイルを指定して翻訳だけ行うサブコマンド** (`translate`) も用意する。

空のリポジトリ (`youtube-transcriber/`) に一から構築する。

### 1.1 主要な決定事項

ユーザーからの初期要求は曖昧だったため、対話を通じて以下を確定した。

| 項目              | 決定                                                                                         | 理由                            |
| ----------------- | -------------------------------------------------------------------------------------------- | ------------------------------- |
| 文字起こし戦略    | **ハイブリッド** (字幕優先→失敗時 Whisper)                                                   | コスト最小・カバレッジ最大      |
| Whisper 実装      | **faster-whisper ローカル**                                                                  | API キー不要・無料・Mac で動作  |
| Whisper モデル    | **medium** (約 1.5GB・初回自動DL)                                                            | 品質と速度のバランス            |
| Markdown 内容     | **メタデータ + プレーン本文** (タイムスタンプ無し)                                           | 読みやすさ優先                  |
| ファイル名        | **`タイトル-<videoID先頭6文字>.md`**                                                         | 読みやすく衝突回避              |
| 言語方針          | **原文ママ出力**。英語なら `-ja.md` を追加生成                                               | 原文を残しつつ日本語でも読める  |
| 翻訳エンジン      | **DeepL API Free** (500k 文字/月まで無料)                                                    | 品質高・無料枠あり              |
| 起動方法          | **サブコマンド形式**: `transcribe <url...>` と `translate <file...>` の 2 つを明示的に提供   | 用途別に UI を分ける            |
| 出力フォルダ構成  | **翻訳ありの動画は動画専用サブフォルダにまとめる**。翻訳無し (日本語動画) はフラットファイル | 原文と訳文を 1 箇所で対で扱える |
| 翻訳専用モード    | 既存 `.md` を指定して同じフォルダに `-ja.md` を出力。入力ファイルは一切移動・変更しない      | 再翻訳・後翻訳を安全に行える    |
| `outputs/` の扱い | **git 管理対象外** (`.gitkeep` のみ commit、md ファイルは ignore)                            | 生成物を履歴に混ぜない          |
| パッケージ管理    | **uv** を使用 (仮想環境・依存同期・実行まで一貫)                                             | 高速かつ lockfile 付き          |
| 失敗動画の扱い    | **処理の最後に失敗動画一覧 (タイトル + URL + 理由) を必ず出力**                              | 再実行対象の把握を容易にする    |
| ドキュメント      | **全関数に pydoc 形式 docstring**、`README.md` はディレクトリ構成と使い方を必須で記載        | 保守性と引き継ぎを容易に        |

## 2. コミット戦略

### コミット1: uv プロジェクトと基本ファイルを初期化

- コミットメッセージ: `chore: initialize uv project and base files`
- コミットの概要: uv 管理下の Python プロジェクトとして骨組みを作る。依存は宣言だけで、コードはまだ含まない。
- 変更ファイル: `pyproject.toml`, `.gitignore`, `.env.example`, `outputs/.gitkeep`

`pyproject.toml` には runtime 依存 (`youtube-transcript-api`, `yt-dlp`, `faster-whisper`, `deepl`, `python-dotenv`) と dev extras (`pytest`) を定義し、`[project.scripts]` に `youtube-transcriber = "transcriber.cli:main"` を追加する。`.gitignore` は `.env`, `outputs/*`, `__pycache__/`, `.venv/`, `uv.lock` 以外のビルド生成物をカバー。`outputs/.gitkeep` のみ commit し、生成される md は履歴に入れない。この時点で `uv venv && uv sync --extra dev` が成功することを確認する。

### コミット2: 共通 dataclass を追加

- コミットメッセージ: `feat: add shared dataclasses for video metadata and transcript`
- コミットの概要: モジュール横断で使う 3 つの frozen dataclass (`VideoMeta` / `TranscriptResult` / `FailedVideo`) を最初に確定する。
- 変更ファイル: `src/transcriber/__init__.py`, `src/transcriber/types.py`

以降のモジュールが参照する型を先に作ることで、依存関係を上流から下流に一方向に整理する。全クラスにモジュール docstring とクラス docstring を付与する (pydoc 形式、概要 1 行)。フィールドには必要に応じて型注釈コメントを付ける。

### コミット3: URL 判別パーサをテスト付きで追加

- コミットメッセージ: `feat: add youtube url parser with tests`
- コミットの概要: 動画 URL / プレイリスト URL の種別判定と ID 抽出を行う純粋関数群を追加。
- 変更ファイル: `src/transcriber/url_parser.py`, `tests/test_url_parser.py`

`classify`, `extract_video_id`, `extract_playlist_id` の 3 関数を `urllib.parse` のみで実装し、`watch?v=...` / `youtu.be/...` / `playlist?list=...` / `watch?v=...&list=...` の 4 パターンを網羅的にテストする。最初に TDD で着手するモジュールであり、以降の実装の土台となる。

### コミット4: 言語判定ユーティリティをテスト付きで追加

- コミットメッセージ: `feat: add language detection and normalization helpers`
- コミットの概要: テキストが日本語かどうかを判定する簡易ヒューリスティックと言語コード正規化を実装。
- 変更ファイル: `src/transcriber/language.py`, `tests/test_language.py`

`is_japanese(text)` はひらがな/カタカナ/CJK の文字比率 (閾値 20%) で判定する。外部ライブラリ (langdetect 等) を増やさず最小依存に保つ方針。`normalize_language_code("ja-JP") -> "ja"` のような変換も提供。境界ケース (空文字/絵文字のみ/混在) をテストする。

### コミット5: Markdown ライタ & フォルダ配置ロジックをテスト付きで追加

- コミットメッセージ: `feat: add markdown writer with folder layout resolver`
- コミットの概要: frontmatter 付き Markdown の生成・ファイル名サニタイズ・翻訳有無によるサブフォルダ切替を実装。
- 変更ファイル: `src/transcriber/markdown_writer.py`, `tests/test_markdown_writer.py`

`sanitize_filename(title, video_id)` で `<base>` 名を作り、`resolve_paths(base, out_dir, *, has_translation)` で以下に分岐させる:

- 翻訳有: `(out_dir/<base>/<base>.md, out_dir/<base>/<base>-ja.md)`
- 翻訳無: `(out_dir/<base>.md, None)`

`build_markdown(meta, result, *, translated_from=None)` で frontmatter 部分を生成し、`write_outputs(...)` が既存ファイルを既定でスキップ (`force=True` で上書き) する。出力ディレクトリ構成は設計の肝なので `resolve_paths` を特に入念にテストする。

### コミット6: 実行結果サマリ (RunReport) をテスト付きで追加

- コミットメッセージ: `feat: add run report for success/skip/failure aggregation`
- コミットの概要: 成功 / スキップ / 失敗の集計をイミュータブルに積み上げ、最終レポートを整形する。
- 変更ファイル: `src/transcriber/run_report.py`, `tests/test_run_report.py`

`RunReport` は `successes: int`, `skipped: int`, `failed: tuple[FailedVideo, ...]` を持つ frozen dataclass。`with_success()` / `with_skip()` / `with_failure(fv)` が新しい `RunReport` を返す (mutation 禁止)。`format_report(report)` が `===== Summary =====` ブロックと `===== Failed videos =====` ブロックを文字列で返す。失敗 0 件時は「すべて成功しました」を明示する。

### コミット7: 字幕取得モジュールを追加

- コミットメッセージ: `feat: add captions fetcher via youtube-transcript-api`
- コミットの概要: YouTube 字幕を優先順に取得する薄いラッパを追加。
- 変更ファイル: `src/transcriber/captions.py`

`fetch_captions(video_id) -> TranscriptResult | None` は `ja → en → list_transcripts() の先頭` の優先順で試し、`TranscriptsDisabled` / `NoTranscriptFound` 等の例外は握り潰して `None` を返す (呼び出し側が Whisper フォールバックへ進む)。ネットワーク依存のためユニットテストは関数の存在確認程度にとどめ、動作検証は手動 E2E で行う。

### コミット8: yt-dlp ラッパを追加

- コミットメッセージ: `feat: add yt-dlp wrapper for metadata and audio download`
- コミットの概要: 動画メタデータ取得・プレイリスト展開・音声ダウンロードを担う薄いラッパ。
- 変更ファイル: `src/transcriber/youtube_client.py`

`fetch_video_meta(url)` / `fetch_playlist_videos(url)` / `download_audio(url, out_dir)` の 3 関数を実装。プレイリスト展開には `extract_flat` を使い、非公開/削除済み (`None` 混入) エントリは filter で除外する。`yt_dlp.YoutubeDL` の例外は上位で扱いやすいよう `TranscriberError` (共通例外) として再送出する。音声は `bestaudio` + `FFmpegExtractAudio` で mp3 に変換する。

### コミット9: Whisper 文字起こしフォールバックを追加

- コミットメッセージ: `feat: add faster-whisper transcription fallback`
- コミットの概要: 字幕が無い動画向けに faster-whisper でローカル文字起こしする。
- 変更ファイル: `src/transcriber/whisper_transcribe.py`

`transcribe(audio_path, model_size="medium") -> TranscriptResult` を実装。`WhisperModel` はシングルトンで遅延初期化し、`device="auto"`, `compute_type="int8"` を既定とする (Apple Silicon でも安定)。初回実行時に 1.5GB 程度のモデル DL が入る旨を docstring と INFO ログで明示する。segment を結合して 1 本の text にし、`source="whisper"` で返す。

### コミット10: DeepL 翻訳モジュールを追加

- コミットメッセージ: `feat: add DeepL translator module`
- コミットの概要: 英語テキストを日本語に翻訳するユーティリティ。API キー未設定時は安全に no-op 化。
- 変更ファイル: `src/transcriber/translator.py`

`translate_to_japanese(text, api_key) -> str | None` を実装。`api_key` が空なら `None` を返し、呼び出し側は翻訳スキップ warning を出す。段落単位で分割して DeepL の `translate_text(..., target_lang="JA")` を呼ぶ。月間 500k 文字上限に到達した場合は `deepl.QuotaExceededException` を捕捉し warning に変換、`RunReport` に `FailedVideo` として追加する。API キーは `python-dotenv` 経由で `.env` から読み込む。

### コミット11: CLI transcribe サブコマンドとパイプライン

- コミットメッセージ: `feat: add transcribe subcommand pipeline`
- コミットの概要: ここまでのモジュールを統合し、URL を受け取る本体パイプラインを組み立てる。
- 変更ファイル: `src/transcriber/cli.py`, `src/transcriber/__main__.py`

`argparse` のサブパーサで `transcribe` サブコマンドを定義。`uv run python -m transcriber transcribe <url> [<url> ...]` の形で起動する。パイプラインは:

1. `ffmpeg` 存在チェック (未インストールなら親切なエラーで中断)
2. 各 URL を `url_parser.classify()` で種別判定
3. プレイリストは `youtube_client.fetch_playlist_videos()` で展開
4. 動画ごとに try/except で独立実行: 字幕 → Whisper → 言語判定 → Markdown 書き出し → 英語なら DeepL 翻訳
5. 例外は `RunReport.with_failure(FailedVideo(...))` に集約
6. 終了時に `format_report(report)` をログ出力

共通オプション: `--output-dir`, `--model`, `--force`, `--no-translate`。

### コミット12: CLI translate サブコマンド (翻訳専用モード)

- コミットメッセージ: `feat: add translate subcommand for translation-only workflow`
- コミットの概要: 既存の Markdown ファイルを指定して DeepL 翻訳だけを行う独立サブコマンド。
- 変更ファイル: `src/transcriber/cli.py`, `src/transcriber/translate_file.py`, `tests/test_translate_file.py`

`uv run python -m transcriber translate <file.md> [<file.md> ...]` の形で起動する。処理内容は:

1. 各 `.md` ファイルをパースし frontmatter + 本文を取得 (`translate_file.py::parse_markdown`)
2. frontmatter の `language` が `ja` なら warning して skip
3. 本文を `translator.translate_to_japanese()` に渡す
4. 元 frontmatter に `language: ja`, `translated_from: <元言語>` を付与した新 Markdown を生成
5. **入力ファイルと同じフォルダに `<元ファイル名>-ja.md` を出力** (入力ファイルは移動も変更もしない)
6. 既存 `-ja.md` があれば既定でスキップ、`--force` で上書き
7. 複数ファイル指定時は `RunReport` で成功/失敗を集計し、最後に失敗一覧を出力

想定ユースケース:

- transcribe 時に DeepL 上限で翻訳だけ失敗した動画を後から再翻訳する
- 過去に手動で書いた Markdown を後追いで日本語化する

`parse_markdown` (frontmatter 分離) はネットワーク非依存のためユニットテスト対象にする。

### コミット13: README を追加

- コミットメッセージ: `docs: add README with usage and directory structure`
- コミットの概要: 使い方・インストール・ディレクトリ構成を含む README を執筆する。
- 変更ファイル: `README.md`

全機能が揃ってから書くことで README と実装の乖離を防ぐ。`9. README の記載内容` アウトラインに沿って記述する。`transcribe` と `translate` の両サブコマンドの例を必ず含める。

### コミット14: uv.lock を commit

- コミットメッセージ: `chore: add uv.lock`
- コミットの概要: 依存バージョンを固定するため `uv.lock` を commit する。
- 変更ファイル: `uv.lock`

実装途中で依存を追加/更新するたびに lockfile は変わる可能性があるため、一通り実装が完了した最後のタイミングで 1 回だけ commit する。

### コミット15: 手動検証の結果を踏まえた微修正 (必要時のみ)

- コミットメッセージ: `fix: adjust edge cases found during manual verification`
- コミットの概要: 手動 E2E 検証で見つかった不具合やエッジケースを修正する。
- 変更ファイル: (検証結果次第)

ケース A–G のいずれかで期待と異なる挙動があれば、原因を特定して最小限の修正を行う。不要なら省略。

## 3. テスト項目 (ユーザー向け受け入れチェックリスト)

実装完了後、以下をユーザー自身で確認する。

- [ ] `uv venv && uv sync --extra dev` が成功する
- [ ] `uv run pytest` が全てグリーン
- [ ] 日本語字幕ありの動画で `outputs/<base>.md` が 1 件生成される (サブフォルダは作られない)
- [ ] 英語字幕ありの動画で `outputs/<base>/<base>.md` と `outputs/<base>/<base>-ja.md` の 2 件がサブフォルダ内に生成される
- [ ] 字幕無しの動画で Whisper フォールバックが動き、frontmatter が `source: whisper` になる
- [ ] プレイリスト URL で全動画が処理される
- [ ] 途中で 1 件失敗させても他動画の処理が継続する
- [ ] 処理終了時に失敗動画一覧 (タイトル + URL + 理由) がログに出力される
- [ ] 失敗 0 件時は「すべて成功しました」相当のメッセージが出る
- [ ] `.env` を空にして英語動画を実行すると翻訳がスキップされる (原文 md は生成される)
- [ ] 同じ URL を 2 回実行した 2 回目はスキップされ、`--force` で上書きされる
- [ ] **`translate` サブコマンドで既存の `.md` を指定すると同じフォルダに `-ja.md` が生成される**
- [ ] **`translate` で複数ファイルを一括指定できる**
- [ ] **`translate` の入力ファイルが日本語の場合は skip される (エラーにはならない)**
- [ ] **`translate` の入力ファイルはいかなる場合も変更・移動されない**
- [ ] `README.md` にディレクトリ構成と使い方 (transcribe / translate 両方) が記載されている
- [ ] 全関数・クラスに pydoc 形式 docstring が書かれている
- [ ] `outputs/` 配下の md ファイルが git 管理対象外である (`git status` で出ない)

## 4. ディレクトリ構成

```
youtube-transcriber/
├── src/
│   └── transcriber/
│       ├── __init__.py
│       ├── __main__.py              # `python -m transcriber` エントリ
│       ├── cli.py                   # argparse サブコマンド + オーケストレーション
│       ├── types.py                 # 全 dataclass (frozen)
│       ├── url_parser.py            # 純粋関数: URL 判別・ID 抽出
│       ├── youtube_client.py        # yt-dlp ラッパ (メタ/プレイリスト/音声DL)
│       ├── captions.py              # youtube-transcript-api 呼び出し
│       ├── whisper_transcribe.py    # faster-whisper フォールバック
│       ├── translator.py            # DeepL 翻訳コア
│       ├── translate_file.py        # translate サブコマンド実装 (frontmatter parse + 再書き出し)
│       ├── markdown_writer.py       # Markdown 生成・filename サニタイズ・フォルダ配置
│       ├── language.py              # 言語検出/正規化
│       └── run_report.py            # 成功/スキップ/失敗の集計と最終レポート
├── tests/
│   ├── test_url_parser.py
│   ├── test_markdown_writer.py
│   ├── test_language.py
│   ├── test_run_report.py
│   └── test_translate_file.py
├── outputs/                         # 生成物置き場 (git 管理対象外)
│   └── .gitkeep                     # フォルダだけ commit
├── pyproject.toml                   # uv 用依存・ビルド設定
├── uv.lock                          # uv lockfile (commit する)
├── .env.example                     # DEEPL_API_KEY=
├── .gitignore                       # .env, outputs/**, ただし outputs/.gitkeep は残す
├── README.md                        # 使い方・ディレクトリ構成
├── CLAUDE.md                        # Claude 向けプロジェクト指示
└── plan.md                          # 本ファイル
```

## 5. ハイクオリティプロンプト (実装時に参照する仕様)

> **あなたは Python CLI 開発者です。以下の仕様に完全に従って `youtube-transcriber` を実装してください。**
>
> ### 5.1 起動コマンドとサブコマンド
>
> - `uv run python -m transcriber transcribe <url> [<url> ...]` — 動画/プレイリストを文字起こし (主機能)
> - `uv run python -m transcriber translate <file.md> [<file.md> ...]` — 既存 Markdown を翻訳のみ
> - `-m` は Python の「モジュールをスクリプトとして実行」オプション。`src/transcriber/__main__.py` がエントリ。`uv run` は uv 管理の仮想環境で Python を起動するラッパ。
> - `[project.scripts]` に `youtube-transcriber` を登録するので `uv run youtube-transcriber transcribe <url>` という短縮呼び出しも可。
>
> ### 5.2 transcribe サブコマンドの仕様
>
> 1. URL は単一動画 (`watch?v=…` / `youtu.be/…`) とプレイリスト (`playlist?list=…` / `watch?v=…&list=…`) を自動判別する。
> 2. 動画ごとに以下を順に試行する (ハイブリッド戦略):
>    1. `youtube-transcript-api` で字幕取得。優先順は `ja` → `en` → 最初に利用可能な言語。
>    2. 字幕が無ければ `yt-dlp` で音声を一時ファイルにダウンロード → `faster-whisper` (既定 `medium`, `device="auto"`, `compute_type="int8"`) で文字起こし。
> 3. 出力フォルダ構成:
>    - 共通ベース名: `<サニタイズ後タイトル>-<videoID先頭6文字>` (以下 `<base>`)
>    - **翻訳あり**: `outputs/<base>/<base>.md` (原文) + `outputs/<base>/<base>-ja.md` (訳文)
>    - **翻訳なし** (本文日本語): `outputs/<base>.md`
> 4. Markdown 本体:
>
>    ```markdown
>    ---
>    title: "<動画タイトル>"
>    url: https://www.youtube.com/watch?v=<videoId>
>    channel: "<チャンネル名>"
>    upload_date: YYYY-MM-DD
>    duration: "HH:MM:SS"
>    language: <ja|en|...>
>    source: <captions|whisper>
>    ---
>
>    # <動画タイトル>
>
>    <プレーン本文。タイムスタンプは入れない>
>    ```
>
>    翻訳版は `language: ja`, `translated_from: <原文言語>` を追加。
>
> 5. 本文言語が英語の場合のみ DeepL API で `-ja.md` を追加出力。日本語ならスキップ。`--no-translate` で明示スキップ可。
> 6. 1 動画の失敗で全体を止めない。warning ログ + `RunReport` に追加。
> 7. **処理の最後に失敗動画一覧 (タイトル + URL + 理由) を必ず出力**。失敗 0 件なら「すべて成功しました」を明示。
>
>    ```
>    ===== Summary =====
>    成功: 8 / スキップ: 1 / 失敗: 2
>
>    ===== Failed videos =====
>    - Example Title A | https://www.youtube.com/watch?v=aaaaaaaaaaa
>      reason: captions disabled and audio download failed
>    - Example Title B | https://www.youtube.com/watch?v=bbbbbbbbbbb
>      reason: DeepL quota exceeded
>    ```
>
> 8. 既存ファイルは既定でスキップ、`--force` で上書き。
> 9. `DEEPL_API_KEY` は `.env` から `python-dotenv` で読む。未設定なら翻訳自動スキップ (エラーにしない)。
> 10. オプション: `--output-dir <path>`, `--model <size>`, `--force`, `--no-translate`
>
> ### 5.3 translate サブコマンドの仕様
>
> 1. 入力: 1 つ以上の既存 `.md` ファイルパス。
> 2. 各ファイルについて:
>    1. `parse_markdown(path)` で frontmatter (YAML-like) と本文を分離。
>    2. frontmatter の `language` が `ja` なら skip warning を出して次へ。
>    3. `translator.translate_to_japanese(body, api_key)` を呼ぶ。
>    4. 新 frontmatter (`language: ja`, `translated_from: <元言語>`) を作り、タイトルと本文をくっつけて新 Markdown 文字列を作成。
>    5. **出力は入力ファイルと同じフォルダ**に `<ベース名>-ja.md` として書き出す (入力ファイル自体は一切変更・移動しない)。
>    6. 既存 `-ja.md` があれば skip (既定) / `--force` で上書き。
> 3. 複数ファイルの失敗は `RunReport` で集計し、最後に失敗一覧を出力する (transcribe と同じレポート形式)。
> 4. オプション: `--force` のみ (`--output-dir` は無い。入力ファイル基準)。
> 5. ユースケース: transcribe 時に DeepL 上限で翻訳だけ失敗した動画の再翻訳 / 手書き Markdown の後追い翻訳。
>
> ### 5.4 非機能要件
>
> - Python 3.11 以上。
> - パッケージマネージャ: **uv** (`pyproject.toml` + `uv.lock`)。仮想環境は `uv venv`、依存同期は `uv sync --extra dev`、実行は `uv run ...`。
> - 依存: `youtube-transcript-api`, `yt-dlp`, `faster-whisper`, `deepl`, `python-dotenv`, (dev) `pytest`。
> - **すべての関数・メソッド・クラス・モジュール冒頭に pydoc 形式 docstring を必ず書く**。最低限 `概要 / Args / Returns / Raises` の 4 節構成 (該当なしは省略可)。
> - コーディング規約: `~/.claude/rules/coding-style.md` に従う。
>   - イミュータブル必須 (`frozen=True`)
>   - 1 ファイル 200 行以下を目安
>   - `print` ではなく `logging`
>   - 機密情報をハードコードしない
>   - 境界でバリデーション
> - 1 動画/1 ファイル単位で例外を捕捉し、具体的エラーメッセージでロギング。
> - 純粋関数中心のモジュールには `pytest` ユニットテストを付ける。
> - `ffmpeg` 未インストール時は起動時に検出して分かりやすいエラー。
> - `README.md` にはディレクトリ構成・インストール・使い方 (両サブコマンド) を必ず書く。
>
> ### 5.5 成果物
>
> - 4 章のディレクトリ構成通りのファイル一式
> - `uv run pytest` がグリーン
> - 3 章のテスト項目が全てチェックできる状態
> - `README.md` が 9 章のアウトラインに従って完成

## 6. アーキテクチャ

```
┌──────────┐
│   CLI    │  (argparse サブパーサ: transcribe / translate)
└────┬─────┘
     │
     ├─── transcribe ──────────────────────────────────────────────┐
     │                                                             │
     │  ┌────────────┐  ┌──────────────┐  ┌──────────┐            │
     │  │ url_parser │─▶│youtube_client│─▶│ captions │──text──┐   │
     │  └────────────┘  └──────┬───────┘  └──────────┘        │   │
     │                         │ VideoMeta                     │   │
     │                         ▼                               ▼   │
     │                   ┌───────────────────┐      ┌──────────────┐
     │                   │ whisper_transcribe│      │   language   │
     │                   └───────┬───────────┘      └──────┬───────┘
     │                           │                         │
     │                           └──────── result ─────────┤
     │                                                     ▼
     │                                             ┌───────────────┐
     │                                             │  translator   │ (英語時のみ)
     │                                             └──────┬────────┘
     │                                                    ▼
     │                                            ┌────────────────┐
     │                                            │ markdown_writer│
     │                                            └───────┬────────┘
     │                                                    │
     ├─── translate ────────────┐                         │
     │                          ▼                         │
     │               ┌───────────────────┐                │
     │               │  translate_file   │───▶translator──┤
     │               │(parse + write)    │                │
     │               └───────────────────┘                │
     │                                                    ▼
     └────────────────────────────────────▶ ┌──────────────────────┐
                                            │  run_report (集計)    │
                                            │  成功/スキップ/失敗     │
                                            │  最後に失敗一覧出力    │
                                            └──────────────────────┘
```

## 7. 各モジュールの責務と主要インタフェース

※ **全関数・クラス・モジュールに pydoc 形式 docstring を書く**。以下はシグネチャ例。

### `types.py`

```python
"""プロジェクト全体で共有するイミュータブル dataclass の定義."""

@dataclass(frozen=True)
class VideoMeta:
    """1 本の YouTube 動画のメタデータ."""
    video_id: str
    title: str
    url: str
    channel: str
    upload_date: str  # "YYYY-MM-DD"
    duration: str     # "HH:MM:SS"

@dataclass(frozen=True)
class TranscriptResult:
    """文字起こし結果。出典と言語も保持."""
    text: str
    language: str           # "ja" / "en" / ...
    source: str             # "captions" | "whisper"

@dataclass(frozen=True)
class FailedVideo:
    """処理に失敗した動画の記録 (最終レポート表示用)."""
    title: str
    url: str
    reason: str
```

### `url_parser.py`

- `classify(url: str) -> Literal["video", "playlist"]`
- `extract_video_id(url: str) -> str`
- `extract_playlist_id(url: str) -> str`
- 純粋関数。`urllib.parse` のみ使用。

### `youtube_client.py`

- `fetch_video_meta(url: str) -> VideoMeta`
- `fetch_playlist_videos(url: str) -> list[VideoMeta]` (`extract_flat`, None/非公開は filter)
- `download_audio(url: str, out_dir: Path) -> Path`
- 内部で `yt_dlp.YoutubeDL`。失敗は `TranscriberError` として再送出。

### `captions.py`

- `fetch_captions(video_id: str) -> TranscriptResult | None`
- 言語優先順: `ja` → `en` → `list_transcripts()` の先頭。
- 取得不能時 (`TranscriptsDisabled` 等) は `None` を返す。

### `whisper_transcribe.py`

- モジュール内で `WhisperModel` をシングルトン遅延初期化。
- `transcribe(audio_path: Path, model_size: str = "medium") -> TranscriptResult`

### `translator.py`

- `translate_to_japanese(text: str, api_key: str | None) -> str | None`
- `api_key` が空なら `None` を返し、呼び出し側でスキップ扱い。
- 段落単位で分割して DeepL `translate_text(..., target_lang="JA")`。

### `translate_file.py`

- `parse_markdown(path: Path) -> tuple[dict, str]` — frontmatter と本文を分離。
- `build_translated_markdown(front: dict, body_ja: str, source_lang: str) -> str`
- `translate_file(path: Path, api_key: str | None, *, force: bool) -> Path | None`
  - 入力と同じフォルダに `<name>-ja.md` を書き出す。入力は触らない。
  - 入力が既に日本語の場合は `None` を返す (スキップ)。

### `language.py`

- `is_japanese(text: str) -> bool` — ひらがな/カタカナ/CJK 比率 20% 以上。
- `normalize_language_code(code: str) -> str`

### `markdown_writer.py`

- `sanitize_filename(title: str, video_id: str) -> str`
- `build_markdown(meta: VideoMeta, result: TranscriptResult, *, translated_from: str | None = None) -> str`
- `resolve_paths(base: str, out_dir: Path, *, has_translation: bool) -> tuple[Path, Path | None]`
- `write_outputs(meta, result, translated_text: str | None, out_dir: Path, *, force: bool) -> list[Path]`

### `run_report.py`

- `@dataclass(frozen=True) class RunReport`: `successes: int`, `skipped: int`, `failed: tuple[FailedVideo, ...]`
- `with_success() / with_skip() / with_failure(fv) -> RunReport`
- `format_report(report: RunReport) -> str`

### `cli.py`

- `argparse.ArgumentParser` + サブパーサ (`transcribe`, `translate`)
- `main()` がエントリ。`__main__.py` から呼ぶ。
- 各サブコマンドのハンドラ (`run_transcribe(args)` / `run_translate(args)`) を分離。
- `logging.basicConfig(level=INFO, format="%(levelname)s %(message)s")`

## 8. テスト計画

重いネットワーク/モデル依存は除外し、純粋関数と整形ロジックを中心に unit test。

| ファイル                  | テスト対象                                                                                                          |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `test_url_parser.py`      | `classify`, `extract_video_id`, `extract_playlist_id` を動画/短縮/プレイリスト/混在 URL で網羅                      |
| `test_markdown_writer.py` | `sanitize_filename` (禁止文字/長すぎ/絵文字)、`build_markdown` の frontmatter、`resolve_paths` の翻訳有無による分岐 |
| `test_language.py`        | `is_japanese` (全角ひら/カナ/漢字/英文/絵文字のみ/短文)、`normalize_language_code`                                  |
| `test_run_report.py`      | イミュータブル更新、失敗 0/複数件でのフォーマット整形                                                               |
| `test_translate_file.py`  | `parse_markdown` (frontmatter 分離)、`build_translated_markdown` の frontmatter 再構築、日本語入力の skip 判定      |

`youtube_client` / `whisper_transcribe` / `translator` (実 API) / `captions` (実 API) はネットワーク・モデル依存のためユニットテスト対象外。手動検証 (10 章) で確認。

## 9. README の記載内容 (アウトライン)

`README.md` には以下を必ず含める。

1. **プロジェクト概要** — 何のツールか・何ができるか (1 段落)
2. **主な機能** — ハイブリッド文字起こし / プレイリスト対応 / 日本語翻訳 / 翻訳専用モード / 失敗レポート 等の箇条書き
3. **前提条件** — Python 3.11+, uv, ffmpeg, (任意) DeepL API Key
4. **インストール手順**
   ```bash
   git clone <repo>
   cd youtube-transcriber
   uv venv
   uv sync --extra dev
   cp .env.example .env  # DEEPL_API_KEY を記入
   ```
5. **使い方**
   - 文字起こし (単一動画): `uv run python -m transcriber transcribe <video-url>`
   - 文字起こし (プレイリスト): `uv run python -m transcriber transcribe <playlist-url>`
   - 文字起こし (複数): `uv run python -m transcriber transcribe <url1> <url2> ...`
   - **翻訳のみ**: `uv run python -m transcriber translate outputs/foo-abc123.md`
   - **翻訳のみ (複数)**: `uv run python -m transcriber translate outputs/a.md outputs/b.md`
   - オプション: `--no-translate`, `--force`, `--model <size>`, `--output-dir <path>`
6. **出力の例** — 翻訳有 (サブフォルダ) / 翻訳無 (フラット) の 2 パターンのディレクトリ例
7. **ディレクトリ構成** — 4 章のツリー図を転記
8. **仕組み (概要)** — 字幕優先 → Whisper フォールバック → 翻訳の流れを 3-4 行
9. **テスト実行** — `uv run pytest`
10. **ライセンス** — MIT (任意)
11. **トラブルシューティング** — `ffmpeg not found` / DeepL 上限 / Whisper 初回 DL 時間 / 翻訳だけ再実行する方法 等

## 10. 手動エンドツーエンド検証手順

前提: [uv](https://docs.astral.sh/uv/) がインストール済み (未なら `brew install uv` か `curl -LsSf https://astral.sh/uv/install.sh | sh`)。

1. `uv venv` で `.venv/` を作成
2. `uv sync --extra dev` で依存同期
3. `which ffmpeg` で `ffmpeg` を確認 (未なら `brew install ffmpeg`)
4. `.env.example` を `.env` にコピーし `DEEPL_API_KEY` を記入
5. **ケース A (日本語字幕あり)**: 任意の日本語動画 URL
   → `outputs/<base>.md` が 1 件。サブフォルダは作られない
6. **ケース B (英語字幕あり)**: TED 等の英語動画
   → `outputs/<base>/<base>.md` と `outputs/<base>/<base>-ja.md` (サブフォルダ内)
7. **ケース C (字幕無し)**: 字幕無効動画
   → Whisper フォールバック、frontmatter `source: whisper`
8. **ケース D (プレイリスト)**: `...playlist?list=...`
   → 全動画分生成。途中失敗は warning で継続し、**最後に失敗一覧 (タイトル+URL)**
9. **ケース E (DeepL キー未設定)**: `.env` を空にして英語動画
   → 原文 md は生成、翻訳は skip warning
10. **ケース F (既存ファイル)**: 同じ URL を 2 回実行
    → 2 回目はスキップ。`--force` で上書き
11. **ケース G (失敗レポート)**: 無効 URL を含む複数 URL を渡す
    → Failed videos 節に該当動画が列挙される
12. **ケース H (translate サブコマンド基本)**: ケース B で生成した英語 `.md` を `--no-translate` 付きで作り直し、後から `translate` で翻訳
    → 同フォルダに `-ja.md` が追加される。元 `.md` は一切変更されない
13. **ケース I (translate 複数ファイル)**: 複数の英語 `.md` を一括指定
    → 全て処理され、失敗があれば最終レポートに表示
14. **ケース J (translate 日本語入力)**: 日本語の `.md` を `translate` に渡す
    → skip warning のみ (エラーではなく)
15. `uv run pytest` がグリーン

## 11. リスクと対処

| リスク                                       | 対処                                                             |
| -------------------------------------------- | ---------------------------------------------------------------- |
| faster-whisper 初回モデル DL が 1.5GB で遅い | CLI 起動時に「初回は DL に数分かかります」と INFO ログ           |
| Apple Silicon で `float16` が使えない        | 既定 `compute_type="int8"` で回避                                |
| プレイリスト非公開動画が `None` で混入       | `extract_flat` 結果を filter してスキップ                        |
| タイトル重複                                 | `-<videoID先頭6文字>` サフィックスで衝突回避                     |
| 長時間動画で Whisper が数十分かかる          | 実行前に INFO ログで警告                                         |
| DeepL 月間 500k 文字上限                     | `Exception` 捕捉 → warning → 失敗一覧追加 → translate で再試行可 |
| YouTube 規約 / レート制限                    | `yt-dlp` の標準挙動に従う。商用利用しない前提                    |
| `ffmpeg` 未インストール                      | 起動時検出し、`brew install ffmpeg` ヒント付きで中断             |
| uv 未インストール                            | README のインストール手順で明示                                  |
| translate で入力ファイルを破壊               | 入力は読み取り専用。出力は必ず別ファイル (`-ja.md`)              |

## 12. 実装ステップ (ToDo 順)

コミット戦略 (2 章) と 1 対 1 で対応する。

- [x] 1. uv 初期化 + `pyproject.toml` / `.gitignore` / `.env.example` / `outputs/.gitkeep` 作成 → コミット1
- [x] 2. `types.py` (dataclass 群) → コミット2
- [x] 3. `url_parser.py` + テスト → コミット3
- [x] 4. `language.py` + テスト → コミット4
- [x] 5. `markdown_writer.py` + テスト → コミット5
- [x] 6. `run_report.py` + テスト → コミット6
- [x] 7. `captions.py` → コミット7
- [x] 8. `youtube_client.py` → コミット8
- [x] 9. `whisper_transcribe.py` → コミット9
- [x] 10. `translator.py` → コミット10
- [x] 11. `cli.py` + `__main__.py` (transcribe サブコマンド) → コミット11
- [ ] 12. `translate_file.py` + translate サブコマンド追加 + テスト → コミット12
- [ ] 13. `uv run pytest` グリーン化
- [ ] 14. `README.md` 執筆 → コミット13
- [ ] 15. `uv.lock` を commit → コミット14
- [ ] 16. 手動検証 (10 章) 実施 → 必要なら コミット15
