"""``transcriber.run_report`` モジュールのユニットテスト.

イミュータブル更新 API (``with_success`` / ``with_skip`` / ``with_failure``) と
``format_report`` の整形結果を確認する.
"""

from transcriber.run_report import RunReport, format_report
from transcriber.types import FailedVideo


class TestImmutableUpdates:
    """``RunReport`` のイミュータブル更新を確認する."""

    def test_initial_is_zero(self) -> None:
        """初期状態は全てゼロ."""
        report = RunReport()
        assert report.successes == 0
        assert report.skipped == 0
        assert report.failed == ()

    def test_with_success_returns_new_instance(self) -> None:
        """``with_success`` は元オブジェクトを変更せず新オブジェクトを返す."""
        original = RunReport()
        updated = original.with_success()
        assert original.successes == 0
        assert updated.successes == 1
        assert updated is not original

    def test_with_skip_returns_new_instance(self) -> None:
        """``with_skip`` も同様."""
        original = RunReport()
        updated = original.with_skip()
        assert original.skipped == 0
        assert updated.skipped == 1

    def test_with_failure_appends(self) -> None:
        """``with_failure`` は failed tuple に追加する."""
        fv = FailedVideo(title="T", url="U", reason="R")
        original = RunReport()
        updated = original.with_failure(fv)
        assert original.failed == ()
        assert updated.failed == (fv,)

    def test_chained_updates(self) -> None:
        """複数更新を連鎖しても元オブジェクトは不変."""
        report = (
            RunReport()
            .with_success()
            .with_success()
            .with_skip()
            .with_failure(FailedVideo("a", "b", "c"))
        )
        assert report.successes == 2
        assert report.skipped == 1
        assert len(report.failed) == 1


class TestFormatReport:
    """``format_report`` の整形結果を確認する."""

    def test_format_all_success(self) -> None:
        """失敗 0 件なら「すべて成功しました」相当のメッセージが出る."""
        report = RunReport().with_success().with_success()
        text = format_report(report)
        assert "成功: 2" in text
        assert "スキップ: 0" in text
        assert "失敗: 0" in text
        assert "すべて成功しました" in text

    def test_format_with_failures(self) -> None:
        """失敗リストが「Failed videos」セクションに列挙される."""
        report = (
            RunReport()
            .with_success()
            .with_failure(FailedVideo("Title A", "https://y/a", "captions disabled"))
            .with_failure(FailedVideo("Title B", "https://y/b", "DeepL quota"))
        )
        text = format_report(report)
        assert "成功: 1" in text
        assert "失敗: 2" in text
        assert "Failed videos" in text
        assert "Title A" in text
        assert "https://y/a" in text
        assert "captions disabled" in text
        assert "Title B" in text
        assert "DeepL quota" in text

    def test_summary_header(self) -> None:
        """「Summary」見出しが含まれる."""
        text = format_report(RunReport())
        assert "Summary" in text
