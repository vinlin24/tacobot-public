import logging
from typing import Optional, Union

import discord
from discord.ext import commands

from .. import helper
from .classes.musicplayer import MusicPlayer

log = logging.getLogger(__name__)

##### COG DEFINITION #####


class Music(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # dict[int, MusicPlayer]: maps guild ID to guild-specific MusicPlayer
        self.players = {}

    ### HELPER METHODS ###

    def get_player(self, ctx) -> MusicPlayer:
        """Retrieves the guild player, or constructs one."""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player

        return player

    async def check_caller(self, ctx, player: MusicPlayer) -> bool:
        """
        Packages the various checks to see if bot should proceed with caller's command.
        Sends the appropriate embedded message depending on the check failed.
        Returns False if a check failed, True otherwise.
        """
        name = f"**{ctx.author.name}**"
        desc = None

        # Get voice channel of caller
        try:
            channel = ctx.author.voice.channel
        # voice is None
        except AttributeError:
            channel = None
            desc = f"{name}, you have to be connected to a voice channel before you can use this command!"

        # Bot is not connected
        if player.vc is None or not player.vc.is_connected():
            desc = f"{name}, I'm not connected to any voice channel! User `%play` or `%join` to summon me."

        # Bot is already in a different channel with nonzero humans
        elif channel != player.vc.channel and helper.has_humans(player.vc.channel):
            desc = f"{name}, someone else is listening to music in {player.vc.channel.mention}"

        if desc is None:
            return True

        embed = helper.make_embed(desc, color="red")
        await ctx.send(embed=embed)
        return False

    ### COMMANDS ###
    """
    Serve as an entry point, called when a bot command is sent in Discord. The bulk of the
    functionality is then handled in the appropriate MusicPlayer.
    The general flow is:
    1) Get guild-specific player
    2) Check that caller is allowed to use the command
    3) Handle arguments and appropriately update bot's voice client, if applicable
    4) Let MusicPlayer's command handler take over from here
    """

    # BASIC COMMANDS #

    @commands.command(name="join", aliases=["connect"],
                      help="Connects to your voice channel")
    async def join(self, ctx, *, channel: Optional[discord.VoiceChannel] = None) -> None:
        """
        Optional param channel to specify what voice channel to join.
        If %join is used after %leave, bot will start at song it left at.
        """

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        ### CHECKS START HERE ###

        name = f"**{ctx.author.name}**"
        desc = None

        # Handle default arg -> join caller's channel
        if channel is None:
            # Set channel to voice channel of caller
            try:
                channel = ctx.author.voice.channel
            # voice is None
            except AttributeError:
                desc = f"{name}, connect to a voice channel or pass the channel ID."

        # Check if already in use
        if player.vc is not None and player.vc.is_connected() \
                and helper.has_humans(player.vc.channel):
            # Pass if using %join for channel bot is already in
            if channel != player.vc.channel:
                desc = f"{name}, someone else is listening to music in {player.vc.channel.mention}"

        ### CHECKS END HERE ###

        # Checks failed
        if desc is not None:
            embed = helper.make_embed(desc, color="red")
            await ctx.send(embed=embed)
            return

        try:
            player.vc = await channel.connect()
        # Move channels if already connected
        except discord.ClientException:
            await player.vc.move_to(channel)

        # Let MusicPlayer take over from here
        await player.join(ctx)

    @commands.command(name="play", aliases=["p"],
                      help="Plays a selected song from YouTube")
    async def play(self, ctx, *, query: Optional[str] = None) -> None:
        """Note: if %play is used after %leave, it'll start at the requested song."""

        # Get guild-specific player
        player = self.get_player(ctx)

        ### CHECKS START HERE ###

        name = f"**{ctx.author.name}**"
        desc = None

        # Get voice channel of caller
        try:
            channel = ctx.author.voice.channel
        # voice is None
        except AttributeError:
            desc = f"{name}, connect to a voice channel first, or use `%join <channel ID>`."

        # Try to connect to voice channel
        try:
            player.vc = await ctx.author.voice.channel.connect()

        # voice is None
        except AttributeError:
            desc = f"{name}, connect to a voice channel first, or use `%join <channel ID>`."

        # Already connected to a channel: move to caller's channel, if not already in use
        except discord.ClientException:
            # No humans in current channel
            if not helper.has_humans(player.vc.channel):
                await player.vc.move_to(channel)
            elif channel != player.vc.channel:
                desc = f"{name}, someone else is listening to music in {player.vc.channel.mention}"

        ### CHECKS END HERE ###

        # Checks failed
        if desc is not None:
            embed = helper.make_embed(desc, color="red")
            await ctx.send(embed=embed)
            return

        # Let MusicPlayer take over from here
        await player.play(ctx, query)

    @commands.command(name="pause", help="Pauses the player")
    async def pause(self, ctx) -> None:

        # Get guild-specific player
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.pause(ctx)

    @commands.command(name="resume", aliases=["unpause"],
                      help="Resumes the player")
    async def resume(self, ctx) -> None:

        # Get guild-specific player
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.resume(ctx)

    @commands.command(
        name="leave", aliases=["disconnect", "dc"],
        help="Disconnects bot from the voice channel")
    async def leave(self, ctx) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.leave(ctx)

    # QUEUE TRAVERSAL #

    @commands.command(
        name="nowplaying", aliases=["np", "song"],
        help="Displays info about the current song")
    async def nowplaying(self, ctx) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        # (No checks needed, anyone can call this command)

        await player.nowplaying(ctx)

    @commands.command(name="queue", aliases=["q"],
                      help="Displays the current songs in queue")
    async def queue(self, ctx) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        # (No checks needed, anyone can call this command)

        await player.queue(ctx)

    @commands.command(name="skip", aliases=["next"],
                      help="Skips the current song being played")
    async def skip(self, ctx) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.skip(ctx)

    @commands.command(name="back", aliases=["previous", "prev"],
                      help="Returns to the previous song in queue")
    async def back(self, ctx) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.back(ctx)

    @commands.command(name="jump", aliases=["j"],
                      help="Jumps to a song by track position or title")
    async def jump(self, ctx, *, request: Union[int, str]) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.jump(ctx, request)

    # QUEUE MANAGEMENT #

    @commands.command(name="clear", help="Clears the current queue")
    async def clear(self, ctx) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        # Make it so that %clear can work even when bot is disconnected
        if player.vc is None or not player.vc.is_connected():
            await player.clear(ctx, disconnected=True)

        elif await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.clear(ctx)

    @commands.command(name="remove", aliases=["r"],
                      help="Removes a song by track position or title")
    async def remove(self, ctx, *, request: Union[int, str]) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.remove(ctx, request)

    @commands.command(
        name="removerange", aliases=["rr"],
        help="Removes all songs between two positions, inclusive")
    async def removerange(self, ctx, pos1: int, pos2: int) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.removerange(ctx, pos1, pos2)

    @commands.command(name="shuffle",
                      help="Shuffles the remaining songs in the queue")
    async def shuffle(self, ctx) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.shuffle(ctx)

    @commands.command(
        name="loop", aliases=["looptrack", "loopt"],
        help="\"on\" or \"off\", or toggles looping of the current track")
    async def loop(self, ctx, option: Optional[str] = None) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):

            # Convert option from str to Optional[bool]
            if option is not None:
                if option.lower() == "on":
                    loop_option = True
                elif option.lower() == "off":
                    loop_option = False
                # Ignore param, treat like default
                else:
                    loop_option = None
            else:
                loop_option = option

            # Let MusicPlayer take over from here
            await player.loop(ctx, loop_option)

    @commands.command(
        name="loopqueue", aliases=["loopq"],
        help="\"on\" or \"off\", or toggles looping of the current queue")
    async def loopqueue(self, ctx, option: Optional[str] = None) -> None:

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):

            # Convert option from str to Optional[bool]
            if option is not None:
                if option.lower() == "on":
                    loop_option = True
                elif option.lower() == "off":
                    loop_option = False
                # Ignore param, treat like default
                else:
                    loop_option = None
            else:
                loop_option = option

            # Let MusicPlayer take over from here
            await player.loopqueue(ctx, loop_option)

    @commands.command(
        name="shuffleloop", aliases=["loopshuffle"],
        help="Shuffles the queue when player %loopqueue back to the start")
    async def shuffleloop(self, ctx, option: Optional[str] = None) -> None:
        """Gives the option of shuffling the queue upon looping back to the start."""

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        if await self.check_caller(ctx, player):

            # Convert option from str to Optional[bool]
            if option is not None:
                if option.lower() == "on":
                    loop_option = True
                elif option.lower() == "off":
                    loop_option = False
                # Ignore param, treat like default
                else:
                    loop_option = None
            else:
                loop_option = option

            # Let MusicPlayer take over from here
            await player.shuffleloop(ctx, loop_option)

    # SAVING/LOADING #

    @commands.command(
        name="namequeue", aliases=["nameq"],
        help="Names the current queue")
    async def namequeue(self, ctx, *, queue_name: Optional[str] = None) -> None:
        """Sets the display name of the current queue. If no arg is given, reset the name."""

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        # Make it so that %namequeue can work even when bot is disconnected
        if player.vc is None or not player.vc.is_connected():
            await player.namequeue(ctx, queue_name)

        elif await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.namequeue(ctx, queue_name)

    @commands.command(
        name="savequeue", aliases=["saveq"],
        help="Saves the current queue to your personal list")
    async def savequeue(self, ctx, *, queue_name: Optional[str] = None) -> None:
        """Saves current queue to author's personal list."""

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        # (No checks needed, anyone can call this command)

        await player.savequeue(ctx, queue_name)

    @commands.command(
        name="loadqueue", aliases=["loadq"],
        help="Loads and starts a queue from your personal list")
    async def loadqueue(self, ctx, *, queue_name: str) -> None:
        """Loads a queue from author's personal list and replaces current queue."""

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        ### CHECKS START HERE - copied from play() ###

        name = f"**{ctx.author.name}**"
        desc = None

        # Get voice channel of caller
        try:
            channel = ctx.author.voice.channel
        # voice is None
        except AttributeError:
            desc = f"{name}, connect to a voice channel first, or use `%join <channel ID>`."

        # Try to connect to voice channel
        try:
            player.vc = await ctx.author.voice.channel.connect()

        # voice is None
        except AttributeError:
            desc = f"{name}, connect to a voice channel first, or use `%join <channel ID>`."

        # Already connected to a channel: move to caller's channel, if not already in use
        except discord.ClientException:
            # No humans in current channel
            if not helper.has_humans(player.vc.channel):
                await player.vc.move_to(channel)
            elif channel != player.vc.channel:
                desc = f"{name}, someone else is listening to music in {player.vc.channel.mention}"

        ### CHECKS END HERE ###

        # Checks failed
        if desc is not None:
            embed = helper.make_embed(desc, color="red")
            await ctx.send(embed=embed)
            return

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.loadqueue(ctx, queue_name)

    @commands.command(name="showqueues",
                      aliases=["showqueue", "showq", "showqs"],
                      help="Previews your list of saved queues")
    async def showqueues(self, ctx) -> None:
        """Displays list of author's saved queues."""

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        # (No checks needed, anyone can call this command)

        await player.showqueues(ctx)

    @commands.command(name="addqueue",
                      aliases=["addq", "appendqueue", "appendq"],
                      help="Appends a queue from your list to current queue")
    async def addqueue(self, ctx, *, queue_name: str) -> None:
        """Loads a queue from author's personal list and appends it to the current queue."""

        # Get guild-specific MusicPlayer
        player = self.get_player(ctx)

        ### CHECKS START HERE - copied from play() ###

        name = f"**{ctx.author.name}**"
        desc = None

        # Get voice channel of caller
        try:
            channel = ctx.author.voice.channel
        # voice is None
        except AttributeError:
            desc = f"{name}, connect to a voice channel first, or use `%join <channel ID>`."

        # Try to connect to voice channel
        try:
            player.vc = await ctx.author.voice.channel.connect()

        # voice is None
        except AttributeError:
            desc = f"{name}, connect to a voice channel first, or use `%join <channel ID>`."

        # Already connected to a channel: move to caller's channel, if not already in use
        except discord.ClientException:
            # No humans in current channel
            if not helper.has_humans(player.vc.channel):
                await player.vc.move_to(channel)
            elif channel != player.vc.channel:
                desc = f"{name}, someone else is listening to music in {player.vc.channel.mention}"

        ### CHECKS END HERE ###

        # Checks failed
        if desc is not None:
            embed = helper.make_embed(desc, color="red")
            await ctx.send(embed=embed)
            return

        if await self.check_caller(ctx, player):
            # Let MusicPlayer take over from here
            await player.addqueue(ctx, queue_name)


async def setup(bot: commands.Bot) -> None:
    """Required for bot to load the cog as an extension."""
    await bot.add_cog(Music(bot))
