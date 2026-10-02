import pytest
import asyncio
import pytest_asyncio
from unittest.mock import AsyncMock, create_autospec, patch
import aiohttp
from datetime import datetime, timedelta
from pydroplet import droplet


@pytest_asyncio.fixture
async def droplet_device() -> droplet.Droplet:
    return droplet.Droplet(
        "localhost", aiohttp.client.ClientSession(), "123456", 443, None
    )


@pytest.fixture
def droplet_discovery() -> droplet.DropletDiscovery:
    return droplet.DropletDiscovery(
        "localhost", 443, "Droplet-1234._droplet._tcp._local."
    )


def test_valid_discovery(droplet_discovery: droplet.DropletDiscovery) -> None:
    assert droplet_discovery.is_valid()


def test_invalid_discovery() -> None:
    no_port = droplet.DropletDiscovery("localhost", None, "Droplet-1234.local")
    assert not no_port.is_valid()

    invalid_port = droplet.DropletDiscovery("localhost", -1, "Droplet-1234.local")
    assert not invalid_port.is_valid()


def test_parse_message(droplet_device: droplet.Droplet) -> None:
    assert droplet_device.get_flow_rate() == 0
    flow_msg = {"flow": 0.5}
    assert droplet_device._parse_message(flow_msg)
    assert droplet_device.get_flow_rate() == 0.5

    assert droplet_device.get_server_status() is None
    server_msg = {"server": "Connected"}
    assert droplet_device._parse_message(server_msg)
    assert droplet_device.get_server_status() == "connected"

    assert droplet_device.get_signal_quality() is None
    signal_msg = {"signal": "Strong Signal"}
    assert droplet_device._parse_message(signal_msg)
    assert droplet_device.get_signal_quality() == "strong_signal"

    assert droplet_device.get_volume_delta() == 0
    volume_msg = {"volume": 0.1}
    assert droplet_device._parse_message(volume_msg)
    assert droplet_device.get_volume_delta() == 0.1

    # The value is unchanged so these should be false
    assert not droplet_device._parse_message(server_msg)
    assert not droplet_device._parse_message(signal_msg)


def test_volume_delta(droplet_device: droplet.Droplet) -> None:
    assert droplet_device.get_volume_last_fetched() is None
    time_before_fetch = datetime.now()
    assert droplet_device.get_volume_delta() == 0
    time_after_fetch = droplet_device.get_volume_last_fetched()
    assert time_after_fetch is not None
    assert time_after_fetch > time_before_fetch

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


def test_leak_string_parsing(droplet_device: droplet.Droplet) -> None:
    assert droplet_device.get_low_leak() is None
    assert droplet_device.get_high_leak() is None

    assert droplet_device._parse_message({"low_leak": "ON", "high_leak": "OFF"})
    assert droplet_device.get_low_leak() is True
    assert droplet_device.get_high_leak() is False

    assert droplet_device._parse_message({"low_leak": "OFF", "high_leak": "ON"})
    assert droplet_device.get_low_leak() is False
    assert droplet_device.get_high_leak() is True

    # Same values again should be a no-op
    assert not droplet_device._parse_message({"low_leak": "OFF", "high_leak": "ON"})


@pytest.mark.asyncio
async def test_client_errors(droplet_device) -> None:
    def callback(_):
        pass

    async def mock_connect():
        return True

    with (patch("aiohttp.ClientWebSocketResponse", autospec=True) as mock_client,):
        client = mock_client.return_value
        client.receive.side_effect = aiohttp.ClientConnectionResetError()
        client.closed = False
        droplet_device.connect = mock_connect
        droplet_device._client = client

        async with asyncio.TaskGroup() as tg:
            tg.create_task(droplet_device.listen_forever(1, callback))
            await asyncio.sleep(1)
            await droplet_device.stop_listening()


@pytest.mark.asyncio
async def test_unhandled_error(droplet_device) -> None:
    def callback(_):
        pass

    async def mock_connect():
        return True

    class DropletError(Exception):
        pass

    with (patch("aiohttp.ClientWebSocketResponse", autospec=True) as mock_client,):
        client = mock_client.return_value
        client.receive.side_effect = DropletError()
        client.closed = False
        droplet_device.connect = mock_connect
        droplet_device._client = client

        with pytest.RaisesGroup(DropletError):
            async with asyncio.TaskGroup() as tg:
                tg.create_task(droplet_device.listen_forever(1, callback))


def test_accumulators_not_shared_between_instances() -> None:
    # Regression test: _accumulators used to be a class-level list shared by
    # every Droplet instance, so accumulators registered on one device were
    # fed by all devices' messages and survived instance replacement.
    device_a = droplet.Droplet("localhost", None, "123456", 443, None)
    device_b = droplet.Droplet("localhost", None, "654321", 443, None)

    assert device_a.add_accumulator("daily", datetime.now() + timedelta(days=1))
    # device_b must not see device_a's accumulator
    assert device_b.add_accumulator("daily", datetime.now() + timedelta(days=1))

    device_a._update_accumulators(100)
    assert device_a.get_accumulated_volume("daily") == 100
    assert device_b.get_accumulated_volume("daily") == 0


@pytest.mark.asyncio
async def test_try_connect_accepts_quiet_connection(
    droplet_discovery: droplet.DropletDiscovery,
) -> None:
    # Droplet may not send its first message until a second or two after the
    # handshake, and a connection that stays open means the pairing code was right
    with (patch("aiohttp.ClientWebSocketResponse", autospec=True) as mock_client,):
        client = mock_client.return_value
        client.receive.side_effect = TimeoutError()
        with patch.object(
            droplet.DropletConnection, "get_client", AsyncMock(return_value=client)
        ):
            assert await droplet_discovery.try_connect(None, "123456")
        client.receive.assert_awaited_once_with(
            timeout=droplet.DropletDiscovery.TIMEOUT
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        aiohttp.WSMessage(aiohttp.WSMsgType.CLOSE, 1000, ""),
        aiohttp.WSMessage(aiohttp.WSMsgType.ERROR, ConnectionResetError(), None),
    ],
)
async def test_try_connect_rejects_closed_connection(
    droplet_discovery: droplet.DropletDiscovery, message: aiohttp.WSMessage
) -> None:
    # Older firmware accepts the handshake, then closes on a wrong code
    with (patch("aiohttp.ClientWebSocketResponse", autospec=True) as mock_client,):
        client = mock_client.return_value
        client.closed = False
        client.receive.return_value = message
        with patch.object(
            droplet.DropletConnection, "get_client", AsyncMock(return_value=client)
        ):
            assert not await droplet_discovery.try_connect(None, "123456")
        client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_try_connect_closes_previous_connection(
    droplet_discovery: droplet.DropletDiscovery,
) -> None:
    # A retried pairing attempt must not leave the earlier connection open
    old_client = create_autospec(aiohttp.ClientWebSocketResponse, instance=True)
    old_client.closed = False
    new_client = create_autospec(aiohttp.ClientWebSocketResponse, instance=True)
    new_client.receive.side_effect = TimeoutError()
    droplet_discovery._client = old_client
    with patch.object(
        droplet.DropletConnection, "get_client", AsyncMock(return_value=new_client)
    ):
        assert await droplet_discovery.try_connect(None, "123456")
    old_client.close.assert_awaited_once()
    new_client.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_discovery_context_manager_closes_connection(
    droplet_discovery: droplet.DropletDiscovery,
) -> None:
    client = create_autospec(aiohttp.ClientWebSocketResponse, instance=True)
    client.closed = False
    async with droplet_discovery:
        droplet_discovery._client = client
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_device_id_waits_through_quiet_seconds() -> None:
    discovery = droplet.DropletDiscovery("localhost", 443, "")
    with (patch("aiohttp.ClientWebSocketResponse", autospec=True) as mock_client,):
        client = mock_client.return_value
        client.closed = False
        client.receive_json.side_effect = [TimeoutError(), {"ids": "Droplet-1234"}]
        discovery._client = client
        assert await discovery.get_device_id() == "Droplet-1234"


@pytest.mark.asyncio
async def test_stop_listening_closes_connection(droplet_device) -> None:
    # Home Assistant cancels the listen task on unload, so nothing else closes it
    client = create_autospec(aiohttp.ClientWebSocketResponse, instance=True)
    client.closed = False
    droplet_device._client = client
    await droplet_device.stop_listening()
    client.close.assert_awaited_once()
