import os
import time
import typing

import discord
from discord.ext import commands

import redis

class Currency(commands.Cog):
    GET_COINS_INTERVAL = 3600
    GET_COINS_AMOUNT = 10

    def __init__(self, bot):
        self.bot = bot
        self.redis = redis.Redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)

    @commands.command()
    async def balance(self, ctx, user: typing.Optional[discord.User]):
        "Check your current coin balance!"
        if ctx.guild is None:
            return

        if user is None:
            user = ctx.author
        coins = self.redis.get(f"currency:balance:{ctx.guild.id}:{user.id}")
        if coins is None:
            self.redis.set(f"currency:balance:{ctx.guild.id}:{user.id}", 0)
            coins = 0
        await ctx.send(f"{user.name} has **{coins}** Breqcoins.")

    @commands.command()
    async def get_coins(self, ctx):
        "Get more money"
        if ctx.guild is None:
            return

        last_daily = float(self.redis.get(f"currency:get_coins:latest:{ctx.guild}:{ctx.author.id}") or 0)
        current_time = time.time()
        time_until = (last_daily + Currency.GET_COINS_INTERVAL) - current_time
        if time_until > 0:
            ftime = time.strftime("%H:%M:%S", time.gmtime(time_until))
            await ctx.send(f"{ctx.author.name}, you must wait **{ftime}** to claim more coins!")
            return

        ftime = time.strftime("%H:%M:%S", time.gmtime(Currency.GET_COINS_INTERVAL))

        self.redis.set(f"currency:get_coins:latest:{ctx.guild.id}:{ctx.author.id}", current_time)
        self.redis.incr(f"currency:balance:{ctx.guild.id}:{ctx.author.id}", Currency.GET_COINS_AMOUNT)

        await ctx.send(f"{ctx.author.name}, you have claimed **{Currency.GET_COINS_AMOUNT}** coins! Wait {ftime} to claim more.")

    @commands.command()
    async def give_coins(self, ctx, user: discord.User, amount: int):
        "Give coins to another user"
        balance = self.redis.get(f"currency:balance:{ctx.guild.id}:{ctx.author.id}")

        if int(balance) < amount:
            await ctx.send("Not enough coins!")
            return

        self.redis.decr(f"currency:balance:{ctx.guild.id}:{ctx.author.id}", amount)
        self.redis.incr(f"currency:balance:{ctx.guild.id}:{user.id}", amount)

        await ctx.send("Transaction successful!")

    @commands.command()
    async def inventory(self, ctx, user: typing.Optional[discord.User]):
        "List items in your current inventory!"
        if ctx.guild is None:
            return
        if user is None:
            user = ctx.author

        items = self.redis.smembers(f"currency:shop:items:{ctx.guild.id}")

        amounts = {}

        for item in items:
            quantity = int(self.redis.get(f"currency:shop:inventory:{ctx.guild.id}:{user.id}:{item}") or 0)
            if quantity > 0:
                amounts[item] = quantity

        if amounts:
            await ctx.send(f"{user.name}'s Inventory:\n"
                           + "\n".join(f"{k}: {v}" for k, v in amounts.items()))
        else:
            await ctx.send(f"{user.name}'s inventory is empty.")

    @commands.command()
    async def shop(self, ctx):
        "List items in the shop!"

        items = self.redis.smembers(f"currency:shop:items:{ctx.guild.id}")
        prices = {}

        for item in items:
            prices[item] = self.redis.get(f"currency:shop:prices:{ctx.guild.id}:{item}")

        if prices:
            await ctx.send(f"Items for sale on {ctx.guild.name}:\n"
                           + "\n".join(f"{k}: {v}\n" for k, v in prices.items()))
        else:
            await ctx.send(f"The shop on {ctx.guild.name} is empty!")

    @commands.command()
    async def buy(self, ctx, item: str):
        "Buy an item!"

        exists = self.redis.sismember(f"currency:shop:items:{ctx.guild.id}", item)
        if not exists:
            await ctx.send("Invalid item!")
            return

        price = self.redis.get(f"currency:shop:prices:{ctx.guild.id}:{item}")
        balance = self.redis.get(f"currency:balance:{ctx.guild.id}:{ctx.author.id}") or 0

        if int(balance) < int(price):
            await ctx.send("Not enough coins!")
            return

        self.redis.decr(f"currency:balance:{ctx.guild.id}:{ctx.author.id}", price)
        self.redis.incr(f"currency:shop:inventory:{ctx.guild.id}:{ctx.author.id}:{item}")

        await ctx.send("Transaction successful!")

    @commands.command()
    async def give_item(self, ctx, user: discord.User, item: str):
        "Give an item to another user"

        exists = self.redis.sismember(f"currency:shop:items:{ctx.guild.id}", item)
        if not exists:
            await ctx.send("Invalid item!")
            return

        amount = int(self.redis.get(f"currency:shop:inventory:{ctx.guild.id}:{ctx.author.id}:{item}") or 0)
        if amount < 1:
            await ctx.send("You don't have that item!")
            return

        self.redis.decr(f"currency:shop:inventory:{ctx.guild.id}:{ctx.author.id}:{item}")
        self.redis.incr(f"currency:shop:inventory:{ctx.guild.id}:{user.id}:{item}")

        await ctx.send("Transaction successful!")

    # @commands.command()
    # async def list(self, ctx, item: str, price: int):
    #     "List an item in the store!"
    #
    #     self.redis.sadd(f"currency:shop:items:{ctx.guild.id}", item)
    #     self.redis.set(f"currency:shop:prices:{ctx.guild.id}:{item}", price)
    #     await ctx.send("Item listed!")
    #
    # @commands.command()
    # async def delist(self, ctx, item: str):
    #     "Remove an item from the store"
    #
    #     self.redis.srem(f"currency:shop:items:{ctx.guild.id}", item)
    #     self.redis.delete(f"currency:shop:prices:{ctx.guild.id}:{item}")
    #     await ctx.send("Item delisted!")


def setup(bot):
    bot.add_cog(Currency(bot))
