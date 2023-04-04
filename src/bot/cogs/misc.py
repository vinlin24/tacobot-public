import logging
from typing import Optional

import discord
from discord.ext import commands

from .. import helper

log = logging.getLogger(__name__)

##### COG DEFINITION #####


class Misc(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # dict[int, Optional[discord.Member]]: maps guild ID to annoy target
        self.annoy_targets = {}

    ### EVENT LISTENERS ###

    @commands.Cog.listener(name="on_message")
    async def on_message(self, message: discord.Message) -> None:
        """Cog-specific handler for on_message event."""
        # For %annoy
        try:
            target = self.annoy_targets[message.guild.id]
        # Key for guild not initialized yet, or guild is None (DM)
        except (KeyError, AttributeError):
            pass
        else:
            if target == message.author:
                realname = helper.realname(message.author.id)
                if realname is None:
                    realname = "Bro"
                text = helper.get_annoy_message().format(name=realname)
                await message.channel.send(text)

    ### COMMANDS ###

    @commands.command(name="annoy", help="Sets target for constant replying")
    async def annoy(self, ctx, *, member: Optional[discord.Member] = None) -> None:

        try:
            target = self.annoy_targets[ctx.guild.id]
        except KeyError:
            target = None

        # Called without args -> reset annoy_target to None
        if member is None:
            self.annoy_targets[ctx.guild.id] = None
            log.info(f"No longer annoying anybody in {ctx.guild}")
            await ctx.send("Fine, I'll stop.")

        # Attempt to annoy bot itself
        elif member.id == self.bot.user.id:
            await ctx.send(f"Nice try! Nothing happened!")

        elif target is None:
            self.annoy_targets[ctx.guild.id] = member
            log.info(f"Now annoying {member} in {ctx.guild}")
            await ctx.send(f"Now annoying **{member.name}**!")

        # Annoy one user at a time: switch to annoying param member
        else:
            await ctx.send(f"No longer annoying **{target.name}**.")
            if member is target:
                self.annoy_targets[ctx.guild.id] = None
            else:
                self.annoy_targets[ctx.guild.id] = member
            log.info(f"Now annoying {member} in {ctx.guild}")
            await ctx.send(f"Now annoying **{member.name}**!")

    @commands.command(name="tragedy",
                      help="Educates you on the tragedy of Darth Plagueis the Wise")
    async def tragedy(self, ctx) -> None:
        await ctx.send(helper.TRAGEDY)


async def setup(bot: commands.Bot) -> None:
    """Required for bot to load the cog as an extension."""
    await bot.add_cog(Misc(bot))
