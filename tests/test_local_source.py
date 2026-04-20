"""``transcriber.local_source`` のユニットテスト.

ファイルシステム I/O を ``tmp_path`` fixture で完結させ、ネットワークも
Whisper モデルも呼ばない純粋なロジック確認に絞る.
"""

import os
import time
from pathlib import Path

from transcriber.local_source import (build_meta, is_media_file,
                                      list_media_files)


class TestIsMediaFile:
    """``is_media_file`` の判定."""

    def test_video_exts(self, tmp_path: Path) -> None:
        """代表的な動画拡張子を媒体と判定する."""
        for ext in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
            assert is_media_file(tmp_path / f"a{ext}") is True

    def test_audio_exts(self, tmp_path: Path) -> None:
        """代表的な音声拡張子を媒体と判定する."""
        for ext in (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac"):
            assert is_media_file(tmp_path / f"a{ext}") is True

    def test_case_insensitive(self, tmp_path: Path) -> None:
        """拡張子の大文字小文字を区別しない."""
        assert is_media_file(tmp_path / "VIDEO.MP4") is True
        assert is_media_file(tmp_path / "Audio.Mp3") is True

    def test_non_media(self, tmp_path: Path) -> None:
        """非対応拡張子は ``False``."""
        for name in ("a.txt", "a.md", "a.json", "a"):
            assert is_media_file(tmp_path / name) is False


class TestListMediaFiles:
    """``list_media_files`` の再帰スキャン."""

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        """存在しないディレクトリは空リストを返す."""
        missing = tmp_path / "nope"
        assert list_media_files(missing) == []

    def test_returns_empty_when_no_media(self, tmp_path: Path) -> None:
        """媒体ファイルが無ければ空リスト."""
        (tmp_path / "note.txt").write_text("hi")
        (tmp_path / "readme.md").write_text("hi")
        assert list_media_files(tmp_path) == []

    def test_lists_media_sorted(self, tmp_path: Path) -> None:
        """媒体ファイルをソート順で返す."""
        (tmp_path / "b.mp3").write_bytes(b"\x00")
        (tmp_path / "a.mp4").write_bytes(b"\x00")
        result = list_media_files(tmp_path)
        names = [p.name for p in result]
        assert names == sorted(names)
        assert len(result) == 2

    def test_recursive(self, tmp_path: Path) -> None:
        """サブフォルダも再帰的に探索する."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.mp4").write_bytes(b"\x00")
        (tmp_path / "top.mp3").write_bytes(b"\x00")
        result = list_media_files(tmp_path)
        names = {p.name for p in result}
        assert names == {"deep.mp4", "top.mp3"}

    def test_excludes_hidden(self, tmp_path: Path) -> None:
        """隠しファイル・隠しフォルダは除外する."""
        (tmp_path / ".hidden.mp3").write_bytes(b"\x00")
        hidden_dir = tmp_path / ".cache"
        hidden_dir.mkdir()
        (hidden_dir / "x.mp4").write_bytes(b"\x00")
        (tmp_path / "visible.mp3").write_bytes(b"\x00")
        result = list_media_files(tmp_path)
        assert [p.name for p in result] == ["visible.mp3"]

    def test_excludes_non_media(self, tmp_path: Path) -> None:
        """非媒体拡張子は無視される."""
        (tmp_path / "note.txt").write_text("hi")
        (tmp_path / "movie.mp4").write_bytes(b"\x00")
        result = list_media_files(tmp_path)
        assert [p.name for p in result] == ["movie.mp4"]


class TestBuildMeta:
    """``build_meta`` の VideoMeta 生成."""

    def test_basic_fields(self, tmp_path: Path) -> None:
        """title は stem、source は local、url/channel/duration は空."""
        f = tmp_path / "sample-video.mp4"
        f.write_bytes(b"\x00")
        meta = build_meta(f)
        assert meta.title == "sample-video"
        assert meta.source == "local"
        assert meta.url == ""
        assert meta.channel == ""
        assert meta.duration == ""

    def test_upload_date_from_mtime(self, tmp_path: Path) -> None:
        """upload_date はファイルの mtime から YYYY-MM-DD に整形."""
        f = tmp_path / "a.mp3"
        f.write_bytes(b"\x00")
        # 2024-06-15 12:00:00 相当のエポックを設定.
        fixed = time.mktime(time.strptime("2024-06-15", "%Y-%m-%d"))
        os.utime(f, (fixed, fixed))
        meta = build_meta(f)
        assert meta.upload_date == "2024-06-15"

    def test_video_id_is_stable_and_unique(self, tmp_path: Path) -> None:
        """同じパスなら同じ video_id、違うパスなら違う video_id."""
        a = tmp_path / "a.mp4"
        a.write_bytes(b"\x00")
        b = tmp_path / "b.mp4"
        b.write_bytes(b"\x00")
        meta_a1 = build_meta(a)
        meta_a2 = build_meta(a)
        meta_b = build_meta(b)
        assert meta_a1.video_id == meta_a2.video_id
        assert meta_a1.video_id != meta_b.video_id
        assert len(meta_a1.video_id) == 12
