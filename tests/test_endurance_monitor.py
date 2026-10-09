"""tests/test_endurance_monitor.py: منطق أداة التحمّل النقي (التلخيص وCSV) ومسار العيّنات على Linux."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import endurance_monitor as em  # noqa: E402


def _series(
    minutes: float, memory: Callable[[float], float], step_s: float = 10.0
) -> list[em.Sample]:
    count = int(minutes * 60 / step_s)
    return [
        em.Sample(k * step_s, memory(k * step_s), memory(k * step_s) * 0.8, 1.0)
        for k in range(1, count + 1)
    ]


def test_flat_memory_passes_with_zero_growth() -> None:
    verdict = em.summarize(_series(60, lambda _t: 120.0))
    assert verdict.growth_pct == pytest.approx(0.0, abs=1e-9)
    assert verdict.passed and verdict.baseline_mb == verdict.final_mb == 120.0


def test_slow_leak_above_five_percent_fails() -> None:
    # 120 MB عند الدقيقة 5-10 ثم +0.2 MB في الدقيقة: بعد 55 دقيقة نحو +10%
    verdict = em.summarize(_series(60, lambda t: 120.0 + 0.2 * t / 60.0))
    assert not verdict.passed and verdict.growth_pct > 5.0


def test_growth_just_under_the_limit_passes() -> None:
    verdict = em.summarize(_series(60, lambda t: 100.0 if t < 3000 else 104.0))
    assert verdict.growth_pct == pytest.approx(4.0) and verdict.passed


def test_warmup_spike_is_ignored() -> None:
    # قفزة كبيرة في أول 4 دقائق (الإحماء) لا تُحسب نموًا
    verdict = em.summarize(_series(60, lambda t: 300.0 if t < 240 else 120.0))
    assert verdict.passed and verdict.growth_pct == pytest.approx(0.0, abs=1e-9)


def test_median_resists_short_spikes() -> None:
    def memory(t: float) -> float:
        return 500.0 if 3000 < t < 3010 else 120.0  # قفزة واحدة قرب النهاية

    assert em.summarize(_series(60, memory)).passed


def test_too_short_runs_and_empty_input_are_rejected() -> None:
    with pytest.raises(ValueError, match="too short"):
        em.summarize(_series(10, lambda _t: 120.0))
    with pytest.raises(ValueError, match="no samples"):
        em.summarize([])


def test_short_windows_can_be_configured_for_quick_checks() -> None:
    samples = _series(6, lambda t: 100.0 + t / 60.0)
    verdict = em.summarize(samples, warmup_s=60.0, baseline_s=60.0, final_s=60.0)
    assert verdict.growth_pct > 0.0 and verdict.samples == len(samples)


def test_markdown_table_reports_the_result() -> None:
    text = em.to_markdown(em.summarize(_series(60, lambda _t: 120.0)))
    assert "| Result | PASS |" in text and "+0.00 %" in text
    bad = em.to_markdown(em.summarize(_series(60, lambda t: 120.0 + 0.2 * t / 60.0)))
    assert "| Result | FAIL |" in bad


def test_csv_round_trip(tmp_path: Path) -> None:
    samples = [em.Sample(10.0, 120.5, 90.25, 1.5), em.Sample(20.0, 121.0, 90.5, 0.75)]
    path = tmp_path / "run.csv"
    em.write_csv(path, samples)
    lines = path.read_text(encoding="ascii").splitlines()
    assert lines[0] == "t_s,working_set_mb,private_mb,cpu_percent"
    assert lines[1] == "10.0,120.50,90.25,1.50" and len(lines) == 3


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc")
def test_sampler_reads_the_current_process_on_linux() -> None:
    sampler = em.Sampler(os.getpid())
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:  # نشغل المعالج قليلًا
        sum(range(1000))
    sample = sampler.sample()
    assert sample.working_set_mb > 5.0 and sample.private_mb > 1.0
    assert sample.cpu_percent >= 0.0 and sample.t_s > 0.0
