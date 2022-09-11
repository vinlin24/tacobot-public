
"""
Entry module. Procfile content should read: 'worker: python main.py'.
Initializes and sets up the Discord bot by registering events and extensions.

<!> Update VERSION_STRING, ON_HEROKU, TESTER_MODE in metadata.json between updates.
<!> Update README.txt between updates.
<!> Uncomment out on_command_error in events.py before pushing.
"""

from typing import *
import json
import os

import discord
from discord.ext import commands

import helper
import events

##### LOGGER #####

logger, *funcs = helper.get_logger(__name__, 10)
# Abbreviate print functions
print, printinf, printwar, printerr, printcrt = funcs

##### BOT INITIALIZATION #####

def load_metadata(path: str) -> dict[str, Union[str, bool]]:
	"""Load json metadata from path and return the data as a Python dict."""
	with open(path, "rt") as file:
		metadata = json.load(file)
	printinf("Loaded metadata")
	return metadata

def load_extensions(bot: commands.Bot, path: str) -> None:
	"""Load all .py modules in path as extensions for bot."""
	printinf("Loading bot extensions...")
	for filename in os.listdir(path):
		if filename.endswith(".py"):
			try:
				# Must use dot notation and exclude .py extension
				bot.load_extension(f"cogs.{filename.removesuffix('.py')}")
			except commands.ExtensionError:
				printcrt(f"FAILED to load {filename} as bot extension")
			# else:
			# 	printinf(f"Loaded {filename} as bot extension")
	printinf("Finished loading bot extensions")

def init_bot() -> commands.Bot:
	"""Package code initializing the Discord bot."""
	metadata = load_metadata("files/metadata.json")

	# Determine what mode the script is in (proper or tester)
	if metadata["TESTER_MODE"]:
		prefix = metadata["TESTER_PREFIX"]
	else:
		prefix = metadata["COMMAND_PREFIX"]

	# Create bot
	intents = discord.Intents().all()
	bot = commands.Bot(command_prefix=prefix, intents=intents, case_insensitive=True)
	
	# Save metadata as attrs so they can be retrieved from any module
	for key, val in metadata.items():
		setattr(bot, key, val)
	printinf("Binded metadata to bot")

	load_extensions(bot, "cogs/")
	events.register_events(bot)

	return bot

##### ENTRY POINT #####

if __name__ == "__main__":
	bot = init_bot()
	token = bot.TESTER_TOKEN if bot.TESTER_MODE else bot.TACOBOT_TOKEN
	bot.run(token)
