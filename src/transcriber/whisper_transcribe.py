"""``faster-whisper`` を使ったローカル文字起こしエンジン.

YouTube の字幕が取得できなかった動画への Whisper フォールバック、X(Twitter)
動画への直接文字起こし、そしてローカル動画/音声ファイル (``local`` サブ
コマンド経由) の文字起こしで共通して利用する.

``faster-whisper`` は PyAV (FFmpeg ライブラリの Python バインディング) を
バンドルしており、mp3/wav/m4a/flac/ogg/opus/aac などの音声だけでなく
mp4/mov/mkv/webm/avi などの動画コンテナからも自動で音声ストリームを抽出
してデコードする. そのため本モジュールは任意の媒体ファイルパスをそのまま
受け付けられる.

モデルはシングルトンとして遅延初期化し、同一プロセスで複数ファイルを処理
する場合も 1 度しかロードしない. Apple Silicon / CPU でも安定する
``compute_type="int8"``、``device="auto"`` を既定とする. 初回実行時に
約 1.5GB のモデルダウンロードが発生する旨を呼び出し前にログで告知する.
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
    """媒体ファイルを Whisper で文字起こしし、プレーンテキストを返す.

    音声ファイル (mp3/wav/m4a/flac/ogg/opus/aac 等) だけでなく、動画
    ファイル (mp4/mov/mkv/webm/avi 等) も直接渡せる. PyAV (faster-whisper
    にバンドルされる FFmpeg ライブラリ) が最初の音声ストリームを抽出して
    デコードするため、呼び出し側で音声抽出は不要.

    Args:
        audio_path: 文字起こし対象の媒体ファイルパス.
        model_size: 使用する Whisper モデルのサイズ. 既定は ``medium``.

    Returns:
        ``source="whisper"`` の ``TranscriptResult``. ``language`` は
        Whisper が推定した言語 (``ja`` / ``en`` など).

    Raises:
        FileNotFoundError: ``audio_path`` が存在しない場合.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"媒体ファイルが存在しません: {audio_path}")

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
