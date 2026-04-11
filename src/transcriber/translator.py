"""DeepL API を用いた英語 → 日本語翻訳ユーティリティ.

本プロジェクトでは英語動画の文字起こしに対してのみ ``-ja.md`` を追加
生成する. そのため翻訳関数は「英語 → 日本語」の一方向のみを提供する.

``api_key`` が空または未設定の場合は ``None`` を返し、呼び出し側は
翻訳ファイルの生成をスキップして warning を出す設計とする (API キー無しで
クラッシュさせない). また、段落単位での分割送信により巨大な本文でも
安定して送信でき、API 側のバッチ処理にも乗りやすい.
"""

import logging
import os

import deepl

from transcriber.types import FailedVideo  # noqa: F401  (型ヒント将来用)

_logger = logging.getLogger(__name__)

_TARGET_LANG = "JA"


class TranslationError(RuntimeError):
    """DeepL 翻訳の呼び出しに失敗したことを表す例外.

    使用量超過・認証失敗・ネットワーク障害などを上位でまとめて捕捉する
    ために用いる.
    """


def _resolve_api_key(api_key: str | None) -> str | None:
    """引数または環境変数から DeepL API キーを解決する.

    Args:
        api_key: 明示的に渡された API キー. ``None`` または空文字列なら
            ``DEEPL_API_KEY`` 環境変数を参照する.

    Returns:
        有効な API キー文字列. 未設定なら ``None``.
    """
    if api_key:
        return api_key
    env = os.environ.get("DEEPL_API_KEY")
    return env if env else None


def _split_paragraphs(text: str) -> list[str]:
    """テキストを空行区切りの段落リストに分割する補助関数.

    Args:
        text: 翻訳対象の原文.

    Returns:
        空でない段落のリスト. 入力が空なら空リスト.
    """
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def translate_to_japanese(text: str, api_key: str | None = None) -> str | None:
    """英語テキストを日本語に翻訳する.

    段落単位で分割送信し、DeepL の ``translate_text`` をまとめて呼び出す.
    呼び出し側の便宜のため、API キー未設定時は例外にせず ``None`` を返す.

    Args:
        text: 翻訳対象の原文 (英語を想定).
        api_key: DeepL API キー. ``None`` なら ``DEEPL_API_KEY`` 環境変数を参照.

    Returns:
        翻訳後のテキスト. 以下の場合は ``None`` を返す:

        - API キーが未設定.
        - 入力テキストが空.

    Raises:
        TranslationError: 使用量超過・認証失敗・ネットワーク障害など、
            DeepL 側の呼び出しが失敗した場合.
    """
    if not text.strip():
        return None

    resolved_key = _resolve_api_key(api_key)
    if resolved_key is None:
        _logger.warning(
            "DEEPL_API_KEY が未設定のため翻訳をスキップします"
        )
        return None

    paragraphs = _split_paragraphs(text) or [text.strip()]
    translator = deepl.Translator(resolved_key)

    try:
        results = translator.translate_text(
            paragraphs, target_lang=_TARGET_LANG)
    except deepl.QuotaExceededException as exc:
        raise TranslationError("DeepL の月間文字数上限を超過しました") from exc
    except deepl.AuthorizationException as exc:
        raise TranslationError("DeepL API キーが不正です") from exc
    except deepl.DeepLException as exc:
        raise TranslationError(f"DeepL 翻訳に失敗: {exc}") from exc

    if isinstance(results, list):
        translated_paragraphs = [r.text for r in results]
    else:
        translated_paragraphs = [results.text]
    return "\n\n".join(translated_paragraphs)
