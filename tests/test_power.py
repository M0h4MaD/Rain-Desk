"""tests/test_power.py: طلب المؤقّتات الدقيقة على Windows (بـ ctypes مزيَّف) ولا شيء في غيرها."""

from __future__ import annotations

import ctypes
import types
from typing import Any

import pytest

from raindesk.platform_win import power


class _Fn:
    def __init__(self, log: list[Any], name: str, result: int = 1) -> None:
        self._log, self._name, self._result = log, name, result
        self.restype: object = None

    def __call__(self, *args: Any) -> int:
        self._log.append((self._name, args))
        return self._result


def _fake_windll(log: list[Any], period_result: int = 0) -> Any:
    kernel32 = types.SimpleNamespace(
        GetCurrentProcess=_Fn(log, "GetCurrentProcess", 1234),
        SetProcessInformation=_Fn(log, "SetProcessInformation", 1),
    )
    winmm = types.SimpleNamespace(
        timeBeginPeriod=_Fn(log, "timeBeginPeriod", period_result),
        timeEndPeriod=_Fn(log, "timeEndPeriod", 0),
    )
    return types.SimpleNamespace(kernel32=kernel32, winmm=winmm)


def test_struct_layout_matches_process_power_throttling_state() -> None:
    assert ctypes.sizeof(power._ProcessPowerThrottlingState) == 12  # ثلاثة ULONG
    assert [name for name, _ in power._ProcessPowerThrottlingState._fields_] == [
        "Version",
        "ControlMask",
        "StateMask",
    ]


def test_nothing_happens_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(power.sys, "platform", "linux")
    assert power.begin_responsive_timing() is None
    power.end_responsive_timing(None)  # لا استثناء


def test_begin_and_end_call_the_expected_apis(monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[Any] = []
    monkeypatch.setattr(power.sys, "platform", "win32")
    monkeypatch.setattr(power, "_windll", lambda: _fake_windll(log))
    boost = power.begin_responsive_timing()
    assert boost is not None and boost.timer_period_set and boost.throttling_disabled
    names = [entry[0] for entry in log]
    assert "timeBeginPeriod" in names and "SetProcessInformation" in names
    set_call = next(entry for entry in log if entry[0] == "SetProcessInformation")
    assert set_call[1][1] == 4  # ProcessPowerThrottling
    state = set_call[1][2]._obj  # byref(...)
    assert (state.ControlMask, state.StateMask) == (0x1 | 0x4, 0)  # تعطيل التخفيض
    log.clear()
    power.end_responsive_timing(boost)
    names = [entry[0] for entry in log]
    assert names.count("timeEndPeriod") == 1 and names.count("SetProcessInformation") == 1
    reset = next(entry for entry in log if entry[0] == "SetProcessInformation")
    assert reset[1][2]._obj.ControlMask == 0  # عودة إلى إدارة النظام


def test_failures_never_raise_and_are_not_undone(monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[Any] = []
    monkeypatch.setattr(power.sys, "platform", "win32")
    monkeypatch.setattr(power, "_windll", lambda: _fake_windll(log, period_result=97))  # فشل
    boost = power.begin_responsive_timing()
    assert boost is not None and not boost.timer_period_set
    log.clear()
    power.end_responsive_timing(boost)
    assert "timeEndPeriod" not in [entry[0] for entry in log]  # لا ننهي ما لم نبدأه
    monkeypatch.setattr(power, "_windll", lambda: None)
    assert power.begin_responsive_timing() == power.TimingBoost(False, False)
