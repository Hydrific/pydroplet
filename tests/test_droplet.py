import json
from pydroplet import droplet


def test_discovery_normal():
    discovery_msg = {
        "dev": {
            "ids": "droplet-ABCD",
            "mdl": "Droplet 1.0",
            "mf": "Hydrific, part of LIXIL",
            "sw": "0.6.0",
            "sn": "ABCD",
        },
        "state_topic": "droplet-ABCD/state",
        "availability_topic": "droplet-ABCD/health",
    }

    discovery = droplet.DropletDiscovery("droplet/discovery/ABCD", discovery_msg)
    assert discovery is not None
    assert discovery.is_valid()


def test_discovery_id_mismatch():
    discovery_msg = {
        "dev": {
            "ids": "droplet-EFGH",
            "mdl": "Droplet 1.0",
            "mf": "Hydrific, part of LIXIL",
            "sw": "0.6.0",
            "sn": "ABCD",
        },
        "state_topic": "droplet-ABCD/state",
        "availability_topic": "droplet-ABCD/health",
    }

    discovery = droplet.DropletDiscovery("droplet/discovery/ABCD", discovery_msg)
    assert discovery is not None
    assert not discovery.is_valid()


def test_discovery_id_missing():
    discovery_msg = {
        "dev": {
            "mdl": "Droplet 1.0",
            "mf": "Hydrific, part of LIXIL",
            "sw": "0.6.0",
            "sn": "ABCD",
        },
        "state_topic": "droplet-ABCD/state",
        "availability_topic": "droplet-ABCD/health",
    }

    discovery = droplet.DropletDiscovery("droplet/discovery/ABCD", discovery_msg)
    assert discovery is not None
    assert not discovery.is_valid()


def test_parse_flow_rate():
    dev = droplet.Droplet()
    assert dev is not None
    assert dev.get_flow_rate() == 0

    msg = {"flow_rate": 0.1}
    dev.parse_message("droplet-ABCD/state", json.dumps(msg), 0, False)
    assert dev.get_flow_rate() == 0.1


def test_parse_server_connectivity():
    dev = droplet.Droplet()
    assert dev is not None
    assert dev.get_server_status() == "Unknown"

    msg = {"server_connectivity": "Connected"}
    dev.parse_message("droplet-ABCD/state", json.dumps(msg), 0, False)
    assert dev.get_server_status() == "Connected"


def test_parse_signal_quality():
    dev = droplet.Droplet()
    assert dev is not None
    assert dev.get_signal_quality() == "Unknown"

    msg = {"signal_quality": "Strong"}
    dev.parse_message("droplet-ABCD/state", json.dumps(msg), 0, False)
    assert dev.get_signal_quality() == "Strong"


def test_parse_health():
    dev = droplet.Droplet()
    assert dev is not None
    assert dev.get_availability()

    msg = "offline"
    dev.parse_message("droplet-ABCD/health", msg, 0, False)
    assert not dev.get_availability()
