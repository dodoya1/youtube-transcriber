"""ローカルの動画・音声ファイルを ``VideoMeta`` に正規化するモジュール.

``inputs/`` フォルダ配下を再帰スキャンするか、CLI から個別パスを渡して
処理する. ネットワーク通信や yt-dlp 呼び出しは一切行わず、ファイル
システムへのアクセスのみで完結するため高速かつオフラインで動作する.

``faster-whisper`` は PyAV 経由で動画・音声の主要フォーマットを直接
デコードできるため、ここで音声抽出は行わない. ファイルパスをそのまま
``whisper_transcribe.transcribe`` に渡すだけでよい.
"""

import hashlib
from datetime import datetime
from pathlib import Path

from transcriber.types import VideoMeta

_MEDIA_EXTS = frozenset(
    {
        # 動画
        ".mp4",
        ".mov",
        ".mkv",
        ".webm",
        ".avi",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".ts",
        ".3gp",
        ".wmv",
        # 音声
        ".mp3",
        ".wav",
        ".m4a",
        ".flac",
        ".ogg",
        ".opus",
        ".aac",
        ".wma",
    }
)

_VIDEO_ID_LENGTH = 12


def is_media_file(path: Path) -> bool:
    """パスが対応済み媒体ファイルの拡張子を持つかを判定する.

    Args:
        path: 判定対象のファイルパス.

    Returns:
        サポート対象の拡張子なら ``True``.
    """
    return path.suffix.lower() in _MEDIA_EXTS


def list_media_files(inputs_dir: Path) -> list[Path]:
    """``inputs_dir`` 以下を再帰スキャンし媒体ファイルのパスを返す.

    隠しファイル (``.`` で始まるファイル / フォルダ) は除外する. 返り値
    はソート済みで、複数回実行しても順序が安定する.

    Args:
        inputs_dir: 探索起点のディレクトリ.

    Returns:
        対応拡張子のファイルパス一覧 (絶対パス, ソート済み). ディレクトリ
        が存在しない場合は空リスト.
    """
    if not inputs_dir.exists() or not inputs_dir.is_dir():
        return []
    candidates: list[Path] = []
    for path in inputs_dir.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(inputs_dir).parts):
            continue
        if is_media_file(path):
            candidates.append(path.resolve())
    return sorted(candidates)


def _hash_id(path: Path) -> str:
    """絶対パスから衝突しにくい短い識別子を生成する.

    Args:
        path: 対象ファイルのパス.

    Returns:
        SHA1 の先頭 12 文字 (16 進).
    """
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()
    return digest[:_VIDEO_ID_LENGTH]


def _mtime_date(path: Path) -> str:
    """ファイルの更新日時を ``YYYY-MM-DD`` 形式で返す.

    Args:
        path: 対象ファイルのパス.

    Returns:
        ローカルタイム基準の日付文字列. 取得できなければ空文字列.
    """
    try:
        stat = path.stat()
    except OSError:
        return ""
    return datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")


def build_meta(path: Path) -> VideoMeta:
    """ローカルファイルから擬似 ``VideoMeta`` を生成する.

    - ``video_id``: 絶対パスの SHA1 先頭 12 文字 (同一パスで安定).
    - ``title``: ファイル名 (stem).
    - ``url``: 空文字列 (markdown_writer 側で省略).
    - ``channel``: 空文字列.
    - ``upload_date``: ファイルの mtime.
    - ``duration``: 空文字列 (ffprobe を呼ばない方針).
    - ``source``: ``"local"``.

    Args:
        path: 対象ファイルのパス.

    Returns:
        生成された ``VideoMeta``.
    """
    return VideoMeta(
        video_id=_hash_id(path),
        title=path.stem,
        url="",
        channel="",
        upload_date=_mtime_date(path),
        duration="",
        source="local",
    )
