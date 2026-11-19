import pytest

from eng_sim_evaluator.thermal import (
    WallLayer,
    composite_heat_flux,
    composite_interface_temperatures,
    heat_flux,
    temperature_profile,
)


def test_temperature_profile_endpoints():
    assert temperature_profile(100.0, 20.0, 0.2, 0.0) == pytest.approx(100.0)
    assert temperature_profile(100.0, 20.0, 0.2, 0.2) == pytest.approx(20.0)
    assert temperature_profile(100.0, 20.0, 0.2, 0.1) == pytest.approx(60.0)


def test_heat_flux_fourier():
    # k=50 W/mK, dT=80 K over 0.2 m -> q = 50*80/0.2 = 20000 W/m^2.
    assert heat_flux(100.0, 20.0, 0.2, 50.0) == pytest.approx(20000.0)


def test_composite_wall_flux():
    layers = [WallLayer(0.1, 0.5), WallLayer(0.1, 1.0)]
    # R = 0.1/0.5 + 0.1/1.0 = 0.3; q = 80/0.3.
    assert composite_heat_flux(100.0, 20.0, layers) == pytest.approx(80.0 / 0.3)


def test_composite_interface_temperatures():
    layers = [WallLayer(0.1, 0.5), WallLayer(0.1, 1.0)]
    temps = composite_interface_temperatures(100.0, 20.0, layers)
    assert len(temps) == 3
    assert temps[0] == pytest.approx(100.0)
    assert temps[-1] == pytest.approx(20.0)
    # Most of the drop happens across the insulating first layer.
    assert temps[1] < 50.0
    assert temps[0] > temps[1] > temps[2]


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        temperature_profile(100.0, 20.0, 0.2, 0.25)
    with pytest.raises(ValueError):
        composite_heat_flux(100.0, 20.0, [])
    with pytest.raises(ValueError):
        WallLayer(0.0, 1.0)
