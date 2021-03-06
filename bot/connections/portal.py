import uuid
import time
import asyncio
import os
import json

import aioredis
import discord
from discord.ext import commands

from bot import base
from bot.economy import itemlib


class Portal(base.BaseCog):
    "Interface with real-world things"

    category = "Connections"

    async def get_portal(self, id, user_id=None):
        portal = await self.redis.hgetall(f"portal:{id}")
        if not portal:
            raise commands.CommandError(f"Portal {id} does not exist.")

        if user_id and int(portal["owner"]) != user_id:
            raise commands.CommandError(f"You do not own the portal {id}.")

        if "price" not in portal:
            portal["price"] = 0

        return portal

    async def set_portal(self, portal):
        id = portal["id"]
        await self.redis.hmset_dict(f"portal:{id}", portal)

        await self.redis.sadd("portal:list", id)
        await self.redis.sadd(f"portal:from_owner:{portal['owner']}", id)

    @commands.group(invoke_without_command=True)
    async def portal(self, ctx, name: str, *, command: str = ""):
        "Send a command to a connected portal"
        job_id = str(uuid.uuid4())

        portal_id = await self.redis.get(
            f"portal:from_name:{ctx.guild.id}:{name}")
        if not portal_id:
            raise commands.CommandError(f"Portal {name} does not exist!")

        portal_name = await self.redis.hget(f"portal:{portal_id}", "name")
        portal_price = await self.redis.hget(
            f"portal:{portal_id}", "price") or 0

        if int(portal_price) > 0:
            async with itemlib.Wallet(ctx.author, ctx.guild, self.redis) \
                    as wallet:
                await wallet.ensure(int(portal_price))

                message = await ctx.send(
                    f"Portal {name} costs **{portal_price} Breqcoins**. "
                    "Confirm purchase?")

                await message.add_reaction("✅")
                await message.add_reaction("❌")

                def check(reaction, user):
                    return (reaction.message.id == message.id
                            and user.id == ctx.author.id
                            and reaction.emoji in ("✅", "❌"))

                try:
                    reaction, user = await self.bot.wait_for(
                        "reaction_add", timeout=120, check=check)
                except asyncio.TimeoutError:
                    return

                await message.clear_reactions()

                if reaction.emoji != "✅":
                    await message.edit(content="Transaction cancelled")
                    return

                await wallet.remove(int(portal_price))
        else:
            message = None

        sub_conn = await aioredis.create_redis(
            os.getenv("REDIS_URL"), encoding="utf-8")
        channel = (await sub_conn.subscribe(f"portal:{portal_id}:{job_id}"))[0]

        query = {
            "type": "query",
            "job": job_id,
            "portal": portal_id,
            "data": command
        }

        clocks = "🕐🕑🕒🕓🕔🕕🕖🕗🕘🕙🕚🕛"

        embed = discord.Embed(title="Waiting for response...")

        if message:
            await message.edit(content="", embed=embed)
        else:
            message = await ctx.send(embed=embed)

        await self.redis.publish_json(
            f"portal:{portal_id}:{job_id}", query)

        async def get_response():
            async for message in channel.iter(decoder=json.loads):
                if message["type"] == "response":
                    return message

        ts = time.time()
        frame = 0

        response_task = asyncio.create_task(get_response())

        while True:
            if time.time() - ts > 120:
                # Connection timed out
                embed.title = "Timed Out"
                embed.description = (f"Portal {portal_name} "
                                     "did not respond in time.")
                await message.edit(embed=embed)
                return

            if frame % 5 == 0:
                clock_index = (frame // 5) % len(clocks)
                clock = clocks[clock_index]
                embed.description = clock
                await message.edit(embed=embed)

            if response_task.done():
                break

            frame += 1

            await asyncio.sleep(0.2)

        response = response_task.result()
        data = response["data"]

        embed = discord.Embed()
        if "title" in data:
            embed.title = data["title"]
        if "description" in data:
            embed.description = data["description"]
        if "image" in data:
            embed.set_image(url=data["image"])

        embed.set_footer(text=f"Connected to Portal: {portal_name}")

        await message.edit(embed=embed)

    @portal.command()
    async def create(self, ctx):
        "Register a new Portal"

        id = str(uuid.uuid4())
        token = str(uuid.uuid4())

        portal = {
            "id": id,
            "name": "A Breqbot Portal",
            "desc": "Example Description",
            "price": 0,
            "owner": ctx.author.id,
            "token": token,
            "status": "0",
        }
        await self.set_portal(portal)

        embed = discord.Embed(title="Portal")
        embed.description = "Thank you for registering a Breqbot portal!"

        embed.add_field(name="Portal ID", value=id, inline=False)
        embed.add_field(name="Portal Token (keep this secret!)",
                        value=f"||{token}||", inline=False)

        await ctx.author.send(embed=embed)
        await ctx.message.add_reaction("✅")

    @portal.command()
    async def retoken(self, ctx, id: str):
        "Regenerate the API token for a portal"

        portal = await self.get_portal(id, ctx.author.id)
        portal["token"] = str(uuid.uuid4())
        await self.set_portal(portal)

        embed = discord.Embed(title="New Portal Token")
        embed.description = "You requested a new token for your portal."

        embed.add_field(name="Portal ID", value=id, inline=False)
        embed.add_field(name="Portal Token (keep this secret!)",
                        value=f"||{portal['token']}||", inline=False)

        await ctx.author.send(embed=embed)
        await ctx.message.add_reaction("✅")

    @portal.command()
    async def set(self, ctx, id: str, field: str, *, value: str):
        "Modify an existing Portal's name, desc, or price"

        portal = await self.get_portal(id, ctx.author.id)

        if field == "name":
            portal["name"] = value
        elif field == "desc":
            portal["desc"] = value
        elif field == "price":
            portal["price"] = int(value)
        else:
            raise commands.CommandError(f"Invalid field {field}")

        await self.set_portal(portal)
        await ctx.message.add_reaction("✅")

    @portal.command()
    async def delete(self, ctx, id: str):
        "Delete an existing Portal"

        await self.get_portal(id, ctx.author.id)

        await self.redis.srem("portal:list", id)
        await self.redis.srem(f"portal:from_owner:{ctx.author.id}", id)
        await self.redis.delete(f"portal:{id}")

        guild_ids = await self.redis.smembers(f"portal:guilds:{id}")
        for gid in guild_ids:
            await self.remove_portal(id, gid)

        await ctx.message.add_reaction("✅")

    @portal.command()
    async def mine(self, ctx):
        "List your registered Portals"

        portal_ids = await self.redis.smembers(
            f"portal:from_owner:{ctx.author.id}")

        embed = discord.Embed(title=f"{ctx.author.display_name}'s Portals")

        portals = []
        for id in portal_ids:
            portal = await self.get_portal(id)
            portals.append(portal)

        if portals:
            embed.description = "\n".join(
                f"{self.portal_status_to_emoji(portal['status'])} "
                f"`{portal['id']}`: {portal['name']}, {portal['desc']}"
                for portal in portals)
        else:
            embed.description = (
                "You haven't registered any Portals yet. "
                f"`{self.bot.main_prefix}portal create`?")

        await ctx.send(embed=embed)

    # MAKE THE PORTAL OBJECTS AVAILABLE USING ALIASES IN GUILDS

    @portal.command()
    async def guilds(self, ctx, id: str):
        "List the servers that a Portal is connected to"

        await self.get_portal(id, ctx.author.id)

        guild_ids = await self.redis.smembers(f"portal:guilds:{id}")

        embed = discord.Embed(title="Connected Guilds")

        guilds = []
        for id in guild_ids:
            guild = self.bot.get_guild(int(id))
            guilds.append(guild)

        if guilds:
            embed.description = "\n".join(
                f"`{guild.id}`: {guild.name}" for guild in guilds)
        else:
            embed.description = (
                "That portal has not been added to any guilds."
                f"`{self.bot.main_prefix}portal add`?")

        await ctx.send(embed=embed)

    async def check_name(self, name, guild_id):
        existing_id = await self.redis.get(
            f"portal:from_name:{guild_id}:{name}")
        if not existing_id:
            return True

        if not await self.redis.exists(f"portal:{existing_id}"):
            await self.redis.delete(f"portal:from_name:{guild_id}:{name}")
            return True

        return False

    @portal.command()
    async def add(self, ctx, id: str, name: str):
        "Add a portal to a server"

        portal = await self.get_portal(id, ctx.author.id)

        if not await self.check_name(name, ctx.guild.id):
            raise commands.CommandError(
                f"A portal with the name {name} already exists.")

        if await self.redis.sismember(
                f"portal:list:{ctx.guild.id}", portal["id"]):
            raise commands.CommandError(
                "That portal already exists in this server.")

        await self.redis.sadd(f"portal:list:{ctx.guild.id}", portal["id"])
        await self.redis.sadd(f"portal:guilds:{portal['id']}", ctx.guild.id)
        await self.redis.set(
            f"portal:from_name:{ctx.guild.id}:{name}", portal["id"])
        await self.redis.set(
            f"portal:from_id:{ctx.guild.id}:{portal['id']}", name)

        await ctx.message.add_reaction("✅")

    @portal.command()
    async def remove(self, ctx, name: str):
        "Remove a portal from a server"

        portal_id = await self.redis.get(
            f"portal:from_name:{ctx.guild.id}:{name}")
        if not portal_id:
            raise commands.CommandError(f"The portal {name} does not exist.")

        portal = await self.get_portal(portal_id, ctx.author.id)

        await self.remove_portal(portal["id"], ctx.guild.id)
        await ctx.message.add_reaction("✅")

    async def remove_portal(self, id, guild_id):
        name = await self.redis.get(f"portal:from_id:{guild_id}:{id}")

        await self.redis.srem(f"portal:list:{guild_id}", id)
        await self.redis.srem(f"portal:guilds:{id}", guild_id)
        await self.redis.delete(f"portal:from_name:{guild_id}:{name}")
        await self.redis.delete(f"portal:from_id:{guild_id}:{id}")

    @staticmethod
    def portal_status_to_emoji(status):
        status = int(status)
        if status == 0:
            return ":x:"  # Disconnected
        elif status == 1:
            return ":orange_circle:"  # Connected, Not Ready
        elif status == 2:
            return ":green_circle:"  # Connected, Ready

    async def custom_bot_help(self, ctx):
        if not ctx.guild:
            return f"`{self.bot.main_prefix}portal create`\n"
        portal_ids = await self.redis.smembers(f"portal:list:{ctx.guild.id}")

        desc = [f"`{self.bot.main_prefix}makeportal` | "]
        for id in portal_ids:
            alias = await self.redis.get(f"portal:from_id:{ctx.guild.id}:{id}")
            desc.append(f"`{self.bot.main_prefix}portal {alias}`")
        return " ".join(desc) + "\n"

    @portal.command()
    async def list(self, ctx):
        "List connected portals"
        portal_ids = await self.redis.smembers(f"portal:list:{ctx.guild.id}")

        embed = discord.Embed(title="Connected Portals")

        portals = []
        for id in portal_ids:
            portal = await self.get_portal(id)
            portal["alias"] = await self.redis.get(
                f"portal:from_id:{ctx.guild.id}:{id}")
            portals.append(portal)

        if int(portal["price"]) > 0:
            price_str = f"*({portal['price']}  ¢)*"
        else:
            price_str = "*(free)*"

        if portals:
            embed.description = "\n".join(
                f"{self.portal_status_to_emoji(portal['status'])} "
                f"`{portal['alias']}`: {portal['name']}, "
                f"{portal['desc']} {price_str} ({portal['id']})"
                for portal in portals)
        else:
            embed.description = (
                "There are no portals currently connected here."
                f"`{self.bot.main_prefix}portal add`?")

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Portal(bot))
