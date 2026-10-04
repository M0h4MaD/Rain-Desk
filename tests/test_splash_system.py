"""tests/test_splash_system.py: اختبارات SplashSystem (NumPy فقط، بلا Qt)."""

from __future__ import annotations

import numpy as np
import pytest

from raindesk.engine.splash_system import SplashSystem

_DT = 1.0 / 60.0
_MAX_RIPPLE_LIFE_S = 0.55  # الحد الأعلى الموثّق لعمر التموّج
_MAX_SPRAY_LIFE_S = 0.42  # الحد الأعلى الموثّق لعمر جسيم الرذاذ
_SIGMAS = 5.0  # تسامح إحصائي: 5 انحرافات معيارية (احتمال فشل عرضي أقل من 1e-6)


def _landings(count: int, z: float = 0.5, y: float = 1000.0) -> np.ndarray:
    xs = np.linspace(0.0, 1900.0, count, dtype=np.float32)
    return np.stack(
        [xs, np.full(count, y, np.float32), np.full(count, z, np.float32)], axis=1
    )


def test_pool_never_exceeds_capacity() -> None:
    capacity = 50
    system = SplashSystem(np.random.default_rng(1), capacity=capacity)
    for _ in range(200):
        system.spawn(_landings(40), 1.0)  # أكثر بكثير من السعة
        system.step(_DT)
        assert system.ripples().shape[0] <= capacity
        assert system.sprays().shape[0] <= capacity


def test_every_particle_dies_by_its_maximum_lifetime() -> None:
    system = SplashSystem(np.random.default_rng(2))
    system.spawn(_landings(200, z=1.0), 1.0)
    assert system.ripples().shape[0] > 0 and system.sprays().shape[0] > 0
    steps = int(_MAX_RIPPLE_LIFE_S / _DT) + 3
    for step in range(steps):
        system.step(_DT)
        if step * _DT > _MAX_SPRAY_LIFE_S + _DT:
            assert system.sprays().shape[0] == 0
    assert system.ripples().shape[0] == 0
    assert system.sprays().shape[0] == 0


def test_alpha_never_increases_over_a_particle_life() -> None:
    system = SplashSystem(np.random.default_rng(3))
    for _ in range(
        50
    ):  # p = 0.35 + 0.65 * 0.7 = 0.805 لهبوط واحد؛ نعيد حتى يتولد رذاذ فعلًا
        system.spawn(_landings(1, z=0.7), 1.0)
        if system.ripples().shape[0] > 0:
            break
    previous_ripple = system.ripples()[0, 4]
    previous_spray_max = float(system.sprays()[:, 3].max())
    for _ in range(40):
        system.step(_DT)
        ripples, sprays = system.ripples(), system.sprays()
        if ripples.shape[0]:
            assert ripples[0, 4] <= previous_ripple + 1e-9
            previous_ripple = float(ripples[0, 4])
        if sprays.shape[0]:
            # كل الجسيمات من هبوط واحد (alpha0 واحد)، وكلها تتلاشى، فالأقصى لا يزيد أبدًا.
            assert float(sprays[:, 3].max()) <= previous_spray_max + 1e-9
            previous_spray_max = float(sprays[:, 3].max())


@pytest.mark.parametrize(("amount", "z"), [(0.6, 0.5), (1.0, 0.0), (0.3, 1.0)])
def test_spawn_frequency_matches_documented_probability(
    amount: float, z: float
) -> None:
    count = 20000
    system = SplashSystem(np.random.default_rng(4), capacity=count)
    system.spawn(_landings(count, z=z), amount)
    probability = amount * (0.35 + 0.65 * z)
    expected = count * probability
    sigma = (count * probability * (1.0 - probability)) ** 0.5
    assert abs(system.ripples().shape[0] - expected) <= _SIGMAS * sigma


def test_zero_amount_and_empty_input_spawn_nothing() -> None:
    system = SplashSystem(np.random.default_rng(5))
    system.spawn(_landings(100), 0.0)
    system.spawn(np.zeros((0, 3), np.float32), 1.0)
    assert system.ripples().shape[0] == 0 and system.sprays().shape[0] == 0


def test_bad_shape_is_rejected() -> None:
    system = SplashSystem(np.random.default_rng(6))
    with pytest.raises(ValueError):
        system.spawn(np.zeros((5, 2), np.float32), 1.0)


def test_ripple_geometry_follows_the_documented_model() -> None:
    system = SplashSystem(np.random.default_rng(7), capacity=400)
    system.spawn(_landings(300, z=1.0), 1.0)
    system.step(0.01)
    ripples = system.ripples()
    assert ripples.shape[1] == 5
    assert np.allclose(ripples[:, 3], ripples[:, 2] / 3.0)  # ry = rx / 3
    assert (ripples[:, 2] >= 2.0).all() and (
        ripples[:, 2] <= 36.0 + 1e-3
    ).all()  # r0 .. r1(z=1)
    assert ((ripples[:, 4] >= 0.0) & (ripples[:, 4] <= 1.0)).all()


def test_sprays_launch_upward_and_clear_empties_the_pools() -> None:
    system = SplashSystem(np.random.default_rng(8), capacity=400)
    system.spawn(_landings(100, z=0.5, y=800.0), 1.0)
    system.step(0.02)
    assert (
        system.sprays()[:, 1] < 800.0
    ).all()  # بعد 20 ms ما زالت كلها أعلى من نقطة الهبوط
    system.clear()
    assert system.ripples().shape[0] == 0 and system.sprays().shape[0] == 0


def test_same_seed_gives_identical_output() -> None:
    outputs = []
    for _ in range(2):
        system = SplashSystem(np.random.default_rng(99))
        for _ in range(30):
            system.spawn(_landings(20), 0.8)
            system.step(_DT)
        outputs.append((system.ripples().copy(), system.sprays().copy()))
    np.testing.assert_array_equal(outputs[0][0], outputs[1][0])
    np.testing.assert_array_equal(outputs[0][1], outputs[1][1])
