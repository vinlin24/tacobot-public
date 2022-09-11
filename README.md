## Description

Backup for my discontinued Discord bot project. There's little commit history because the contents of the repository was copied over to a new one before pushing to GitHub. This is because previous commits exposed sensitive credentials like the bot token, AWS secrets, etc.

An instance of my bot has been running on Heroku since March 2021, and my friends and I have been using it on our private Discord server since then. It will continue to run undisturbed until November 28, 2022, the day [Heroku will shut down its free tier](https://blog.heroku.com/next-chapter). I have given this bot one final update, v2.2.9, only modifying the source code in areas that naively saved sensitive information as constants instead of environment variables.

Basic features of the bot include:

- Streaming audio from YouTube with the [youtube-dl](https://github.com/ytdl-org/youtube-dl) library.
- Managing the audio queue with commands and embed responses heavily inspired by the discontinued [Groovy bot](https://groovy.bot/). In fact, this project started in part as a way to have multiple music bots in my friend's server at once, so I attempted to reverse-engineer Groovy's behavior.
- Saving, loading, and viewing playlist as saved queues, although implementation was quite primitive and functionality quite limited as it was the first time I used 3rd party object storage, namely AWS S3.
- Various tools that assisted me personally in my school life, such as Python `eval` and REPL commands (which I know now are a security hazard without proper sanitization), pulling up data from [PubChem](https://pubchem.ncbi.nlm.nih.gov/), currency conversions, etc.
- Some commands related to the [Mudae bot](https://discord.bots.gg/bots/432610292342587392), which some of my friends and I were obsessed with at the time. Not sure if these features even work anymore.
- Easter egg features like making the bot `annoy` a user by replying to everything they say, reciting the [Tragedy of Darth Plagueis the Wise](https://knowyourmeme.com/memes/the-tragedy-of-darth-plagueis-the-wise), etc.

## History

This bot had been my passion project for some time, and any feature that made me think "but what if I could do xyz without having to leave the Discord app?" was the next new idea. Unfortunately, I eventually lost interest (in coding altogether, for some time) and did not want to continue maintaining a codebase that was the most complex I've ever dealt with in my hobbyist career.

I was also hesistant to return even after I rekindled my love for coding because by then I had learned much more and realized how many poor practices my code exhibited, and it seemed too daunting to refactor.

I figured it would be easier to start from scratch, so I've been working on a successor, [tacocat](https://github.com/vinlin24/tacocat), but depending on how much progress I make with it, I might just decide to refactor and resume development on this existing code.

I think writing code that works but is so utterly garbage is an indispensable experience every coder goes through, so I've decided after a long time to put this repository in public display as one monument of many to come in my coding journey and as a reminder to myself to keep pushing for cleaner code.

## Environment Recovery

If for whatever reason I lose my local copy, three [.gitignore](.gitignore)'d files need to be replaced:

**/files/.env**

The required key names are:

- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `SPOTIFY_REDIRECT_URI`
- `SPOTIFY_REFRESH_TOKEN`

**/files/metadata.json**

The schema is:

```json
{
  "TESTER_MODE": "<bool>",
  "ON_HEROKU": "<bool>",
  "VERSION_STRING": "<string>",
  "COMMAND_PREFIX": "<string>",
  "TESTER_PREFIX": "<string>",
  "TACOBOT_TOKEN": "<string>",
  "TESTER_TOKEN": "<string>",
  "AWS_ACCESS_KEY": "<string>",
  "AWS_SECRET_KEY": "<string>",
  "CURRENCYSCOOP_KEY": "<string>"
}
```

API tokens or secrets can be found or regenerated on their respective developer portals.

**/names.py**

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

Dependencies are tracked with [requirements.txt](requirements.txt). I just recently replaced the content of the file with the output of running `pip freeze` on the Heroku console since some libraries may have undergone breaking changes since my last update, most notably the [v2 release of the discord.py framework](https://pypi.org/project/discord.py/2.0.0/). As usual, you can recreate the environment with:

```powershell
python -m venv .venv
.venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

The link to my Heroku app (only accessibly to me, obviously) is:

https://dashboard.heroku.com/apps/tacobot-py-alt

As a reminder to myself, this application belongs to the account using my UCLA school email.

> The "alt" in the app name is an indicator of this. Long story short, I had been alternating between two Heroku accounts to get 100% uptime for my Heroku apps, and when TacoBot became the last app in use, the last (and currently) running instance was on my alt account. The copy on my "main" account is several versions behind and has been abandoned since.
