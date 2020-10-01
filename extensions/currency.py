import typing
import random

import discord
from discord.ext import commands

from .utils import *


class Currency(BaseCog):
    "Earn and spend Breqcoins!"

    @commands.command()
    @commands.guild_only()
    @passfail
    async def balance(self, ctx, user: typing.Optional[discord.User]):
        "Check your current coin balance :moneybag:"
        if user is None:
            user = ctx.author
        coins = self.redis.get(f"currency:balance:{ctx.guild.id}:{user.id}")
        if coins is None:
            self.redis.set(f"currency:balance:{ctx.guild.id}:{user.id}", 0)
            coins = 0
        return f"{user.display_name} has **{coins}** Breqcoins."

    @commands.command()
    @commands.guild_only()
    @passfail
    async def pay(self, ctx, user: discord.User, amount: int):
        "Give coins to another user :incoming_envelope:"
        balance = self.redis.get(
            f"currency:balance:{ctx.guild.id}:{ctx.author.id}") or "0"

        if amount < 0:
            raise Fail(f"Nice try {ctx.author.mention}, you cannot steal coins.")

        if int(balance) < amount:
            raise Fail("Not enough coins!")
            return

        self.redis.decr(
            f"currency:balance:{ctx.guild.id}:{ctx.author.id}", amount)
        self.redis.incr(f"currency:balance:{ctx.guild.id}:{user.id}", amount)

    @commands.command()
    @commands.guild_only()
    @passfail
    async def shop(self, ctx):
        "List items in the shop :shopping_bags:"

        item_uuids = self.redis.smembers(f"shop:items:{ctx.guild.id}")
        shop_items = {uuid: Item.from_redis(self.redis, uuid)
                      for uuid in item_uuids}
        prices = {}

        missing = []
        for uuid, item in shop_items.items():
            if isinstance(item, MissingItem):
                missing.append(uuid)
                self.redis.srem(f"shop:items:{ctx.guild.id}", uuid)

        for uuid in missing:
            self.redis.delete(f"shop:prices:{ctx.guild.id}:{item_uuid}")
            del shop_items[uuid]

        for item_uuid in item_uuids:
            prices[item_uuid] = self.redis.get(
                f"shop:prices:{ctx.guild.id}:{item_uuid}")

        embed = discord.Embed(title=f"Items for sale on {ctx.guild.name}")

        if prices:
            embed.description = "\n".join(
                f"{shop_items[uuid].name}: {prices[uuid]} coins"
                for uuid in shop_items.keys())
        else:
            embed.description = "The shop is empty for now."

        return embed

    @commands.command()
    @commands.guild_only()
    @passfail
    async def buy(self, ctx, item: str, amount: typing.Optional[int] = 1):
        "Buy an item from the shop :coin:"

        item = Item.from_name(self.redis, ctx.guild.id, item)

        price_ea = self.redis.get(f"shop:prices:{ctx.guild.id}:{item.uuid}")
        if price_ea is None:
            raise Fail("Item is not for sale!")

        price = int(price_ea) * amount
        balance = int(self.redis.get(
            f"currency:balance:{ctx.guild.id}:{ctx.author.id}") or 0)

        if balance < price:
            raise Fail("Not enough coins!")

        self.redis.decr(
            f"currency:balance:{ctx.guild.id}:{ctx.author.id}", price)
        self.redis.hincrby(
            f"inventory:{ctx.guild.id}:{ctx.author.id}", item.uuid, amount)

    @commands.command()
    @commands.guild_only()
    @commands.check(shopkeeper_only)
    @passfail
    async def list(self, ctx, item: str, price: int):
        "List an item in the shop :new:"
        item = Item.from_name(self.redis, ctx.guild.id, item)
        self.redis.sadd(f"shop:items:{ctx.guild.id}", item.uuid)
        self.redis.set(f"shop:prices:{ctx.guild.id}:{item.uuid}", price)

    @commands.command()
    @commands.guild_only()
    @commands.check(shopkeeper_only)
    @passfail
    async def delist(self, ctx, item: str):
        "Remove an item from the shop :no_entry:"
        item = Item.from_name(self.redis, ctx.guild.id, item)
        self.redis.srem(f"shop:items:{ctx.guild.id}", item.uuid)
        self.redis.delete(f"shop:prices:{ctx.guild.id}:{item.uuid}")

    @commands.command()
    @commands.guild_only()
    @passfail
    async def roulette(self, ctx, bet: str, wager: str):
        "Gamble coins - will you earn more, or lose them all?"

        balance = int(self.redis.get(f"currency:balance:{ctx.guild.id}:{ctx.author.id}"))

        if wager == "all":
            wager = balance
        elif wager == "none":
            wager = 0
        elif wager == "half":
            wager = balance // 2
        else:
            try:
                wager = int(wager)
            except ValueError:
                raise Fail(f"Invalid wager: {wager}")

        if wager > balance:
            raise Fail("You cannot wager more than you have.")
        if wager < 0:
            raise Fail("Wager must be a positive number.")

        if bet not in ("red", "black", "even", "odd", "high", "low"):
            try:
                bet = int(bet)
            except ValueError:
                raise Fail(f"Invalid bet: {bet}")

        self.redis.decr(f"currency:balance:{ctx.guild.id}:{ctx.author.id}", wager)

        wheel = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

        red = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        black = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]

        ball = random.choice(wheel)

        color = "red" if ball in red else "black" if ball in black else "green"
        parity = "none" if ball == 0 else "even" if ball % 2 == 0 else "odd"
        range = "high" if ball >= 19 else "low" if ball >= 1 else "none"

        color_emoji = {
            "red": "🟥",
            "black": "⬛",
            "green": "🟩"
        }

        message = await ctx.send(f"{ball}: {color_emoji[color]}")

        if bet == color:
            winnings = wager * 2
        elif bet == parity:
            winnings = wager * 2
        elif bet == range:
            winnings = wager * 2
        elif bet == ball:
            winnings = wager * 36
        else:
            winnings = 0

        self.redis.incr(f"currency:balance:{ctx.guild.id}:{ctx.author.id}", winnings)

        if winnings > 0:
            return f"You win **{winnings - wager}** coins!"
        else:
            return f"You lost **{wager}** coins."


def setup(bot):
    bot.add_cog(Currency(bot))
