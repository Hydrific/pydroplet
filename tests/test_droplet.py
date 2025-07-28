import pytest
import aiohttp
from datetime import datetime, timedelta
from pydroplet import droplet


@pytest.fixture
def droplet_device() -> droplet.Droplet:
    return droplet.Droplet(
        "localhost", aiohttp.client.ClientSession, "123456", 443, None
    )


@pytest.fixture
def droplet_discovery() -> droplet.DropletDiscovery:
    return droplet.DropletDiscovery(
        "localhost", 443, "Droplet-1234._droplet._tcp._local.", {}
    )


def test_valid_discovery(droplet_discovery: droplet.DropletDiscovery) -> None:
    assert droplet_discovery.is_valid()


def test_invalid_discovery() -> None:
    invalid_device_id = droplet.DropletDiscovery("localhost", 443, "", {})
    assert not invalid_device_id.is_valid()

    no_port = droplet.DropletDiscovery("localhost", None, "Droplet-1234.local", {})
    assert not no_port.is_valid()

    invalid_port = droplet.DropletDiscovery("localhost", -1, "Droplet-1234.local", {})
    assert not invalid_port.is_valid()


def test_parse_message(droplet_device: droplet.Droplet) -> None:
    assert droplet_device.get_flow_rate() == 0
    flow_msg = {"flow": 0.5}
    assert droplet_device._parse_message(flow_msg)
    assert droplet_device.get_flow_rate() == 0.5

    assert droplet_device.get_server_status() == "Unknown"
    server_msg = {"server": "Connected"}
    assert droplet_device._parse_message(server_msg)
    assert droplet_device.get_server_status() == "Connected"

    assert droplet_device.get_signal_quality() == "Unknown"
    signal_msg = {"signal": "Strong Signal"}
    assert droplet_device._parse_message(signal_msg)
    assert droplet_device.get_signal_quality() == "Strong Signal"

    assert droplet_device.get_volume_delta() == 0
    volume_msg = {"volume": 0.1}
    assert droplet_device._parse_message(volume_msg)
    assert droplet_device.get_volume_delta() == 0.1

    # The value is unchanged so these should be false
    assert not droplet_device._parse_message(server_msg)
    assert not droplet_device._parse_message(signal_msg)


def test_volume_delta(droplet_device: droplet.Droplet) -> None:
    assert droplet_device.get_volume_delta() == 0
    volume_msg = {"volume": 0.5}
    assert droplet_device._parse_message(volume_msg)
    assert droplet_device.get_volume_delta() == 0.5
    # Since the volume delta was read, it should be subtracted
    assert droplet_device.get_volume_delta() == 0

    # Try with multiple volumes before reading delta
    for i in range(3):
        volume_msg = {"volume": i}
        assert droplet_device._parse_message(volume_msg)
    assert droplet_device.get_volume_delta() == 3
    assert droplet_device.get_volume_delta() == 0


def test_volume_accumulator(droplet_device: droplet.Droplet) -> None:
    droplet_device.add_accumulator("daily", datetime.now() - timedelta(days=1))
    volume_msg = {"volume": 0.5}
    assert droplet_device._parse_message(volume_msg)
    assert droplet_device.get_accumulated_volume("daily") == 0.5

    # Accumulator should be expired since it was set to 1 day ago
    assert droplet_device.accumulator_expired(datetime.now(), "daily")

    # Resetting accumulator should set it to 0
    droplet_device.reset_accumulator("daily", datetime.now() + timedelta(days=1))
    assert not droplet_device.accumulator_expired(datetime.now(), "daily")
    assert droplet_device.get_accumulated_volume("daily") == 0

    # Adding an accumulator with the same name as an existing one should fail
    assert not droplet_device.add_accumulator("daily", datetime.now())

    # Removing a non-existent accumulator should fail
    assert not droplet_device.remove_accumulator("test")
    # But an existing one succeeds
    assert droplet_device.remove_accumulator("daily")
