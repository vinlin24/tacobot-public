"""
Initializes and sets up the Discord bot by registering events and extensions.
"""

import logging
import os

import discord
from discord.ext import commands

from . import (COMMAND_PREFIX, INTENTS, TACOBOT_TOKEN, TESTER_MODE,
               TESTER_PREFIX, TESTER_TOKEN, events)

discord.utils.setup_logging()
log = logging.getLogger(__name__)


class TacoBot(commands.Bot):
    def __init__(self) -> None:
        # Determine what mode the script is in (proper or tester)
        if TESTER_MODE:
            prefix: str = TESTER_PREFIX
        else:
            prefix: str = COMMAND_PREFIX
        super().__init__(command_prefix=prefix,
                         intents=INTENTS,
                         case_insensitive=True)
        # UPDATED: Removed saving of metadata as attrs.  I don't know if
        # that breaks anything yet, but that was a huge mess and
        # shouldn't have been done in the first place.

    async def setup_hook(self) -> None:
        await self.load_extensions("bot/cogs/")
        events.register_events(self)

    async def load_extensions(self, path: str) -> None:
        """Load all .py modules in path as extensions for bot."""
        log.info("Loading bot extensions...")
        for filename in os.listdir(path):
            if filename.startswith("_") or os.path.isdir(filename):
                continue
            if filename.endswith(".py"):
                try:
                    # Must use dot notation and exclude .py extension
                    await self.load_extension(f".cogs.{filename.removesuffix('.py')}",
                                              package=__package__)
                except commands.ExtensionError:
                    log.critical(f"FAILED to load {filename} as bot extension")
                # else:
                #     log.info(f"Loaded {filename} as bot extension")
        log.info("Finished loading bot extensions")


def main() -> None:
    bot = TacoBot()
    token = TESTER_TOKEN if TESTER_MODE else TACOBOT_TOKEN
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
