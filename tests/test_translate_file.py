"""``transcriber.translate_file`` モジュールのユニットテスト.

DeepL API は呼ばず ``translate_to_japanese`` を ``monkeypatch`` で差し替える.
これにより翻訳パイプライン自体の副作用 (入力ファイルを書き換えない・
``-ja.md`` が正しい場所に作られる・既存ファイルスキップ) を安定に検証する.
"""

from pathlib import Path

import pytest

from transcriber import translate_file as translate_file_module
from transcriber.translate_file import (build_translated_markdown,
                                        parse_markdown, translate_file)


def _write_sample(path: Path, *, language: str = "en", body: str = "Hello world") -> None:
    """テスト用のフィクスチャファイルを書き出す補助関数."""
    content = (
        "---\n"
        'title: "Sample Video"\n'
        "url: https://www.youtube.com/watch?v=abc123def456\n"
        'channel: "Sample Channel"\n'
        "upload_date: 2025-01-15\n"
        'duration: "00:12:34"\n'
        f"language: {language}\n"
        "source: captions\n"
        "---\n"
        "\n"
        "# Sample Video\n"
        "\n"
        f"{body}\n"
    )
    path.write_text(content, encoding="utf-8")


class TestParseMarkdown:
    """``parse_markdown`` の frontmatter / 本文分離."""

    def test_parses_basic_frontmatter_and_body(self, tmp_path: Path) -> None:
        """典型的な ``build_markdown`` 出力を往復できる."""
        path = tmp_path / "sample.md"
        _write_sample(path)
        front, body = parse_markdown(path)
        assert front["title"] == "Sample Video"
        assert front["channel"] == "Sample Channel"
        assert front["duration"] == "00:12:34"
        assert front["url"] == "https://www.youtube.com/watch?v=abc123def456"
        assert front["language"] == "en"
        assert front["source"] == "captions"
        assert "# Sample Video" in body
        assert "Hello world" in body

    def test_preserves_key_order(self, tmp_path: Path) -> None:
        """dict 挿入順で frontmatter のキー順を保持する."""
        path = tmp_path / "sample.md"
        _write_sample(path)
        front, _ = parse_markdown(path)
        assert list(front.keys()) == [
            "title",
            "url",
            "channel",
            "upload_date",
            "duration",
            "language",
            "source",
        ]

    def test_unescapes_quoted_value(self, tmp_path: Path) -> None:
        """クォート内のエスケープ ``\\"`` は実際の ``"`` に戻る."""
        path = tmp_path / "sample.md"
        path.write_text(
            "---\n"
            'title: "He said \\"hi\\""\n'
            "language: en\n"
            "---\n"
            "\n"
            "# Title\n"
            "\n"
            "Body\n",
            encoding="utf-8",
        )
        front, _ = parse_markdown(path)
        assert front["title"] == 'He said "hi"'

    def test_file_without_frontmatter_returns_empty_dict(
        self, tmp_path: Path
    ) -> None:
        """frontmatter 無しファイルは空 dict と本文を返す."""
        path = tmp_path / "plain.md"
        path.write_text("# No Frontmatter\n\nJust body.\n", encoding="utf-8")
        front, body = parse_markdown(path)
        assert front == {}
        assert "No Frontmatter" in body

    def test_file_with_unclosed_frontmatter(self, tmp_path: Path) -> None:
        """閉じ ``---`` が無いファイルも壊れず空 dict を返す."""
        path = tmp_path / "broken.md"
        path.write_text("---\ntitle: x\n\nbody without closer\n", encoding="utf-8")
        front, body = parse_markdown(path)
        assert front == {}
        assert "body without closer" in body


class TestBuildTranslatedMarkdown:
    """``build_translated_markdown`` の frontmatter 再構築."""

    def test_overrides_language_and_sets_translated_from(self) -> None:
        """``language`` が ``ja`` に上書きされ ``translated_from`` が付く."""
        front = {
            "title": "Sample",
            "url": "https://example.com",
            "channel": "CH",
            "upload_date": "2025-01-15",
            "duration": "00:10:00",
            "language": "en",
            "source": "captions",
        }
        md = build_translated_markdown(front, "# Sample\n\n本文", "en")
        assert "language: ja" in md
        assert "translated_from: en" in md
        # 元 language 行は 1 箇所のみ (ja) で残らない.
        assert md.count("language: en") == 0

    def test_quotes_title_channel_duration(self) -> None:
        """quoted キー 3 種はダブルクォートで囲まれる."""
        front = {
            "title": "Title",
            "channel": "CH",
            "duration": "00:01:02",
            "language": "en",
        }
        md = build_translated_markdown(front, "body", "en")
        assert 'title: "Title"' in md
        assert 'channel: "CH"' in md
        assert 'duration: "00:01:02"' in md

    def test_escapes_special_chars_in_quoted_value(self) -> None:
        """quoted 値に ``"`` が含まれるとエスケープされる."""
        front = {"title": 'He said "hi"', "language": "en"}
        md = build_translated_markdown(front, "body", "en")
        assert 'title: "He said \\"hi\\""' in md

    def test_body_appears_after_frontmatter(self) -> None:
        """本文は ``---`` の閉じの後ろ・空行を 1 行挟んで配置される."""
        front = {"title": "T", "language": "en"}
        md = build_translated_markdown(front, "# T\n\n本文", "en")
        assert md.endswith("# T\n\n本文\n")
        assert "---\n\n# T" in md

    def test_preserves_original_key_order(self) -> None:
        """元の frontmatter のキー順が維持され、末尾に translated_from が追加される."""
        front = {
            "title": "T",
            "url": "u",
            "channel": "CH",
            "upload_date": "2025-01-15",
            "duration": "00:01:02",
            "language": "en",
            "source": "captions",
        }
        md = build_translated_markdown(front, "body", "en")
        # translated_from は追加で末尾に来る.
        idx_language = md.index("language: ja")
        idx_translated_from = md.index("translated_from: en")
        idx_source = md.index("source: captions")
        assert idx_source < idx_language < idx_translated_from


class TestTranslateFile:
    """``translate_file`` のスキップ条件と出力先を確認する."""

    def test_skips_japanese_input(self, tmp_path: Path, monkeypatch) -> None:
        """language=ja の入力は翻訳を呼ばずスキップする."""
        called = {"n": 0}

        def fake_translate(text: str, api_key: str | None = None) -> str | None:
            called["n"] += 1
            return "翻訳結果"

        monkeypatch.setattr(
            translate_file_module, "translate_to_japanese", fake_translate
        )

        path = tmp_path / "sample.md"
        _write_sample(path, language="ja")
        result = translate_file(path)
        assert result is None
        assert called["n"] == 0
        # 入力ファイルは消えておらず内容も同一.
        assert path.exists()
        # 出力ファイルは作られない.
        assert not (tmp_path / "sample-ja.md").exists()

    def test_skips_file_already_ending_with_ja(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """ファイル名が ``-ja`` で終わっている入力はスキップする."""
        called = {"n": 0}

        def fake_translate(text: str, api_key: str | None = None) -> str | None:
            called["n"] += 1
            return "翻訳結果"

        monkeypatch.setattr(
            translate_file_module, "translate_to_japanese", fake_translate
        )
        path = tmp_path / "sample-ja.md"
        _write_sample(path, language="en")
        result = translate_file(path)
        assert result is None
        assert called["n"] == 0

    def test_writes_translated_file_next_to_input(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """翻訳成功時は同じフォルダに ``-ja.md`` を書き出し、入力は触らない."""
        def fake_translate(text: str, api_key: str | None = None) -> str | None:
            return "# サンプル動画\n\nこんにちは 世界"

        monkeypatch.setattr(
            translate_file_module, "translate_to_japanese", fake_translate
        )

        path = tmp_path / "sample.md"
        _write_sample(path, language="en", body="Hello world")
        original_bytes = path.read_bytes()

        result = translate_file(path)

        assert result is not None
        assert result == tmp_path / "sample-ja.md"
        assert result.exists()
        # 入力ファイルはバイト単位で一致 (無改変).
        assert path.read_bytes() == original_bytes
        # 出力 frontmatter と本文を確認.
        out_text = result.read_text(encoding="utf-8")
        assert "language: ja" in out_text
        assert "translated_from: en" in out_text
        assert "こんにちは 世界" in out_text

    def test_skips_when_output_exists_without_force(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """出力先が既に存在し force=False なら翻訳せずスキップ."""
        called = {"n": 0}

        def fake_translate(text: str, api_key: str | None = None) -> str | None:
            called["n"] += 1
            return "翻訳結果"

        monkeypatch.setattr(
            translate_file_module, "translate_to_japanese", fake_translate
        )

        path = tmp_path / "sample.md"
        _write_sample(path, language="en")
        existing = tmp_path / "sample-ja.md"
        existing.write_text("pre-existing", encoding="utf-8")

        result = translate_file(path, force=False)
        assert result is None
        assert called["n"] == 0
        assert existing.read_text(encoding="utf-8") == "pre-existing"

    def test_force_overwrites_existing_output(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """force=True なら既存 ``-ja.md`` を上書きする."""
        def fake_translate(text: str, api_key: str | None = None) -> str | None:
            return "新しい翻訳"

        monkeypatch.setattr(
            translate_file_module, "translate_to_japanese", fake_translate
        )

        path = tmp_path / "sample.md"
        _write_sample(path, language="en")
        existing = tmp_path / "sample-ja.md"
        existing.write_text("old", encoding="utf-8")

        result = translate_file(path, force=True)
        assert result is not None
        assert "新しい翻訳" in existing.read_text(encoding="utf-8")

    def test_raises_file_not_found(self, tmp_path: Path) -> None:
        """入力ファイルが存在しない場合は FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            translate_file(tmp_path / "missing.md")

    def test_skips_when_translator_returns_none(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """翻訳器が None を返した (API キー未設定等) 場合はスキップ."""
        def fake_translate(text: str, api_key: str | None = None) -> str | None:
            return None

        monkeypatch.setattr(
            translate_file_module, "translate_to_japanese", fake_translate
        )

        path = tmp_path / "sample.md"
        _write_sample(path, language="en")
        result = translate_file(path)
        assert result is None
        assert not (tmp_path / "sample-ja.md").exists()
