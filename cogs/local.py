"""
ssh.py
26 June 2022 14:24:06
"""

from typing import *

import discord
import helper
import tekore as tk
from discord.ext import commands
from dotenv import load_dotenv

# Read/write preferences
tk.client_id_var = "SPOTIFY_CLIENT_ID"
tk.client_secret_var = "SPOTIFY_CLIENT_SECRET"
tk.redirect_uri_var = "SPOTIFY_REDIRECT_URI"
tk.user_refresh_var = "SPOTIFY_REFRESH_TOKEN"

FAV_PLAYLIST_ID = "5FpuSaX0kDeItlPMIIYBZS"
SAD_PLAYLIST_ID = "0L2mJHbM06D5AbuDbGffp6"


def _load_config() -> tuple[str, str, str, str]:
    """Return application credentials.

    Tuple is in the form of (client ID, client secret, redirect URI, user refresh token).
    """
    load_dotenv("files/.env")
    return tk.config_from_environment(return_refresh=True)


class Local(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        client_id, client_secret, _, user_refresh = _load_config()
        token = tk.refresh_user_token(client_id, client_secret, user_refresh)
        self.spotify = tk.Spotify(token.access_token)

    def cog_check(self, ctx: commands.Context) -> bool:
        """
        Define a global check for commands of this cog.
        Commands in this cog are "god commands" - exclusive to script writer.
        """
        return ctx.author.id in (helper.VIN_ID, helper.BORG_ID)

    @commands.command(name="sad", help="Adds active Spotify song to playlist(s)")
    async def sad(self, ctx: commands.Context, fav: bool = False) -> None:
        # if fav is True, add to both sad playlist and fav playlist
        # if fav is False, add to sad playlist only

        # API calls
        vin = self.spotify.current_user()
        current_playback = self.spotify.playback_currently_playing()
        if current_playback is None:
            await ctx.send("No playback detected!")
            return
        current_track = current_playback.item

        sad_playlist = self.spotify.playlist(SAD_PLAYLIST_ID)
        fav_playlist = self.spotify.playlist(FAV_PLAYLIST_ID)

        # remove then readd to avoid duplication
        self.spotify.playlist_remove(SAD_PLAYLIST_ID, [current_track.uri])
        self.spotify.playlist_add(SAD_PLAYLIST_ID, [current_track.uri])
        if fav:
            self.spotify.playlist_remove(FAV_PLAYLIST_ID, [current_track.uri])
            self.spotify.playlist_add(FAV_PLAYLIST_ID, [current_track.uri])

        # link the track
        track_url = current_track.external_urls["spotify"]

        # link the artists
        def linked_artist(artist: tk.model.SimpleArtist) -> str:
            """Return hyperlink-formatted string with artist's name and external url."""
            return f"[{artist.name}]({artist.external_urls['spotify']})"
        artists = current_track.artists
        artist_links = ", ".join(linked_artist(artist) for artist in artists)

        # link the modified playlists
        def linked_playlist(playlist: tk.model.FullPlaylist):
            return f"[{playlist.name}]({playlist.external_urls['spotify']})"
        playlists = (sad_playlist,) + ((fav_playlist,) if fav else ())
        playlist_links = ", ".join(linked_playlist(playlist)
                                   for playlist in playlists)

        # create embed
        spotify_green = discord.Color.from_rgb(30, 215, 96)
        description = f"**{vin.display_name}**, I added [{current_track.name}]({track_url}) by {artist_links} to your following playlists:\n{playlist_links}"

        embed = discord.Embed(color=spotify_green, description=description)
        await ctx.send(embed=embed)


def setup(bot: commands.Bot) -> None:
    """Required for bot to load the cog as an extension."""
    bot.add_cog(Local(bot))
