from email import message
from urllib.request import Request
import aiohttp
import aiosqlite # Using this package instead of sqlite for asynchronous processing support
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
from gspread.utils import ValueRenderOption
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials

load_dotenv(find_dotenv())
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

"""
All of the following constants are variables which are set in the .env file, and several are crucial to the bot's functions.
If you don't have an .env file in the same directory as bot.py, ensure you downloaded everything from the bot's GitHub repository and that you renamed ".env.template" to .env.
"""

TOKEN = os.getenv('BOT_TOKEN') # Gets the bot's password token from the .env file and sets it to TOKEN.
GUILD = os.getenv('GUILD_TOKEN') # Gets the server's id from the .env file and sets it to GUILD.
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
MVP_VOTE_THRESHOLD = 3  # Configurable minimum vote threshold

# The following is all used in matchmaking:

RANK_VALUES = {
    "challenger": 100, "grandmaster": 97, "master": 94,
    "diamond": 88, "emerald": 82, "platinum": 75, "gold": 65,
    "silver": 55, "bronze": 40, "iron": 30, "unranked": 0
}

ROLE_MODS = {

    "challenger1": 1.30, "grandmaster1": 1.25, "master1": 1.22,
    "diamond1": 1.15, "emerald1": 1.07, "platinum1": 1.04, "gold1": 1.00,
    "silver1": 1.00, "bronze1": 1.00, "iron1": 1.00, "unranked": 1.00,

    "challenger2": 1.25, "grandmaster2": 1.20, "master2": 1.15,
    "diamond2": 1.10, "emerald2": 1.04, "platinum2": 1.00, "gold2": 1.00,
    "silver2": .95, "bronze2": .95, "iron2": .95, "unranked": 1.00,

    "challenger3": 1.20, "grandmaster3": 1.15, "master3": 1.20,
    "diamond3": 1.00, "emerald3": 1.00, "platinum3": .95, "gold3": .90,
    "silver3": .88, "bronze3": .88, "iron3": .88, "unranked": 1.00,

    "challenger4": 1.05, "grandmaster4": 1.05, "master4": 1.20,
    "diamond4": .90, "emerald4": .82, "platinum4": .75, "gold4": .70,
    "silver4": .70, "bronze4": .70, "iron4": .70, "unranked": 1.00,

    "challenger5": 1.00, "grandmaster5": 1.00, "master5": .95,
    "diamond5": .85, "emerald5": .75, "platinum5": .70, "gold5": .70,
    "silver5": .70, "bronze5": .70, "iron5": .70, "unranked": 1.00

}

randomness = 5 # Used in matchmaking, 5 total points of randomness between scores for players, I.E. a player with 100 base points could be rated as anywhere between 95 and 105 points
absoluteMaximumDifference = 21  # Also used in matchmaking, this is the largest number of Quality Points a team can differ from the other team and still play

# Define current_teams as a global variable
current_teams = {"team1": None, "team2": None}

# Adjust event loop policy for Windows
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Semaphore to limit the number of concurrent API requests to Riot (added to address connection errors pulling player rank with /stats)
api_semaphore = asyncio.Semaphore(5)  # Limit concurrent requests to 5

session = None

# Set up gspread for access by functions

gc = gspread.service_account(filename='C:\\Users\\jlp75069\\source\\repos\\ksu capstone testing\\ksu capstone testing\\gspread_service_account.json')
googleWorkbook = gc.open_by_key(GSHEETS_ID)

tourneyDB = googleWorkbook.worksheet('TournamentDatabase')
gameDB = googleWorkbook.worksheet('GameDatabase')
playerDB = googleWorkbook.worksheet('PlayerDatabase')

# Set up API call to get data from the database

playerAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(
    GSHEETS_ID) + '/values/PlayerDatabase!A%3AI?majorDimension=ROWS&key=' + str(GSHEETS_API))
gameAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(
    GSHEETS_ID) + '/values/GameDatabase!A%3AI?majorDimension=COLUMNS&key=' + str(GSHEETS_API))
tourneyAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(
    GSHEETS_ID) + '/values/TournamentDatabase!A%3AD?majorDimension=COLUMNS&key=' + str(GSHEETS_API))

async def get_friendly_discord_id(discord_id: int, guild: discord.Guild) -> str:
    """
    Converts a numeric Discord ID into a friendly username#discriminator format.
    """
    member = guild.get_member(discord_id)
    if member:
        return f"{member.name}#{member.discriminator}"

    return None

def refreshPlayerData():
    playerDB = googleWorkbook.worksheet('PlayerDatabase')
    playerAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(
    GSHEETS_ID) + '/values/PlayerDatabase!A%3AI?majorDimension=ROWS&key=' + str(GSHEETS_API))


def refreshGameData():
    gameDB = googleWorkbook.worksheet('GameDatabase')
    gameAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(
        GSHEETS_ID) + '/values/GameDatabase!A%3AI?majorDimension=COLUMNS&key=' + str(GSHEETS_API))


def refreshTourneyData():
    tourneyDB = googleWorkbook.worksheet('TournamentDatabase')
    tourneyAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(
        GSHEETS_ID) + '/values/TournamentDatabase!A%3AD?majorDimension=COLUMNS&key=' + str(GSHEETS_API))

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
                async with session.get(url, headers=headers, timeout=timeout, ssl=False) as response:  # Disable SSL verification
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

        super().__init__(timeout=180)  # 3-minute timeout for voting

        self.lobby_id = lobby_id

        self.winning_team_players = winning_team_players

        self.add_item(MVPDropdown(winning_team_players))



class MVPDropdown(discord.ui.Select):
    def init(self, winning_team_players):
        options = [discord.SelectOption(label=player.name, value=player.name) for player in winning_team_players]
        super().init(placeholder="Select the MVP", options=options)
        self.winning_team_players = winning_team_players  # Store for reference in callback

    async def callback(self, interaction: discord.Interaction):
        # Get the voter's Discord ID in username#discriminator format
        voter_discord_id = f"{interaction.user.name}#{interaction.user.discriminator}"

        # Fetch the voter's name from PlayerDatabase using their Discord ID
        existing_records = playerDB.get_all_records()
        voter_name = None
        for record in existing_records:
            if record.get("Discord ID") == voter_discord_id:
                voter_name = record.get("Discord ID")
                break

        if not voter_name:
            await interaction.response.send_message("❌ Could not find your name in the database. Please link your account with /link.", ephemeral=True)
            return

        # Get the selected MVP's name
        selected_mvp_name = self.values[0]

        # Prevent self-voting by comparing voter's name (from database) with selected MVP's name
        if voter_name.lower() == selected_mvp_name.lower():
            await interaction.response.send_message("❌ You cannot vote for yourself!", ephemeral=True)
            return

        # Update MVP votes using the player's name
        mvp_votes[self.view.lobby_id][selected_mvp_name] += 1
        await interaction.response.send_message(f"✅ You voted for {selected_mvp_name} as MVP!", ephemeral=True)



@tree.command(

    name="mvp",

    description="Vote for the MVP from the winning team.",

    guild=discord.Object(GUILD)

)

async def mvp(interaction: discord.Interaction):

    global current_teams, game_winners



    # Check if the game has a winner

    lobby_id = gameDB.col_values(1)[-1]  # Get the latest game ID

    if lobby_id not in game_winners:

        await interaction.response.send_message("❌ No winner has been declared for this game yet.", ephemeral=True)

        return



    # Get the winning team

    winning_team = game_winners[lobby_id]

    winning_team_players = winning_team.playerList



    # Create the MVP voting view

    view = MVPView(lobby_id, winning_team_players)

    await interaction.response.send_message("Vote for the MVP from the winning team:", view=view, ephemeral=True)



@tree.command(

    name="gamewinner",

    description="Declare the winning team for the current game (Admin only).",

    guild=discord.Object(GUILD)

)

@commands.has_permissions(administrator=True)

async def gamewinner(interaction: discord.Interaction, winning_team: str):

    global current_teams, game_winners



    # Validate the winning team input

    if winning_team.lower() not in ["blue", "red"]:

        await interaction.response.send_message("❌ Invalid team. Please specify 'blue' or 'red'.", ephemeral=True)

        return



    # Get the current lobby ID

    lobby_id = gameDB.col_values(1)[-1]  # Get the latest game ID

    game_row = int(lobby_id) + 1  # Row number in GameDatabase (header is row 1)



    # Determine the winning team

    if winning_team.lower() == "blue":

        game_winners[lobby_id] = current_teams["team1"]

    else:

        game_winners[lobby_id] = current_teams["team2"]



    # Update GameDatabase with the winning team

    gameDB.update_acell(f'C{game_row}', winning_team.capitalize())  # Column C is "Winning Team"



    # Notify the server

    await interaction.response.send_message(f"✅ {winning_team.capitalize()} team has been declared the winner!", ephemeral=False)



    # Start MVP voting

    winning_team_players = game_winners[lobby_id].playerList

    view = MVPView(lobby_id, winning_team_players)

    await interaction.followup.send("Vote for the MVP from the winning team:", view=view)



@tree.command(

    name="mvpresult",

    description="Declare the MVP for the current game (Admin only).",

    guild=discord.Object(GUILD)

)

@commands.has_permissions(administrator=True)

async def mvpresult(interaction: discord.Interaction):

    global mvp_votes, game_winners



    # Get the current lobby ID

    lobby_id = gameDB.col_values(1)[-1]  # Get the latest game ID

    game_row = int(lobby_id) + 1  # Row number in GameDatabase (header is row 1)



    # Check if there are any MVP votes

    if lobby_id not in mvp_votes or not mvp_votes[lobby_id]:

        await interaction.response.send_message("❌ No MVP votes have been cast for this game.", ephemeral=True)

        return



    # Find the MVP(s) with the most votes

    max_votes = max(mvp_votes[lobby_id].values())

    mvps = [player for player, votes in mvp_votes[lobby_id].items() if votes == max_votes]



    # Check if the MVP(s) meet the vote threshold

    if max_votes < MVP_VOTE_THRESHOLD:

        await interaction.response.send_message(f"❌ No MVP has reached the minimum vote threshold of {MVP_VOTE_THRESHOLD}.", ephemeral=True)

        return



    # Save MVP(s) to GameDatabase and update PlayerDatabase

    existing_records = playerDB.get_all_records()

    if len(mvps) == 1:

        mvp_name = mvps[0]

        gameDB.update_acell(f'D{game_row}', mvp_name)  # Column D is "MVP"



        # Update MVP count in PlayerDatabase

        for i, record in enumerate(existing_records, start=2):

            if record["Discord ID"] == mvp_name:

                current_mvps = int(record.get("MVPs", 0))

                playerDB.update_cell(i, 11, current_mvps + 1)  # Column K (11) is "MVPs"

                break



        await interaction.response.send_message(f"🎉 **{mvp_name}** has been declared the MVP with {max_votes} votes!", ephemeral=False)

    else:

        mvp_names = ", ".join(mvps)

        gameDB.update_acell(f'D{game_row}', mvp_names)  # Save co-MVPs as a comma-separated string



        # Update MVP count for each co-MVP in PlayerDatabase

        for mvp_name in mvps:

            for i, record in enumerate(existing_records, start=2):

                if record["Discord ID"] == mvp_name:

                    current_mvps = int(record.get("MVPs", 0))

                    playerDB.update_cell(i, 11, current_mvps + 1)  # Column K (11) is "MVPs"

                    break



        await interaction.response.send_message(f"🎉 **{mvp_names}** have been declared co-MVPs with {max_votes} votes each!", ephemeral=False)



    # Clear MVP votes for this lobby

    mvp_votes[lobby_id].clear()

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

                    # Debug: Print all records and the friendly Discord ID being searched
                    print(f"Searching for friendly Discord ID: {friendly_discord_id}")
                    print("Existing records:")
                    for record in existing_records:
                        print(record)

                    # Search for the player in the database using the friendly Discord ID
                    for i, record in enumerate(existing_records, start=2):  # Start from row 2 (headers in row 1)
                        if record.get("Discord ID") == friendly_discord_id:  # Compare using friendly Discord ID
                            row_index = i
                            break

                    if row_index:
                        # Player already exists in the database, update their Riot ID and rank
                        playerDB.update_cell(row_index, 2, friendly_discord_id)  # Update friendly Discord ID
                        playerDB.update_cell(row_index, 3, rank)  # Update Rank Tier

                        await interaction.followup.send(
                            f"Your Riot ID '{riot_id}' has been updated, and your rank has been updated to {rank}.",
                            ephemeral=True,
                        )
                    else:
                        # Player does not exist in the database, create a new row
                        new_row = [
                            member.display_name,  # Player Name
                            friendly_discord_id,  # Friendly Discord ID
                            rank,                 # Rank Tier
                            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0  # Default stats
                        ]
                        playerDB.append_row(new_row)

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
                            rank = f"{entry.get('tier', 'N/A')} {entry.get('rank', '')}".strip()

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
            embed.add_field(name="Win Rate", value=f"{player_stats['WR %'] * 100:.0f}%" if player_stats['WR %'] is not None else "N/A", inline=True)

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

# Player class.
class participant():

    def __init__(self, playerName, playerRank, topPreference, jgPreference, midPreference, adcPreference,
                 supPreference):

        self.name = playerName
        self.rank = playerRank
        self.baseQualityPoints = int(RANK_VALUES[self.rank]) + random.uniform(-randomness,randomness)
        self.topPreference = topPreference
        self.topQP = round(
            (self.baseQualityPoints * ROLE_MODS[self.rank + str(self.topPreference)]) + random.uniform(-randomness,
                                                                                                       randomness), 2)
        self.jgPreference = jgPreference
        self.jgQP = round(
            (self.baseQualityPoints * ROLE_MODS[self.rank + str(self.jgPreference)]) + random.uniform(-randomness,
                                                                                                      randomness), 2)
        self.midPreference = midPreference
        self.midQP = round(
            (self.baseQualityPoints * ROLE_MODS[self.rank + str(self.midPreference)]) + random.uniform(-randomness,
                                                                                                       randomness), 2)
        self.adcPreference = adcPreference
        self.adcQP = round(
            (self.baseQualityPoints * ROLE_MODS[self.rank + str(self.adcPreference)]) + random.uniform(-randomness,
                                                                                                       randomness), 2)
        self.supPreference = supPreference
        self.supQP = round(
            (self.baseQualityPoints * ROLE_MODS[self.rank + str(self.supPreference)]) + random.uniform(-randomness,
                                                                                                       randomness), 2)
        self.QPList = [self.topQP, self.jgQP, self.midQP, self.adcQP, self.supQP]
        self.currentRole = ""
        self.currentQP = 0

    def updatePlayerQP(self):

        match self.currentRole:

            case "top":

                self.currentQP = self.topQP

            case "jg":

                self.currentQP = self.jgQP

            case "mid":

                self.currentQP = self.midQP

            case "adc":

                self.currentQP = self.adcQP

            case "sup":

                self.currentQP = self.supQP

            case "":

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
            playerList[0].baseQualityPoints + playerList[1].baseQualityPoints + playerList[2].baseQualityPoints + playerList[3].baseQualityPoints +
            playerList[4].baseQualityPoints + random.uniform(-randomness,randomness), 2)
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

        for player in self.playerList:
            player.updatePlayerQP()

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
        all_potential_role_assignments = list(itertools.permutations(range(1,6)))
        best_assignment = None
        lowest_score = float('inf')

        for potentialAssignment in all_potential_role_assignments:
            current_score = self.checkScore(potentialAssignment)
            myList.append([current_score,potentialAssignment])

        intermediateList = (sorted(myList, key=operator.itemgetter(0)))
        finalList = []
        for x in range(0,len(intermediateList)):

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

def isPlayerMatchupValid(player1,player2):

    if player1.rank in ['challenger','grandmaster','master'] and player2.rank in ['challenger','grandmaster','master']:

        return True

    elif player1.rank in ['emerald','diamond','master'] and player2.rank in ['emerald','diamond','master']:

        return True

    elif (player1.rank in ['platinum','gold'] and player2.rank in ['platinum','gold']) or (player1.rank in ['platinum','emerald'] and player2.rank in ['platinum','emerald']):

        return True

    elif (player1.rank in ['iron','bronze','silver'] and player2.rank in ['iron','bronze','silver']) or (player1.rank in ['gold','silver'] and player2.rank in ['gold','silver']):

        return True

    else:
      
        return False

def createDummyTeam(teamPlayerList,roleConfiguration):

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

def formatList(playerList):
    returnableList = []

    # Ensure the playerList has the correct number of columns (7 per player)
    for x in range(0, len(playerList), 7):
        try:
            # Extract player data
            playerName = playerList[x]
            playerRank = playerList[x + 1]
            topPreference = int(playerList[x + 2])
            jgPreference = int(playerList[x + 3])
            midPreference = int(playerList[x + 4])
            adcPreference = int(playerList[x + 5])
            supPreference = int(playerList[x + 6])

            # Create a participant object
            participantToAdd = participant(
                playerName, playerRank, topPreference, jgPreference, midPreference, adcPreference, supPreference
            )
            print(f"Adding the following participant to the list of players: {participantToAdd.name}")
            returnableList.append(participantToAdd)
        except Exception as e:
            print(f"Error creating participant from row {x}: {e}")

    return returnableList


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


def matchmake(
        playerList):  # Start by randomizing teams and calculating QP. Then, compare to absoluteMaximumDifference. If
    # diff is large, swap best and worst players. If diff is above threshold but not as large, swap random players. Continue
    # swapping until it either works or we need to start over.

    keepLooping = True
    totalLoops = 0
    while keepLooping == True:

        totalLoops+=1
        random.shuffle(playerList)

        team1 = []
        team2 = []

        for x in range(0, len(playerList), 2):
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

        needsOptimization = True
        numRuns = 0
        plausibleBackupTeam1 = []
        plausibleBackupTeam2 = []
        while needsOptimization == True:  # Attempt to more balance teams

            # Case 1----------------------------------------------------------------------------------------

            if (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) < 0 and abs(
                    intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > 75:  # Case 1: A negative difference that is larger than an arbirary large number means that team 2 is better than team 1 and teams are too unbalanced

                numRuns += 1

                print("Case 1 is happening")
                print("Total difference is: ")
                print((intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))

                print('swapping players')
                print('team 1 before swap: ')
                print(intermediateTeam1.topLaner.name)
                print(intermediateTeam1.jgLaner.name)
                print(intermediateTeam1.midLaner.name)
                print(intermediateTeam1.adcLaner.name)
                print(intermediateTeam1.supLaner.name)
                print('team 2 before swap: ')
                print(intermediateTeam2.topLaner.name)
                print(intermediateTeam2.jgLaner.name)
                print(intermediateTeam2.midLaner.name)
                print(intermediateTeam2.adcLaner.name)
                print(intermediateTeam2.supLaner.name)
                print('worst player on team 1 is: ')
                print(intermediateTeam1.findLowestQP().name)
                print('worst player on team 1s role is: ')
                print(intermediateTeam1.findLowestQP().currentRole)
                print('best player on team 2 is: ')
                print(intermediateTeam2.findHighestQP().name)
                print('best player on team 2s role is: ')
                print(intermediateTeam2.findHighestQP().currentRole)

                swapPlayersToDifferentTeam(intermediateTeam1.findLowestQP(), intermediateTeam1,
                                           intermediateTeam2.findHighestQP(), intermediateTeam2)

                print("swap complete")
                print('team 1 after swap: ')
                print(intermediateTeam1.topLaner.name)
                print(intermediateTeam1.jgLaner.name)
                print(intermediateTeam1.midLaner.name)
                print(intermediateTeam1.adcLaner.name)
                print(intermediateTeam1.supLaner.name)
                print('team 2 after swap: ')
                print(intermediateTeam2.topLaner.name)
                print(intermediateTeam2.jgLaner.name)
                print(intermediateTeam2.midLaner.name)
                print(intermediateTeam2.adcLaner.name)
                print(intermediateTeam2.supLaner.name)
                print("Total difference is now: ")
                print(((intermediateTeam1.teamTotalQP) - (intermediateTeam2.teamTotalQP)))

                if (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) < 0 and abs(
                        intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference:

                    needsOptimization = True
                    print("Still needs work! Case 1 complete")
                    print("Current QP difference is: ")
                    print(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP)

                else:

                    needsOptimization = False
                    print("Might be relatively balanced! Case 1 complete")
                    print("Current QP difference is: ")
                    print(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP)

                if numRuns > 10:

                    break

            # Case 1----------------------------------------------------------------------------------------

            # Case 2----------------------------------------------------------------------------------------

            elif (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > 0 and abs(
                    intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > 75:  # Case 2: A positive difference that is larger than an arbitrary large number means that team 1 is better than team 2 and teams are too unbalanced

                numRuns += 1

                print("Case 2 is happening")
                print("Total difference is: ")
                print((intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))

                print('swapping players')
                print('team 1 before swap: ')
                print(intermediateTeam1.topLaner.name)
                print(intermediateTeam1.jgLaner.name)
                print(intermediateTeam1.midLaner.name)
                print(intermediateTeam1.adcLaner.name)
                print(intermediateTeam1.supLaner.name)
                print('team 2 before swap: ')
                print(intermediateTeam2.topLaner.name)
                print(intermediateTeam2.jgLaner.name)
                print(intermediateTeam2.midLaner.name)
                print(intermediateTeam2.adcLaner.name)
                print(intermediateTeam2.supLaner.name)
                print('worst player on team 2 is: ')
                print(intermediateTeam2.findLowestQP().name)
                print('worst player on team 2s role is: ')
                print(intermediateTeam2.findLowestQP().currentRole)
                print('best player on team 1 is: ')
                print(intermediateTeam1.findHighestQP().name)
                print('best player on team 1s role is: ')
                print(intermediateTeam1.findHighestQP().currentRole)

                swapPlayersToDifferentTeam(intermediateTeam1.findHighestQP(), intermediateTeam1,
                                           intermediateTeam2.findLowestQP(), intermediateTeam2)

                print("swap complete")
                print('team 1 after swap: ')
                print(intermediateTeam1.topLaner.name)
                print(intermediateTeam1.jgLaner.name)
                print(intermediateTeam1.midLaner.name)
                print(intermediateTeam1.adcLaner.name)
                print(intermediateTeam1.supLaner.name)
                print('team 2 after swap: ')
                print(intermediateTeam2.topLaner.name)
                print(intermediateTeam2.jgLaner.name)
                print(intermediateTeam2.midLaner.name)
                print(intermediateTeam2.adcLaner.name)
                print(intermediateTeam2.supLaner.name)
                print("Total difference is now: ")
                print((intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))

                if (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > 0 and abs(
                        intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference:

                    needsOptimization = True
                    print("Still needs work! Case 2 complete")
                    print("Current QP difference is: ")
                    print(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP)

                else:

                    needsOptimization = False
                    print("Might be relatively balanced! Case 2 complete")
                    print("Current QP difference is: ")
                    print(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP)    
                    
                if numRuns > 10:

                    break

            # Case 2----------------------------------------------------------------------------------------

            # Case 3----------------------------------------------------------------------------------------

            elif (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) < 0 and abs(
                    intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference:  # Case 3: A negative difference that is larger than the maximum but smaller than an arbitrary large number means that team 2 is better than team 1 and teams are only slightly unbalanced.

                numRuns += 1

                print("Case 3 is happening")
                print("Total difference before making a swap is: ")
                print(abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))

                tries = 0
                keepLoopingInner = True
                while keepLoopingInner == True:

                    tries += 1
                  
                    team1List = [intermediateTeam1.topLaner, intermediateTeam1.jgLaner ,intermediateTeam1.midLaner, intermediateTeam1.adcLaner, intermediateTeam1.supLaner]
                    team1WorstToBest = (sorted(team1List, key=lambda x: x.baseQualityPoints))
                    team2List = [intermediateTeam2.topLaner, intermediateTeam2.jgLaner ,intermediateTeam2.midLaner, intermediateTeam2.adcLaner, intermediateTeam2.supLaner]
                    team2WorstToBest = (sorted(team2List, key=lambda x: x.baseQualityPoints))

                    randomPlayerTeam1 = team1WorstToBest[2:]
                    randomChoice1 = random.choice(randomPlayerTeam1)

                    randomPlayerTeam2 = team2WorstToBest[:2]
                    randomChoice2 = random.choice(randomPlayerTeam2)
                  
                    swapPlayersToDifferentTeam(randomChoice1,intermediateTeam1,randomChoice2,intermediateTeam2)
                    print("Made a swap!")
                    print("Total difference after making a swap is: ")
                    print((intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))

                    if abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference and tries < 10:

                        keepLoopingInner = True

                    else:

                        keepLoopingInner = False

                if numRuns > 10:

                    break

            # Case 3----------------------------------------------------------------------------------------

            # Case 4----------------------------------------------------------------------------------------

            elif (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > 0 and abs(
                    intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference:  # Case 4: A positive difference that is larger than the maximum but smaller than an arbitrary large number means that team 1 is better than team 2 and teams are only slightly unbalanced.

                numRuns += 1

                print("Case 4 is happening")
                print("Total difference before making a swap is: ")
                print((intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))

                tries = 0
                keepLoopingInner = True
                while keepLoopingInner == True:

                    tries += 1

                    team1List = [intermediateTeam1.topLaner, intermediateTeam1.jgLaner ,intermediateTeam1.midLaner, intermediateTeam1.adcLaner, intermediateTeam1.supLaner]
                    team1WorstToBest = (sorted(team1List, key=lambda x: x.baseQualityPoints))
                    team2List = [intermediateTeam2.topLaner, intermediateTeam2.jgLaner ,intermediateTeam2.midLaner, intermediateTeam2.adcLaner, intermediateTeam2.supLaner]
                    team2WorstToBest = (sorted(team2List, key=lambda x: x.baseQualityPoints))

                    randomPlayerTeam1 = team1WorstToBest[:2]
                    randomChoice1 = random.choice(randomPlayerTeam1)

                    randomPlayerTeam2 = team2WorstToBest[2:]
                    randomChoice2 = random.choice(randomPlayerTeam2)

                    swapPlayersToDifferentTeam(randomChoice1,intermediateTeam1,randomChoice2,intermediateTeam2)
                    print("Made a swap!")
                    print("Total difference after making a swap is: ")
                    print((intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))

                    if abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference and tries < 10:

                        keepLoopingInner = True

                    else:

                        keepLoopingInner = False

                if numRuns > 10:

                    break

            # Case 4----------------------------------------------------------------------------------------

            # Case 5----------------------------------------------------------------------------------------

            else:  # Case 5: The difference should now be below AbsoluteMaximumValue, so teams are quite balanced.

                break
            
        numRuns += 1
        needsOptimization = False
        print(str(intermediateTeam1.teamTotalQP) + ' is team 1s points')
        print(str(intermediateTeam2.teamTotalQP) + ' is team 2s points')
        print("this is the point differential, which should be less than " + str(absoluteMaximumDifference))
        print(abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))
        print("This is team 1")
        print(intermediateTeam1.topLaner.name)
        print(intermediateTeam1.jgLaner.name)
        print(intermediateTeam1.midLaner.name)
        print(intermediateTeam1.adcLaner.name)
        print(intermediateTeam1.supLaner.name)
        print('This is team 2')
        print(intermediateTeam2.topLaner.name)
        print(intermediateTeam2.jgLaner.name)
        print(intermediateTeam2.midLaner.name)
        print(intermediateTeam2.adcLaner.name)
        print(intermediateTeam2.supLaner.name)

        needsOptimization = False
        keepLooping = False

        # Run final checks here (is a Grandmaster facing a gold, somehow?)

        masterListTeam1 = intermediateTeam1.playerList
        masterListTeam2 = intermediateTeam2.playerList

        intermediateTeam1.findListOfBestToWorstRoleAssignments()
        intermediateTeam2.findListOfBestToWorstRoleAssignments()

        team1Configurations = intermediateTeam1.listOfBestToWorstRoleAssignments
        team2Configurations = intermediateTeam2.listOfBestToWorstRoleAssignments

        plausibleTeamCombos = []
                
        for x in range(0,len(team1Configurations)):

            dummyTeam1 = createDummyTeam(masterListTeam1,team1Configurations[x])

            for y in range(0,len(team2Configurations)):

                dummyTeam2 = createDummyTeam(masterListTeam2,team2Configurations[y])

                result1 = isPlayerMatchupValid(dummyTeam1.playerList[0],dummyTeam2.playerList[0])
                result2 = isPlayerMatchupValid(dummyTeam1.playerList[1],dummyTeam2.playerList[1])
                result3 = isPlayerMatchupValid(dummyTeam1.playerList[2],dummyTeam2.playerList[2])
                result4 = isPlayerMatchupValid(dummyTeam1.playerList[3],dummyTeam2.playerList[3])
                result5 = isPlayerMatchupValid(dummyTeam1.playerList[4],dummyTeam2.playerList[4])
                if result1 == True and result2 == True and result3 == True and result4 == True and result5 == True:

                    plausibleTeamCombos.append([team1Configurations[x],team2Configurations[y]])

        lowestScore = 1000     

        for z in range(0, len(plausibleTeamCombos)):

            plausibleTeam1 = createDummyTeam(masterListTeam1,plausibleTeamCombos[z][0])
            plausibleTeam2 = createDummyTeam(masterListTeam2,plausibleTeamCombos[z][1])

            matchupScore =  plausibleTeam1.topLaner.topPreference + plausibleTeam1.jgLaner.jgPreference + plausibleTeam1.midLaner.midPreference + plausibleTeam1.adcLaner.adcPreference + plausibleTeam1.supLaner.supPreference + plausibleTeam2.topLaner.topPreference + plausibleTeam2.jgLaner.jgPreference + plausibleTeam2.midLaner.midPreference + plausibleTeam2.adcLaner.adcPreference + plausibleTeam2.supLaner.supPreference
            if matchupScore < lowestScore:

                bestMatchup = [plausibleTeam1,plausibleTeam2]
                lowestScore = matchupScore

                plausibleBackupTeam1.append(plausibleTeam1)
                plausibleBackupTeam2.append(plausibleTeam2)

        if len(plausibleBackupTeam1) == 0 and totalLoops < 11: # No valid team exists, but we can try to create new random teams.

            print('Trying to loop through from the beginning.')
            keepLooping = True

        elif len(plausibleBackupTeam1) == 0 and totalLoops >= 11: # We have tried, but nothing is valid. Probably due to not valid matchup-able players.

            print("We have tried many times, but no valid team has been created. A backup pair of teams has been presented, but Admins should be aware that these teams may be very imbalanced.")
            return [intermediateTeam1,intermediateTeam2]
                       
        else: # There is at least one valid team, have to find the best matchup between the list of valid teams.

            lowestDiff = 1000
            finalLowestMatchup = []
            for x in range(len(plausibleBackupTeam1)):

                for y in range(len(plausibleBackupTeam2)):

                    differenceInSkill = abs(plausibleBackupTeam1[x].teamTotalQP - plausibleBackupTeam2[y].teamTotalQP)
                    if differenceInSkill < lowestDiff:

                        finalLowestMatchup = [plausibleBackupTeam1[x],plausibleBackupTeam2[y]]                   
                
            if finalLowestMatchup != []:

                return finalLowestMatchup

            else:

                print("No valid Teams exist, returning random teams in idealized roles.")
                return [intermediateTeam1,intermediateTeam2]

    print("The best matchup is these two teams:")

    print(bestMatchup[0].playerList[0])
    print(bestMatchup[0].playerList[0].rank)
    print(bestMatchup[0].playerList[1])
    print(bestMatchup[0].playerList[1].rank)
    print(bestMatchup[0].playerList[2])
    print(bestMatchup[0].playerList[3].rank)
    print(bestMatchup[0].playerList[3])
    print(bestMatchup[0].playerList[3].rank)
    print(bestMatchup[0].playerList[4])
    print(bestMatchup[0].playerList[4].rank)

    print(bestMatchup[1].playerList[0])
    print(bestMatchup[1].playerList[0].rank)
    print(bestMatchup[1].playerList[1])
    print(bestMatchup[1].playerList[1].rank)
    print(bestMatchup[1].playerList[2])
    print(bestMatchup[1].playerList[3].rank)
    print(bestMatchup[1].playerList[3])
    print(bestMatchup[1].playerList[3].rank)
    print(bestMatchup[1].playerList[4])
    print(bestMatchup[1].playerList[4].rank)

    returnableList = []
    returnableList.append(bestMatchup[0])
    returnableList.append(bestMatchup[1])
    return returnableList

class lobby:
    def __init__(self):
        # Initialize team attributes
        self.team1 = None
        self.team2 = None

        # Fetch the current tournament and game IDs
        currentTourneyID = tourneyDB.col_values(1)[-1]
        previousGameID = gameDB.col_values(1)[-1]
        currentGameID = ""

        if previousGameID.isnumeric():
            currentGameID = int(previousGameID) + 1
        else:
            currentGameID = 1

        # Write the game ID to the database
        gameDB.update_acell('A' + str(currentGameID + 1), str(currentGameID))
        gameDB.update_acell('B' + str(currentGameID + 1), str(currentTourneyID))

        # Fetch player data from the database
        playerDataImport = playerDB.get_all_records()
        players = []
        for x in range(0,len(playerDataImport)):

            players.append([playerDataImport[x]['Discord ID'],playerDataImport[x]['Rank Tier'],playerDataImport[x]['Role 1 (Top)'],playerDataImport[x]['Role 2 (Jungle)'],playerDataImport[x]['Role 3 (Mid)'],playerDataImport[x]['Role 4 (ADC)'],playerDataImport[x]['Role 5 (Support)']])

        random.shuffle(players)

        # Prepare the player list for matchmaking
        finalPlayerList = []
        intermediateList = []

        for person in players:
            
            intermediateList.extend(person)

        finalPlayerList = intermediateList[:70]  # Grabs first 70 elements, 10 players with 7 elements each.
        # Name, rank, role1, role2, role3, role4, role5

        # Format the player list for matchmaking
        matchmakingList = formatList(finalPlayerList)

        # Perform matchmaking
        bothTeams = matchmake(matchmakingList)

        # The teams are stored in two lists
        self.team1 = bothTeams[0]
        self.team2 = bothTeams[1]

        # Format teams for Discord embed
        team1_info = (
            f"**Top:** {self.team1.topLaner.name}\n"
            f"**Jungle:** {self.team1.jgLaner.name}\n"
            f"**Mid:** {self.team1.midLaner.name}\n"
            f"**ADC:** {self.team1.adcLaner.name}\n"
            f"**Support:** {self.team1.supLaner.name}"
        )

        team2_info = (
            f"**Top:** {self.team2.topLaner.name}\n"
            f"**Jungle:** {self.team2.jgLaner.name}\n"
            f"**Mid:** {self.team2.midLaner.name}\n"
            f"**ADC:** {self.team2.adcLaner.name}\n"
            f"**Support:** {self.team2.supLaner.name}"
        )

        # Create and send embed message
        embed = discord.Embed(title="Game Lobby Created", color=0x00ff00)
        embed.add_field(name="**Team 1**", value=team1_info, inline=False)
        embed.add_field(name="**Team 2**", value=team2_info, inline=False)


        # Write the teams to the database
        gameDB.update_acell('E' + str(currentGameID + 1) + 'N' + str(currentGameID + 1), str(currentGameID))
        gameDB.batch_update([{
            'range': 'E' + str(currentGameID + 1) + ':N' + str(currentGameID + 1),
            'values': [
                [str(self.team1.topLaner.name), str(self.team1.jgLaner.name), str(self.team1.midLaner.name),
                 str(self.team1.adcLaner.name), str(self.team1.supLaner.name), str(self.team2.topLaner.name),
                 str(self.team2.jgLaner.name), str(self.team2.midLaner.name), str(self.team2.adcLaner.name),
                 str(self.team2.supLaner.name)]
            ],
        }])

def declareWinner(self, team, gameNumber):
    return team


def declareMVP(self, gameNumber):
    MVP = "winner"
    return MVP


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

    @discord.ui.button(
        label="Volunteer",
        style=discord.ButtonStyle.green)
    async def checkin(self, interaction: discord.Interaction, button: discord.ui.Button):

        player = get(interaction.guild.roles, name='Player')
        volunteer = get(interaction.guild.roles, name='Volunteer')
        member = interaction.user

        if player in member.roles:
            await member.remove_roles(player)
        if volunteer in member.roles:
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                'You have already volunteered to sit out, if you wish to rejoin click rejoin.', ephemeral=True)
            return "Is already checked in"
        await member.add_roles(volunteer)
        await interaction.response.edit_message(view=self)
        await interaction.followup.send('You have volunteered to sit out!', ephemeral=True)
        return "Checked in"

    """
    This button is the leave button. It is used for if the player who has volunteer wants to rejoin
    The following output is to be expected:

    If the user has the player role, it will remove it and tell the player that it has been removed
    If the user does not have the volunteer role, it will tell them to volunteer first.
    """

    @discord.ui.button(
        label="Rejoin",
        style=discord.ButtonStyle.red)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):

        player = get(interaction.guild.roles, name='Player')
        volunteer = get(interaction.guild.roles, name='Volunteer')
        member = interaction.user

        if volunteer in member.roles:
            await member.remove_roles(volunteer)
            await member.add_roles(player)
            await interaction.response.edit_message(view=self)
            await interaction.followup.send('Welcome back in!', ephemeral=True)
            return "Role Removed"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send('You have not volunteered to sit out, please volunteer to sit out first.',
                                        ephemeral=True)
        return "Did not check in yet"


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

        # TODO Write to Database

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
class CheckinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=900)  # 15-minute timeout
        self.roles = {}

    @discord.ui.select(
        placeholder="Select your preferred roles",
        options=[
            discord.SelectOption(label="Top", value="Top"),
            discord.SelectOption(label="Jungle", value="Jungle"),
            discord.SelectOption(label="Mid", value="Mid"),
            discord.SelectOption(label="ADC", value="ADC"),
            discord.SelectOption(label="Support", value="Support"),
        ]
    )
    async def roles_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.roles[select.values[0]] = 1  # Set preference to 1 for selected role
        await interaction.response.send_message(f"You selected: {select.values[0]}", ephemeral=True)

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.green)
    async def submit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.roles:
            await interaction.response.send_message("❌ Please select your roles.", ephemeral=True)
            return

        # Open a modal for Riot ID input
        modal = RiotIDModal(self.roles)
        await interaction.response.send_modal(modal)
class RiotIDModal(discord.ui.Modal, title="Enter Your Riot ID"):
    def __init__(self, roles):
        super().__init__()
        self.roles = roles
        self.riot_id = discord.ui.TextInput(
            label="Riot ID",
            placeholder="Enter your Riot ID (e.g., SummonerName#Tagline)",
            required=True
        )
        self.add_item(self.riot_id)

    async def on_submit(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        discord_username = interaction.user.display_name
        riot_id = self.riot_id.value

        if discord_id in existing_discord_ids:
            await interaction.response.send_message("❌ You have already checked in!", ephemeral=True)
        else:
            try:
                # Prepare the row data to match the Google Sheet structure
                row_data = [
                    discord_username,  # Players1
                    discord_id,        # Discord ID
                    "N/A",            # Rank Tier (will be updated later)
                    self.roles.get("Top", 0),  # Role 1 (Top)
                    self.roles.get("Jungle", 0),  # Role 2 (Jungle)
                    self.roles.get("Mid", 0),  # Role 3 (Mid)
                    self.roles.get("ADC", 0),  # Role 4 (ADC)
                    self.roles.get("Support", 0),  # Role 5 (Support)
                    0,  # Participation (default to 0)
                    0,  # Wins (default to 0)
                    0,  # MVPs (default to 0)
                    0,  # Toxicity (default to 0)
                    0,  # Games Played (default to 0)
                    0,  # WR % (default to 0)
                    0   # Point Total (default to 0)
                ]

                # Append the row to the Google Sheet
                playerDB.append_row(row_data)
                existing_discord_ids.add(discord_id)
                await interaction.response.send_message(
                    f"✅ You have successfully checked in, {discord_username}!",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ An error occurred while checking in: {e}",
                    ephemeral=True
                )

@tree.command(
    name = 'start_tournament',
    description = 'Initiate tournament creation',
    guild = discord.Object(GUILD))
async def startTourney(interaction: discord.Interaction):
    player = interaction.user
    checkinStart = time.time()
    checkinFinish = time.time() + CHECKIN_TIME
    totalMinutes = round(round(CHECKIN_TIME)//60)
    totalSeconds = round(round(CHECKIN_TIME)%60)
    
    view = CheckinButtons()
    await interaction.response.send_message('A new tournament has been started by ' + str(player) + '! You have ' + str(totalMinutes) + ' minutes and ' + str(totalSeconds) + ' seconds to check in. This tournament check-in started at <t:' + str(round(checkinStart)) + ':T>', view = view)

    newTournament = Tournament()

@tree.command(
    name="checkin",
    description="Check in for matchmaking and select your role preferences.",
    guild=discord.Object(GUILD),
)

async def checkin(interaction: discord.Interaction):
    member = interaction.user

    # Fetch the friendly Discord ID
    friendly_discord_id = await get_friendly_discord_id(member.id, interaction.guild)
    if not friendly_discord_id:
        await interaction.response.send_message("❌ Could not find your Discord account.", ephemeral=True)
        return

    # Fetch existing records from Google Sheets
    existing_records = playerDB.get_all_records()
    row_index = None

    # Debug: Print all records and the friendly Discord ID being searched
    print(f"Searching for friendly Discord ID: {friendly_discord_id}")
    print("Existing records:")
    for record in existing_records:
        print(record)

    # Search for the user in the database using the friendly Discord ID
    for i, record in enumerate(existing_records, start=2):
        if record.get("Discord ID") == friendly_discord_id:  # Compare using friendly Discord ID
            row_index = i
            break

    if not row_index:
        await interaction.response.send_message("❌ You must link your Riot ID first using /link.", ephemeral=True)
        return

    # Create the role preference view
    view = RolePreferenceView(member.id)
    embed = discord.Embed(
        title="Role Preferences",
        description="Please rank your preferences for each role (1 = most preferred, 5 = least preferred).",
        color=0xffc629,
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # Send notification to the designated channel
    channel = client.get_channel(int(NOTIFICATION_CHANNEL_ID))
    await channel.send("✅ Tournament check-in has started!")
    
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
    try:
        player = interaction.user
        await interaction.response.send_message('Creating game...', ephemeral=True)

        refreshGameData()
        refreshPlayerData()
        refreshTourneyData()

        # Create a new lobby
        newLobby = lobby()

        # Get the teams from the lobby
        team1 = newLobby.team1
        team2 = newLobby.team2

        # Update the global current_teams variable
        global current_teams
        current_teams["team1"] = team1
        current_teams["team2"] = team2

        # Format the team information for Discord
        team1_info = (
            f"****\n"
            f"Top: {team1.topLaner.name}\n"
            f"Jungle: {team1.jgLaner.name}\n"
            f"Mid: {team1.midLaner.name}\n"
            f"ADC: {team1.adcLaner.name}\n"
            f"Support: {team1.supLaner.name}\n"
        )

        team2_info = (
            f"****\n"
            f"Top: {team2.topLaner.name}\n"
            f"Jungle: {team2.jgLaner.name}\n"
            f"Mid: {team2.midLaner.name}\n"
            f"ADC: {team2.adcLaner.name}\n"
            f"Support: {team2.supLaner.name}\n"
        )

        # Create an embed for better formatting
        embed = discord.Embed(title="Game Lobby Created", color=0x00ff00)
        embed.add_field(name="Team 1", value=team1_info, inline=False)
        embed.add_field(name="Team 2", value=team2_info, inline=False)

        await interaction.followup.send(embed=embed)

    except Exception as e:
        # Log the error and notify the user
        print(f"An error occurred while creating the game: {e}")
        await interaction.followup.send('An error occurred while creating the game. Please try again later.',
                                      ephemeral=True)
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
            await interaction.response.send_message("❌ No teams found. Make sure matchmaking has run first.", ephemeral=True)
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
            await interaction.response.send_message("❌ One or both players were not found in the teams.", ephemeral=True)
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
        playerDB.update_cell(row_index, 12, new_toxicity)  # Assuming column 13 is for toxicity points

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
        playerDB.update_cell(row_index, 12, new_toxicity)  # Assuming column 13 is for toxicity points

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
