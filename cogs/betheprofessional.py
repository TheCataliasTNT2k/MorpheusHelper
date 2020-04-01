import string
from typing import List

from discord import Role, Guild, Member
from discord.ext import commands
from discord.ext.commands import Cog, Bot, guild_only, Context, CommandError

from database import run_in_thread, db
from models.btp_role import BTPRole
from util import permission_level


def split_topics(topics: str) -> List[str]:
    return list(map(str.strip, topics.replace(";", ",").split(",")))


async def parse_topics(guild: Guild, topics: str) -> List[Role]:
    roles: List[Role] = []
    for topic in split_topics(topics):
        for role in guild.roles:
            if role.name.lower() == topic.lower() and await run_in_thread(db.get, BTPRole, role.id) is not None:
                break
        else:
            raise CommandError(f"Topic `{topic}` not found.")
        roles.append(role)
    return roles


async def list_topics(guild: Guild) -> List[Role]:
    roles: List[Role] = []
    for btp_role in await run_in_thread(db.all, BTPRole):
        if (role := guild.get_role(btp_role.role_id)) is None:
            await run_in_thread(db.delete, btp_role)
        else:
            roles.append(role)
    return roles


class BeTheProfessionalCog(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.group(name="btp")
    @guild_only()
    async def btp(self, ctx: Context):
        """
        manage language roles
        """

        if ctx.invoked_subcommand is None:
            await ctx.send_help("btp")

    @btp.command(name="?")
    async def list_roles(self, ctx: Context):
        """
        lists all registered topics
        """

        out = [role.name for role in await list_topics(ctx.guild)]
        if out:
            await ctx.send("Available Topics:\n" + ", ".join(out))
        else:
            await ctx.send("No topics have been registered yet.")

    @btp.command(name="+")
    async def add_role(self, ctx: Context, *, topics: str):
        """
        add one or more topics you are interested in
        """

        member: Member = ctx.author
        roles: List[Role] = [r for r in await parse_topics(ctx.guild, topics) if r not in member.roles]

        await member.add_roles(*roles)
        if roles:
            await ctx.send(f"{len(roles)} topic" + [" has", "s have"][len(roles) > 1] + " been added successfully.")
        else:
            await ctx.send("No topic has been added.")

    @btp.command(name="-")
    async def remove_roles(self, ctx: Context, *, topics: str):
        """
        remove one or more topics (use * to remove all topics)
        """

        member: Member = ctx.author
        if topics.strip() == "*":
            roles: List[Role] = await list_topics(ctx.guild)
        else:
            roles: List[Role] = await parse_topics(ctx.guild, topics)
        roles = [r for r in roles if r in member.roles]

        await member.remove_roles(*roles)
        if roles:
            await ctx.send(f"{len(roles)} topic" + [" has", "s have"][len(roles) > 1] + " been removed successfully.")
        else:
            await ctx.send("No topic has been removed.")

    @btp.command(name="*")
    @permission_level(1)
    async def register_role(self, ctx: Context, *, topics: str):
        """
        register one or more new topics
        """

        guild: Guild = ctx.guild
        names = split_topics(topics)
        if not names:
            await ctx.send_help(self.register_role)
            return

        valid_chars = set(string.ascii_letters + string.digits + " !\"#$%&'()*+-./:<=>?[\\]^_`{|}~")
        to_be_created: List[str] = []
        roles: List[Role] = []
        for topic in names:
            if any(c not in valid_chars for c in topic):
                raise CommandError(f"Topic name `{topic}` contains invalid characters.")
            elif not topic:
                raise CommandError("Topic name may not be empty.")

            for role in guild.roles:
                if role.name.lower() == topic.lower():
                    break
            else:
                to_be_created.append(topic)
                continue

            if await run_in_thread(db.get, BTPRole, role.id) is not None:
                raise CommandError(f"Topic `{topic}` has already been registered.")
            if role > ctx.me.top_role:
                raise CommandError(
                    f"Topic could not be registered because `@{role}` is higher than `@{ctx.me.top_role}`."
                )
            if role.managed:
                raise CommandError(f"Topic could not be registered because `@{role}` cannot be assigned manually.")
            roles.append(role)

        for name in to_be_created:
            roles.append(await guild.create_role(name=name, mentionable=True))

        for role in roles:
            await run_in_thread(BTPRole.create, role.id)

        await ctx.send(f"{len(roles)} topic" + [" has", "s have"][len(roles) > 1] + " been registered successfully.")

    @btp.command(name="/")
    @permission_level(1)
    async def unregister_role(self, ctx: Context, *, topics: str):
        """
        deletes one or more topics
        """

        guild: Guild = ctx.guild
        roles: List[Role] = []
        btp_roles: List[BTPRole] = []
        names = split_topics(topics)
        if not names:
            await ctx.send_help(self.register_role)
            return
        for topic in names:
            for role in guild.roles:
                if role.name.lower() == topic.lower():
                    break
            else:
                raise CommandError(f"Topic `{topic}` has not been registered.")
            if (btp_role := await run_in_thread(db.get, BTPRole, role.id)) is None:
                raise CommandError(f"Topic `{topic}` has not been registered.")

            roles.append(role)
            btp_roles.append(btp_role)

        for role, btp_role in zip(roles, btp_roles):
            await run_in_thread(db.delete, btp_role)
            await role.delete()
        await ctx.send(f"{len(roles)} topic" + [" has", "s have"][len(roles) > 1] + " been deleted successfully.")
