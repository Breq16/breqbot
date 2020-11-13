import typing

import discord
from discord.ext import commands

from ..base import BaseCog


class Vex(BaseCog):
    "Information about the VEX Robotics Competition"

    SEASON = "Tower Takeover"

    async def get_json(self, url, params={}):
        async with self.session.get(url, params=params) as response:
            return await response.json()

    async def get_team_overview(self, team):
        team = (await self.get_json(
            "https://api.vexdb.io/v1/get_teams",
            params={"team": team})
        )["result"][0]

        embed = discord.Embed(
            title=f"{team['program']} team {team['number']}: "
            f"{team['team_name']}")

        awards_raw = (await self.get_json(
            "https://api.vexdb.io/v1/get_awards",
            params={"team": team["number"], "season": self.SEASON})
        )["result"]

        awards = []
        for award_raw in awards_raw:
            award_name = award_raw["name"]

            event_raw = (await self.get_json(
                "https://api.vexdb.io/v1/get_events",
                params={"sku": award_raw["sku"]})
            )["result"][0]
            event_name = event_raw["name"]
            awards.append((award_name, event_name))

        awards = "\n".join(f"• **{award}** | {event}"
                           for award, event in awards)
        if not awards:
            awards = "This team has not won any awards."

        awards = "**Awards:**\n" + awards

        rankings_raw = (await self.get_json(
            "https://api.vexdb.io/v1/get_rankings",
            params={"team": team["number"], "season": self.SEASON})
        )["result"]

        rankings = []
        for ranking_raw in rankings_raw:
            ranking = ranking_raw["rank"]

            teams_count = (await self.get_json(
                "https://api.vexdb.io/v1/get_teams",
                params={"sku": ranking_raw["sku"], "nodata": "true"})
            )["size"]

            event_raw = (await self.get_json(
                "https://api.vexdb.io/v1/get_events",
                params={"sku": ranking_raw["sku"]})
            )["result"][0]
            event_name = event_raw["name"]

            rankings.append((ranking, teams_count, event_name))

        rankings = "\n".join(f"• **{rank}**/{teams} | {event}"
                             for rank, teams, event in rankings)
        if not rankings:
            rankings = "This team has not competed."

        rankings = "**Rankings:**\n" + rankings

        embed.description = awards + "\n" + rankings

        return None, [], embed

    async def get_meet_data(self, team, sku):
        team = (await self.get_json(
            "https://api.vexdb.io/v1/get_teams",
            params={"team": team})
        )["result"][0]

        event = (await self.get_json(
            "https://api.vexdb.io/v1/get_events",
            params={"sku": sku})
        )["result"][0]

        matches = (await self.get_json(
            "https://api.vexdb.io/v1/get_matches",
            params={"sku": sku, "team": team["number"], "scored": 1})
        )["result"]

        driver_skills = (await self.get_json(
            "https://api.vexdb.io/v1/get_skills",
            params={"sku": sku, "team": team["number"], "type": 0})
        )["result"][0]

        programming_skills = (await self.get_json(
            "https://api.vexdb.io/v1/get_skills",
            params={"sku": sku, "team": team["number"], "type": 1})
        )["result"][0]

        ranking = (await self.get_json(
            "https://api.vexdb.io/v1/get_rankings",
            params={"sku": sku, "team": team["number"]})
        )["result"][0]

        return team, event, matches, driver_skills, programming_skills, ranking

    def matchnum(self, match):
        if match["round"] == 1:  # Practice
            return f"P{match['matchnum']}"
        if match["round"] == 2:  # Qualification
            return f"Q{match['matchnum']}"
        if match["round"] == 3:  # QuarterFinals
            return f"QF{match['matchnum']}-{match['instance']}"
        if match["round"] == 4:  # SemiFinals
            return f"SF{match['matchnum']}-{match['instance']}"
        if match["round"] == 5:  # Finals
            return f"Final {match['instance']}"

    def matchstr(self, match, team=None):
        team = team["number"]
        num = self.matchnum(match)

        teams = [match[key] for key in ("red1", "red2", "blue1", "blue2")]

        redteams = " ".join((f"**{t}**" if t == team else t)
                            for t in teams[:2])
        blueteams = " ".join((f"**{t}**" if t == team else t)
                             for t in teams[2:])

        if team in teams[:2]:  # Team On Red
            score = f" **{match['redscore']}** - *{match['bluescore']}* "
        else:  # Team On Blue
            score = f" *{match['redscore']}* - **{match['bluescore']}** "

        if match["redscore"] > match["bluescore"]:
            # Red win
            score = f"🟥{score}⬛"
            if team in teams[:2]:
                result = "✅"
            else:
                result = "❌"

        elif match["bluescore"] > match["redscore"]:
            # Blue win
            score = f"⬛{score}🟦"
            if team in teams[2:]:
                result = "✅"
            else:
                result = "❌"
        else:
            # Tie
            score = f"🟪{score}🟪"
            result = "🔸"

        return f"{num}\t-\t{redteams}\t{score}\t{blueteams}\t-\t{result}"

    async def get_meet_overview(self, team, sku):
        team, event, matches, driver_skills, programming_skills, ranking \
            = await self.get_meet_data(team, sku)

        embed = discord.Embed(
            title=f"**{team['number']}**: *{team['team_name']}* at"
            f"*{event['name']}*")

        matches_str = "\n".join(f"{self.matchstr(match, team)}"
                                for match in matches)

        skills_str = (f"Driver: {driver_skills['score']} "
                      f"*({driver_skills['attempts']} attempts)*\n"
                      f"Programming: {programming_skills['score']} "
                      f"*({programming_skills['attempts']} attempts)*")

        rankings_str = (f"**{ranking['rank']}** "
                        f"({ranking['wins']}-{ranking['losses']}-"
                        f"{ranking['ties']})")

        embed.add_field(name="Matches", value=matches_str, inline=False)
        embed.add_field(name="Skills", value=skills_str, inline=False)
        embed.add_field(name="Rankings", value=rankings_str, inline=False)

        return None, [], embed

    @commands.command()
    async def vex(self, ctx, team: str, sku: typing.Optional[str] = None):
        ":mag: :robot: Get info about a Vex team :video_game:"
        if sku:
            content, files, embed = await self.get_meet_overview(team, sku)
        else:
            content, files, embed = await self.get_team_overview(team)

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Vex(bot))
