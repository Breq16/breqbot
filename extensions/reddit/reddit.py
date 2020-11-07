import json

import discord
from discord.ext import commands, tasks

from ..base import BaseCog, graceful_task
from . import cache


class BaseReddit(BaseCog):
    def __init__(self, bot, config):
        super().__init__(bot)
        self.cache = cache.RedditCache(self.redis, config)
        self.build_cache.start()
        self.prune_history.start()

    @tasks.loop(hours=3)
    @graceful_task
    async def build_cache(self):
        await self.cache.build()

    @tasks.loop(minutes=1)
    @graceful_task
    async def prune_history(self):
        await self.cache.prune_history()

    async def default(self, ctx, sub_config):
        return await self.cache.get(sub_config, ctx.channel.id)

    @commands.command()
    async def reddit(self, ctx, subreddit: str):
        "post from a subreddit of your choice!"
        channel_is_nsfw = ctx.guild and ctx.channel.is_nsfw()
        async with ctx.channel.typing():
            image = await self.cache.get_custom(
                subreddit,
                channel_id=ctx.channel.id,
                nsfw=(None if channel_is_nsfw else False)
            )
        await ctx.send(image)


with open("extensions/reddit/config.json") as f:
    config = json.load(f)


def conditional_decorator(dec, condition):
    def decorator(func):
        if not condition:
            return func
        return dec(func)
    return decorator


def make_command(alias):
    @commands.command(name=alias["command"], brief=alias["desc"])
    @conditional_decorator(commands.is_nsfw(),
                           (alias.get("nsfw") or alias.get("some_nsfw")))
    async def _command(self, ctx):
        ret = await self.default(ctx, alias)
        if isinstance(ret, discord.Embed):
            await ctx.send(embed=ret)
        else:
            await ctx.send(ret)

    return _command


new_attrs = {}
for sub_config in config:
    new_attrs[sub_config["command"]] = make_command(sub_config)

Reddit = type("Reddit", (BaseReddit,), new_attrs)
Reddit.description = "View memes, images, and other posts from Reddit"


def setup(bot):
    bot.add_cog(Reddit(bot, config))
