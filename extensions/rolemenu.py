import typing
from urllib.parse import urlparse

import discord
from discord.ext import commands, tasks

from .utils import *


class Menu:
    def __init__(self, name="Under Construction", desc="Role menu currently under construction.", mapping={}, channel_id=None, message_id=None):
        self.name = name
        self.desc = desc
        self.mapping = mapping
        self.channel_id = channel_id
        self.message_id = message_id

    @staticmethod
    def from_redis(redis, channel_id, message_id):
        hash = redis.hgetall(f"rolemenu:{channel_id}:{message_id}")
        if not hash:
            raise Fail(f"Role Menu with ID {channel_id}:{message_id} does not exist")

        name = hash["name"]
        desc = hash["desc"]

        mapping = {}
        for key, val in hash.items():
            if key.startswith("emoji:"):
                emoji = key[len("emoji:"):]
                mapping[emoji] = val

        return Menu(name, desc, mapping, channel_id, message_id)

    def to_redis(self, redis):
        hash = {
            "name": self.name,
            "desc": self.desc,
            "message_id": self.message_id,
            "channel_id": self.channel_id
        }

        for key, val in self.mapping.items():
            hash[f"emoji:{key}"] = val

        redis.hset(f"rolemenu:{self.channel_id}:{self.message_id}", mapping=hash)
        redis.sadd("rolemenu:list", f"{self.channel_id}:{self.message_id}")

    def delete(self, redis):
        redis.srem("rolemenu:list", f"{self.channel_id}{self.message_id}")
        redis.delete(f"rolemenu:{self.channel_id}:{self.message_id}")

    async def post(self, bot, channel=None):
        text = []

        text.append(f"Role Menu: **{self.name}**")
        text.append(self.desc)
        text.append("")

        if self.message_id:
            guild = bot.get_channel(int(self.channel_id)).guild
        elif channel:
            guild = channel.guild

        for key, val in self.mapping.items():
            text.append(f"{key}: {guild.get_role(int(val))}")

        text = "\n".join(text)

        if self.message_id:
            message = await bot.get_channel(int(self.channel_id)).fetch_message(int(self.message_id))
            await message.edit(content=text)

        elif channel:
            message = await channel.send(text)
            self.channel_id = channel.id
            self.message_id = message.id

        await message.clear_reactions()

        for emoji in self.mapping:
            await message.add_reaction(emoji)


class RoleMenu(BaseCog):
    "Create and manage menus for users to choose their roles"

    def get_menu_from_link(self, ctx, link):
        # Grab the guild, channel, message out of the message link
        # https://discordapp.com/channels/747905649303748678/747921216186220654/748237781519827114
        _, guild_id, channel_id, message_id = urlparse(link).path.lstrip("/").split("/")

        if int(guild_id) != ctx.guild.id:
            raise Fail("That role menu belongs to a different guild!")

        return Menu.from_redis(self.redis, channel_id, message_id)

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    @passfail
    async def menu(self, ctx):
        "Create a menu for members to choose their roles using message reactions"

        menu = Menu()
        await menu.post(self.bot, ctx.channel)
        menu.to_redis(self.redis)

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    @passfail
    async def modifymenu(self, ctx, message_link: str, field: str, *, value: str):
        "Modify the name or description of a role menu"
        menu = self.get_menu_from_link(ctx, message_link)

        if field == "name":
            menu.name = value
        elif field == "desc":
            menu.desc = value

        await menu.post(self.bot)
        menu.to_redis(self.redis)

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    @passfail
    async def addrole(self, ctx, message_link: str, emoji: str, *, role: str):
        "Add a role to an existing role menu"

        for irole in ctx.guild.roles:
            if irole.name == role:
                break
        else:
            raise Fail(f"Role {role} does not exist")

        menu = self.get_menu_from_link(ctx, message_link)
        menu.mapping[emoji] = irole.id
        await menu.post(self.bot)
        menu.to_redis(self.redis)

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    @passfail
    async def remrole(self, ctx, message_link: str, emoji: str):
        "Remove a role from an existing role menu"

        menu = self.get_menu_from_link(ctx, message_link)
        del menu.mapping[emoji]
        await menu.post(self.bot)
        menu.to_redis(self.redis)


def setup(bot):
    bot.add_cog(RoleMenu(bot))

    @bot.listen()
    async def on_raw_message_delete(payload):
        if bot.redis.sismember("rolemenu:list", f"{payload.channel_id}:{payload.message_id}"):
            await bot.wait_until_ready()
            menu = Menu.from_redis(bot.redis, payload.channel_id, payload.message_id)
            menu.delete(bot.redis)

    @bot.listen()
    async def on_raw_reaction_add(payload):
        if bot.redis.sismember("rolemenu:list", f"{payload.channel_id}:{payload.message_id}"):
            await bot.wait_until_ready()
            menu = Menu.from_redis(bot.redis, payload.channel_id, payload.message_id)

            emoji = payload.emoji
            if emoji.is_custom_emoji():
                return

            role_id = menu.mapping.get(payload.emoji.name)
            if not role_id:
                return

            role = bot.get_channel(payload.channel_id).guild.get_role(int(role_id))

            roles = payload.member.roles
            if role in roles:
                return

            roles.append(role)

            print("Role Add")
            await payload.member.edit(roles=roles)

    @bot.listen()
    async def on_raw_reaction_remove(payload):
        if bot.redis.sismember("rolemenu:list", f"{payload.channel_id}:{payload.message_id}"):
            await bot.wait_until_ready()
            menu = Menu.from_redis(bot.redis, payload.channel_id, payload.message_id)

            emoji = payload.emoji
            if emoji.is_custom_emoji():
                return

            role_id = menu.mapping.get(payload.emoji.name)
            if not role_id:
                return

            message = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)

            roles = message.author.roles
            for role in roles:
                if role.id == role_id:
                    break

            roles.remove(role)

            print("Role Remove")
            await message.author.edit(roles=roles)
