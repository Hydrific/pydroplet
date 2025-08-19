import aiohttp
import asyncio
import argparse
import logging
from pydroplet import droplet

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

updated = asyncio.Event()


def update_callback(_):
    updated.set()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o", "--host", action="store", required=True, help="IP address of your Droplet"
    )
    parser.add_argument(
        "-t",
        "--token",
        action="store",
        required=True,
        help="Token from the Droplet app",
    )
    args = parser.parse_args()

    session = aiohttp.ClientSession()

    dev = droplet.Droplet(
        args.host, session, args.token, droplet.DropletConnection.DEFAULT_PORT, _LOGGER
    )
    async with asyncio.TaskGroup() as tg:
        tg.create_task(dev.listen_forever(5, update_callback))

        while True:
            await updated.wait()
            print(f"Droplet updated: flow={dev.get_flow_rate()},"
                f"volume_delta={dev.get_volume_delta()},"
                f"server_connectivity={dev.get_server_status()},"
                f"signal_quality={dev.get_signal_quality()}"
            )
            updated.clear()


if __name__ == "__main__":
    asyncio.run(main())
