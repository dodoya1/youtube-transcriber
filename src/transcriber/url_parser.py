"""YouTube URL の種別判定と ID 抽出を行う純粋関数群.

このモジュールは ``urllib.parse`` のみを用いた純粋関数のみで構成され、
ネットワーク通信や外部プロセス呼び出しは一切行わない. そのため
ユニットテストでの検証が容易で、下流モジュール (``youtube_client``
など) から安心して利用できる.

主な 3 関数:

- ``classify(url)`` — 動画 URL / プレイリスト URL の判定.
- ``extract_video_id(url)`` — 動画 ID の抽出.
- ``extract_playlist_id(url)`` — プレイリスト ID の抽出.

判定ポリシー:

- ``watch?v=...`` 形式、``youtu.be/...`` 形式は動画と見なす.
- ``playlist?list=...`` (パスが ``/playlist``) はプレイリストと見なす.
- ``watch?v=...&list=...`` のように両方の情報を含む URL は「単一動画の
  ページを開いた状態」として ``video`` 扱いにする. プレイリスト全体を
  対象にしたい場合は ``playlist`` 形式の URL を渡すこと.
"""

from typing import Literal
from urllib.parse import parse_qs, urlparse

UrlKind = Literal["video", "playlist"]

_YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }
)
_SHORT_HOSTS = frozenset({"youtu.be"})


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


def classify(url: str) -> UrlKind:
    """URL が動画かプレイリストかを判定する.

    Args:
        url: 判定対象の URL 文字列.

    Returns:
        ``"video"`` または ``"playlist"``.

    Raises:
        ValueError: 空文字列や YouTube 以外の URL など、動画/プレイリスト
            のいずれとしても解釈できない場合.
    """
    if not url:
        raise ValueError("URL が空です")
    if not _is_youtube_host(url):
        raise ValueError(f"YouTube の URL ではありません: {url}")

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    query = parse_qs(parsed.query)

    # 短縮 URL は常に動画.
    if host in _SHORT_HOSTS:
        if not path.strip("/"):
            raise ValueError(f"動画 ID が含まれていません: {url}")
        return "video"

    # ``watch?v=...`` は動画 (``list=`` が同時に含まれていても動画優先).
    if path == "/watch":
        if "v" in query and query["v"]:
            return "video"
        raise ValueError(f"watch URL に v パラメータがありません: {url}")

    # ``/playlist?list=...`` はプレイリスト.
    if path == "/playlist":
        if "list" in query and query["list"]:
            return "playlist"
        raise ValueError(f"playlist URL に list パラメータがありません: {url}")

    raise ValueError(f"対応していない YouTube URL 形式です: {url}")


def extract_video_id(url: str) -> str:
    """動画 URL から YouTube 動画 ID を取り出す.

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
