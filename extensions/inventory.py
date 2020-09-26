import typing
import os

import discord
from discord.ext import commands

from .utils import *


class Inventory(BaseCog):
    "Store items from the shop"

    @commands.command()
    @commands.guild_only()
    @passfail
    async def inventory(self, ctx, user: typing.Optional[discord.User]):
        "List items in your current inventory :dividers:"
        if user is None:
            user = ctx.author

        embed = discord.Embed(title=f"{user.name}'s Inventory")

        inventory = self.redis.hgetall(f"inventory:{ctx.guild.id}:{user.id}")
        amounts = {Item.from_redis(self.redis, item): int(amount)
                   for item, amount in inventory.items() if int(amount) > 0}

        balance = (
            self.redis.get(f"currency:balance:{ctx.guild.id}:{user.id}") or 0)

        embed.description = (f"*Breqcoins: {balance}*\n"
                             + "\n".join(f"{item.name}: **{amount}**"
                                         for item, amount in amounts.items()))

        return embed

    @commands.command()
    @commands.guild_only()
    @passfail
    async def give(self, ctx, user: discord.User, item: str,
                   amount: typing.Optional[int] = 1):
        "Give an item to another user :incoming_envelope:"
        item = self.get_item(item)
        self.ensure_item(ctx, ctx.author, item, amount)

        self.redis.hincrby(
            f"inventory:{ctx.guild.id}:{ctx.author.id}", item.uuid, -amount)
        self.redis.hincrby(
            f"inventory:{ctx.guild.id}:{user.id}", item.uuid, amount)

    @commands.command()
    @commands.guild_only()
    @passfail
    async def use(self, ctx, item: str):
        "Use an item [TESTING]"
        item = self.get_item(item)
        self.ensure_item(ctx, ctx.author, item)

        # self.redis.hincrby(f"inventory:{ctx.guild.id}:{ctx.author.id}",
        #                    item.uuid, -1)

        return f"You used {item.name}. It did nothing!"

    @commands.command()
    @commands.check(config_only)
    @passfail
    async def divine_gift(self, ctx, item: str, guild_id: int, user_id: int):
        "Give a user an item on that server."
        item = Item.from_name(self.redis, item)
        self.redis.hincrby(f"inventory:{guild_id}:{user_id}", item.uuid)


def setup(bot):
    bot.add_cog(Inventory(bot))
