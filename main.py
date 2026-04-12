import sys
import os
import asyncio

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tfs import bot as tfs_bot
from kick import bot as kick_bot


async def main():
    await asyncio.gather(
        tfs_bot.start(os.getenv("TFS_TOKEN")),
        kick_bot.start(os.getenv("KICK_TOKEN"))
    )

asyncio.run(main())
