import json
import logging
import re
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from .. import helper

log = logging.getLogger(__name__)

##### COG DEFINITION #####


class Mudae(commands.Cog):

    ### INIT ###

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # Reference: Discord mention regex raw str is r"<@!?(\d+)>"
        # where the capturing group is the user ID

        self.claimed_finder = re.compile(
            r"claimed:\*\* (\d+)/")
        self.me_response_finder = re.compile(
            r"<@!?(\d+)>, type the name\(s\) of the character\(s\) you want to trade against .+")
        self.me_confirm_finder = re.compile(
            r"<@!?(\d+)>, (.+) vs (.+)\. Do you confirm the exchange\? \(y/n/yes/no\)")

        self.datetime_fmts = self.datetime_formats()

    def datetime_formats(self) -> list[str]:
        # A lotta possible formats (at least month and day are required)
        formats = ["%m/%d", "%m/%d", "%m-%d",
                   "%m-%d", "%b %d", "%d %b %y", "%d %b"]
        for fmt in formats.copy():
            formats.extend(
                (fmt + "/%Y", fmt + "/%y", fmt + "-%Y", fmt + "-%y", fmt + " %Y",
                 fmt + " %y", fmt + ", %Y", fmt + ", %y"))
        for fmt in formats.copy():
            formats.extend((fmt + " %H", fmt + " %H:%M", fmt + " %H:%M:%S"))
        return formats

    ### HELPER METHODS ###

    def chars_claimed(self, message: discord.Message) -> Optional[int]:
        """
        Parse message and see if it is Mudae's response message to the $left command.
        If it is, return the number characters claimed in that server.
        If not, return None.
        """
        if message.author.id == helper.MUDAE_ID:
            match = self.claimed_finder.search(message.content)
            # Not a $left message
            if match is None:
                return None
            group = match.group(1)
            return int(group)

        return None

    async def update_json(self, guild_id: int, num_claimed: int) -> None:
        """Update mudae_data.json on AWS S3."""

        # Update mudae_data.json locally
        with open("bot/files/mudae_data.json", "rt+") as file:
            data = json.load(file)  # dict[str, int]: the guild ID is a str!
            data["CHARS_CLAIMED"][str(guild_id)] = num_claimed
            # Overwrite everything
            file.seek(0)
            file.truncate(0)
            json.dump(data, file, indent=4)

        # Upload local file to AWS S3
        await self.bot.s3_client.upload(
            "bot/files/mudae_data.json", "tacobot", "mudae_data.json")

    async def get_exchange_dets(self, message: discord.Message) -> Optional[tuple[discord.Member, str, discord.Member, str, discord.Message]]:
        """
        Parse history before message to find the participants in the $marryexchange.
        Return a 5-tuple:
        (initiator, initiator charnames, other, other charnames, original param message).
        If history parsing failed, return None.
        """
        # module/attr -> local
        MUDAE_ID = helper.MUDAE_ID
        me_confirm_finder = self.me_confirm_finder
        me_response_finder = self.me_response_finder

        response_match = None
        confirm_match = None
        # Realistically, trade should've timed out before limit is reached
        async for older_msg in message.channel.history(limit=50, before=message.created_at):
            if older_msg.author.id != MUDAE_ID:
                continue

            if confirm_match is None:
                # @initiator, <names> vs <names> Do you confirm the exchange?...
                match = me_confirm_finder.fullmatch(older_msg.content)
                if match is not None:
                    confirm_match = match
                    continue

            elif response_match is None:
                # @other, type the name of the character(s)...
                match = me_response_finder.fullmatch(older_msg.content)
                if match is not None:
                    response_match = match
                    continue

            # Both response_match and confirm_match found
            else:
                break
        # No-break: one of response_match and confirm_match not found
        else:
            log.warning(
                f"get_exchange_dets() failed to parse history of #{message.channel}")
            return None

        other_id, = response_match.groups()  # <!> 1-tuple
        initiator_id, initiator_chars, other_chars = confirm_match.groups()

        initiator = await message.guild.fetch_member(initiator_id)
        other = await message.guild.fetch_member(other_id)

        return (initiator, initiator_chars.strip(), other, other_chars.strip(), message)

    ### EVENT LISTENERS ###

    @commands.Cog.listener(name="on_message")
    async def on_message(self, message: discord.Message) -> None:

        # Update number of total claimed characters when it detects a $left message
        num_claimed = self.chars_claimed(message)
        if num_claimed is not None:
            log.info(
                f"$left message detected in #{message.channel}: updating mudae_data.json")
            await self.update_json(message.guild.id, num_claimed)

    ### COMMANDS ###

    @commands.command(
        name="kakeravalue", aliases=["kv"],
        help="Calculates the kakera value of Mudae character")
    async def kakeravalue(self, ctx,
                          claim_rank: int, like_rank: int, chars_claimed: Optional[int] = None, keys: int = 0) -> None:

        def key_multiplier(keys: int) -> float:
            """The part of the formula that depends on the number of keys unlocked."""
            if keys < 1:
                return 1.0
            if 1 <= keys < 3:
                return 1.0 + 0.1*(keys-1)
            if 3 <= keys < 6:
                return 1.1 + 0.1*(keys-3)
            if 6 <= keys < 10:
                return 1.3 + 0.1*(keys-6)
            return 1.6 + 0.05*(keys-10)

        # Handle no arg given for chars_claimed: use last updated value from $left
        if chars_claimed is None:

            # Download from AWS to local file
            await self.bot.s3_client.download(
                "mudae_data.json", "tacobot", "bot/files/mudae_data.json")
            # Load from local file
            with open("bot/files/mudae_data.json", "rt") as file:
                data = json.load(file)

            try:
                chars_claimed = data["CHARS_CLAIMED"][str(ctx.guild.id)]
            # No data for this guild yet: default to 0
            except KeyError:
                chars_claimed = 0

        # Abbreviate
        rc = claim_rank
        rl = like_rank
        cc = chars_claimed
        k = keys

        # Base value formula
        base_value = int((25000*((rc+rl)/2+70)**-0.75+20)*(1+cc/5500)+0.5)

        # Accounting for keys
        kakera_value = int(base_value * key_multiplier(keys) + 0.5)

        outstr = f"The kakera value of this character would be: **{kakera_value}** ka\n"
        outstr += f"> Claim rank: **#{rc}**\n> Like rank: **#{rl}**\n"
        outstr += f"> Total characters claimed: **{cc}**\n> Keys unlocked: **{k}**"

        await ctx.send(outstr)

    @commands.command(
        name="exchanges", aliases=["trades"],
        help="Parses channel history and displays most recent $marryexchange's")
    async def exchanges(self, ctx, num_messages: int = 100, *, before: Optional[str] = None) -> None:
        # Handle args

        # Restrict parsing to 1 to 1000 messages, inclusive
        num_messages = max(1, min(1000, num_messages))

        # Attempt to convert param before to a datetime object
        if before is not None:
            for fmt in self.datetime_fmts:
                try:
                    before = datetime.strptime(before, fmt)
                    # Year wasn't given or before Discord epoch:
                    if before.year < 2015:
                        before = before.replace(year=datetime.now().year)
                    log.info(f"Converted param before to datetime: {before}")
                    break
                except (ValueError, re.error):
                    continue
            # Parsing failed: default to None
            else:
                log.warning(
                    f"Failed to convert '{before}' to a datetime object")
                before = None

        async with ctx.typing():

            # list[tuple]: 5-tuples with typing described in get_exchange_dets()
            payloads = []

            # module/attr -> local
            MUDAE_ID = helper.MUDAE_ID
            get_exchange_dets = self.get_exchange_dets

            # Skip overx rolls
            def check(m): return m.author.id == MUDAE_ID and len(m.embeds) == 0

            search_start = datetime.now()
            async for message in ctx.history(limit=num_messages, before=before).filter(check):

                # Only parse for exchanges that actually went through
                if "The exchange is over" in message.content:
                    payload = await get_exchange_dets(message)
                    if payload is not None:
                        payloads.append(payload)

            search_end = datetime.now()
            search_dur = (search_end-search_start).total_seconds()

            # Format output embed
            entries = []
            for exchange in payloads:
                initiator, initchars, other, otherchars, message = exchange
                dt_str = message.created_at.strftime("%b %d, %Y %H:%M:%S UTC")
                link = f"[{dt_str}]({message.jump_url})"
                entry = f"{link}\n{initiator.mention}: {initchars} ↔ {otherchars} :{other.mention}"
                entries.append(entry)

            body = "\n".join(entries)
            if body == "":
                body = "No `$marryexchange`s found!"

            header = f"Searched **{num_messages}** messages in {ctx.channel.mention}"
            if before is None:
                header += "\n Searched **most recent** messages in channel | Most recent first:"
            else:
                header += f"\nSearched before: **{before.strftime('%b %d, %Y %H:%M:%S UTC')}** | Most recent first:"
            desc = f"{header}\n\n{body}"
            title = f"Mudae $marryexchange History"
            embed = helper.make_embed(desc, title, "dark_blue")
            embed.set_footer(text=f"Completed search in {search_dur:.3f}s")

        await ctx.send(embed=embed)

    @commands.command(name="claims",
                      help="Parses channel history and displays most recent claims")
    async def claims(self, ctx) -> None:
        await ctx.send("Command coming soon!")


async def setup(bot: commands.Bot) -> None:
    """Required for bot to load the cog as an extension."""
    await bot.add_cog(Mudae(bot))
