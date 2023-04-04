"""
# TacoBot

Discord Bot project, initially developed as a loose clone of the former
Groovy bot: https://groovy.bot/
"""

import os

import discord
import dotenv

# Project constants.

__author__ = "Vincent Lin"
__version__ = "2.3.0"
"""
I didn't exactly adhere to the true rules of semantic versioning when
this bot was active, so this version string really just helped me sanity
check that a new copy of the source code was deployed.  I left off at
2.2.9, so I guess I'll update it to 2.3.0 since this reorganization is a
major event despite no change in functionality.
"""

# Sensitive environment variables.

dotenv.load_dotenv()
TACOBOT_TOKEN = os.environ["TACOBOT_TOKEN"]
TESTER_TOKEN = os.environ["TESTER_TOKEN"]
AWS_ACCESS_KEY = os.environ["AWS_ACCESS_KEY"]
AWS_SECRET_KEY = os.environ["AWS_SECRET_KEY"]
CURRENCYSCOOP_KEY = os.environ["CURRENCYSCOOP_KEY"]
DEV_USER_ID = int(os.environ["DEV_USER_ID"])

# Bot configuration.

INTENTS = discord.Intents.all()
COMMAND_PREFIX = "%"
TESTER_PREFIX = "&"

# Hard-coded for now for backwards compatibility.

TESTER_MODE = False
ON_HEROKU = False
