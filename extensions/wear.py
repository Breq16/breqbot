import typing

import discord
from discord.ext import commands

from .utils import *


class Wear(BaseCog):
    "Wear the items in your inventory"

    @commands.command()
    @commands.guild_only()
    @passfail
    async def wear(self, ctx, item: str):
        "Wear an item :lab_coat:"
        item = Item.from_name(self.redis, ctx.guild.id, item)

        if not int(item.wearable):
            raise Fail("Item is not wearable!")
        self.ensure_item(ctx, ctx.author, item)

        wearing = self.redis.sismember(
            f"wear:{ctx.guild.id}:{ctx.author.id}", item.uuid)

        if wearing:
            raise Fail(f"You are already wearing a {item.name}!")

        self.redis.hincrby(
            f"inventory:{ctx.guild.id}:{ctx.author.id}", item.uuid, -1)
        self.redis.sadd(f"wear:{ctx.guild.id}:{ctx.author.id}", item.uuid)

    @commands.command()
    @commands.guild_only()
    @passfail
    async def takeoff(self, ctx, item: str):
        "Take off an item :x:"
        item = Item.from_name(self.redis, ctx.guild.id, item)

        wearing = self.redis.sismember(
            f"wear:{ctx.guild.id}:{ctx.author.id}", item.uuid)

        if not wearing:
            raise Fail(f"You are not wearing a {item.name}!")

        self.redis.hincrby(
            f"inventory:{ctx.guild.id}:{ctx.author.id}", item.uuid, 1)
        self.redis.srem(f"wear:{ctx.guild.id}:{ctx.author.id}", item.uuid)

    @commands.command()
    @commands.guild_only()
    @passfail
    async def outfit(self, ctx, user: typing.Optional[discord.User]):
        "List the items that a user is wearing :lab_coat:"
        if user is None:
            user = ctx.author

        embed = discord.Embed(title=f"{user.name} is wearing...")

        items = [Item.from_redis(self.redis, uuid)
                 for uuid in self.redis.smembers(
                     f"wear:{ctx.guild.id}:{user.id}")]

        missing = []
        for item in items:
            if isinstance(item, MissingItem):
                missing.append(item)
                self.redis.srem(f"wear:{ctx.guild.id}:{user.id}", item.uuid)

        items = [item for item in items if item not in missing]

        if items:
            embed.description = "\n".join(f"• {item.name} ({item.desc})"
                                          for item in items)
        else:
            embed.description = (f"{user.name} does not have any swag. "
                                 f"`{self.bot.command_prefix}give` them some?")

        return embed


def setup(bot):
    bot.add_cog(Wear(bot))