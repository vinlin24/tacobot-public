"""Some useful constants and helper functions for the program."""

import asyncio
import logging
import math
import os
import re
import sys
import time
from datetime import date, datetime, time, timedelta, timezone
from functools import partial
# Not used here but to be available for commands using eval()
from pprint import pformat, pprint
from random import random, randrange
from typing import Callable, NoReturn, Optional, Union

import discord
from discord.ext import commands
from PIL.Image import Image

from . import (AWS_ACCESS_KEY, AWS_SECRET_KEY, CURRENCYSCOOP_KEY,
               TACOBOT_TOKEN, TESTER_TOKEN)
from .names import BORG_ID, LH_ID, MUDAE_ID, REAL_NAMES, TSC_ID, VIN_ID

log = logging.getLogger(__name__)

##### GLOBAL CONSTANTS #####

SENSITIVE_KEYS = (
    TACOBOT_TOKEN,
    TESTER_TOKEN,
    AWS_ACCESS_KEY,
    AWS_SECRET_KEY,
    CURRENCYSCOOP_KEY,
)

REACTREMOVE_TIMEOUT = 180

ANNOY_MESSAGES = \
    (
        "Lol!",
        "You're like really weird and stuff!",
        "That's mad!",
        "Yeah {name}?",
        "Please be quiet.",
        "Say one more thing and I'll slap you.",
        "Tell me more!",
        "Are you like really dumb and stuff?",
        "Ohhh {name}~~~",
        "I don't like you {name}.",
        "Keep talking, I dare you.",
        "{name}, you have to understand that no one likes you.",
        "( ͡° ͜ʖ ͡°)",
        "Let's be best friends!",
        "{name}, you are my favorite person.",
        "Duhgee.",
        "Truly {name}, truly.",
        "I guess so man I guess so.",
        "Wooord.",
    )

TRAGEDY = "Did you ever hear the tragedy of Darth Plagueis the Wise? I thought not. It's not a story the Jedi would tell you. It's a Sith legend. Darth Plagueis was a Dark Lord of the Sith, so powerful and so wise he could use the Force to influence the midichlorians to create life... He had such a knowledge of the dark side that he could even keep the ones he cared about from dying. The dark side of the Force is a pathway to many abilities some consider to be unnatural. He became so powerful... the only thing he was afraid of was losing his power, which eventually, of course, he did. Unfortunately, he taught his apprentice everything he knew, then his apprentice killed him in his sleep. Ironic, he could save others from death, but not himself."

##### FUNCTIONS #####


async def sendvin(bot: commands.Bot, content: str, header: Optional[str] = None) -> None:
    """Sends message with content and bolded header to vin."""
    vin = bot.get_user(VIN_ID)

    if header is not None:
        outstr = f"**{header}**\n"
    else:
        outstr = ""
    outstr += content

    try:
        await vin.dm_channel.send(outstr)
    # dm_channel is None -> create DM channel
    except AttributeError:
        dm_channel = await vin.create_dm()
        await dm_channel.send(outstr)

    log.info("Sent message to vin dm_channel")


async def reactremove(bot: commands.Bot, message: discord.Message, delete_emoji: str = "🗑",
                      timeout: Optional[float] = None, member: Optional[discord.Member] = None) -> bool:
    """
    Helper function for removing messages on reaction.
    If param timeout is None, the bot will not stop listening.
    Returns True if the message was removed due to a reaction, False otherwise
    (timed out or already deleted).
    """
    # Handle default/bad arg
    if not timeout:  # timeout is None or 0
        timeout = REACTREMOVE_TIMEOUT
    else:
        timeout = abs(timeout)

    # If param member is None, any member can delete the message with reaction
    def check_emoji(reaction: discord.Reaction, user: discord.User) -> bool:
        return not user.bot and \
            str(reaction) == delete_emoji and \
            (member is None or member == user) and \
            reaction.message == message

    await message.add_reaction(delete_emoji)

    try:
        await bot.wait_for("reaction_add", check=check_emoji, timeout=timeout)
        await message.delete()
        log.info(
            f"Deleted message on reaction in #{message.channel}, {message.guild}")
        return True
    # Timed out
    except asyncio.TimeoutError:
        log.info(
            f"Message delete option timed out for message: {message.jump_url}")
        return False
    # message already deleted by other means
    except discord.NotFound:
        return False


async def ask_for_confirmation(ctx,
                               warning_msg: str,
                               timeout_msg: str,
                               decline_msg: str,
                               timeout: float = 10) -> Optional[bool]:
    """
    Abstract the process of asking for confirmation from a user:
    1) Send embed with description=warning, prompting user to respond with y/n/yes/no.
    2) Wait for appropriate message for timeout seconds.
    2a) If user responds with n/no in time, send embed with description=decline_msg.
    2b) If user responds with y/yes in time, pass.
    2c) If user fails to respond in time, send embed with description=timeout_msg.
    3) Return value and edit the embed footer to reflect response.

    Return value based on user response:
    True if the user responded with y/yes.
    False if the user responded with n/no.
    None if the user failed to respond with y/n/yes/no within timeout seconds.
    """
    def confirm_check(message: discord.Message) -> Union[bool, NoReturn]:
        """
        Check to pass into bot.wait_for().
        Return True if y/yes detected, raise ValueError if n/no detected.
        Return False otherwise.
        """
        if message.author != ctx.author or message.channel != ctx.channel:
            return False
        if message.content.lower() in ("y", "yes"):
            return True
        if message.content.lower() in ("n", "no"):
            raise ValueError("confirmation canceled in confirm_check")
        return False

    retval = None   # Optional[bool]

    # Initial warning, prompting user to type y/n/yes/no
    embed = make_embed(warning_msg, color="orange")
    out_msg = await ctx.send(embed=embed)

    try:
        await ctx.bot.wait_for("message", check=confirm_check, timeout=timeout)

    # User ran out of time to respond
    except asyncio.TimeoutError:
        await ctx.send(embed=make_embed(timeout_msg, color="orange"))
        retval = None

    # User declined (n/no)
    except ValueError:
        await ctx.send(embed=make_embed(decline_msg, color="orange"))
        retval = False

    # User confirmed (y/yes)
    else:
        retval = True

    finally:
        footer_text = ctx.author.name
        if retval is True:
            footer_text += " responded with yes ✅"
        elif retval is False:
            footer_text += " responded with no ❌"
        else:
            footer_text += " did not respond in time ⌛"

        embed.set_footer(text=footer_text)
        await out_msg.edit(embed=embed)

        return retval


def make_embed(
        description: Optional[str] = None, title: Optional[str] = None,
        color: str = "gold") -> discord.Embed:
    """Shortcut for creating discord Embeds.  Color defaults to gold."""
    try:
        discord_color = eval(f"discord.Color.{color}()")
    # Invalid color name, resort to default
    except AttributeError:
        log.warning(f"Invalid color name '{color}' passed into make_embed()")
        discord_color = "gold"

    embed = discord.Embed(color=discord_color,
                          title=title or "", description=description or "")
    return embed


def has_humans(channel: discord.VoiceChannel) -> bool:
    """Return whether channel currently has nonzero bots connected to it."""
    return any(not member.bot for member in channel.members)


def get_annoy_message() -> str:
    rand_num = randrange(len(ANNOY_MESSAGES))
    return ANNOY_MESSAGES[rand_num]


def realname(user_id: int) -> Optional[str]:
    try:
        return REAL_NAMES[user_id]
    except KeyError:
        return None


def get_mention(bot: commands.Bot, text: str) -> Optional[discord.User]:
    """
    Return the User object of the first mention in text.
    Return None if no mentions found in text.
    """
    pattern = r"<@!?(\d+)>"
    match = re.search(pattern, text)
    if match is None:
        return None
    uid = int(match.group(1))
    return bot.get_user(uid)


def to_hexcode(red: int, green: int, blue: int) -> str:
    """Return the color code '#RRGGBB' given RGB values."""
    return "#" + "".join(hex(val).removeprefix("0x").rjust(2, "0")
                         for val in (red, green, blue))


def rms_rgb(image: Image) -> Optional[tuple[int, int, int]]:
    """
    Calculate and returns the root mean squared RGB of param Image image.
    Return None if image is a GIF (unsupported format).
    """
    pixels = image.load()  # PixelAccess object
    width, height = image.size

    total_redsq = 0
    total_greensq = 0
    total_bluesq = 0

    for y in range(height):
        for x in range(width):
            pv = pixels[x, y]  # pixel value of pixel(x,y)
            try:
                total_redsq += pv[0]**2
                total_greensq += pv[1]**2
                total_bluesq += pv[2]**2
            # Ex: for some reason, pv is type int when image is a GIF
            except TypeError:
                return None

    num_pixels = width * height
    rms_red = math.sqrt(total_redsq / num_pixels)
    rms_green = math.sqrt(total_greensq / num_pixels)
    rms_blue = math.sqrt(total_bluesq / num_pixels)

    rmsrgb = (round(rms_red), round(rms_green), round(rms_blue))

    return rmsrgb

##### TESTING SPACE #####


def main() -> None:
    pass


if __name__ == "__main__":
    main()
