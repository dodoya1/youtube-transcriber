"""既存 Markdown ファイルを翻訳する ``translate`` サブコマンドの実装.

``transcribe`` 時に DeepL 上限で翻訳だけ失敗した動画を後追いで翻訳したり、
手書きの英語 Markdown をまとめて日本語化したりするユースケースを想定している.

本モジュールは入力 ``.md`` を決して書き換えず、必ず同じフォルダに
``<ファイル名>-ja.md`` を新規作成する. 既存の ``-ja.md`` は既定でスキップし、
``force=True`` のとき明示的に上書きする.

frontmatter の取り扱いはプロジェクト内で自前実装する. これは PyYAML 等の
追加依存を避けつつ、``markdown_writer.build_markdown`` が生成する決定論的な
フォーマット (``key: value`` / ``key: "quoted"``) のみを想定しているためである.
"""

import logging
from pathlib import Path

from transcriber.translator import translate_to_japanese

_logger = logging.getLogger(__name__)

_QUOTED_KEYS = frozenset({"title", "channel", "duration"})
_FRONTMATTER_DELIMITER = "---"


def _parse_frontmatter(text: str) -> dict[str, str]:
    """frontmatter の本文 (``---`` を含まない行群) を dict に変換する.

    ``markdown_writer.build_markdown`` が書き出す形式だけを想定し、
    ``key: value`` または ``key: "quoted value"`` の 1 行 1 ペアを扱う.
    クォート内では ``\\"`` と ``\\\\`` のみエスケープ解除する.

    Args:
        text: frontmatter の内側テキスト.

    Returns:
        キー順を保持した辞書 (Python 3.7+ の ``dict`` 挿入順依存).
    """
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        result[key] = value
    return result


def parse_markdown(path: Path) -> tuple[dict[str, str], str]:
    """Markdown ファイルから frontmatter 辞書と本文を取り出す.

    先頭が ``---\\n`` で始まらない、または閉じ ``---`` が見つからない場合は
    frontmatter 無しとみなし、空 dict と元テキストをそのまま返す.

    Args:
        path: 対象の Markdown ファイルパス.

    Returns:
        ``(frontmatter, body)`` のタプル. ``body`` の先頭・末尾の余分な
        空白行は ``strip`` され、H1 見出しを含む本文がそのまま入る.

    Raises:
        FileNotFoundError: ``path`` が存在しない場合.
    """
    content = path.read_text(encoding="utf-8")
    if not content.startswith(_FRONTMATTER_DELIMITER + "\n"):
        return ({}, content.strip())

    remainder = content[len(_FRONTMATTER_DELIMITER) + 1:]
    end_marker = remainder.find("\n" + _FRONTMATTER_DELIMITER)
    if end_marker == -1:
        return ({}, content.strip())

    front_text = remainder[:end_marker]
    after = remainder[end_marker + len(_FRONTMATTER_DELIMITER) + 1:]
    body = after.lstrip("\n").rstrip()
    return (_parse_frontmatter(front_text), body)


def _format_frontmatter_value(key: str, value: str) -> str:
    """単一の frontmatter 行を整形する.

    ``_QUOTED_KEYS`` に含まれるキーはダブルクォートで囲み、``\\`` と ``"``
    をエスケープする. それ以外は素のまま出力する.

    Args:
        key: キー名.
        value: 値文字列.

    Returns:
        ``key: value`` の 1 行.
    """
    if key in _QUOTED_KEYS:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}: "{escaped}"'
    return f"{key}: {value}"


def build_translated_markdown(
    front: dict[str, str],
    body_ja: str,
    source_lang: str,
) -> str:
    """翻訳後の frontmatter と本文を連結して Markdown 文字列を作る.

    元 frontmatter のキー順を保ったまま ``language`` を ``ja`` に上書きし、
    ``translated_from`` に原文言語を設定する (末尾に追加). 本文の H1 見出しや
    本文テキストは翻訳済みのものをそのまま利用する.

    Args:
        front: 元の frontmatter 辞書.
        body_ja: 翻訳済みの本文テキスト (H1 見出しを含んでよい).
        source_lang: 原文の言語コード (``en`` など).

    Returns:
        ``---`` 区切り frontmatter + 空行 + 本文 + 末尾改行の文字列.
    """
    new_front: dict[str, str] = {}
    for key, value in front.items():
        if key in ("language", "translated_from"):
            continue
        new_front[key] = value
    new_front["language"] = "ja"
    new_front["translated_from"] = source_lang

    lines: list[str] = [_FRONTMATTER_DELIMITER]
    for key, value in new_front.items():
        lines.append(_format_frontmatter_value(key, value))
    lines.append(_FRONTMATTER_DELIMITER)
    lines.append("")
    lines.append(body_ja.strip())
    lines.append("")
    return "\n".join(lines)


def _derive_output_path(source: Path) -> Path:
    """入力パスから ``<ベース名>-ja.md`` 出力パスを導出する.

    Args:
        source: 入力 Markdown ファイルのパス.

    Returns:
        同じディレクトリ内の ``<stem>-ja.md`` パス.
    """
    return source.with_name(f"{source.stem}-ja.md")


def translate_file(
    path: Path,
    api_key: str | None = None,
    *,
    force: bool = False,
) -> Path | None:
    """単一の Markdown ファイルを翻訳し、隣に ``-ja.md`` を書き出す.

    入力ファイルは一切変更・移動しない. 以下のケースでは ``None`` を返して
    スキップする:

    - frontmatter の ``language`` が既に ``ja``.
    - 入力ファイル名が既に ``-ja`` で終わっている.
    - 出力先 ``-ja.md`` が既に存在し ``force`` が ``False``.
    - DeepL API キー未設定・翻訳結果が空.

    Args:
        path: 翻訳対象の Markdown ファイルパス.
        api_key: DeepL API キー. ``None`` なら環境変数 ``DEEPL_API_KEY`` を参照.
        force: 既存の ``-ja.md`` を上書きするかどうか.

    Returns:
        書き出した出力ファイルのパス. スキップ時は ``None``.

    Raises:
        FileNotFoundError: 入力ファイルが存在しない場合.
        transcriber.translator.TranslationError: DeepL 呼び出しが失敗した場合.
    """
    if not path.exists():
        raise FileNotFoundError(f"入力ファイルが存在しません: {path}")

    if path.stem.endswith("-ja"):
        _logger.warning("既に -ja 付きのファイルのためスキップ: %s", path)
        return None

    front, body = parse_markdown(path)

    source_lang = (front.get("language") or "").strip().lower() or "en"
    if source_lang == "ja":
        _logger.warning("日本語ファイルのためスキップ: %s", path)
        return None

    if not body.strip():
        _logger.warning("本文が空のためスキップ: %s", path)
        return None

    out_path = _derive_output_path(path)
    if out_path.exists() and not force:
        _logger.info("既存のためスキップ: %s", out_path)
        return None

    body_ja = translate_to_japanese(body, api_key=api_key)
    if body_ja is None:
        _logger.warning("翻訳結果が得られなかったためスキップ: %s", path)
        return None

    content = build_translated_markdown(front, body_ja, source_lang)
    out_path.write_text(content, encoding="utf-8")
    _logger.info("翻訳済み Markdown を書き出し: %s", out_path)
    return out_path
