import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, NoReturn, Optional, Union

import discord
import requests
from discord.ext import commands
from PIL import Image
from requests.exceptions import MissingSchema

from .. import CURRENCYSCOOP_KEY, helper
from .classes.exchanger import Exchanger

log = logging.getLogger(__name__)

##### COG DEFINITION #####


class Utils(commands.Cog):

    ### CLASS CONSTANTS ###

    # For eval_()
    NAMESPACE = \
        {
            "pformat": helper.pformat,
            "math": helper.math,
            "random": helper.random,
            "randrange": helper.randrange,
            "datetime": helper.datetime,
            "date": helper.date,
            "time": helper.time,
            "timedelta": helper.timedelta,
            "timezone": helper.timezone,
            "time": helper.time,
            "re": helper.re,
        }

    # For currency()
    UPDATE_AFTER = timedelta(days=1)

    ### INIT ###

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # For repl()
        self.text_to_print = None
        # list[tuple[int, int]]: list of (user ID, channel ID)
        self.bot.repl_sessions = []

        # For eval_(): Redirect call to not display text to log
        self.NAMESPACE.update({"print": self.printer, "pprint": self.pprinter})

        # For anagrams()
        with open("bot/files/words.txt", "rt") as file:
            self.WORDS = file.read().splitlines()

        # For currency()
        self.exchanger = Exchanger(
            CURRENCYSCOOP_KEY, "bot/files/exchange_rates.json")

    def printer(
            self, *args: Any, sep: str = " ", end: str = "\n", file=None,
            flush: bool = False) -> None:
        """Wrapper function for making print() work in %repl.

        Keyword params file and flush are there to mirror the real print(), but do not actually
        do anything as they are not applicable here.
        """
        outstr = sep.join(str(obj) for obj in args) + end
        self.text_to_print = outstr

    def pprinter(
            self, obj: Any, stream=None, indent: int = 1, width: int = 80,
            depth: Optional[int] = None, *, compact: bool = False,
            sort_dicts: bool = True) -> None:
        """Wrapper function for making pprint() work in %repl.

        Param stream is there to mirror the real pprint(), but does not actually do anything as
        it is not applicable here.
        """
        self.text_to_print = helper.pformat(
            obj, indent, width, depth, compact=compact, sort_dicts=sort_dicts)

    ### HELPER METHODS ###

    def evaluate(self, expression: str, namespace: dict[str, Any]) -> Union[Any, NoReturn]:
        """
        Run eval() on expression, returning what should be displayed for %repl.
        If user tries something that is illegal in eval(), such as assigning variables, raise
        SyntaxError so repl() knows to handle expression with exec() instead.
        Update namespace and self.text_to_print appropriately.
        """
        try:
            result = eval(expression, namespace)
        except SyntaxError:
            raise SyntaxError from None
        except Exception as E:
            return f"{E.__class__.__name__}: {E}"

        # Prevent display of sensitive values
        if any(key in str(result) for key in helper.SENSITIVE_KEYS):
            return "⛔ Your code attempted to display a sensitive value(s)!"

        return result

    def execute(
            self, expression: str, namespace: dict[str, Any]) -> Optional[str]:
        """
        Run exec() on expression, returning an error message if applicable.
        Update namespace and self.text_to_print appropriately, including preventing the
        inclusion of the dangerous os and sys modules, and redefining pprint.pprint to custom
        wrapper method.
        """
        try:
            exec(expression, namespace)
        except Exception as E:
            return f"{E.__class__.__name__}: {E}"

        # namespace import checks:
        #    Make sure pprint gets redefined if it gets imported
        #    Prevent usage of os module (to prevent chdir, which can mess up file handling)
        for key, val in namespace.items():
            if val == helper.pprint:
                namespace[key] = self.pprinter
            elif val == helper.os:
                del namespace[key]
                return "⛔ You are not allowed to use the os module"
            elif val == helper.sys:
                del namespace[key]
                return "⛔ You are not allowed to use the sys module"

        return None

    def get_anagrams(self, letters: str) -> dict[int, list[str]]:
        """Return a dict that maps word len to valid anagrams of letters with that len."""
        letters = letters.lower()
        letters_count = Counter(letters)
        anagrams = set()
        for word in self.WORDS:
            original = word
            word = word.lower()
            if not set(word) - set(letters):
                check_word = set()
                for k, v in Counter(word).items():
                    if v <= letters_count[k]:
                        check_word.add(k)
                if check_word == set(word):
                    anagrams.add(original)

        dct = {}
        for item in anagrams:
            length = len(item)
            if length in dct:
                dct[length].append(item)
            else:
                dct[length] = [item]

        # Return the dict ordered by key (1, 2, 3, ...) and with each list alphabetized
        return {key: sorted(dct[key]) for key in sorted(dct.keys())}

    ### COMMANDS ###

    @commands.command(name="eval", aliases=["pythoneval"],
                      help="Runs Python's eval() on expression")
    async def eval_(self, ctx, *, expression: str) -> None:
        # Echo input
        instr = f">>> {expression}"

        try:
            result = repr(eval(expression, self.NAMESPACE))
        except Exception as E:
            msg = f"{E.__class__.__name__}: {E}"
        else:
            # Prevent display of sensitive values
            if any(key in result for key in helper.SENSITIVE_KEYS):
                msg = "⛔ Your code attempted to display a sensitive value(s)!"
            else:
                msg = None

        try:
            outstr = f"```{instr}\n{result}```" if msg is None else f"```{instr}```{msg}"
            await ctx.send(outstr)
        # "Invalid Form Body" - content is too long (> 2000 characters)
        except discord.HTTPException as E:
            if E.code == 50035:
                msg = "🖐 The resulting message exceeds Discord's character limit!"
                await ctx.send(f"```{instr[:1950]}```{msg}")

    @commands.command(name="repl", aliases=["python"],
                      help="Starts a Python REPL session in current channel")
    async def repl(self, ctx) -> None:

        tup = (ctx.author.id, ctx.channel.id)
        self.bot.repl_sessions.append(tup)

        header = f"**{ctx.author.name}** has started a Python REPL session in {ctx.channel.mention}"
        code = ""
        footer = f"Exit at any time by entering `exit()`"
        outstr = f"{header}\n{footer}"
        namespace = {"print": self.printer}

        # Initial message
        log.info(
            f"User has started a REPL session ({ctx.author}, #{ctx.channel})")
        out_msg = await ctx.send(outstr)

        def check(
            msg): return msg.author == ctx.author and msg.channel == ctx.channel
        # Clear buffer in case text_to_print has lingering text (such as from previous %eval)
        self.text_to_print = None

        # Keep listening until times out or message becomes too long to send
        while len(header) + len(code) + 6 + len(footer) <= 2000:

            if code != "":
                outstr = f"{header}```{code}```{footer}"
                await out_msg.edit(content=outstr)

            # Get user input until timeout
            try:
                in_msg = await self.bot.wait_for("message", check=check, timeout=300)
            except asyncio.TimeoutError:
                log.info(
                    f"REPL session timed out ({ctx.author}, #{ctx.channel})")
                footer = f"⌛ Your session timed out from inactivity!"
                outstr = f"{header}{f'```{code}```' if code != '' else ''}{footer}"
                await out_msg.edit(content=outstr)
                await helper.reactremove(self.bot, out_msg, member=ctx.author)
                return

            instr = in_msg.content
            code += f"\n>>> {instr}"

            # Attempt to delete user's message to not clutter space
            try:
                await in_msg.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

            # Exit
            if instr == "exit()":
                log.info(
                    f"User exited REPL session ({ctx.author}, #{ctx.channel})")
                footer = "You have exited the REPL session."
                break

            try:
                # Display repr
                result = repr(self.evaluate(instr, namespace))
            except SyntaxError:
                # result is error msg | None
                result = self.execute(instr, namespace)

            # See if print/pprint was used
            if self.text_to_print is not None:
                # repl() already handles newlines; don't let print()'s end double the effect
                result = self.text_to_print.removesuffix("\n")
                self.text_to_print = None

            # Don't write anything if output of an expression is None/no error msg
            if result is not None:
                code += f"\n{result}"

        # No-break: the message became too long to send
        else:
            log.warning(
                f"Message for REPL session became too long ({ctx.author}, #{ctx.channel})")
            footer = "⚠ Your session has exceeded Discord's character limit!"
            code = code[:2000 - 7 - len(header) - len(footer)] + "…"

        self.bot.repl_sessions.remove(tup)

        outstr = f"{header}```{code}```{footer}"
        await out_msg.edit(content=outstr)
        await helper.reactremove(self.bot, out_msg, member=ctx.author)

    @commands.command(
        name="analyze", aliases=["rgb"],
        help="Calculates the root mean square RGB of most recent image")
    async def analyze(self, ctx) -> None:

        # Fetch the most recent message with an image
        async for message in ctx.channel.history(limit=100):

            # If image is embedded
            try:
                image_url = message.embeds[0].image.url
            except IndexError:
                # If image is an attachment
                try:
                    image_url = message.attachments[0].url
                except IndexError:
                    continue

            try:
                image_data = requests.get(image_url).content
            # image_url is Embed.Empty
            except MissingSchema:
                continue

            # At this point in runtime, image_url and image_data have to be defined

            log.info(
                f"Attempting to calculate r.m.s RGB on image with url: {image_url}")
            break

        else:
            log.info(
                f"No images detected in most recent 100 messages of channel #{ctx.channel}")
            await ctx.message.add_reaction("❌")
            return

        # Create/overwrite temp file
        with open(f"bot/files/image_to_analyze.png", "wb") as file:
            file.write(image_data)

        # Use PIL Image object
        image = Image.open(f"bot/files/image_to_analyze.png")
        rmsrgb = helper.rms_rgb(image)

        # image is a GIF -> pixel values of image retrieved as int -> rms_rgb() returns None
        if rmsrgb is None:
            log.warning(f"%analyze does not support analyzing GIFs")
            await ctx.send(f"**{ctx.author.name}**, `%analyze` does not support analyzing GIFs")
            return

        hexcode = helper.to_hexcode(*rmsrgb)[1:]    # Omit '#'

        # Create embed

        desc = f"The r.m.s. RGB of the most recent image:\n**#{hexcode}**"
        # Color the sidebar with the calculated hexcode
        embed = discord.Embed(
            color=discord.Color(int(hexcode, 16)),
            description=desc)

        embed.set_author(name=f"Image Analyzed (%analyze)")
        embed.set_image(url=image_url)

        out_message = await ctx.send(embed=embed)
        await helper.reactremove(self.bot, out_message)

    @commands.command(name="anagrams", aliases=["anagram"],
                      help="Finds the anagrams of your word")
    async def anagrams(self, ctx, *, word: str) -> None:
        dct = self.get_anagrams(word)

        entries = []
        for length, lst in dct.items():
            entry = f"**{length} {'LETTER:' if length == 1 else 'LETTERS:'}**"
            entry += f"```{', '.join(lst)}```"
            entries.append(entry)
        outstr = f"**{ctx.author.name}**, here are the anagrams I found for \"**{word}**\":\n\n{''.join(entries)}"
        out_msg = await ctx.send(outstr)

        await helper.reactremove(self.bot, out_msg)

    @commands.command(name="currency",
                      help="Calculates amount of a currency in terms of another currency.")
    async def currency(self, ctx, amount: float, original: str, new: str = "USD", latest: bool = False):

        # Handle formatting: currency abbreviations are all uppercase
        original = original.upper()
        new = new.upper()

        if latest:
            force_update = True

        # Determine if data is outdated enough to warrant force updating
        else:
            last_updated = self.exchanger.last_updated
            if last_updated is None or datetime.now()-last_updated > self.UPDATE_AFTER:
                force_update = True
            else:
                force_update = False

        try:
            new_amount = await self.exchanger.convert(amount, original, new, force_update)
        except LookupError as E:
            desc = f"⚠ **{ctx.author.name}**, {E}\n"
            desc += "View list of supported currencies [here](https://currencyscoop.com/supported-currencies)."
            embed = helper.make_embed(desc, color="red")
            await ctx.send(embed=embed)
            return
        except requests.RequestException:
            desc = f"⚠ **{ctx.author.name}**, I failed to extract the lastest data from [CurrencyScoop](https://currencyscoop.com/)!"
            embed = helper.make_embed(desc, color="red")
            await ctx.send(embed=embed)
            return

        last_updated = self.exchanger.last_updated.strftime(
            "%b %d, %Y %H:%M:%S")
        title = f"{amount:.2f} {original} = {new_amount:.4f} {new}"
        # <!> Not sure if datetime displayed is actually UTC
        desc = f"Using data from **{last_updated}** UTC, from [CurrencyScoop](https://currencyscoop.com/)"
        embed = helper.make_embed(desc, title, "teal")
        await ctx.send(embed=embed)

    @commands.command(name="memberdetails",
                      aliases=["memberdets", "member", "dets"],
                      help="Gets details about a member")
    async def memberdetails(self, ctx, *, member: discord.Member) -> None:
        ...


async def setup(bot: commands.Bot) -> None:
    """Required for bot to load the cog as an extension."""
    await bot.add_cog(Utils(bot))
