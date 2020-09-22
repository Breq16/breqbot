import os
import typing

import redis
import discord
from discord.ext import commands

prefix = os.getenv("BOT_PREFIX") or ";"

activity = discord.Game(f"{prefix}help | breq.dev")
breqbot = commands.Bot(prefix, description="Hi, I'm Breqbot! Beep boop :robot:", activity=activity)

breqbot.redis = redis.Redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)

# General
breqbot.load_extension("cogs.info")
breqbot.load_extension("cogs.reddit")
breqbot.load_extension("cogs.minecraft")
breqbot.load_extension("cogs.vex")
breqbot.load_extension("cogs.comics")
breqbot.load_extension("cogs.soundboard")
breqbot.load_extension("cogs.things")

# Economy/shop/outfits
breqbot.load_extension("cogs.currency")
breqbot.load_extension("cogs.inventory")
breqbot.load_extension("cogs.quests")
breqbot.load_extension("cogs.wear")

# Utility
breqbot.load_extension("cogs.help_command")
breqbot.load_extension("cogs.guild_watch")

breqbot.run(os.getenv("DISCORD_TOKEN"))
