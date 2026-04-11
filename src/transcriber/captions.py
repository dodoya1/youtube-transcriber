"""``youtube-transcript-api`` を用いた字幕取得ラッパ.

YouTube が提供している字幕 (CC) があれば、それを優先的に取得する.
言語優先順は ``ja`` → ``en`` → ``list`` で見つかった先頭順で、この順で
試して最初に成功したものを返す. 字幕が完全に存在しない動画 (字幕無効 /
字幕非公開 / 動画自体が非公開) については ``None`` を返し、呼び出し側は
Whisper フォールバックへ進む設計.

ネットワーク I/O を伴うため、このモジュール自体に対するユニットテストは
設けず、動作検証は手動 E2E で行う.
"""

import logging

from youtube_transcript_api import (FetchedTranscript, YouTubeTranscriptApi,
                                    YouTubeTranscriptApiException)

from transcriber.language import normalize_language_code
from transcriber.types import TranscriptResult

_logger = logging.getLogger(__name__)

_PREFERRED_LANGUAGES: tuple[str, ...] = ("ja", "en")


def _snippets_to_text(fetched: FetchedTranscript) -> str:
    """``FetchedTranscript`` の字幕スニペット群をプレーンテキストに結合する.

    スニペット間はスペース区切りで連結し、連続スペース・前後空白は最終的に
    正規化して 1 本の段落として扱えるようにする. タイムスタンプは付与しない.

    Args:
        fetched: ``YouTubeTranscriptApi.fetch`` の戻り値.

    Returns:
        結合済みのテキスト. 1 スニペットも無ければ空文字列.
    """
    parts = [snippet.text.strip() for snippet in fetched if snippet.text]
    joined = " ".join(p for p in parts if p)
    return " ".join(joined.split())


def _try_preferred(
    api: YouTubeTranscriptApi, video_id: str
) -> FetchedTranscript | None:
    """``ja`` → ``en`` の優先順で ``fetch`` を試みる補助関数.

    Args:
        api: ``YouTubeTranscriptApi`` のインスタンス.
        video_id: YouTube 動画 ID.

    Returns:
        取得できた場合は ``FetchedTranscript``、いずれの言語でも取得できな
        ければ ``None``.
    """
    try:
        return api.fetch(video_id, languages=_PREFERRED_LANGUAGES)
    except YouTubeTranscriptApiException as exc:
        _logger.debug("優先言語での字幕取得に失敗 (%s): %s", video_id, exc)
        return None


def _try_any_available(
    api: YouTubeTranscriptApi, video_id: str
) -> FetchedTranscript | None:
    """``list`` で列挙できた最初の字幕を取得する補助関数.

    Args:
        api: ``YouTubeTranscriptApi`` のインスタンス.
        video_id: YouTube 動画 ID.

    Returns:
        取得できた場合は ``FetchedTranscript``、1 件も列挙できなければ
        ``None``.
    """
    try:
        transcript_list = api.list(video_id)
    except YouTubeTranscriptApiException as exc:
        _logger.debug("字幕リスト列挙に失敗 (%s): %s", video_id, exc)
        return None

    for transcript in transcript_list:
        try:
            return transcript.fetch()
        except YouTubeTranscriptApiException as exc:  # noqa: PERF203
            _logger.debug(
                "列挙済み字幕の取得に失敗 (%s / %s): %s",
                video_id,
                getattr(transcript, "language_code", "?"),
                exc,
            )
            continue
    return None


def fetch_captions(video_id: str) -> TranscriptResult | None:
    """YouTube 字幕を優先順 (``ja`` → ``en`` → 列挙先頭) で取得する.

    Args:
        video_id: YouTube 動画 ID (例: ``dQw4w9WgXcQ``).

    Returns:
        取得できた場合は ``TranscriptResult`` (``source="captions"``).
        字幕が存在しない / 取得不能な場合は ``None``.
    """
    api = YouTubeTranscriptApi()
    fetched = _try_preferred(api, video_id) or _try_any_available(api, video_id)
    if fetched is None:
        return None

    text = _snippets_to_text(fetched)
    if not text:
        _logger.debug("字幕は取得できたが本文が空: %s", video_id)
        return None

    language = normalize_language_code(getattr(fetched, "language_code", "") or "")
    return TranscriptResult(text=text, language=language, source="captions")
