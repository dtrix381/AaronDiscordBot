import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
import os

async def main():
    await asyncio.gather(
        tfs_bot.start(os.getenv("TFS_TOKEN")),
        kick_bot.start(os.getenv("KICK_TOKEN"))
    )

asyncio.run(main())
