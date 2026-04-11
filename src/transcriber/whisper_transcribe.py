"""``faster-whisper`` を使ったローカル文字起こしフォールバック.

YouTube の字幕が取得できなかった動画に対して、ダウンロード済み音声ファイルを
ローカルの Whisper モデルで文字起こしする. モデルはシングルトンとして
遅延初期化し、同一プロセスで複数動画を処理する場合も 1 度しかロードしない.

Apple Silicon / CPU でも安定する ``compute_type="int8"``、``device="auto"`` を
既定とする. 初回実行時に約 1.5GB のモデルダウンロードが発生する旨を呼び出し
前にログで告知する.
"""

import logging
from pathlib import Path

from faster_whisper import WhisperModel

from transcriber.language import normalize_language_code
from transcriber.types import TranscriptResult

_logger = logging.getLogger(__name__)

_DEFAULT_MODEL_SIZE = "medium"
_DEFAULT_DEVICE = "auto"
_DEFAULT_COMPUTE_TYPE = "int8"

_model_cache: dict[str, WhisperModel] = {}


def _get_model(model_size: str) -> WhisperModel:
    """指定サイズの ``WhisperModel`` を遅延初期化して返す.

    同一プロセス内では同じサイズのモデルを再利用する. 初回呼び出し時は
    モデル重み (``medium`` なら約 1.5GB) が自動ダウンロードされ、数分の
    時間とネットワーク帯域を要する.

    Args:
        model_size: ``tiny`` / ``base`` / ``small`` / ``medium`` / ``large-v3`` 等.

    Returns:
        ロード済みの ``WhisperModel``.
    """
    if model_size not in _model_cache:
        _logger.info(
            "Whisper モデル '%s' をロードします (初回は自動ダウンロードで数分かかる場合があります)",
            model_size,
        )
        _model_cache[model_size] = WhisperModel(
            model_size,
            device=_DEFAULT_DEVICE,
            compute_type=_DEFAULT_COMPUTE_TYPE,
        )
    return _model_cache[model_size]


def transcribe(
    audio_path: Path, model_size: str = _DEFAULT_MODEL_SIZE
) -> TranscriptResult:
    """音声ファイルを Whisper で文字起こしし、プレーンテキストを返す.

    Args:
        audio_path: 文字起こし対象の音声ファイルパス (mp3 等).
        model_size: 使用する Whisper モデルのサイズ. 既定は ``medium``.

    Returns:
        ``source="whisper"`` の ``TranscriptResult``. ``language`` は
        Whisper が推定した言語 (``ja`` / ``en`` など).

    Raises:
        FileNotFoundError: ``audio_path`` が存在しない場合.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"音声ファイルが存在しません: {audio_path}")

    _logger.info("Whisper 文字起こしを開始: %s", audio_path)
    model = _get_model(model_size)
    segments, info = model.transcribe(str(audio_path), beam_size=5)

    parts: list[str] = []
    for segment in segments:
        text = (segment.text or "").strip()
        if text:
            parts.append(text)
    joined = " ".join(parts)
    body = " ".join(joined.split())

    language = normalize_language_code(getattr(info, "language", "") or "")
    return TranscriptResult(text=body, language=language, source="whisper")
