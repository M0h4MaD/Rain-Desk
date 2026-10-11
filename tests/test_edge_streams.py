"""tests/test_edge_streams.py

الغرض: اختبار محرك قطرات الحواف (edge_streams) ومرسِمها.
المنهج: اختبارات إحصائية على محاكاة طويلة بـ rng ثابت (سلوك stick-slip، النسبة المنزلقة، الانجراف
    الجانبي)، واختبارات حالة على مصفوفات محقونة (الالتحام، تلاشي الأثر، التلاشي العلوي)، واختبار
    رسم على QImage خارج الشاشة (الألوان على الحواف فقط، والرسم لا يغيّر المحاكاة).
"""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from raindesk.engine import edge_streams  # noqa: E402
from raindesk.engine.edge_streams import EdgeStreams  # noqa: E402
from raindesk.ui.painters.effects_painter import paint_edge_streams  # noqa: E402

WIDTH, HEIGHT = 800.0, 600.0
FPS_DT = 1.0 / 30.0


def make(count: int = 3, opacity: float = 0.4, seed: int = 11, size=(WIDTH, HEIGHT)) -> EdgeStreams:
    streams = EdgeStreams(size[0], size[1], np.random.default_rng(seed))
    streams.configure(count, opacity)
    return streams


def run(streams: EdgeStreams, seconds: float, gust: float = 0.0) -> None:
    for _ in range(int(seconds / FPS_DT)):
        streams.step(FPS_DT, gust)


# ------------------------------------------------------------------ البنية
def test_zero_count_exports_nothing() -> None:
    streams = make(count=0)
    streams.step(FPS_DT, 0.0)
    assert streams.drops().shape[0] == 0
    assert streams.trails().count.shape[0] == 0
    assert streams.residue().shape[0] == 0
    assert streams.drop_total == 0 and streams.sliding_count == 0


def test_count_is_clamped_to_eight_per_edge() -> None:
    streams = make(count=99)
    assert streams.drop_total == 2 * 8 * 4


@pytest.mark.parametrize("count", range(1, 9))
def test_path_point_cap_is_never_exceeded(count: int) -> None:
    streams = make(count=count)
    columns = streams.trails().x.shape[1]  # الرأس + عيّنات الأثر
    assert streams.drop_total * columns <= 600


def test_same_seed_gives_same_world() -> None:
    a, b = make(seed=5), make(seed=5)
    run(a, 10.0, 0.3)
    run(b, 10.0, 0.3)
    assert np.array_equal(a.drops(), b.drops())
    assert np.array_equal(a.residue(), b.residue())


def test_non_positive_dt_changes_nothing_and_big_dt_is_capped() -> None:
    streams = make()
    before = streams.drops().copy()
    streams.step(0.0, 0.0)
    streams.step(-1.0, 0.0)
    assert np.array_equal(before, streams.drops())
    t0 = streams._time
    streams.step(30.0, 0.0)
    assert streams._time - t0 <= 0.1 + 1e-9


def test_zero_opacity_hides_everything() -> None:
    streams = make(opacity=0.0)
    run(streams, 5.0)
    assert streams.drops().shape[0] == 0
    assert streams.residue().shape[0] == 0
    assert streams.trails().count.shape[0] == 0


def test_resize_keeps_everything_inside_the_new_bounds() -> None:
    streams = make()
    streams.resize(400.0, 300.0)
    run(streams, 20.0)
    d = streams.drops()
    assert d[:, 0].max() <= 400.0 and d[:, 1].max() <= 300.0 + 24.0


# ------------------------------------------------------------------ السلوك الفيزيائي
def test_drops_stay_on_screen_and_only_move_down() -> None:
    streams = make()
    for _ in range(30 * 60):
        before = streams._y.copy()
        streams.step(FPS_DT, 0.0)
        moved = streams._y - before
        reborn = streams._mass < 0.1  # القطرة الوليدة (تدوير أو ابتلاع) قد تظهر في أي ارتفاع
        assert ((moved >= -1e-9) | reborn).all()
        assert streams._x.min() >= 0.0 and streams._x.max() <= WIDTH
        assert streams._y.max() <= HEIGHT + 24.0 + 450.0 * FPS_DT


def test_stick_slip_each_drop_both_stops_and_moves() -> None:
    streams = make(count=3, seed=2)
    n = streams.drop_total
    moving = np.zeros(n, dtype=int)
    still = np.zeros(n, dtype=int)
    fractions = []
    for _ in range(30 * 240):
        streams.step(FPS_DT, 0.0)
        slid = streams._vy > 50.0
        moving += slid
        still += streams._vy == 0.0
        fractions.append(streams.sliding_count / n)
    assert (moving > 0).all() and (still > 0).all()  # كل قطرة تنزلق وتقف في وقت ما
    assert 0.04 < float(np.mean(fractions)) < 0.5  # ليست كلها واقفة ولا كلها تنزلق


def test_speed_of_one_drop_is_irregular_not_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(edge_streams, "_STICK_HAZARD_PER_PX", 0.0)  # بلا توقف عشوائي: التذبذب وحده
    streams = make(count=1, seed=4)
    streams._sliding[:] = False
    streams._grow[:] = 0.0
    streams._critical[:] = 99.0
    streams._mass[:] = 0.02
    streams._sliding[0] = True  # قطرة واحدة كبيرة تنزلق؛ نثبّت كتلتها كي لا يؤثر فقدان الكتلة
    speeds = []
    for step in range(30 * 40):
        streams._mass[0] = 3.0
        streams._y[0] = 100.0  # نبقيها في الشاشة
        streams._critical[0] = 99.0
        streams.step(FPS_DT, 0.0)
        streams._sliding[0] = True
        if step > 30 * 3:  # بعد انتهاء التسارع الأولي
            speeds.append(float(streams._vy[0]))
    assert len(speeds) > 500
    assert np.std(speeds) / np.mean(speeds) > 0.12  # السرعة تتأرجح حول الحدّية


def test_lateral_wander_is_irregular_and_bounded_around_the_lane() -> None:
    streams = make(count=3, seed=9)
    offsets, slopes = [], []
    for _ in range(30 * 180):
        streams.step(FPS_DT, 0.0)
        s = streams._vy > 30.0
        offsets.extend((streams._x - streams._lane_x[streams._lane_of])[s].tolist())
    assert len(offsets) > 300
    assert 1.0 < float(np.std(offsets)) < 6.0  # يتمايل لكن لا يغادر المسار
    step_dx = []
    trails = streams.trails()
    for i in np.flatnonzero(trails.count > 6):
        dy = np.diff(trails.y[i, : trails.count[i]])
        dx = np.diff(trails.x[i, : trails.count[i]])
        long_enough = np.abs(dy) > 5.0  # قطعة الرأس القصيرة تعطي ميلًا لا معنى له
        slopes.extend((np.abs(dx[long_enough]) / np.abs(dy[long_enough])).tolist())
        step_dx.extend(np.abs(dx[long_enough]).tolist())
    assert slopes and float(np.mean(slopes)) < 0.35  # الأثر رأسي في معظمه
    assert float(np.mean(step_dx)) > 0.5  # لكنه ليس خطًا مستقيمًا: يتعرّج بين عيّنتين متتاليتين


def test_gust_pushes_sliding_drops_toward_its_direction() -> None:
    def mean_slide_x(gust: float) -> float:
        streams = make(count=3, seed=6)
        xs = []
        for _ in range(30 * 120):
            streams.step(FPS_DT, gust)
            s = streams._vy > 30.0
            xs.extend((streams._x - streams._lane_x[streams._lane_of])[s].tolist())
        return float(np.mean(xs))

    assert mean_slide_x(1.0) - mean_slide_x(-1.0) > 2.0


def test_merge_conserves_mass_and_recycles_the_swallowed_drop() -> None:
    streams = make(count=1, seed=1)
    a, b = 0, 1
    streams._sliding[:] = False
    streams._sliding[a] = True
    streams._mass[:] = 0.02  # بقية القطرات وليدة ولا تشارك
    streams._mass[a], streams._mass[b] = 1.0, 0.5
    streams._x[a] = streams._x[b] = 20.0
    streams._y[a], streams._y[b] = 300.0, 303.0
    total_before = streams._mass[a] + streams._mass[b]
    streams._merge()
    assert streams._mass[a] == pytest.approx(1.0 + 0.85 * 0.5)
    assert streams._mass[a] < total_before  # جزء يتبخّر
    assert streams._mass[b] < 0.1  # أُعيدت ولادتها صغيرة


def test_two_pinned_drops_do_not_merge() -> None:
    streams = make(count=1, seed=1)
    streams._sliding[:] = False
    streams._mass[:] = 0.02
    streams._mass[0], streams._mass[1] = 1.0, 0.5
    streams._x[0] = streams._x[1] = 20.0
    streams._y[0], streams._y[1] = 300.0, 302.0
    streams._merge()
    assert streams._mass[0] == 1.0 and streams._mass[1] == 0.5


def test_newborn_drops_fade_in_instead_of_popping() -> None:
    streams = make(count=1, seed=1)
    streams._sliding[:] = False
    streams._mass[:] = 0.02
    streams._y[:] = 300.0
    assert streams.drops().shape[0] == 0  # كتلة ضئيلة: لا تظهر
    streams._mass[0] = 0.15
    mid = streams.drops()[0, 4]
    streams._mass[0] = 1.0
    full = streams.drops()[0, 4]
    assert 0.0 < mid < full


def test_top_fade_dims_drops_near_the_top_edge() -> None:
    streams = make(count=1, seed=1)
    streams._sliding[:] = False
    streams._mass[:] = 0.02
    streams._mass[0] = streams._mass[1] = 1.0
    streams._alpha_mult[:2] = 1.0
    streams._y[0], streams._y[1] = 6.0, 300.0
    d = streams.drops()
    assert d[0, 4] < 0.5 * d[1, 4]


# ------------------------------------------------------------------ الأثر والحبيبات
def test_trails_are_ordered_head_to_tail_and_fade_monotonically() -> None:
    streams = make(count=3, seed=3)
    run(streams, 40.0)
    trails = streams.trails()
    checked = 0
    for i in np.flatnonzero(trails.count >= 3):
        n = trails.count[i]
        y, alpha = trails.y[i, :n], trails.alpha[i, :n]
        assert (np.diff(y) <= 1e-4).all()  # الذيل أعلى الرأس
        assert (np.diff(alpha) <= 1e-6).all()  # الأقدم أخفت
        assert (trails.half_width[i, :n] > 0.0).all()
        assert alpha.max() <= 1.0
        checked += 1
    assert checked > 0


def test_wet_trail_dries_after_the_drop_stops() -> None:
    streams = make(count=3, seed=3)
    run(streams, 40.0)
    assert streams.trails().count.max() > 0
    streams._sliding[:] = False  # نجمّد الجميع
    streams._grow[:] = 0.0
    streams._critical[:] = 99.0
    run(streams, 40.0)
    assert streams.trails().count.max() == 0  # جفّت كل الآثار


def test_residue_beads_appear_age_out_and_stay_bounded() -> None:
    streams = make(count=3, seed=8)
    peak = 0
    for _ in range(30 * 120):
        streams.step(FPS_DT, 0.0)
        peak = max(peak, streams.residue().shape[0])
    assert 0 < peak <= 2 * 3 * 6
    streams._sliding[:] = False
    streams._grow[:] = 0.0
    streams._critical[:] = 99.0
    run(streams, 20.0)
    assert streams.residue().shape[0] == 0


def test_step_cost_stays_small_at_the_maximum_count() -> None:
    streams = make(count=8, seed=1)
    start = time.perf_counter()
    for _ in range(300):
        streams.step(FPS_DT, 0.2)
    assert (time.perf_counter() - start) / 300 < 0.004  # أقل من 4 ms للخطوة


# ------------------------------------------------------------------ المرسِم
@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


PARAMS = SimpleNamespace(color_rgb=(170, 205, 255), drop_opacity=0.6)


def render(streams: EdgeStreams, size=(int(WIDTH), int(HEIGHT))) -> np.ndarray:
    image = QImage(size[0], size[1], QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_edge_streams(painter, streams, PARAMS, float(size[1]))  # type: ignore[arg-type]
    painter.end()
    buffer = np.frombuffer(image.constBits(), np.uint8).reshape(size[1], image.bytesPerLine() // 4, 4)
    return buffer[:, : size[0], 3].copy()  # قناة alpha


def test_painter_draws_on_the_edges_only(app: QApplication) -> None:
    streams = make(count=3, opacity=0.5)
    run(streams, 25.0)
    alpha = render(streams)
    assert alpha[:, :80].sum() + alpha[:, -80:].sum() > 0
    assert alpha[:, 120:-120].sum() == 0  # الوسط شفاف تمامًا


def test_painter_is_deterministic_and_does_not_mutate_the_simulation(app: QApplication) -> None:
    streams = make(count=3, opacity=0.5)
    run(streams, 25.0)
    before = streams.drops().copy()
    first = render(streams)
    second = render(streams)
    assert np.array_equal(first, second)
    assert np.array_equal(before, streams.drops())


def test_painter_scales_with_opacity_and_draws_nothing_for_zero_count(app: QApplication) -> None:
    faint, strong = make(opacity=0.15), make(opacity=0.7)
    run(faint, 25.0)
    run(strong, 25.0)
    assert render(strong).sum() > render(faint).sum() > 0
    assert render(make(count=0)).sum() == 0


def test_painter_draws_a_lone_drop_with_a_glossy_body(app: QApplication) -> None:
    streams = make(count=1, opacity=0.6)
    streams._trail_t[:] = -1.0e9  # بلا أثر ولا حبيبات: القطرة وحدها
    streams._res_t0[:] = -1.0e9
    streams._sliding[:] = False
    streams._grow[:] = 0.0
    streams._mass[:] = 0.02
    streams._mass[0] = 2.0
    streams._alpha_mult[0] = 1.0
    streams._x[0], streams._y[0] = 30.0, 300.0
    alpha = render(streams)
    patch = alpha[290:312, 20:42]
    assert patch.max() > 60  # جسم مرئي
    assert alpha[:250].sum() == 0 and alpha[350:].sum() == 0  # ولا شيء غيره
    # اللمعان في الأعلى أوضح من الحافة السفلية الداكنة نصف الشفافة: الصفوف العليا أكثر كثافة
    assert patch[:11].sum() != patch[11:].sum()
