"""tools/bench_engine.py

الغرض: قياس أداء المحرك والرسم ومقارنته بميزانية الأداء (performance_budget).
المسؤوليات: وسيط ووصول p95 وp99 لكل من RainField.step وlayer_lines ورسم paint_rain على
    لوحة 1080p، لأعداد قطرات مختلفة، ومقارنة نهجي تقسيم الطبقات (argsort مقابل الأقنعة).
المخرجات: جدول Markdown في الطرفية وملف bench_results.csv في مجلد التشغيل.
ملاحظة: نسخة M4؛ يُضاف قياس RainSynth (الصوت) عند تسليم مرحلة الصوت.
الاستعمال: python tools/bench_engine.py
"""

from __future__ import annotations

import csv
import math
import sys
import time
from pathlib import Path
from typing import Final

import numpy as np

# python tools/bench_engine.py يضيف مجلد tools فقط إلى المسار، فنضيف جذر المشروع يدويًا.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raindesk.config.schema import default_settings  # noqa: E402
from raindesk.engine.params import params_from_settings  # noqa: E402
from raindesk.engine.rain_field import RainField  # noqa: E402

_COUNTS: Final[tuple[int, ...]] = (500, 1000, 2000, 5000)
_FRAMES: Final[int] = 600  # عدد الإطارات المقيسة لكل عدد قطرات
_WARMUP_FRAMES: Final[int] = 30  # إطارات إحماء لا تُحسب (ملء الذاكرة المؤقتة وJIT الداخلي)
_WIDTH: Final[int] = 1920
_HEIGHT: Final[int] = 1080
_DT: Final[float] = 1.0 / 60.0
_SEED: Final[int] = 12345
_LAYERS: Final[int] = 5
_NS_PER_MS: Final[float] = 1e6
_PARTITION_REPEATS: Final[int] = 300
_CSV_PATH: Final[Path] = Path("bench_results.csv")
# حدود ميزانية الأداء (ms) من المواصفة.
_BUDGET_STEP_1000_MS: Final[float] = 1.0
_BUDGET_STEP_5000_MS: Final[float] = 3.0
_BUDGET_PAINT_1000_MS: Final[float] = 6.0


def _stats(samples_ns: list[int]) -> tuple[float, float, float]:
    """(الوسيط، p95، p99) بالميلي ثانية من عينات بالنانوثانية."""
    values = np.asarray(samples_ns, dtype=np.float64) / _NS_PER_MS
    median, p95, p99 = np.percentile(values, [50, 95, 99])
    return float(median), float(p95), float(p99)


def _bench_engine(count: int) -> tuple[tuple[float, float, float], float]:
    """يقيس step (وسيط وp95 وp99) وlayer_lines (وسيط) لعدد قطرات معيّن."""
    params = params_from_settings(default_settings())
    field = RainField(_WIDTH, _HEIGHT, np.random.default_rng(_SEED))
    field.set_active_count(count)
    step_ns: list[int] = []
    lines_ns: list[int] = []
    for frame in range(_WARMUP_FRAMES + _FRAMES):
        gust = math.sin(frame * 0.05)
        started = time.perf_counter_ns()
        field.step(_DT, params, gust)
        step_done = time.perf_counter_ns()
        field.layer_lines(_LAYERS)
        lines_done = time.perf_counter_ns()
        if frame >= _WARMUP_FRAMES:
            step_ns.append(step_done - started)
            lines_ns.append(lines_done - step_done)
    return _stats(step_ns), _stats(lines_ns)[0]


def _bench_paint(count: int) -> tuple[float, float, float] | None:
    """يقيس paint_rain على QImage بدقة 1080p مع antialiasing؛ None إذا تعذّر PySide6."""
    try:
        from PySide6.QtGui import QImage, QPainter

        from raindesk.ui.painters.rain_painter import paint_rain
    except ImportError:
        return None
    params = params_from_settings(default_settings())
    field = RainField(_WIDTH, _HEIGHT, np.random.default_rng(_SEED))
    field.set_active_count(count)
    image = QImage(_WIDTH, _HEIGHT, QImage.Format.Format_ARGB32_Premultiplied)
    samples: list[int] = []
    for frame in range(_WARMUP_FRAMES + _FRAMES):
        field.step(_DT, params, math.sin(frame * 0.05))
        image.fill(0)  # مسح اللوحة خارج الزمن المقيس (المسح جزء من paintEvent لا من paint_rain)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        started = time.perf_counter_ns()
        paint_rain(painter, field, params)
        elapsed = time.perf_counter_ns() - started
        painter.end()
        if frame >= _WARMUP_FRAMES:
            samples.append(elapsed)
    return _stats(samples)


def _partition_argsort(lines: np.ndarray, idx: np.ndarray, layers: int) -> list[np.ndarray]:
    """النهج المعتمد: argsort مستقر (radix على uint8) ثم take ثم تقطيع بالحدود."""
    order = np.argsort(idx, kind="stable")
    ordered = np.take(lines, order, axis=0)
    bounds = np.concatenate(([0], np.cumsum(np.bincount(idx, minlength=layers))))
    return [ordered[bounds[k] : bounds[k + 1]] for k in range(layers)]


def _partition_masks(lines: np.ndarray, idx: np.ndarray, layers: int) -> list[np.ndarray]:
    """النهج البديل: قناع منطقي ونسخة لكل طبقة (L مرورًا على البيانات)."""
    return [lines[idx == k] for k in range(layers)]


def _bench_partition(count: int) -> tuple[float, float]:
    """يعيد (وسيط argsort، وسيط الأقنعة) بالميكروثانية لتقسيم count خطًا إلى طبقات."""
    rng = np.random.default_rng(_SEED)
    lines = rng.random((count, 4), dtype=np.float32)
    idx = (rng.random(count) ** 1.6 * _LAYERS).astype(np.uint8)
    results: list[float] = []
    for function in (_partition_argsort, _partition_masks):
        samples: list[int] = []
        for _ in range(_PARTITION_REPEATS):
            started = time.perf_counter_ns()
            function(lines, idx, _LAYERS)
            samples.append(time.perf_counter_ns() - started)
        results.append(float(np.median(np.asarray(samples))) / 1e3)
    return results[0], results[1]


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def main() -> int:
    rows: list[dict[str, float | int | None]] = []
    for count in _COUNTS:
        (s_med, s_p95, s_p99), lines_med = _bench_engine(count)
        paint = _bench_paint(count)
        rows.append({
            "drops": count,
            "step_median_ms": s_med, "step_p95_ms": s_p95, "step_p99_ms": s_p99,
            "layer_lines_median_ms": lines_med,
            "paint_median_ms": paint[0] if paint else None,
            "paint_p95_ms": paint[1] if paint else None,
            "paint_p99_ms": paint[2] if paint else None,
        })

    header = list(rows[0].keys())
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for row in rows:
        cells = [str(row["drops"])] + [_fmt(row[k]) for k in header[1:]]  # type: ignore[arg-type]
        print("| " + " | ".join(cells) + " |")

    with _CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {_CSV_PATH.resolve()}")

    print("\nPartition strategies (median microseconds, lower is better):")
    print("| drops | argsort (used) | masks |\n|---|---|---|")
    for count in _COUNTS:
        argsort_us, masks_us = _bench_partition(count)
        print(f"| {count} | {argsort_us:.1f} | {masks_us:.1f} |")

    by_count = {int(r["drops"]): r for r in rows}  # type: ignore[call-overload]
    checks = [
        ("step @1000 <= 1.0 ms", by_count[1000]["step_median_ms"], _BUDGET_STEP_1000_MS),
        ("step @5000 <= 3.0 ms", by_count[5000]["step_median_ms"], _BUDGET_STEP_5000_MS),
        ("paint @1000 <= 6.0 ms", by_count[1000]["paint_median_ms"], _BUDGET_PAINT_1000_MS),
    ]
    print("\nBudget check (median):")
    failed = False
    for label, value, limit in checks:
        if value is None:
            print(f"  SKIP  {label} (PySide6 not available)")
            continue
        ok = float(value) <= limit  # type: ignore[arg-type]
        failed = failed or not ok
        verdict = "PASS" if ok else "FAIL"
        print(f"  {verdict}  {label}: {float(value):.3f} ms")  # type: ignore[arg-type]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())