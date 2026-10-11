"""tests/test_toggle_switch.py: المقبض يتبع الحالة في كل المسارات (نقر، لوحة مفاتيح، برمجيًا)."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from raindesk.ui.widgets.toggle_switch import ToggleSwitch


def _settle(app: QApplication, seconds: float = 0.4) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()


@pytest.fixture
def switch(qapp: QApplication) -> Iterator[ToggleSwitch]:
    widget = ToggleSwitch()
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()


def test_mouse_click_moves_the_knob(qapp: QApplication, switch: ToggleSwitch) -> None:
    """الخطأ الأصلي: النقر يغيّر isChecked دون أن يتحرك المقبض حتى تبديل الصفحة."""
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
    _settle(qapp)
    assert switch.isChecked() and switch.progress == 1.0
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
    _settle(qapp)
    assert not switch.isChecked() and switch.progress == 0.0


def test_space_key_moves_the_knob(qapp: QApplication, switch: ToggleSwitch) -> None:
    switch.setFocus()
    QTest.keyClick(switch, Qt.Key.Key_Space)
    _settle(qapp)
    assert switch.isChecked() and switch.progress == 1.0


def test_programmatic_change_moves_the_knob_even_with_signals_blocked(
    qapp: QApplication, switch: ToggleSwitch
) -> None:
    switch.blockSignals(True)  # كما يفعل الربط الثنائي الاتجاه عند تحديث الصفحة من المخزن
    switch.setChecked(True)
    switch.blockSignals(False)
    _settle(qapp)
    assert switch.progress == 1.0
    switch.blockSignals(True)
    switch.setChecked(False)
    switch.blockSignals(False)
    _settle(qapp)
    assert switch.progress == 0.0


def test_hidden_switch_jumps_immediately(qapp: QApplication) -> None:
    widget = ToggleSwitch()
    widget.setChecked(True)
    assert widget.progress == 1.0  # بلا حركة ولا انتظار حين تكون النافذة مخفية


def test_rapid_double_click_ends_in_the_matching_position(
    qapp: QApplication, switch: ToggleSwitch
) -> None:
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
    _settle(qapp)
    assert not switch.isChecked() and switch.progress == 0.0
