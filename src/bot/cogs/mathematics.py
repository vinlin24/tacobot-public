import logging
from typing import Any, NoReturn, Union

from discord.ext import commands
from sympy.matrices import Matrix
from sympy.printing.str import StrPrinter

from .. import helper

log = logging.getLogger(__name__)

##### COG DEFINITION #####


class Mathematics(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    ### HELPER METHODS ###

    def parse_matrix(self, expression: str) -> Union[Matrix, str]:
        """
        Parse expression with the syntax rules in rref() and return the sympy Matrix object.
        If parsing failed, return an error message str instead.
        """
        # Handle leading or trailing "%" if added for some reason
        expression = expression.removeprefix("%").removesuffix("%")
        row_strs = expression.split("%")

        def convert(val: Any) -> Union[int, float, NoReturn]:
            """If val represents an int, keep it as an int for display purposes."""
            val = float(val)  # May raise ValueError
            if int(val) == val:
                return int(val)
            return val

        try:
            rows = [
                [convert(val) for val in row_str.split()]
                for row_str in row_strs]
        except ValueError:
            return "the entries of the matrix must be numeric!"

        try:
            matrix = Matrix(rows)
        except ValueError:
            return "the rows of the matrix must have the same length!"
        return matrix

    ### COMMANDS ###

    @commands.command(name="rref", aliases=["gaussjordan"],
                      help="Calculates the rref of the given matrix")
    async def rref(self, ctx, *, expression: str) -> None:
        """
        Param expression should have entries separated with spaces and rows delimited with %.
        Example:
        %rref 2 -5 3 % 0.8 9 3 % -1 -7.5 0
        """
        result = self.parse_matrix(expression)

        # Parsing failed: result is an error message
        if isinstance(result, str):
            syntax_rules = \
                """
            > Your expression should have entries separated with spaces and rows delimited with `%`.
            > You should have the same number of entries in each row of the represented matrix.
            > Example: `%rref 2 -5 3 % 0.8 9 3 % -1 -7.5 0`
            """.strip("\n")
            await ctx.send(f"⚠ **{ctx.author.name}**, {result}\n{syntax_rules}")
            return

        printer = StrPrinter()  # Formatter object for sympy Matrix objects

        matrix_rref = result.rref()[0]  # Matrix.rref() returns a 2-tuple

        in_matrix_str = result.table(printer)
        out_matrix_str = matrix_rref.table(printer)

        lines = [
            f"**{ctx.author.name}**, you inputted the matrix:",
            f"```{in_matrix_str}```",
            f"The reduced row-echelon form of this matrix is:",
            f"```{out_matrix_str}```"]
        outstr = "".join(line for line in lines)

        out_msg = await ctx.send(outstr)
        await helper.reactremove(self.bot, out_msg, member=ctx.author)


async def setup(bot: commands.Bot) -> None:
    """Required for bot to load the cog as an extension."""
    await bot.add_cog(Mathematics(bot))
