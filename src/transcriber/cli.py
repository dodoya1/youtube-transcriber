"""CLI エントリポイントと ``transcribe`` / ``translate`` サブコマンド.

``transcribe`` サブコマンドは各モジュールを統合し、1 つ以上の YouTube URL を
受け取って以下のパイプラインを実行する:

1. ``ffmpeg`` の存在確認 (無ければ親切なエラーで即中断).
2. 各 URL を ``url_parser.classify`` で動画 / プレイリストに判別.
3. プレイリストは ``youtube_client.fetch_playlist_videos`` で展開.
4. 動画ごとに try/except で独立実行:

   - 字幕 (``captions.fetch_captions``) 取得.
   - 失敗時は音声 DL → ``whisper_transcribe.transcribe`` にフォールバック.
   - ``language.is_japanese`` で最終的な言語を確定.
   - ``markdown_writer.write_outputs`` で Markdown を書き出し.
   - 英語かつ ``--no-translate`` 未指定なら DeepL 翻訳して ``-ja.md`` を追加.

5. 1 動画の失敗は ``RunReport`` に集約し、他の動画の処理は継続.
6. 終了時に ``format_report`` を INFO ログで出力する.

``translate`` サブコマンドは既存の Markdown ファイルを複数受け取り、
``translate_file.translate_file`` を 1 件ずつ呼び出して同じフォルダに
``-ja.md`` を書き出す. transcribe 時に翻訳だけ失敗した動画の再翻訳や
後追いで日本語化したい手書き Markdown への対応を想定する.
"""

import argparse
import logging
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from transcriber import (captions, url_parser, whisper_transcribe,
                         youtube_client)
from transcriber.language import is_japanese, normalize_language_code
from transcriber.markdown_writer import write_outputs
from transcriber.run_report import RunReport, format_report
from transcriber.translate_file import translate_file
from transcriber.translator import TranslationError, translate_to_japanese
from transcriber.types import FailedVideo, TranscriptResult, VideoMeta

_logger = logging.getLogger("transcriber")

_DEFAULT_OUTPUT_DIR = Path("outputs")
_DEFAULT_MODEL_SIZE = "medium"


def _configure_logging() -> None:
    """INFO レベルの標準ロギングを設定する.

    ``print`` を使わず常に ``logging`` 経由で出力するポリシーに合わせ、
    CLI 起動時に 1 度だけ呼び出す.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _ensure_ffmpeg() -> None:
    """``ffmpeg`` バイナリの存在を確認する.

    Raises:
        SystemExit: ``ffmpeg`` が PATH に無い場合は終了コード 1 で中断する.
    """
    if shutil.which("ffmpeg") is None:
        _logger.error(
            "ffmpeg が見つかりません. インストールしてください (macOS: brew install ffmpeg)"
        )
        raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    """``argparse`` パーサとサブパーサを構築する.

    Returns:
        サブコマンドを登録済みの ``ArgumentParser``.
    """
    parser = argparse.ArgumentParser(
        prog="transcriber",
        description="YouTube 動画/プレイリストを文字起こしし、必要に応じて日本語訳を出力する CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    transcribe = subparsers.add_parser(
        "transcribe",
        help="YouTube URL から文字起こしを行い Markdown を出力する",
    )
    transcribe.add_argument("urls", nargs="+", help="動画またはプレイリストの URL")
    transcribe.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help="出力ディレクトリ (既定: outputs)",
    )
    transcribe.add_argument(
        "--model",
        default=_DEFAULT_MODEL_SIZE,
        help="Whisper モデルサイズ (既定: medium)",
    )
    transcribe.add_argument(
        "--force",
        action="store_true",
        help="既存ファイルを上書きする",
    )
    transcribe.add_argument(
        "--no-translate",
        action="store_true",
        help="英語動画でも DeepL 翻訳をスキップする",
    )

    translate = subparsers.add_parser(
        "translate",
        help="既存の Markdown ファイルを DeepL で翻訳し -ja.md を追加出力する",
    )
    translate.add_argument(
        "files", nargs="+", help="翻訳対象の .md ファイルパス (複数可)"
    )
    translate.add_argument(
        "--force",
        action="store_true",
        help="既存の -ja.md を上書きする",
    )
    return parser


def _collect_videos(urls: Sequence[str], report: RunReport) -> tuple[list[VideoMeta], RunReport]:
    """入力 URL 群から処理対象の ``VideoMeta`` リストを構築する.

    動画 URL はそのままメタ取得、プレイリスト URL は ``fetch_playlist_videos``
    で展開する. いずれかの URL 解釈・取得で失敗したものは ``FailedVideo`` として
    レポートに積み上げ、残りの動画のみを返す.

    Args:
        urls: CLI から渡された URL リスト.
        report: 更新前の ``RunReport``.

    Returns:
        ``(videos, updated_report)`` のタプル.
    """
    videos: list[VideoMeta] = []
    for url in urls:
        try:
            kind = url_parser.classify(url)
        except ValueError as exc:
            report = report.with_failure(FailedVideo(
                title=url, url=url, reason=str(exc)))
            continue

        try:
            if kind == "playlist":
                expanded = youtube_client.fetch_playlist_videos(url)
                if not expanded:
                    report = report.with_failure(
                        FailedVideo(title=url, url=url, reason="プレイリストが空です")
                    )
                videos.extend(expanded)
            else:
                videos.append(youtube_client.fetch_video_meta(url))
        except youtube_client.TranscriberError as exc:
            report = report.with_failure(FailedVideo(
                title=url, url=url, reason=str(exc)))
    return videos, report


def _ensure_full_meta(meta: VideoMeta) -> VideoMeta:
    """プレイリスト展開で得た軽量メタを必要に応じて詳細取得で補完する.

    ``extract_flat`` はチャンネル名や投稿日が欠けることがあるため、
    ``upload_date`` または ``channel`` が空の場合のみ ``fetch_video_meta``
    を呼び直して再取得する.

    Args:
        meta: プレイリストから得た ``VideoMeta``.

    Returns:
        詳細取得済みの ``VideoMeta``. 既に充足していれば元オブジェクトを返す.
    """
    if meta.channel and meta.upload_date and meta.duration:
        return meta
    try:
        return youtube_client.fetch_video_meta(meta.url)
    except youtube_client.TranscriberError as exc:
        _logger.warning("詳細メタ取得に失敗 (軽量メタで続行): %s: %s", meta.url, exc)
        return meta


def _obtain_transcript(meta: VideoMeta) -> TranscriptResult:
    """字幕 → Whisper の順に文字起こしを試みる.

    Args:
        meta: 対象動画のメタデータ.

    Returns:
        取得できた ``TranscriptResult``.

    Raises:
        youtube_client.TranscriberError: 音声ダウンロードに失敗した場合.
        FileNotFoundError: ダウンロードした音声ファイルが消失した場合.
    """
    captioned = captions.fetch_captions(meta.video_id)
    if captioned is not None:
        _logger.info("字幕取得成功: %s (%s)", meta.video_id, captioned.language)
        return captioned

    _logger.info("字幕が見つからないため Whisper にフォールバックします: %s", meta.video_id)
    with tempfile.TemporaryDirectory(prefix="yt-audio-") as tmp_str:
        tmp_dir = Path(tmp_str)
        audio_path = youtube_client.download_audio(meta.url, tmp_dir)
        return whisper_transcribe.transcribe(audio_path)


def _finalize_language(result: TranscriptResult) -> TranscriptResult:
    """ヒューリスティック判定で最終的な言語コードを確定する.

    Args:
        result: 字幕または Whisper から返った ``TranscriptResult``.

    Returns:
        ``language`` フィールドを ``ja`` / 正規化済み元言語に固定した新インスタンス.
    """
    normalized = normalize_language_code(result.language) or ""
    if is_japanese(result.text):
        final = "ja"
    else:
        final = normalized or "en"
    if final == result.language:
        return result
    return replace(result, language=final)


def _maybe_translate(result: TranscriptResult, *, no_translate: bool) -> str | None:
    """必要なら DeepL 翻訳を実行し、結果の日本語文字列を返す.

    Args:
        result: 言語確定済みの ``TranscriptResult``.
        no_translate: ``True`` のとき翻訳を行わない.

    Returns:
        翻訳された日本語テキスト. 翻訳不要 / スキップ / 失敗時は ``None``.
    """
    if no_translate or result.language == "ja":
        return None
    try:
        return translate_to_japanese(result.text)
    except TranslationError as exc:
        _logger.warning("DeepL 翻訳に失敗: %s", exc)
        return None


def _process_video(
    meta: VideoMeta,
    *,
    out_dir: Path,
    force: bool,
    no_translate: bool,
) -> tuple[bool, bool, str | None]:
    """1 動画分のパイプラインを実行する.

    Args:
        meta: プレイリスト展開 or 単品取得で得た ``VideoMeta``.
        out_dir: 出力ディレクトリ.
        force: 既存ファイルを上書きするかどうか.
        no_translate: 翻訳を完全にスキップするかどうか.

    Returns:
        ``(written_any, skipped, error_reason_or_None)`` のタプル.
        例外が投げられた場合は呼び出し側で捕捉する.
    """
    full_meta = _ensure_full_meta(meta)
    result = _finalize_language(_obtain_transcript(full_meta))
    translated = _maybe_translate(result, no_translate=no_translate)

    written = write_outputs(
        full_meta,
        result,
        translated_text=translated,
        out_dir=out_dir,
        force=force,
    )
    if written:
        return True, False, None
    return False, True, None


def run_transcribe(args: argparse.Namespace) -> int:
    """``transcribe`` サブコマンドの本体ハンドラ.

    Args:
        args: ``argparse`` がパースした引数.

    Returns:
        プロセス終了コード. 失敗動画があっても全体は 0 を返し、致命的な
        起動エラー (ffmpeg 欠如等) のみ非ゼロを返す.
    """
    load_dotenv()
    _ensure_ffmpeg()

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    report = RunReport()
    videos, report = _collect_videos(args.urls, report)

    for meta in videos:
        try:
            written, skipped, _ = _process_video(
                meta,
                out_dir=out_dir,
                force=args.force,
                no_translate=args.no_translate,
            )
        except Exception as exc:  # noqa: BLE001  (1 動画単位の広域捕捉)
            _logger.exception("動画処理で予期せぬエラー: %s", meta.url)
            report = report.with_failure(
                FailedVideo(title=meta.title or meta.url,
                            url=meta.url, reason=str(exc))
            )
            continue

        if written:
            report = report.with_success()
        elif skipped:
            report = report.with_skip()

    _logger.info("\n%s", format_report(report))
    return 0


def run_translate(args: argparse.Namespace) -> int:
    """``translate`` サブコマンドの本体ハンドラ.

    各入力ファイルを ``translate_file`` に渡し、成功 / スキップ / 失敗を
    ``RunReport`` に積み上げる. 1 ファイル単位で例外を捕捉し、他のファイル
    の処理を継続する. 最後に ``format_report`` をログ出力する.

    Args:
        args: ``argparse`` がパースした引数. ``files`` と ``force`` を持つ.

    Returns:
        プロセス終了コード. 失敗があっても全体は 0 を返す.
    """
    load_dotenv()

    report = RunReport()
    for file_str in args.files:
        path = Path(file_str)
        try:
            result = translate_file(path, force=args.force)
        except FileNotFoundError as exc:
            _logger.warning("入力ファイルが見つかりません: %s", path)
            report = report.with_failure(
                FailedVideo(title=path.name, url=str(path), reason=str(exc))
            )
            continue
        except TranslationError as exc:
            _logger.warning("翻訳に失敗: %s: %s", path, exc)
            report = report.with_failure(
                FailedVideo(title=path.name, url=str(path), reason=str(exc))
            )
            continue
        except Exception as exc:  # noqa: BLE001  (1 ファイル単位の広域捕捉)
            _logger.exception("翻訳で予期せぬエラー: %s", path)
            report = report.with_failure(
                FailedVideo(title=path.name, url=str(path), reason=str(exc))
            )
            continue

        if result is None:
            report = report.with_skip()
        else:
            report = report.with_success()

    _logger.info("\n%s", format_report(report))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI のエントリ関数.

    Args:
        argv: 引数リスト (テスト用). ``None`` なら ``sys.argv[1:]`` を使う.

    Returns:
        プロセス終了コード.
    """
    _configure_logging()
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "transcribe":
        return run_transcribe(args)
    if args.command == "translate":
        return run_translate(args)

    parser.error(f"未知のサブコマンド: {args.command}")
    return 2
