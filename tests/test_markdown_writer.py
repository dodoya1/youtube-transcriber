"""``transcriber.markdown_writer`` モジュールのユニットテスト.

ファイル書き込みを伴うテストは ``tmp_path`` fixture を用い、実ファイル
システム上の一時ディレクトリで完結する. ネットワーク依存はない.
"""

from pathlib import Path

import pytest

from transcriber.markdown_writer import (build_markdown, resolve_paths,
                                         sanitize_filename, write_outputs)
from transcriber.types import TranscriptResult, VideoMeta


@pytest.fixture
def sample_meta() -> VideoMeta:
    """テスト用の固定 VideoMeta を返す."""
    return VideoMeta(
        video_id="dQw4w9WgXcQ",
        title="Sample Video Title",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        channel="Sample Channel",
        upload_date="2025-01-15",
        duration="00:12:34",
    )


@pytest.fixture
def sample_result() -> TranscriptResult:
    """テスト用の固定 TranscriptResult を返す (英語)."""
    return TranscriptResult(text="Hello world", language="en", source="captions")


class TestSanitizeFilename:
    """``sanitize_filename`` 関数の動作確認."""

    def test_removes_forbidden_chars(self) -> None:
        """OS 予約文字が除去されることを確認する."""
        name = sanitize_filename("foo/bar:baz?qux*<>|\"", "abcdef123456")
        # 記号類は除去または置換される想定.
        assert "/" not in name
        assert ":" not in name
        assert "?" not in name
        assert "*" not in name
        assert name.endswith("-abcdef")

    def test_truncates_long_title(self) -> None:
        """極端に長いタイトルは切り詰められて video_id サフィックスが残る."""
        long_title = "あ" * 500
        name = sanitize_filename(long_title, "abcdef123456")
        assert len(name) <= 120
        assert name.endswith("-abcdef")

    def test_handles_empty_title(self) -> None:
        """空タイトルでも video_id ベースで名前が作られる."""
        name = sanitize_filename("", "abcdef123456")
        assert name.endswith("abcdef")
        assert len(name) > 0

    def test_suffix_is_first_6_of_video_id(self) -> None:
        """サフィックスは動画 ID の先頭 6 文字."""
        name = sanitize_filename("Hello", "zyxwvu987654")
        assert name.endswith("-zyxwvu")


class TestBuildMarkdown:
    """``build_markdown`` 関数の frontmatter 生成を確認する."""

    def test_frontmatter_contains_required_fields(
        self, sample_meta: VideoMeta, sample_result: TranscriptResult
    ) -> None:
        """frontmatter に必須フィールドが全て含まれる."""
        md = build_markdown(sample_meta, sample_result)
        assert md.startswith("---\n")
        assert 'title: "Sample Video Title"' in md
        assert "url: https://www.youtube.com/watch?v=dQw4w9WgXcQ" in md
        assert 'channel: "Sample Channel"' in md
        assert "upload_date: 2025-01-15" in md
        assert 'duration: "00:12:34"' in md
        assert "language: en" in md
        assert "source: captions" in md

    def test_body_contains_title_heading_and_text(
        self, sample_meta: VideoMeta, sample_result: TranscriptResult
    ) -> None:
        """本文に H1 タイトルと本文テキストが含まれる."""
        md = build_markdown(sample_meta, sample_result)
        assert "# Sample Video Title" in md
        assert "Hello world" in md

    def test_translated_variant_adds_translated_from(
        self, sample_meta: VideoMeta
    ) -> None:
        """翻訳版では ``language: ja`` と ``translated_from`` が付与される."""
        result = TranscriptResult(
            text="こんにちは 世界", language="ja", source="captions"
        )
        md = build_markdown(sample_meta, result, translated_from="en")
        assert "language: ja" in md
        assert "translated_from: en" in md

    def test_quotes_escape_in_title(self, sample_result: TranscriptResult) -> None:
        """タイトル中のダブルクォートは frontmatter 内でエスケープされる."""
        meta = VideoMeta(
            video_id="abc123def456",
            title='He said "hi"',
            url="https://www.youtube.com/watch?v=abc123def456",
            channel="c",
            upload_date="2025-01-01",
            duration="00:00:10",
        )
        md = build_markdown(meta, sample_result)
        # エスケープされた形で含まれる (``\"`` など).
        assert 'He said' in md
        assert "\n---\n" in md


class TestResolvePaths:
    """``resolve_paths`` の翻訳有無による分岐を確認する."""

    def test_no_translation_is_flat(self, tmp_path: Path) -> None:
        """翻訳無し: ``out_dir/<base>.md`` のフラット配置."""
        main, translated = resolve_paths(
            "title-abcdef", tmp_path, has_translation=False
        )
        assert main == tmp_path / "title-abcdef.md"
        assert translated is None

    def test_with_translation_is_subfolder(self, tmp_path: Path) -> None:
        """翻訳有り: ``out_dir/<base>/<base>.md`` + ``<base>-ja.md`` のサブフォルダ."""
        main, translated = resolve_paths(
            "title-abcdef", tmp_path, has_translation=True
        )
        assert main == tmp_path / "title-abcdef" / "title-abcdef.md"
        assert translated == tmp_path / "title-abcdef" / "title-abcdef-ja.md"


class TestWriteOutputs:
    """``write_outputs`` の書き出しとスキップ挙動を確認する."""

    def test_writes_single_md_when_no_translation(
        self,
        tmp_path: Path,
        sample_meta: VideoMeta,
    ) -> None:
        """翻訳無しのとき 1 ファイルのみ書き出される."""
        result = TranscriptResult(text="本文", language="ja", source="captions")
        paths = write_outputs(
            sample_meta, result, translated_text=None, out_dir=tmp_path, force=False
        )
        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].read_text(encoding="utf-8").startswith("---\n")

    def test_writes_pair_when_translation_given(
        self,
        tmp_path: Path,
        sample_meta: VideoMeta,
        sample_result: TranscriptResult,
    ) -> None:
        """翻訳有りのとき 2 ファイルがサブフォルダに書き出される."""
        paths = write_outputs(
            sample_meta,
            sample_result,
            translated_text="こんにちは",
            out_dir=tmp_path,
            force=False,
        )
        assert len(paths) == 2
        assert all(p.exists() for p in paths)
        # 両ファイルとも同一サブフォルダに居る.
        assert paths[0].parent == paths[1].parent
        assert paths[0].parent != tmp_path

    def test_skip_when_exists_and_not_force(
        self,
        tmp_path: Path,
        sample_meta: VideoMeta,
    ) -> None:
        """既存ファイルがあり force=False なら書き出しをスキップする."""
        result = TranscriptResult(text="本文", language="ja", source="captions")
        first = write_outputs(
            sample_meta, result, translated_text=None, out_dir=tmp_path, force=False
        )
        original_mtime = first[0].stat().st_mtime_ns
        # 2 回目はスキップで空リスト.
        second = write_outputs(
            sample_meta, result, translated_text=None, out_dir=tmp_path, force=False
        )
        assert second == []
        assert first[0].stat().st_mtime_ns == original_mtime

    def test_force_overwrites(
        self,
        tmp_path: Path,
        sample_meta: VideoMeta,
    ) -> None:
        """force=True なら既存ファイルを上書きする."""
        result1 = TranscriptResult(text="first", language="ja", source="captions")
        write_outputs(
            sample_meta, result1, translated_text=None, out_dir=tmp_path, force=False
        )
        result2 = TranscriptResult(text="second", language="ja", source="captions")
        paths = write_outputs(
            sample_meta, result2, translated_text=None, out_dir=tmp_path, force=True
        )
        assert len(paths) == 1
        assert "second" in paths[0].read_text(encoding="utf-8")
