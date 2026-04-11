"""言語検出・言語コード正規化の純粋関数群.

外部ライブラリ (langdetect 等) を増やさないため、日本語判定は Unicode の
コードポイントレンジ (ひらがな/カタカナ/CJK 統合漢字) に属する文字の比率
で行う簡易ヒューリスティックを採用する. 文字起こしの言語が ``ja`` か否か
という二値判定しか必要ないため、これで十分実用に足りる.
"""

_HIRAGANA_START, _HIRAGANA_END = 0x3040, 0x309F
_KATAKANA_START, _KATAKANA_END = 0x30A0, 0x30FF
_CJK_START, _CJK_END = 0x4E00, 0x9FFF

_JAPANESE_RATIO_THRESHOLD = 0.2


def _is_japanese_char(ch: str) -> bool:
    """1 文字が日本語 (ひら/カナ/CJK) に属するか判定する補助関数.

    Args:
        ch: 判定対象の 1 文字.

    Returns:
        ひらがな/カタカナ/CJK 統合漢字のいずれかなら ``True``.
    """
    code = ord(ch)
    return (
        _HIRAGANA_START <= code <= _HIRAGANA_END
        or _KATAKANA_START <= code <= _KATAKANA_END
        or _CJK_START <= code <= _CJK_END
    )


def is_japanese(text: str) -> bool:
    """テキストが日本語かどうかを簡易ヒューリスティックで判定する.

    日本語文字 (ひらがな/カタカナ/CJK) の占める比率が閾値 (20%) を
    超えれば日本語とみなす. 英文中に単語レベルの日本語が混ざる程度では
    日本語扱いにならない.

    Args:
        text: 判定対象のテキスト.

    Returns:
        日本語と推定される場合 ``True``、そうでなければ ``False``.
        空文字列・空白のみ・記号のみは ``False``.
    """
    if not text:
        return False

    visible = [c for c in text if not c.isspace()]
    if not visible:
        return False

    japanese_count = sum(1 for c in visible if _is_japanese_char(c))
    ratio = japanese_count / len(visible)
    return ratio >= _JAPANESE_RATIO_THRESHOLD


def normalize_language_code(code: str) -> str:
    """言語コードを小文字・主要部分のみに正規化する.

    ``ja-JP`` / ``en_US`` / ``zh-Hans`` のような拡張付きコードから
    ``ja`` / ``en`` / ``zh`` を抽出する. YouTube / Whisper / DeepL で
    表記ゆれがあるため、横断的に比較する前に必ず通す.

    Args:
        code: 正規化前の言語コード.

    Returns:
        小文字化された主要言語コード. 空入力はそのまま空文字列を返す.
    """
    if not code:
        return ""
    lowered = code.lower()
    for separator in ("-", "_"):
        if separator in lowered:
            return lowered.split(separator, 1)[0]
    return lowered
