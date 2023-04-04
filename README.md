# Discord Bot Project

Backup for my discontinued Discord bot project, which was initially developed as
a loose clone of the former [Groovy bot](https://groovy.bot/).

There's little commit history because the contents of the repository were copied
over to a new one before pushing to GitHub. This is because I accidentally
exposed sensitive credentials like the bot token, AWS secrets, etc. when I
returned to clean up the code and make it more presentable. That mistake aside,
I performed some refactors, including:

* Migrating to [discord.py
  v2](https://discordpy.readthedocs.io/en/stable/migrating.html#migrating-to-v2-0).
* Organizing the source files into a Python package (also managed by
  [pyproject.toml](pyproject.toml) instead of the legacy requirements.txt
  approach).
* Use better practices, such as improved
  [logging](https://docs.python.org/3/library/logging.html) and opting for
  the more conventional .env file instead of the previous metadata.json file.


## Features


### Music Player

* Streaming audio from YouTube with the
  [yt_dlp](https://github.com/yt-dlp/yt-dlp) library.
* Managing the audio queue with commands and embed responses heavily inspired by
  Groovy. In fact, this project started in part as a way to have multiple music
  bots in my friend's server at once, so I attempted to reverse-engineer
  Groovy's behavior.
* Saving, loading, and viewing playlist as saved queues, although implementation
  was quite primitive and functionality quite limited as it was the first time I
  used 3rd party object storage, namely AWS S3.


### Convenience Commands

* Various tools that assisted me personally in my school life, such as Python
  `eval` and REPL commands (which I know now are a security hazard without
  proper sanitization), pulling up data from
  [PubChem](https://pubchem.ncbi.nlm.nih.gov/), currency conversions, etc.
* Some commands related to the [Mudae
  bot](https://discord.bots.gg/bots/432610292342587392), which some of my
  friends and I were obsessed with at the time.
* Easter egg features like making the bot `annoy` a user by replying to
  everything they say, reciting the [Tragedy of Darth Plagueis the
  Wise](https://knowyourmeme.com/memes/the-tragedy-of-darth-plagueis-the-wise),
  etc.


## History

An instance of my bot had been running on Heroku since March 2021, and my
friends and I used it on our private Discord server since then until November
28, 2022, the day [Heroku shut down its free
tier](https://blog.heroku.com/next-chapter). Now, the bot only runs when I run
it manually on my local machine.

This bot had been my passion project for some time, and any feature that made me
think "but what if I could do xyz without having to leave the Discord app?" was
the next new idea. Unfortunately, I eventually lost interest (in coding
altogether, for some time) and did not want to continue maintaining a codebase
that was the most complex I've ever dealt with in my hobbyist career.

I was also hesistant to return even after I rekindled my love for coding because
by then I had learned much more and realized how many poor practices my code
exhibited, and it seemed too daunting to refactor. I eventually came back to
bring some aspects of the codebase up to my new standards, but the core
implementation remains as legacy code that I'll leave be for now.

I think writing code that works but is so utterly garbage is an indispensable
experience every coder goes through, so I've decided after a long time to put
this repository in public display as one monument of many to come in my coding
journey and as a reminder to myself to keep pushing for cleaner code.


## Setup

As usual, you can recreate the Python environment with:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The program is run by invoking the package as a module from within the
[src](src/) directory:

```sh
cd src && python -m bot
# Or use the Makefile rule:
make
```

To use voice capabilities, you must have [FFmpeg](https://ffmpeg.org/) installed
and on your `PATH`.


### Heroku Deployment (Legacy)

The link to my Heroku app (only accessibly to me, obviously) is:

https://dashboard.heroku.com/apps/tacobot-py-alt

As a reminder to myself, this application belongs to the account using my UCLA
school email.

The process also involved setting up the required buildpacks, notably the one
for [FFmpeg](https://elements.heroku.com/buildpacks/jonathanong/heroku-buildpack-ffmpeg-latest).


## Environment Recovery

If for whatever reason I lose my local copy, two [.gitignore](.gitignore)'d
files need to be replaced:

**.env**

The required key names are:

* `TACOBOT_TOKEN`: the Discord bot token, which can be regenerated on the
  [developer portal](https://discord.com/developers/applications).
* `TESTER_TOKEN`: alternate Discord bot token, similar to above.
* `AWS_ACCESS_KEY`: access key for this application, which can be found/regenerated on the
  [IAM
  console](https://us-east-1.console.aws.amazon.com/iamv2/home#/security_credentials).
* `AWS_SECRET_KEY`: secret key for this application, similar to above.
* `CURRENCYSCOOP_KEY`: API key for CurrencyScoop (renamed CurrencyBeacon), which
  can be found at [account settings](https://currencybeacon.com/account).
* `DEV_USER_ID`: my Discord user ID, which can be found by enabling Developer
  Mode and right clicking my user profile and selecting Copy ID.

API tokens or secrets can be found or regenerated on their respective developer
portals.

**src/bot/names.py**

The constants are:

```python
# Mapping of ID to real names for some of my friends
REAL_NAMES: dict[int, str]

MUDAE_ID: int  # ID of the Mudae bot
BORG_ID: int  # My alt account ID
VIN_ID: int  # My ID
LH_ID: int  # My friend's server, LoudHouse
TSC_ID: int  # A testing server, Tofu Soup Congress
```
