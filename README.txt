Discord Bot - TacoBot by Vincent Lin.
Designed to be uploaded to Heroku and run indefinitely.

[v2.2.0] Update Notes (previous: v2.1.0)

Started using README.txt to store update notes.
Added %addqueue.
	Restructured %loadqueue.
	Added get_mention() function to helper module.
	Currently, %addqueue will cancel the loading of another queue if it's taking place.
Added %updatenotes.
Revamped %queue.
	Abstracted chunks of code into helper methods.
	Replaced the "home" emoji with the "refresh" emoji.
	Reacting to the "refresh" emoji now updates the queue pages and sets display to the page with the current song.
	Changed the order of emojis added to: 🔄⏫⬆⬇⏬; 🔄 will be added for any number of pages.
Made %clear also reset the queue name.
Removed asking for confirmation for %shuffleloop.
Tweaked logger format to use %(module)s instead of %(name)s and removed %(lineno)d.
Made helper module available in %scripteval namespace.
Moved all remaining commands in main.py into their own cogs.
	Made Moderator, Misc, and Mudae cogs.
	Brought %annoy back.
Moved bot event registration to its own module, events.py.
	Moved helper function load_s3() to events.py.
Began implementing %nowplaying, but it is currently nonfunctional.
Fixed embeds not working for some commands: forgot to change music_embed -> make_embed.

[v2.2.1] Update Notes (previous: v2.2.0)

Fixed %annoy using "None" as the real name for users not in helper.REAL_NAMES.
Created Utils cog.
Added %eval.
	Imported pprint.pprint, pprint.pformat into helper.
Added %repl.
	Updated on_message bot listener to ignore commands in REPL sessions.
	Imported os and sys modules into helper.

[v2.2.2] Update Notes (previous: v2.2.1)

Moved %analyze from the Misc to the Utils cog.
Created Mathematics cog.
Added %rref.
	Added sympy to list of required dependencies.
Added %anagrams.
	Added words.txt to files; source: https://raw.githubusercontent.com/dwyl/english-words/master/words.txt.
Fixed %eval and %repl.
	Now clears buffer to not display lingering text in text_to_print from print() in previous %eval calls.
	Now displays values in repr form when not displayed through print().

[v2.2.3] Update Notes (previous: v2.2.2)

Fixed case-sensitivity in %anagrams: now matches words with different case.
Made param word for %anagrams a kwonly param: spaces are now allowed in the argument.
Created Chemistry cog.
Added %pubchem.
	Added pubchempy to list of required dependencies.
	Added generate_url() to amazons3.py.
Changed timeout for reaction-removing messages from 120 to 180 seconds.
Added aliases for various commands.

[v2.2.4] Update Notes (previous: v2.2.3)

Updated on_command_error to handle exceptions raised by bad user input.
Added (god command) %restart.
	Moved helper function ask_for_confirmation() to helper module.
	Updated Music cog and MusicPlayer class to use updated ask_for_confirmation().
Added (god command) %abort.
Added %currency.
	Added exchange_rates.json to files.
	Updated metadata.json to include CurrencyScoop API key.

[v2.2.5] Update Notes (previous: v2.2.4)

Created option to run in tester mode (with a different token and prefix, to not conflict with bot running on Heroku)
	Added various entries to metadata.json.
	Restructured load_metadata() and init_bot() in main.py.
Updated %kakeravalue to use the last detected number of characters claimed in server.
	Added cog-specific listener on_message() to Mudae cog.
	Added mudae_data.json to files and to tacobot bucket on AWS S3.
Updated %nowplaying to display hyperlinked song title, total duration, and requester.

[v2.2.6] Update Notes (previous: v2.2.5)

Added %exchanges.
%nowplaying now displays the position of the song in the queue.
Fixed %playereval: self.SENSITIVE_KEYS -> helper.SENSITIVE_KEYS.

[v2.2.7] Update Note (previous: v2.2.6)

Added %sad to automatically add current Spotify track to my playlist(s).
	Added tekore dependency to requirements.txt for Spotify API usage
This works for myself only and I only added it because I wanted to automate something.
This bot is unlikely to see any productive updates as it has been discontinued.

[v2.2.8] Update Note (previous: v2.2.7)

Changed bot token because my dumbass exposed it on GitHub by accident.

[v2.2.9] Update Note (previous: v2.2.8)

Final update. Hid sensitive values in source code to prepare to display repository publicly.
