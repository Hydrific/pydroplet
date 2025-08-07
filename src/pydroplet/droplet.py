"""Droplet API."""

import asyncio
from dataclasses import dataclass
import json
import logging
import socket
import ssl
import datetime
from collections.abc import Callable
from typing import Any, Self, Tuple
import time

import aiohttp


class DropletConnection:
    """Connection to Droplet device."""

    DEFAULT_PORT = 443

    @staticmethod
    async def get_client(
        session: aiohttp.client.ClientSession, host: str, port: int | None, token: str
    ) -> aiohttp.ClientWebSocketResponse:
        """Create connection to Droplet device."""
        url = f"wss://{host}:{port if port else DropletConnection.DEFAULT_PORT}/ws"
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        headers = {"Authorization": token}
        return await session.ws_connect(
            url=url, ssl_context=ssl_context, headers=headers, heartbeat=10
        )


class DropletDiscovery:
    """Store Droplet discovery information."""

    METADATA_TIMEOUT: int = 5

    host: str
    port: int | None

    _device_id: str
    _client: aiohttp.ClientWebSocketResponse | None = None

    def __init__(self, host: str, port: int | None, service_name: str) -> None:
        """Initialize Droplet discovery."""
        self.host = host
        self.port = port
        try:
            self._device_id = service_name.split(".")[0]
        except IndexError:
            self._device_id = ""

    def is_valid(self) -> bool:
        """Check discovery validity."""
        if self.port is None or self.port < 1:
            return False
        return True

    async def try_connect(
        self, session: aiohttp.client.ClientSession, pairing_code: str
    ) -> bool:
        """Try to connect to Droplet with provided credentials."""
        try:
            self._client = await DropletConnection.get_client(
                session, self.host, self.port, pairing_code
            )
            res = await self._client.receive(timeout=1)
            if not res or res.type in [
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSED,
            ]:
                return False
            # If this message happened to contain the device ID, we should get that
            msg: dict[str, str] = {}
            try:
                msg = res.json()
            except json.JSONDecodeError:
                return True
            if dev_id := msg.get("ids"):
                self._device_id = dev_id
        except (
            aiohttp.WSServerHandshakeError,
            aiohttp.ClientConnectionError,
            socket.gaierror,
        ):
            return False
        return True

    async def get_device_id(self) -> str:
        """Get the Droplet's device ID."""
        if self._device_id:
            return self._device_id

        if not self._client or self._client.closed:
            return ""

        # If we don't already have the device ID, try to get it
        end = time.time() + self.METADATA_TIMEOUT
        while not self._device_id and time.time() < end:
            msg: dict[str, str] = {}
            try:
                msg = await self._client.receive_json(timeout=1)
            except json.JSONDecodeError:
                continue
            self._device_id = msg.get("ids", "")
        return self._device_id

    def __enter__(self) -> Self:
        return self

    async def __exit__(self, *_: Tuple[Any, ...]) -> None:
        if self._client and not self._client.closed:
            await self._client.close()


@dataclass
class VolumeAccumulator:
    """Track volume accumulation over a period."""

    name: str
    next_reset: datetime.datetime

    _volume: float = 0

    def add_volume(self, volume: float) -> None:
        """Add volume to the accumulator."""
        self._volume += volume

    def get_volume(self) -> float:
        """Retrieve the accumulated volume."""
        return self._volume

    def reset(self) -> None:
        """Reset volume to 0."""
        self._volume = 0

    def set_next_reset(self, reset_time: datetime.datetime) -> None:
        """Set the next time at which the accumulator will expire."""
        self.next_reset = reset_time

    def reset_expired(self, local_time: datetime.datetime) -> bool:
        """Check if reset time has expired. Returns true if expired, false otherwise."""
        return local_time > self.next_reset


class Droplet:
    """Droplet device."""

    host: str
    session: aiohttp.client.ClientSession
    token: str
    port: int = 80
    logger: logging.Logger | None = None
    timeout: float = 5

    _properties: dict[str, str] = {}
    _flow_rate: float = 0
    _volume_delta: float = 0
    _signal_quality: str = "Unknown"
    _server_status: str = "Unknown"
    _available: bool = False
    _accumulators: list[VolumeAccumulator] = []

    _client: aiohttp.ClientWebSocketResponse | None = None
    _connected: bool = False
    _listen_forever = False

    def __init__(
        self,
        host: str,
        session: aiohttp.client.ClientSession,
        token: str,
        port: int,
        logger: logging.Logger | None = None,
    ) -> None:
        self.host = host
        self.session = session
        self.token = token
        self.port = port
        self.logger = logger

    @property
    def connected(self) -> bool:
        """Return true if we are connected to Droplet."""
        return self._client is not None and not self._client.closed

    async def connect(self) -> bool:
        """Connect to Droplet."""
        if self._connected:
            return True

        if not self.session:
            return False

        try:
            self._client = await DropletConnection.get_client(
                self.session, self.host, self.port, self.token
            )
        except (
            aiohttp.WSServerHandshakeError,
            aiohttp.ClientConnectionError,
            socket.gaierror,
        ) as ex:
            self._log(logging.WARNING, "Failed to open connection: %s", str(ex))
            self._available = False
            return False

        return True

    async def disconnect(self) -> bool:
        """Disconnect from WebSocket."""
        self._available = False
        self._connected = False
        if self._client and not self._client.closed:
            return await self._client.close()
        return True

    async def listen(self, callback: Callable[[Any], None]) -> None:
        """Listen for messages over the websocket."""
        while self._client and not self._client.closed:
            try:
                message = await self._client.receive(self.timeout)
            except TimeoutError:
                self._log(logging.WARNING, "Read timeout")
                continue
            match message.type:
                case aiohttp.WSMsgType.ERROR:
                    self._log(
                        logging.WARNING, "Received error message: %s", message.data
                    )
                    await self.disconnect()
                    return
                case aiohttp.WSMsgType.TEXT:
                    if not self._available:
                        self._available = True
                        callback(None)
                    try:
                        if self._parse_message(message.json()):
                            callback(None)
                    except json.JSONDecodeError:
                        pass
                case aiohttp.WSMsgType.CLOSE | aiohttp.WSMsgType.CLOSED:
                    self._log(logging.WARNING, "Connection closed!")
                    await self.disconnect()
                    return
                case aiohttp.WSMsgType.CLOSING:
                    pass
                case _:
                    self._log(
                        logging.WARNING,
                        f"Received unexpected message type: {aiohttp.WSMsgType(message.type).name}",
                    )

    async def listen_forever(
        self, reconnect_delay: int, callback: Callable[[Any], None]
    ) -> None:
        """Listen for messages. If Droplet disconnects, try to connect again."""
        self._listen_forever = True
        while self._listen_forever:
            connected = await self.connect()
            if connected:
                await self.listen(callback=callback)
            callback(None)
            await asyncio.sleep(reconnect_delay)

    async def stop_listening(self) -> None:
        """Stop the listen_forever loop."""
        self._listen_forever = False

    def add_accumulator(self, name: str, reset_time: datetime.datetime) -> bool:
        """Add a volume accumulator. Returns true on success, false if there is already an accumulator of the same name."""
        for a in self._accumulators:
            if a.name == name:
                self._log(
                    logging.WARNING, "Accumulator with name %s already exists", name
                )
                return False
        self._accumulators.append(VolumeAccumulator(name, reset_time))
        return True

    def remove_accumulator(self, name: str) -> bool:
        """Remove accumulator. Returns true if accumulator found, false otherwise."""
        for a in self._accumulators:
            if a.name == name:
                self._accumulators.remove(a)
                return True
        return False

    def _update_accumulators(self, volume: float) -> None:
        """Update accumulators with a new volume delta."""
        for a in self._accumulators:
            a.add_volume(volume)

    def accumulator_expired(self, local_time: datetime.datetime, name: str) -> bool:
        """Check if accumulator is expired. True if expired, false if not or accumulator not found."""
        for a in self._accumulators:
            if a.name == name:
                return a.reset_expired(local_time)
        return False

    def reset_accumulator(self, name: str, next_reset: datetime.datetime) -> None:
        """Reset accumulator to new expiration date and zero volume."""
        for a in self._accumulators:
            if a.name == name:
                a.reset()
                a.set_next_reset(next_reset)

    def get_accumulated_volume(self, name: str) -> float:
        """Get volume for an accumulator."""
        for a in self._accumulators:
            if a.name == name:
                return a.get_volume()
        self._log(logging.WARNING, "Accumulator '%s' not found", name)
        return -1

    def _parse_message(self, msg: dict[str, Any]) -> bool:
        if msg.get("ids"):
            return self._parse_info_message(msg)
        return self._parse_state_message(msg)

    def _parse_info_message(self, msg: dict[str, str]) -> bool:
        if self._properties != msg:
            self._properties = msg
            return True
        return False

    def _parse_state_message(self, msg: dict[str, Any]) -> bool:
        """Parse state message and return true if anything changed."""
        changed = False
        if (flow_rate := msg.get("flow")) is not None:
            self._flow_rate = flow_rate
            changed = True
        if (volume := msg.get("volume")) is not None:
            self._volume_delta += volume
            self._update_accumulators(volume)
            changed = True
        if (network := msg.get("server")) and self._server_status != network:
            self._server_status = network
            changed = True
        if (signal := msg.get("signal")) and self._signal_quality != signal:
            self._signal_quality = signal
            changed = True
        return changed

    def _log(self, level: int, msg: object, *args: object) -> None:
        """Log a message, if a logger is available."""
        if not self.logger:
            return
        self.logger.log(level, msg, *args)

    def get_flow_rate(self) -> float:
        """Get Droplet's flow rate."""
        return self._flow_rate

    def get_volume_delta(self) -> float:
        res = self._volume_delta
        self._volume_delta -= res
        return res

    def get_signal_quality(self) -> str:
        """Get Droplet's signal quality."""
        return self._signal_quality

    def get_server_status(self) -> str:
        """Get Droplet's server status."""
        return self._server_status

    def get_availability(self) -> bool:
        """Return true if Droplet device is available."""
        return self._available

    def get_model(self) -> str:
        return self._properties.get("mdl", "")

    def get_manufacturer(self) -> str:
        return self._properties.get("mf", "")

    def get_device_id(self) -> str:
        return self._properties.get("ids", "")

    def get_fw_version(self) -> str:
        return self._properties.get("sw", "")

    def get_sn(self) -> str:
        return self._properties.get("sn", "")

    def version_info_available(self) -> bool:
        return self._properties != {}
