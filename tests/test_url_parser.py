"""``transcriber.url_parser`` モジュールのユニットテスト.

純粋関数 (``classify`` / ``classify_source`` / ``is_x_url`` /
``extract_video_id`` / ``extract_playlist_id``) のみを対象とし、
ネットワーク通信は一切発生しない.
"""

import pytest

from transcriber.url_parser import (classify, classify_source,
                                    extract_playlist_id, extract_video_id,
                                    is_x_url)


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
            "https://x.com/elonmusk/status/1234567890",
            "https://twitter.com/elonmusk/status/1234567890",
            "https://www.x.com/someuser/status/9876543210",
            "https://mobile.twitter.com/u/status/12345",
            "https://x.com/u/status/12345?s=20",
            "https://x.com/u/status/12345/",
            "https://x.com/u/status/12345/photo/1",
        ],
    )
    def test_x_urls_are_video(self, url: str) -> None:
        """X(Twitter) の status URL は ``video`` 扱い."""
        assert classify(url) == "video"

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "not-a-url",
            "https://www.example.com/",
            "https://www.youtube.com/",
            "https://www.youtube.com/watch",  # v パラメータが無い
            "https://x.com/",
            "https://x.com/elonmusk",  # status セグメント無し
            "https://x.com/u/status/",  # ID 無し
            "https://x.com/u/status/abc",  # ID が数字でない
        ],
    )
    def test_invalid_urls_raise(self, url: str) -> None:
        """解釈できない URL は ``ValueError`` を送出する."""
        with pytest.raises(ValueError):
            classify(url)


class TestClassifySource:
    """``classify_source`` 関数の動作確認."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/playlist?list=PL1234567890",
        ],
    )
    def test_youtube(self, url: str) -> None:
        """YouTube 系ドメインは ``youtube``."""
        assert classify_source(url) == "youtube"

    @pytest.mark.parametrize(
        "url",
        [
            "https://x.com/elonmusk/status/1234567890",
            "https://twitter.com/u/status/1234",
            "https://mobile.x.com/u/status/1234",
        ],
    )
    def test_x(self, url: str) -> None:
        """X(Twitter) 系ドメインは ``x``."""
        assert classify_source(url) == "x"

    @pytest.mark.parametrize(
        "url",
        ["", "https://www.example.com/", "https://vimeo.com/12345"],
    )
    def test_invalid(self, url: str) -> None:
        """サポート外ドメインは ``ValueError``."""
        with pytest.raises(ValueError):
            classify_source(url)


class TestIsXUrl:
    """``is_x_url`` 関数の動作確認."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://x.com/u/status/1234",
            "https://twitter.com/u/status/5678",
            "https://www.x.com/u/status/9",
            "https://mobile.twitter.com/u/status/1",
        ],
    )
    def test_true(self, url: str) -> None:
        """有効な X status URL は ``True``."""
        assert is_x_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "https://x.com/u",
            "https://x.com/u/status/",
            "https://x.com/u/status/notanumber",
            "https://www.youtube.com/watch?v=abc",
            "https://example.com/u/status/1234",
        ],
    )
    def test_false(self, url: str) -> None:
        """X status URL でないものは ``False``."""
        assert is_x_url(url) is False


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
            "https://x.com/u/status/1234567890",
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
