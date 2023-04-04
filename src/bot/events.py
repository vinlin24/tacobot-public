
"""Registers event listeners for the bot."""


import logging

import discord
from discord.ext import commands

from . import (AWS_ACCESS_KEY, AWS_SECRET_KEY, ON_HEROKU, TESTER_MODE,
               __version__, amazons3, helper)

log = logging.getLogger(__name__)

##### HELPER FUNCTIONS #####


async def load_s3(bot: commands.Bot) -> None:
    """
    Creates S3 handler, binds it to bot, and ensures existence of directories.
    Precondition: bot has AWS_ACCESS_KEY and AWS_SECRET_KEY attrs.
    Precondition: bot is logged in; called in on_connect() event.
    Postcondition: bot has attr "s3_client".
    """
    bot.s3_client = amazons3.S3Client(AWS_ACCESS_KEY, AWS_SECRET_KEY)
    log.info("Binded S3Client object to bot")

    log.info("Initializing AWS S3 directories...")
    for guild in bot.guilds:
        await bot.s3_client.create_folder("tacobot", f"guilds/{guild.id}/")
    await bot.s3_client.create_folder("tacobot", "users/")
    log.info("Finished initializing AWS S3 directories")

##### EVENT REGISTRATION #####


def register_events(bot: commands.Bot) -> None:
    """To be called from main.py."""

    @bot.event
    async def on_connect() -> None:

        await load_s3(bot)

        # Load and set activity
        log.info("Attempting to load presence from last session...")
        if await bot.s3_client.download("activity.txt", "tacobot", "bot/files/activity.txt"):
            with open("bot/files/activity.txt", "rt") as file:
                saved_activity = file.read()

            activity = None if saved_activity == "" else discord.Game(
                saved_activity)
            await bot.change_presence(activity=activity)
            log.info(
                "Cleared bot activity"
                if activity is None else
                f"Changed bot activity to: '{saved_activity}'")

    @bot.event
    async def on_ready() -> None:
        prefix = "<TESTER MODE> " if TESTER_MODE else ""
        if ON_HEROKU:
            log.info(f"{prefix}Loaded script {__version__} on Heroku!")
            await helper.sendvin(bot, f"Running script **{__version__}** on Heroku!", "HEROKU UPDATE")
        else:
            log.info(
                f"{prefix}Loaded script {__version__} from local machine!")

    @bot.event
    async def on_disconnect() -> None:
        log.warning(f"Bot disconnected")

    @bot.event
    async def on_resumed() -> None:
        log.info("Bot reconnected")

    @bot.event
    async def on_message(message: discord.Message) -> None:

        # Ignore commands in messages in REPL sessions
        try:
            if (message.author.id, message.channel.id) in bot.repl_sessions:
                return
        except KeyError:
            pass

        # Necessary when overriding on_message to not silence commands
        await bot.process_commands(message)

    # @bot.event
    # async def on_command_error(ctx, error: Exception) -> None:

    #     # Ignore unknown commands
    #     if isinstance(error, commands.CommandNotFound):
    #         return

    #     if isinstance(error, commands.CheckFailure):
    #         log.info(f"({ctx.author}, %{ctx.command.name}) Failed to use this command")
    #         await ctx.send(f"⛔ **{ctx.author.name}**, you do not have the power to use `%{ctx.command.name}`")
    #         return

    #     if isinstance(error, commands.UserInputError):
    #         log.info(f"({ctx.author}, %{ctx.command.name}) User input error: {error}")
    #         return

    #     if isinstance(error, commands.CommandInvokeError):
    #         original = error.original # discord.xxx exception type
    #         log.error(f"({ctx.author}, %{ctx.command.name}) {original.__class__.__name__}: {original}")

    #         if isinstance(original, discord.HTTPException):
    #             # "Invalid Form Body" - content is too long
    #             if original.code == 50035:
    #                 await ctx.send(f"⚠ **{ctx.author.name}**, I couldn't send the requested message because its content was too long!")
    #                 log.warning(f"({ctx.author}, %{ctx.command.name}) Attempted to send message that exceeds character limit")

    #         return

    #     # Logger will already specify "on_command_error", so this part is redundant
    #     error_str = str(error).replace("Command raised an exception: ", "")
    #     log.error(f"({ctx.author}, %{ctx.command.name}) {error_str}")

    @bot.event
    async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        """pass"""
