"""``transcriber.language`` モジュールのユニットテスト.

``is_japanese`` / ``normalize_language_code`` の純粋関数を対象にする.
外部依存はなく、ネットワーク通信も発生しない.
"""

import pytest

from transcriber.language import is_japanese, normalize_language_code


class TestIsJapanese:
    """``is_japanese`` 関数の動作確認."""

    @pytest.mark.parametrize(
        "text",
        [
            "これは日本語の文章です。",
            "カタカナとひらがなの混在テスト",
            "漢字のみ含有文章例",
            "Hello こんにちは World",  # 混在でも日本語閾値を超える
            "ゲーム",  # 短文だが 100% カナ
        ],
    )
    def test_returns_true_for_japanese(self, text: str) -> None:
        """日本語文字が閾値以上含まれていれば ``True`` を返す."""
        assert is_japanese(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "This is an English sentence.",
            "Hello world",
            "Lorem ipsum dolor sit amet consectetur",
            "1234567890",
            "!!!???...",
            "",
            "   ",
            "🚀🔥✨",  # 絵文字のみ
        ],
    )
    def test_returns_false_for_non_japanese(self, text: str) -> None:
        """日本語文字が閾値未満なら ``False`` を返す."""
        assert is_japanese(text) is False


class TestNormalizeLanguageCode:
    """``normalize_language_code`` 関数の動作確認."""

    @pytest.mark.parametrize(
        "input_code, expected",
        [
            ("ja", "ja"),
            ("ja-JP", "ja"),
            ("JA", "ja"),
            ("en", "en"),
            ("en-US", "en"),
            ("en_GB", "en"),
            ("zh-Hans", "zh"),
            ("", ""),
        ],
    )
    def test_normalize(self, input_code: str, expected: str) -> None:
        """言語コードを小文字 & 主要部分のみに正規化する."""
        assert normalize_language_code(input_code) == expected
