"""プロジェクト全体で共有するイミュータブルな dataclass 定義.

モジュール横断で利用する値オブジェクトをここに集約する. すべて
``frozen=True`` の dataclass であり、生成後の変更を禁止することで
副作用のないデータフローを保証する.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoMeta:
    """1 本の動画 (YouTube / X / ローカル) のメタデータ.

    yt-dlp などから取得した動画情報を正規化して保持する. ファイル名の
    生成や Markdown の frontmatter 出力に用いる. ソース (YouTube / X /
    ローカルファイル) によって一部フィールドが空文字列になり得る.

    Attributes:
        video_id: 動画 ID (YouTube 動画 ID / X ツイート ID / ローカル
            ファイルパスから算出した識別子).
        title: 動画タイトル (サニタイズ前).
        url: 動画の正規 URL. ローカルファイルの場合は空文字列.
        channel: チャンネル名 / 投稿者名. 取得できない場合は空文字列.
        upload_date: 投稿日 (``YYYY-MM-DD`` 形式). 不明なら空文字列.
        duration: 再生時間 (``HH:MM:SS`` 形式). 不明なら空文字列.
        source: 入力ソース種別 (``"youtube"`` / ``"x"`` / ``"local"``).
            markdown_writer の frontmatter 出力時に ``origin`` キーとして
            出力する. デフォルトは ``"youtube"`` で後方互換を保つ.
    """

    video_id: str
    title: str
    url: str
    channel: str
    upload_date: str
    duration: str
    source: str = "youtube"


@dataclass(frozen=True)
class TranscriptResult:
    """文字起こし結果を表す値オブジェクト.

    字幕取得 (captions) と Whisper ローカル推論 (whisper) の両方で
    共通して利用する. どちらから得られた結果かは ``source`` に
    格納する.

    Attributes:
        text: 本文テキスト (タイムスタンプ無しのプレーンテキスト).
        language: 言語コード (``ja`` / ``en`` など、正規化済み).
        source: 出典. ``"captions"`` または ``"whisper"``.
    """

    text: str
    language: str
    source: str


@dataclass(frozen=True)
class FailedVideo:
    """処理に失敗した動画を記録するための値オブジェクト.

    実行結果サマリ (``RunReport``) の失敗一覧に積み上げる. ユーザーが
    後で再実行対象を把握しやすいように、タイトル・URL・失敗理由を
    必ず含める.

    Attributes:
        title: 動画タイトル (取得できない場合は URL を代用してよい).
        url: 動画 URL.
        reason: 失敗理由 (例外メッセージなど).
    """

    title: str
    url: str
    reason: str
