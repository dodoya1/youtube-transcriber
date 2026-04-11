"""``transcriber.url_parser`` モジュールのユニットテスト.

純粋関数 (``classify`` / ``extract_video_id`` / ``extract_playlist_id``)
のみを対象とし、ネットワーク通信は一切発生しない.
"""

import pytest

from transcriber.url_parser import (classify, extract_playlist_id,
                                    extract_video_id)


class TestClassify:
    """``classify`` 関数の動作確認."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ?t=10",
            # 動画 ID と list= が共存する場合は「動画」として扱う.
            # 単一動画の URL を開いている状況を優先する方が安全.
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890",
        ],
    )
    def test_video_urls(self, url: str) -> None:
        """動画 URL は ``video`` と判定される."""
        assert classify(url) == "video"

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/playlist?list=PL1234567890",
            "http://youtube.com/playlist?list=PLabcdef",
            "https://m.youtube.com/playlist?list=PLxyz",
        ],
    )
    def test_playlist_urls(self, url: str) -> None:
        """プレイリスト URL は ``playlist`` と判定される."""
        assert classify(url) == "playlist"

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "not-a-url",
            "https://www.example.com/",
            "https://www.youtube.com/",
            "https://www.youtube.com/watch",  # v パラメータが無い
        ],
    )
    def test_invalid_urls_raise(self, url: str) -> None:
        """YouTube として解釈できない URL は ``ValueError`` を送出する."""
        with pytest.raises(ValueError):
            classify(url)


class TestExtractVideoId:
    """``extract_video_id`` 関数の動作確認."""

    def test_watch_url(self) -> None:
        """``watch?v=`` 形式から動画 ID を抽出する."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url(self) -> None:
        """``youtu.be/ID`` 形式から動画 ID を抽出する."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url_with_query(self) -> None:
        """``youtu.be/ID?t=10`` のようにクエリが付いていても抽出できる."""
        url = "https://youtu.be/dQw4w9WgXcQ?t=10"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_watch_with_playlist(self) -> None:
        """``watch?v=...&list=...`` でも動画 ID 側を正しく抽出する."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_mobile_domain(self) -> None:
        """``m.youtube.com`` でも動画 ID を抽出できる."""
        url = "https://m.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "https://www.youtube.com/playlist?list=PL1234567890",
            "https://www.example.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch",
            "https://youtu.be/",
        ],
    )
    def test_invalid_raises(self, url: str) -> None:
        """動画 ID を特定できない URL は ``ValueError`` を送出する."""
        with pytest.raises(ValueError):
            extract_video_id(url)


class TestExtractPlaylistId:
    """``extract_playlist_id`` 関数の動作確認."""

    def test_playlist_url(self) -> None:
        """``playlist?list=`` 形式からプレイリスト ID を抽出する."""
        url = "https://www.youtube.com/playlist?list=PL1234567890"
        assert extract_playlist_id(url) == "PL1234567890"

    def test_watch_with_list(self) -> None:
        """``watch?v=...&list=...`` でもプレイリスト ID は取れる."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabc"
        assert extract_playlist_id(url) == "PLabc"

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.example.com/playlist?list=PL1234",
        ],
    )
    def test_invalid_raises(self, url: str) -> None:
        """プレイリスト ID を特定できない URL は ``ValueError`` を送出する."""
        with pytest.raises(ValueError):
            extract_playlist_id(url)
