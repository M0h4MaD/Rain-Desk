"""tests/test_bench_engine.py

الغرض: اختبار الجزء الإحصائي والتقريري في tools/bench_engine.py (لا الأرقام نفسها).
المنهج: دوال نقية بقيم معروفة (الوسيط وIQR والنسب المئوية والحمل المشتق)، ثم تشغيل سريع كامل
    على أعداد صغيرة للتأكد من الملفات الناتجة وأعمدتها وإمكان تكرار نتائج البروتوكول.
"""

from __future__ import annotations

import csv
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "bench_engine.py"


@pytest.fixture(scope="module")
def bench() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bench_engine_under_test", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_stats_converts_ns_to_ms_and_takes_percentiles(bench: ModuleType) -> None:
    stats = bench.run_stats([i * 1_000_000 for i in range(1, 101)])  # 1..100 ms
    assert stats.median == pytest.approx(50.5)
    assert stats.p95 == pytest.approx(95.05)
    assert stats.p99 == pytest.approx(99.01)


def test_aggregate_uses_median_of_medians_and_iqr(bench: ModuleType) -> None:
    runs = [bench.RunStats(m, m + 1.0, m + 2.0) for m in (1.0, 2.0, 3.0, 4.0, 100.0)]
    agg = bench.aggregate(runs)
    assert agg.median == 3.0  # الشاذة 100 لا تؤثر
    assert agg.iqr == pytest.approx(2.0)  # Q3 = 4، Q1 = 2
    assert agg.p95 == 4.0 and agg.p99 == 5.0 and agg.reps == 5


def test_aggregate_single_run_has_zero_iqr_and_empty_is_rejected(bench: ModuleType) -> None:
    assert bench.aggregate([bench.RunStats(2.0, 3.0, 4.0)]).iqr == 0.0
    with pytest.raises(ValueError):
        bench.aggregate([])


def test_frame_load_matches_the_documented_formula(bench: ModuleType) -> None:
    budget, load = bench.frame_load(cost_ms=5.0, fps_cap=30)
    assert budget == pytest.approx(1000.0 / 30.0)
    assert load == pytest.approx(5.0 * 30 / 10.0)  # 15% من نواة واحدة


def test_markdown_table_shape(bench: ModuleType) -> None:
    text = bench.markdown_table(["A", "B"], [["1", "2"], ["3", "4"]])
    assert text.splitlines() == ["| A | B |", "|---|---|", "| 1 | 2 |", "| 3 | 4 |"]


def test_counts_parser_rejects_bad_input(bench: ModuleType) -> None:
    assert bench._parse_counts("100, 200") == (100, 200)
    with pytest.raises(Exception):  # noqa: B017  (argparse.ArgumentTypeError)
        bench._parse_counts("0,5")


def test_quick_run_writes_report_and_long_csv(bench: ModuleType, tmp_path: Path) -> None:
    code = bench.main(["--quick", "--counts", "50,100", "--skip-audio", "--out", str(tmp_path)])
    assert code in (0, 1)  # 1 = تجاوز ميزانية على هذا الجهاز، وهذا ليس فشل الأداة
    report = (tmp_path / "bench_report.md").read_text(encoding="utf-8")
    assert "## Environment" in report and "RainField.step" in report
    with (tmp_path / "bench_results.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and set(rows[0]) == set(bench._CSV_FIELDS)
    engine = [r for r in rows if r["metric"] == "step_ms"]
    assert {(r["resolution"], r["drops"]) for r in engine} == {
        (res, n) for res in ("1080p", "4K") for n in ("50", "100")
    }
    assert all(int(r["reps"]) == 2 for r in rows)  # --quick = تكراران
    assert all(float(r["median_ms"]) > 0 for r in rows)


def test_warmup_frames_are_excluded_from_the_samples(
    bench: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    lengths: list[int] = []
    real = bench.run_stats

    def spy(samples: list[int]) -> object:
        lengths.append(len(samples))
        return real(samples)

    monkeypatch.setattr(bench, "run_stats", spy)
    bench._run_step(50, bench.RESOLUTIONS[0], frames=7, warmup=3)
    assert lengths == [7, 7]  # step وlayer_lines: 7 إطارات مقيسة لا 10
