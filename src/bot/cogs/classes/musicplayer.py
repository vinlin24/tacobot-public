"""Implements the MusicPlayer class."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Union

import discord
from async_timeout import timeout

from ... import DEV_USER_ID, helper
from ..classes.songs import Song, SongQueue

log = logging.getLogger(__name__)

##### MUSICPLAYER DEFINITION #####


class MusicPlayer(object):
    """
    Represents a guild-specific music player that a Discord bot implements.
    Has methods that mirror the commands with which it is given, to manage the
    queue and position internally instead of on the caller's side.
    UNLIKE the original code this started with, MusicPlayer instances are NOT destroyed
    upon disconnect. This way, the queue is saved and playing resumes when reconnected.
    """

    ### CLASS CONSTANTS ###

    # Time in seconds before bot disconnects from inactivity
    TIMEOUT = 600
    # Time in seconds before bot stops listening for reactions to paginated queue messages
    REACTPAGE_TIMEOUT = 180
    # Reload queue when more than timedelta has elapsed since a song's creation/reload
    # source_url (googlevideo link) observed to expire 6 hours after generation
    RELOAD_INTERVAL = timedelta(hours=5)

    DOWNLOAD_FAILED_MSG = \
        """
    ⚠ **{name}**, I could not download the result of query: `{query}`
    This could be due to one or more of the following reasons:
    > **1)** The video is a playlist or livestream, which I do not yet support.
    > **2)** Your query pulled no results when searched in YouTube.
    > **3)** HTTP Error 429: YouTube banned my IP! Notify {mention}>.
    """

    ### CONSTRUCTOR & PROPERTIES ###

    def __init__(self, ctx) -> None:
        # Save so player_loop can send messages
        # Updates upon join(), play(), skip(), back(), and jump()
        self.ctx = ctx

        # Abbreviate; these values won't be reassigned even when ctx is updated
        self.bot = ctx.bot
        self.s3_client = self.bot.s3_client
        self.guild = ctx.guild

        # discord.VoiceClient; initialized with %play or %join (caller side, in music.py)
        self.vc = None

        # Use guild name to name queue of session on startup
        self.song_queue = SongQueue(str(ctx.guild) + " Queue")
        self.song_queue.loaded_by = None    # Optional[discord.Member]
        # Maintained to be >= 0 (0 if %back is used at pos 1, effectively stopping player)
        self.pos = 1

        # discord.Message: save "Now Playing" message so it can be deleted
        self.np_message = None
        # discord.Message: message with progress bar when loading a queue
        self.loading_msg = None

        # Keeps track of where in the track we are
        self.current_song = None    # Song
        self.started_at = None      # datetime
        self.checkpoint = None      # datetime
        self.playing_for = None     # timedelta

        # ad hoc solution for preserving paused state after self.vc.stop()
        # Needed for when bot is outside the queue or disconnected
        self.should_be_paused = False
        # ad hoc solution for letting %skip and %jump change pos even when looped
        self.skipped = False

        # Keep track if player is currently listening for a confirmation message
        self.wf_clear_confirm = False
        self.wf_savequeue_by = []   # list[discord.Member]
        self.wf_loadqueue_by = []   # list[discord.Member]
        self.wf_addqueue_by = []    # list[discord.Member]

        # Loop settings
        self.looped = False
        self.queue_looped = False
        self.shuffle_on_loop = False

        # Create first loop Task
        self.loop_task = self.bot.loop.create_task(self.player_loop())

        self.loadqueue_task = None  # asyncio.Task from loadqueue()

    @property
    def numtracks(self) -> int:
        """Shortcut for getting length of song queue."""
        return len(self.song_queue)

    ### HELPER METHODS ###

    def format_queue_page(self, start: int) -> str:
        """
        Format the description of one page of the queue message starting at track pos start.
        Precondition: param start in [1, queue length]
        """
        segment = self.song_queue.segment(
            start, start+9)  # SongQueue w/ len 10

        # SongQueue loaded by
        if self.song_queue.loaded_by is None:
            outstr = "**Default Guild Queue**\n\n"
        else:
            outstr = f"**Loaded by** {self.song_queue.loaded_by.mention}\n\n"

        for offset, song in enumerate(segment):
            pos = start + offset
            # For queue message, truncate song titles to keep them on one line
            # Note: some wide characters (like in Japanese names) still wrap over to next line
            line = f"{pos}) {song.truncstr(50)} | {song.duration_str}"
            # Track at current pos
            if pos == self.pos:
                line = f"**{line}** 👈"
            outstr += line + "\n"

        # Page number
        page_num = start // 10 + 1
        num_pages = (self.numtracks - 1) // 10 + 1
        if page_num == num_pages:
            outstr += "\nThis is the end of the queue!"
        else:
            outstr += "\nThe queue continues!"
        outstr += f" (**{page_num}** / **{num_pages}**)"

        return outstr

    def get_queue_pages(self) -> list[discord.Embed]:
        """Return a a list of embeds representing the pages of the queue message."""
        length = self.numtracks
        header = f"📜 {self.song_queue.name}"

        # No pagination needed

        if length <= 10:
            # Handle empty queue
            if length == 0:
                desc = "The queue is empty! 🤔"
            else:
                desc = self.format_queue_page(1)

            embed = helper.make_embed(desc, header)
            return [embed]

        # Pagination needed

        pages = []

        # Add pages
        for top_pos in range(1, length+1, 10):
            segment = self.song_queue.segment(top_pos, top_pos+9)
            page_str = self.format_queue_page(top_pos)
            embed = helper.make_embed(page_str, header)
            pages.append(embed)

        return pages

    async def queue_listener_loop(self, message: discord.Message, pages: list[discord.Embed], current_index: int) -> None:
        """Abstract the part of %queue that listens to reactions to update the message."""

        async def update_arrows() -> None:
            """
            Update arrow reactions as length of pages changes.  If the appropriate reactions
            are already present, do nothing.
            """
            # Asynchronously update message (otherwise message.reactions doesn't update)
            nonlocal message
            message = await message.channel.fetch_message(message.id)

            def has_emoji(emoji): return any(str(rxn) == emoji
                                             for rxn in message.reactions)
            # pages grew to when start/end arrows are necessary (-> 3+)
            if len(pages) > 2:
                # If either of these arrows are missing, clear and add full set of emojis
                if not (has_emoji("⏫") and has_emoji("⏬")):
                    try:
                        await message.clear_reactions()
                    except discord.Forbidden:
                        for rxn in message.reactions:
                            await message.remove_reaction(rxn.emoji, self.bot.user)
                    for emoji in "🔄⏫⬆⬇⏬":
                        await message.add_reaction(emoji)

            # pages grew from len 1 -> 2
            elif len(pages) > 1:
                # Add the emojis to the existing 🔄 if not already there
                if not has_emoji("⬆"):
                    await message.add_reaction("⬆")
                if not has_emoji("⬇"):
                    await message.add_reaction("⬇")

        def check(rxn, user): return rxn.message == message and not user.bot
        try:
            async with timeout(self.REACTPAGE_TIMEOUT):

                # Loop to continue listening for reactions until timeout
                while True:

                    # Update arrows if number of pages has been updated via 🔄
                    await update_arrows()

                    add_aw = asyncio.create_task(
                        self.bot.wait_for("reaction_add", check=check))
                    remove_aw = asyncio.create_task(
                        self.bot.wait_for("reaction_remove", check=check))

                    # Stop waiting upon one event detected; returns (set[Task], set[Future])
                    done, pending = await asyncio.wait((add_aw, remove_aw),
                                                       return_when=asyncio.FIRST_COMPLETED)
                    # set[Task] -> Task -> (discord.Reaction, discord.User)
                    rxn, user = done.pop().result()

                    # Cancel the Tasks to not hinder performance
                    add_aw.cancel()
                    remove_aw.cancel()

                    emoji = str(rxn)
                    if emoji == "🔄":
                        pages = self.get_queue_pages()  # Refresh pages
                        # init_index formula
                        current_index = (
                            min(self.pos, self.numtracks) - 1) // 10
                    elif emoji == "⬆":
                        # Don't go below 0
                        current_index = max(0, current_index-1)
                    elif emoji == "⬇":
                        # Don't go above last index
                        current_index = min(len(pages)-1, current_index+1)
                    elif emoji == "⏫":
                        current_index = 0
                    elif emoji == "⏬":
                        current_index = len(pages)-1

                    # Other emoji
                    else:
                        continue

                    # Edit message
                    current_page = pages[current_index]
                    # As a bonus, footer will update while scrolling, regardless of 🔄
                    self.set_embed_footer(current_page)
                    await message.edit(embed=current_page)

        except asyncio.TimeoutError:
            return

    def queue_preview_embed(self, owner: discord.Member,
                            queue_name: str,
                            song_ids: list[str]) -> discord.Embed:
        """Returns an embed with a preview of the queue containing song_ids."""

        # Show preview of up to first 10 songs: maybe support pagination in the future
        desc = f"**Playlist PREVIEW** [{owner.mention}]\n\n"
        for i in range(min(10, len(song_ids))):
            song_str = Song.preview_str(song_ids[i])
            if song_str is None:
                song_str = f"(Failed to load preview for id: {song_ids[i]})"
            desc += f"{i+1}) {song_str}\n"

        if len(song_ids) == 0:
            desc += "(The queue is empty)"
        elif len(song_ids) <= 10:
            desc += "\n(This is the end of the queue)"
        else:
            num_pages = (len(song_ids) - 1) // 10 + 1
            desc += f"\n(The queue continues for **{num_pages-1}** more page(s): **{len(song_ids)}** total songs)"

        return helper.make_embed(desc, f"❗ {queue_name}", "orange")

    def set_embed_footer(self, embed: discord.Embed) -> None:
        """Adds appropriate footer, if at all, to param embed based on player's vc state(s)."""

        # list[tuple[str, str]]: each item is the (description, emoji)
        states = []

        # Get the discord.Member object for bot
        bot_as_member = discord.utils.get(
            self.guild.members, id=self.bot.user.id)

        if self.vc is None or not self.vc.is_connected():
            states.append(("disconnected", "👋"))
        if bot_as_member.voice is not None and bot_as_member.voice.mute:
            states.append(("muted", "🔇"))
        if self.vc is not None and (
                self.vc.is_paused() or self.should_be_paused):
            states.append(("paused", "⏸"))
        if self.looped:
            states.append(("looping track", "🔂"))
        if self.queue_looped:
            if self.shuffle_on_loop:
                states.append(("shuffle-looping queue", "🔁🔀"))
            else:
                states.append(("looping queue", "🔁"))

        # Don't add a footer at all
        if len(states) == 0:
            return

        # Format with all cases:
        # '👋🔇⏸🔂🔀🔁 Player is disconnected, muted, paused, looping track, shuffle-looping queue'
        text = "".join(state[1] for state in states)
        text += " Player is " + ", ".join(state[0] for state in states)
        embed.set_footer(text=text)

    def progress_msg(self, current: int, total: int) -> str:
        """Return progress message for loadqueue(), including numbers and progress bar."""
        if current == total:
            outstr = "✅"
            log.info(f"Finished loading in queue")
        else:
            outstr = "⌛"
        outstr += f" Queuing: **{current}** / **{total}**\n"

        num_filled = round(current / total * 30)
        progress_bar = "`" + num_filled*"█" + (30-num_filled)*" " + "`"

        if current == total:
            cancel_msg = ""
        else:
            cancel_msg = "\nCancel loading by reacting to the X"

        return outstr + progress_bar + cancel_msg

    async def queue_songs(self, ctx, song_ids: list[str], embed_desc: str) -> None:
        """Queue songs represented by song_ids through self.play()."""
        for pos, song_id in enumerate(song_ids, 1):

            # Update progress message
            progress = self.progress_msg(pos, len(song_ids))
            embed = helper.make_embed(embed_desc + progress)
            self.set_embed_footer(embed)
            try:
                await self.loading_msg.edit(embed=embed)
            except discord.NotFound:
                pass

            await self.play(ctx, song_id, from_loadqueue=True)
            await asyncio.sleep(0.5)    # Lend execution

    async def reload_song(self, song: Song) -> None:
        """
        Reload song if need to and send appropriate messages to ctx and stdout.
        If song does not need reloading yet, do nothing.
        """
        if datetime.now() - song.creation > self.RELOAD_INTERVAL:
            log.info(f"Attempting to reload song {song.title}")
            msg = await self.ctx.send(embed=helper.make_embed(f"⏳ Reloading {song}..."))
            if song.reload():
                log.info(f"SUCCESS: Reloaded {song.title}")
            else:
                log.error(f"FAILED to reload {song.title}")
            try:
                await msg.delete()
            except discord.NotFound:
                pass

    async def cancel_loading(self, by: discord.Member) -> None:
        """
        Cancels the loading of a queue. If no queue is being loaded, do nothing.
        Param by is the member that canceled the loading.
        """
        if self.loadqueue_task is not None and not self.loadqueue_task.done():
            self.loadqueue_task.cancel()

            log.info(f"{by} canceled current loadqueue task")

            lines = self.loading_msg.embeds[0].description.splitlines()
            # Replace hourglass with x
            lines[2] = "❌" + lines[2][1:]
            # Replace cancel instruction with canceled message
            lines[-1] = f"(Canceled by {by.mention})"

            embed = helper.make_embed("\n".join(lines), color="red")
            self.set_embed_footer(embed)

            # self.loading_msg can't be None if self.loadqueue_task is not None
            await self.loading_msg.edit(embed=embed)

    def on_reconnect(self, ctx) -> None:
        """
        Called when the bot connects/reconnects to a voice channel.
        Recreates a portion of __init__(), including:
        Recreating player_loop() Task, updating the TextChannel (in ctx) to where it was
        resummoned.
        Handled internally instead of in Music cog to give more control over queue pos.
        """
        self.ctx = ctx  # Update ctx
        # Cancel current task if not already terminated
        self.loop_task.cancel()
        self.loop_task = self.bot.loop.create_task(self.player_loop())

    def increment_pos(self) -> None:
        """
        Callable to pass as arg "after" in self.vc.play().
        Increments the queue's track position every time self.vc.play() terminates.
        Now accounts for loop settings.
        """
        self.pos += 1
        if self.looped:
            # Reached end of track naturally
            if not self.skipped:
                self.pos -= 1
                self.vc.stop()

        # looped logically takes precedence over queue_looped
        elif self.queue_looped:
            if self.pos > self.numtracks:

                # Shuffle the whole queue first
                if self.shuffle_on_loop:
                    self.song_queue.shuffle()

                self.pos = 1  # Go back to start

            # %back should take pos back to the end
            elif self.pos == 0:
                self.pos = self.numtracks

        self.skipped = False  # Reset

    ### MAIN LOOP ###

    async def player_loop(self) -> None:
        """
        Main async loop that lets player automatically play songs sequentially.
        Precondition: retrieved Song objects have attr "requester".
        """
        await self.bot.wait_until_ready()

        while self.vc is not None and self.vc.is_connected():

            # Try to get next song to play until timeout
            try:
                async with timeout(self.TIMEOUT):
                    while True:
                        try:
                            song = self.song_queue.at(self.pos)
                        # Player is hanging outside of queue, waiting for new song
                        except IndexError:
                            # Delete lingering "Now Playing" message
                            try:
                                await self.np_message.delete()
                            # np_message is None or already deleted
                            except (AttributeError, discord.NotFound):
                                pass
                            await asyncio.sleep(0.5)  # Lend execution
                            continue

                        # Check this so bot times out when paused for too long or has
                        # been playing music when no human is left in the call
                        if self.vc.is_paused() or not helper.has_humans(self.vc.channel):
                            await asyncio.sleep(0.5)  # Lend execution
                            continue

                        break

            except asyncio.TimeoutError:
                log.info(f"MusicPlayer for guild {self.guild} timed out")
                await self.leave(self.ctx, by_timeout=True)
                return

            # Player is already playing
            if self.vc.is_playing():
                await asyncio.sleep(0.5)  # Lend execution
                continue

            # Reload song if need to
            await self.reload_song(song)

            # Start playing song
            try:
                self.current_song = song
                self.started_at = datetime.now()
                self.vc.play(song.audiosource,
                             after=lambda error: self.increment_pos())
            # Disconnected while paused
            except discord.ClientException:
                return

            # Player should be paused right now but isn't
            # Example: %skip when paused would otherwise unpause player
            if self.should_be_paused:
                self.vc.pause()

            try:
                await self.np_message.delete()
            # np_message is None or already deleted
            except (AttributeError, discord.NotFound):
                pass

            # Send new "Now Playing" message and update self.np_message
            log.info(f"Now playing ({self.pos}) {song.title}")
            desc = f"**({self.pos})** {song} [{song.requester.mention}]"
            embed = helper.make_embed(desc, "Now playing")
            self.set_embed_footer(embed)
            self.np_message = await self.ctx.send(embed=embed)

            # See if rest of queue needs reloading
            # Put at end so it runs in background; this way users should only have to wait
            # once per command (such as when reconnecting the bot)
            for song in self.song_queue:
                await self.reload_song(song)

    ### COMMAND HANDLERS ###
    """
    These all have the precondition that the caller was allowed to run the command.
    They assume that the caller in music.py properly handled updating the voice client.
    It follows that this applies to the helper function on_reconnect() too.
    """

    # BASIC COMMANDS #

    async def join(self, ctx) -> None:
        """MusicPlayer continues at the position it left off."""
        await ctx.message.add_reaction("👌")

        # !!! not sure if this is redundant
        # Reconnected; if not, task will be canceled in on_reconnect()
        if not self.vc.is_playing():
            self.on_reconnect(ctx)
        # In any case, rebind self.ctx to update where player_loop sends messages
        else:
            self.ctx = ctx

    async def play(self, ctx, query: Optional[str], *, from_loadqueue=False) -> None:
        """
        Generates song from query and appends it to the queue.
        Param from_loadqueue for internal use only; called with True from loadqueue()
        """

        # query was not specified
        if query is None:
            desc = f"**{ctx.author.name}**, tell me what to search for! Example: `%play see you again`"
            await ctx.send(embed=helper.make_embed(desc, color="red"))

            # !!! not sure if this is redundant
            # Reconnected; if not, task will be canceled in on_reconnect()
            if not self.vc.is_playing() and not self.vc.is_paused():
                self.on_reconnect(ctx)
            # In any case, rebind self.ctx to update where player_loop sends messages
            else:
                self.ctx = ctx

            return

        # Construct song
        song = Song.from_query(query)

        # Download failed
        if song is None:
            log.warning(f"Failed to download song from query: {query}")
            dev_user: discord.User = await self.bot.fetch_user(DEV_USER_ID)
            desc = self.DOWNLOAD_FAILED_MSG.format(
                name=ctx.author.name, query=query, mention=dev_user.mention)
            embed = helper.make_embed(desc, color="red")
            await ctx.send(embed=embed)
            return

        song.requester = ctx.author  # Bind a new attr "requester", points to caller
        self.song_queue.add_song(song)

        # Only display queued message when bot is inside queue and already playing music
        # Omit the message when play() is called from loadqueue() (to not spam)
        if not from_loadqueue and (
                self.vc.is_playing() or self.vc.is_paused()):

            log.info(f"Queued ({self.numtracks}) {song.title}")

            desc = f"Queued **({self.numtracks})** {song} [{song.requester.mention}]"
            embed = helper.make_embed(desc)
            self.set_embed_footer(embed)
            await ctx.send(embed=embed)

        # !!! not sure if this is redundant
        # Reconnected upon %play, play new song right away
        # Put this check AFTER obtaining song so that pos is set correctly
        # before recreating player_loop
        if not self.vc.is_playing() and not self.vc.is_paused():
            self.pos = self.numtracks
            self.on_reconnect(ctx)
        # In any case, rebind self.ctx to update where player_loop sends messages
        else:
            self.ctx = ctx

    async def pause(self, ctx) -> None:
        """Pause the voice client."""
        self.vc.pause()
        self.should_be_paused = True
        log.info("Paused MusicPlayer")
        await ctx.message.add_reaction("⏸")

    async def resume(self, ctx) -> None:
        """Resume the voice client."""
        self.vc.resume()
        self.should_be_paused = False
        log.info("Resumed MusicPlayer")
        await ctx.message.add_reaction("▶")

    async def leave(self, ctx, *, by_timeout: bool = False) -> None:
        """
        Leaves the channel, leaving the queue intact.
        by_timeout param for internal use only, called with True when bot leaves via timeout
        instead of via command.
        """
        if self.vc.is_playing() or self.vc.is_paused():
            # Offset the increment_pos() that's called when vc.play() is terminated
            self.pos -= 1

        await self.vc.disconnect()
        log.info(f"{self.guild} MusicPlayer disconnected from channel")

        if by_timeout:
            embed = helper.make_embed(
                "❗ I left the voice channel because I was inactive for too long.")
            await ctx.send(embed=embed)
        else:
            await ctx.message.add_reaction("👋")

    # QUEUE INFO & TRAVERSAL #

    async def nowplaying(self, ctx) -> None:
        """
        Display info about the song currently playing.
        Precondition: self.current_song has attr "requester".
        This currently does not display position within the track.
        """
        song = self.current_song
        duration = song.duration_str

        title = "Current song"
        desc = f"**({self.pos})** {song} | **?** / **{duration}** | Requested by {song.requester.mention}"
        embed = helper.make_embed(desc, title)
        self.set_embed_footer(embed)

        await ctx.send(embed=embed)

    async def queue(self, ctx) -> None:
        """
        Display queue message.  Now supports reaction pagination, with reactions for jumping
        to start/end/current added for series that have more than 2 pages.
        Queue message fits at most 10 songs per page (implemented in format_queue_page()).
        """
        # Send initial message

        pages = self.get_queue_pages()

        # Zero-indexed, since it indexes pages, a list
        # NOTE: if self.pos is 0, init_index is -1, which is acceptable b/c %queue
        # should display last page when bot is outside the queue
        init_index = (min(self.pos, self.numtracks) - 1) // 10
        current_page = pages[init_index]
        self.set_embed_footer(current_page)
        out_msg = await ctx.send(embed=current_page)

        # Add reactions
        await out_msg.add_reaction("🔄")
        if len(pages) > 2:
            await out_msg.add_reaction("⏫")
        if len(pages) > 1:
            await out_msg.add_reaction("⬆")
            await out_msg.add_reaction("⬇")
        if len(pages) > 2:
            await out_msg.add_reaction("⏬")

        # Listener loop
        await self.queue_listener_loop(out_msg, pages, init_index)

    async def skip(self, ctx) -> None:
        """Skips the currently playing song."""

        self.skipped = True
        # pos is automatically incremented by self.vc.play(after=...) in main loop
        self.vc.stop()

        try:
            log.info(
                f"Stopped ({self.pos}) {self.song_queue.at(self.pos).title}")
        except IndexError:
            log.info(
                f"Skipped nothing, outside of the queue already (pos={self.pos})")
        await ctx.message.add_reaction("👌")
        self.ctx = ctx

    async def back(self, ctx) -> None:
        """Returns to the previous song in queue."""

        # pos not hanging at 0 already
        if self.pos > 0:

            self.skipped = True

            # If player is inside queue, so DON'T check should_be_paused
            if self.vc.is_playing() or self.vc.is_paused():
                # Offset increment_pos() caused by vc.stop() so that in effect, pos -= 1
                self.pos -= 2
                self.vc.stop()
            # Player is outside the queue, including when it should be paused
            else:
                self.pos -= 1

        try:
            log.info(
                f"Stopped ({self.pos+2}) {self.song_queue.at(self.pos+2).title}")
        except IndexError:
            log.info(
                f"Skipped nothing, outside of the queue already (pos={self.pos})")

        await ctx.message.add_reaction("👌")
        self.ctx = ctx

    async def jump(self, ctx, request: Union[int, str]) -> None:
        """Jumps to a song by track position or title."""

        # Jump by pos option
        if isinstance(request, int):

            # Out of range
            if request < 1 or request > self.numtracks:
                embed = helper.make_embed(
                    f"**{ctx.author.name}**, track position `{request}` is out of range",
                    color="red")
                await ctx.send(embed=embed)
                return

            pos = request

        # Jump by title option
        else:
            pos = self.song_queue.get_song_pos(request)

            if pos is None:
                embed = helper.make_embed(
                    f"**{ctx.author.name}**, could not find a track for \"{request}\"",
                    color="red")
                await ctx.send(embed=embed)
                return

        self.skipped = True

        # pos now points to the track position to jump to
        old_pos = self.pos
        # If is inside the queue (so DON'T check should_be_paused)
        if self.vc.is_playing() or self.vc.is_paused():
            self.pos = pos-1  # -1 to offset for increment_pos()
            self.vc.stop()
        else:
            self.pos = pos

        try:
            log.info(
                f"Stopped ({old_pos}) {self.song_queue.at(old_pos).title}")
        except IndexError:
            log.info(
                f"Skipped nothing, outside of the queue already (pos={old_pos})")
        self.ctx = ctx

    # QUEUE MANAGEMENT #

    async def clear(self, ctx, *, disconnected: bool = False) -> None:
        """
        Clear the queue and stops the player.  If a queue is being loaded when this is
        called, clear() will cancel that task so that the end result is an empty queue.
        Also reset the queue name and "Loaded by" description.
        disconnected param called with True from music.py when %clear is called when bot
        is disconnected.
        NOTE: Not sure if param disconnected is necessary.
        """
        # A confirmation check is already undergoing
        if self.wf_clear_confirm:
            await ctx.message.add_reaction("🚫")
            return

        # Ask for confirmation
        if self.numtracks > 0:
            self.wf_clear_confirm = True

            warning_msg = f"⚠ **{ctx.author.name}**, the `%queue` currently has **{self.numtracks}** song(s).\n"
            warning_msg += "Do you confirm? (y/n/yes/no)"
            timeout_msg = "⌛ Time's up. Queue preserved."
            decline_msg = "🖐 Gotcha. Queue preserved."

            response = await helper.ask_for_confirmation(ctx, warning_msg, timeout_msg, decline_msg)
            self.wf_clear_confirm = False

            # Not y/yes
            if response is not True:
                return

        # No confirmation needed since %clear does nothing, just react with an emoji
        else:
            await ctx.message.add_reaction("👌")
            return

        # Cancel loading queue if currently doing so
        await self.cancel_loading(ctx.author)

        # The actual clearing
        num_cleared = self.song_queue.clear_queue()

        if not disconnected:
            self.vc.stop()

        # Reset: point to pos 1 again to wait for song to be appended
        self.pos = 1
        self.song_queue.loaded_by = None
        self.song_queue.name = f"{self.guild} Queue"

        log.info(f"Cleared {num_cleared} song(s) from queue")
        desc = f"💥 Cleared **{num_cleared}** song(s) from queue [{ctx.author.mention}]"
        embed = helper.make_embed(desc)
        await ctx.send(embed=embed)

    async def remove(self, ctx, request: Union[int, str]) -> None:
        """Removes a song by track position or title."""

        # Remove by pos option
        if isinstance(request, int):

            # Out of range
            if request < 1 or request > self.numtracks:
                embed = helper.make_embed(
                    f"**{ctx.author.name}**, track position `{request}` is out of range",
                    color="red")
                await ctx.send(embed=embed)
                return

            pos = request

        # Remove by title option
        else:
            pos = self.song_queue.get_song_pos(request)

            if pos is None:
                embed = helper.make_embed(
                    f"**{ctx.author.name}**, could not find a track for \"{request}\"",
                    color="red")
                await ctx.send(embed=embed)
                return

        # pos now points to the track position to remove

        removed_song = self.song_queue.pop_song(pos)

        # Removed current song
        if pos == self.pos:
            # Only matters if bot was currently playing that song
            if self.vc.is_playing() or self.vc.is_paused() or self.should_be_paused:
                self.pos -= 1  # -1 to offset for increment_pos()
                self.vc.stop()

        # Removed song before current song -> move self.pos back appropriately
        if pos < self.pos:
            self.pos -= 1

        desc = f"Removed **({pos})** {removed_song} [{ctx.author.mention}]"
        await ctx.send(embed=helper.make_embed(desc))

        log.info(f"Removed ({pos}) {removed_song.title}")

    async def removerange(self, ctx, pos1: int, pos2: int) -> None:
        """
        Removes all songs between track positions pos1 and pos2, inclusive.
        Doesn't need to handle bag args because SongQueue.pop_range() uses list slicing logic.
        """
        num_removed = len(self.song_queue.pop_range(pos1, pos2))

        if num_removed == 0:
            await ctx.message.add_reaction("❓")
            return

        # Removed current song
        if self.pos in range(pos1, pos2+1):
            # Only matters if bot was currently playing that song
            if self.vc.is_playing() or self.vc.is_paused() or self.should_be_paused:
                self.pos -= 1  # -1 to offset for increment_pos()
                self.vc.stop()

        # Removed songs before current song -> update self.pos appropriately
        elif pos2 < self.pos:
            self.pos -= num_removed

        log.info(
            f"Removed {num_removed} song(s) ({pos1}~{pos1+num_removed-1}) from queue")
        desc = f"🔪 Removed **{num_removed}** song(s) (**{pos1}**~**{pos1+num_removed-1}**) from queue"
        desc += f" [{ctx.author.mention}]"
        await ctx.send(embed=helper.make_embed(desc))

    async def shuffle(self, ctx) -> None:
        """Shuffles the remaining songs in the queue."""

        self.song_queue.shuffle(self.pos)
        await ctx.message.add_reaction("🔀")
        log.info(
            f"Shuffled {max(0, self.numtracks-self.pos)} tracks (after pos {self.pos})")

    async def loop(self, ctx, option: Optional[bool]) -> None:
        """
        Changes looping of the current track based on param option.
        None: toggles to the opposite of what it is now.
        True: sets to ON.
        False: sets to OFF.
        """
        # Toggle
        if option is None:
            self.looped = not self.looped
        # Explicit
        else:
            self.looped = option

        if self.looped:
            desc = "🔂 Now looping the **current track**.\n\n"
            desc += "To disable, use: `%loop off`\nTo loop whole queue: `%loopqueue on`"
        else:
            desc = "No longer looping the **current track**."

        embed = helper.make_embed(desc)
        self.set_embed_footer(embed)
        await ctx.send(embed=embed)
        log.info(desc.replace("*", "").replace("\n\n", " "))

    async def loopqueue(self, ctx, option: Optional[bool]) -> None:
        """
        Changes looping of the current queue based on param option.
        None: toggles to the opposite of what it is now.
        True: sets to ON.
        False: sets to OFF.
        """
        # Toggle
        if option is None:
            self.queue_looped = not self.queue_looped
        # Explicit
        else:
            self.queue_looped = option

        if self.queue_looped:
            desc = "🔁 Now looping the **queue**.\n\n"
            desc += "To disable, use: `%loopqueue off`\nTo loop one track: `%loop on`"
        else:
            desc = "No longer looping the **queue**."
            # Also disable shuffle-looping
            self.shuffle_on_loop = False

        embed = helper.make_embed(desc)
        self.set_embed_footer(embed)
        await ctx.send(embed=embed)
        log.info(desc.replace("*", "").replace("\n\n", " "))

    async def shuffleloop(self, ctx, option: Optional[bool]) -> None:
        """
        Changes the option of shuffling the queue upon looping back to the start based on param.
        None: toggles to the opposite of what it is now.
        True: sets to ON.
        False: sets to OFF.
        If the queue is not already looped and the option is set to ON, the queue will be looped.
        """
        # Handle arg

        # Toggle
        if option is None:
            self.shuffle_on_loop = not self.shuffle_on_loop
        # Explicit
        else:
            self.shuffle_on_loop = option

        if self.shuffle_on_loop:
            # Loop the queue if not already looped
            self.queue_looped = True
            desc = "🔁🔀 Player will **shuffle the queue** upon looping to the start.\n\n"
            desc += "To disable, use: `%shuffleloop off` or `%loopqueue off`\n"
            desc += "To shuffle remaining songs right away: `%shuffle`"
        else:
            desc = "No longer **shuffling the queue** upon looping to the start."

        embed = helper.make_embed(desc)
        self.set_embed_footer(embed)
        await ctx.send(embed=embed)
        log.info(desc.replace("*", "").replace("\n\n", " ").replace("\n", " "))

    # SAVING/LOADING #

    async def namequeue(self, ctx, queue_name: Optional[str]) -> None:
        """Sets the display name of the current queue. If no arg was given, reset the name."""
        if queue_name is None:
            self.song_queue.name = f"{self.guild} Queue"
            desc = "✏ Reset"
        else:
            self.song_queue.name = queue_name
            desc = "✏ Set"

        desc += f" current queue name to **{self.song_queue.name}** [{ctx.author.mention}]"
        await ctx.send(embed=helper.make_embed(desc))

    async def savequeue(self, ctx, queue_name: Optional[str]) -> None:
        """
        Saves current queue to personal playlists.txt in user-specific files folder.
        Saves with the name queue_name if specified, else uses the current queue name.
        If queue_name matches an existing name (case-insensitive) in playlists.txt, the user
        is prompted to confirm whether he/she wants to replace it.
        """
        # Process already started
        if ctx.author in self.wf_savequeue_by:
            await ctx.message.add_reaction("🚫")
            return

        # Handle default arg: use queue's current name
        queue_name = self.song_queue.name if queue_name is None else queue_name

        filedir = f"users/{ctx.author.id}/"
        localpath = "bot/files/temp_playlist.txt"

        # Ensure directory exists
        await self.s3_client.create_folder("tacobot", filedir)
        # Download playlists.txt if exists
        if not await self.s3_client.download(f"{filedir}playlists.txt", "tacobot", "bot/files/temp_playlist.txt"):
            open("bot/files/temp_playlist.txt", "w").close()
            log.info(
                f"{ctx.author} does not have a playlists.txt yet; using local file")

        # Check if user already saved a playlist with the same name (case-insensitive)
        payload = SongQueue.get_saved_contents(localpath, queue_name)

        # Saved queue with same name exists: alert user and give option to replace
        if payload is not None:
            existing_name, song_ids = payload

            preview = self.queue_preview_embed(
                ctx.author, existing_name, song_ids)
            preview_msg = await ctx.send(embed=preview)

            warning_msg = f"⚠ **{ctx.author.name}**, you already saved a queue with name `{existing_name}`\n"
            warning_msg += "Sent queue preview above. **Replace it?** (y/n/yes/no)"
            timeout_msg = "⌛ Time's up. Keeping old playlist."
            decline_msg = "🖐 Gotcha. Keeping old playlist."

            self.wf_savequeue_by.append(ctx.author)
            response = await helper.ask_for_confirmation(ctx, warning_msg, timeout_msg, decline_msg, 20.0)
            self.wf_savequeue_by.remove(ctx.author)

            if response is not True:
                return

            # Get span to remove the queue later
            span = SongQueue.get_repr_span(localpath, existing_name)

        # Save queue locally
        with open(localpath, "rt+", encoding="utf-8") as file:
            content = file.read()

            # Remove existing queue if needed
            try:
                content = content[:span[0]] + content[span[1]:]
            except NameError:
                pass

            # Append queue repr: temporarily rename song_queue
            temp = self.song_queue.name
            self.song_queue.name = queue_name
            content += repr(self.song_queue)
            self.song_queue.name = temp

            # Overwrite everything with edited content
            file.seek(0)
            file.truncate(0)
            file.write(content)

        # Update on AWS S3
        await self.s3_client.upload(localpath, "tacobot", f"{filedir}playlists.txt")

        log.info(
            f"{ctx.author} saved current queue as {queue_name} to personal list")
        desc = f"📝 Saved current queue as `{queue_name}` to personal list [{ctx.author.mention}]"
        await ctx.send(embed=helper.make_embed(desc))

    async def loadqueue(self, ctx, queue_name: str, *, append: bool = False) -> None:
        """
        Load the queue, if exists, named queue_name from author's personal list.
        If the current queue is non-empty, prompt user to confirm replacing queue.
        If another queue is being loaded when this is called, the loading Task will be
        canceled.
        Param append for internal use only; called with True when called from addqueue().
        """
        # Process already started
        if ctx.author in self.wf_loadqueue_by:
            await ctx.message.add_reaction("🚫")
            return

        # Download from AWS S3

        filepath = f"users/{ctx.author.id}/playlists.txt"
        localpath = "bot/files/temp_playlist.txt"

        if not await self.s3_client.obj_exists("tacobot", filepath):
            desc = f"**{ctx.author.name}**, you don't have any saved playlists!"
            await ctx.send(embed=helper.make_embed(desc, color="red"))
            return

        await self.s3_client.download(filepath, "tacobot", localpath)

        payload = SongQueue.get_saved_contents(localpath, queue_name)

        if payload is None:
            desc = f"**{ctx.author.name}**, you don't have a playlist named `{queue_name}`"
            await ctx.send(embed=helper.make_embed(desc, color="red"))
            return

        existing_name, song_ids = payload
        preview = self.queue_preview_embed(ctx.author, existing_name, song_ids)
        preview_msg = await ctx.send(embed=preview)

        if append:
            log.info(f"{ctx.author} is adding a queue: {existing_name}")
            embed_desc = f"✳ **Appending playlist:** `{existing_name}` [{ctx.author.mention}]\n\n"

        else:

            # Ask if user wants to replace current queue (if non-empty)
            if self.numtracks > 0:

                warning_msg = f"⚠ **{ctx.author.name}**, the `%queue` currently has **{self.numtracks}** song(s).\n"
                warning_msg += "💥 Do you want to **replace** the current queue? (y/n/yes/no)"
                timeout_msg = "⌛ Time's up. Queue preserved."
                decline_msg = "🖐 Gotcha. Queue preserved."

                self.wf_loadqueue_by.append(ctx.author)
                response = await helper.ask_for_confirmation(ctx, warning_msg, timeout_msg, decline_msg, 20.0)
                self.wf_loadqueue_by.remove(ctx.author)

                if response is not True:
                    return

            # User went through with replacing current queue

            # Clear current queue and bring pos to start
            self.song_queue.clear_queue()
            self.vc.stop()
            self.pos = 1
            self.song_queue.name = existing_name
            self.song_queue.loaded_by = ctx.author

            log.info(f"{ctx.author} is loading in a queue: {existing_name}")
            embed_desc = f"🔄 **Loading playlist:** `{existing_name}` [{ctx.author.mention}]\n\n"

        # Cancel loading other queue if currrently doing so
        await self.cancel_loading(ctx.author)

        # Progress message
        progress = self.progress_msg(0, len(song_ids))
        embed = helper.make_embed(embed_desc + progress)
        self.set_embed_footer(embed)

        self.loading_msg = await ctx.send(embed=embed)
        await self.loading_msg.add_reaction("❌")

        # Option to cancel loading manually with reaction

        def check(rxn, user): return rxn.message == self.loading_msg and str(
            rxn) == "❌" and not user.bot
        rxn_aw = asyncio.create_task(
            self.bot.wait_for("reaction_add", check=check))
        self.loadqueue_task = asyncio.create_task(
            self.queue_songs(ctx, song_ids, embed_desc))
        done, pending = await asyncio.wait((self.loadqueue_task, rxn_aw),
                                           return_when=asyncio.FIRST_COMPLETED)
        # Reaction to X happened first
        if rxn_aw in done:
            await self.cancel_loading(done.pop().result()[1])

        # In any case, remove the X
        try:
            try:
                await self.loading_msg.clear_reaction("❌")
            except discord.Forbidden:
                await self.loading_msg.remove_reaction("❌", self.bot.user)
        except discord.NotFound:
            pass

    async def showqueues(self, ctx) -> None:
        """Displays list of author's saved queues."""
        # Download from AWS S3

        filepath = f"users/{ctx.author.id}/playlists.txt"
        localpath = "bot/files/temp_playlist.txt"

        if not await self.s3_client.obj_exists("tacobot", filepath):
            desc = f"**{ctx.author.name}**, you don't have any saved playlists!"
            await ctx.send(embed=helper.make_embed(desc, color="red"))
            return

        await self.s3_client.download(filepath, "tacobot", localpath)

        names = SongQueue.get_names(localpath)
        names_to_len = {
            name: len(SongQueue.get_saved_contents(localpath, name)[1])
            for name in names}

        desc = f"**Playlists PREVIEW** [{ctx.author.mention}]\n\n"
        body = "\n".join(f"**{name}**: {len_} songs" for name,
                         len_ in names_to_len.items())
        desc += "Your list is empty!" if body == "" else body

        embed = helper.make_embed(desc, f"💾 Saved Queues")
        await ctx.send(embed=embed)

    async def addqueue(self, ctx, queue_name: str) -> None:
        """
        Append the queue, if exists, named queue_name from author's personal list to the
        current queue.  This will cancel the current loadqueue task if exists, so warn
        the caller and ask for confirmation first.
        """
        # Process already started
        if ctx.author in self.wf_addqueue_by:
            await ctx.message.add_reaction("🚫")
            return

        if self.loadqueue_task is not None and not self.loadqueue_task.done():
            desc = self.loading_msg.embeds[0].description
            loading_by = helper.get_mention(self.bot, desc)

            # Just in case
            if loading_by is None:
                suffix = "!"
            else:
                suffix = f" from {loading_by.mention}"

            warning_msg = f"⚠ **{ctx.author.name}**, I'm already loading another queue{suffix}\n"
            warning_msg += "🛑 Do you want to **cancel** the current process? (y/n/yes/no)"
            timeout_msg = "⌛ Time's up. Queuing preserved."
            decline_msg = "🖐 Gotcha. Queuing preserved."

            self.wf_addqueue_by.append(ctx.author)
            response = await helper.ask_for_confirmation(ctx, warning_msg, timeout_msg, decline_msg)
            self.wf_addqueue_by.remove(ctx.author)

            if response is not True:
                return

        await self.loadqueue(ctx, queue_name, append=True)
