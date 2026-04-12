from tfs import bot as tfs_bot
from kick import bot as kick_bot  # your other bot

import asyncio
import os

async def main():
    await asyncio.gather(
        tfs_bot.start(os.getenv("TFS_TOKEN")),
        kick_bot.start(os.getenv("KICK_TOKEN"))
    )

asyncio.run(main())