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
import os
import platform
import random
import traceback
import time
import requests
import random
import gspread
import gspread.utils
from gspread.utils import ValueRenderOption
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


load_dotenv(find_dotenv())
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

"""
All of the following constants are variables which are set in the .env file, and several are crucial to the bot's functions.
If you don't have an .env file in the same directory as bot.py, ensure you downloaded everything from the bot's GitHub repository and that you renamed ".env.template" to .env.
"""

TOKEN = os.getenv('BOT_TOKEN')#Gets the bot's password token from the .env file and sets it to TOKEN.
GUILD = os.getenv('GUILD_TOKEN')#Gets the server's id from the .env file and sets it to GUILD.
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
GSHEETS_API = os.getenv('GSHEETS_API')
GSHEETS_ID = os.getenv('GSHEETS_ID')
GHSEETS_GAMEDB = os.getenv('GHSEETS_GAMEDB')
GSHEETS_PLAYERDB = os.getenv('GSHEETS_PLAYERDB')
GSHEETS_TOURNAMENTDB = os.getenv('GSHEETS_TOURNAMENTDB')
WELCOME_CHANNEL_ID = os.getenv('WELCOME_CHANNEL_ID')
TIER_WEIGHT = float(os.getenv('TIER_WEIGHT', 0.7))  # Default value of 0.7 if not specified in .env
ROLE_PREFERENCE_WEIGHT = float(os.getenv('ROLE_PREFERENCE_WEIGHT', 0.3))  # Default value of 0.3 if not specified in .env
TIER_GROUPS = os.getenv('TIER_GROUPS', 'UNRANKED,IRON,BRONZE,SILVER:GOLD,PLATINUM:EMERALD:DIAMOND:MASTER:GRANDMASTER:CHALLENGER') # Setting default tier configuration if left blank in .env
CHECKIN_TIME = os.getenv('CHECKIN_TIME')
CHECKIN_TIME = int(CHECKIN_TIME)

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
absoluteMaximumDifference = 20 # Also used in matchmaking, this is the largest number of Quality Points a team can differ from the other team and still play

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

# Set up API call to get data from the database

playerAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/PlayerDatabase!A%3AI?majorDimension=COLUMNS&key=' + str(GSHEETS_API))
playerAPIRequest2 = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/PlayerDatabase!A%3AI?majorDimension=ROWS&key=' + str(GSHEETS_API))
gameAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/GameDatabase!A%3AI?majorDimension=COLUMNS&key=' + str(GSHEETS_API))
tourneyAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/TournamentDatabase!A%3AD?majorDimension=COLUMNS&key=' + str(GSHEETS_API))

def refreshPlayerData():
    
    playerDB = googleWorkbook.worksheet('PlayerDatabase')
    playerAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/PlayerDatabase!A%3AI?majorDimension=COLUMNS&key=' + str(GSHEETS_API))

def refreshGameData():

    gameDB = googleWorkbook.worksheet('GameDatabase')
    gameAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/GameDatabase!A%3AI?majorDimension=COLUMNS&key=' + str(GSHEETS_API))

def refreshTourneyData():

    tourneyDB = googleWorkbook.worksheet('TournamentDatabase')
    tourneyAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/TournamentDatabase!A%3AD?majorDimension=COLUMNS&key=' + str(GSHEETS_API))


# On bot ready event
@client.event
async def on_ready():
    global session
    # Initialize aiohttp session when the bot starts (simplified)
    connector = aiohttp.TCPConnector(
        ttl_dns_cache=300,  # Cache DNS resolution for 5 minutes
        ssl=False           # Disable SSL verification (use with caution)
    )
    session = aiohttp.ClientSession(connector=connector)
    
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

# This is production code that connects to Riot's API. Unnecessary for testing.
""" 
    # Safe API call function with retries for better error handling
async def safe_api_call(url, headers):
    max_retries = 3
    retry_delay = 1  # Delay between retries in seconds

    for attempt in range(max_retries):
        try:
            async with api_semaphore:  # Limit concurrent access to the API
                # Using a timeout context inside the aiohttp request
                timeout = aiohttp.ClientTimeout(total=5)  # Set a 5-second total timeout for the request
                async with session.get(url, headers=headers, timeout=timeout) as response:
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

update_excel() is a function to update the Excel file / spreadsheet for offline database manipulation.
This implementation (as of 2024-10-25) allows the bot host to update the database by simply altering the
spreadsheet, and vice versa; changes through the bot / db update the spreadsheet at the specified path in .env.

This function will work correctly regardless of whether users rename the template spreadsheet (called "PlayerStats.xlsx"), but do not change the sheet name inside it from "PlayerStats".
In this code, the "workbook" is what we normally call a spreadsheet, and the "sheet name" is just a tab inside that spreadsheet.
So, don't confuse the two and think that you can't change the spreadsheet's file name to something different; you can, as long as you leave the tab/sheet name unaltered and
update the spreadsheet path in ".env".

def update_excel(discord_id, player_data):
    try:
        # Load the workbook and get the correct sheet
        workbook = load_workbook(SPREADSHEET_PATH)
        sheet_name = 'PlayerStats'
        if sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
        else:
            raise ValueError(f'Sheet {sheet_name} does not exist in the workbook')

        # Check if the player already exists in the sheet
        found = False
        for row in sheet.iter_rows(min_row=2):  # Assuming the first row is headers
            if str(row[0].value) == discord_id:  # Check if Discord ID matches
                # Update only if there's a difference
                for idx, key in enumerate(player_data.keys()):
                    if row[idx].value != player_data[key]:
                        row[idx].value = player_data[key]
                        found = True
                break

        # If player not found, add a new row
        if not found:
            # Find the first truly empty row, ignoring formatting
            empty_row_idx = sheet.max_row + 1
            for i, row in enumerate(sheet.iter_rows(min_row=2), start=2):
                if all(cell.value is None for cell in row):
                    empty_row_idx = i
                    break

            # Insert the new data into the empty row
            for idx, key in enumerate(player_data.keys(), start=1):
                sheet.cell(row=empty_row_idx, column=idx).value = player_data[key]

        # Save the workbook after updates
        workbook.save(SPREADSHEET_PATH)
        print(f"Spreadsheet '{SPREADSHEET_PATH}' has been updated successfully.")

    except Exception as e:
        print(f"Error updating Excel file: {e}")
        


# Updated get_encrypted_summoner_id function
async def get_encrypted_summoner_id(riot_id):

    Fetches the encrypted summoner ID from the Riot API using Riot ID.
    Args:
    - riot_id: The player's Riot ID in 'username#tagline' format.
    Returns:
    - Encrypted summoner ID (summonerId) if successful, otherwise None.

    # Riot ID is expected to be in the format 'username#tagline'
    if '#' not in riot_id:
        return None

    username, tagline = riot_id.split('#', 1)
    url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{username}/{tagline}"
    headers = {
        "X-Riot-Token": RIOT_API_KEY
    }

    # Fetch PUUID using the safe API call function
    data = await safe_api_call(url, headers)
    if data:
        puuid = data.get('puuid', None)
        if puuid:
            # Use the PUUID to fetch the encrypted summoner ID
            summoner_url = f"https://na1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
            summoner_data = await safe_api_call(summoner_url, headers)
            if summoner_data:
                return summoner_data.get('id', None)  # The summonerId is referred to as `id` in this response

    return None



    Fetches the player's rank from Riot API and updates it in the database.
    Args:
    - conn: The aiosqlite connection object.
    - discord_id: The player's Discord ID.
    - encrypted_summoner_id: The player's encrypted summoner ID.
    - max_retries was added because sometimes the bot failed to connect to the Riot API and properly pull player rank etc (which was leading to rank showing as N/A in /stats.)
      Now, the bot automatically retries the connection several times if this occurs.


async def update_player_rank(conn, discord_id, encrypted_summoner_id):
    await asyncio.sleep(3)  # Initial delay before making the API call

    url = f"https://na1.api.riotgames.com/lol/league/v4/entries/by-summoner/{encrypted_summoner_id}"
    headers = {
        "X-Riot-Token": RIOT_API_KEY
    }

    max_retries = 3

    for attempt in range(max_retries):
        try:
            async with api_semaphore:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        for entry in data:
                            if entry.get("queueType") == "RANKED_SOLO_5x5":
                                rank = entry.get('tier', 'N/A')
                                await conn.execute(
                                    "UPDATE PlayerStats SET PlayerRank = ? WHERE DiscordID = ?",
                                    (rank, discord_id)
                                )
                                await conn.commit()
                                return rank
                        return "UNRANKED"
                    else:
                        print(f"Error fetching player rank: {response.status}, response: {await response.text()}")
        except (aiohttp.ClientConnectionError, aiohttp.ClientResponseError, aiohttp.ClientPayloadError) as e:
            print(f"An error occurred while connecting to the Riot API (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in 5 seconds (attempt {attempt + 1}/{max_retries})...")
                await asyncio.sleep(5)  # Wait for 5 seconds before retrying

    print("All attempts to connect to the Riot API have failed.")
    return "N/A"  # Return "N/A" if all attempts fail

# Command to display stats for a given user
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

        # Update the player's Discord username in the database if needed
        await update_username(player)

        # Connect to the database
        async with aiosqlite.connect(DB_PATH) as conn:
            # Fetch stats from the database
            async with conn.execute("SELECT * FROM PlayerStats WHERE DiscordID=?", (str(player.id),)) as cursor:
                player_stats = await cursor.fetchone()

            # If player exists in the database, proceed
            if player_stats:
                riot_id = player_stats[2]  # The Riot ID column from the database

                # Update encrypted summoner ID and rank in the database
                if riot_id:
                    encrypted_summoner_id = await get_encrypted_summoner_id(riot_id)
                    player_rank = await update_player_rank(conn, str(player.id), encrypted_summoner_id) if encrypted_summoner_id else "N/A"
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
                embed.add_field(name="Participation Points", value=player_stats[3], inline=True)
                embed.add_field(name="Games Played", value=player_stats[7], inline=True)
                embed.add_field(name="Wins", value=player_stats[4], inline=True)
                embed.add_field(name="MVPs", value=player_stats[5], inline=True)
                embed.add_field(name="Win Rate", value=f"{player_stats[8] * 100:.0f}%" if player_stats[8] is not None else "N/A", inline=True)

                # Send the embed as a follow-up response
                await interaction.followup.send(embed=embed, ephemeral=True)

                # Prepare player data dictionary to pass to update_excel
                player_data = {
                    "DiscordID": player_stats[0],
                    "DiscordUsername": player_stats[1],
                    "PlayerRiotID": player_stats[2],
                    "Participation": player_stats[3],
                    "Wins": player_stats[4],
                    "MVPs": player_stats[5],
                    "ToxicityPoints": player_stats[6],
                    "GamesPlayed": player_stats[7],
                    "WinRate": player_stats[8],
                    "PlayerTier": player_stats[10],
                    "PlayerRank": player_rank,
                    "RolePreference": player_stats[12]
                }

                
                # Load the workbook and sheet
                workbook = load_workbook(SPREADSHEET_PATH)
                sheet = workbook.active  # Using the active sheet as the default

                # Check if the player exists in the sheet and if updates are needed
                found = False
                needs_update = False
                for row in sheet.iter_rows(min_row=2):  # Assuming the first row is headers
                    if str(row[0].value) == player_data["DiscordID"]:
                        # Compare each cell to see if an update is needed
                        for key, cell in zip(player_data.keys(), row):
                            if cell.value != player_data[key]:
                                needs_update = True
                                break
                        found = True
                        break

                # If player is not found or an update is needed, update the Excel sheet
                if not found or needs_update:
                    await asyncio.to_thread(update_excel, str(player.id), player_data)
                    await interaction.followup.send(f"Player stats for {player.display_name} have been updated in the Excel sheet.", ephemeral=True)

            else:
                await interaction.followup.send(f"No stats found for {player.display_name}", ephemeral=True)

    except Exception as e:
        # Log the error or handle it appropriately
        print(f"An error occurred: {e}")
        await interaction.followup.send("An unexpected error occurred while fetching player stats.", ephemeral=True)
        

# Riot ID linking command. This is the first command users should type before using other bot features, as it creates a record for them in the database.
@tree.command(
    name='link',
    description="Link your Riot ID to your Discord account.",
    guild=discord.Object(GUILD)
)
async def link(interaction: discord.Interaction, riot_id: str):
    member = interaction.user

    # Riot ID is in the format 'username#tagline', e.g., 'jacstogs#1234'
    if '#' not in riot_id:
        await interaction.response.send_message(
            "Invalid Riot ID format. Please enter your Riot ID in the format 'username#tagline'.",
            ephemeral=True
        )
        return

    # Split the Riot ID into name and tagline
    summoner_name, tagline = riot_id.split('#', 1)
    summoner_name = summoner_name.strip()
    tagline = tagline.strip()

    # Verify that the Riot ID exists using the Riot API
    api_key = os.getenv("RIOT_API_KEY")
    headers = {"X-Riot-Token": api_key}
    url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{summoner_name}/{tagline}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    # Riot ID exists, proceed to link it
                    data = await response.json()  # Get the response data

                    # Debugging: Print the data to see what comes back from the API
                    print(f"Riot API response: {data}")

                    async with aiosqlite.connect(DB_PATH) as conn:
                        try:
                            # Check if the user already exists in the database
                            async with conn.execute("SELECT * FROM PlayerStats WHERE DiscordID = ?", (str(member.id),)) as cursor:
                                result = await cursor.fetchone()

                            if result:
                                # Update the existing record with the new Riot ID
                                await conn.execute(
                                    "UPDATE PlayerStats SET PlayerRiotID = ? WHERE DiscordID = ?",
                                    (riot_id, str(member.id))
                                )
                            else:
                                # Insert a new record if the user doesn't exist in the database
                                await conn.execute(
                                    "INSERT INTO PlayerStats (DiscordID, DiscordUsername, PlayerRiotID) VALUES (?, ?, ?)",
                                    (str(member.id), member.display_name, riot_id)
                                )

                            await conn.commit()

                            await interaction.response.send_message(
                                f"Your Riot ID '{riot_id}' has been successfully linked to your Discord account.",
                                ephemeral=True
                            )
                        except aiosqlite.IntegrityError as e:
                            # Handle UNIQUE constraint violation (i.e., Riot ID already linked)
                            if 'UNIQUE constraint failed: PlayerStats.PlayerRiotID' in str(e):
                                # Riot ID is already linked to another user
                                async with conn.execute(
                                    SELECT DiscordID, DiscordUsername FROM PlayerStats WHERE PlayerRiotID = ?
                                , (riot_id,)) as cursor:
                                    existing_user_data = await cursor.fetchone()

                                if existing_user_data:
                                    existing_user_id, existing_username = existing_user_data
                                    await interaction.response.send_message(
                                        f"Error: This Riot ID is already linked to another Discord user: <@{existing_user_id}>. "
                                        "If this is a mistake, please contact an administrator.",
                                        ephemeral=True
                                    )
                            else:
                                raise e  # Reraise the error if it's not related to UNIQUE constraint
                else:
                    # Riot ID does not exist or other error
                    error_msg = await response.text()
                    print(f"Riot API error response: {error_msg}")
                    await interaction.response.send_message(
                        f"The Riot ID '{riot_id}' could not be found. Please double-check and try again.",
                        ephemeral=True
                    )
    except Exception as e:
        print(f"An error occurred while connecting to the Riot API: {e}")
        await interaction.response.send_message(
            "An unexpected error occurred while trying to link your Riot ID. Please try again later.",
            ephemeral=True
        )


@tree.command(
    name='unlink',
    description="Unlink a player's Riot ID and remove their statistics from the database.",
    guild=discord.Object(GUILD) 
)
@commands.has_permissions(administrator=True)
async def unlink(interaction: discord.Interaction, player: discord.Member):
    try:
        # Store the player to be unlinked for confirmation
        global player_to_unlink
        player_to_unlink = player
        await interaction.response.send_message(f"Type /confirm if you are sure you want to remove {player.display_name}'s record from the bot database.", ephemeral=True)
    
    except commands.MissingPermissions:
        await interaction.response.send_message("You do not have permission to use this command. Only administrators can unlink a player's account.", ephemeral=True)
    
    except Exception as e:
        # Log the error or handle it appropriately
        print(f"An error occurred: {e}")
        await interaction.response.send_message("An unexpected error occurred while unlinking the account.", ephemeral=True)

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
            # Check if the user exists in the database
            async with aiosqlite.connect(DB_PATH) as conn:
                async with conn.execute("SELECT * FROM PlayerStats WHERE DiscordID = ?", (str(player_to_unlink.id),)) as cursor:
                    player_stats = await cursor.fetchone()

                if player_stats:
                    # Delete user from the database
                    await conn.execute("DELETE FROM PlayerStats WHERE DiscordID = ?", (str(player_to_unlink.id),))
                    await conn.commit()
                    await interaction.response.send_message(f"{player_to_unlink.display_name}'s Riot ID and statistics have been successfully unlinked and removed from the database.", ephemeral=True)
                    player_to_unlink = None
                else:
                    await interaction.response.send_message(f"No statistics found for {player_to_unlink.display_name}. Make sure the account is linked before attempting to unlink.", ephemeral=True)
        else:
            await interaction.response.send_message("No player unlink request found. Please use /unlink first.", ephemeral=True)
    
    except commands.MissingPermissions:
        await interaction.response.send_message("You do not have permission to use this command. Only administrators can confirm the unlinking of a player's account.", ephemeral=True)
    
    except Exception as e:
        # Log the error or handle it appropriately
        print(f"An error occurred: {e}")
        await interaction.response.send_message("An unexpected error occurred while confirming the unlinking of the account.", ephemeral=True)


@tree.command(
    name='resetdb',
    description="Reset player data to defaults, except for ID/rank/role preference information.",
    guild=discord.Object(GUILD)
)
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
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                UPDATE PlayerStats
                SET
                    Participation = 0,
                    Wins = 0,
                    MVPs = 0,
                    ToxicityPoints = 0,
                    GamesPlayed = 0,
                    WinRate = NULL,
                    TotalPoints = 0
            )
            await conn.commit()

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

"""

# Continuing code here

        

# Role preference command
class RolePreferenceView(discord.ui.View):
    def __init__(self, member_id, initial_values):
        super().__init__(timeout=60)
        self.member_id = member_id
        self.values = initial_values  # Use the initial preferences from the database
        self.embed_message = None  # Track the embed message to edit later
        roles = ["Top", "Jungle", "Mid", "Bot", "Support"]
        for role in roles:
            self.add_item(RolePreferenceDropdown(role, self))  # Pass the view to the dropdown

    async def update_embed_message(self, interaction):
        # Create an embed to display role preferences
        embed = discord.Embed(title="Role Preferences", color=0xffc629)
        for role, value in self.values.items():
            embed.add_field(name=role, value=f"Preference: {value}", inline=False)

        # Send or edit the ephemeral embed message with the updated preferences
        if self.embed_message is None:
            self.embed_message = await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await self.embed_message.edit(embed=embed)


class RolePreferenceDropdown(discord.ui.Select):
    def __init__(self, role, parent_view: RolePreferenceView):
        self.role = role
        self.parent_view = parent_view  # Reference to the parent view
        options = [
            discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 6)
        ]
        super().__init__(
            placeholder=f"Select your matchmaking priority for {role}",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        # Update the selected value in the parent view's `values` dictionary
        self.parent_view.values[self.role] = int(self.values[0])

        # Concatenate the role preferences into a single string
        role_pref_string = ''.join(str(self.parent_view.values[role]) for role in ["Top", "Jungle", "Mid", "Bot", "Support"])

        # Acknowledge interaction
        await interaction.response.defer()  # Acknowledge the interaction without updating the message

        # Update the role preferences embed
        await self.parent_view.update_embed_message(interaction)


@tree.command(
    name='rolepreference',
    description="Set your role preferences for matchmaking.",
    guild=discord.Object(GUILD)
)
async def rolepreference(interaction: discord.Interaction):
    member = interaction.user

    # Check if the user has the Player or Volunteer role
    if not any(role.name in ["Player", "Volunteer"] for role in member.roles):
        await interaction.response.send_message("You must have the Player or Volunteer role to set role preferences.", ephemeral=True)
        return

#Player class.
class participant():

    def __init__(self,playerName,playerRank,topPreference,jgPreference,midPreference,adcPreference,supPreference):

        self.name = playerName
        self.rank = playerRank
        self.baseQualityPoints = RANK_VALUES[self.rank]
        self.topPreference = topPreference
        self.topQP = round((self.baseQualityPoints * ROLE_MODS[self.rank + str(self.topPreference)]) + random.uniform(-randomness, randomness),2)
        self.jgPreference = jgPreference
        self.jgQP = round((self.baseQualityPoints * ROLE_MODS[self.rank + str(self.jgPreference)]) + random.uniform(-randomness, randomness),2)
        self.midPreference = midPreference
        self.midQP = round((self.baseQualityPoints * ROLE_MODS[self.rank + str(self.midPreference)]) + random.uniform(-randomness, randomness),2)
        self.adcPreference = adcPreference
        self.adcQP = round((self.baseQualityPoints * ROLE_MODS[self.rank + str(self.adcPreference)]) + random.uniform(-randomness, randomness),2)
        self.supPreference = supPreference
        self.supQP = round((self.baseQualityPoints * ROLE_MODS[self.rank + str(self.supPreference)]) + random.uniform(-randomness, randomness),2)
        self.QPList = [self.topQP,self.jgQP,self.midQP,self.adcQP,self.supQP]
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
 
#Team class.
class team():

    def __init__(self,playerList):

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
        self.playerListNames = [self.topLaner.name,self.jgLaner.name,self.midLaner.name,self.adcLaner.name,self.supLaner.name]
        self.teamTotalQP = round(playerList[0].currentQP + playerList[1].currentQP + playerList[2].currentQP + playerList[3].currentQP + playerList[4].currentQP,2)
        self.averageTeamQP = round(self.teamTotalQP / len(self.playerList),2)
        
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
        for x in range(0,len(self.playerList)):

            total += self.playerList[x].currentQP

        self.teamTotalQP = round((total),2)
        self.averageTeamQP = round(self.teamTotalQP / len(self.playerList),2)

    def assignRole(self,player,role):

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

    def calculatePotentialQPChange(self,player1,player2):

        player1CurrentQP = player1.currentQP
        player1NewRole = player2.currentRole
        player2CurrentQP = player2.currentQP  
        player2NewRole = player1.currentRole

        match player1NewRole:

            case "top":

                player1PotentialQP = player1.topQP

            case "jg":

                player1PotentialQP = player1.jgQP

            case "mid":

                player1PotentialQP = player1.midQP

            case "adc":

                player1PotentialQP = player1.adcQP

            case "sup":

                player1PotentialQP = player1.supQP

        match player2NewRole:

            case "top":

                player2PotentialQP = player2.topQP

            case "jg":

                player2PotentialQP = player2.jgQP

            case "mid":

                player2PotentialQP = player2.midQP

            case "adc":

                player2PotentialQP = player2.adcQP

            case "sup":

                player2PotentialQP = player2.supQP

        player1Change = player1PotentialQP - player1CurrentQP
        player2Change = player2PotentialQP - player2CurrentQP
        
        # Positive total change here implies the change improves the teams QP.
        # Negative implies it reduce team QP

        totalChange = player1Change + player2Change

        return totalChange        

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

        all_potential_role_assignments = list(itertools.permutations(range(1,6)))
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

    def checkScore(self, potentialAssignment):
        
        total_score = 0
        self.playerList = [self.topLaner, self.jgLaner, self.midLaner, self.adcLaner, self.supLaner]

        for z in range(0,len(potentialAssignment)):

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
        idealTeam = [0,0,0,0,0]

        for x in range(0,len(idealRoles)):

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
        
def formatList(playerList):

    returnableList = []

    for x in range(0,len(playerList),7):

        participantToAdd = participant(playerList[x],playerList[x + 1],playerList[x + 2],playerList[x + 3],playerList[x + 4],playerList[x + 5],playerList[x + 6])
        print("Adding the following participant to the list of players: " + str(participantToAdd.name))
        returnableList.append(participantToAdd)   

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

    if player1 in [team1.topLaner,team1.jgLaner,team1.midLaner,team1.adcLaner,team1.supLaner]: # They need to go to team 2

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

def matchmake(playerList): # Start by randomizing teams and calculating QP. Then, compare to absoluteMaximumDifference. If 
# diff is large, swap best and worst players. If diff is above threshold but not as large, un-optimize roles. Continue
# un-optimizing roles until it's no longer good (and keep last known good).

    keepLooping = True

    while keepLooping == True:

        random.shuffle(playerList)

        team1 = []
        team2 = []

        for x in range(0,len(playerList),2):

            print("Adding this player to Team 1: " + str(playerList[x].name))
            team1.append(playerList[x])
            print("Adding this player to Team 2: " + str(playerList[x + 1].name))
            team2.append(playerList[x+ 1])

        intermediateTeam1 = team(team1)
        intermediateTeam1.updateTeamQP()

        intermediateTeam2 = team(team2)
        intermediateTeam2.updateTeamQP()

        intermediateTeam1.reinstateIdealizedRoles()
        intermediateTeam2.reinstateIdealizedRoles()

        needsOptimization = True
        numRuns = 0

        while needsOptimization == True: # Attempt to more balance teams       

            if numRuns > 50:

                break

        # Case 1----------------------------------------------------------------------------------------

            if (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) < 0 and abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > 75: # Case 1: A negative difference that is larger than an arbirary large number means that team 2 is better than team 1 and teams are too unbalanced
                               
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

                swapPlayersToDifferentTeam(intermediateTeam1.findLowestQP(), intermediateTeam1, intermediateTeam2.findHighestQP(), intermediateTeam2)

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

                if (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) < 0 and abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference:

                    needsOptimization = True  
                    print("Still needs work! Case 1 complete")
                    print("Current QP difference is: ")
                    print(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP)

                    numRuns += 1
                    
                else:

                    needsOptimization = False
                    print("Might be relatively balanced! Case 1 complete")
                    print("Current QP difference is: ")
                    print(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP)

                    numRuns += 1
                

        # Case 1----------------------------------------------------------------------------------------

        # Case 2----------------------------------------------------------------------------------------
    
            elif (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > 0 and abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > 75: # Case 2: A positive difference that is larger than an arbitrary large number means that team 1 is better than team 2 and teams are too unbalanced

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

                swapPlayersToDifferentTeam(intermediateTeam1.findHighestQP(), intermediateTeam1, intermediateTeam2.findLowestQP(), intermediateTeam2)

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

                if (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > 0 and abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference:

                    needsOptimization = True  
                    print("Still needs work! Case 2 complete")
                    print("Current QP difference is: ")
                    print(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP)

                    numRuns += 1
                    
                else:

                    needsOptimization = False
                    print("Might be relatively balanced! Case 2 complete")
                    print("Current QP difference is: ")
                    print(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP)

                    numRuns += 1
                

        # Case 2----------------------------------------------------------------------------------------

        # Case 3----------------------------------------------------------------------------------------

            elif (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) < 0 and abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference: # Case 3: A negative difference that is larger than the maximum but smaller than an arbitrary large number means that team 2 is better than team 1 and teams are only slightly unbalanced.

                print("Case 3 is happening")
                print("Total difference before making a swap is: ")
                print(abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))

                
                tries = 0
                keepLooping = True
                while keepLooping == True:

                    randomPlayerList = [0,1,2,3,4]
                    randomChoice1 = random.choice(randomPlayerList)
                    randomPlayer1 = intermediateTeam2.playerList[randomChoice1]
                    randomPlayerList.remove(randomChoice1)
                    randomChoice2 = random.choice(randomPlayerList)
                    randomPlayer2 = intermediateTeam2.playerList[randomChoice2]
                    change = intermediateTeam2.calculatePotentialQPChange(randomPlayer1,randomPlayer2)  
                    print("This is the projected change by swapping")
                    print(change)

                    if change < 0 and tries < 50: # If the change reduces the QP of the team, which is what we want

                        tries += 1
                        swapPlayerRolesSameTeam(intermediateTeam2,randomPlayer1,randomPlayer2)
                        print("Made a swap!")
                        print("Total difference after making a swap is: ")
                        print((intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))
                        
                        if abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference and tries < 50:

                            keepLooping = True

                        else:

                            keepLooping = False

                    else:

                        tries += 1
                        keepLooping = False         

        # Case 3----------------------------------------------------------------------------------------

        # Case 4----------------------------------------------------------------------------------------

            elif (intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > 0 and abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference: # Case 4: A positive difference that is larger than the maximum but smaller than an arbitrary large number means that team 1 is better than team 2 and teams are only slightly unbalanced.

                print("Case 4 is happening")
                print("Total difference before making a swap is: ")
                print((intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))

                
                tries = 0
                keepLooping = True
                while keepLooping == True:

                    randomPlayerList = [0,1,2,3,4]
                    randomChoice1 = random.choice(randomPlayerList)
                    randomPlayer1 = intermediateTeam1.playerList[randomChoice1]
                    randomPlayerList.remove(randomChoice1)
                    randomChoice2 = random.choice(randomPlayerList)
                    randomPlayer2 = intermediateTeam1.playerList[randomChoice2]
                    change = intermediateTeam1.calculatePotentialQPChange(randomPlayer1,randomPlayer2)   
                    print("This is the projected change by swapping")
                    print(change)

                    if change < 0 and tries < 50: # If the change reduces the QP of the team, which is what we want

                        tries += 1
                        swapPlayerRolesSameTeam(intermediateTeam1,randomPlayer1,randomPlayer2)
                        print("Made a swap!")
                        print("Total difference after making a swap is: ")
                        print((intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP))
                        
                        if abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference and tries < 50:

                            keepLooping = True

                        else:

                            keepLooping = False

                    else:

                        tries += 1
                        keepLooping = False     
                

        # Case 4----------------------------------------------------------------------------------------

        # Case 5----------------------------------------------------------------------------------------

            else: # Case 5: The difference should now be below AbsoluteMaximumValue, so teams are quite balanced.
                
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
        # TODO

        if abs(intermediateTeam1.teamTotalQP - intermediateTeam2.teamTotalQP) > absoluteMaximumDifference:

            print("Couldnt make it work, looping through from the beginning.")
            keepLooping = True

    returnableList = []
    returnableList.append(intermediateTeam1)
    returnableList.append(intermediateTeam2)
    return returnableList

class lobby:
    def __init__(self):

        team1 = []
        team2 = [] 

        currentTourneyID = tourneyDB.col_values(1)[-1]
        previousGameID = gameDB.col_values(1)[-1]
        currentGameID = ""

        if previousGameID.isnumeric() == True:

            currentGameID = int(previousGameID) + 1
        else:

            currentGameID = 1

        # Game is created, so write to database. Will need for buttons to work later.

        gameDB.update_acell('A' + str(currentGameID + 1) , str(currentGameID))
        gameDB.update_acell('B' + str(currentGameID + 1) , str(currentTourneyID))

        # This part just creates random teams, no real matchmaking yet.
        # TODO - add working matchmaking

        players = playerAPIRequest2.json()['values']
        players.pop(0)

        finalPlayerList = []
        intermediateList = []

        for person in players:

            person.pop(0)
            participantToAdd = person[:7]

            for x in range(0,7):

                intermediateList.append(participantToAdd[x])


        finalPlayerList = intermediateList[:70]
     
        self.playerList = finalPlayerList

        matchmakingList = formatList(finalPlayerList)
        bothTeams = matchmake(matchmakingList)

        print("")
        print(str(bothTeams[0].topLaner.name) + " is player 1 for team 1. They will be playing Top.")
        print(str(bothTeams[0].jgLaner.name) + " is player 2 for team 1. They will be playing JG.")
        print(str(bothTeams[0].midLaner.name) + " is player 3 for team 1. They will be playing Mid.")
        print(str(bothTeams[0].adcLaner.name) + " is player 4 for team 1. They will be playing ADC.")
        print(str(bothTeams[0].supLaner.name) + " is player 5 for team 1. They will be playing Sup.")

        print("")
        print(str(bothTeams[1].topLaner.name) + " is player 1 for team 2. They will be playing Top.")
        print(str(bothTeams[1].jgLaner.name) + " is player 2 for team 2. They will be playing JG.")
        print(str(bothTeams[1].midLaner.name) + " is player 3 for team 2. They will be playing Mid.")
        print(str(bothTeams[1].adcLaner.name) + " is player 4 for team 2. They will be playing ADC.")
        print(str(bothTeams[1].supLaner.name) + " is player 5 for team 2. They will be playing Sup.")
        
        team1 = bothTeams[0]
        team2 = bothTeams[1]
            
        # Write players to database

        gameDB.update_acell('E' + str(currentGameID + 1) + 'N' + str(currentGameID + 1), str(currentGameID))

        gameDB.batch_update([{
    'range': 'E' + str(currentGameID + 1) + ':N' + str(currentGameID + 1),
    'values': [[str(team1.topLaner.name), str(team1.jgLaner.name),str(team1.midLaner.name),str(team1.adcLaner.name),str(team1.supLaner.name),str(team2.topLaner.name),str(team2.jgLaner.name),str(team2.midLaner.name),str(team2.adcLaner.name),str(team2.supLaner.name)]],
}])
 
def declareWinner(self,team,gameNumber):
        
    return team

def declareMVP(self,gameNumber):

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
        DBFormula = tourneyDB.get("B2" , value_render_option=ValueRenderOption.formula)
        tourneyDB.update_acell('A' + str(currentTourneyID + 1) , str(currentTourneyID))
        tourneyDB.update_acell('B' + str(currentTourneyID + 1) , '=COUNTIF(GameDatabase!B:B,"="&A' +  str(currentTourneyID + 1) + ')')

#Check-in button class for checking in to tournaments.
class CheckinButtons(discord.ui.View):
    # timeout after 900 seconds = end of 15-minute check-in period
    def __init__(self, *, timeout = 900):
        super().__init__(timeout = timeout)
    """
    This button is a green button that is called check in
    When this button is pulled up, it will show the text "Check-In"

    The following output when clicking the button is to be expected:
    If the user already has the player role, it means that they are already checked in.
    If the user doesn't have the player role, it will give them the player role. 
    """
    @discord.ui.button(
            label = "Check-In",
            style = discord.ButtonStyle.green)
    async def checkin(self, interaction: discord.Interaction, button: discord.ui.Button):

        player = get(interaction.guild.roles, name = 'Player')
        member = interaction.user

        if player in member.roles:
            await interaction.response.edit_message(view = self)
            await interaction.followup.send('You have already checked in.', ephemeral=True)
            return "Is already checked in"
        await member.add_roles(player)
        await interaction.response.edit_message(view = self)
        await interaction.followup.send('You have checked in!', ephemeral = True)
        return "Checked in"        

    """
    This button is the leave button. It is used for if the player checked in but has to leave
    The following output is to be expected:

    If the user has the player role, it will remove it and tell the player that it has been removed
    If the user does not have the player role, it will tell them to check in first.
    """
    @discord.ui.button(
            label = "Leave",
            style = discord.ButtonStyle.red,
            custom_id = 'experimentingHere')
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):

        player = get(interaction.guild.roles, name = 'Player')
        member = interaction.user

        if player in member.roles:
            await member.remove_roles(player)
            await interaction.response.edit_message(view = self)
            await interaction.followup.send('Sorry to see you go.', ephemeral = True)
            return "Role Removed"
        await interaction.response.edit_message(view = self)
        await interaction.followup.send('You have not checked in. Please checkin first', ephemeral = True)
        return "Did not check in yet"

class volunteerButtons(discord.ui.View):
    # timeout after 900 seconds = end of 15-minute volunteer period
    def __init__(self, *, timeout = 900):
        super().__init__(timeout = timeout)
    """
    This button is a green button that is called check in
    When this button is pulled up, it will show the text "Volunteer"

    The following output when clicking the button is to be expected:
    If the user already has the volunteer role, it means that they are already volunteered.
    If the user doesn't have the volunteer role, it will give them the volunteer role. 
    """
    @discord.ui.button(
            label = "Volunteer",
            style = discord.ButtonStyle.green)
    async def checkin(self, interaction: discord.Interaction, button: discord.ui.Button):

        player = get(interaction.guild.roles, name = 'Player')
        volunteer = get(interaction.guild.roles, name = 'Volunteer')
        member = interaction.user

        if player in member.roles:
            await member.remove_roles(player)
        if volunteer in member.roles:
            await interaction.response.edit_message(view = self)
            await interaction.followup.send('You have already volunteered to sit out, if you wish to rejoin click rejoin.', ephemeral=True)
            return "Is already checked in"
        await member.add_roles(volunteer)
        await interaction.response.edit_message(view = self)
        await interaction.followup.send('You have volunteered to sit out!', ephemeral = True)
        return "Checked in"        

    """
    This button is the leave button. It is used for if the player who has volunteer wants to rejoin
    The following output is to be expected:

    If the user has the player role, it will remove it and tell the player that it has been removed
    If the user does not have the volunteer role, it will tell them to volunteer first.
    """
    @discord.ui.button(
            label = "Rejoin",
            style = discord.ButtonStyle.red)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        player = get(interaction.guild.roles, name = 'Player')
        volunteer = get(interaction.guild.roles, name = 'Volunteer')
        member = interaction.user

        if volunteer in member.roles:
            await member.remove_roles(volunteer)
            await member.add_roles(player)
            await interaction.response.edit_message(view = self)
            await interaction.followup.send('Welcome back in!', ephemeral = True)
            return "Role Removed"
        await interaction.response.edit_message(view = self)
        await interaction.followup.send('You have not volunteered to sit out, please volunteer to sit out first.', ephemeral = True)
        return "Did not check in yet"

class winnerButtons(discord.ui.View):
    # timeout after 900 seconds = end of 15-minute volunteer period
    def __init__(self, *, timeout = 900):
        super().__init__(timeout = timeout)

    winnerVariable = "None Entered"

    @discord.ui.button(
            label = "Blue Team",
            style = discord.ButtonStyle.blurple)
    async def winnerBlue(self, interaction: discord.Interaction, button: discord.ui.Button):

        member = interaction.user
        await interaction.response.edit_message(view = self)
        await interaction.followup.send('You have selected the Blue team as the winner!', ephemeral = True)
        winnerVariable = "Blue"
        return "Blue"        

    @discord.ui.button(
            label = "Red Team",
            style = discord.ButtonStyle.red)
    async def winnerRed(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        member = interaction.user
        await interaction.response.edit_message(view = self)
        await interaction.followup.send('You have selected the Red team as the winner!', ephemeral = True)
        winnerVariable = "Red"
        return "Red"   

    @discord.ui.button(
            label = "Confirm",
            style = discord.ButtonStyle.grey)
    async def commitToDB(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        member = interaction.user
        await interaction.response.edit_message(view = self)
        await interaction.followup.send('Committing to DB', ephemeral = True)

        #TODO Write to Database


        #Command to start check-in
@tree.command(
    name = 'checkin',
    description = 'Initiate tournament check-in',
    guild = discord.Object(GUILD))
async def checkin(interaction: discord.Interaction):
    player = interaction.user
    checkinStart = time.time()
    checkinFinish = time.time() + CHECKIN_TIME
    totalMinutes = round(round(CHECKIN_TIME)//60)
    totalSeconds = round(round(CHECKIN_TIME)%60)

    # Upon checking in, update the player's Discord username in the database if it has been changed
    #await update_username(player)
    
    view = CheckinButtons()
    await interaction.response.send_message('Check-in for the tournament has been started by ' + str(player) + '! You have ' + str(totalMinutes) + ' minutes and ' + str(totalSeconds) + ' seconds to check in. This tournament check-in started at <t:' + str(round(checkinStart)) + ':T>', view = view)
    
    #Wait for tournament time (900 seconds?)

    newTournament = Tournament()

#Command to start check for volunteers to sit out of a match.
@tree.command(
    name = 'sitout',
    description = 'Initiate check for volunteers to sit out from a match',
    guild = discord.Object(GUILD))
async def sitout(interaction: discord.Interaction):
    player = interaction.user
    
    # Upon volunteering to sit out for a round, update the player's Discord username in the database if it has been changed.
    # This may be redundant if users are eventually restricted from volunteering before they've checked in.
    #await update_username(player)
    
    view = volunteerButtons()
    await interaction.response.send_message('The Volunteer check has started! You have 15 minutes to volunteer if you wish to sit out.', view = view)
  
    
@tree.command(
    name = 'create_game',
    description = 'Create a lobby of 10 players after enough have checked in',
    guild = discord.Object(GUILD))
async def create_game(interaction: discord.Interaction):
    player = interaction.user
    newLobby = lobby()  
    await interaction.response.send_message('Creating game...')




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

# Entry point to run async setup before bot starts
if __name__ == '__main__':
    try:
        # This line of code starts the bot.
        client.run(TOKEN)
    finally:
        asyncio.run(close_session())
