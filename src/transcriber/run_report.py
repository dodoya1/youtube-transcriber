"""実行結果サマリ (成功 / スキップ / 失敗) の集計と整形.

``RunReport`` は frozen dataclass であり、状態を変更するには必ず新しい
インスタンスを返す ``with_success`` / ``with_skip`` / ``with_failure`` を
経由する. これにより複数動画の並列処理でも安全に状態を積み上げられる.

``format_report`` は CLI の末尾で出力する整形文字列を返す. 失敗ゼロ件の
場合は明示的に「すべて成功しました」を表示し、何を再実行すべきかが
ひと目で分かるよう Failed videos セクションを提供する.
"""

from dataclasses import dataclass, field, replace

from transcriber.types import FailedVideo


@dataclass(frozen=True)
class RunReport:
    """実行結果の集計を保持するイミュータブル dataclass.

    Attributes:
        successes: 成功件数.
        skipped: 既存ファイルスキップ等によるスキップ件数.
        failed: 失敗した動画のタプル (挿入順).
    """

    successes: int = 0
    skipped: int = 0
    failed: tuple[FailedVideo, ...] = field(default_factory=tuple)

    def with_success(self) -> "RunReport":
        """成功件数を 1 増やした新しい ``RunReport`` を返す.

        Returns:
            ``successes`` を +1 した新インスタンス.
        """
        return replace(self, successes=self.successes + 1)

    def with_skip(self) -> "RunReport":
        """スキップ件数を 1 増やした新しい ``RunReport`` を返す.

        Returns:
            ``skipped`` を +1 した新インスタンス.
        """
        return replace(self, skipped=self.skipped + 1)

    def with_failure(self, failure: FailedVideo) -> "RunReport":
        """失敗リストに 1 件追加した新しい ``RunReport`` を返す.

        Args:
            failure: 追加する ``FailedVideo``.

        Returns:
            ``failed`` に 1 件追加した新インスタンス.
        """
        return replace(self, failed=(*self.failed, failure))


def format_report(report: RunReport) -> str:
    """``RunReport`` を CLI 末尾に表示する文字列に整形する.

    常に ``===== Summary =====`` ブロックを含み、失敗があれば続けて
    ``===== Failed videos =====`` ブロックを追加する. 失敗 0 件時は
    「すべて成功しました」と明示する.

    Args:
        report: 整形対象の ``RunReport``.

    Returns:
        改行区切りの整形済み文字列.
    """
    lines: list[str] = []
    lines.append("===== Summary =====")
    lines.append(
        f"成功: {report.successes} / スキップ: {report.skipped} / 失敗: {len(report.failed)}"
    )

    if not report.failed:
        lines.append("すべて成功しました")
        return "\n".join(lines)

    lines.append("")
    lines.append("===== Failed videos =====")
    for fv in report.failed:
        lines.append(f"- {fv.title} | {fv.url}")
        lines.append(f"  reason: {fv.reason}")
    return "\n".join(lines)
