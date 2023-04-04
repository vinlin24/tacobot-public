import logging
from pprint import pformat

import discord
from discord.ext import commands

from .. import ON_HEROKU, helper

log = logging.getLogger(__name__)

##### COG DEFINITION #####


class Maintenance(commands.Cog):

    ### INIT ###

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_check(self, ctx) -> bool:
        """
        Defines a global check for commands of this cog.
        Commands in this cog are "god commands" - exclusive to script writer.
        """
        return ctx.author.id in (helper.VIN_ID, helper.BORG_ID)

    ### COMMANDS ###

    @commands.command(name="mentionvin", hidden=True)
    async def mentionvin(self, ctx, *, content: str = "") -> None:
        """Helper command for mentioning me."""
        vin = self.bot.get_user(helper.VIN_ID)
        await ctx.send(f"{vin.mention} {content}")

    @commands.command(name="setactivity", aliases=["sa"], hidden=True)
    async def setactivity(self, ctx, *, name: str = None) -> None:
        """Sets the activity in bot presence and updates activity.txt."""
        activity = None if name is None else discord.Game(name)

        await self.bot.change_presence(activity=activity)
        await ctx.message.add_reaction("✅")
        log.info("Reset bot presence"
                 if activity is None else
                 f"Changed bot activity to: '{activity}'")

        # Save to file and update on AWS S3
        with open("bot/files/activity.txt", "wt") as file:
            file.write("" if name is None else name)
        await self.bot.s3_client.upload("bot/files/activity.txt", "tacobot", "activity.txt")

    @commands.command(
        name="scripteval", aliases=["seval", "scriptvar", "svar"],
        hidden=True)
    async def scripteval(self, ctx, *, expression: str) -> None:
        """Runs eval() on expression. Has access to script variables."""
        namespace = {"bot": self.bot, "helper": helper}
        try:
            # Check if expression is attempting to do something asynchronous
            if expression.startswith("await "):
                result = await eval(expression.removeprefix("await "), namespace)
            else:
                result = eval(expression, namespace)
        except Exception as E:
            await ctx.send(f"⚠ Error in `eval()`ing expression:```{E.__class__.__name__}: {E}```")
            return

        # Prevent display of sensitive values
        if any(key in str(result) for key in helper.SENSITIVE_KEYS):
            await ctx.message.add_reaction("⛔")
            return

        outstr = f"```{pformat(result)}```"
        await ctx.send(outstr)

    @commands.command(
        name="playereval", aliases=["peval", "playervar", "pvar"],
        hidden=True)
    async def playereval(self, ctx, *, expression: str) -> None:
        """
        Similar to %scripteval but with acceess to namespace of guild-specific MusicPlayer.
        expression should be what would be written within the MusicPlayer class; example:
        "self.pos" retrieves the pos attribute of the player.
        """
        try:
            player = self.bot.cogs["Music"].players[ctx.guild.id]
        except KeyError:
            await ctx.send(f"MusicPlayer does not exist for guild {ctx.guild} yet")
            return

        namespace = {"bot": self.bot, "helper": helper, "self": player}

        try:
            # Check if expression is attempting to do something asynchronous
            if expression.startswith("await "):
                result = await eval(expression.removeprefix("await "), namespace)
            else:
                result = eval(expression, namespace)
        except Exception as E:
            await ctx.send(f"⚠ Error in `eval()`ing expression:```{E.__class__.__name__}: {E}```")
            return

        # Prevent display of sensitive values
        if any(key in str(result) for key in helper.SENSITIVE_KEYS):
            await ctx.message.add_reaction("⛔")
            return

        outstr = f"```{pformat(result)}```"
        await ctx.send(outstr)

    @commands.command(name="restart", aliases=["reset", "reboot"], hidden=True)
    async def restart(self, ctx) -> None:
        """
        Log the bot out, crashing the program and causing Heroku to automatically
        restart the script.
        Ignore the command if script is not running on Heroku.
        """
        if ON_HEROKU:
            warning_msg = "⚠ Heroku will automatically **restart** the script. Proceed? (y/n/yes/no)"
            timeout_msg = "⌛ Time's up. Bot is staying online."
            decline_msg = "🖐 Gotcha. Bot is staying online."

            response = await helper.ask_for_confirmation(ctx,
                                                         warning_msg=warning_msg,
                                                         timeout_msg=timeout_msg,
                                                         decline_msg=decline_msg)

            if response is not True:
                return

            embed = helper.make_embed(
                "☁ Restarting script running on Heroku...",
                color="dark_red")
            await ctx.send(embed=embed)

            log.info(f"Restart call made by {ctx.author}")
            await self.bot.close()  # Raises a bunch of errors out of my control

    @commands.command(
        name="abort", aliases=["shutdown", "logout"],
        hidden=True)
    async def abort(self, ctx) -> None:
        """
        Log the bot out.  Ignore the command if script is running on Heroku.
        This way, %abort can be used to only abort scripts running locally, and
        %restart can be used to only abort scripts running on Heroku.
        """
        if not ON_HEROKU:

            embed = helper.make_embed(
                "💻 Aborting script running on local machine...",
                color="dark_red")
            await ctx.send(embed=embed)

            log.info(f"Abort call made by {ctx.author}")
            await self.bot.close()  # Raises a bunch of errors out of my control


async def setup(bot: commands.Bot) -> None:
    """Required for bot to load the cog as an extension."""
    await bot.add_cog(Maintenance(bot))
