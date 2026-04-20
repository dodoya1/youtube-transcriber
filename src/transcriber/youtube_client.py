"""``yt-dlp`` をラップし、メタデータ取得 / プレイリスト展開 / 音声 DL を行う.

``yt_dlp.YoutubeDL`` は YouTube だけでなく X(Twitter) など多数のサイトを
サポートしているため、本モジュールは URL のドメインを気にせず yt-dlp の
info dict を ``VideoMeta`` に正規化することに集中する.

必要な処理は以下 3 点:

1. 単一動画の正規化されたメタデータ取得 (タイトル / チャンネル / 長さ etc.)
2. プレイリストから動画 URL 一覧への展開 (``extract_flat=True``、YouTube 専用)
3. ``bestaudio`` + ``FFmpegExtractAudio`` による mp3 音声ダウンロード

yt-dlp 側の ``DownloadError`` / ``ExtractorError`` は上位層で扱いやすいよう
``TranscriberError`` として再送出する. 非公開・削除済みなどのプレイリスト
エントリ (``None`` 混入) は呼び出し側に見えないよう filter で除外する.
"""

import logging
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from transcriber.types import VideoMeta
from transcriber.url_parser import classify_source

_logger = logging.getLogger(__name__)


class TranscriberError(RuntimeError):
    """yt-dlp 由来のエラーを上位で捕捉するための共通例外.

    ``youtube_client`` 以外のモジュールはこの型だけを捕捉すれば、
    yt-dlp の内部例外階層に依存せずに済む.
    """


def _format_duration(seconds: Any) -> str:
    """``yt-dlp`` が返す秒数を ``HH:MM:SS`` 形式に整形する.

    Args:
        seconds: ``duration`` フィールドの値 (int/float/None).

    Returns:
        ``HH:MM:SS`` 形式の文字列. 取得できない場合は空文字列.
    """
    if not isinstance(seconds, (int, float)):
        return ""
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_upload_date(raw: Any) -> str:
    """``yt-dlp`` が返す ``YYYYMMDD`` 文字列を ``YYYY-MM-DD`` に整形する.

    Args:
        raw: ``upload_date`` の値.

    Returns:
        ``YYYY-MM-DD`` 形式の文字列. 解釈できなければ空文字列.
    """
    if isinstance(raw, str) and len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return ""


def _resolve_source(url: str) -> str:
    """URL から ``VideoMeta.source`` 用の識別子を決定する.

    Args:
        url: 動画 URL.

    Returns:
        ``"youtube"`` / ``"x"`` / 判定不能時は ``"youtube"``.
    """
    try:
        return classify_source(url)
    except ValueError:
        return "youtube"


def _info_to_meta(info: dict[str, Any], *, source: str) -> VideoMeta:
    """``YoutubeDL.extract_info`` の戻り dict を ``VideoMeta`` に変換する.

    YouTube の info dict は ``channel`` を持つが X(Twitter) は持たず
    ``uploader`` / ``uploader_id`` のみのため、フォールバック順で埋める.

    Args:
        info: yt-dlp が返す動画情報 dict.
        source: 入力ソース種別 (``"youtube"`` / ``"x"`` 等).

    Returns:
        正規化された ``VideoMeta``.
    """
    video_id = info.get("id") or ""
    fallback_url = (
        f"https://www.youtube.com/watch?v={video_id}"
        if source == "youtube" and video_id
        else ""
    )
    url = info.get("webpage_url") or fallback_url
    channel = (
        info.get("channel")
        or info.get("uploader")
        or info.get("uploader_id")
        or ""
    )
    return VideoMeta(
        video_id=video_id,
        title=info.get("title") or "",
        url=url,
        channel=channel,
        upload_date=_format_upload_date(info.get("upload_date")),
        duration=_format_duration(info.get("duration")),
        source=source,
    )


def fetch_video_meta(url: str) -> VideoMeta:
    """単一動画 URL からメタデータを取得する (YouTube / X 共通).

    Args:
        url: 動画 URL (YouTube の ``watch?v=...`` / ``youtu.be/...`` /
            X の ``x.com/.../status/...`` / ``twitter.com/.../status/...``).

    Returns:
        正規化済みの ``VideoMeta``. ``source`` フィールドに URL から判定
        したソース種別 (``youtube`` / ``x``) が入る.

    Raises:
        TranscriberError: yt-dlp が情報取得に失敗した場合 (非公開 / 削除 /
            地理ブロック / 年齢制限 / ネットワーク障害 など).
    """
    opts: dict[str, Any] = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise TranscriberError(f"動画メタ取得に失敗: {url}: {exc}") from exc
    if not isinstance(info, dict):
        raise TranscriberError(f"動画情報が取得できませんでした: {url}")
    return _info_to_meta(info, source=_resolve_source(url))


def fetch_playlist_videos(url: str) -> list[VideoMeta]:
    """プレイリスト URL から各動画の最小メタ情報を展開する.

    ``extract_flat=True`` を使い、プレイリスト内の動画 ID / URL / タイトル
    の軽量な情報だけをまとめて取得する. 非公開 / 削除済みエントリは yt-dlp
    側で ``None`` あるいは空の dict になるため、filter で除外する.

    Args:
        url: プレイリスト URL.

    Returns:
        展開された ``VideoMeta`` のリスト. 空の場合もあり得る.

    Raises:
        TranscriberError: プレイリスト情報の取得そのものに失敗した場合.
    """
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise TranscriberError(f"プレイリスト展開に失敗: {url}: {exc}") from exc
    if not isinstance(info, dict):
        raise TranscriberError(f"プレイリスト情報が取得できませんでした: {url}")

    entries = info.get("entries") or []
    results: list[VideoMeta] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        video_id = entry.get("id")
        if not video_id:
            continue
        entry_url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
        results.append(
            VideoMeta(
                video_id=video_id,
                title=entry.get("title") or "",
                url=entry_url,
                channel=entry.get("channel") or entry.get("uploader") or "",
                upload_date=_format_upload_date(entry.get("upload_date")),
                duration=_format_duration(entry.get("duration")),
                source="youtube",
            )
        )
    return results


def download_audio(url: str, out_dir: Path) -> Path:
    """動画の音声を mp3 としてダウンロードする.

    ``bestaudio/best`` + ``FFmpegExtractAudio`` (mp3) ポストプロセッサで
    軽量な音声ファイルに変換する. ``ffmpeg`` が別途必要.

    Args:
        url: 動画 URL.
        out_dir: 出力先ディレクトリ. 存在しなければ自動作成される.

    Returns:
        生成された mp3 ファイルのパス.

    Raises:
        TranscriberError: yt-dlp または ffmpeg 側の処理に失敗した場合、
            もしくは出力ファイルを特定できなかった場合.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(out_dir / "%(id)s.%(ext)s")
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as exc:
        raise TranscriberError(f"音声ダウンロードに失敗: {url}: {exc}") from exc
    if not isinstance(info, dict):
        raise TranscriberError(f"音声情報が取得できませんでした: {url}")

    video_id = info.get("id") or ""
    candidate = out_dir / f"{video_id}.mp3"
    if candidate.exists():
        return candidate

    # 稀に拡張子がずれるケースに備え、ID 一致の音声ファイルを探す.
    for path in out_dir.glob(f"{video_id}.*"):
        if path.is_file():
            return path
    raise TranscriberError(f"ダウンロードした音声ファイルが見つかりません: {url}")
