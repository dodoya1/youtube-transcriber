"""Markdown 生成・ファイル名サニタイズ・出力フォルダ配置ロジック.

出力ファイルの配置規則はプロジェクト全体の設計上の肝であり、翻訳の有無で
構造が切り替わる:

- **翻訳あり** (英語動画など): ``out_dir/<base>/<base>.md`` と
  ``<base>-ja.md`` をサブフォルダにまとめる. 原文と訳文を対で管理するため.
- **翻訳なし** (日本語動画など): ``out_dir/<base>.md`` のフラット配置.

既存ファイルは既定でスキップし、``force=True`` で明示的に上書きする.
"""

import logging
import re
from pathlib import Path

from transcriber.types import TranscriptResult, VideoMeta

_logger = logging.getLogger(__name__)

_MAX_BASE_LENGTH = 120
_VIDEO_ID_SUFFIX_LENGTH = 6
_FORBIDDEN_CHARS_RE = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_filename(title: str, video_id: str) -> str:
    """動画タイトルと動画 ID からファイル名用のベース文字列を作る.

    OS で禁止されている記号類を除去し、空白を単一化し、長すぎる場合は
    切り詰める. 衝突回避のため末尾に ``-<video_id の先頭 6 文字>`` を付与する.

    Args:
        title: 動画タイトル (サニタイズ前).
        video_id: YouTube の動画 ID.

    Returns:
        ファイル名の拡張子を含まないベース文字列.
    """
    cleaned = _FORBIDDEN_CHARS_RE.sub("", title)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    suffix = f"-{video_id[:_VIDEO_ID_SUFFIX_LENGTH]}"
    max_title_len = _MAX_BASE_LENGTH - len(suffix)
    if len(cleaned) > max_title_len:
        cleaned = cleaned[:max_title_len].rstrip()
    return f"{cleaned}{suffix}" if cleaned else video_id[:_VIDEO_ID_SUFFIX_LENGTH]


def _escape_quotes(value: str) -> str:
    """frontmatter のダブルクォート囲みに入れる文字列をエスケープする.

    Args:
        value: エスケープ対象文字列.

    Returns:
        ``\\`` と ``"`` をバックスラッシュでエスケープした文字列.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_markdown(
    meta: VideoMeta,
    result: TranscriptResult,
    *,
    translated_from: str | None = None,
) -> str:
    """YAML frontmatter + 本文の Markdown 文字列を生成する.

    翻訳版を生成する際は ``translated_from`` に元言語コードを渡すと、
    frontmatter に ``translated_from:`` 行が追加される.

    Args:
        meta: 動画メタデータ.
        result: 文字起こし結果 (翻訳版の場合は訳文とメタを詰めたもの).
        translated_from: 翻訳版のときの元言語コード. 原文出力時は ``None``.

    Returns:
        frontmatter を含む完全な Markdown 文字列.
    """
    lines: list[str] = ["---"]
    lines.append(f'title: "{_escape_quotes(meta.title)}"')
    lines.append(f"url: {meta.url}")
    lines.append(f'channel: "{_escape_quotes(meta.channel)}"')
    lines.append(f"upload_date: {meta.upload_date}")
    lines.append(f'duration: "{meta.duration}"')
    lines.append(f"language: {result.language}")
    lines.append(f"source: {result.source}")
    if translated_from is not None:
        lines.append(f"translated_from: {translated_from}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {meta.title}")
    lines.append("")
    lines.append(result.text)
    lines.append("")
    return "\n".join(lines)


def resolve_paths(
    base: str,
    out_dir: Path,
    *,
    has_translation: bool,
) -> tuple[Path, Path | None]:
    """ベース名と出力ディレクトリから原文・訳文の出力パスを決定する.

    Args:
        base: :func:`sanitize_filename` が返すベース名.
        out_dir: 出力先ディレクトリ.
        has_translation: 翻訳版も出力するかどうか.

    Returns:
        ``(main_path, translated_path_or_None)`` のタプル.
        ``has_translation=False`` の場合はフラット配置、``True`` の場合は
        ``out_dir/<base>/`` サブフォルダ配下にまとめる.
    """
    if has_translation:
        folder = out_dir / base
        return (folder / f"{base}.md", folder / f"{base}-ja.md")
    return (out_dir / f"{base}.md", None)


def _write_if_needed(path: Path, content: str, *, force: bool) -> Path | None:
    """存在チェックを行い、必要ならファイルを書き出す補助関数.

    Args:
        path: 書き出し先.
        content: 書き出す文字列.
        force: ``True`` なら既存ファイルを上書きする.

    Returns:
        実際に書き出した場合はそのパス、スキップした場合は ``None``.
    """
    if path.exists() and not force:
        _logger.info("既存のためスキップ: %s", path)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_outputs(
    meta: VideoMeta,
    result: TranscriptResult,
    translated_text: str | None,
    out_dir: Path,
    *,
    force: bool,
) -> list[Path]:
    """動画 1 本分の Markdown を (必要に応じて訳文と共に) 書き出す.

    Args:
        meta: 動画メタデータ.
        result: 原文の文字起こし結果.
        translated_text: 日本語訳文字列. 翻訳無しなら ``None``.
        out_dir: 出力先ディレクトリ.
        force: 既存ファイルを上書きするかどうか.

    Returns:
        実際に書き出したファイルのパス一覧. スキップされた場合は空リスト.
    """
    base = sanitize_filename(meta.title, meta.video_id)
    has_translation = translated_text is not None
    main_path, translated_path = resolve_paths(
        base, out_dir, has_translation=has_translation
    )

    written: list[Path] = []
    main_content = build_markdown(meta, result)
    if (p := _write_if_needed(main_path, main_content, force=force)) is not None:
        written.append(p)

    if has_translation and translated_path is not None:
        translated_result = TranscriptResult(
            text=translated_text or "",
            language="ja",
            source=result.source,
        )
        translated_content = build_markdown(
            meta, translated_result, translated_from=result.language
        )
        if (
            p := _write_if_needed(translated_path, translated_content, force=force)
        ) is not None:
            written.append(p)

    return written
