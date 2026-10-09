"""tools/endurance_monitor.py

الغرض: اختبار التحمّل: يراقب ذاكرة عملية RainDesk ومعالجها مدة طويلة (60 دقيقة افتراضيًا) ويحسب
    نسبة نمو الذاكرة بعد فترة الإحماء، ويكتب CSV وملخصًا بجدول Markdown (معيار القبول: أقل من 5%).
المسؤوليات: أخذ عيّنات (working set وprivate bytes ونسبة المعالج) من نظام التشغيل، وتلخيصها
    رياضيًا، وتشغيل التطبيق بنفسه إن لم يُعطَ pid. لا يعدّل التطبيق ولا يحتاج مكتبات إضافية.
الاعتماديات: المكتبة القياسية فقط (ctypes على Windows وملفات /proc على Linux لأغراض الاختبار).
النمط التصميمي: Adapter (واجهة عيّنات موحدة فوق Win32 و/proc) مع دالة تلخيص نقية قابلة للاختبار.
ملاحظات: الإحماء 5 دقائق تُهمَل (تعبئة مخازن الطباعة والذاكرات المؤقتة)، خط الأساس = وسيط
    الدقائق 5-10، والنهاية = وسيط آخر 5 دقائق، النمو = (النهاية - الأساس) / الأساس. استخدام
    الوسيط (لا المتوسط) يقاوم الارتفاعات اللحظية. نسبة المعالج = وقت المعالج المستهلك / الزمن /
    عدد الأنوية، أي نفس "الإجمالي" في مدير المهام. اختُبر على Linux فقط؛ مسار Win32 يحتاج تحققًا
    على جهازك (انظر الأمر 'python tools/endurance_monitor.py --selfcheck').
الاستعمال: python tools/endurance_monitor.py                 (يشغّل main.py ويراقبه 60 دقيقة)
           python tools/endurance_monitor.py --pid 1234 --minutes 15
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

_MB: Final[float] = 1024.0 * 1024.0
WARMUP_S: Final[float] = 300.0  # s: إحماء يُهمَل
BASELINE_WINDOW_S: Final[float] = 300.0  # s: نافذة الأساس بعد الإحماء
FINAL_WINDOW_S: Final[float] = 300.0  # s: نافذة النهاية (آخر 5 دقائق)
MAX_GROWTH_PCT: Final[float] = 5.0  # %: معيار القبول
_DEFAULT_MINUTES: Final[float] = 60.0
_DEFAULT_INTERVAL_S: Final[float] = 10.0
_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_EXIT_OK: Final[int] = 0
_EXIT_GROWTH: Final[int] = 1
_EXIT_ERROR: Final[int] = 2
_CSV_HEADER: Final[tuple[str, ...]] = ("t_s", "working_set_mb", "private_mb", "cpu_percent")
_FILETIME_TICKS_PER_S: Final[float] = 1.0e7  # FILETIME بوحدات 100 ns
_PROCESS_QUERY_LIMITED_INFORMATION: Final[int] = 0x1000
_PROCESS_VM_READ: Final[int] = 0x0010


@dataclass(frozen=True, slots=True)
class Sample:
    """عيّنة واحدة: الزمن منذ البدء (ثانية) وذاكرة بالميغابايت ونسبة معالج (من إجمالي الأنوية)."""

    t_s: float
    working_set_mb: float
    private_mb: float
    cpu_percent: float


@dataclass(frozen=True, slots=True)
class Verdict:
    """نتيجة التلخيص: وسيط الأساس والنهاية بالميغابايت ونسبة النمو والقبول وعدد العيّنات."""

    baseline_mb: float
    final_mb: float
    growth_pct: float
    passed: bool
    samples: int


def summarize(
    samples: Sequence[Sample],
    *,
    warmup_s: float = WARMUP_S,
    baseline_s: float = BASELINE_WINDOW_S,
    final_s: float = FINAL_WINDOW_S,
    max_growth_pct: float = MAX_GROWTH_PCT,
) -> Verdict:
    """يحسب نمو working set بعد الإحماء: (وسيط النهاية - وسيط الأساس) / وسيط الأساس.

    Raises:
        ValueError: إن لم تغطِّ العيّنات نافذتي الأساس والنهاية متتاليتين بعد الإحماء.
    """
    if not samples:
        raise ValueError("no samples")
    end = samples[-1].t_s
    baseline = [s.working_set_mb for s in samples if warmup_s <= s.t_s < warmup_s + baseline_s]
    final = [s.working_set_mb for s in samples if s.t_s > end - final_s]
    if end < warmup_s + baseline_s + final_s or not baseline or not final:
        needed = (warmup_s + baseline_s + final_s) / 60.0
        raise ValueError(f"run too short: need at least {needed:.0f} minutes of samples")
    base, last = statistics.median(baseline), statistics.median(final)
    growth = (last - base) / base * 100.0
    return Verdict(base, last, growth, growth < max_growth_pct, len(samples))


def to_markdown(verdict: Verdict) -> str:
    """جدول Markdown جاهز للصق في docs/quality_assurance.md."""
    status = "PASS" if verdict.passed else "FAIL"
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---|",
            f"| Samples | {verdict.samples} |",
            f"| Baseline working set (median, minutes 5-10) | {verdict.baseline_mb:.1f} MB |",
            f"| Final working set (median, last 5 minutes) | {verdict.final_mb:.1f} MB |",
            f"| Growth | {verdict.growth_pct:+.2f} % (limit {MAX_GROWTH_PCT:.0f} %) |",
            f"| Result | {status} |",
        ]
    )


def write_csv(path: Path, samples: Sequence[Sample]) -> None:
    """يكتب العيّنات إلى CSV (الترميز ASCII؛ الفاصل فاصلة)."""
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(_CSV_HEADER)
        for s in samples:
            writer.writerow(
                [
                    f"{s.t_s:.1f}",
                    f"{s.working_set_mb:.2f}",
                    f"{s.private_mb:.2f}",
                    f"{s.cpu_percent:.2f}",
                ]
            )


# ---------------------------------------------------------------------------
# أخذ العيّنات من نظام التشغيل
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _Raw:
    working_set_bytes: int
    private_bytes: int
    cpu_seconds: float


def _read_linux(pid: int) -> _Raw:
    """من /proc: VmRSS وRssAnon (بالكيلوبايت) ووقت المعالج من utime + stime (نبضات)."""
    status: dict[str, int] = {}
    for line in (
        Path(f"/proc/{pid}/status").read_text(encoding="ascii", errors="replace").splitlines()
    ):
        key, _, rest = line.partition(":")
        if key in ("VmRSS", "RssAnon") and rest.split():
            status[key] = int(rest.split()[0]) * 1024
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
    fields = stat[stat.rindex(")") + 2 :].split()  # بعد اسم الأمر (قد يحوي مسافات)
    ticks = int(fields[11]) + int(fields[12])  # utime وstime (الحقلان 14 و15 في الملف الأصلي)
    return _Raw(
        status.get("VmRSS", 0),
        status.get("RssAnon", status.get("VmRSS", 0)),
        ticks / os.sysconf("SC_CLK_TCK"),
    )


def _read_windows(pid: int) -> _Raw:
    """K32GetProcessMemoryInfo وGetProcessTimes عبر ctypes مع تصريح argtypes وrestype."""
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    kernel32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION | _PROCESS_VM_READ, False, pid)
    if not handle:
        raise OSError(f"OpenProcess failed (error {ctypes.get_last_error()})")  # type: ignore[attr-defined]
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        if not kernel32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise OSError(f"GetProcessMemoryInfo failed (error {ctypes.get_last_error()})")  # type: ignore[attr-defined]
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            raise OSError(f"GetProcessTimes failed (error {ctypes.get_last_error()})")  # type: ignore[attr-defined]
        kernel, user = (((t.dwHighDateTime << 32) | t.dwLowDateTime) for t in times[2:])
        return _Raw(
            counters.WorkingSetSize, counters.PrivateUsage, (kernel + user) / _FILETIME_TICKS_PER_S
        )
    finally:
        kernel32.CloseHandle(handle)


def _read_raw(pid: int) -> _Raw:
    if sys.platform == "win32":
        return _read_windows(pid)
    return _read_linux(pid)


class Sampler:
    """يأخذ عيّنات متتالية لعملية؛ نسبة المعالج من فرق وقت المعالج بين عيّنتين."""

    def __init__(self, pid: int) -> None:
        self._pid = pid
        self._cores = os.cpu_count() or 1
        self._start = time.monotonic()
        self._last_time = self._start
        self._last_cpu = _read_raw(pid).cpu_seconds

    def sample(self) -> Sample:
        """عيّنة الآن؛ ترفع OSError إن انتهت العملية."""
        raw = _read_raw(self._pid)
        now = time.monotonic()
        elapsed = max(now - self._last_time, 1e-9)
        cpu = (raw.cpu_seconds - self._last_cpu) / elapsed / self._cores * 100.0
        self._last_time, self._last_cpu = now, raw.cpu_seconds
        return Sample(now - self._start, raw.working_set_bytes / _MB, raw.private_bytes / _MB, cpu)


def _monitor(pid: int, minutes: float, interval_s: float) -> list[Sample]:
    sampler = Sampler(pid)
    samples: list[Sample] = []
    deadline = time.monotonic() + minutes * 60.0
    try:
        while time.monotonic() < deadline:
            time.sleep(interval_s)
            samples.append(sampler.sample())
            print(
                f"\r{samples[-1].t_s / 60:6.1f} min  WS {samples[-1].working_set_mb:7.1f} MB",
                end="",
            )
    except KeyboardInterrupt:
        print("\ninterrupted: summarizing what was collected")
    except OSError as exc:
        print(f"\nprocess ended or cannot be read: {exc}")
    print()
    return samples


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RainDesk endurance monitor (memory growth).")
    parser.add_argument("--pid", type=int, help="existing process id (default: launch main.py)")
    parser.add_argument("--minutes", type=float, default=_DEFAULT_MINUTES)
    parser.add_argument("--interval", type=float, default=_DEFAULT_INTERVAL_S, help="seconds")
    parser.add_argument("--output", type=Path, help="CSV path (default: endurance_<stamp>.csv)")
    parser.add_argument("--selfcheck", action="store_true", help="sample this process once")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    if args.selfcheck:
        sampler = Sampler(os.getpid())
        time.sleep(0.2)
        print(sampler.sample())
        return _EXIT_OK
    child: subprocess.Popen[bytes] | None = None
    pid: int = args.pid or 0
    if not pid:
        child = subprocess.Popen(
            [sys.executable, str(_PROJECT_ROOT / "main.py")], cwd=_PROJECT_ROOT
        )
        pid = child.pid
        print(f"launched main.py (pid {pid}); leave the machine idle and the overlay visible")
    try:
        samples = _monitor(pid, args.minutes, args.interval)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
    output: Path = args.output or Path(f"endurance_{datetime.now():%Y%m%d-%H%M%S}.csv")
    write_csv(output, samples)
    print(f"samples written to {output}")
    try:
        verdict = summarize(samples)
    except ValueError as exc:
        print(f"no verdict: {exc}")
        return _EXIT_ERROR
    print(to_markdown(verdict))
    return _EXIT_OK if verdict.passed else _EXIT_GROWTH


if __name__ == "__main__":
    raise SystemExit(main())
