"""Test the configuration reading."""
import pytest
import yaml

from trollsched.pass_scheduling_utils import Satellite
from trollsched.utils import read_config


@pytest.mark.parametrize("coverage_loss", [0, 5.5, 100])
def test_satellites_can_allow_configured_coverage_loss(tmp_path, coverage_loss):
    """Read the satellite trim flag and percentage coverage-loss allowance."""
    config = dict(default=dict(station=["nrk"], forward=12, start=0),
                  stations=dict(nrk=dict(name="nrk", longitude=16, latitude=58, altitude=0,
                                         area="euron1", satellites=["fengyun 3f"])),
                  pattern=dict(),
                  satellites={"fengyun 3f": dict(night=0.2, day=0.8, trimmable=True,
                                                max_coverage_loss=coverage_loss)})
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(config))

    scheduler = read_config(str(config_file))

    assert scheduler.stations[0].satellites[0].trimmable
    assert scheduler.stations[0].satellites[0].max_coverage_loss == coverage_loss


@pytest.mark.parametrize(("station_settings", "expected_antenna"), [({"antenna": "ANT-1"}, "ANT-1"), ({}, None)])
def test_station_antenna_is_optional_in_config(tmp_path, station_settings, expected_antenna):
    """Read the antenna of a station, leaving it unset when the config does not give one."""
    config = dict(default=dict(station=["nrk"], forward=12, start=0),
                  stations=dict(nrk=dict(name="nrk", longitude=16, latitude=58, altitude=0,
                                         area="euron1", satellites=["fengyun 3f"], **station_settings)),
                  pattern=dict(),
                  satellites={"fengyun 3f": dict(night=0.2, day=0.8)})
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(config))

    assert read_config(str(config_file)).stations[0].antenna == expected_antenna


@pytest.mark.parametrize("coverage_loss", [-1, 100.1, float("nan"), float("inf"), "5", None, True])
def test_satellites_reject_invalid_coverage_loss(coverage_loss):
    """Reject non-numeric, non-finite, and out-of-range percentage allowances."""
    with pytest.raises(ValueError, match="max_coverage_loss"):
        Satellite("fengyun 3f", night=0.2, day=0.8, max_coverage_loss=coverage_loss)


def test_satellite_trimming_is_disabled_without_coverage_loss_by_default():
    """Omitted settings preserve opt-in trimming and the zero-loss default."""
    satellite = Satellite("fengyun 3f", night=0.2, day=0.8)
    assert (satellite.trimmable, satellite.max_coverage_loss) == (False, 0)
