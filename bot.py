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

# Paths for spreadsheet and SQLite database on the bot host's device
SPREADSHEET_PATH = os.path.abspath(os.getenv('SPREADSHEET_PATH'))
DB_PATH = os.getenv('DB_PATH')

WELCOME_CHANNEL_ID = os.getenv('WELCOME_CHANNEL_ID')

TIER_WEIGHT = float(os.getenv('TIER_WEIGHT', 0.7))  # Default value of 0.7 if not specified in .env
ROLE_PREFERENCE_WEIGHT = float(os.getenv('ROLE_PREFERENCE_WEIGHT', 0.3))  # Default value of 0.3 if not specified in .env
TIER_GROUPS = os.getenv('TIER_GROUPS', 'UNRANKED,IRON,BRONZE,SILVER:GOLD,PLATINUM:EMERALD:DIAMOND:MASTER:GRANDMASTER:CHALLENGER') # Setting default tier configuration if left blank in .env
CHECKIN_TIME = os.getenv('CHECKIN_TIME')
CHECKIN_TIME = int(CHECKIN_TIME)

ROLE_ORDER = ["top", "jungle", "mid", "adc(bot)", "support"]

# # Adjust event loop policy for Windows
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
# Semaphore to limit the number of concurrent API requests to Riot (added to address connection errors pulling player rank with /stats)
api_semaphore = asyncio.Semaphore(5)  # Limit concurrent requests to 5

session = None

"""

# This is for Google Sheets OAuth2 code
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SAMPLE_SPREADSHEET_ID = GSHEETS_ID
SAMPLE_RANGE_NAME = "TournamentDatabase!A2:E"
creds = None
if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES
    )
    creds = flow.run_local_server(port=0)
# Save the credentials for the next run
with open("token.json", "w") as token:
    token.write(creds.to_json())

service = build("sheets", "v4", credentials=creds)
sheet = service.spreadsheets()
result = (
    sheet.values()
    .get(spreadsheetId=SAMPLE_SPREADSHEET_ID, range=SAMPLE_RANGE_NAME)
    .execute()
)
values = result.get("values", [])

print("Name, Major:")
for row in values:
    # Print columns A and E, which correspond to indices 0 and 4.
    print(row)

"""

# Set up gspread for access by functions

gc = gspread.service_account(filename='C:\\Users\\Jacob\\source\\repos\\KSU Capstone Project\\KSU Capstone Project\\gspread_service_account.json')
googleWorkbook = gc.open_by_key(GSHEETS_ID)

tourneyDB = googleWorkbook.worksheet('TournamentDatabase')
gameDB = googleWorkbook.worksheet('GameDatabase')
playerDB = googleWorkbook.worksheet('PlayerDatabase')


# MM Testing----------------------------------------------------------------------

kidusSheet = gc.open_by_key('1PTSCaGA8kza90SWagWrnrvAhlb5EJyh04k5jQFvVam4').worksheet('Test2')

ROLE_ORDER = ["Top", "Jungle", "Mid", "ADC", "Support"]

RANK_VALUES = {
    "Challenger": 10, "Grandmaster": 9, "Master": 8,
    "Diamond": 7, "emerald": 6, "Platinum": 5, "Gold": 4,  #Kidus has the emerald in lowercase in the google sheets so ensure it is lowercase in integration or update to make them all case insensitive
    "Silver": 3, "Bronze": 2, "Iron": 1, "Unranked": 0
}

RANK_GROUPS = [
    {10, 9, 8},# Challenger, Grandmaster, Master
    {8},         #Master
    {7},         # Diamond
    {6, 5},      # Emerald, Platinum
    {5, 4},      # Platinum, Gold
    {3, 2, 1}    # Silver, Bronze, Iron
]

def get_players_sheet():
    """Fetch player data from Google Sheets."""
    data = kidusSheet.get_all_records()
    players = []

    for row in data:
        rank = row.get("Rank Tier", "Unranked").strip()
        last_rank = row.get("Last Season Rank", "Unranked").strip()
        rank_value = RANK_VALUES.get(rank, RANK_VALUES.get(last_rank, 0))

        roles = [role for role in ROLE_ORDER if row.get(f"Role {ROLE_ORDER.index(role) + 1} ({role})", "").strip().lower() == "yes"]
        if not roles:
            roles.append(random.choice(ROLE_ORDER))

        players.append({
            "name": row.get("Player Name", "").strip(),
            "rank": rank,
            "rank_value": rank_value,
            "roles": roles,
        })
    return players


def assign_roles(players):
    """Distribute players into roles, ensuring balance and no duplicate players."""
    assigned_roles = {role: [] for role in ROLE_ORDER}
    random.shuffle(players)

    for player in players:
        for role in player["roles"]:
            if len(assigned_roles[role]) < 2:
                assigned_roles[role].append(player)
                break
    return assigned_roles


def valid_team_match(team1, team2):
    """Check if teams meet rank restrictions with fallback logic."""
    team1_ranks = {p["rank_value"] for p in team1}
    team2_ranks = {p["rank_value"] for p in team2}
    combined_ranks = team1_ranks | team2_ranks  # Merge both teams' ranks into one set(used for fallback ranks(i.e not enough emerald players so plat can play))

    # Bronze, Silver, and Iron can always match together
    if combined_ranks.issubset({3, 2, 1}):
        return True  

    #  Challenger (10) & Grandmaster (9) can play together
    if combined_ranks.issubset({10, 9}):
        return True  

    #  If there aren’t enough, they can play with Masters (8) ONLY
    if combined_ranks.issubset({10, 9, 8}):
        return True  

    #  High tiers (10, 9, 8) should NEVER match with 7 (Diamond) or below
    if any(r in combined_ranks for r in {10, 9, 8}) and any(r in combined_ranks for r in {7, 6, 5, 4, 3, 2, 1}):
        return False  

    #  Platinum (5) can play with Emerald (6) if Gold (4) is NOT present
    if 5 in combined_ranks and 6 in combined_ranks and 4 not in combined_ranks:
        return True  

    #  Platinum (5) can play with Gold (4) if Emerald (6) is NOT present
    if 5 in combined_ranks and 4 in combined_ranks and 6 not in combined_ranks:
        return True  

    #  Prevent Gold (4) and Emerald (6) from playing together
    if 4 in combined_ranks and 6 in combined_ranks:
        return False  

    # If both teams are within the same defined rank group, allow match
    for group in RANK_GROUPS:
        if team1_ranks.issubset(group) and team2_ranks.issubset(group):
            return True  

    return False  



def find_player_for_role(unassigned, role, rank_group, fallback_group=None):
    """Find a player for a role within a specific rank group, falling back only to the highest adjacent rank."""
    for player in unassigned:
        if player["rank_value"] in rank_group:
            player["role"] = role
            unassigned.remove(player)
            return player
    if fallback_group:
        for player in unassigned:
            if player["rank_value"] in fallback_group:
                player["role"] = role
                unassigned.remove(player)
                return player
    return None


def balance_rank_distribution(team1, team2):
    """Ensure higher-ranked players are evenly distributed across teams, 
       but allow a max difference of 1 for any rank group."""
    
    # Group players by rank
    team1_ranks = {p["rank_value"]: [] for p in team1}
    team2_ranks = {p["rank_value"]: [] for p in team2}

    for p in team1:
        team1_ranks[p["rank_value"]].append(p)
    for p in team2:
        team2_ranks[p["rank_value"]].append(p)

    # Identify unbalanced ranks
    for rank in set(team1_ranks.keys()) | set(team2_ranks.keys()):  
        count1 = len(team1_ranks.get(rank, []))
        count2 = len(team2_ranks.get(rank, []))

        # Allows a difference of 1 (e.g., 2 vs. 3 Emeralds is fine)
        if abs(count1 - count2) <= 1:
            continue  

        # swap players only if the difference is greater than 1(i.e 4 emerald 1 plat vs 1 emerald 4 plat )
        while abs(count1 - count2) > 1:
            if count1 > count2:
                # Move a player from team1 → team2
                swap_player = team1_ranks[rank].pop(0)  
                team1.remove(swap_player)
                team2.append(swap_player)
                team2_ranks[rank].append(swap_player)
            else:
                # Move a player from team2 → team1
                swap_player = team2_ranks[rank].pop(0)  
                team2.remove(swap_player)
                team1.append(swap_player)
                team1_ranks[rank].append(swap_player)

            # Update counts after swap
            count1 = len(team1_ranks.get(rank, []))
            count2 = len(team2_ranks.get(rank, []))

def fill_remaining_spots(team, other_team, unassigned):
    """Ensure each team has 5 players, prioritizing role preferences, while validating rank compatibility."""
    assigned_roles = {p["role"] for p in team}  # Tracks which roles are already filled
    
    while len(team) < 5 and unassigned:
        for player in unassigned:
            preferred_role = next((role for role in player["roles"] if role not in assigned_roles), None)
            if preferred_role and valid_team_match(team + [player], other_team):  
                player["role"] = preferred_role
                team.append(player)
                unassigned.remove(player)
                assigned_roles.add(preferred_role)
                break  
        if len(team) < 5:
            for player in unassigned:
                temp_team = team + [player]
                if valid_team_match(temp_team, other_team):  
                    available_roles = [role for role in ROLE_ORDER if role not in assigned_roles]
                    player["role"] = available_roles[0] if available_roles else "Fill"  # Assign any available role when there isn't anymore valid rank matchups regardless of preference(we could add this part for the volunteer queue)
                    team.append(player)
                    unassigned.remove(player)
                    assigned_roles.add(player["role"])
                    break  # Exit loop when roles are filled


def create_balanced_teams(attempts=0):
    """Create balanced teams ensuring rank restrictions, role assignment, and reshuffling if necessary."""
    players = get_players_sheet()
    if len(players) < 10:
        return "Error: Not enough players."

    assigned_roles = {role: [] for role in ROLE_ORDER}
    random.shuffle(players)

    for player in players:
        for role in player["roles"]:
            if len(assigned_roles[role]) < 2:
                assigned_roles[role].append(player)
                break

    team1, team2, used_players = [], [], set()
    team1_rank_group, team2_rank_group = set(), set()

    # Assign first player, who sets the rank group so players in wrong rank won't match
    for role in ROLE_ORDER:
        if len(assigned_roles[role]) == 2:
            p1, p2 = assigned_roles[role]

            team1_rank_group = {p1["rank_value"], p1["rank_value"] + 1}
            team2_rank_group = {p2["rank_value"], p2["rank_value"] + 1}

            team1.append({"name": p1["name"], "rank": p1["rank"], "rank_value": p1["rank_value"], "role": role})
            team2.append({"name": p2["name"], "rank": p2["rank"], "rank_value": p2["rank_value"], "role": role})
            used_players.update([p1["name"], p2["name"]])
            break

    unassigned = [p for p in players if p["name"] not in used_players]

    for team, rank_group in zip([team1, team2], [team1_rank_group, team2_rank_group]):
        for role in ROLE_ORDER:
            if not any(p["role"] == role for p in team):
                player = find_player_for_role(unassigned, role, rank_group)
                if player:
                    temp_team = team + [player]
                    if valid_team_match(team1, team2):
                        team.append(player)
                        used_players.add(player["name"])
                    else:
                        print(f"⚠ Skipping {player['name']} for {role} due to rank mismatch.")

    """This part of the code is to ensure 5 players and that if higher tiers are in a game it is equal amount on both teams(within 1 since it's 5v5)"""
    fill_remaining_spots(team1, team2, unassigned)
    fill_remaining_spots(team2, team1, unassigned)
    balance_rank_distribution(team1, team2)

    print("\n--- Final Team Check ---")
    for i, team in enumerate([team1, team2], 1):
        print(f"\nTeam {i}:")
        for player in team:
            print(f"{player['name']} - Rank: {player['rank']} (Value: {player['rank_value']}) - Role: {player['role']}")

    #Final validation
    if not valid_team_match(team1, team2):
        return "Error: Teams do not meet rank restrictions."

    return team1, team2

finalTest = create_balanced_teams()

# MM Testing---------------------------------------------------------------

# API Calls to get the current database informations. Running this now should cut down on the total number of required calls. 

tourneyAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/TournamentDatabase!A%3AD?majorDimension=COLUMNS&key=' + str(GSHEETS_API))
gameAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/GameDatabase!A%3AI?majorDimension=COLUMNS&key=' + str(GSHEETS_API)) 
playerAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/PlayerDatabase!A%3AI?majorDimension=COLUMNS&key=' + str(GSHEETS_API))

def refreshData():
    tourneyAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/TournamentDatabase!A%3AD?majorDimension=COLUMNS&key=' + str(GSHEETS_API))
    gameAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/GameDatabase!A%3AI?majorDimension=COLUMNS&key=' + str(GSHEETS_API)) 
    playerAPIRequest = requests.get('https://sheets.googleapis.com/v4/spreadsheets/' + str(GSHEETS_ID) + '/values/PlayerDatabase!A%3AI?majorDimension=COLUMNS&key=' + str(GSHEETS_API))

def rank_to_value(rank):
    rank_order = {
        "IRON": 1, "BRONZE": 2, "SILVER": 3, "GOLD": 4,
        "PLATINUM": 5, "DIAMOND": 6, "Emerald": 7, "MASTER": 8,
        "GRANDMASTER": 9, "CHALLENGER": 10
    }

    parts = rank.upper().split()
    base_rank = parts[0]
    tier = parts[1] if len(parts) > 1 else None

    base_value = rank_order.get(base_rank, 1)

    if base_rank in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
        return base_value * 10

    tier_values = {"I": 1, "II": 2, "III": 3, "IV": 4}
    tier_value = tier_values.get(tier, 4)

    return base_value * 10 + (5 - tier_value)

def can_match(team1, team2):
    if len(team1) != 5 or len(team2) != 5:
        return False, "Invalid teams: Each team must have exactly 5 players."
    
    team1_values = [rank_to_value(player.tier) for player in team1]
    team2_values = [rank_to_value(player.tier) for player in team2]
    
    if None in team1_values or None in team2_values:
        return "UNRANKED", "Admin must manually assign a rank before matching."
    
    base_ranks1 = [value // 10 for value in team1_values]
    base_ranks2 = [value // 10 for value in team2_values]
    
    # Enforce restrictions
    if any(br == 10 for br in base_ranks1) and any(br == 9 for br in base_ranks2):
        return True
    if any(br in [10, 9] for br in base_ranks1) and any(br == 8 for br in base_ranks2):
        return True
    if all(abs(br1 - br2) <= 1 and br1 >= 6 for br1, br2 in zip(base_ranks1, base_ranks2)):
        return True
    if all(br <= 3 for br in base_ranks1 + base_ranks2):
        return True
    if all(br in [4, 5] for br in base_ranks1 + base_ranks2):
        return True
    if all(br1 == br2 for br1, br2 in zip(base_ranks1, base_ranks2)):
        return True
    
    return False,

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

        # Update the database with the new role preferences
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE PlayerStats SET RolePreference = ? WHERE DiscordID = ?",
                (role_pref_string, str(self.parent_view.member_id))
            )
            await conn.commit()

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

    # Check if the user is in the database and retrieve their current preferences
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT RolePreference FROM PlayerStats WHERE DiscordID = ?", (str(member.id),)) as cursor:
            user_data = await cursor.fetchone()

        if not user_data:
            await interaction.response.send_message("You need to link your Riot ID using /link before setting role preferences.", ephemeral=True)
            return

    # Convert the existing role preferences into a dictionary
    role_pref_string = user_data[0]
    initial_values = {
        "Top": int(role_pref_string[0]),
        "Jungle": int(role_pref_string[1]),
        "Mid": int(role_pref_string[2]),
        "Bot": int(role_pref_string[3]),
        "Support": int(role_pref_string[4])
    }

    # Create the view with initial values and send initial response
    view = RolePreferenceView(member.id, initial_values)
    await interaction.response.send_message(
        "Please select your roles in order of preference, with 1 being the most preferred:", 
        view=view,
        ephemeral=True
    )



#Player class.
class Player:
    def __init__(self, discord_id, riot_id, rank, role_pref):
        self.discord_id = discord_id
        self.riot_id = riot_id
        self.rank = self.rank_to_value(rank)  # Convert rank to numerical value
        self.role_pref = role_pref  # List of preferred roles

    @staticmethod
    def rank_to_value(rank):
        rank_dict = {"IRON": 1, "BRONZE": 2, "SILVER": 3, "GOLD": 4, "PLATINUM": 5,
                     "DIAMOND": 6, "EMERALD": 7, "MASTER": 8, "GRANDMASTER": 9, "CHALLENGER": 10}
        return rank_dict.get(rank.upper(), 1)  # Default to IRON if rank is missing
        
    def calculate_weight(self, tier_weight, role_preference_weight):
        # Calculate weight based on tier, role preference, and a random factor
        base_weight = self.tier * tier_weight + (
            self.top_priority +
            self.jungle_priority +
            self.mid_priority +
            self.bot_priority +
            self.support_priority
        ) * role_preference_weight
        
        return base_weight * self.random_factor  # Add randomness to the final weight
 
#Team class.
class Team:
    def __init__(self):
        self.players = []
        self.skill_sum = 0

    def add_player(self, player):
        self.players.append(player)
        self.skill_sum += player.rank

    def average_rank(self):
        return self.skill_sum / len(self.players) if self.players else 0  

class lobby:
    def __init__(self,tourneyID):

        self.tourneyID = tourneyID
        team1 = []
        team2 = [] 

        previousGameID = gameAPIRequest.json()['values'][0][-1]

        if previousGameID.isnumeric() == True:

            self.gameID = int(previousGameID) + 1
        else:

            self.gameID = 1

        # Game is created, so write to database. Will need for buttons to work later.
        gameDB.update_acell('A' + str(self.gameID + 1) , str(self.gameID))
        gameDB.update_acell('B' + str(self.gameID + 1) , str(self.tourneyID))

        players = playerAPIRequest.json()['values'][0]
        players.pop(0)
        random.shuffle(players)
        self.playerList = players

        for x in range(0,5):
            team1.append(players[x])

        for x in range(6,11):
            team2.append(players[x])

        for x in range(len(team1)):
            print("")
            print(str(team1[x]) + " is player " + str(x + 1) + " for team 1.")

        for x in range(len(team2)):
            print("")
            print(str(team2[x]) + " is player " + str(x + 1) + " for team 2.")



    # Wait here for game to finish, somehow

    # What if we have a "create game" button, that will fire when the person wants it to go.
    # It can create a number of games based on volunteer size.
    # Write everything to database, then pull from database to get most up to date info.
    # Database is be-all-end-all authority. 
    # For example, when checkin is run, create database entry for the tournament ID. 
    # Then, when a game is created, the create game buttons will be tied to the latest entry as the tourney ID.
    # Then, when a game is finished, run the winner command with game number as input?
    # MVP command the same way
    # That way, create as many games as you want?

        
        

    def declareWinner(self,team):
        
        return team

    def declareMVP(self,winner):

        MVP = winner
        return MVP
        # End lobby

    
class Tournament:

    def __init__(self):

        self.gameList = [] 
        
        previousTourneyID = tourneyAPIRequest.json()['values'][0][-1]

        if previousTourneyID.isnumeric() == True:

            self.tourneyID = int(previousTourneyID) + 1

        else:

            self.tourneyID = 1
        
        # Write to tournament database
        DBFormula = tourneyDB.get("B2" , value_render_option=ValueRenderOption.formula)
        tourneyDB.update_acell('A' + str(self.tourneyID + 1) , str(self.tourneyID))
        tourneyDB.update_acell('B' + str(self.tourneyID + 1) , '=COUNTIF(GameDatabase!B:B,"="&A' +  str(self.tourneyID + 1) + ')')

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

        #Write to Database


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

    # Create X lobbies, potentially more than one, need to loop

    newLobby = lobby(newTournament.tourneyID)

    # Wait here for game to finish, somehow



# Create lobby command


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
