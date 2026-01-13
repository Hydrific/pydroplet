import aiohttp
import asyncio
import argparse
import logging
import time
from pydroplet import droplet

logger = logging.getLogger(__name__)


def update_callback(_):
    logger.debug("Updated")


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

    async with aiohttp.ClientSession() as session, asyncio.TaskGroup() as tg:
        dev = droplet.Droplet(
            args.host,
            session,
            args.token,
            droplet.DropletConnection.DEFAULT_PORT,
            logger,
        )
        start = time.time()
        task = tg.create_task(dev.listen_forever(5, update_callback))
        while True:
            if dev.connected:
                break
            await asyncio.sleep(0.01)
        end = time.time()
        task.cancel()
    logger.warning(f"Droplet took {end - start} seconds to connect")


if __name__ == "__main__":
    asyncio.run(main())
