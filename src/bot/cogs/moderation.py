import logging

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

##### COG DEFINITION #####


class Moderation(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    ### COMMANDS ###
    @commands.command(name="clean", aliases=["delete", "purge"],
                      help="(ADMIN) Purges messages from text channel")
    @commands.has_permissions(administrator=True)
    async def clean(self, ctx, num_messages: int = 1) -> None:
        # Limit to deleting 0 (deleting only the command msg itself) to 100 messages at a time
        num_messages = max(min(num_messages, 100), 0)
        try:
            # +1 to account for the command itself
            await ctx.channel.purge(limit=num_messages+1)
        except discord.Forbidden:
            log.error(
                f"Bot does not have permission to use purge() in #{ctx.channel}")
        else:
            log.info(
                f"{ctx.message.author} cleaned {num_messages} message(s) in #{ctx.channel}")


async def setup(bot: commands.Bot) -> None:
    """Required for bot to load the cog as an extension."""
    await bot.add_cog(Moderation(bot))
