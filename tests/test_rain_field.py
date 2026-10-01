"""tests/test_rain_field.py: اختبارات RainField (NumPy فقط، بلا Qt)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from raindesk.config.schema import default_settings
from raindesk.core.constants import MAX_DROPS_PER_SCREEN, SPAWN_MARGIN_TOP_FRACTION
from raindesk.engine.params import EngineParams, params_from_settings
from raindesk.engine.rain_field import RainField

_WIDTH = 1920.0
_HEIGHT = 1080.0
_DT = 1.0 / 60.0
_PAD = 40.0  # يطابق هامش rain_field
_EPS = 1e-3
_CHI_SQUARE_LIMIT = 27.88  # df = 9, p = 0.001 (القيمة المطلوبة في المواصفة)


def _params(wind: float = 12.0, gusts: float = 0.0) -> EngineParams:
    settings = default_settings()
    settings.wind_angle_deg = wind
    settings.wind_gusts = gusts
    return params_from_settings(settings)


def _field(seed: int, count: int) -> RainField:
    field = RainField(_WIDTH, _HEIGHT, np.random.default_rng(seed))
    field.set_active_count(count)
    return field


def _all_lines(field: RainField, layers: int = 5) -> np.ndarray:
    return np.concatenate(field.layer_lines(layers))


def test_same_seed_gives_identical_arrays() -> None:
    params = _params(wind=25.0, gusts=0.5)
    fields = [_field(seed=7, count=800) for _ in range(2)]
    for field in fields:
        for i in range(300):
            field.step(_DT, params, math.sin(i * 0.05))
    np.testing.assert_array_equal(_all_lines(fields[0]), _all_lines(fields[1]))
    np.testing.assert_array_equal(fields[0].drain_landings(), fields[1].drain_landings())


def test_different_seeds_differ() -> None:
    a, b = _field(1, 500), _field(2, 500)
    assert not np.array_equal(_all_lines(a), _all_lines(b))


@pytest.mark.parametrize("wind", [-60.0, 0.0, 60.0])
def test_no_nan_or_inf_after_1000_steps(wind: float) -> None:
    params = _params(wind=wind, gusts=1.0)
    field = _field(seed=3, count=1500)
    for i in range(1000):
        field.step(_DT, params, math.sin(i * 0.1))
    assert np.isfinite(_all_lines(field)).all()


def test_active_drops_respect_bounds_and_count_matches_target() -> None:
    wind = 30.0
    params = _params(wind=wind)
    target = RainField.target_count(_WIDTH, _HEIGHT, params.intensity, 1.0, wind)
    field = _field(seed=11, count=0)
    field.set_active_count(target)
    for _ in range(600):
        field.step(_DT, params, 0.0)
    assert field.active_count == target
    lines = _all_lines(field)
    margin = SPAWN_MARGIN_TOP_FRACTION * _HEIGHT
    x_limit = (_HEIGHT + margin) * abs(math.tan(math.radians(wind))) + _PAD
    x_head, y_head, y_tail = lines[:, 2], lines[:, 3], lines[:, 1]
    assert lines.shape[0] == target
    assert (x_head >= -x_limit - _EPS).all() and (x_head <= _WIDTH + x_limit + _EPS).all()
    assert (y_head >= -margin - _EPS).all() and (y_head <= _HEIGHT + _EPS).all()
    assert (y_tail <= _HEIGHT + _PAD + _EPS).all()


def test_wind_compensated_spawn_band_gives_uniform_density() -> None:
    params = _params(wind=30.0)
    field = _field(seed=2024, count=4000)
    for _ in range(20 * 60):  # 20 ثانية محاكاة بخطوة 1/60
        field.step(_DT, params, 0.0)
    heads = _all_lines(field)[:, 2:4]
    visible = heads[(heads[:, 1] >= 0.0) & (heads[:, 1] <= _HEIGHT)]
    middle = visible[(visible[:, 0] >= _WIDTH / 3.0) & (visible[:, 0] < 2.0 * _WIDTH / 3.0)]
    observed, _ = np.histogram(middle[:, 0], bins=10, range=(_WIDTH / 3.0, 2.0 * _WIDTH / 3.0))
    expected = observed.sum() / 10.0
    chi_square = float(((observed - expected) ** 2 / expected).sum())
    assert observed.sum() > 200  # عينة كافية لصحة الاختبار
    assert chi_square < _CHI_SQUARE_LIMIT


def test_target_count_grows_with_intensity_and_wind_and_respects_capacity() -> None:
    counts = [RainField.target_count(_WIDTH, _HEIGHT, i / 10, 1.0, 10.0) for i in range(11)]
    assert counts == sorted(counts) and counts[0] < counts[-1]
    winds = (0.0, 20.0, 45.0, 70.0)
    by_wind = [RainField.target_count(_WIDTH, _HEIGHT, 0.5, 1.0, w) for w in winds]
    assert by_wind == sorted(by_wind) and by_wind[0] < by_wind[-1]
    assert by_wind[0] == RainField.target_count(_WIDTH, _HEIGHT, 0.5, 1.0, -0.0)
    assert RainField.target_count(_WIDTH, _HEIGHT, 0.5, 1.0, 20.0) == RainField.target_count(
        _WIDTH, _HEIGHT, 0.5, 1.0, -20.0
    )  # التناظر: |الزاوية| فقط
    assert RainField.target_count(7680, 4320, 1.0, 5.0, 70.0) == MAX_DROPS_PER_SCREEN
    assert RainField.target_count(_WIDTH, _HEIGHT, 1.0, 1.0, 0.0, capacity=100) == 100
    assert RainField.target_count(0.0, _HEIGHT, 0.5, 1.0, 0.0) == 0


def test_resize_and_set_active_count_keep_invariants() -> None:
    field = _field(seed=5, count=300)
    field.resize(1280.0, 720.0)
    assert field.active_count == 300
    field.set_active_count(10**9)
    assert field.active_count == MAX_DROPS_PER_SCREEN
    field.set_active_count(-5)
    assert field.active_count == 0
    assert _all_lines(field).shape == (0, 4)


def test_landings_are_recorded_then_drained() -> None:
    params = _params()
    field = _field(seed=9, count=1000)
    for _ in range(120):
        field.step(_DT, params, 0.0)
    landings = field.drain_landings()
    assert landings.ndim == 2 and landings.shape[1] == 3 and landings.shape[0] > 0
    assert np.allclose(landings[:, 1], _HEIGHT)  # bottom_edge: الهبوط عند أسفل الشاشة
    assert field.drain_landings().shape == (0, 3)  # المخزن فُرّغ


def test_layer_lines_partition_is_complete_and_ordered_far_to_near() -> None:
    field = _field(seed=4, count=1200)
    field.step(_DT, _params(), 0.0)
    layers = field.layer_lines(5)
    assert len(layers) == 5
    assert sum(a.shape[0] for a in layers) == 1200
    assert all(a.dtype == np.float32 and a.shape[1] == 4 for a in layers)
    # تبديل عدد الطبقات يعيد حساب الفهارس دون فقد قطرات.
    assert sum(a.shape[0] for a in field.layer_lines(8)) == 1200