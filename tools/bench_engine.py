"""tools/bench_engine.py

الغرض: قياس أداء المحرك والرسم والصوت بالبروتوكول المنصوص عليه في تقرير RainDesk (الفصل 7).
المسؤوليات: تشغيل تجارب مضبوطة (إحماء ثم إطارات مقيسة ثم تكرارات)، وتلخيص كل تجربة بالوسيط
    والمدى الربيعي IQR وp95 وp99، وطباعة جداول Markdown جاهزة للصق في التقرير، وكتابة ملفين:
    bench_results.csv (بصيغة طويلة) وbench_report.md (البيئة والجداول).
    التجارب: (1) RainField.step وlayer_lines لكل N والدقة، (2) paint_rain لكل N والدقة
    والتنعيم، (3) RainSynth.render لكتل 20 ms عند ثلاث شدّات وزمن أول تفعيل، (4) حمل الإطار
    المشتق لكل fps_cap، (5) مقارنة نهجي تقسيم الطبقات (argsort مقابل الأقنعة).
البروتوكول: 5 تكرارات (--reps) من 600 إطار (--frames) بعد إحماء 120 إطارًا (--warmup) وبذرة
    ثابتة (rng_seed = 12345)؛ نبلّغ وسيط أوساط التكرارات وIQR أوساطها ووسيط p95 وp99.
حدود القياس: هذه الأداة تقيس كلفة الشيفرة داخل عملية واحدة ولا تقيس CPU التطبيق الكامل ولا
    الذاكرة؛ استعمل لذلك typeperf وtools/endurance_monitor.py (انظر docs/quality_assurance.md).
    "حمل الإطار" مشتق = (كلفة المحاكاة + الرسم) * fps / 10 بالمئة من نواة واحدة، وليس قياسًا.
الاعتماديات: NumPy وraindesk (و PySide6 اختياريًا للرسم).
النمط التصميمي: Template Method بسيط (_repeat) لتكرار أي تجربة، ودوال نقية للإحصاء كي تُختبر.
الاستعمال: python tools/bench_engine.py            (البروتوكول الكامل؛ قد يستغرق دقائق)
    python tools/bench_engine.py --quick           (فحص سريع للتأكد من أن الأداة تعمل)
مثال: python tools/bench_engine.py --counts 1000,5000 --skip-audio --out results
"""

from __future__ import annotations

import argparse
import csv
import math
import platform
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Final

import numpy as np

# python tools/bench_engine.py يضيف مجلد tools فقط إلى المسار، فنضيف جذر المشروع يدويًا.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raindesk.config.schema import default_settings  # noqa: E402
from raindesk.core.constants import (  # noqa: E402
    AUDIO_BLOCK_MS,
    AUDIO_DROPLET_BANK_SIZE,
    AUDIO_LOOP_SECONDS,
    AUDIO_SAMPLE_RATE,
)
from raindesk.engine.params import params_from_settings  # noqa: E402
from raindesk.engine.rain_field import RainField  # noqa: E402

_COUNTS: Final[tuple[int, ...]] = (500, 1000, 2000, 5000)
_FPS_CAPS: Final[tuple[int, ...]] = (20, 30, 60)
_INTENSITIES: Final[tuple[float, ...]] = (0.2, 0.6, 1.0)
_DEFAULT_REPS: Final[int] = 5  # أقل عدد تكرارات يطلبه البروتوكول
_DEFAULT_FRAMES: Final[int] = 600  # إطارات مقيسة في كل تكرار
_DEFAULT_WARMUP: Final[int] = 120  # إطارات إحماء لا تُحسب
_QUICK_REPS: Final[int] = 2
_QUICK_FRAMES: Final[int] = 60
_QUICK_WARMUP: Final[int] = 10
_SEED: Final[int] = 12345
_DT: Final[float] = 1.0 / 60.0  # s: خطوة المحاكاة (كلفة step لا تتوقف على fps_cap)
_LAYERS: Final[int] = 5
_GUST_PHASE_RATE: Final[float] = 0.05  # rad/إطار: عصفة جيبية بسيطة لتحريك الحقل
_NS_PER_MS: Final[float] = 1e6
_MS_PER_S: Final[float] = 1000.0
_PERCENT_FACTOR: Final[float] = 10.0  # ms * fps / 10 = بالمئة من نواة واحدة
_PARTITION_REPEATS: Final[int] = 300
_AUDIO_PAN_WIND: Final[float] = 0.5  # wind_amount ثابت أثناء قياس الصوت
_CSV_NAME: Final[str] = "bench_results.csv"
_REPORT_NAME: Final[str] = "bench_report.md"
# حدود ميزانية الأداء (ms) من المواصفة، على الوسيط.
_BUDGET_STEP_1000_MS: Final[float] = 1.0
_BUDGET_STEP_5000_MS: Final[float] = 3.0
_BUDGET_PAINT_1000_MS: Final[float] = 6.0
_BUDGET_AUDIO_BLOCK_MS: Final[float] = 0.5
_BUDGET_AUDIO_STARTUP_MS: Final[float] = 400.0
_CSV_FIELDS: Final[tuple[str, ...]] = (
    "experiment", "drops", "resolution", "antialiasing", "intensity", "metric",
    "median_ms", "iqr_ms", "p95_ms", "p99_ms", "reps",
)


@dataclass(frozen=True, slots=True)
class Resolution:
    """دقة منطقية (device-independent) للتجربة."""

    name: str
    width: int
    height: int


RESOLUTIONS: Final[tuple[Resolution, ...]] = (
    Resolution("1080p", 1920, 1080),
    Resolution("4K", 3840, 2160),
)


@dataclass(frozen=True, slots=True)
class RunStats:
    """إحصاءات تكرار واحد بالميلي ثانية: الوسيط وp95 وp99 على إطاراته المقيسة."""

    median: float
    p95: float
    p99: float


@dataclass(frozen=True, slots=True)
class Aggregate:
    """تلخيص كل التكرارات: وسيط الأوساط وIQR الأوساط ووسيط p95 ووسيط p99."""

    median: float
    iqr: float
    p95: float
    p99: float
    reps: int


@dataclass(frozen=True, slots=True)
class Measurement:
    """صف نتيجة واحد (صيغة طويلة): التجربة ومتغيراتها والمقياس وملخصه."""

    experiment: str
    drops: int | None
    resolution: str
    antialiasing: str
    intensity: float | None
    metric: str
    agg: Aggregate


# ---------------------------------------------------------------------------
# إحصاء نقي (يُختبر وحده)
# ---------------------------------------------------------------------------
def run_stats(samples_ns: Sequence[int | float]) -> RunStats:
    """(الوسيط، p95، p99) بالميلي ثانية من عيّنات بالنانوثانية."""
    values = np.asarray(samples_ns, dtype=np.float64) / _NS_PER_MS
    median, p95, p99 = np.percentile(values, [50, 95, 99])
    return RunStats(float(median), float(p95), float(p99))


def aggregate(runs: Sequence[RunStats]) -> Aggregate:
    """وسيط أوساط التكرارات وIQR = Q3 - Q1 لأوساطها ووسيطا p95 وp99.

    الوسيط والـ IQR أمتن أمام القيم الشاذة من المتوسط والانحراف المعياري (تشويش الخلفية).
    """
    if not runs:
        raise ValueError("at least one run is required")
    medians = np.asarray([r.median for r in runs], dtype=np.float64)
    q1, q3 = np.percentile(medians, [25, 75])
    return Aggregate(
        median=float(np.median(medians)),
        iqr=float(q3 - q1),
        p95=float(np.median([r.p95 for r in runs])),
        p99=float(np.median([r.p99 for r in runs])),
        reps=len(runs),
    )


def frame_load(cost_ms: float, fps_cap: int) -> tuple[float, float]:
    """(ميزانية الإطار ms، الحمل المشتق بالمئة من نواة واحدة) لكلفة محاكاة+رسم وسقف fps."""
    budget_ms = _MS_PER_S / fps_cap
    return budget_ms, cost_ms * fps_cap / _PERCENT_FACTOR


def markdown_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """جدول Markdown من عنوان وصفوف نصية."""
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _repeat(reps: int, one_run: Callable[[], RunStats | None]) -> list[RunStats] | None:
    """يكرّر تجربة reps مرة؛ يعيد None إن تعذّرت (مثل غياب PySide6)."""
    runs: list[RunStats] = []
    for _ in range(reps):
        result = one_run()
        if result is None:
            return None
        runs.append(result)
    return runs


# ---------------------------------------------------------------------------
# التجارب
# ---------------------------------------------------------------------------
def _run_step(
    count: int, res: Resolution, frames: int, warmup: int
) -> tuple[RunStats, RunStats]:
    """تكرار واحد: (إحصاءات RainField.step، إحصاءات layer_lines) على حقل جديد ببذرة ثابتة."""
    params = params_from_settings(default_settings())
    field = RainField(res.width, res.height, np.random.default_rng(_SEED))
    field.set_active_count(count)
    step_ns: list[int] = []
    lines_ns: list[int] = []
    for frame in range(warmup + frames):
        gust = math.sin(frame * _GUST_PHASE_RATE)
        started = time.perf_counter_ns()
        field.step(_DT, params, gust)
        step_done = time.perf_counter_ns()
        field.layer_lines(_LAYERS)
        lines_done = time.perf_counter_ns()
        if frame >= warmup:
            step_ns.append(step_done - started)
            lines_ns.append(lines_done - step_done)
    return run_stats(step_ns), run_stats(lines_ns)


def _run_paint(
    count: int, res: Resolution, antialiasing: bool, frames: int, warmup: int
) -> RunStats | None:
    """تكرار واحد لـ paint_rain على QImage بدقة res؛ None إن تعذّر PySide6."""
    try:
        from PySide6.QtGui import QImage, QPainter

        from raindesk.ui.painters.rain_painter import paint_rain
    except ImportError:
        return None
    params = params_from_settings(default_settings())
    field = RainField(res.width, res.height, np.random.default_rng(_SEED))
    field.set_active_count(count)
    image = QImage(res.width, res.height, QImage.Format.Format_ARGB32_Premultiplied)
    samples: list[int] = []
    for frame in range(warmup + frames):
        field.step(_DT, params, math.sin(frame * _GUST_PHASE_RATE))
        image.fill(0)  # المسح جزء من paintEvent لا من paint_rain: خارج الزمن المقيس
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, antialiasing)
        started = time.perf_counter_ns()
        paint_rain(painter, field, params)
        elapsed = time.perf_counter_ns() - started
        painter.end()
        if frame >= warmup:
            samples.append(elapsed)
    return run_stats(samples)


def _audio_modules() -> tuple[type, type] | None:
    """(RainSynth، AudioParams) أو None إن لم تتوفر وحدة الصوت في هذه النسخة."""
    try:
        from raindesk.engine.rain_audio import AudioParams, RainSynth
    except ImportError:
        return None
    return RainSynth, AudioParams


def _run_audio_block(intensity: float, frames: int, warmup: int) -> RunStats | None:
    """تكرار واحد: زمن RainSynth.render لكتلة AUDIO_BLOCK_MS على مُخلِّق جديد ببذرة ثابتة."""
    modules = _audio_modules()
    if modules is None:
        return None
    synth_cls, params_cls = modules
    synth = synth_cls(
        np.random.default_rng(_SEED), AUDIO_SAMPLE_RATE, AUDIO_LOOP_SECONDS,
        AUDIO_DROPLET_BANK_SIZE,
    )
    block = round(AUDIO_SAMPLE_RATE * AUDIO_BLOCK_MS / _MS_PER_S)
    samples: list[int] = []
    for index in range(warmup + frames):
        params = params_cls(
            intensity=intensity, wind_amount=_AUDIO_PAN_WIND,
            gust=math.sin(index * _GUST_PHASE_RATE), master=1.0, wind_enabled=True,
        )
        started = time.perf_counter_ns()
        synth.render(block, params)
        elapsed = time.perf_counter_ns() - started
        if index >= warmup:
            samples.append(elapsed)
    return run_stats(samples)


def _run_audio_startup() -> RunStats | None:
    """تكرار واحد: زمن بناء الحلقات وبنك القطرات (أول تفعيل للصوت) كقيمة وحيدة."""
    modules = _audio_modules()
    if modules is None:
        return None
    synth_cls, _ = modules
    started = time.perf_counter_ns()
    synth = synth_cls(
        np.random.default_rng(_SEED), AUDIO_SAMPLE_RATE, AUDIO_LOOP_SECONDS,
        AUDIO_DROPLET_BANK_SIZE,
    )
    prepare = getattr(synth, "prepare_thunder", None)
    if callable(prepare):
        prepare()  # الرعد جزء من تكلفة التفعيل الفعلية في التطبيق
    elapsed = time.perf_counter_ns() - started
    return run_stats([elapsed])


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
    """(وسيط argsort، وسيط الأقنعة) بالميكروثانية لتقسيم count خطًا إلى طبقات."""
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


# ---------------------------------------------------------------------------
# التشغيل والتقرير
# ---------------------------------------------------------------------------
def environment_lines() -> list[str]:
    """وصف البيئة (العتاد والنظام والإصدارات) كما يطلب البروتوكول."""
    lines = [
        f"- OS: {platform.platform()}",
        f"- Machine: {platform.machine()}, processor: {platform.processor() or 'n/a'}",
        f"- Logical CPUs: {_cpu_count()}",
        f"- Python: {platform.python_version()} ({platform.python_implementation()})",
        f"- NumPy: {np.__version__}",
    ]
    try:
        import PySide6

        lines.append(f"- PySide6: {PySide6.__version__}")
    except ImportError:
        lines.append("- PySide6: not installed (paint experiments skipped)")
    getwindowsversion = getattr(sys, "getwindowsversion", None)
    if callable(getwindowsversion):
        lines.append(f"- Windows build: {getwindowsversion().build}")
    return lines


def _cpu_count() -> int:
    import os

    return os.cpu_count() or 1


def _find(
    items: Sequence[Measurement], experiment: str, drops: int, resolution: str, antialiasing: str
) -> Measurement | None:
    for item in items:
        if (item.experiment, item.drops, item.resolution, item.antialiasing) == (
            experiment, drops, resolution, antialiasing,
        ):
            return item
    return None


def run_all(
    counts: Sequence[int], reps: int, frames: int, warmup: int, *,
    skip_paint: bool, skip_audio: bool,
) -> list[Measurement]:
    """يشغّل كل التجارب ويعيد نتائجها بصيغة طويلة (مع تقدّم على stderr)."""
    results: list[Measurement] = []

    def progress(text: str) -> None:
        print(f"  ... {text}", file=sys.stderr, flush=True)

    for res in RESOLUTIONS:
        for count in counts:
            progress(f"engine step: N={count}, {res.name}")
            pairs = [_run_step(count, res, frames, warmup) for _ in range(reps)]
            for metric, runs in (
                ("step_ms", [p[0] for p in pairs]), ("layer_lines_ms", [p[1] for p in pairs])
            ):
                results.append(
                    Measurement("engine", count, res.name, "-", None, metric, aggregate(runs))
                )
    if not skip_paint:
        for res in RESOLUTIONS:
            for aa in (True, False):
                for count in counts:
                    progress(f"paint: N={count}, {res.name}, AA={'on' if aa else 'off'}")
                    runs = _repeat(reps, partial(_run_paint, count, res, aa, frames, warmup))
                    if runs is None:
                        break
                    results.append(Measurement(
                        "paint", count, res.name, "on" if aa else "off", None, "paint_ms",
                        aggregate(runs),
                    ))
    if not skip_audio and _audio_modules() is not None:
        for intensity in _INTENSITIES:
            progress(f"audio block: intensity={intensity}")
            runs = _repeat(reps, partial(_run_audio_block, intensity, frames, warmup))
            if runs is not None:
                results.append(Measurement(
                    "audio", None, "-", "-", intensity, "audio_block_ms", aggregate(runs)
                ))
        progress("audio first-enable cost")
        startup = _repeat(reps, _run_audio_startup)
        if startup is not None:
            results.append(Measurement(
                "audio", None, "-", "-", None, "audio_startup_ms", aggregate(startup)
            ))
    return results


def build_tables(results: Sequence[Measurement], counts: Sequence[int]) -> str:
    """جداول Markdown بالأرقام الفعلية (تقابل الجداول 7-1 و7-2 و7-4 وجدول الحمل المشتق)."""
    parts: list[str] = []
    rows = []
    for res in RESOLUTIONS:
        for count in counts:
            m = _find(results, "engine", count, res.name, "-")
            if m is not None and m.metric == "step_ms":
                a = m.agg
                rows.append([res.name, str(count), _fmt(a.median), _fmt(a.iqr), _fmt(a.p95),
                             _fmt(a.p99)])
    parts.append("### RainField.step (ms)\n\n" + markdown_table(
        ["Resolution", "N", "Median", "IQR", "p95", "p99"], rows))

    paint_rows = []
    for item in results:
        if item.experiment == "paint":
            a = item.agg
            paint_rows.append([item.resolution, item.antialiasing, str(item.drops),
                               _fmt(a.median), _fmt(a.iqr), _fmt(a.p95), _fmt(a.p99)])
    if paint_rows:
        parts.append("### paint_rain (ms)\n\n" + markdown_table(
            ["Resolution", "AA", "N", "Median", "IQR", "p95", "p99"], paint_rows))
        load_rows = []
        for res in RESOLUTIONS:
            for count in counts:
                step = _find(results, "engine", count, res.name, "-")
                paint = _find(results, "paint", count, res.name, "on")
                if step is None or paint is None:
                    continue
                cost = step.agg.median + paint.agg.median
                for fps in _FPS_CAPS:
                    budget, load = frame_load(cost, fps)
                    load_rows.append([res.name, str(count), str(fps), _fmt(cost),
                                      f"{budget:.1f}", f"{load:.1f}"])
        parts.append("### Derived frame load (AA on; not a process measurement)\n\n"
                     + markdown_table(["Resolution", "N", "fps_cap", "step+paint ms",
                                       "budget ms", "% of one core"], load_rows))

    audio_rows = []
    for item in results:
        if item.experiment == "audio":
            a = item.agg
            label = ("first enable" if item.intensity is None else f"{item.intensity}")
            audio_rows.append([label, item.metric, _fmt(a.median), _fmt(a.iqr), _fmt(a.p95),
                               _fmt(a.p99)])
    if audio_rows:
        parts.append("### RainSynth (ms)\n\n" + markdown_table(
            ["Intensity", "Metric", "Median", "IQR", "p95", "p99"], audio_rows))
    return "\n\n".join(parts)


def budget_checks(results: Sequence[Measurement]) -> list[tuple[str, float, float]]:
    """(الوصف، القيمة، الحد) لكل بند ميزانية توفّر قياسه (1080p، تنعيم مفعّل، وسيط)."""
    checks: list[tuple[str, float, float]] = []
    for count, limit in ((1000, _BUDGET_STEP_1000_MS), (5000, _BUDGET_STEP_5000_MS)):
        m = _find(results, "engine", count, "1080p", "-")
        if m is not None:
            checks.append((f"step @{count} (1080p)", m.agg.median, limit))
    paint = _find(results, "paint", 1000, "1080p", "on")
    if paint is not None:
        checks.append(("paint @1000 (1080p, AA on)", paint.agg.median, _BUDGET_PAINT_1000_MS))
    for item in results:
        if item.metric == "audio_block_ms" and item.intensity == 1.0:
            checks.append(("audio block @intensity 1.0", item.agg.median, _BUDGET_AUDIO_BLOCK_MS))
        if item.metric == "audio_startup_ms":
            checks.append(("audio first enable", item.agg.median, _BUDGET_AUDIO_STARTUP_MS))
    return checks


def write_csv(path: Path, results: Sequence[Measurement]) -> None:
    """يكتب النتائج بصيغة طويلة: صف لكل (تجربة، متغيرات، مقياس)."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(_CSV_FIELDS)
        for m in results:
            a = m.agg
            writer.writerow([
                m.experiment, "" if m.drops is None else m.drops, m.resolution, m.antialiasing,
                "" if m.intensity is None else m.intensity, m.metric,
                f"{a.median:.6f}", f"{a.iqr:.6f}", f"{a.p95:.6f}", f"{a.p99:.6f}", a.reps,
            ])


def _parse_counts(text: str) -> tuple[int, ...]:
    """يحوّل '500,1000' إلى (500, 1000)؛ يرفض الأرقام غير الموجبة."""
    values = tuple(int(part) for part in text.split(",") if part.strip())
    if not values or any(v <= 0 for v in values):
        raise argparse.ArgumentTypeError("counts must be positive integers, e.g. 500,1000")
    return values


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RainDesk benchmark (report chapter 7).")
    parser.add_argument("--reps", type=int, default=None, help="repetitions (default 5)")
    parser.add_argument("--frames", type=int, default=None, help="measured frames (default 600)")
    parser.add_argument("--warmup", type=int, default=None, help="warm-up frames (default 120)")
    parser.add_argument("--counts", type=_parse_counts, default=_COUNTS)
    parser.add_argument("--quick", action="store_true", help="tiny run to smoke-test the tool")
    parser.add_argument("--skip-paint", action="store_true")
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("."), help="output directory")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """نقطة الدخول: يعيد 0 إن نجحت كل بنود الميزانية المقيسة (أو لم يُقَس أيّ منها) وإلا 1."""
    args = _parse_args(argv)
    reps = args.reps or (_QUICK_REPS if args.quick else _DEFAULT_REPS)
    frames = args.frames or (_QUICK_FRAMES if args.quick else _DEFAULT_FRAMES)
    warmup = args.warmup if args.warmup is not None else (
        _QUICK_WARMUP if args.quick else _DEFAULT_WARMUP
    )
    counts: tuple[int, ...] = args.counts
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Protocol: {reps} reps x {frames} frames after {warmup} warm-up, seed {_SEED}",
          file=sys.stderr)
    results = run_all(counts, reps, frames, warmup,
                      skip_paint=args.skip_paint, skip_audio=args.skip_audio)
    tables = build_tables(results, counts)

    partition_rows = []
    for count in counts:
        argsort_us, masks_us = _bench_partition(count)
        partition_rows.append([str(count), f"{argsort_us:.1f}", f"{masks_us:.1f}"])
    partition = "### Layer partition (median us, lower is better)\n\n" + markdown_table(
        ["N", "argsort (used)", "masks"], partition_rows)

    checks = budget_checks(results)
    check_lines = ["### Budget check (median)", ""]
    failed = False
    for label, value, limit in checks:
        ok = value <= limit
        failed = failed or not ok
        check_lines.append(f"- {'PASS' if ok else 'FAIL'}  {label}: {value:.3f} ms (limit {limit})")
    if not checks:
        check_lines.append("- nothing measured against the budget")

    report = "\n\n".join([
        "# RainDesk benchmark report",
        f"Protocol: {reps} repetitions x {frames} frames after {warmup} warm-up frames, "
        f"seed {_SEED}. Values are median of per-run medians; IQR is over per-run medians.",
        "## Environment\n\n" + "\n".join(environment_lines()),
        "## Results\n\n" + tables, partition, "\n".join(check_lines),
    ])
    print(report)
    write_csv(out_dir / _CSV_NAME, results)
    (out_dir / _REPORT_NAME).write_text(report + "\n", encoding="utf-8")
    print(f"\nWrote {(out_dir / _CSV_NAME).resolve()} and {(out_dir / _REPORT_NAME).resolve()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
