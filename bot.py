from contextlib import suppress
from email import message
from urllib.request import Request
import aiohttp
import aiosqlite  # Using this package instead of sqlite for asynchronous processing support
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
import discord
from discord import AllowedMentions, Message, app_commands
from discord.app_commands.commands import Check
from discord.ext import commands, tasks
from discord.utils import get
from dotenv import load_dotenv, find_dotenv
import itertools
import json
import logging
from openpyxl import load_workbook
import aiohttp
import os
import sys
import platform
import random
import traceback
import time
import requests
import operator
import random
import gspread
import gspread.utils
import time
from functools import wraps
from gspread.utils import ValueRenderOption
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials

load_dotenv(find_dotenv())
intents = discord.Intents.default()
client = discord.Client(
    intents=intents,
    heartbeat_timeout=60.0
)
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

"""
All of the following constants are variables which are set in the .env file, and several are crucial to the bot's functions.
If you don't have an .env file in the same directory as bot.py, ensure you downloaded everything from the bot's GitHub repository and that you renamed ".env.template" to .env.
"""

TOKEN = os.getenv('BOT_TOKEN')  # Gets the bot's password token from the .env file and sets it to TOKEN.
GUILD = os.getenv('GUILD_TOKEN')  # Gets the server's id from the .env file and sets it to GUILD.
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
GSHEETS_API = os.getenv('GSHEETS_API')
GSHEETS_ID = os.getenv('GSHEETS_ID')
GHSEETS_GAMEDB = os.getenv('GHSEETS_GAMEDB')
GSHEETS_PLAYERDB = os.getenv('GSHEETS_PLAYERDB')
GSHEETS_TOURNAMENTDB = os.getenv('GSHEETS_TOURNAMENTDB')
WELCOME_CHANNEL_ID = os.getenv('WELCOME_CHANNEL_ID')
TIER_WEIGHT = float(os.getenv('TIER_WEIGHT', 0.7))  # Default value of 0.7 if not specified in .env
ROLE_PREFERENCE_WEIGHT = float(
    os.getenv('ROLE_PREFERENCE_WEIGHT', 0.3))  # Default value of 0.3 if not specified in .env
TIER_GROUPS = os.getenv('TIER_GROUPS',
                        'UNRANKED,IRON,BRONZE,SILVER:GOLD,PLATINUM:EMERALD:DIAMOND:MASTER:GRANDMASTER:CHALLENGER')  # Setting default tier configuration if left blank in .env
CHECKIN_TIME = os.getenv('CHECKIN_TIME')
CHECKIN_TIME = int(CHECKIN_TIME)
NOTIFICATION_CHANNEL_ID = os.getenv('NOTIFICATION_CHANNEL_ID')

# Global variables to track MVP votes and game winners

mvp_votes = defaultdict(lambda: defaultdict(int))  # {lobby_id: {player_name: vote_count}}
game_winners = {}  # {lobby_id: winning_team}
MVP_VOTE_THRESHOLD = 3  # Minimum votes needed to win MVP
mvp_winners = {}  # {lobby_id: mvp_name}
# Define current_teams as a global variable
current_teams = {"team1": None, "team2": None}

# The following is all used in matchmaking:

mvp_votes = defaultdict(lambda: defaultdict(int))  # {lobby_id: {player_name: vote_count}}
game_winners = {}  # {lobby_id: winning_team}
MVP_VOTE_THRESHOLD = 3  # Configurable minimum vote threshold

# The following is all used in matchmaking:

TIER_VALUES = {
    "1": 100, "2": 97, "3": 93,
    "4": 87, "5": 78, "6": 68, "7": 55
}

randomness = 5  # Used in matchmaking, 5 total points of randomness between scores for players, I.E. a player with 100 base points could be rated as anywhere between 95 and 105 points
# Purely used to allow for some variance in matchmaking

absoluteMaximumDifference = 21  # Also used in matchmaking, this is the largest number of Quality Points a team can differ from the other team and still play
# A lower number means teams have to be closer in quality to be valid.

# Adjust event loop policy for Windows
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Semaphore to limit the number of concurrent API requests to Riot (added to address connection errors pulling player rank with /stats)
api_semaphore = asyncio.Semaphore(5)  # Limit concurrent requests to 5

session = None

# Set up gspread for access by functions

gc = gspread.service_account(filename='C:\\Users\\Jacob\\source\\repos\\KSU Capstone Project\\KSU Capstone Project\\gspread_service_account.json')
googleWorkbook = gc.open_by_key(GSHEETS_ID)

tourneyDB = googleWorkbook.worksheet('TournamentDatabase')
gameDB = googleWorkbook.worksheet('GameDatabase')
playerDB = googleWorkbook.worksheet('PlayerDatabase')

# Rate limiter decorator
def rate_limited(max_per_minute):
    min_interval = 60.0 / max_per_minute
    def decorator(func):
        last_called = [0.0]
        @wraps(func)
        async def wrapped(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            wait = min_interval - elapsed
            if wait > 0:
                time.sleep(wait)
            last_called[0] = time.time()
            return await func(*args, **kwargs)
        return wrapped
    return decorator

# Apply to Sheet operations
@rate_limited(60)  # 60 requests per minute
async def safe_sheet_update(sheet, *args, **kwargs):
    try:
        return sheet.update(*args, **kwargs)
    except gspread.exceptions.APIError as e:
        if 'quota' in str(e).lower():
            print("Hit rate limit, waiting...")
            time.sleep(60)
            return safe_sheet_update(sheet, *args, **kwargs)
        raise

def get_admin_mention(guild: discord.Guild) -> str:
    """Returns a string that mentions all administrators"""
    admin_mentions = []
    for member in guild.members:
        if member.guild_permissions.administrator:
            admin_mentions.append(member.mention)
    return " ".join(admin_mentions) if admin_mentions else "@admin"

async def get_friendly_discord_id(discord_id: int, guild: discord.Guild) -> str:
    """
    Converts a numeric Discord ID into a friendly username#discriminator format.
    """
    member = guild.get_member(discord_id)
    if member:
        return f"{member.name}#{member.discriminator}"

    return None

async def safe_sheet_fetch(sheet, max_retries=3):
    """Fetch sheet data with retry logic"""
    for attempt in range(max_retries):
        try:
            return sheet.get_all_records()
        except gspread.exceptions.APIError as e:
            if attempt == max_retries - 1:
                raise
            wait = (attempt + 1) * 10  # Exponential backoff
            print(f"API Error (attempt {attempt + 1}), retrying in {wait} seconds...")
            await asyncio.sleep(wait)


async def batch_sheet_update(sheet, updates):
    """Update multiple cells in a single batch"""
    try:
        # Group updates by row to minimize API calls
        update_batches = {}
        for row, col, value in updates:
            if row not in update_batches:
                update_batches[row] = {}
            update_batches[row][col] = value

        # Process batches
        for row, cols in update_batches.items():
            range_start = gspread.utils.rowcol_to_a1(row, min(cols.keys()))
            range_end = gspread.utils.rowcol_to_a1(row, max(cols.keys()))
            cell_list = sheet.range(f"{range_start}:{range_end}")

            for cell in cell_list:
                if cell.col in cols:
                    cell.value = cols[cell.col]

            await asyncio.sleep(1)  # Rate limiting
            sheet.update_cells(cell_list)

    except Exception as e:
        print(f"Error in batch update: {str(e)}")
        raise

# On bot ready event
@client.event
async def on_ready():
    global session
    # Initialize aiohttp session
    connector = aiohttp.TCPConnector(ttl_dns_cache=300, ssl=False)
    session = aiohttp.ClientSession(connector=connector)

    # Sync commands with Discord
    await tree.sync(guild=discord.Object(GUILD))
    print(f'Logged in as {client.user}')

    # Get the guild object
    guild = discord.utils.get(client.guilds, id=int(GUILD))
    if guild is None:
        print(f'Guild with ID {GUILD} not found.')
        return

    # Get bot's role and the roles for Player and Volunteer
    bot_role = discord.utils.get(guild.roles, name=client.user.name)
    player_role = discord.utils.get(guild.roles, name='Player')
    volunteer_role = discord.utils.get(guild.roles, name='Volunteer')

    # Create Player role if it doesn't exist
    if player_role is None:
        player_role = await guild.create_role(name='Player', mentionable=True)

    # Create Volunteer role if it doesn't exist
    if volunteer_role is None:
        volunteer_role = await guild.create_role(name='Volunteer', mentionable=True)

    # Adjust Player and Volunteer roles to be below the bot role, if possible
    if bot_role is not None:
        new_position = max(bot_role.position - 1, 1)
        await player_role.edit(position=new_position)
        await volunteer_role.edit(position=new_position)

    @client.event
    async def on_member_join(member):
        # Determine which channel to use for the welcome message
        welcome_channel = None

        if WELCOME_CHANNEL_ID:
            # If a welcome channel is specified in .env, use that channel
            welcome_channel = member.guild.get_channel(int(WELCOME_CHANNEL_ID))
        else:
            # Otherwise, try to find the default channel named "general" (created automatically when a Discord server is made)
            for channel in member.guild.text_channels:
                if channel.name.lower() == "general":
                    welcome_channel = channel
                    break

        if welcome_channel:
            await welcome_channel.send(
                f"Welcome to the server, {member.mention}! 🎉\n"
                "Please use `/link [riot_id]` to connect your Riot ID to the bot so you can participate in our in-house tournaments, and set your preferred roles with `/rolepreference` afterward. You can use `/help` for more information!"
            )
        else:
            print(f"Could not find a welcome channel for guild {member.guild.name}.")


# Safe API call function with retries for better error handling
async def safe_api_call(url, headers):
    max_retries = 3
    retry_delay = 1  # Delay between retries in seconds

    for attempt in range(max_retries):
        try:
            async with api_semaphore:  # Limit concurrent access to the API
                # Using a timeout context inside the aiohttp request
                timeout = aiohttp.ClientTimeout(total=5)  # Set a 5-second total timeout for the request
                async with session.get(url, headers=headers, timeout=timeout,
                                       ssl=False) as response:  # Disable SSL verification
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:  # Rate limit hit
                        retry_after = response.headers.get("Retry-After", 1)
                        print(f"Rate limit reached. Retrying after {retry_after} seconds.")
                        await asyncio.sleep(int(retry_after))  # Wait for specified time
                    else:
                        print(f"Error fetching data: {response.status}, response: {await response.text()}")
                        return None
        except aiohttp.ClientConnectorError as e:
            print(f"Connection error on attempt {attempt + 1}/{max_retries}: {e}")
        except asyncio.TimeoutError as e:
            print(f"Timeout error on attempt {attempt + 1}/{max_retries}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred on attempt {attempt + 1}/{max_retries}: {e}")
            print(traceback.format_exc())  # Print the full traceback for more details

        # Retry if there are remaining attempts
        if attempt < max_retries - 1:
            print(f"Retrying API call in {retry_delay} seconds... (Attempt {attempt + 2}/{max_retries})")
            await asyncio.sleep(retry_delay)

    print("All attempts to connect to the Riot API have failed.")
    return None


class MVPView(discord.ui.View):

    def __init__(self, lobby_id, winning_team_players):

        super().__init__(timeout=180)  # 3-minute timeout
        self.lobby_id = lobby_id
        self.add_item(MVPDropdown(winning_team_players, lobby_id))

class MVPDropdown(discord.ui.Select):
    def __init__(self, winning_team_players, lobby_id):
        options = [
            discord.SelectOption(label=player.name, value=player.name)
            for player in winning_team_players
        ]
        super().__init__(
            placeholder="Select the MVP",
            min_values=1,
            max_values=1,
            options=options
        )
        self.lobby_id = lobby_id

    async def callback(self, interaction: discord.Interaction):
        selected_mvp = self.values[0]
        voter_id = f"{interaction.user.name}#{interaction.user.discriminator}"

        # Prevent self-voting
        if voter_id == selected_mvp:
            await interaction.response.send_message(
                "❌ You cannot vote for yourself!",
                ephemeral=True
            )
            return

        # Update vote count
        mvp_votes[self.lobby_id][selected_mvp] += 1
        current_votes = mvp_votes[self.lobby_id][selected_mvp]

        # Check if this vote reached the threshold
        if current_votes >= MVP_VOTE_THRESHOLD and self.lobby_id not in mvp_winners:
            mvp_winners[self.lobby_id] = selected_mvp
            await interaction.response.send_message(
                f"🎉 {selected_mvp} has reached {MVP_VOTE_THRESHOLD} votes and is the MVP!",
                ephemeral=False
            )

            # Update database with MVP
            try:
                game_row = int(self.lobby_id) + 1
                gameDB.update_cell(f'D{game_row}', selected_mvp)  # Update MVP in database

                # Update player's MVP count
                existing_records = playerDB.get_all_records()
                for i, record in enumerate(existing_records, start=2):
                    if record.get("Players1") == selected_mvp:
                        current_mvps = int(record.get("MVPs", 0))
                        playerDB.update_cell(i, 11, current_mvps + 1)  # Column K (11) is "MVPs"
                        break
            except Exception as e:
                print(f"Error updating MVP in database: {e}")
        else:
            await interaction.response.send_message(
                f"✅ You voted for {selected_mvp} (Total votes: {current_votes}/{MVP_VOTE_THRESHOLD})",
                ephemeral=True
            )

@tree.command(
    name="mvp",
    description="Vote for the MVP from the winning team",
    guild=discord.Object(GUILD)
)
async def mvp(interaction: discord.Interaction):
    try:
        lobby_id = gameDB.col_values(1)[-1]  # Get latest game ID

        # Check if MVP already declared
        if lobby_id in mvp_winners:
            await interaction.response.send_message(
                f"❌ MVP has already been awarded to {mvp_winners[lobby_id]}",
                ephemeral=True
            )
            return

        # Check if game has a winner
        if lobby_id not in game_winners:
            await interaction.response.send_message(
                "❌ No winner has been declared for this game yet",
                ephemeral=True
            )
            return

        # Create voting view
        winning_team = game_winners[lobby_id]
        view = MVPView(lobby_id, winning_team.playerList)
        await interaction.response.send_message(
            f"Vote for MVP from the winning team (First to {MVP_VOTE_THRESHOLD} votes wins):",
            view=view,
            ephemeral=False
        )

    except Exception as e:
        print(f"Error in /mvp: {e}")
        await interaction.response.send_message(
            "❌ Failed to start MVP voting",
            ephemeral=True
        )


@tree.command(
    name="gamewinner",
    description="Declare the winning team for the current game (Admin only).",
    guild=discord.Object(GUILD)
)
@commands.has_permissions(administrator=True)
async def gamewinner(interaction: discord.Interaction, winning_team: str):
    global current_teams, game_winners

    try:
        await interaction.response.defer()

        # Enhanced team validation with database fallback
        if not current_teams or not current_teams.get("team1") or not current_teams.get("team2"):
            # Try to recover teams from database
            try:
                lobby_id = gameDB.col_values(1)[-1]
                if lobby_id.isdigit():
                    game_row = int(lobby_id) + 1
                    game_data = gameDB.row_values(game_row)
                    if len(game_data) >= 14:  # Ensure we have all player columns
                        # Get player names from database
                        team1_players = game_data[4:9]  # Columns E-I (Team 1)
                        team2_players = game_data[9:14]  # Columns J-N (Team 2)

                        # Reconstruct player objects
                        team1 = team([participant(name, "UNRANKED", 0, 0, 0, 0, 0) for name in team1_players])
                        team2 = team([participant(name, "UNRANKED", 0, 0, 0, 0, 0) for name in team2_players])

                        current_teams = {
                            "team1": team1,
                            "team2": team2
                        }
            except Exception as e:
                print(f"Error trying to recover teams from database: {e}")

            if not current_teams or not current_teams.get("team1") or not current_teams.get("team2"):
                await interaction.followup.send(
                    "❌ No active game found! Please create teams first with /create_game.",
                    ephemeral=True
                )
                return

        # Validate team selection
        winning_team = winning_team.lower()
        if winning_team not in ["blue", "red"]:
            await interaction.followup.send(
                "❌ Invalid team. Please specify 'blue' or 'red'.",
                ephemeral=True
            )
            return

        # Get current game ID safely
        try:
            lobby_id = gameDB.col_values(1)[-1]  # Get latest game ID
            if not lobby_id.isdigit():
                raise ValueError("Invalid game ID")
            game_row = int(lobby_id) + 1
        except Exception as e:
            print(f"Error getting game ID: {e}")
            await interaction.followup.send(
                "❌ Could not determine current game. Please try again.",
                ephemeral=True
            )
            return

        # Determine winning team
        try:
            if winning_team == "blue":
                winning_team_obj = current_teams["team1"]
            else:
                winning_team_obj = current_teams["team2"]

            winning_team_players = winning_team_obj.playerList
            game_winners[lobby_id] = winning_team_obj
        except AttributeError as e:
            print(f"Error accessing team data: {e}")
            await interaction.followup.send(
                "❌ Team data is corrupted. Please recreate the game.",
                ephemeral=True
            )
            return

        # Update game database
        try:
            gameDB.update_cell(game_row, 3, winning_team.capitalize())  # Column C (3) is Winner
        except Exception as e:
            print(f"Error updating game DB: {e}")
            await interaction.followup.send(
                "❌ Failed to update game record. Check console for details.",
                ephemeral=True
            )
            return
            # Update participation for all players
        try:
            all_players = current_teams["team1"].playerList + current_teams["team2"].playerList
            for player in all_players:
                is_winner = (winning_team.lower() == "blue" and player in current_teams["team1"].playerList) or \
                            (winning_team.lower() == "red" and player in current_teams["team2"].playerList)
                await update_participation(player.name, is_winner)
        except Exception as e:
            print(f"Error updating participation: {e}")

        # Update wins for winning team
        try:
            for player in winning_team_players:
                existing_records = playerDB.get_all_records()
                for i, record in enumerate(existing_records, start=2):
                    if record.get("Players1") == player.name:
                        current_wins = int(record.get("Wins", 0))
                        playerDB.update_cell(i, 11, current_wins + 1)  # Column K (11) is Wins
                        break
        except Exception as e:
            print(f"Error updating wins: {e}")

        # Adjust tiers
        try:
            await adjust_tiers()
        except Exception as e:
            print(f"Error adjusting tiers: {e}")

        # Send announcement to notification channel
        try:
            notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
            if notification_channel:
                winning_team_name = winning_team.capitalize()
                player_names = "\n".join([f"• {player.name}" for player in winning_team_players])

                embed = discord.Embed(
                    title=f"🏆 {winning_team_name} Team Wins!",
                    description=f"**Congratulations to:**\n{player_names}",
                    color=0x3498db if winning_team == "blue" else 0xe74c3c
                )
                embed.add_field(
                    name="Game ID",
                    value=lobby_id,
                    inline=False
                )
                embed.set_thumbnail(url="https://i.imgur.com/t7k6Z2F.png")  # Add your trophy icon

                await notification_channel.send(embed=embed)
        except Exception as e:
            print(f"Error sending notification: {e}")

        # Create and send MVP voting
        try:
            view = MVPView(lobby_id, winning_team_players)
            await interaction.followup.send(
                f"✅ {winning_team.capitalize()} team declared winner!",
                ephemeral=False
            )
            await interaction.followup.send(
                "Vote for MVP from the winning team:",
                view=view
            )
        except Exception as e:
            print(f"Error creating MVP vote: {e}")
            await interaction.followup.send(
                "✅ Winner declared but MVP voting failed to start.",
                ephemeral=True
            )

    except Exception as e:
        print(f"Unexpected error in gamewinner: {e}")
        await interaction.followup.send(
            "❌ An unexpected error occurred. Check console for details.",
            ephemeral=True
        )

@tree.command(
    name="mvpresult",
    description="Declare the MVP for the current game (Admin only).",
    guild=discord.Object(GUILD)
)
@commands.has_permissions(administrator=True)
async def mvpresult(interaction: discord.Interaction):
    global mvp_votes, game_winners, mvp_winners, current_teams

    try:
        await interaction.response.defer()

        # Get current game info
        lobby_id = gameDB.col_values(1)[-1]
        game_row = int(lobby_id) + 1

        # Check if MVP was already automatically declared
        if lobby_id in mvp_winners:
            mvp_name = mvp_winners[lobby_id]
            await interaction.followup.send(
                f"🏆 MVP was already awarded to {mvp_name} (reached {MVP_VOTE_THRESHOLD} votes)",
                ephemeral=False
            )
            return

        # Check if there are votes
        if lobby_id not in mvp_votes or not mvp_votes[lobby_id]:
            await interaction.followup.send(
                "❌ No MVP votes have been cast for this game.",
                ephemeral=True
            )
            return

        # Find player(s) with most votes
        vote_counts = mvp_votes[lobby_id]
        max_votes = max(vote_counts.values())
        mvps = [p for p, v in vote_counts.items() if v == max_votes]

        # Check threshold
        if max_votes < MVP_VOTE_THRESHOLD:
            # Admin override option
            view = discord.ui.View()

            async def declare_mvp_callback(interaction: discord.Interaction):
                selected_mvp = mvps[0] if mvps else "Unknown"
                await declare_mvp(lobby_id, game_row, selected_mvp, max_votes, True)
                await interaction.response.send_message(
                    f"✅ Admin override: {selected_mvp} declared MVP with {max_votes} votes",
                    ephemeral=True
                )

            # Only add button if there's at least one candidate
            if mvps:
                declare_button = discord.ui.Button(
                    label=f"Declare MVP Anyway (Top: {mvps[0]} with {max_votes} votes)",
                    style=discord.ButtonStyle.red
                )
                declare_button.callback = declare_mvp_callback
                view.add_item(declare_button)

            vote_list = "\n".join([f"{p}: {v} votes" for p, v in vote_counts.items()])
            await interaction.followup.send(
                f"❌ No player has reached {MVP_VOTE_THRESHOLD} votes yet.\nCurrent votes:\n{vote_list}",
                view=view,
                ephemeral=False
            )
            return

        # If we get here, threshold was reached
        mvp_name = mvps[0]  # Take the first one if multiple have same votes
        await declare_mvp(lobby_id, game_row, mvp_name, max_votes, False)

    except Exception as e:
        print(f"Error in mvpresult: {e}")
        await interaction.followup.send(
            "❌ Failed to process MVP result",
            ephemeral=True
        )


async def declare_mvp(lobby_id, game_row, mvp_name, vote_count, is_override=False):
    """Helper function to declare MVP and update databases"""
    global mvp_winners

    try:
        # Update GameDatabase - MVP column (D)
        gameDB.update_cell(game_row, 4, mvp_name)  # Column D is index 4

        # Update PlayerDatabase - increment MVP count
        existing_records = playerDB.get_all_records()
        for i, record in enumerate(existing_records, start=2):  # Start from row 2
            if record.get("Players1") == mvp_name:
                current_mvps = int(record.get("MVPs", 0))
                playerDB.update_cell(i, 15, current_mvps + 1)  # Column K is index 11
                break

        # Mark as declared
        mvp_winners[lobby_id] = mvp_name

        # Send announcement
        notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
        message = (
            f"🏆 **MVP DECLARED** ({'Admin Override' if is_override else 'Automatic'})\n"
            f"Player: {mvp_name}\n"
            f"Votes: {vote_count}/{MVP_VOTE_THRESHOLD}"
        )

        if notification_channel:
            await notification_channel.send(message)

        # Clear game state
        current_teams["team1"] = None
        current_teams["team2"] = None
        if lobby_id in mvp_votes:
            mvp_votes[lobby_id].clear()

        return True

    except Exception as e:
        print(f"Error updating MVP in database: {e}")
        return False


class MVPDropdown(discord.ui.Select):
    def __init__(self, winning_team_players, lobby_id):
        options = [
            discord.SelectOption(label=player.name, value=player.name)
            for player in winning_team_players
        ]
        super().__init__(
            placeholder="Select the MVP",
            min_values=1,
            max_values=1,
            options=options
        )
        self.lobby_id = lobby_id

    async def callback(self, interaction: discord.Interaction):
        selected_mvp = self.values[0]
        voter_id = f"{interaction.user.name}#{interaction.user.discriminator}"

        # Prevent self-voting
        if voter_id == selected_mvp:
            await interaction.response.send_message(
                "❌ You cannot vote for yourself!",
                ephemeral=True
            )
            return

        # Update vote count
        mvp_votes[self.lobby_id][selected_mvp] += 1
        current_votes = mvp_votes[self.lobby_id][selected_mvp]

        # Check if this vote reached the threshold
        if current_votes >= MVP_VOTE_THRESHOLD and self.lobby_id not in mvp_winners:
            # Try to update database
            success = await declare_mvp(
                self.lobby_id,
                int(self.lobby_id) + 1,
                selected_mvp,
                current_votes
            )

            if success:
                await interaction.response.send_message(
                    f"🎉 {selected_mvp} has reached {MVP_VOTE_THRESHOLD} votes and is the MVP!",
                    ephemeral=False
                )
            else:
                await interaction.response.send_message(
                    f"🎉 {selected_mvp} reached {MVP_VOTE_THRESHOLD} votes but couldn't save to database!",
                    ephemeral=False
                )
        else:
            await interaction.response.send_message(
                f"✅ You voted for {selected_mvp} (Total votes: {current_votes}/{MVP_VOTE_THRESHOLD})",
                ephemeral=True
            )
@tree.command(
    name="link",
    description="Link your Riot ID to your Discord account and update rank.",
    guild=discord.Object(GUILD),
)
async def link(interaction: discord.Interaction, riot_id: str):
    await interaction.response.defer(ephemeral=True)  # Defer the response immediately
    member = interaction.user

    if "#" not in riot_id:
        await interaction.followup.send("Invalid Riot ID format. Please use 'username#tagline'.", ephemeral=True)
        return

    summoner_name, tagline = riot_id.split("#", 1)
    summoner_name, tagline = summoner_name.strip(), tagline.strip()

    headers = {"X-Riot-Token": RIOT_API_KEY}
    url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{summoner_name}/{tagline}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=False) as response:
                if response.status == 200:
                    data = await response.json()
                    encrypted_summoner_id = await get_encrypted_summoner_id(riot_id)
                    rank = await update_player_rank(str(member.id), encrypted_summoner_id)

                    # Fetch the friendly Discord ID (username#discriminator)
                    friendly_discord_id = await get_friendly_discord_id(member.id, interaction.guild)
                    if not friendly_discord_id:
                        await interaction.followup.send("❌ Could not find your Discord account.", ephemeral=True)
                        return

                    # Fetch existing records from Google Sheets
                    existing_records = playerDB.get_all_records()
                    discord_id = str(member.id)
                    row_index = None

                    # Search for the player in the database using the friendly Discord ID
                    for i, record in enumerate(existing_records, start=2):  # Start from row 2 (headers in row 1)
                        if record.get("Discord ID") == friendly_discord_id:  # Compare using friendly Discord ID
                            row_index = i
                            break

                    if row_index:
                        # Player already exists in the database, update their Riot ID and rank
                        playerDB.update_cell(row_index, 2, friendly_discord_id)  # Update friendly Discord ID
                        playerDB.update_cell(row_index, 3, rank)  # Update Rank Tier

                        # Check if player is unranked and notify admin
                        if rank.lower() == "unranked":
                            admin_mention = get_admin_mention(interaction.guild)
                            notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
                            await notification_channel.send(
                                f"{admin_mention} - Player {member.mention} ({riot_id}) has linked their account but is UNRANKED!"
                            )

                        await interaction.followup.send(
                            f"Your Riot ID '{riot_id}' has been updated, and your rank has been updated to {rank}.",
                            ephemeral=True,
                        )
                    else:
                        # Player does not exist in the database, create a new row
                        new_row = [
                            member.display_name,  # Player Name
                            friendly_discord_id,  # Friendly Discord ID
                            rank,  # Rank Tier
                            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,   # Default stats
                        ]
                        playerDB.append_row(new_row)

                        # Check if player is unranked and notify admin
                        if rank.lower() == "unranked":
                            admin_mention = get_admin_mention(interaction.guild)
                            notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
                            await notification_channel.send(
                                f"{admin_mention} - New player {member.mention} ({riot_id}) has linked their account but is UNRANKED!"
                            )

                        await interaction.followup.send(
                            f"Your Riot ID '{riot_id}' has been linked, and your rank '{rank}' has been saved.",
                            ephemeral=True,
                        )

                else:
                    error_msg = await response.text()
                    await interaction.followup.send(
                        f"Failed to fetch Riot ID '{riot_id}'. Error: {error_msg}", ephemeral=True
                    )

    except Exception as e:
        print(f"An error occurred: {e}")
        await interaction.followup.send(
            "An unexpected error occurred while linking your Riot ID.", ephemeral=True
        )
async def get_encrypted_summoner_id(riot_id):
    """Fetches the encrypted summoner ID from Riot API using Riot ID."""
    if "#" not in riot_id:
        return None

    username, tagline = riot_id.split("#", 1)
    url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{username}/{tagline}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    data = await safe_api_call(url, headers)
    if data:
        puuid = data.get("puuid", None)
        if puuid:
            summoner_url = f"https://na1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
            summoner_data = await safe_api_call(summoner_url, headers)
            return summoner_data.get("id", None)  # Encrypted summoner ID

    return None


async def update_player_rank(discord_id, encrypted_summoner_id):
    """Fetches the player's rank from Riot API and updates Google Sheets."""
    await asyncio.sleep(3)  # Small delay to avoid rate-limiting

    url = f"https://na1.api.riotgames.com/lol/league/v4/entries/by-summoner/{encrypted_summoner_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=False) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Riot API Response: {data}")  # Debugging: Print the API response

                    for entry in data:
                        if entry.get("queueType") == "RANKED_SOLO_5x5":
                            rank = f"{entry.get('tier', 'UNRANKED')} {entry.get('rank', '')}".strip()

                            # Fetch existing records from Google Sheets
                            existing_records = playerDB.get_all_records()
                            row_index = None
                            for i, record in enumerate(existing_records, start=2):
                                if record["Discord ID"] == discord_id:
                                    row_index = i
                                    break

                            if row_index:
                                # Update Rank Tier in Google Sheets
                                playerDB.update_cell(row_index, 3, rank)  # Column 3 is "Rank Tier"
                                print(f"Updated Rank Tier for {discord_id} to {rank}")

                            return rank

                    return "UNRANKED"  # Default if no rank is found

    except Exception as e:
        print(f"Error fetching player rank: {e}")
        return "N/A"

@tree.command(
    name='stats',
    description='Get inhouse stats for a server member who has connected their Riot account with /link.',
    guild=discord.Object(GUILD)
)
async def stats(interaction: discord.Interaction, player: discord.Member):
    # Check if player name is given
    if not player:
        await interaction.response.send_message("Please provide a player name.", ephemeral=True)
        return

    try:
        # Defer the interaction response to prevent timeout
        await interaction.response.defer(ephemeral=True)

        # Fetch stats from the Google Sheet
        existing_records = playerDB.get_all_records()
        discord_id = str(player.id)

        # Find the player in the Google Sheet
        player_stats = None
        for record in existing_records:
            if record["Discord ID"] == discord_id:
                player_stats = record
                break

        # If player exists in the database, proceed
        if player_stats:
            riot_id = player_stats["Riot ID"]

            # Update encrypted summoner ID and rank in the database
            if riot_id:
                encrypted_summoner_id = await get_encrypted_summoner_id(riot_id)
                player_rank = await update_player_rank(str(player.id), encrypted_summoner_id)
            else:
                player_rank = "N/A"

            # Create an embed to display player stats
            embed = discord.Embed(
                title=f"{player.display_name}'s Stats",
                color=0xffc629  # Hex color #ffc629
            )
            embed.set_thumbnail(url=player.avatar.url if player.avatar else None)

            # Add player stats to the embed
            embed.add_field(name="Riot ID", value=riot_id or "N/A", inline=False)
            embed.add_field(name="Player Rank", value=player_rank, inline=False)
            embed.add_field(name="Participation Points", value=player_stats["Participation"], inline=True)
            embed.add_field(name="Games Played", value=player_stats["Games Played"], inline=True)
            embed.add_field(name="Wins", value=player_stats["Wins"], inline=True)
            embed.add_field(name="MVPs", value=player_stats["MVPs"], inline=True)
            embed.add_field(name="Win Rate",
                            value=f"{player_stats['WR %'] * 100:.0f}%" if player_stats['WR %'] is not None else "N/A",
                            inline=True)

            # Send the embed as a follow-up response
            await interaction.followup.send(embed=embed, ephemeral=True)

        else:
            await interaction.followup.send(f"No stats found for {player.display_name}", ephemeral=True)

    except Exception as e:
        # Log the error or handle it appropriately
        print(f"An error occurred: {e}")
        await interaction.followup.send("An unexpected error occurred while fetching player stats.", ephemeral=True)


@tree.command(
    name="unlink",
    description="Unlink a player's Riot ID and remove their statistics from the database.",
    guild=discord.Object(GUILD),
)
@commands.has_permissions(administrator=True)
async def unlink(interaction: discord.Interaction, player: discord.Member):
    try:
        # Fetch existing records from Google Sheets
        existing_records = playerDB.get_all_records()

        # Get the player's Discord ID and display name
        player_name = player.display_name
        row_index = None

        # Look for the player in the "Players1" column
        for i, record in enumerate(existing_records, start=2):  # Start from row 2 (headers are in row 1)
            if record.get("Players1") == player_name:  # Match by player name
                row_index = i
                break

        if row_index:
            # Delete the player's row from Google Sheets
            playerDB.delete_rows(row_index)

            await interaction.response.send_message(
                f"Successfully unlinked and removed {player_name}'s Riot ID and stats from the database.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"No records found for {player_name}.",
                ephemeral=True,
            )

    except commands.MissingPermissions:
        await interaction.response.send_message(
            "You do not have permission to use this command. Only administrators can unlink a player's account.",
            ephemeral=True,
        )

    except Exception as e:
        print(f"An error occurred: {e}")
        await interaction.response.send_message(
            "An unexpected error occurred while unlinking the account.", ephemeral=True
        )


@tree.command(
    name='confirm',
    description="Confirm the removal of a player's statistics from the database.",
    guild=discord.Object(GUILD)
)
@commands.has_permissions(administrator=True)
async def confirm(interaction: discord.Interaction):
    global player_to_unlink
    try:
        if player_to_unlink:
            # Fetch existing records from the Google Sheet
            existing_records = playerDB.get_all_records()
            discord_id = str(player_to_unlink.id)

            # Find the player in the Google Sheet
            player_stats = None
            for i, record in enumerate(existing_records):
                if record["Discord ID"] == discord_id:
                    player_stats = record
                    # Delete the row from the Google Sheet
                    playerDB.delete_rows(
                        i + 2)  # +2 because Google Sheets rows start at 1 and headers are row 1
                    break

            if player_stats:
                await interaction.response.send_message(
                    f"{player_to_unlink.display_name}'s Riot ID and statistics have been successfully unlinked and removed from the database.",
                    ephemeral=True)
                player_to_unlink = None
            else:
                await interaction.response.send_message(
                    f"No statistics found for {player_to_unlink.display_name}. Make sure the account is linked before attempting to unlink.",
                    ephemeral=True)
        else:
            await interaction.response.send_message("No player unlink request found. Please use /unlink first.",
                                                    ephemeral=True)

    except commands.MissingPermissions:
        await interaction.response.send_message(
            "You do not have permission to use this command. Only administrators can confirm the unlinking of a player's account.",
            ephemeral=True)

    except Exception as e:
        # Log the error or handle it appropriately
        print(f"An error occurred: {e}")
        await interaction.response.send_message(
            "An unexpected error occurred while confirming the unlinking of the account.", ephemeral=True)

        @tree.command(
            name='resetdb',
            description="Reset player data to defaults, except for ID/rank/role preference information.",
            guild=discord.Object(GUILD))
        async def resetdb(interaction: discord.Interaction):
            # Only the server owner can use this command
            if interaction.user != interaction.guild.owner:
                await interaction.response.send_message(
                    "You do not have permission to use this command. Only the server owner can reset the database.",
                    ephemeral=True
                )
                return

            # Send confirmation message to the server owner
            await interaction.response.send_message(
                "You are about to reset the player database to default values for participation, wins, MVPs, toxicity points, games played, win rate, and total points (excluding rank, tier, and role preferences). "
                "Please type /resetdb again within the next 10 seconds to confirm.",
                ephemeral=True
            )

            def check(res: discord.Interaction):
                # Check if the command is resetdb and if it's the same user who issued the original command
                return res.command.name == 'resetdb' and res.user == interaction.user

            try:
                # Wait for the confirmation within 10 seconds
                response = await client.wait_for('interaction', timeout=10.0, check=check)

                # If the confirmation is received, proceed with resetting the database
                existing_records = playerDB.get_all_records()
                for i, record in enumerate(existing_records):
                    # Reset all fields except Discord ID, Discord Username, Riot ID, Rank Tier, and Role Preferences
                    playerDB.update_cell(i + 2, 10, 0)  # Participation
                    playerDB.update_cell(i + 2, 11, 0)  # Wins
                    playerDB.update_cell(i + 2, 12, 0)  # MVPs
                    playerDB.update_cell(i + 2, 13, 0)  # Toxicity
                    playerDB.update_cell(i + 2, 14, 0)  # Games Played
                    playerDB.update_cell(i + 2, 15, 0)  # WR %
                    playerDB.update_cell(i + 2, 16, 0)  # Point Total

                # Send a follow-up message indicating the reset was successful
                await response.followup.send(
                    "The player database has been successfully reset to default values, excluding rank, tier, and role preferences.",
                    ephemeral=True
                )

            except asyncio.TimeoutError:
                # If no confirmation is received within 10 seconds, send a follow-up message indicating timeout
                await interaction.followup.send(
                    "Reset confirmation timed out. Please type /resetdb again if you still wish to reset the database.",
                    ephemeral=True
                )


async def update_tier_based_on_winrate(discord_id):
    records = playerDB.get_all_records()
    for i, record in enumerate(records, start=2):
        if record["Discord ID"] == discord_id:
            games_played = int(record.get("Games Played", 0))
            wins = int(record.get("Wins", 0))
            winrate = wins / games_played if games_played > 0 else 0
            current_tier = record["Rank Tier"].lower()

            if winrate > 0.7 and current_tier != "challenger":
                new_tier = list(TIER_VALUES.keys())[list(TIER_VALUES.keys()).index(current_tier) - 1]
                playerDB.update_cell(i, 3, new_tier.capitalize())
            elif winrate < 0.3 and current_tier != "unranked":
                new_tier = list(TIER_VALUES.keys())[list(TIER_VALUES.keys()).index(current_tier) + 1]
                playerDB.update_cell(i, 3, new_tier.capitalize())
            break

@tree.command(
    name="set_tier",
    description="Manually set a player's tier (Admin only).",
    guild=discord.Object(GUILD)
)
@commands.has_permissions(administrator=True)
async def set_tier(interaction: discord.Interaction, player: discord.Member, tier: str):
    valid_tiers = TIER_VALUES.keys()
    if tier not in valid_tiers:
        await interaction.response.send_message(f"❌ Invalid tier. Valid options: {', '.join(valid_tiers)}", ephemeral=True)
        return

    try:
        friendly_discord_id = await get_friendly_discord_id(player.id, interaction.guild)
        existing_records = playerDB.get_all_records()
        row_index = None

        # Find player in database
        for i, record in enumerate(existing_records, start=2):
            if record.get("Discord ID") == friendly_discord_id:
                row_index = i
                break

        if row_index:
            # Update tier in spreadsheet (capitalized for consistency)
            playerDB.update_cell(row_index, 3, tier.capitalize())

            # Send confirmation
            await interaction.response.send_message(
                f"✅ Set {player.display_name}'s tier to Tier {tier}",
                ephemeral=True
            )

            # Log change in notification channel
            notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
            if notification_channel:
                await notification_channel.send(
                    f"⚙️ Admin {interaction.user.mention} manually set "
                    f"{player.mention}'s tier to  Tier {tier}"
                )
        else:
            await interaction.response.send_message(
                f"❌ Player {player.display_name} not found in database",
                ephemeral=True
            )

    except Exception as e:
        print(f"Error in set_tier: {e}")
        await interaction.response.send_message(
            "❌ Failed to update tier. Please try again.",
            ephemeral=True
        )

class RolePreferenceView(discord.ui.View):
    def __init__(self, member_id):
        super().__init__(timeout=60)
        self.member_id = member_id
        self.role_preferences = {}  # Stores the role preferences
        self.rank_counter = 1  # Tracks the ranking from 1 to 5
        self.add_item(RolePreferenceDropdown())  # Add the role dropdown
        self.add_item(SubmitButton())  # Add the submit button
        self.add_item(BackButton())  # Add the back button

    async def update_embed(self, interaction: discord.Interaction):
        # Update the embed to reflect the current role preferences
        embed = discord.Embed(
            title="Role Preferences",
            description="Select your preferred roles in order. (1 = most preferred, 5 = least preferred)",
            color=0xffc629
        )
        for role, preference in self.role_preferences.items():
            embed.add_field(name=role, value=f"Preference: {preference}", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    async def save_preferences(self, interaction: discord.Interaction):
        try:
            # Fetch the friendly Discord ID (username#discriminator)
            guild = interaction.guild  # Get the guild object from the interaction
            friendly_discord_id = await get_friendly_discord_id(self.member_id, guild)  # Fetch friendly ID
            if not friendly_discord_id:  # Check if the friendly ID was fetched successfully
                await interaction.response.send_message("❌ Could not find your Discord account.", ephemeral=True)
                return

            # Fetch existing records from Google Sheets
            existing_records = playerDB.get_all_records()

            row_index = None

            # Search for the player using the friendly Discord ID
            for i, record in enumerate(existing_records, start=2):  # Start from row 2 (headers in row 1)
                if record.get("Discord ID") == friendly_discord_id:
                    row_index = i
                    break

            if row_index:
                # Update existing player's role preferences
                role_order = ["Top", "Jungle", "Mid", "ADC", "Support"]
                for idx, role in enumerate(role_order, start=4):  # Columns 4-8 are for role preferences
                    value = self.role_preferences.get(role, record.get(role, 0))  # Keep existing value if not updated
                    playerDB.update_cell(row_index, idx, value)

                await interaction.response.send_message("✅ Your role preferences have been updated!", ephemeral=True)
            else:
                # Don't create new entry, just inform user they need to link first
                await interaction.response.send_message(
                    "❌ You must link your Riot ID using /link before setting role preferences.",
                    ephemeral=True
                )

        except Exception as e:
            print(f"An error occurred: {e}")
            await interaction.response.send_message(
                "❌ An unexpected error occurred while saving your preferences.", ephemeral=True
            )


class RolePreferenceDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Top", value="Top"),
            discord.SelectOption(label="Jungle", value="Jungle"),
            discord.SelectOption(label="Mid", value="Mid"),
            discord.SelectOption(label="ADC", value="ADC"),
            discord.SelectOption(label="Support", value="Support"),
        ]
        super().__init__(placeholder="Select your role preference", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: RolePreferenceView = self.view
        if self.values[0] not in view.role_preferences:
            view.role_preferences[self.values[0]] = view.rank_counter
            view.rank_counter += 1
        await view.update_embed(interaction)


class SubmitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Submit", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        view: RolePreferenceView = self.view
        if len(view.role_preferences) < 5:
            await interaction.response.send_message("⚠ Please select all five roles before submitting.", ephemeral=True)
        else:
            await view.save_preferences(interaction)  # Call the save_preferences method


class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.red)

    async def callback(self, interaction: discord.Interaction):
        view: RolePreferenceView = self.view
        if view.role_preferences:
            # Remove the last selected role
            last_role = list(view.role_preferences.keys())[-1]
            del view.role_preferences[last_role]
            view.rank_counter -= 1  # Decrement the rank counter
            await view.update_embed(interaction)  # Update the embed to reflect the changes
        else:
            await interaction.response.send_message("No roles to remove.", ephemeral=True)


@tree.command(
    name="rolepreference",
    description="Set your role preferences for matchmaking.",
    guild=discord.Object(GUILD),
)
async def rolepreference(interaction: discord.Interaction):
    member = interaction.user

    # Check if the user has the Player or Volunteer role
    if not any(role.name in ["Player", "Volunteer"] for role in member.roles):
        await interaction.response.send_message(
            "❌ You must have the Player or Volunteer role to set role preferences.", ephemeral=True
        )
        return

    # Create the role preference view
    view = RolePreferenceView(member.id)
    embed = discord.Embed(
        title="Role Preferences",
        description="Please rank your preferences for each role (1 = most preferred, 5 = least preferred).",
        color=0xffc629,
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def update_participation(player_name: str, is_winner: bool = False, points: int = 1):
    """Update all player statistics including participation, wins, and games played"""
    try:
        # Refresh player data to get latest values
        
        existing_records = playerDB.get_all_records()

        for i, record in enumerate(existing_records, start=2):  # Start from row 2
            if record.get("Players1") == player_name:
                # Get current values with defaults if empty
                current_part = int(record.get("Current Participation", 0))
                total_part = int(record.get("Total Participation", 0))
                games_played = int(record.get("Games Played", 0))
                current_wins = int(record.get("Wins (this tier)", 0))
                total_wins = int(record.get("Wins (Total)", 0))

                # Update participation stats (using your existing logic)
                new_current = current_part + points
                new_total = total_part + points
                new_games = games_played + 1

                playerDB.update_cell(i, 9, new_current)  # Current Participation (Column I)
                playerDB.update_cell(i, 10, new_total)  # Total Participation (Column J)
                playerDB.update_cell(i, 14, new_games)  # Games Played (Column N)

                # Update win stats if player is on winning team
                if is_winner:
                    playerDB.update_cell(i, 11, current_wins + 1)  # Current Tier Wins (Column K)
                    playerDB.update_cell(i, 12, total_wins + 1)  # Total Wins (Column L)

                # Reset current participation every 15 games (your existing logic)
                if new_games % 15 == 0:
                    playerDB.update_cell(i, 9, 0)

                # Update win rate
                new_win_rate = (total_wins + (1 if is_winner else 0)) / max(1, new_games)
                playerDB.update_cell(i, 15, round(new_win_rate, 2))  # Win Rate (Column O)

                return True

        print(f"Player {player_name} not found in database")
        return False

    except Exception as e:
        print(f"Error updating participation for {player_name}: {e}")
        return False


async def adjust_tiers():
    """Automatically adjust player tiers based on performance and participation"""
    try:
        # Define tier hierarchy
        TIER_HIERARCHY = [
            "unranked", "iron", "bronze", "silver", "gold",
            "platinum", "emerald", "diamond", "master",
            "grandmaster", "challenger"
        ]

        # Use safe sheet fetching with rate limiting
        existing_records = await safe_sheet_fetch(playerDB)

        # Batch updates to reduce API calls
        updates = []
        notifications = []

        for i, record in enumerate(existing_records, start=2):
            try:
                # Safely extract values with defaults
                games_played = int(record.get("Games Played", 0))
                if games_played < 5:  # Minimum games threshold
                    continue

                wins = int(record.get("Wins", 0))
                total_participation = int(record.get("Total Participation", 0))
                current_tier = str(record.get("Rank Tier", "UNRANKED")).lower().split()[0]

                # Calculate metrics
                win_rate = wins / games_played
                participation_rate = total_participation / games_played

                # Skip if tier is invalid
                if current_tier not in TIER_HIERARCHY:
                    continue

                current_index = TIER_HIERARCHY.index(current_tier)
                new_tier = None
                message = None

                # Promotion logic
                if (win_rate > 0.65 and participation_rate > 0.8
                        and current_tier != "challenger"):
                    new_tier = TIER_HIERARCHY[min(current_index + 1, len(TIER_HIERARCHY) - 1)]
                    message = (
                        f"⬆️ {record.get('Players1', 'Player')} promoted to {new_tier.capitalize()}! "
                        f"(WR: {win_rate:.0%}, Part: {participation_rate:.0%})"
                    )

                # Demotion logic
                elif (win_rate < 0.35 and participation_rate < 0.5
                      and current_tier != "unranked"):
                    new_tier = TIER_HIERARCHY[max(current_index - 1, 0)]
                    message = (
                        f"⬇️ {record.get('Players1', 'Player')} demoted to {new_tier.capitalize()}. "
                        f"(WR: {win_rate:.0%}, Part: {participation_rate:.0%})"
                    )

                # Queue updates
                if new_tier:
                    updates.append((i, 3, new_tier.capitalize()))  # (row, col, value)
                    if message:
                        notifications.append(message)

            except Exception as e:
                print(f"Error processing player {record.get('Players1', 'Unknown')}: {str(e)}")
                continue

        # Batch update spreadsheet
        if updates:
            await batch_sheet_update(playerDB, updates)

        # Send notifications
        if notifications and NOTIFICATION_CHANNEL_ID:
            notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
            if notification_channel:
                for msg in notifications:
                    try:
                        await notification_channel.send(msg)
                        await asyncio.sleep(1)  # Rate limit Discord messages
                    except Exception as e:
                        print(f"Error sending notification: {str(e)}")

    except Exception as e:
        print(f"System error in adjust_tiers(): {str(e)}")
        raise
# Player class.
class participant():

    def __init__(self, playerName, playerTier, topPreference, jgPreference, midPreference, adcPreference,
                 supPreference):

        self.name = playerName
        self.tier = playerTier
        self.baseQualityPoints = int(TIER_VALUES[str(self.tier)]) + random.uniform(-randomness, randomness)
        self.topPreference = topPreference
        self.topQP = self.baseQualityPoints + random.uniform(-randomness,randomness)
        self.jgPreference = jgPreference
        self.jgQP = self.baseQualityPoints + random.uniform(-randomness,randomness)
        self.midPreference = midPreference
        self.midQP = self.baseQualityPoints + random.uniform(-randomness,randomness)
        self.adcPreference = adcPreference
        self.adcQP = self.baseQualityPoints + random.uniform(-randomness,randomness)
        self.supPreference = supPreference
        self.supQP = self.baseQualityPoints + random.uniform(-randomness,randomness)
        self.QPList = [self.topQP, self.jgQP, self.midQP, self.adcQP, self.supQP]
        self.currentRole = ""
        self.currentQP = 0

# Team class.
class team():

    def __init__(self, playerList):

        self.playerList = playerList
        self.topLaner = playerList[0]
        self.topLaner.currentRole = "top"
        self.jgLaner = playerList[1]
        self.jgLaner.currentRole = "jg"
        self.midLaner = playerList[2]
        self.midLaner.currentRole = "mid"
        self.adcLaner = playerList[3]
        self.adcLaner.currentRole = "adc"
        self.supLaner = playerList[4]
        self.supLaner.currentRole = "sup"
        self.playerListNames = [self.topLaner.name, self.jgLaner.name, self.midLaner.name, self.adcLaner.name,
                                self.supLaner.name]
        self.teamTotalQP = round(
            playerList[0].baseQualityPoints + playerList[1].baseQualityPoints + playerList[2].baseQualityPoints +
            playerList[3].baseQualityPoints +
            playerList[4].baseQualityPoints + random.uniform(-randomness, randomness), 2)
        self.averageTeamQP = round(self.teamTotalQP / len(self.playerList), 2)

    def updateTeamQP(self):

        self.topLaner = self.playerList[0]
        self.topLaner.currentRole = "top"
        self.jgLaner = self.playerList[1]
        self.jgLaner.currentRole = "jg"
        self.midLaner = self.playerList[2]
        self.midLaner.currentRole = "mid"
        self.adcLaner = self.playerList[3]
        self.adcLaner.currentRole = "adc"
        self.supLaner = self.playerList[4]
        self.supLaner.currentRole = "sup"

        total = 0
        for x in range(0, len(self.playerList)):
            total += self.playerList[x].baseQualityPoints

        self.teamTotalQP = round((total), 2)
        self.averageTeamQP = round(self.teamTotalQP / len(self.playerList), 2)

    def assignRole(self, player, role):

        match role:

            case "top":

                self.topLaner = player

            case "jg":

                self.jgLaner = player

            case "mid":

                self.midLaner = player

            case "adc":

                self.adcLaner = player

            case "sup":

                self.supLaner = player

            case "":

                return

    def findLowestQP(self):

        lowest = 1000

        for player in [self.topLaner, self.jgLaner, self.midLaner, self.adcLaner, self.supLaner]:

            if player.baseQualityPoints < lowest:
                lowestPlayer = player
                lowest = lowestPlayer.baseQualityPoints

        return lowestPlayer

    def findHighestQP(self):

        highest = 0

        for player in [self.topLaner, self.jgLaner, self.midLaner, self.adcLaner, self.supLaner]:

            if player.baseQualityPoints > highest:
                highestPlayer = player
                highest = highestPlayer.baseQualityPoints

        return highestPlayer

    def selfSortMatchmaking(self):

        all_potential_role_assignments = list(itertools.permutations(range(1, 6)))
        best_assignment = None
        lowest_score = float('inf')

        for potentialAssignment in all_potential_role_assignments:
            current_score = self.checkScore(potentialAssignment)

            # If we find a lower score, update the best_assignment and lowest_score
            if current_score < lowest_score:
                best_assignment = potentialAssignment
                lowest_score = current_score

        # Return the best assignment found
        return best_assignment

    def findListOfBestToWorstRoleAssignments(self):

        myList = []
        all_potential_role_assignments = list(itertools.permutations(range(1, 6)))
        best_assignment = None
        lowest_score = float('inf')

        for potentialAssignment in all_potential_role_assignments:
            current_score = self.checkScore(potentialAssignment)
            myList.append([current_score, potentialAssignment])

        intermediateList = (sorted(myList, key=operator.itemgetter(0)))
        finalList = []
        for x in range(0, len(intermediateList)):
            finalList.append(intermediateList[x][1])

        self.listOfBestToWorstRoleAssignments = finalList
        self.listOfAssignmentsScoreAndAssignment = myList

    def checkScore(self, potentialAssignment):

        total_score = 0
        self.playerList = [self.topLaner, self.jgLaner, self.midLaner, self.adcLaner, self.supLaner]

        for z in range(0, len(potentialAssignment)):

            if potentialAssignment[z] == 1:

                total_score += int(self.playerList[z].topPreference)

            elif potentialAssignment[z] == 2:

                total_score += int(self.playerList[z].jgPreference)

            elif potentialAssignment[z] == 3:

                total_score += int(self.playerList[z].midPreference)

            elif potentialAssignment[z] == 4:

                total_score += int(self.playerList[z].adcPreference)

            else:

                total_score += int(self.playerList[z].supPreference)

        return total_score

    def reinstateIdealizedRoles(self):

        idealRoles = self.selfSortMatchmaking()
        idealTeam = [0, 0, 0, 0, 0]

        for x in range(0, len(idealRoles)):

            if idealRoles[x] == 1:

                idealTeam[0] = self.playerList[x]

            elif idealRoles[x] == 2:

                idealTeam[1] = self.playerList[x]

            elif idealRoles[x] == 3:

                idealTeam[2] = self.playerList[x]

            elif idealRoles[x] == 4:

                idealTeam[3] = self.playerList[x]

            elif idealRoles[x] == 5:

                idealTeam[4] = self.playerList[x]

        modifiedTeam = team(idealTeam)

        self.__dict__.update(modifiedTeam.__dict__)

        self.updateTeamQP() 

def isPlayerMatchupValidMostRestrictive(player1, player2): 

    # This is the most restrictive checks. If a team passes these tests, they will be quite balanced.

    # Tiers are closely tied to rank. Tier 1 is GM/Challenger, Tier 2 is Master/Diamond
    # Tier 3 is Emerald, Tier 4 is Platinum, Tier 5 is Gold, Tier 6 is Silver, Tier 7 is Bronze/Iron

    if player1.tier == 1 and player2.tier == 1: # GM and Challenger Players can play vs each other.

        return True

    elif player1.tier == 2 and player2.tier == 2: # Masters and Diamonds can play vs each other.

        return True

    elif player1.tier  in [3,4] and player2.tier in [3,4]: # Emerald and Platinum can play vs each other.

        return True

    elif player1.tier in [4,5] and player2.tier in [4,5]: # Platinum and Gold can play vs each other.

        return True

    elif player1.tier in [5,6] and player2.tier in [5,6]: # Gold and Silver can play against each other.

        return True

    elif player1.tier in [7] and player2.tier in [7]: # Bronze and Iron can play against each other.

        return True

    else:

        return False

def isPlayerMatchupValidMediumRestrictive(player1, player2):

    # This is the medium-level restrictive checks. If a team passes these tests, they will still probably be decent teams.

    # Tiers are closely tied to rank. Tier 1 is GM/Challenger, Tier 2 is Master/Diamond
    # Tier 3 is Emerald, Tier 4 is Platinum, Tier 5 is Gold, Tier 6 is Silver, Tier 7 is Bronze/Iron

    if player1.tier == 1 and player2.tier == 1: # GM and Challenger Players can play vs each other.

        return True

    elif player1.tier == 2 and player2.tier == 2: # Masters and Diamonds can play vs each other.

        return True

    elif player1.tier  in [3,4] and player2.tier in [3,4]: # Emerald and Platinum can play vs each other.

        return True

    elif player1.tier in [4,5,6] and player2.tier in [4,5,6]: # Platinum, Gold, and Silver can play vs each other.

        return True

    elif player1.tier in [6,7] and player2.tier in [6,7]: # Silver Bronze, and Iron can play against each other.

        return True

    else:

        return False

def isPlayerMatchupValidLowRestrictive(player1, player2):

    # This is the low-restriction checks. Teams will, on average, be less balanced here.
    
    # Tiers are closely tied to rank. Tier 1 is GM/Challenger, Tier 2 is Master/Diamond
    # Tier 3 is Emerald, Tier 4 is Platinum, Tier 5 is Gold, Tier 6 is Silver, Tier 7 is Bronze/Iron

    if player1.tier in [1,2] and player2.tier in [1,2]: # GM, Challenger, Master, and Diamond players can all play together.

        return True

    elif player1.tier in [2,3] and player2.tier in [2,3]: # Masters, Diamonds and Emeralds can play vs each other. They can also match up one or down one tier.

        return True

    elif player1.tier in [3,4,5] and player2.tier in [3,4,5]: # Emerald, Platinum, and Gold can play vs each other.

        return True

    elif player1.tier in [4,5,6] and player2.tier in [4,5,6]: # Platinum, Gold, and Silver can play against each other.

        return True

    elif player1.tier in [6,7] and player2.tier in [6,7]: # Silver Bronze, and Iron can play against each other.

        return True

    else:

        return False

def isPlayerMatchupValidLeastRestrictive(player1, player2):

    # This is the lowest restriction checks. Teams will, on average, be much less balanced here.

    # Tiers are closely tied to rank. Tier 1 is GM/Challenger, Tier 2 is Master/Diamond
    # Tier 3 is Emerald, Tier 4 is Platinum, Tier 5 is Gold, Tier 6 is Silver, Tier 7 is Bronze/Iron

    if player1.tier in [1,2] and player2.tier in [1,2]: # GM, Challenger, Master, and Diamond players can all play together.

        return True

    elif player1.tier in [2,3,4] and player2.tier in [2,3,4]: # Masters, Diamonds and Emeralds can play vs each other.

        return True

    elif player1.tier in [3,4,5,6] and player2.tier in [3,4,5,6]: # Emerald, Platinum, Gold, and Silver can play against each other.

        return True

    elif player1.tier in [6,7] and player2.tier in [6,7]: # Silver Bronze, and Iron can play against each other.

        return True

    else:

        return False

def createDummyTeam(teamPlayerList, roleConfiguration):
    idealRoles = roleConfiguration
    idealTeam = [0, 0, 0, 0, 0]

    for x in range(0, len(idealRoles)):

        if idealRoles[x] == 1:

            idealTeam[0] = teamPlayerList[x]

        elif idealRoles[x] == 2:

            idealTeam[1] = teamPlayerList[x]

        elif idealRoles[x] == 3:

            idealTeam[2] = teamPlayerList[x]

        elif idealRoles[x] == 4:

            idealTeam[3] = teamPlayerList[x]

        elif idealRoles[x] == 5:

            idealTeam[4] = teamPlayerList[x]

    modifiedTeam = team(idealTeam)
    """
    print("This is the team that has been created:")

    print(str(modifiedTeam.topLaner.name) + ', ' + str(modifiedTeam.topLaner.rank))
    print(str(modifiedTeam.jgLaner.name) + ', ' + str(modifiedTeam.jgLaner.rank))
    print(str(modifiedTeam.midLaner.name) + ', ' + str(modifiedTeam.midLaner.rank))
    print(str(modifiedTeam.adcLaner.name) + ', ' + str(modifiedTeam.adcLaner.rank))
    print(str(modifiedTeam.supLaner.name) + ', ' + str(modifiedTeam.supLaner.rank))
    """
    return modifiedTeam


def formatList(playerList): # Takes in player data and turns them into player objects.
    returnableList = []
    # Ensure the playerList has the correct number of columns (7 per player)
    for x in range(0, len(playerList), 7):
        try:
            # Extract player data
            playerName = playerList[x]
            playerTier = playerList[x + 1]
            topPreference = int(playerList[x + 2])
            jgPreference = int(playerList[x + 3])
            midPreference = int(playerList[x + 4])
            adcPreference = int(playerList[x + 5])
            supPreference = int(playerList[x + 6])

            # Create a participant object
            participantToAdd = participant(
                playerName, playerTier, topPreference, jgPreference,
                midPreference, adcPreference, supPreference
            )
            print(f"Adding participant: {participantToAdd.name}")
            returnableList.append(participantToAdd)
        except Exception as e:
            print(f"Error creating participant from row {x}: {e}")
            continue

    return returnableList


def save_teams_to_sheet(teams):
    """Save teams to Google Sheets GameDatabase"""
    team1, team2 = teams

    try:
        # Get the next game ID
        all_game_ids = gameDB.col_values(1)  # Column A has game IDs
        if not all_game_ids:
            currentGameID = 1
        else:
            try:
                last_id = max(int(id) for id in all_game_ids if id.isdigit())
                currentGameID = last_id + 1
            except:
                currentGameID = 1

        # Prepare the row data
        row_data = [
            str(currentGameID),  # Game ID (Column A)
            tourneyDB.col_values(1)[-1],  # Tournament ID (Column B)
            "",  # Winning Team (Column C) - empty initially
            "",  # MVP (Column D) - empty initially
            # Team 1 Players (Columns E-I)
            team1.topLaner.name,
            team1.jgLaner.name,
            team1.midLaner.name,
            team1.adcLaner.name,
            team1.supLaner.name,
            # Team 2 Players (Columns J-N)
            team2.topLaner.name,
            team2.jgLaner.name,
            team2.midLaner.name,
            team2.adcLaner.name,
            team2.supLaner.name
        ]

        # Find the first empty row
        all_rows = gameDB.get_all_values()
        first_empty_row = len(all_rows) + 1

        # Update the worksheet
        gameDB.update(          
            [row_data],
            f"A{first_empty_row}:N{first_empty_row}",
            value_input_option="USER_ENTERED"
        )

        print(f"Successfully saved game {currentGameID} to database")

    except Exception as e:
        print(f"Error saving to GameDatabase: {e}")
        raise

def swapPlayerRolesSameTeam(team, player1, player2):
    swap1Role = player1.currentRole
    swap2Role = player2.currentRole

    match swap1Role:

        case "top":

            team.playerList[0] = player2

        case "jg":

            team.playerList[1] = player2

        case "mid":

            team.playerList[2] = player2

        case "adc":

            team.playerList[3] = player2

        case "sup":

            team.playerList[4] = player2

    match swap2Role:

        case "top":

            team.playerList[0] = player1

        case "jg":

            team.playerList[1] = player1

        case "mid":

            team.playerList[2] = player1

        case "adc":

            team.playerList[3] = player1

        case "sup":

            team.playerList[4] = player1

    team.updateTeamQP()


def swapPlayersToDifferentTeam(player1, team1, player2, team2):
    if player1 in [team1.topLaner, team1.jgLaner, team1.midLaner, team1.adcLaner,
                   team1.supLaner]:  # They need to go to team 2

        team2.playerList.append(player1)
        team1.playerList.append(player2)
        team2.playerList.remove(player2)
        team1.playerList.remove(player1)

    else:

        team1.playerList.append(player1)
        team2.playerList.append(player2)
        team1.playerList.remove(player2)
        team2.playerList.remove(player1)

    team1.updateTeamQP()
    team2.updateTeamQP()

    team1.reinstateIdealizedRoles()
    team2.reinstateIdealizedRoles()


async def send_team_embed(interaction, team1, team2, is_balanced=True):
    """
    Send a Discord embed showing team information
    - interaction: The Discord interaction object
    - team1: First team object
    - team2: Second team object
    - is_balanced: Whether teams are properly balanced
    """
    # Create embed
    if is_balanced:
        embed = discord.Embed(
            title="✅ Balanced Teams Created",
            description="Matchmaking created balanced teams successfully!",
            color=0x00ff00  # Green
        )
    else:
        embed = discord.Embed(
            title="⚠️ Warning: Potentially Imbalanced Teams",
            description="Matchmaking couldn't create perfectly balanced teams.\nAdmin review recommended!",
            color=0xffcc00  # Yellow
        )

    # Add team info
    def format_team(team):
        return (
            f"Top: {team.topLaner.name} ({team.topLaner.tier})\n"
            f"Jungle: {team.jgLaner.name} ({team.jgLaner.tier})\n"
            f"Mid: {team.midLaner.name} ({team.midLaner.tier})\n"
            f"ADC: {team.adcLaner.name} ({team.adcLaner.tier})\n"
            f"Support: {team.supLaner.name} ({team.supLaner.tier})\n"
            f"Team QP: {team.teamTotalQP:.2f}"
        )

    embed.add_field(name="🔷 Team 1", value=format_team(team1), inline=False)
    embed.add_field(name="🔴 Team 2", value=format_team(team2), inline=False)

    # Send to both notification channel and command issuer
    try:
        notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
        await notification_channel.send(embed=embed)
    except:
        print("Couldn't send to notification channel")

    await interaction.followup.send(embed=embed)


async def optimizeTeams(team1,team2):

    caseNumber = 0

    # Case 1----------------------------------------------------------------------------------------

    if (team1.teamTotalQP - team2.teamTotalQP) < 0 and abs(
            team1.teamTotalQP - team2.teamTotalQP) > 75:  # Case 1: A negative difference that is larger than an arbirary large number means that team 2 is better than team 1 and teams are too unbalanced

        caseNumber = 1
        print("Case 1 is happening")
        print("Total difference is: ")
        print((team1.teamTotalQP - team2.teamTotalQP))

        print('swapping players')
        print('team 1 before swap: ')
        print(team1.topLaner.name)
        print(team1.jgLaner.name)
        print(team1.midLaner.name)
        print(team1.adcLaner.name)
        print(team1.supLaner.name)
        print('team 2 before swap: ')
        print(team2.topLaner.name)
        print(team2.jgLaner.name)
        print(team2.midLaner.name)
        print(team2.adcLaner.name)
        print(team2.supLaner.name)
        print('worst player on team 1 is: ')
        print(team2.findLowestQP().name)
        print('worst player on team 1s role is: ')
        print(team2.findLowestQP().currentRole)
        print('best player on team 2 is: ')
        print(team2.findHighestQP().name)
        print('best player on team 2s role is: ')
        print(team2.findHighestQP().currentRole)

        swapPlayersToDifferentTeam(team1.findLowestQP(), team1,
                                    team2.findHighestQP(), team2)

        print("swap complete")
        print('team 1 after swap: ')
        print(team1.topLaner.name)
        print(team1.jgLaner.name)
        print(team1.midLaner.name)
        print(team1.adcLaner.name)
        print(team1.supLaner.name)
        print('team 2 after swap: ')
        print(team2.topLaner.name)
        print(team2.jgLaner.name)
        print(team2.midLaner.name)
        print(team2.adcLaner.name)
        print(team2.supLaner.name)
        print("Total difference is now: ")
        print(((team1.teamTotalQP) - (team2.teamTotalQP)))

        if (team1.teamTotalQP - team2.teamTotalQP) < 0 and abs(
                team1.teamTotalQP - team2.teamTotalQP) > absoluteMaximumDifference:

            needsOptimization = True
            print("Still needs work! Case 1 complete")
            print("Current QP difference is: ")
            print(team1.teamTotalQP - team2.teamTotalQP)

        else:

            needsOptimization = False
            print("Might be relatively balanced! Case 1 complete")
            print("Current QP difference is: ")
            print(team1.teamTotalQP - team2.teamTotalQP)

    # Case 1----------------------------------------------------------------------------------------

    # Case 2----------------------------------------------------------------------------------------

    elif (team1.teamTotalQP - team2.teamTotalQP) > 0 and abs(
            team1.teamTotalQP - team2.teamTotalQP) > 75:  # Case 2: A positive difference that is larger than an arbitrary large number means that team 1 is better than team 2 and teams are too unbalanced

        caseNumber = 2
        print("Case 2 is happening")
        print("Total difference is: ")
        print((team1.teamTotalQP - team2.teamTotalQP))

        print('swapping players')
        print('team 1 before swap: ')
        print(team1.topLaner.name)
        print(team1.jgLaner.name)
        print(team1.midLaner.name)
        print(team1.adcLaner.name)
        print(team1.supLaner.name)
        print('team 2 before swap: ')
        print(team2.topLaner.name)
        print(team2.jgLaner.name)
        print(team2.midLaner.name)
        print(team2.adcLaner.name)
        print(team2.supLaner.name)
        print('worst player on team 2 is: ')
        print(team2.findLowestQP().name)
        print('worst player on team 2s role is: ')
        print(team2.findLowestQP().currentRole)
        print('best player on team 1 is: ')
        print(team1.findHighestQP().name)
        print('best player on team 1s role is: ')
        print(team1.findHighestQP().currentRole)

        swapPlayersToDifferentTeam(team1.findHighestQP(), team1,
                                    team2.findLowestQP(), team2)

        print("swap complete")
        print('team 1 after swap: ')
        print(team1.topLaner.name)
        print(team1.jgLaner.name)
        print(team1.midLaner.name)
        print(team1.adcLaner.name)
        print(team1.supLaner.name)
        print('team 2 after swap: ')
        print(team2.topLaner.name)
        print(team2.jgLaner.name)
        print(team2.midLaner.name)
        print(team2.adcLaner.name)
        print(team2.supLaner.name)
        print("Total difference is now: ")
        print((team1.teamTotalQP - team2.teamTotalQP))

        if (team1.teamTotalQP - team2.teamTotalQP) > 0 and abs(
                team1.teamTotalQP - team2.teamTotalQP) > absoluteMaximumDifference:

            needsOptimization = True
            print("Still needs work! Case 2 complete")
            print("Current QP difference is: ")
            print(team1.teamTotalQP - team2.teamTotalQP)

        else:

            needsOptimization = False
            print("Might be relatively balanced! Case 2 complete")
            print("Current QP difference is: ")
            print(team1.teamTotalQP - team2.teamTotalQP)

    # Case 2----------------------------------------------------------------------------------------

    # Case 3----------------------------------------------------------------------------------------

    elif (team1.teamTotalQP - team2.teamTotalQP) < 0 and abs(
            team1.teamTotalQP - team2.teamTotalQP) > absoluteMaximumDifference:  # Case 3: A negative difference that is larger than the maximum but smaller than an arbitrary large number means that team 2 is better than team 1 and teams are only slightly unbalanced.

        caseNumber = 3
        print("Case 3 is happening")
        print("Total difference before making a swap is: ")
        print(abs(team1.teamTotalQP - team2.teamTotalQP))

        team1List = [team1.topLaner, team1.jgLaner, team1.midLaner,
                        team1.adcLaner, team1.supLaner]
        team1WorstToBest = (sorted(team1List, key=lambda x: x.baseQualityPoints))
        team2List = [team2.topLaner, team2.jgLaner, team2.midLaner,
                        team2.adcLaner, team2.supLaner]
        team2WorstToBest = (sorted(team2List, key=lambda x: x.baseQualityPoints))

        randomPlayerTeam1 = team1WorstToBest[2:]
        randomChoice1 = random.choice(randomPlayerTeam1)

        randomPlayerTeam2 = team2WorstToBest[:2]
        randomChoice2 = random.choice(randomPlayerTeam2)

        swapPlayersToDifferentTeam(randomChoice1, team1, randomChoice2, team2)
        print("Made a swap!")
        print("Total difference after making a swap is: ")
        print((team1.teamTotalQP - team2.teamTotalQP))

    # Case 3----------------------------------------------------------------------------------------

    # Case 4----------------------------------------------------------------------------------------

    elif (team1.teamTotalQP - team2.teamTotalQP) > 0 and abs(
            team1.teamTotalQP - team2.teamTotalQP) > absoluteMaximumDifference:  # Case 4: A positive difference that is larger than the maximum but smaller than an arbitrary large number means that team 1 is better than team 2 and teams are only slightly unbalanced.

        caseNumber = 4
        print("Case 4 is happening")
        print("Total difference before making a swap is: ")
        print((team1.teamTotalQP - team2.teamTotalQP))

        team1List = [team1.topLaner, team1.jgLaner, team1.midLaner,
                        team1.adcLaner, team1.supLaner]
        team1WorstToBest = (sorted(team1List, key=lambda x: x.baseQualityPoints))
        team2List = [team2.topLaner, team2.jgLaner, team2.midLaner,
                        team2.adcLaner, team2.supLaner]
        team2WorstToBest = (sorted(team2List, key=lambda x: x.baseQualityPoints))

        randomPlayerTeam1 = team1WorstToBest[:2]
        randomChoice1 = random.choice(randomPlayerTeam1)

        randomPlayerTeam2 = team2WorstToBest[2:]
        randomChoice2 = random.choice(randomPlayerTeam2)

        swapPlayersToDifferentTeam(randomChoice1, team1, randomChoice2, team2)
        print("Made a swap!")
        print("Total difference after making a swap is: ")
        print((team1.teamTotalQP - team2.teamTotalQP))

    # Case 4----------------------------------------------------------------------------------------

    return[team1,team2]

async def matchmake(interaction: discord.Interaction, playerList):
    """Matchmake players into balanced teams and send Discord embeds with results."""
    # Start by randomizing teams and calculating QP. Then, compare to absoluteMaximumDifference. If
    # diff is large, swap best and worst players. If diff is above threshold but not as large, swap random players. Continue
    # swapping until it either works, we need to start over with freshly randomized teams, or we reach a certain loop threshold.

    def format_team(team):
        return (
            f"**Top:** {team.topLaner.name} ({team.topLaner.tier})\n"
            f"**Jungle:** {team.jgLaner.name} ({team.jgLaner.tier})\n"
            f"**Mid:** {team.midLaner.name} ({team.midLaner.tier})\n"
            f"**ADC:** {team.adcLaner.name} ({team.adcLaner.tier})\n"
            f"**Support:** {team.supLaner.name} ({team.supLaner.tier})\n"
        )

    keepLooping = True
    totalOuterLoops = 0  
    while keepLooping == True:

        print("This is the total loopage")
        print(totalOuterLoops)
        totalOuterLoops += 1

        random.shuffle(playerList)

        team1 = []
        team2 = []

        for x in range(0, 10, 2):
            print("Adding this player to Team 1: " + str(playerList[x].name))
            team1.append(playerList[x])
            print("Adding this player to Team 2: " + str(playerList[x + 1].name))
            team2.append(playerList[x + 1])

        intermediateTeam1 = team(team1)
        intermediateTeam1.updateTeamQP()

        intermediateTeam2 = team(team2)
        intermediateTeam2.updateTeamQP()

        intermediateTeam1.reinstateIdealizedRoles()
        intermediateTeam2.reinstateIdealizedRoles()

        if totalOuterLoops > 20:

            warning_embed = discord.Embed(
            title="⚠️ Warning: Matchmaking Failed",
            description="Matchmaking couldn't create teams after multiple attempts.\n"
                        "These teams are simply randomized from the pool of potential players, and are likely unbalanced:",
            color=0xffcc00  # Yellow for warning
        )

            warning_embed.add_field(
                name="🔷 Team 1",
                value=format_team(intermediateTeam1),
                inline=False
            )
            warning_embed.add_field(
                name="🔴 Team 2",
                value=format_team(intermediateTeam2),
                inline=False
            )

            try:
                notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
                await notification_channel.send(embed=warning_embed)
                return [intermediateTeam1, intermediateTeam2]
            except Exception as e:
                print(f"Couldn't send to notification channel: {e}")

        else:

            needsOptimization = True
            numRuns = 0
            plausibleBackupTeam1 = []
            plausibleBackupTeam2 = []
            while needsOptimization == True:  # Attempt to more balance teams, part 1

                numRuns += 1

                optimizedTeams = await optimizeTeams(intermediateTeam1,intermediateTeam2)

                if abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) <= absoluteMaximumDifference or numRuns >= 7:

                    needsOptimization = False # Stop the loops
                    break

            if abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) < absoluteMaximumDifference and totalOuterLoops < 20:

                print(str(intermediateTeam1.teamTotalQP) + ' is team 1s points')
                print(str(intermediateTeam2.teamTotalQP) + ' is team 2s points')

            # Run final checks here (is a Grandmaster facing a gold, somehow?)

                masterListTeam1 = intermediateTeam1.playerList
                masterListTeam2 = intermediateTeam2.playerList

                intermediateTeam1.findListOfBestToWorstRoleAssignments()
                intermediateTeam2.findListOfBestToWorstRoleAssignments()

                team1Configurations = intermediateTeam1.listOfBestToWorstRoleAssignments
                team2Configurations = intermediateTeam2.listOfBestToWorstRoleAssignments

                plausibleTeamCombos = []
                plausibleTeamCombosRelaxedRestrictions = []

                # Step 1: Create "dummy" teams with all possible combinations of teams.
                # Step 2: Check for "plausibility" by checking each lane matchup within the teams.
                # Step 3: If the team is valid, add to list of plausible teams. 
                # Step 4: Find "best" team within all plausible teams. "Best" is defined as the lowest
                # sum of all role preference scores I.E. a lower score means more players got more preferred roles.

                # We have 4 separate matchup validity checks, in
                # order from most to least restrictive. Ideally, the most restrictive will create
                # a team first, but if not the others will kick in.

                for x in range(0, len(team1Configurations)): # Step 1

                    dummyTeam1 = createDummyTeam(masterListTeam1, team1Configurations[x])

                    for y in range(0, len(team2Configurations)):

                        dummyTeam2 = createDummyTeam(masterListTeam2, team2Configurations[y])

                        result1 = isPlayerMatchupValidMostRestrictive(dummyTeam1.playerList[0], dummyTeam2.playerList[0])
                        result2 = isPlayerMatchupValidMostRestrictive(dummyTeam1.playerList[1], dummyTeam2.playerList[1])
                        result3 = isPlayerMatchupValidMostRestrictive(dummyTeam1.playerList[2], dummyTeam2.playerList[2])
                        result4 = isPlayerMatchupValidMostRestrictive(dummyTeam1.playerList[3], dummyTeam2.playerList[3])
                        result5 = isPlayerMatchupValidMostRestrictive(dummyTeam1.playerList[4], dummyTeam2.playerList[4])
                        if result1 == True and result2 == True and result3 == True and result4 == True and result5 == True:
                            plausibleTeamCombos.append([team1Configurations[x], team2Configurations[y]])

                lowestScore = 1000

                for z in range(0, len(plausibleTeamCombos)): # Step 2

                    plausibleTeam1 = createDummyTeam(masterListTeam1, plausibleTeamCombos[z][0])
                    plausibleTeam2 = createDummyTeam(masterListTeam2, plausibleTeamCombos[z][1])

                    matchupScore = plausibleTeam1.topLaner.topPreference + plausibleTeam1.jgLaner.jgPreference + plausibleTeam1.midLaner.midPreference + plausibleTeam1.adcLaner.adcPreference + plausibleTeam1.supLaner.supPreference + plausibleTeam2.topLaner.topPreference + plausibleTeam2.jgLaner.jgPreference + plausibleTeam2.midLaner.midPreference + plausibleTeam2.adcLaner.adcPreference + plausibleTeam2.supLaner.supPreference
                    if matchupScore < lowestScore:

                        lowestScore = matchupScore
                        plausibleBackupTeam1.append(plausibleTeam1) # Step 3
                        plausibleBackupTeam2.append(plausibleTeam2)                       

                if len(plausibleBackupTeam1) != 0: # A valid team exists! Step 4

                    print('Teams reached level 0 relaxing')
                    lowestDiff = 1000
                    finalLowestMatchup = []
                    for x in range(len(plausibleBackupTeam1)):
                        differenceInSkill = abs(plausibleBackupTeam1[x].teamTotalQP - plausibleBackupTeam2[x].teamTotalQP)
                        if differenceInSkill < lowestDiff:
                            finalLowestMatchup = [plausibleBackupTeam1[x], plausibleBackupTeam2[x]]
                            lowestDiff = differenceInSkill

                    if finalLowestMatchup:
                        success_embed = discord.Embed(
                            title="✅ Balanced Teams Created",
                            description="Matchmaking created balanced teams successfully!",
                            color=0x00ff00  # Green for success
                        )

                        success_embed.add_field(
                            name="🔷 Team 1",
                            value=format_team(finalLowestMatchup[0]),
                            inline=False
                        )
                        success_embed.add_field(
                            name="🔴 Team 2",
                            value=format_team(finalLowestMatchup[1]),
                            inline=False
                        )

                        try:
                            notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))  # Ensure the correct channel is used
                            if notification_channel:
                                await notification_channel.send("A team has been created!")
                                await notification_channel.send(embed=success_embed)
                                return[finalLowestMatchup[0],finalLowestMatchup[1]]
                        except Exception as e:
                            print(f"Couldn't send to notification channel: {e}")                       

                else: # A valid team does not exist, relax restrictions a bit.

                    print('Teams reached level 1 relaxing')
                    for x in range(0, len(team1Configurations)):

                        dummyTeam1 = createDummyTeam(masterListTeam1, team1Configurations[x])

                        for y in range(0, len(team2Configurations)):

                            dummyTeam2 = createDummyTeam(masterListTeam2, team2Configurations[y])

                            result1 = isPlayerMatchupValidMediumRestrictive(dummyTeam1.playerList[0], dummyTeam2.playerList[0])
                            result2 = isPlayerMatchupValidMediumRestrictive(dummyTeam1.playerList[1], dummyTeam2.playerList[1])
                            result3 = isPlayerMatchupValidMediumRestrictive(dummyTeam1.playerList[2], dummyTeam2.playerList[2])
                            result4 = isPlayerMatchupValidMediumRestrictive(dummyTeam1.playerList[3], dummyTeam2.playerList[3])
                            result5 = isPlayerMatchupValidMediumRestrictive(dummyTeam1.playerList[4], dummyTeam2.playerList[4])
                            if result1 == True and result2 == True and result3 == True and result4 == True and result5 == True:
                                plausibleTeamCombos.append([team1Configurations[x], team2Configurations[y]])

                    lowestScore = 1000

                    for z in range(0, len(plausibleTeamCombos)):

                        plausibleTeam1 = createDummyTeam(masterListTeam1, plausibleTeamCombos[z][0])
                        plausibleTeam2 = createDummyTeam(masterListTeam2, plausibleTeamCombos[z][1])

                        matchupScore = plausibleTeam1.topLaner.topPreference + plausibleTeam1.jgLaner.jgPreference + plausibleTeam1.midLaner.midPreference + plausibleTeam1.adcLaner.adcPreference + plausibleTeam1.supLaner.supPreference + plausibleTeam2.topLaner.topPreference + plausibleTeam2.jgLaner.jgPreference + plausibleTeam2.midLaner.midPreference + plausibleTeam2.adcLaner.adcPreference + plausibleTeam2.supLaner.supPreference
                        if matchupScore < lowestScore:

                            lowestScore = matchupScore
                            plausibleBackupTeam1.append(plausibleTeam1)
                            plausibleBackupTeam2.append(plausibleTeam2)

                    if len(plausibleBackupTeam1) != 0: # A valid team exists!

                        lowestDiff = 1000
                        finalLowestMatchup = []
                        for x in range(len(plausibleBackupTeam1)):
                            differenceInSkill = abs(plausibleBackupTeam1[x].teamTotalQP - plausibleBackupTeam2[x].teamTotalQP)
                            if differenceInSkill < lowestDiff:
                                finalLowestMatchup = [plausibleBackupTeam1[x], plausibleBackupTeam2[x]]
                                lowestDiff = differenceInSkill

                        if finalLowestMatchup:
                            success_embed = discord.Embed(
                            title="✅ Balanced Teams Created",
                            description="Matchmaking created balanced teams successfully!",
                            color=0x00ff00  # Green for success
                        )

                            success_embed.add_field(
                            name="🔷 Team 1",
                            value=format_team(finalLowestMatchup[0]),
                            inline=False
                        )
                            success_embed.add_field(
                            name="🔴 Team 2",
                            value=format_team(finalLowestMatchup[1]),
                            inline=False
                        )

                            try:
                                notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))  # Ensure the correct channel is used
                                if notification_channel:
                                    await notification_channel.send(embed=success_embed)
                                    return[finalLowestMatchup[0],finalLowestMatchup[1]]
                            except Exception as e:
                                print(f"Couldn't send to notification channel: {e}")

                    else: # A valid team still doesn't exist, relax restrictions again.

                        print('Teams reached level 2 relaxing')
                        for x in range(0, len(team1Configurations)):

                            dummyTeam1 = createDummyTeam(masterListTeam1, team1Configurations[x])

                            for y in range(0, len(team2Configurations)):

                                dummyTeam2 = createDummyTeam(masterListTeam2, team2Configurations[y])

                                result1 = isPlayerMatchupValidLowRestrictive(dummyTeam1.playerList[0], dummyTeam2.playerList[0])
                                result2 = isPlayerMatchupValidLowRestrictive(dummyTeam1.playerList[1], dummyTeam2.playerList[1])
                                result3 = isPlayerMatchupValidLowRestrictive(dummyTeam1.playerList[2], dummyTeam2.playerList[2])
                                result4 = isPlayerMatchupValidLowRestrictive(dummyTeam1.playerList[3], dummyTeam2.playerList[3])
                                result5 = isPlayerMatchupValidLowRestrictive(dummyTeam1.playerList[4], dummyTeam2.playerList[4])
                                if result1 == True and result2 == True and result3 == True and result4 == True and result5 == True:
                                    plausibleTeamCombos.append([team1Configurations[x], team2Configurations[y]])

                        lowestScore = 1000

                        for z in range(0, len(plausibleTeamCombos)):

                            plausibleTeam1 = createDummyTeam(masterListTeam1, plausibleTeamCombos[z][0])
                            plausibleTeam2 = createDummyTeam(masterListTeam2, plausibleTeamCombos[z][1])

                            matchupScore = plausibleTeam1.topLaner.topPreference + plausibleTeam1.jgLaner.jgPreference + plausibleTeam1.midLaner.midPreference + plausibleTeam1.adcLaner.adcPreference + plausibleTeam1.supLaner.supPreference + plausibleTeam2.topLaner.topPreference + plausibleTeam2.jgLaner.jgPreference + plausibleTeam2.midLaner.midPreference + plausibleTeam2.adcLaner.adcPreference + plausibleTeam2.supLaner.supPreference
                            if matchupScore < lowestScore:

                                lowestScore = matchupScore
                                plausibleBackupTeam1.append(plausibleTeam1)
                                plausibleBackupTeam2.append(plausibleTeam2)

                        if len(plausibleBackupTeam1) != 0: # A valid team exists!

                            lowestDiff = 1000
                            finalLowestMatchup = []
                            for x in range(len(plausibleBackupTeam1)):
                                differenceInSkill = abs(plausibleBackupTeam1[x].teamTotalQP - plausibleBackupTeam2[x].teamTotalQP)
                                if differenceInSkill < lowestDiff:
                                    finalLowestMatchup = [plausibleBackupTeam1[x], plausibleBackupTeam2[x]]
                                    lowestDiff = differenceInSkill

                            if finalLowestMatchup:
                                success_embed = discord.Embed(
                                title="✅ Balanced Teams Created",
                                description="Matchmaking created balanced teams successfully!",
                                color=0x00ff00  # Green for success
                            )

                                success_embed.add_field(
                                name="🔷 Team 1",
                                value=format_team(finalLowestMatchup[0]),
                                inline=False
                            )
                                success_embed.add_field(
                                name="🔴 Team 2",
                                value=format_team(finalLowestMatchup[1]),
                                inline=False
                            )

                                try:
                                    notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))  # Ensure the correct channel is used
                                    if notification_channel:
                                        await notification_channel.send(embed=success_embed)
                                        return[finalLowestMatchup[0],finalLowestMatchup[1]]
                                except Exception as e:
                                    print(f"Couldn't send to notification channel: {e}")

                        else: # Still invalid, relax restrictions one final time.

                            print('Teams reached level 3 relaxing (final)')
                            for x in range(0, len(team1Configurations)):

                                dummyTeam1 = createDummyTeam(masterListTeam1, team1Configurations[x])

                                for y in range(0, len(team2Configurations)):

                                    dummyTeam2 = createDummyTeam(masterListTeam2, team2Configurations[y])

                                    result1 = isPlayerMatchupValidLowRestrictive(dummyTeam1.playerList[0], dummyTeam2.playerList[0])
                                    result2 = isPlayerMatchupValidLowRestrictive(dummyTeam1.playerList[1], dummyTeam2.playerList[1])
                                    result3 = isPlayerMatchupValidLowRestrictive(dummyTeam1.playerList[2], dummyTeam2.playerList[2])
                                    result4 = isPlayerMatchupValidLowRestrictive(dummyTeam1.playerList[3], dummyTeam2.playerList[3])
                                    result5 = isPlayerMatchupValidLowRestrictive(dummyTeam1.playerList[4], dummyTeam2.playerList[4])
                                    if result1 == True and result2 == True and result3 == True and result4 == True and result5 == True:
                                        plausibleTeamCombos.append([team1Configurations[x], team2Configurations[y]])

                            lowestScore = 1000

                            for z in range(0, len(plausibleTeamCombos)):

                                plausibleTeam1 = createDummyTeam(masterListTeam1, plausibleTeamCombos[z][0])
                                plausibleTeam2 = createDummyTeam(masterListTeam2, plausibleTeamCombos[z][1])

                                matchupScore = plausibleTeam1.topLaner.topPreference + plausibleTeam1.jgLaner.jgPreference + plausibleTeam1.midLaner.midPreference + plausibleTeam1.adcLaner.adcPreference + plausibleTeam1.supLaner.supPreference + plausibleTeam2.topLaner.topPreference + plausibleTeam2.jgLaner.jgPreference + plausibleTeam2.midLaner.midPreference + plausibleTeam2.adcLaner.adcPreference + plausibleTeam2.supLaner.supPreference
                                if matchupScore < lowestScore:

                                    lowestScore = matchupScore
                                    plausibleBackupTeam1.append(plausibleTeam1)
                                    plausibleBackupTeam2.append(plausibleTeam2)

                            if len(plausibleBackupTeam1) != 0: # A valid team exists!

                                lowestDiff = 1000
                                finalLowestMatchup = []
                                for x in range(len(plausibleBackupTeam1)):
                                    differenceInSkill = abs(plausibleBackupTeam1[x].teamTotalQP - plausibleBackupTeam2[x].teamTotalQP)
                                    if differenceInSkill < lowestDiff:
                                        finalLowestMatchup = [plausibleBackupTeam1[x], plausibleBackupTeam2[x]]
                                        lowestDiff = differenceInSkill

                                if finalLowestMatchup:
                                    success_embed = discord.Embed(
                                    title="✅ Balanced Teams Created",
                                    description="Matchmaking created balanced teams successfully!",
                                    color=0x00ff00  # Green for success
                                )

                                    success_embed.add_field(
                                    name="🔷 Team 1",
                                    value=format_team(finalLowestMatchup[0]),
                                    inline=False
                                )
                                    success_embed.add_field(
                                    name="🔴 Team 2",
                                    value=format_team(finalLowestMatchup[1]),
                                    inline=False
                                )

                                    try:
                                        notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))  # Ensure the correct channel is used
                                        if notification_channel:
                                            await notification_channel.send(embed=success_embed)
                                            return[finalLowestMatchup[0],finalLowestMatchup[1]]
                                    except Exception as e:
                                        print(f"Couldn't send to notification channel: {e}")

                            else: # Nothing has been valid. Either try again or return randomized teams.

                                print('We must loop again, sadly.')
                                if totalOuterLoops > 20:

                                    print(
                            "We have tried many times, but no valid team has been created. A backup pair of teams has been presented.")                          

                                    warning_embed = discord.Embed(
                                        title="⚠️ Warning: Potentially Imbalanced Teams",
                                        description="Matchmaking couldn't create perfectly balanced teams after multiple attempts.\n"
                                                    "These teams may be imbalanced - please review:",
                                        color=0xffcc00  # Yellow for warning
                                    )

                                    warning_embed.add_field(
                                        name="🔷 Team 1",
                                        value=format_team(intermediateTeam1),
                                        inline=False
                                    )
                                    warning_embed.add_field(
                                        name="🔴 Team 2",
                                        value=format_team(intermediateTeam2),
                                        inline=False
                                    )

                                    try:
                                        notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
                                        await notification_channel.send(embed=warning_embed)
                                        return [intermediateTeam1, intermediateTeam2]
                                    except Exception as e:
                                        print(f"Couldn't send to notification channel: {e}")  

                                else:

                                    continue
                                               
class Tournament:

    def __init__(self):

        previousTourneyID = tourneyDB.col_values(1)[-1]
        currentTourneyID = ""

        if previousTourneyID.isnumeric() == True:

            currentTourneyID = int(previousTourneyID) + 1

        else:

            currentTourneyID = 1

        # Write to tournament database
        DBFormula = tourneyDB.get("B2", value_render_option=ValueRenderOption.formula)
        tourneyDB.update_acell('A' + str(currentTourneyID + 1), str(currentTourneyID))
        tourneyDB.update_acell('B' + str(currentTourneyID + 1),
                               '=COUNTIF(GameDatabase!B:B,"="&A' + str(currentTourneyID + 1) + ')')


# Check-in button class for checking in to tournaments.
class CheckinButtons(discord.ui.View):
    # timeout after 900 seconds = end of 15-minute check-in period
    def __init__(self, *, timeout=900):
        super().__init__(timeout=timeout)

    """
    This button is a green button that is called check in
    When this button is pulled up, it will show the text "Check-In"

    The following output when clicking the button is to be expected:
    If the user already has the player role, it means that they are already checked in.
    If the user doesn't have the player role, it will give them the player role. 
    """

    @discord.ui.button(
        label="Check-In",
        style=discord.ButtonStyle.green)
    async def checkin(self, interaction: discord.Interaction, button: discord.ui.Button):

        player = get(interaction.guild.roles, name='Player')
        member = interaction.user

        if player in member.roles:
            await interaction.response.edit_message(view=self)
            await interaction.followup.send('You have already checked in.', ephemeral=True)
            return "Is already checked in"
        await member.add_roles(player)
        await interaction.response.edit_message(view=self)
        await interaction.followup.send('You have checked in!', ephemeral=True)
        return "Checked in"

    """
    This button is the leave button. It is used for if the player checked in but has to leave
    The following output is to be expected:

    If the user has the player role, it will remove it and tell the player that it has been removed
    If the user does not have the player role, it will tell them to check in first.
    """

    @discord.ui.button(
        label="Leave",
        style=discord.ButtonStyle.red,
        custom_id='experimentingHere')
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):

        player = get(interaction.guild.roles, name='Player')
        member = interaction.user

        if player in member.roles:
            await member.remove_roles(player)
            await interaction.response.edit_message(view=self)
            await interaction.followup.send('Sorry to see you go.', ephemeral=True)
            return "Role Removed"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send('You have not checked in. Please checkin first', ephemeral=True)
        return "Did not check in yet"


class volunteerButtons(discord.ui.View):
    # timeout after 900 seconds = end of 15-minute volunteer period
    def __init__(self, *, timeout=900):
        super().__init__(timeout=timeout)

    """
    This button is a green button that is called check in
    When this button is pulled up, it will show the text "Volunteer"

    The following output when clicking the button is to be expected:
    If the user already has the volunteer role, it means that they are already volunteered.
    If the user doesn't have the volunteer role, it will give them the volunteer role. 
    """

    """
    This button is the leave button. It is used for if the player who has volunteer wants to rejoin
    The following output is to be expected:

    If the user has the player role, it will remove it and tell the player that it has been removed
    If the user does not have the volunteer role, it will tell them to volunteer first.
    """


@tree.command(
    name="rejoin",
    description="Rejoin the tournament after volunteering to sit out",
    guild=discord.Object(GUILD)
)
async def rejoin(interaction: discord.Interaction):
    member = interaction.user
    player_role = discord.utils.get(interaction.guild.roles, name='Player')
    volunteer_role = discord.utils.get(interaction.guild.roles, name='Volunteer')

    # Check if user is actually a volunteer
    if volunteer_role not in member.roles:
        await interaction.response.send_message(
            "❌ You're not currently volunteering to sit out!",
            ephemeral=True
        )
        return

    try:
        # Remove Volunteer role and add Player role
        await member.remove_roles(volunteer_role)
        await member.add_roles(player_role)

        await interaction.response.send_message(
            "✅ You've rejoined the tournament and may be selected for matches!",
            ephemeral=True
        )

        # Send notification to admin channel
        notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
        if notification_channel:
            await notification_channel.send(
                f"🎉 {member.mention} has rejoined the tournament after sitting out!"
            )

    except Exception as e:
        print(f"Error in rejoin command: {e}")
        await interaction.response.send_message(
            "❌ An error occurred while processing your request. Please try again.",
            ephemeral=True
        )

class winnerButtons(discord.ui.View):
    # timeout after 900 seconds = end of 15-minute volunteer period
    def __init__(self, *, timeout=900):
        super().__init__(timeout=timeout)

    winnerVariable = "None Entered"

    @discord.ui.button(
        label="Blue Team",
        style=discord.ButtonStyle.blurple)
    async def winnerBlue(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        await interaction.response.edit_message(view=self)
        await interaction.followup.send('You have selected the Blue team as the winner!', ephemeral=True)
        winnerVariable = "Blue"
        return "Blue"

    @discord.ui.button(
        label="Red Team",
        style=discord.ButtonStyle.red)
    async def winnerRed(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        await interaction.response.edit_message(view=self)
        await interaction.followup.send('You have selected the Red team as the winner!', ephemeral=True)
        winnerVariable = "Red"
        return "Red"

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.grey)
    async def commitToDB(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        await interaction.response.edit_message(view=self)
        await interaction.followup.send('Committing to DB', ephemeral=True)

#Command to start check-in
# Fetch existing Discord IDs from Google Sheets
def fetch_existing_discord_ids():
    try:
        existing_records = playerDB.get_all_records()
        discord_ids = {str(record["Discord ID"]) for record in existing_records}
        return discord_ids
    except Exception as e:
        print(f"Error fetching existing Discord IDs: {e}")
        return set()


existing_discord_ids = fetch_existing_discord_ids()

@tree.command(
    name='start_tournament',
    description='Initiate tournament creation',
    guild=discord.Object(GUILD))
async def startTourney(interaction: discord.Interaction):
    player = interaction.user
    checkinStart = time.time()
    checkinFinish = time.time() + CHECKIN_TIME
    totalMinutes = round(round(CHECKIN_TIME) // 60)
    totalSeconds = round(round(CHECKIN_TIME) % 60)

    # Simple message without role selection
    await interaction.response.send_message(
        f'A new tournament has been started by {player.mention}!\n'
        f'Check-in started at <t:{round(checkinStart)}:T>\n\n'
        'Use `/checkin` to participate!\n'
        'Use `/rolepreference` to set your role preferences.'
    )

    # Send notification to admin channel
    notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
    if notification_channel:
        await notification_channel.send(
            f"🏆 Tournament started by {player.mention}! Check-in open for {totalMinutes} minutes."
        )

    newTournament = Tournament()


@tree.command(
    name='checkin',
    description='Check in for tournament participation',
    guild=discord.Object(GUILD)
)
async def checkin(interaction: discord.Interaction):
    member = interaction.user

    # Check if user is already checked in
    player_role = discord.utils.get(interaction.guild.roles, name='Player')
    if player_role in member.roles:
        await interaction.response.send_message("❌ You're already checked in!", ephemeral=True)
        return

    # Check if user has linked their account
    friendly_discord_id = await get_friendly_discord_id(member.id, interaction.guild)
    existing_records = playerDB.get_all_records()
    is_linked = any(record.get("Discord ID") == friendly_discord_id for record in existing_records)

    if not is_linked:
        await interaction.response.send_message(
            "❌ You must link your Riot ID with `/link` before checking in!",
            ephemeral=True
        )
        return

    # Add Player role
    try:
        await member.add_roles(player_role)
        await interaction.response.send_message(
            "✅ You've successfully checked in for the tournament!",
            ephemeral=True
        )

        # Send notification to admin channel
        notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
        if notification_channel:
            await notification_channel.send(
                f"🎟️ {member.mention} has checked in for the tournament!"
            )

    except Exception as e:
        print(f"Error during check-in: {e}")
        await interaction.response.send_message(
            "❌ An error occurred during check-in. Please try again.",
            ephemeral=True
        )


# Command to start check for volunteers to sit out of a match.
@tree.command(
    name='sitout',
    description='Initiate check for volunteers to sit out from a match',
    guild=discord.Object(GUILD))
async def sitout(interaction: discord.Interaction):
    player = interaction.user

    # Upon volunteering to sit out for a round, update the player's Discord username in the database if it has been
    # changed. This may be redundant if users are eventually restricted from volunteering before they've checked in.
    # await update_username(player)

    view = volunteerButtons()
    await interaction.response.send_message(
        'The Volunteer check has started! You have 15 minutes to volunteer if you wish to sit out.', view=view)


@tree.command(
    name='create_game',
    description='Create a lobby of 10 players after enough have checked in',
    guild=discord.Object(GUILD))
async def create_game(interaction: discord.Interaction):

    def format_team(team, team_name):
            return (
                f"**{team_name}**\n"
                f"Top: {team.topLaner.name}\n"
                f"Jungle: {team.jgLaner.name}\n"
                f"Mid: {team.midLaner.name}\n"
                f"ADC: {team.adcLaner.name}\n"
                f"Support: {team.supLaner.name}"
            )


    try:
        await interaction.response.defer()

        # Get and validate players

        playerDataImport = playerDB.get_all_records()
        checked_in_players = [p for p in playerDataImport if p.get("Checked In", "").lower() == "yes"]

        if len(checked_in_players) < 10:
            await interaction.followup.send(
                f"❌ Not enough players checked in ({len(checked_in_players)}/10). Cannot create game.",
                ephemeral=True
            )
            return

        else: # Create 1 or more lobbies
            
            totalNeededLobbies = len(checked_in_players)//10 # Integer division, divides into fully fillable lobbies
            # Prepare player data
            players = []
            for player in checked_in_players:
                players.append(player.get("Players1", "UNKNOWN"))
                players.append(player.get("Rank Tier", "1"))
                players.append(player.get("Role 1 (Top)"))
                players.append(player.get("Role 2 (Jungle)"))
                players.append(player.get("Role 3 (Mid)"))
                players.append(player.get("Role 4 (ADC)"))
                players.append(player.get("Role 5 (Support)"))
                
            intermediateList = formatList(players) # Now we have a list of participant objects.
            random.shuffle(intermediateList)
           
            # If we only need 1 lobby, we can just leave it randomized for more variety.
            if totalNeededLobbies == 1:
                
                finalList = [players]

            else: # If we need more than one lobby, we should sort players, so that higher tier players play against each other

                sortedPlayers = (sorted(intermediateList, key=lambda x: x.tier))

                finalList = []
                num_players = len(sortedPlayers)
    
                base_size = num_players // totalNeededLobbies
    
                remainder = num_players % totalNeededLobbies
    
                start_index = 0
    
                for i in range(totalNeededLobbies):

                    # Each lobby will have at least `base_size` players
                    # If there are extra players (from the remainder),
                    # give one more player to the first 'remainder' lobbies

                    if i < remainder:
                        end_index = start_index + base_size + 1
                    else:
                        end_index = start_index + base_size
        
                    lobby = sortedPlayers[start_index:end_index]
                    finalList.append(lobby)
        
                    # Step 4.3: Update the starting index of the list for the next lobby
                    start_index = end_index

            # Run matchmaking
            for x in range(0,totalNeededLobbies):  

                matchmakingList = finalList[x]
                bothTeams = await matchmake(interaction, matchmakingList)

                try:
                    save_teams_to_sheet(bothTeams)
                    print("Team successfully saved to database.")
                except Exception as e:
                    print(f"Error saving team: {e}")

                # Confirm success
                await interaction.followup.send("✅ Game created and saved to database successfully!")

                # Increment participation for all players in the game
                try:
                    # Get all player names from both teams
                    all_players = []
                    for team in [bothTeams[0], bothTeams[1]]:
                        all_players.extend([
                            team.topLaner.name,
                            team.jgLaner.name,
                            team.midLaner.name,
                            team.adcLaner.name,
                            team.supLaner.name
                        ])

                    # Update participation for each player
                    existing_records = playerDB.get_all_records()
                    for player_name in all_players:
                        for i, record in enumerate(existing_records, start=2):  # Start from row 2
                            if record.get("Players1") == player_name:
                                # Get current values
                                current_tier_participation = int(record.get("Participation (Current Tier)", 0))
                                total_participation = int(record.get("Participation (Total)", 0))

                                # Update both participation columns
                                playerDB.update_cell(i, 9,
                                                     current_tier_participation + 1)  # Column 9: Participation (Current Tier)
                                playerDB.update_cell(i, 10, total_participation + 1)  # Column 10: Participation (Total)

                                # Also update Games Played columns (columns 15 and 16)
                                current_tier_games = int(record.get("Games Played (current tier)", 0))
                                total_games = int(record.get("Games Played (Total)", 0))
                                playerDB.update_cell(i, 15, current_tier_games + 1)  # Column 15: Games Played (current tier)
                                playerDB.update_cell(i, 16, total_games + 1)  # Column 16: Games Played (Total)

                                # Update win rate (column 11 and 12) if needed
                                wins_current = int(record.get("Wins (Current Tier)", 0))
                                new_current_games = current_tier_games + 1
                                current_win_rate = wins_current / new_current_games if new_current_games > 0 else 0
                                playerDB.update_cell(i, 11, current_win_rate)  # Column 11: WR %

                                wins_total = int(record.get("Wins (Total)", 0))
                                new_total_games = total_games + 1
                                win_rate = wins_total / new_total_games if new_total_games > 0 else 0
                                playerDB.update_cell(i, 11, win_rate)  # Column 11: WR %

                                break

                    print("Updated participation and games played for all players in the game.")
                except Exception as e:
                    print(f"Error updating participation: {e}")
                         

    except Exception as e:
        print(f"Error in create_game: {e}")
        await interaction.followup.send(
            "An error occurred while creating the game. Check console for details.",
            ephemeral=True
        )

@tree.command(
    name="swap",
    description="Swap two players between teams (Admin only).",
    guild=discord.Object(GUILD)
)
@commands.has_permissions(administrator=True)
async def swap(interaction: discord.Interaction, player1: str, player2: str):
    global current_teams
    try:
        # Check if teams exist
        if not current_teams.get("team1") or not current_teams.get("team2"):
            await interaction.response.send_message("❌ No teams found. Make sure matchmaking has run first.",
                                                    ephemeral=True)
            return

        team1 = current_teams["team1"]
        team2 = current_teams["team2"]

        # Find the players in the teams
        player1_found = None
        player2_found = None
        player1_team = None
        player2_team = None

        # Search both teams for the players
        for player in team1.playerList:
            if player.name == player1:
                player1_found = player
                player1_team = team1
            elif player.name == player2:
                player2_found = player
                player2_team = team1

        for player in team2.playerList:
            if player.name == player1:
                player1_found = player
                player1_team = team2
            elif player.name == player2:
                player2_found = player
                player2_team = team2

        # If one or both players are not found, send an error message
        if not player1_found or not player2_found:
            await interaction.response.send_message("❌ One or both players were not found in the teams.",
                                                    ephemeral=True)
            return

        # Perform the swap
        if player1_team == team1 and player2_team == team2:
            team1.playerList.remove(player1_found)
            team2.playerList.remove(player2_found)
            team1.playerList.append(player2_found)
            team2.playerList.append(player1_found)
        elif player1_team == team2 and player2_team == team1:
            team2.playerList.remove(player1_found)
            team1.playerList.remove(player2_found)
            team2.playerList.append(player2_found)
            team1.playerList.append(player1_found)
        else:
            # If players are on the same team, swap their roles instead
            swapPlayerRolesSameTeam(player1_team, player1_found, player2_found)

        # Update team QP
        team1.updateTeamQP()
        team2.updateTeamQP()

        # Update the global teams
        current_teams["team1"] = team1
        current_teams["team2"] = team2

        # Get current game ID from GameDatabase
        latest_game_id = gameDB.col_values(1)[-1]
        if not latest_game_id.isnumeric():
            await interaction.response.send_message("❌ Could not determine current game ID.", ephemeral=True)
            return
        game_row = int(latest_game_id) + 1  # +1 because row 1 is headers

        # Update GameDatabase
        gameDB.batch_update([{
            'range': f'E{game_row}:N{game_row}',
            'values': [[
                team1.topLaner.name, team1.jgLaner.name, team1.midLaner.name,
                team1.adcLaner.name, team1.supLaner.name,
                team2.topLaner.name, team2.jgLaner.name, team2.midLaner.name,
                team2.adcLaner.name, team2.supLaner.name
            ]]
        }])

        # Format updated team info to match desired output
        team1_info = (
            f"**\n"
            f"Top: {team1.topLaner.name}\n"
            f"Jungle: {team1.jgLaner.name}\n"
            f"Mid: {team1.midLaner.name}\n"
            f"ADC: {team1.adcLaner.name}\n"
            f"Support: {team1.supLaner.name}"
        )
        team2_info = (
            f"**\n"
            f"Top: {team2.topLaner.name}\n"
            f"Jungle: {team2.jgLaner.name}\n"
            f"Mid: {team2.midLaner.name}\n"
            f"ADC: {team2.adcLaner.name}\n"
            f"Support: {team2.supLaner.name}"
        )

        # Create embed with updated teams
        embed = discord.Embed(
            title="Game Lobby Created",
            description=f"Swapped **{player1}** and **{player2}** between teams!",
            color=0x00ff00
        )
        embed.add_field(name="Team 1", value=team1_info, inline=False)
        embed.add_field(name="Team 2", value=team2_info, inline=False)

        # Send to notification channel
        notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
        await notification_channel.send(embed=embed)

        # Send to the current channel (where command was executed) using followup
        await interaction.response.send_message(embed=embed)
        await interaction.followup.send(
            f"✅ Swapped **{player1}** and **{player2}** between teams!",
            ephemeral=False
        )

    except Exception as e:
        print(f"Error swapping players: {e}")
        await interaction.response.send_message(f"❌ Error swapping players: {e}", ephemeral=True)


@tree.command(
    name="toxicity",
    description="Add a toxicity point to a player (Admin only).",
    guild=discord.Object(GUILD)
)
@commands.has_permissions(administrator=True)
async def toxicity(interaction: discord.Interaction, player_name: str):
    try:
        # Fetch existing records from the Google Sheet
        existing_records = playerDB.get_all_records()

        # Find the player in the database by name
        player_found = None
        row_index = None
        for i, record in enumerate(existing_records, start=2):  # Start from row 2 (row 1 is headers)
            if record["Players1"] == player_name:  # Assuming "Players1" is the column for player names
                player_found = record
                row_index = i
                break

        if not player_found:
            await interaction.response.send_message(f"❌ Player '{player_name}' not found in the database.",
                                                    ephemeral=True)
            return

        # Increment the toxicity points
        current_toxicity = int(player_found.get("Toxicity", 0))  # Assuming "Toxicity" is the column for toxicity points
        new_toxicity = current_toxicity + 1

        # Update the toxicity points in the Google Sheet
        playerDB.update_cell(row_index, 16, new_toxicity)  # Assuming column 16 is for toxicity points

        await interaction.response.send_message(
            f"✅ Added 1 toxicity point to {player_name}. Their total toxicity points are now {new_toxicity}.",
            ephemeral=True
        )

    except Exception as e:
        print(f"An error occurred: {e}")
        await interaction.response.send_message(
            "An unexpected error occurred while adding toxicity points.",
            ephemeral=True
        )


@tree.command(
    name="remove_toxicity",
    description="Remove a toxicity point from a player (Admin only).",
    guild=discord.Object(GUILD)
)
@commands.has_permissions(administrator=True)
async def remove_toxicity(interaction: discord.Interaction, player_name: str):
    try:
        # Fetch existing records from the Google Sheet
        existing_records = playerDB.get_all_records()

        # Find the player in the database by name
        player_found = None
        row_index = None
        for i, record in enumerate(existing_records, start=2):  # Start from row 2 (row 1 is headers)
            if record["Players1"] == player_name:  # Assuming "Players1" is the column for player names
                player_found = record
                row_index = i
                break

        if not player_found:
            await interaction.response.send_message(f"❌ Player '{player_name}' not found in the database.",
                                                    ephemeral=True)
            return

        # Decrement the toxicity points (ensure it doesn't go below 0)
        current_toxicity = int(player_found.get("Toxicity", 0))  # Assuming "Toxicity" is the column for toxicity points
        new_toxicity = max(0, current_toxicity - 1)  # Ensure toxicity points don't go below 0

        # Update the toxicity points in the Google Sheet
        playerDB.update_cell(row_index, 16, new_toxicity)  # Assuming column 16 is for toxicity points

        await interaction.response.send_message(
            f"✅ Removed 1 toxicity point from {player_name}. Their total toxicity points are now {new_toxicity}.",
            ephemeral=True
        )

    except Exception as e:
        print(f"An error occurred: {e}")
        await interaction.response.send_message(
            "An unexpected error occurred while removing toxicity points.",
            ephemeral=True
        )


@tree.command(
    name="view_toxicity",
    description="View a player's toxicity points.",
    guild=discord.Object(GUILD)
)
async def view_toxicity(interaction: discord.Interaction, player_name: str):
    try:
        # Fetch existing records from the Google Sheet
        existing_records = playerDB.get_all_records()

        # Find the player in the database by name
        player_found = None
        for record in existing_records:
            if record["Players1"] == player_name:  # Assuming "Players1" is the column for player names
                player_found = record
                break

        if not player_found:
            await interaction.response.send_message(f"❌ Player '{player_name}' not found in the database.",
                                                    ephemeral=True)
            return

        # Get the player's toxicity points
        toxicity_points = int(player_found.get("Toxicity", 0))  # Assuming "Toxicity" is the column for toxicity points

        await interaction.response.send_message(
            f"🔍 {player_name} has {toxicity_points} toxicity points.",
            ephemeral=True
        )

    except Exception as e:
        print(f"An error occurred: {e}")
        await interaction.response.send_message(
            "An unexpected error occurred while fetching toxicity points.",
            ephemeral=True
        )

@tree.command(
    name="uncheckin",
    description="Remove yourself from the tournament",
    guild=discord.Object(GUILD)
)
async def uncheckin(interaction: discord.Interaction):
    member = interaction.user
    player_role = discord.utils.get(interaction.guild.roles, name='Player')

    if player_role not in member.roles:
        await interaction.response.send_message(
            "❌ You're not currently checked in!",
            ephemeral=True
        )
        return

    try:
        # Remove Player role
        await member.remove_roles(player_role)

        await interaction.response.send_message(
            "✅ You've been removed from the tournament. Use `/checkin` to rejoin.",
            ephemeral=True
        )

        # Send notification to admin channel
        notification_channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
        if notification_channel:
            await notification_channel.send(
                f"❌ {member.mention} has un-checked from the tournament."
            )

    except Exception as e:
        print(f"Error in uncheckin command: {e}")
        await interaction.response.send_message(
            "❌ Failed to uncheckin. Please try again or contact an admin.",
            ephemeral=True
        )


@tree.command(
    name="show_teams",
    description="Show current teams")
async def show_teams(interaction: discord.Interaction):
    if current_teams["team1"] is None:
        await interaction.response.send_message("No teams created yet!", ephemeral=True)
        return

    embed = discord.Embed(title="Current Teams")
    # Add team info to embed
    await interaction.response.send_message(embed=embed)

async def help_command(interaction: discord.Interaction):
    pages = [
        discord.Embed(
            title="Help Menu 📚",
            color=0xffc629
        ).add_field(
            name="/help",
            value="Displays documentation on all bot commands.",
            inline=False
        ).add_field(
            name="/link [riot_id]",
            value="Link your Riot ID to your Discord account. Users are required to type this command before any others except /help.",
            inline=False
        ).add_field(
            name="/rolepreference",
            value="Set your role preferences for matchmaking.",
            inline=False
        ),
        discord.Embed(
            title="Help Menu 📚",
            color=0xffc629
        ).add_field(
            name="/checkin",
            value="Initiate tournament check-in.",
            inline=False
        ).add_field(
            name="/sitout",
            value="Volunteer to sit out of the current match..",
            inline=False
        ),
        discord.Embed(
            title="Help Menu 📚",
            description="**/win [match_number] [lobby_number] [team]** - Add a win for the specified players.",
            color=0xffc629
        ),
        discord.Embed(
            title="Help Menu 📚",
            description="**/toxicity [discord_username]** - Give a user a point of toxicity.",
            color=0xffc629
        ),
        discord.Embed(
            title="Help Menu 📚",
            description="**/clear** - Remove all users from Player and Volunteer roles.",
            color=0xffc629
        ),
        discord.Embed(
            title="Help Menu 📚",
            description="**/players** - Find all players and volunteers currently enrolled in the game.",
            color=0xffc629
        ),
        discord.Embed(
            title="Help Menu 📚",
            description="**/points** - Update participation points in the spreadsheet.",
            color=0xffc629
        ),
        discord.Embed(
            title="Help Menu 📚",
            description="**/matchmake [match_number]** - Form teams for all players enrolled in the game.",
            color=0xffc629
        ),
        discord.Embed(
            title="Help Menu 📚",
            description="**/votemvp [username]** - Vote for the MVP of your match.",
            color=0xffc629
        ),
        discord.Embed(
            title="/uncheckin",
            description="Remove yourself from the tournament",
            color=0xffc629
        ),
        discord.Embed(
            title="/volunteer",
            description="Volunteer to sit out of the next match",
            color=0xffc629
        ),
        discord.Embed(
            title="/rejoin",
            description="Rejoin the tournament after volunteering to sit out",
            color=0xffc629
        )
    ]

    # Set the footer for each page
    for i, page in enumerate(pages, start=1):
        page.set_footer(text=f"Page {i} of {len(pages)}")

    current_page = 0

    class HelpView(discord.ui.View):
        def __init__(self, *, timeout=180):
            super().__init__(timeout=timeout)
            self.message = None

        async def update_message(self, interaction: discord.Interaction):
            await interaction.response.defer()  # Defer response to prevent timeout error
            if self.message:
                await self.message.edit(embed=pages[current_page], view=self)

        @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
        async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            nonlocal current_page
            current_page = (current_page - 1) % len(pages)  # Loop back to last page if on the first page
            await self.update_message(interaction)

        @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            nonlocal current_page
            current_page = (current_page + 1) % len(pages)  # Loop back to first page if on the last page
            await self.update_message(interaction)

    view = HelpView()
    await interaction.response.send_message(embed=pages[current_page], view=view, ephemeral=True)
    view.message = await interaction.original_response()


# Shutdown of aiohttp session
async def close_session():
    global session
    if session is not None:
        await session.close()
        print("HTTP session has been closed.")


@client.event
async def on_disconnect():
    global session
    if session:
        await session.close()  # Ensure session is closed when bot disconnects
        print("Closed aiohttp session.")


# Entry point to run async setup before bot starts
if __name__ == '__main__':
    try:
        # This line of code starts the bot.
        client.run(TOKEN)
    finally:
        asyncio.run(close_session())
