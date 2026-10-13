"""Test the configuration reading."""
import yaml

from trollsched.utils import read_config


def test_satellites_can_be_marked_trimmable(tmp_path):
    """Test that a satellite can be configured as trimmable."""
    config = dict(default=dict(station=["nrk"], forward=12, start=0),
                  stations=dict(nrk=dict(name="nrk", longitude=16, latitude=58, altitude=0,
                                         area="euron1", satellites=["fengyun 3f"])),
                  pattern=dict(),
                  satellites={"fengyun 3f": dict(night=0.2, day=0.8, trimmable=True)})
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(config))

    scheduler = read_config(str(config_file))

    assert scheduler.stations[0].satellites[0].trimmable
