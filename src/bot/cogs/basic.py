"""Implements commands in the "Basic" category."""

import logging
from typing import Optional

import discord
from discord.ext import commands

from .. import __version__, helper

log = logging.getLogger(__name__)

##### COG DEFINITION #####


class Basic(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    ### COMMANDS ###

    @commands.command(name="ping", help="Checks if bot is alive")
    async def ping(self, ctx) -> None:
        outstr = f"**[{__version__}]** Yes, I'm here! Bot latency: **{round(self.bot.latency*1000)}** ms"
        await ctx.send(outstr)

    @commands.command(name="version", aliases=["v"],
                      help="Displays version of running script")
    async def version(self, ctx) -> None:
        await ctx.send(f"Script version: **{__version__}**")

    @commands.command(name="say", aliases=["echo"], help="Echoes what you say")
    async def say(self, ctx, *, content: Optional[str] = None) -> None:
        # Attempt to delete user's message
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            log.warning(
                f"Couldn't delete user message in #{ctx.channel}, {ctx.guild}")
        if content is not None:
            await ctx.send(content)

    @commands.command(name="cleandm", aliases=["purgedm"],
                      help="Deletes bot messages from your DM")
    async def cleandm(self, ctx, num_messages: int = 1) -> None:
        """Makes bot delete up to 100 of its own messages in DM with user."""

        # Limit to deleting 1 to 100 messages at a time
        num_messages = max(min(num_messages, 100), 1)

        # Get or create and get DM channel of caller
        channel = ctx.author.dm_channel or await ctx.author.create_dm()

        log.info(
            f"Deleting up to {num_messages} message(s) from DM channel of {channel.recipient}...")

        num_deleted = 0
        # DMChannel has no method purge()
        async for message in channel.history():

            if num_messages == 0:
                break
            if message.author != self.bot.user:
                continue

            try:
                await message.delete()
                num_messages -= 1
                num_deleted += 1
            except (discord.NotFound, discord.HTTPException):
                continue

        log.info(
            f"Deleted {num_deleted} message(s) from DM channel of {channel.recipient}")
        await ctx.message.add_reaction("✅")

    @commands.command(
        name="updatenotes", aliases=["updatenote"],
        help="Displays update notes for current script version")
    async def updatenotes(self, ctx) -> None:
        with open("../README.txt", "rt", encoding="utf-8") as file:
            content = file.read()

        # Match "[vX.X.X]" header up until end of file
        pattern = r"(?is)\[" + __version__ + r".*\].*$"
        match = helper.re.search(pattern, content)
        if match is None:
            await ctx.send(f"No update notes found for **{__version__}**!")
            return

        span = slice(*match.span())
        content = content[span].rstrip("\n")

        # Formatting
        lines = []
        for line in content.splitlines():
            if line == "" or line.isspace():
                f_line = ""
            elif line.startswith("["):
                f_line = line
            elif line.startswith("\t"):
                f_line = "\t⮩ " + line.removeprefix("\t")
            else:
                f_line = f"• {line}"
            lines.append(f_line)
        outstr = "\n".join(lines)
        outstr = f"```{outstr}```"

        out_msg = await ctx.send(outstr)
        await helper.reactremove(self.bot, out_msg)


async def setup(bot: commands.Bot) -> None:
    """Required for bot to load the cog as an extension."""
    await bot.add_cog(Basic(bot))
