# youtube-transcriber に X(Twitter) URL とローカルファイル対応を追加する計画

## 概要

### なぜこの変更が必要か

現在の youtube-transcriber は YouTube の URL しか受け付けない。ユーザーから以下 2 点の拡張要望があった:

1. **X(Twitter) URL 対応**: `https://x.com/.../status/...` のツイート内動画を文字起こししたい
2. **ローカルファイル対応**: プロジェクト直下に `inputs/` フォルダを設け、そこに置いた動画・音声ファイルを一括で文字起こし・翻訳したい

### 実現方針 (調査結果を反映)

- **X 対応は軽量で済む**: `yt-dlp` は 2024 年以降 `x.com` / `twitter.com` のエクストラクタを標準搭載しており、`fetch_video_meta` / `download_audio` の yt-dlp ラッパはほぼそのまま流用できる。律速になっているのは `url_parser.classify()` が YouTube ホストを enum でホワイトリスト化している点のみ。ここを拡張すれば既存パイプラインに X をそのまま通せる。
- **X は常に Whisper**: 調査の結果 X の投稿動画に字幕 (captions) が付くケースは稀で、`youtube-transcript-api` は YouTube 専用 API のため X には使えない。よって X URL は字幕取得をスキップし、直接 Whisper で文字起こしする (ユーザー同意済み)。
- **ローカルファイルは Whisper に直渡し**: `faster-whisper` は PyAV 経由で mp4/mov/mkv/webm/mp3/wav/m4a/flac/ogg/opus/aac をすべて直接デコードできる (README 明記)。したがってローカルファイルは音声抽出も yt-dlp も介さず、ファイルパスを `whisper_transcribe.transcribe()` に直接渡すだけで済む。
- **CLI 設計はユーザー確認済み**: X URL は既存の `transcribe` に自動判定で統合、ローカルファイルは新規 `local` サブコマンド (引数省略時は `inputs/` を再帰スキャン)。

### 達成したい最終像

```bash
# YouTube (従来通り)
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=..."

# X(Twitter) も同じ transcribe で通る
uv run python -m transcriber transcribe "https://x.com/elonmusk/status/1234567890"

# 混在も可
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=..." "https://x.com/.../status/..."

# ローカルファイル: inputs/ フォルダを一括処理
uv run python -m transcriber local

# ローカルファイル: 個別パス指定
uv run python -m transcriber local /path/to/video.mp4 /path/to/audio.mp3

# オプションは共通 (--model, --force, --no-translate, --output-dir)
uv run python -m transcriber local --model large-v3 --no-translate
```

---

## コミット戦略

### コミット1: url_parser を X(Twitter) に拡張

- コミットメッセージ: `feat: url_parser を拡張して x.com/twitter.com URL を受け付ける`
- コミットの概要: `classify` と補助関数を YouTube / X の両ソースに対応させ、URL ソース判定 (`classify_source`) を追加する純粋関数レイヤの変更
- 変更ファイル:
  - `src/transcriber/url_parser.py`
  - `tests/test_url_parser.py`

純粋関数 + ユニットテストのみで構成されるため最初に切り出し、後続コミットから安心して使える土台を作る。`classify_source(url) -> "youtube" | "x"` を新規追加する二段構えにして、既存テスト互換性を維持。テストは既存の `test_url_parser.py` に X URL パターン (`x.com/u/status/123`, `twitter.com/u/status/123`, クエリ付き, トレイリングスラッシュ等) を追加。

### コミット2: youtube_client のメタ取得を URL ソース非依存に補強

- コミットメッセージ: `refactor: youtube_client のメタ取得を URL 非依存にし X にも流用できるようにする`
- コミットの概要: `fetch_video_meta` が yt-dlp の info dict を VideoMeta へ正規化する際、YouTube 固有フィールド (`channel`) に依存しないフォールバックを追加。`VideoMeta.source` フィールドをここで追加する
- 変更ファイル:
  - `src/transcriber/youtube_client.py`
  - `src/transcriber/types.py`

X の info dict には `channel` が無く `uploader` / `uploader_id` のみ、`title` も自動合成される。`channel` が無ければ `uploader` → `uploader_id` → 空文字、`upload_date` は YYYYMMDD → YYYY-MM-DD 正規化済みヘルパを流用。`VideoMeta.source: str = "youtube"` をデフォルト付きで追加し既存テストを壊さない。

### コミット3: transcribe パイプラインで X URL の字幕取得をスキップ

- コミットメッセージ: `feat: X(Twitter) URL は字幕取得をスキップして直接 Whisper で文字起こし`
- コミットの概要: `cli._obtain_transcript` が X ソースの VideoMeta を見たら captions 段をバイパスするよう分岐、`_collect_videos` が X URL も通るよう整備
- 変更ファイル:
  - `src/transcriber/cli.py`

`VideoMeta.source == "x"` の場合は `whisper_only=True` と同じ挙動にする。`_obtain_transcript` 内で `meta.source == "x" or whisper_only` の OR 条件に変更するだけで実現。

### コミット4: local サブコマンドの新規追加 (inputs/ スキャン + 個別パス)

- コミットメッセージ: `feat: ローカル動画/音声ファイルを文字起こしする local サブコマンドを追加`
- コミットの概要: 新規モジュール `local_source.py` で入力ファイル列挙 + 擬似 VideoMeta 生成を行い、cli に `local` サブパーサを追加
- 変更ファイル:
  - `src/transcriber/local_source.py` (新規)
  - `src/transcriber/cli.py`
  - `src/transcriber/whisper_transcribe.py` (任意パス OK を docstring で明示)
  - `inputs/.gitkeep` (新規)
  - `.gitignore` (inputs/ 内の媒体ファイルを除外)
  - `tests/test_local_source.py` (新規)

`local_source.list_media_files(inputs_dir)` が対応拡張子 (`.mp4 .mov .mkv .webm .avi .mp3 .wav .m4a .flac .ogg .opus .aac`) を再帰的に列挙。`local_source.build_meta(path)` がファイル mtime → upload_date、stem → title、path hash → video_id 代替、`url` / `channel` は空文字、`source="local"` で VideoMeta を構成。CLI 側は `_obtain_transcript` の代わりに `whisper_transcribe.transcribe(path)` を直接呼ぶローカル専用 `_process_local_file` を用意。

### コミット5: markdown_writer を source 対応に更新

- コミットメッセージ: `feat: frontmatter に origin=x/local を出力し不要フィールドを省略`
- コミットの概要: `source=local` の場合に `channel` / `url` を省略、`source=x` の場合は `channel` を省略、YouTube は従来通り
- 変更ファイル:
  - `src/transcriber/markdown_writer.py`
  - `tests/test_markdown_writer.py`

YAML frontmatter の各キーを条件付き出力に変更 (空文字は出さない)。入力ソースを別キー `origin: youtube | x | local` として分離 (従来の `source: captions | whisper` はそのまま維持)。テストは YouTube / X / local 各ケースで frontmatter 出力を検証。

### コミット6: README / README.en の更新

- コミットメッセージ: `docs: X URL とローカルファイル対応を README に追記`
- コミットの概要: 主な機能・使い方・ディレクトリ構成節に新機能を追加
- 変更ファイル:
  - `README.md`
  - `README.en.md`

---

## テスト項目 (ユーザー向け受け入れチェックリスト)

- [ ] YouTube 単一動画の transcribe が従来通り動く (回帰無し)
- [ ] YouTube プレイリスト transcribe が従来通り動く
- [ ] `transcribe "https://x.com/<user>/status/<id>"` で X の動画が文字起こしされる
- [ ] `transcribe "https://twitter.com/<user>/status/<id>"` (twitter.com ドメイン) でも動く
- [ ] YouTube と X の URL を混在させても両方処理される
- [ ] X 動画の出力 Markdown の frontmatter に `origin: x` が記録される
- [ ] X 動画の本文が英語なら `-ja.md` が DeepL で出力される
- [ ] `uv run python -m transcriber local` で `inputs/` 配下の動画・音声がすべて処理される
- [ ] `local inputs/sample.mp4` のように個別パス指定でも処理される
- [ ] `inputs/` に .mp4 .mov .mp3 .wav .m4a を置いてすべて処理されることを確認
- [ ] ローカルファイルの Markdown の frontmatter に `origin: local`、`channel` / `url` が出ないことを確認
- [ ] ローカルファイルの出力ファイル名がファイル名 stem ベースで生成される
- [ ] `--force` 無しで再実行するとスキップされ、`--force` で上書きされる (ローカル/X/YouTube すべて)
- [ ] `--no-translate` でローカル/X の翻訳もスキップされる
- [ ] `--model large-v3` が local / X / YouTube すべてで反映される
- [ ] 存在しないパスを `local` に渡した場合 RunReport の失敗一覧に記録される
- [ ] X のプライベート/削除済みツイート URL は失敗一覧に入るが他の動画の処理は継続する
- [ ] `uv run pytest` がすべて通る (既存テスト + 新規 url_parser/markdown_writer/local_source)

---

## ディレクトリ構成

```
youtube-transcriber/
├── src/
│   └── transcriber/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py                   (*) transcribe multi-source 化 + local サブコマンド追加
│       ├── types.py                 (*) VideoMeta に source フィールド追加
│       ├── url_parser.py            (*) x.com / twitter.com 対応, classify_source 追加
│       ├── youtube_client.py        (*) info dict → VideoMeta 正規化を非 YouTube でも動くよう補強
│       ├── captions.py
│       ├── whisper_transcribe.py    (*) docstring 整備 (任意パス OK を明記)
│       ├── translator.py
│       ├── translate_file.py
│       ├── markdown_writer.py       (*) origin=x/local に応じた frontmatter 条件出力
│       ├── language.py
│       ├── local_source.py          (+) inputs/ スキャン, 擬似 VideoMeta 生成
│       └── run_report.py
├── tests/
│   ├── test_url_parser.py           (*) X URL テスト追加
│   ├── test_markdown_writer.py      (*) x/local ケース追加
│   ├── test_language.py
│   ├── test_run_report.py
│   ├── test_translate_file.py
│   └── test_local_source.py         (+) 拡張子フィルタ・VideoMeta 生成検証
├── inputs/                          (+) ローカル入力置き場
│   └── .gitkeep                     (+)
├── outputs/
│   └── .gitkeep
├── plan/
│   └── 2026-04-20-x-twitter-and-local-files.md  (+) 本計画書
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore                       (*) inputs/*.* の媒体ファイルを除外
├── README.md                        (*) X/ローカル節を追加
├── README.en.md                     (*)
└── CLAUDE.md
```

---

## その他

### 主要モジュールの詳細設計

#### `url_parser.py` の拡張

破壊的変更を避けるため、既存の `classify(url) -> UrlKind` は YouTube 専用のまま保ち、新規関数 `classify_source(url) -> "youtube" | "x"` と `is_x_url(url) -> bool` を追加する方針。X URL は常に単一動画扱い (プレイリスト概念なし)。

#### `VideoMeta.source` フィールド

```python
@dataclass(frozen=True)
class VideoMeta:
    video_id: str
    title: str
    url: str
    channel: str
    upload_date: str
    duration: str
    source: str = "youtube"   # "youtube" | "x" | "local"
```

デフォルト値を `"youtube"` にして既存テストを壊さない。

#### `local_source.py` の骨子

```python
_MEDIA_EXTS = frozenset({
    ".mp4", ".mov", ".mkv", ".webm", ".avi",
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac",
})

def list_media_files(inputs_dir: Path) -> list[Path]: ...
def build_meta(path: Path) -> VideoMeta:
    # video_id: sha1(absolute_path)[:12]
    # title: path.stem
    # url: ""
    # channel: ""
    # upload_date: mtime → YYYY-MM-DD
    # duration: "" (ffprobe を呼ばないので省略)
    # source: "local"
```

#### `cli.py` のフロー変更

- `_collect_videos`: URL ごとに `url_parser.classify_source(url)` を呼び、youtube なら従来経路、x なら `youtube_client.fetch_video_meta(url)` (yt-dlp はそのまま通る) + `source="x"` に差し替え。
- `_obtain_transcript`: `if not whisper_only and meta.source != "x":` に変更。
- `run_local` (新規): `inputs_dir` と `files` 引数を受け、`local_source.list_media_files` + 明示パスをマージ、各パスで `build_meta` → `whisper_transcribe.transcribe` → `_finalize_language` → `_maybe_translate` → `write_outputs` の最短経路。

### 再利用する既存関数 (車輪の再発明を避ける)

- `src/transcriber/whisper_transcribe.py:transcribe(audio_path, model_size)` — ローカルファイル対応はこの関数をそのまま呼ぶだけで完了 (PyAV が動画もデコードできる)
- `src/transcriber/cli.py:_finalize_language` / `_maybe_translate` — ローカル/X でも共通で使用
- `src/transcriber/markdown_writer.py:write_outputs` / `sanitize_filename` — 出力パス決定とファイル名サニタイズを共通で使う
- `src/transcriber/run_report.py` — 成功/スキップ/失敗の集計は既存のまま
- `src/transcriber/language.py:is_japanese` / `normalize_language_code` — 言語確定は共通

### リスクと対処

- **yt-dlp の X エクストラクタは時折壊れる**: 取得失敗時は `TranscriberError` として現行の失敗一覧に載るので全体は止まらない。ユーザーは yt-dlp 最新化で対処可。
- **X のプライベート動画は認証が必要**: スコープ外とし、失敗一覧に反映のみ。クッキー対応は将来拡張。
- **ローカル大容量ファイルで Whisper が長時間かかる**: 既存制約と同じ。README トラブルシュートに一言追記。
- **`VideoMeta.source` 追加は破壊的変更になり得る**: デフォルト値 `"youtube"` で後方互換。

### 手動検証手順 (E2E)

```bash
# 1. 環境準備
uv sync --extra dev

# 2. 回帰確認 (YouTube)
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 3. X (Twitter) 新機能
uv run python -m transcriber transcribe "https://x.com/<公開動画のステータスID>"

# 4. ローカル (inputs/)
cp /path/to/test.mp4 inputs/
cp /path/to/test.mp3 inputs/
uv run python -m transcriber local

# 5. ローカル個別パス
uv run python -m transcriber local inputs/test.mp4 --force

# 6. 混在 (YouTube + X)
uv run python -m transcriber transcribe "https://www.youtube.com/watch?v=..." "https://x.com/.../status/..."

# 7. 単体テスト
uv run pytest -v
```

### 実装ステップ

コミット戦略節の順序に従って 1→2→3→4→5→6 で進める。各コミット後にチェックリストの該当項目を埋めていく。
