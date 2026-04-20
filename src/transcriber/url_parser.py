"""YouTube / X(Twitter) URL の種別判定と ID 抽出を行う純粋関数群.

このモジュールは ``urllib.parse`` のみを用いた純粋関数のみで構成され、
ネットワーク通信や外部プロセス呼び出しは一切行わない. そのため
ユニットテストでの検証が容易で、下流モジュール (``youtube_client``
など) から安心して利用できる.

主な関数:

- ``classify(url)`` — 動画 URL / プレイリスト URL の判定 (X は常に ``video``).
- ``classify_source(url)`` — URL のソース種別 (``youtube`` / ``x``) を返す.
- ``extract_video_id(url)`` — YouTube 動画 ID の抽出.
- ``extract_playlist_id(url)`` — YouTube プレイリスト ID の抽出.

判定ポリシー:

- YouTube: ``watch?v=...`` / ``youtu.be/...`` は動画、``playlist?list=...``
  はプレイリスト. ``watch?v=...&list=...`` は動画扱い.
- X(Twitter): ``https://x.com/<user>/status/<id>`` /
  ``https://twitter.com/<user>/status/<id>`` を動画扱い.
  プレイリストの概念は無い.
"""

from typing import Literal
from urllib.parse import parse_qs, urlparse

UrlKind = Literal["video", "playlist"]
UrlSource = Literal["youtube", "x"]

_YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }
)
_SHORT_HOSTS = frozenset({"youtu.be"})
_X_HOSTS = frozenset(
    {
        "x.com",
        "www.x.com",
        "mobile.x.com",
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
        "m.twitter.com",
    }
)


def _normalized_host(url: str) -> str:
    """URL のホスト名を小文字で返す補助関数.

    Args:
        url: 解析対象 URL.

    Returns:
        小文字化されたホスト名. 解析不能な場合は空文字列.
    """
    return (urlparse(url).hostname or "").lower()


def _is_youtube_host(url: str) -> bool:
    """URL が YouTube のドメイン配下かを判定する.

    Args:
        url: 解析対象 URL.

    Returns:
        ``youtube.com`` 系または ``youtu.be`` なら ``True``.
    """
    host = _normalized_host(url)
    return host in _YOUTUBE_HOSTS or host in _SHORT_HOSTS


def _is_x_host(url: str) -> bool:
    """URL が X(Twitter) のドメイン配下かを判定する.

    Args:
        url: 解析対象 URL.

    Returns:
        ``x.com`` 系または ``twitter.com`` 系なら ``True``.
    """
    return _normalized_host(url) in _X_HOSTS


def _is_x_status_path(path: str) -> bool:
    """X(Twitter) のパスが ``/<user>/status/<id>`` 形式かを判定する.

    Args:
        path: URL のパス部分 (例: ``/elonmusk/status/123456``).

    Returns:
        ``/status/`` セグメントの直後に数字 ID が続く場合 ``True``.
    """
    parts = [p for p in (path or "").split("/") if p]
    if len(parts) < 3:
        return False
    if parts[1] != "status":
        return False
    return parts[2].isdigit()


def is_x_url(url: str) -> bool:
    """URL が X(Twitter) の投稿 URL かを判定する.

    Args:
        url: 判定対象 URL.

    Returns:
        X(Twitter) の ``/<user>/status/<id>`` 形式なら ``True``.
    """
    if not url or not _is_x_host(url):
        return False
    return _is_x_status_path(urlparse(url).path or "")


def classify_source(url: str) -> UrlSource:
    """URL のソース種別 (YouTube / X) を判定する.

    Args:
        url: 判定対象 URL.

    Returns:
        ``"youtube"`` または ``"x"``.

    Raises:
        ValueError: サポート対象外のドメインだった場合.
    """
    if not url:
        raise ValueError("URL が空です")
    if _is_youtube_host(url):
        return "youtube"
    if _is_x_host(url):
        return "x"
    raise ValueError(f"対応していない URL のドメインです: {url}")


def classify(url: str) -> UrlKind:
    """URL が動画かプレイリストかを判定する.

    Args:
        url: 判定対象の URL 文字列.

    Returns:
        ``"video"`` または ``"playlist"``. X(Twitter) URL は常に ``"video"``.

    Raises:
        ValueError: 空文字列やサポート外の URL など、動画/プレイリスト
            のいずれとしても解釈できない場合.
    """
    if not url:
        raise ValueError("URL が空です")

    if _is_x_host(url):
        parsed = urlparse(url)
        if _is_x_status_path(parsed.path or ""):
            return "video"
        raise ValueError(f"対応していない X(Twitter) URL 形式です: {url}")

    if not _is_youtube_host(url):
        raise ValueError(f"YouTube の URL ではありません: {url}")

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    query = parse_qs(parsed.query)

    if host in _SHORT_HOSTS:
        if not path.strip("/"):
            raise ValueError(f"動画 ID が含まれていません: {url}")
        return "video"

    if path == "/watch":
        if "v" in query and query["v"]:
            return "video"
        raise ValueError(f"watch URL に v パラメータがありません: {url}")

    if path == "/playlist":
        if "list" in query and query["list"]:
            return "playlist"
        raise ValueError(f"playlist URL に list パラメータがありません: {url}")

    raise ValueError(f"対応していない YouTube URL 形式です: {url}")


def extract_video_id(url: str) -> str:
    """動画 URL から YouTube 動画 ID を取り出す.

    X(Twitter) URL では使用しない (yt-dlp が URL から直接抽出するため).

    Args:
        url: ``watch?v=...`` 形式または ``youtu.be/...`` 形式の URL.

    Returns:
        動画 ID 文字列.

    Raises:
        ValueError: URL が空、YouTube 以外、あるいは動画 ID を特定できない
            フォーマットだった場合.
    """
    if not url:
        raise ValueError("URL が空です")
    if not _is_youtube_host(url):
        raise ValueError(f"YouTube の URL ではありません: {url}")

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if host in _SHORT_HOSTS:
        video_id = parsed.path.lstrip("/")
        if not video_id:
            raise ValueError(f"動画 ID を抽出できません: {url}")
        return video_id

    if parsed.path == "/watch":
        query = parse_qs(parsed.query)
        values = query.get("v")
        if values and values[0]:
            return values[0]
        raise ValueError(f"watch URL に v パラメータがありません: {url}")

    raise ValueError(f"動画 URL ではありません: {url}")


def extract_playlist_id(url: str) -> str:
    """URL からプレイリスト ID を取り出す.

    Args:
        url: ``playlist?list=...`` 形式、または ``list=`` クエリを含む
            ``watch?v=...&list=...`` 形式の URL.

    Returns:
        プレイリスト ID 文字列.

    Raises:
        ValueError: URL が空、YouTube 以外、あるいは ``list`` パラメータが
            存在しない場合.
    """
    if not url:
        raise ValueError("URL が空です")
    if not _is_youtube_host(url):
        raise ValueError(f"YouTube の URL ではありません: {url}")

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    values = query.get("list")
    if values and values[0]:
        return values[0]
    raise ValueError(f"プレイリスト ID を抽出できません: {url}")
