"""Implements the Song and SongQueue classes."""

import json
import random
import re
import urllib
import urllib.request
from datetime import datetime
from typing import Any, Generator, Iterable, NoReturn, Optional, Union

import discord
from yt_dlp import YoutubeDL

##### DATA CLASSES #####


class Song(object):
    """
    Represents a song from YouTube.
    Serves as a wrapper for YoutubeDL's info dict corresponding to the song.
    Has a classmethod to construct a song from a YouTube search.
    Songs can return a Discord-playable audio stream of self.
    """

    ### CLASS CONSTANTS & INSTANCES ###

    YTDL_OPTIONS = {
        "format": "bestaudio",
        "noplaylist": True,
        "quiet": True,
        "ignoreerrors": True,
        "default_search": "auto",
        "source_address": "0.0.0.0"  # "ipv6 addresses cause issues sometimes"
    }
    """Options to use for the yt_dlp handler."""

    FFMPEG_OPTIONS = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn"
    }
    """Options to pass to discord.FFmpegPCMAudio()."""

    # YouTube download manager
    ytdl = YoutubeDL(YTDL_OPTIONS)

    ### METHODS ###

    def __init__(self, info: dict) -> None:
        """Wraps the info dict returned by ytdl.extract_info()."""
        assert "entries" not in info, \
            "param info must correspond to ONE video, not an ENTRY of videos"

        # Time of creation; updated when reloaded
        self.creation = datetime.now()

        # Save relevant key: value pairs as attributes for intuitive retrieval
        # Use . notation instead of iterative setattr() for faster performance
        self.id = info["id"]
        self.title = info["title"]
        self.duration = info["duration"]
        self.webpage_url = info["webpage_url"]

        self.formats = info["formats"]

        # Save the rest as is; not needed as commonly
        self.info = info

    @property
    def duration_str(self) -> str:
        """Return the duration of song in format '[[H]H:]MM:SS'."""

        # If more than a day, take the remainder
        seconds = self.duration % (24 * 3600)
        hours = seconds // 3600
        minutes = seconds // 60
        seconds %= 60

        if hours > 0:
            duration = f"{hours}:{minutes:02}:{seconds:02}"
        else:
            duration = f"{minutes:02}:{seconds:02}"

        return duration

    @property
    def source_url(self) -> str:
        """
        This can be passed into discord.FFmpegPCMAudio() to be convered to AudioSource.
        Apparently this is different from info["url"].
        """
        return self.info["url"]

    @property
    def audiosource(self) -> discord.AudioSource:
        """Return an ffmpeg AudioSource that can be played on Discord."""
        return discord.FFmpegPCMAudio(self.source_url, **self.FFMPEG_OPTIONS)

    def __repr__(self) -> str:
        """Return a string with the song ID, as that is unlikely to change."""
        return f"Song(id='{self.id}')"

    def __str__(self) -> str:
        """Return a string with hyperlink markdown: "[title](webpage_url)"."""
        return f"[{self.title}]({self.webpage_url})"

    def __eq__(self, other: Any) -> bool:
        """Determine if other represents the same YouTube video as self."""
        try:
            return self.id == other.id  # I assume YouTube video IDs don't change
        except Exception:
            return False

    def __ne__(self, other: Any) -> bool:
        """Determine if other represents a different Youtube video, if at all, as self."""
        return not (self == other)

    def __len__(self) -> int:
        """Implement len() call as duration of song, in seconds."""
        return self.duration

    def truncstr(self, max_chars: Optional[int] = None) -> str:
        """
        Return str(self) but with a truncated title (marked with …) if the length of the title
        exceeds max_chars.
        """
        # Handle default arg
        if max_chars is None:
            return str(self)

        title = self.title[:max_chars]
        if len(title) < len(self.title):
            title += "…"

        # Unmatched [] will result in undesired parsing of hyperlink markdown
        title = title.replace("[", "").replace("]", "")

        return f"[{title}]({self.webpage_url})"

    def reload(self) -> bool:
        """Update self by querying YouTube with video ID.
        Necessary for avoiding 403 Forbidden errors (source_url expires after 6 hours).

        Returns
        -------
        bool
            True if reload was successful, False otherwise.
        """
        with self.ytdl as ytdl:
            info = ytdl.extract_info(self.id, download=False)
            if info is None:
                return False
            info = info["entries"][0]
            self.__init__(info)
            return True

    @classmethod
    def from_query(cls, query: str) -> Optional["Song"]:
        """
        Search query on YouTube and return a corresponding Song object.

        Parameters
        ----------
        query: str
            The search words or Youtube URL to use.

        Returns
        -------
        Optional[Song]
            A Song object representing the video, or None if extracting failed.
        """
        with cls.ytdl as ytdl:
            info = ytdl.extract_info(f"ytsearch:{query}", download=False)
            if info is None:
                return None
            # Always take the top choice for now.
            return cls(info["entries"][0])

    @classmethod
    def preview_str(cls, video_id: int) -> Optional[str]:
        """
        Return what would be the str() of the song with ID video_id.
        This does not extract through ytdl and is thus much faster for previewing purposes.
        Return None if request fails.
        """
        webpage_url = f"https://www.youtube.com/watch?v={video_id}"

        params = {"format": "json", "url": webpage_url}
        url = "https://www.youtube.com/oembed"
        query_string = urllib.parse.urlencode(params)
        url = f"{url}?{query_string}"

        try:
            with urllib.request.urlopen(url) as response:
                response_text = response.read()
                # dict[str, Union[str, int]]
                data = json.loads(response_text.decode())
                return f"[{data['title']}]({webpage_url})"

        # "Error 400: Bad Request" - invalid video ID
        # "Error 404: Not Found" - video doesn't exist
        except urllib.error.HTTPError:
            return None


class SongQueue(object):
    """
    Represents a queue, an ordered list of Songs whose track positions start from 1.
    Serves as a wrapper for a Song array.
    """

    ### CLASS CONSTANTS ###

    # RegEx patterns
    # From: https://webapps.stackexchange.com/questions/54443/format-for-id-of-youtube-video
    VIDEO_ID_PATTERN = r"[0-9A-Za-z_-]{10}[048AEIMQUYcgkosw]"
    QUEUE_PATTERN = "\\{{{name}\\}}\\{{(\\n{video_id})*\\n?\\}}\\n"

    ### METHODS ###

    def __init__(self, name: str = "") -> None:
        """
        Initializes a non-public Song array.
        Optional param name to name the SongQueue. Forbidden chars '{' and '}' are removed.
        """
        self._queue = []  # list[Song]
        self.name = name

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name: str):
        # Remove {} to prevent hindering of parsing
        self._name = new_name.replace("{", "").replace("}", "")

    def __repr__(self) -> str:
        """
        Used for writing a SongQueue to a file for saving.
        Save in the format of:
        {name}{
        xxxxxxxxxxx
        xxxxxxxxxxx
        xxxxxxxxxxx}
        Because of this format, name should not have any {} chars in it that would hinder parsing.
        """
        outstr = f"{{{self.name}}}{{\n"
        # Use IDs because that's unlikely to change over time
        outstr += "\n".join(f"{song.id}" for song in self) + "}\n"
        return outstr

    def __str__(self) -> str:
        """Display queue with str() of each song in queue."""
        return f"{{{self.name}}}{{\n" + "\n".join(
            str(song) for song in self) + "}"

    def __len__(self) -> int:
        """Length of SongQueue is interpreted as number of songs in the queue."""
        return len(self._queue)

    def __eq__(self, other: Any) -> bool:
        """Determine if other represents the same queue as self."""
        try:
            return all(self.at(i) == other.at(i) for i in range(
                1, len(self) + 1)) and len(self) == len(other)
        except (AttributeError, TypeError):
            return False

    def __ne__(self, other: Any) -> bool:
        """Determine if other represents a different queue, if at all, as self."""
        return not (self == other)

    def __iter__(self) -> Generator[Song, None, None]:
        """Implement for-in iteration through a SongQueue."""
        return (song for song in self._queue)

    def truncstr(self, max_chars: Optional[int] = None) -> str:
        """Return str(self) but with a truncstr() called on every song."""
        return f"({self.name})" + "\n{\n" + "\n".join(song.truncstr(max_chars)
                                                      for song in self) + "\n}"

    ### RETRIEVAL ###

    def at(self, pos: int) -> Union[Song, NoReturn]:
        """
        Return the Song at queue position pos; raise custom IndexError if out of range.
        Track positions start counting from 1 as opposed to zero-indexing of arrays.
        """
        if pos < 1 or pos > len(self):
            raise IndexError(
                f"queue position {pos} out of range [1, len(self)]")
        # Use if instead of try becasue (pos-1) can return negative index
        return self._queue[pos-1]

    def segment(self, start: int, end: int) -> "SongQueue":
        """
        Analogous to slicing, return a SongQueue with songs from track positions start to
        end, inclusive. Instead of raising an exception, break upon encountering an
        out-of-range position.
        """
        new_sq = self.__class__()
        for pos in range(start, end+1):
            try:
                new_sq.add_song(self.at(pos))
            except IndexError:
                break
        return new_sq

    ### MANAGEMENT ###

    def add_song(self, song: Song) -> None:
        self._queue.append(song)

    def get_song(self, search: str) -> Optional[Song]:
        """
        Attempt to search and return the first song whose title contains search.
        Return None if none found.
        """
        search = search.lower()  # Ignore case
        for song in self:
            if search in song.title.lower():
                return song
        return None

    def get_song_pos(self, search: str) -> Optional[int]:
        """
        Attempt to search and return the pos of first song whose title contains search.
        Return None if none found.
        Postcondition: if int is returned, it is a valid pos in the queue.
        """
        search = search.lower()  # Ignore case
        for pos in range(1, len(self)+1):
            if search in self.at(pos).title.lower():
                return pos
        return None

    def pop_song(self, pos: int) -> Union[Song, NoReturn]:
        """Attempt to remove and return a Song from the queue, by track position."""
        song = self.at(
            pos)  # Use this so it can appropriately raise custom IndexError
        self._queue.pop(pos-1)  # The actual removing
        return song

    def pop_range(self, pos1: int, pos2: int) -> list[Song]:
        """Remove and return Songs between positions pos1 and pos2, inclusive."""

        # Use slice to not raise any exception
        # -1 offset for array counting, but not on pos2 b/c we want it to be inclusive
        s = slice(pos1-1, pos2)
        songs = self._queue[s]  # Save copy of segment
        del self._queue[s]
        return songs

    def remove_song(self, name: str) -> Union[Song, NoReturn]:
        """Attempt to remove and return a Song from the queue, by name."""
        for song in self:
            if name.lower() in song.title.lower():
                self._queue.remove(song)
                return song
        else:
            raise KeyError(
                f"could not find Song whose title contains substring '{name}'")

    def clear_queue(self) -> int:
        """Clear the queue and returns number of Songs cleared."""
        num = len(self)
        self._queue.clear()
        return num

    def swap_pos(self, pos1: int, pos2: int) -> Union[tuple[Song, Song], NoReturn]:
        """Attempt to swap Songs at pos1 and pos2 in queue."""
        swapped_songs = (self.at(pos1), self.at(
            pos2))  # Can raise custom IndexError

        # The actual swapping
        temp = self._queue[pos1-1]
        self._queue[pos1-1] = self._queue[pos2-1]
        self._queue[pos2-1] = temp

        return swapped_songs

    def shuffle(self, pos: int = 0) -> None:
        """Shuffle the sequence of songs AFTER pos."""
        # Handle bad arg
        pos = max(0, pos)

        # Returns a copy; shuffle won't mutate self._queue
        tail = self._queue[pos:]
        random.shuffle(tail)  # In-place shuffle
        self._queue[pos:] = tail

    ### SAVING & LOADING ###

    # UNTESTED
    def as_dict(self) -> dict[str, list[str]]:
        """
        Return the single-item dict representation of self, mapping name to list of song IDs:
        {name: ["xxxxxxxxxxx", "xxxxxxxxxxx", ...]}
        """
        return {self.name: [song.id for song in self]}

    # UNTESTED
    @staticmethod
    def to_json(sqs: Iterable["SongQueue"], filepath: str) -> None:
        """Save the collection of SongQueues sqs as a json file to filepath."""
        payload = {"PLAYLISTS": [sq.as_dict() for sq in sqs]}
        with open(filepath, "wt", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

    # UNTESTED
    @staticmethod
    def from_json(filepath: str, name: str) -> Optional[tuple[str, list[str]]]:
        """
        Search for a saved queue named name in the json file at filepath.
        Return a 2-tuple with the song the queue was saved as and the list of song IDs.
        Return None if could not find any saved queue whose name matches param name, case-
        insensitive.
        """
        with open(filepath, "rt", encoding="utf-8") as file:
            payload = json.load(file)
        queues = payload["PLAYLISTS"]   # list[dict[str, list[str]]]
        for queue in queues:
            saved_name, ids = queue.popitem()
            if saved_name.lower() == name.lower():
                return (saved_name, ids)
        return None

    @classmethod
    def get_names(cls, filepath: str) -> list[str]:
        """Return a list of the names of all the save queues in the file."""
        name_pattern = r"\{.*\}"
        with open(filepath, "rt", encoding="utf-8") as file:
            content = file.read()
        spans = (match.span() for match in re.finditer(name_pattern, content))
        return [content[s[0]+1: s[1]-1] for s in spans]

    @classmethod
    def get_saved_contents(cls, filepath: str, name: str) -> Optional[tuple[str, list[str]]]:
        """
        Search for the first saved queue named name in file and returns a tuple containing the
        name the queue was saved with and a list of the saved YouTube video IDs. Return None if
        name did not match any saved names, case-insensitive.
        """

        # Replace placeholders
        pattern = cls.QUEUE_PATTERN.format(
            name=name, video_id=cls.VIDEO_ID_PATTERN)
        # Case insensitive matching
        re_obj = re.compile(pattern, re.IGNORECASE)

        with open(filepath, "rt", encoding="utf-8") as file:
            content = file.read()
            match = re_obj.search(content)

            if match is None:
                return None

            sl = slice(*match.span())   # tuple[int, int] -> slice
            queue_repr = content[sl]

        # Parse queue_repr
        lines = queue_repr.splitlines()
        first_line = lines[0]
        queue_name = first_line[1:first_line.index("}")]

        song_ids = []  # list[str]
        for i in range(1, len(lines)):  # Ignore name line
            song_ids.append(lines[i].removesuffix("}"))

        # Empty queue
        if song_ids[-1] == "":
            song_ids.pop()  # Make song_ids an empty list

        return (queue_name, song_ids)

    @classmethod
    def get_repr_span(cls, filepath: str, name: str) -> Optional[tuple[int, int]]:
        """Return the start and end index of the repr of the SongQueue named name in file."""

        # Replace placeholders
        pattern = cls.QUEUE_PATTERN.format(
            name=name, video_id=cls.VIDEO_ID_PATTERN)
        # Case insensitive matching
        re_obj = re.compile(pattern, re.IGNORECASE)

        with open(filepath, "rt", encoding="utf-8") as file:
            content = file.read()
            match = re_obj.search(content)

            if match is None:
                return None

            return match.span()
