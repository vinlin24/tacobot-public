import logging
from functools import partial
from typing import Union

import pubchempy as pcp
from discord.ext import commands

from .. import helper

log = logging.getLogger(__name__)

##### COG DEFINITION #####


class Chemistry(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # Options for param namespace for pcp.get_compounds: unique -> broad
        # Excluding: sdf (idek what that is)
        # Excluding: formula (makes searches take forever; "name" covers it decently well)
        self.namespaces = ("cid", "inchi", "inchikey", "smiles", "name")
        # Mapping for converting digit characters in molecular formulas
        self.subscripts = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")

    ### HELPER METHODS ###

    def basic_info_dict(self, compound: pcp.Compound) -> dict[str,
                                                              Union[int, str]]:
        """Return an info dict with the basic information of param compound."""
        data = {}

        # Identifiers
        data["IUPAC Name"] = compound.iupac_name
        # data["PubChem CID"] = compound.cid
        # data["InChI"] = compound.inchi
        # data["InChI Key"] = compound.inchikey
        data["Isomeric SMILE"] = compound.isomeric_smiles

        # Basic physical data
        try:
            data["Mol. Formula"] = compound.molecular_formula.translate(
                self.subscripts)
        # molecular_formula can be None apparently
        except AttributeError:
            data["Mol. Formula"] = "N/A"
        data["Mol. Weight"] = compound.molecular_weight

        return data

    ### COMMANDS ###

    # The image background is ugly af
    @commands.command(
        name="periodictable", aliases=["periodic", "ptable"],
        help="Displays the periodic table of the chemical elements")
    async def periodictable(self, ctx) -> None:
        embed = helper.make_embed(color="green")
        embed.set_image(
            url="https://upload.wikimedia.org/wikipedia/commons/thumb/0/03/Simple_Periodic_Table_Chart-blocks.svg/1920px-Simple_Periodic_Table_Chart-blocks.svg.png")
        out_msg = await ctx.send(embed=embed)
        await helper.reactremove(self.bot, out_msg)

    @commands.command(
        name="pubchem", aliases=["chem"],
        help="Searches query on PubChem and returns basic info if found")
    async def pubchem(self, ctx, *, query: str) -> None:

        async with ctx.typing():

            # Search, going through most unique search type then broadening out
            for namespace in self.namespaces:
                try:
                    matches = pcp.get_compounds(query, namespace)
                    if len(matches) > 0:
                        break
                except (pcp.BadRequestError, pcp.ServerError):
                    continue
            # No-break: query pulls no results
            else:
                log.info(
                    f"{ctx.author} searched for '{query}' on PubChem and pulled no results")
                desc = f"⚠ **{ctx.author.name}**, your query `{query}` pulled no results on [PubChem](https://pubchem.ncbi.nlm.nih.gov/)!"
                await ctx.send(embed=helper.make_embed(desc, color="red"))
                return

            log.info(
                f"Processing result of PubChem query '{query}' for {ctx.author}...")
            # Use first result
            match = matches[0]  # pcp.Compound
            # Get basic info
            data = self.basic_info_dict(match)
            # Get picture: use query and the namespace from the loop that was successful
            func = partial(
                pcp.download, "PNG", "bot/files/molecule.png", query,
                namespace, overwrite=True)
            await self.bot.loop.run_in_executor(None, func)

            # Generate URL for image so it can be used in an embed
            await self.bot.s3_client.upload("bot/files/molecule.png", "tacobot", "molecule.png")
            url = await self.bot.s3_client.generate_url("tacobot", "molecule.png")
            # Failed
            if url is None:
                await ctx.send(embed=helper.make_embed("An error occurred", color="red"))
                return

            # Format embed
            title = "PubChem Search Result"
            # Start with PubChem URL (plus an empty string for newline spacing)
            entries = [
                f"https://pubchem.ncbi.nlm.nih.gov/compound/{match.cid}",
                ""]
            for key, val in data.items():
                if len(str(val)) > 20:
                    entry = f"**{key}:**\n`{val}`"  # Separate onto new line
                else:
                    entry = f"**{key}:** `{val}`"
                entries.append(entry)
            desc = "\n".join(entries)
            embed = helper.make_embed(desc, title, "green")
            embed.set_image(url=url)
            embed.set_thumbnail(url="https://scontent-lax3-2.xx.fbcdn.net/v/t1.6435-9/78271466_2626547837392990_8333308535127408640_n.png?_nc_cat=101&ccb=1-3&_nc_sid=973b4a&_nc_ohc=OgXRHrSdrJIAX-ytGg9&_nc_ht=scontent-lax3-2.xx&oh=b59c7f83f5d29444701c0c38bf473c44&oe=60C720B7")
            embed.set_footer(
                text=f"Search type: {namespace.upper()}\nQuery: \"{query}\"")

        # Send embed
        msg_out = await ctx.send(embed=embed)
        await helper.reactremove(self.bot, msg_out)


async def setup(bot: commands.Bot) -> None:
    """Required for bot to load the cog as an extension."""
    await bot.add_cog(Chemistry(bot))
