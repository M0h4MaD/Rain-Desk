"""tests/test_win32_api.py: اختبارات غلاف Win32 (معظمها windows_only وتُتخطّى خارج Windows)."""

from __future__ import annotations

import pytest

from raindesk.platform_win import win32_api
from raindesk.platform_win.win32_api import UserNotificationState

windows_only = pytest.mark.windows_only


def test_notification_state_values_match_shellapi() -> None:
    assert UserNotificationState.NOT_PRESENT == 1
    assert UserNotificationState.RUNNING_D3D_FULL_SCREEN == 3
    assert UserNotificationState.PRESENTATION_MODE == 4
    assert UserNotificationState.QUIET_TIME == 6


@windows_only
def test_windows_build_returns_int() -> None:
    build = win32_api.windows_build()
    assert isinstance(build, int) and build > 0


@windows_only
def test_query_user_notification_state_returns_enum_member() -> None:
    assert isinstance(win32_api.query_user_notification_state(), UserNotificationState)


@windows_only
def test_set_exclude_from_capture_error_path_returns_false() -> None:
    assert win32_api.set_exclude_from_capture(0, True) is False


@windows_only
def test_is_battery_saver_on_returns_bool() -> None:
    assert isinstance(win32_api.is_battery_saver_on(), bool)


@windows_only
def test_invalid_handle_calls_return_false_without_raising() -> None:
    assert win32_api.set_topmost(0) is False
    assert win32_api.ensure_click_through(0) is False
    assert win32_api.set_dark_title_bar(0, True) is False


@windows_only
def test_client_animations_enabled_returns_bool() -> None:
    assert isinstance(win32_api.client_animations_enabled(), bool)