"""tests/test_mascot_ui.py: Drip في الواجهة: الرسم والمضيف والمدير وافتراض أول تشغيل."""

from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor, QImage, QPainter

from raindesk.config.store import SettingsStore
from raindesk.engine.mascot import Effect, Expression, Mascot, MascotState
from raindesk.ui.frame_clock import FrameClock
from raindesk.ui.mascot_host import MascotHost, wind_look
from raindesk.ui.overlay_manager import OverlayManager
from raindesk.ui.painters.mascot_painter import paint_mascot

_S = MascotState
_DT = 1.0 / 30.0


# --------------------------------------------------------------------- الرسم
@pytest.fixture
def canvas(qapp: object) -> QImage:
    """لوحة QImage شفافة 200x140."""
    image = QImage(200, 140, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    return image


def _paint(image: QImage, mascot: Mascot) -> None:
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    paint_mascot(painter, mascot, mascot.height_px)
    assert painter.transform().isIdentity()  # المرسِم يعيد حالة الرسام
    painter.end()


def _alpha(image: QImage, x: int, y: int) -> int:
    return int(image.pixelColor(x, y).alpha())


def _placed(state: MascotState = _S.IDLE) -> Mascot:
    mascot = Mascot(random.Random(1))
    mascot.configure(True, 1.0, 1.0)
    mascot.set_stage(0.0, 200.0, 120.0)
    mascot.state, mascot.x, mascot.y = state, 100.0, 120.0
    return mascot


def _snapshot(image: QImage, mascot: Mascot) -> bytes:
    _paint(image, mascot)
    return bytes(image.constBits())


def test_painter_draws_a_chubby_drop_standing_on_the_ground(canvas: QImage) -> None:
    _paint(canvas, _placed())
    assert _alpha(canvas, 100, 100) > 200  # قلب الجسم (مركزه عند y = 120 - 0.46 * 44)
    assert _alpha(canvas, 100, 84) > 0  # قرب الرأس
    assert _alpha(canvas, 100, 70) == 0  # فوق الرأس (الارتفاع 44 فالرأس عند 76)
    assert _alpha(canvas, 10, 10) == 0 and _alpha(canvas, 190, 130) == 0
    assert _alpha(canvas, 100, 121) > 0  # الظل تحت القدم
    assert _alpha(canvas, 100 - 19, 100) > 100 and _alpha(canvas, 100 + 19, 100) > 100  # ممتلئ


def test_painter_squash_and_stretch_change_the_silhouette(canvas: QImage) -> None:
    mascot = _placed()
    mascot.scale_y, mascot.scale_x = 0.7, 1.0 / 0.7
    _paint(canvas, mascot)
    assert _alpha(canvas, 100, 84) == 0  # مضغوط: الرأس انخفض (89)
    mascot.scale_y, mascot.scale_x = 1.2, 1.0 / 1.2
    _paint(canvas, mascot)
    assert _alpha(canvas, 100, 70) > 0  # ممتد: الرأس ارتفع (67)


def test_painter_eyes_blink_and_follow_the_look_direction(canvas: QImage) -> None:
    base = _snapshot(canvas, _placed())
    looking = _placed()
    looking.look_dir = 1.0
    assert _snapshot(canvas, looking) != base  # البؤبؤان يتحركان
    blinking = _placed()
    blinking.blink = 1.0
    assert _snapshot(canvas, blinking) != base  # العينان تُغلقان
    up = _placed()
    up.look_y = -1.0
    assert _snapshot(canvas, up) != base


def test_every_expression_and_effect_draws_something_different(canvas: QImage) -> None:
    base = _snapshot(canvas, _placed())
    seen = {base}
    for expression in Expression:
        mascot = _placed()
        mascot.expression = expression
        seen.add(_snapshot(canvas, mascot))
    assert len(seen) >= 6  # التعابير الستة متمايزة (مع العادي)
    for effect in Effect:
        if effect is Effect.NONE:
            continue
        mascot = _placed()
        mascot.effect, mascot.effect_t = effect, 0.4
        assert _snapshot(canvas, mascot) != base, effect


def test_arms_and_feet_move_the_picture(canvas: QImage) -> None:
    base = _snapshot(canvas, _placed())
    waving = _placed()
    waving.arm_r = 140.0
    assert _snapshot(canvas, waving) != base
    walking = _placed()
    walking.gait, walking.foot_phase = 1.0, 1.2
    assert _snapshot(canvas, walking) != base


def test_painter_skips_hidden_and_draws_every_state(canvas: QImage) -> None:
    _paint(canvas, _placed(_S.HIDDEN))
    assert all(_alpha(canvas, x, y) == 0 for x in range(0, 200, 7) for y in range(0, 140, 7))
    for state in MascotState:
        if state is not _S.HIDDEN:
            _paint(canvas, _placed(state))
            assert _alpha(canvas, 100, 100) > 200


# --------------------------------------------------------------------- المضيف والمدير
@pytest.fixture
def make_store(qapp: object, tmp_path: Path) -> Iterator[Callable[[str], SettingsStore]]:
    """مصنع مخازن مؤقتة؛ تُحفظ عند النهاية فلا يتسرب مؤقّت حفظ مؤجَّل إلى اختبارات تالية."""
    made: list[SettingsStore] = []

    def factory(name: str) -> SettingsStore:
        store = SettingsStore(path=tmp_path / f"{name}.json")
        made.append(store)
        return store

    yield factory
    for store in made:
        store.save_now()  # يوقف مؤقّت الـ debounce


@pytest.fixture
def manager(make_store: Callable[[str], SettingsStore]) -> Iterator[OverlayManager]:
    """OverlayManager حقيقي على شاشة Qt الوهمية بشخصية مفعّلة."""
    store = make_store("manager")
    store.set("mascot_enabled", True)
    overlay_manager = OverlayManager(store, FrameClock())
    overlay_manager.rebuild()
    yield overlay_manager
    overlay_manager.shutdown()


def test_wind_look_has_a_deadzone_and_saturates() -> None:
    assert wind_look(0.0) == 0.0 and wind_look(1.9) == 0.0 and wind_look(-1.9) == 0.0
    assert wind_look(15.0) == pytest.approx(0.5)
    assert wind_look(-15.0) == pytest.approx(-0.5)
    assert wind_look(75.0) == 1.0 and wind_look(-75.0) == -1.0


def test_manager_hosts_the_mascot_on_exactly_one_window(manager: OverlayManager) -> None:
    holders = [w for w in manager._windows if w._mascot is not None]
    assert len(holders) == 1 and holders[0] is manager._mascot.window
    assert holders[0]._mascot is manager._mascot.mascot
    assert manager._mascot.mascot.ground_y == pytest.approx(holders[0]._stage_ground_y())


def test_host_feeds_the_pointer_in_window_coordinates_or_none(
    manager: OverlayManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    host, window = manager._mascot, manager._mascot.window
    assert window is not None
    seen: list[tuple[float, float] | None] = []
    monkeypatch.setattr(host.mascot, "set_pointer", seen.append)
    for local in (QPoint(120, 80), QPoint(-500, -500)):
        global_point = window.mapToGlobal(local)
        monkeypatch.setattr(QCursor, "pos", staticmethod(lambda point=global_point: point))
        host.step(_DT, 0.0)
    assert seen == [(120.0, 80.0), None]


def test_host_forwards_rain_and_triggers_one_startle_per_lightning_flash(
    manager: OverlayManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = manager._mascot
    startles: list[int] = []
    monkeypatch.setattr(host.mascot, "startle", lambda: startles.append(1))
    host.step(_DT, 0.0, rain=0.8, flash=0.0)
    assert host.mascot._rain == pytest.approx(0.8)
    for flash in (0.0, 0.1, 0.12, 0.09, 0.0, 0.0, 0.1):  # وميضان منفصلان
        host.step(_DT, 0.0, rain=0.0, flash=flash)
    assert len(startles) == 2  # حافة الصعود فقط، لا كل إطار مرتفع


def test_disabled_mascot_costs_nothing_and_leaves_the_window(
    manager: OverlayManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = manager._store
    steps: list[float] = []
    monkeypatch.setattr(manager._mascot.mascot, "step", lambda dt, _wind: steps.append(dt))
    manager._on_tick(_DT)
    assert steps == [_DT]  # مفعّلة: تُقدَّم مرة لكل tick
    store.set("mascot_enabled", False)
    assert manager._mascot.window is None and all(w._mascot is None for w in manager._windows)
    manager._on_tick(_DT)
    assert steps == [_DT]  # معطّلة: لا خطوة إطلاقًا
    store.set("mascot_enabled", True)
    assert sum(w._mascot is not None for w in manager._windows) == 1


def test_manager_soak_paints_an_interacting_mascot_without_errors(manager: OverlayManager) -> None:
    manager._store.set("mascot_frequency", 1.0)
    window = manager._mascot.window
    assert window is not None
    seen: set[MascotState] = set()
    grabs = 0
    for tick in range(9000):  # نحو 5 دقائق محاكاة بـ 30 fps
        manager._on_tick(_DT)
        seen.add(manager._mascot.mascot.state)
        if manager._mascot.mascot.visible and tick % 150 == 0:
            window.grab()  # يمرّ على paintEvent بما فيه رسم الشخصية
            grabs += 1
    assert grabs > 5 and {_S.ENTERING, _S.WALKING, _S.EXITING} <= seen


def test_first_run_disables_the_mascot_when_windows_animations_are_off(
    make_store: Callable[[str], SettingsStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    from raindesk.app import bootstrap

    def fresh(name: str, first_run_done: bool) -> SettingsStore:
        store = make_store(name)
        store.set("first_run_completed", first_run_done)
        store.set("mascot_enabled", True)
        return store

    monkeypatch.setattr(bootstrap.win32_api, "client_animations_enabled", lambda: False)
    first = fresh("first", False)
    bootstrap._apply_first_run_defaults(first)
    assert first.get("mascot_enabled") is False
    later = fresh("later", True)  # بعد أول تشغيل لا نغيّر اختيار المستخدم
    bootstrap._apply_first_run_defaults(later)
    assert later.get("mascot_enabled") is True
    monkeypatch.setattr(bootstrap.win32_api, "client_animations_enabled", lambda: True)
    normal = fresh("normal", False)
    bootstrap._apply_first_run_defaults(normal)
    assert normal.get("mascot_enabled") is True


def test_mascot_host_is_inert_without_a_window(make_store: Callable[[str], SettingsStore]) -> None:
    store = make_store("inert")
    store.set("mascot_enabled", True)
    host = MascotHost(store, random.Random(1))
    host.sync([])  # لا نوافذ
    host.step(_DT, 20.0, 1.0, 0.5)  # لا استثناء ولا أثر
    assert host.window is None and not host.mascot.visible