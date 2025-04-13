              KSU Esports Tournament Bot Guide

For Players

How to Use the Bot
The KSU Esports Tournament Bot is a Discord bot designed to manage in-house tournaments for games like League of Legends. It handles player registration, role preferences, matchmaking, MVP voting, and more. Here’s how you can get started:

1. **Join the Server**: Ensure you’re in the Discord server where the bot is active.
2. **Link Your Riot ID**: Before participating, you must link your Riot ID to your Discord account using the `/link` command. This is required for most bot features.
3. **Set Role Preferences**: Use `/rolepreference` to rank your preferred roles (Top, Jungle, Mid, ADC, Support) from 1 (most preferred) to 5 (least preferred).
4. **Check In**: When a tournament starts, use `/checkin` to join the matchmaking pool and confirm your role preferences.
5. **Participate**: Once teams are created with `/create_game`, play your match. After the game, vote for the MVP using `/mvp` if your team wins.
6. **View Stats**: Check your stats (wins, MVPs, etc.) with `/stats`.

Commands for Players
- **`/help`**: Displays a paginated help menu with all available commands.
- **`/link [riot_id]`**: Links your Riot ID (e.g., `SummonerName#Tagline`) to your Discord account. Required before other commands.
- **`/rolepreference`**: Opens a dropdown menu to set your role preferences for matchmaking.
- **`/checkin`**: Registers you for the current tournament and prompts for role preferences.
- **`/sitout`**: Volunteer to sit out of a match if there are too many players (15-minute window).
- **`/stats [player]`**: View your in-house stats (e.g., wins, MVPs, win rate).
- **`/mvp`**: Vote for the MVP from the winning team after a match.
- **`/view_toxicity [player_name]`**: Check a player’s toxicity points.

Useful Information
- **Role Preferences**: Ranking your roles helps the bot assign you to a position you’re comfortable with during matchmaking.
- **Check-In Period**: Tournaments have a 15-minute check-in window (configurable via `CHECKIN_TIME` in `.env`). Be prompt!
- **MVP Voting**: After a game, you can vote for an MVP from the winning team. A minimum of 3 votes is required (configurable via `MVP_VOTE_THRESHOLD`).
- **Toxicity Points**: Admins can track toxic behavior. Too many points might affect your participation (admin discretion).

For Admins

Installation Instructions (How to Add Bot to Server)
1. **Invite the Bot**:
   - Go to the Discord Developer Portal (https://discord.com/developers/applications).
   - Click create a new application 
   -Click the Installation tab and under “guild install” click the drop down and add a bot user.
   - Generate an invite link (under installation tab) with the following permissions: `bot` scope, `applications.commands` scope, and give the bot administrator permissions under “guild installs”.
   - Click on the three lines in the top left corner and click on Bot
   - Scroll down and ensure that the bot has presence, server members, and message contents intent checked on
   - Paste the bot invite link in your address bar to add the bot to your server.
   - Inside Discord ensure that you have developer mode enabled (user settings>Advanced)
2. **Set Up Environment**:
   - Clone the bot’s GitHub repository (assuming it’s hosted there).
   - Rename `.env.template` to `.env` and fill in the required variables (see Configuration Options below).
   - Install dependencies: `pip install -r requirements.txt` (ensure you have Python 3.8+ installed).
3. **Run the Bot**:
   - Run `python bot.py` from the command line in the bot’s directory.
   - Ensure the bot has a role higher than `Player` and `Volunteer` roles in the server’s role hierarchy.
  
Google Sheets Integration

The bot uses Google Sheets to store data related to players, games, and tournaments. Follow these steps to correctly configure and integrate Google Sheets:
Setting Up Google Cloud Credentials
To integrate Google Sheets with the bot, you must first create a Google Cloud Project and generate API credentials:
1. Create or Select a Project:
  - Visit Google Cloud Console.
  - Create a new project or select an existing one.
2.	Enable the Google Sheets API:
  - Navigate to APIs & Services → Library.
  - Search for and enable Google Sheets API.
3. Create Service Account Credentials:
  - Navigate to IAM & Admin → Service Accounts.
  - Click Create Service Account, assign a relevant name, and continue.
  - Assign the Editor or Viewer role
  - Click Done to complete creation.
  - After creation click on the service account and navigate to keys
  - Generate a new key (this will be your gspread_service_account file, ensure it is named that and saved in same folder as the bot)
**The email that is generated from the service account must be shared with the master Google sheets
4. Getting the GSheets API Key
  - Navigate back to the credentials screen and click create credential 
  - Create a new API Key
  - After generating, copy the displayed key and paste that into your env file.
5. Integrate JSON file with the Bot:
  - Move the downloaded JSON file to a secure location on your system.
  - Update the path in Bot2.py (line ~113) to reference the exact location of your JSON file (e.g., C:/path/to/your/gspread_service_account.json).

Riot API Key Steps
1. Sign Up on Riot Developer Portal
   Visit Riot Developer Portal at https://developer.riotgames.com/
   Log in using your Riot account credentials(create if you do not already have credentails)

2. Agree to the Terms:
   You must agree to Riot’s API Terms of Use before you can create an API key.

3. Create an Application:
   Once logged in, navigate to your developer dashboard.
   Create a new application (sometimes called a project)

4. Receive Your API Key
   After creating your application, Riot will provide you with an API key that you can use immediately for development and testing purposes.
    
API Key Lifespan and Usage
**Development API Key:
  -The default API key you obtain for development is typically valid for 24 hours
  -Sometimes the portal may automatically refresh the key. However, you must be prepared to generate a new key once the 24‑hour period expires if you continue     testing. (to get a more permanent key see Production API Key)


**Production API Key:
  -If you plan to deploy your application publicly or need higher rate limits, you’ll need to submit your application for review to obtain a production key.
  -Production keys generally have longer validity, though you must adhere to Riot’s guidelines and rate limits to maintain it.


.env Configuration Options
Edit the `.env` file with these variables in a plain text document or in an IDE (i.e Visual Studio code):
- **`BOT_TOKEN`**: Your Discord bot token from the Developer Portal (Bot tab> Reset Token>copy the token).
- **`GUILD_TOKEN`**: The ID of your Discord server (right-click Discord server > Copy ID).
- **`RIOT_API_KEY`**: Your Riot Games API key (See Riot API section).
- **`GSHEETS_API`**: Google Sheets API key (see Google Sheets integration).
- **`GSHEETS_ID`**: Google Spreadsheet ID for the main workbook(after "/d/" and before "/edit" in the url).
- **`GHSEETS_GAMEDB`**: Worksheet name for game data (default: `GameDatabase`).
- **`GSHEETS_PLAYERDB`**: Worksheet name for player data (default: `PlayerDatabase`).
- **`GSHEETS_TOURNAMENTDB`**: Worksheet name for tournament data (default: `TournamentDatabase`).
- **`WELCOME_CHANNEL_ID`**: Channel ID for welcome messages (optional).
- **`NOTIFICATION_CHANNEL_ID`**: Channel ID for game notifications.
- **`CHECKIN_TIME`**: Check-in duration in seconds (e.g., `900` for 15 minutes).
- **`TIER_WEIGHT`** (optional): Weight for tier in matchmaking (default: `0.7`).
- **`ROLE_PREFERENCE_WEIGHT`** (optional): Weight for role preference (default: `0.3`).
- **`TIER_GROUPS`** (optional): Tier groupings for matchmaking (default: `UNRANKED,IRON,BRONZE,SILVER:GOLD,PLATINUM:EMERALD:DIAMOND:MASTER:GRANDMASTER:CHALLENGER`).

Admin Commands
- **`/start_tournament`**: Starts a new tournament with a check-in period.
- **`/create_game`**: Creates a lobby with 10 players after check-in.
- **`/swap [player1] [player2]`**: Swaps two players between teams (updates Google Sheets).
- **`/gamewinner [winning_team]`**: Declares the winning team (e.g., `blue` or `red`) and starts MVP voting.
- **`/mvpresult`**: Finalizes MVP voting and updates the database.
- **`/toxicity [player_name]`**: Adds a toxicity point to a player.
- **`/remove_toxicity [player_name]`**: Removes a toxicity point from a player.
- **`/unlink [player]`**: Removes a player’s Riot ID and stats from the database.
- **`/confirm`**: Confirms the unlinking of a player (must follow `/unlink`).
- **`/resetdb`**: Resets player stats (except ID/rank/role preferences) to defaults (server owner only, requires confirmation).
- **`/setrole [member] [role]`**: Assigns `Player` or `Volunteer` role to a member.
- **`/listmembers`**: Lists all members with `Player` or `Volunteer` roles.

Known Bugs
1. **Riot API Rate Limiting**: The bot may hit rate limits with frequent `/link` or `/stats` usage. The `api_semaphore` limits concurrent requests to 5, but this might still fail under heavy load.
2. **Friendly Discord ID Issues**: The `get_friendly_discord_id` function may fail if a member’s discriminator isn’t available (e.g., due to Discord’s username changes). This could break commands like `/link` or `/checkin`.
3. **Matchmaking Imbalance**: The `matchmake` function might not always produce balanced teams if the player pool has extreme rank disparities (e.g., Challenger vs. Iron).
4. **Google Sheets Sync**: Updating Google Sheets can fail if the API quota is exceeded or credentials are invalid, causing data inconsistencies.
5. **MVP Voting Timeout**: The 3-minute timeout for `/mvp` voting might not persist across bot restarts.

Undeveloped Features
1. **`/win` Command**: Mentioned in `/help` but not implemented in the code.
2. **`/clear` Command**: Mentioned in `/help` but not implemented.
3. **`/players` Command**: Mentioned in `/help` but not implemented (use `/listmembers` instead).
4. **`/points` Command**: Mentioned in `/help` but not implemented.
5. **`/matchmake` Command**: Mentioned in `/help` but replaced by `/create_game`.
6. **`/votemvp` Command**: Mentioned in `/help` but replaced by `/mvp`.
7. **Role Preference Validation**: The bot doesn’t enforce that all 5 roles are ranked in `/rolepreference`.
8. **Tournament Progression**: The `Tournament` class doesn’t fully implement multi-game tournaments (e.g., brackets).

Potential Issues/Compatibility Problems
- **Python Version**: Requires Python 3.8+ due to `asyncio` and `discord.py` dependencies.
- **Windows Event Loop**: The bot adjusts the event loop policy for Windows, but this might cause issues on other OSes if not adjusted.
- **Google Sheets API**: Requires a `credentials.json` file and proper OAuth setup, which isn’t detailed in the code comments.
- **Discord API Changes**: The bot uses `discord.py` and might break with future Discord API updates (e.g., username changes affecting `friendly_discord_id`).
- **SSL Verification**: Disabling SSL (`ssl=False`) in API calls might pose security risks or fail on some networks.

Code Documentation
The code includes some comments, but not all methods/variables are fully documented. Below is a summary of key components:

Key Classes and Methods
- **`participant`**: Represents a player with rank, role preferences, and Quality Points (QP) for matchmaking.
  - `updatePlayerQP()`: Updates QP based on assigned role.
- **`team`**: Manages a 5-player team with role assignments and QP calculations.
  - `updateTeamQP()`: Recalculates team QP after changes.
  - `selfSortMatchmaking()`: Optimizes role assignments within the team.
- **`lobby`**: Creates a game with two teams and updates the database.  
- **`Tournament`**: Initializes a tournament and tracks its ID.
- **`matchmake(playerList)`**: Balances two teams based on QP and role preferences.
- **`safe_api_call(url, headers)`**: Handles Riot API requests with retries and timeouts.

Key Variables
- **`current_teams`**: Global dict storing the current teams (`team1` and `team2`).
- **`mvp_votes`**: Tracks MVP votes per lobby (`{lobby_id: {player_name: vote_count}}`).
- **`game_winners`**: Stores winning teams per lobby.
- **`RANK_VALUES`**: Maps ranks to base QP (e.g., `challenger: 100`, `unranked: 0`).
- **`ROLE_MODS`**: Adjusts QP based on rank and role preference (e.g., `challenger1: 1.30`).

Additional Admin Notes
- **Debugging**: Enable logging (`logging` module is imported but not used) to track errors.
- **Database Management**: Regularly back up Google Sheets to prevent data loss from API failures.
- **Scalability**: The bot assumes 10 players per game; adjust `matchmake` for different sizes if needed.
- **Security**: Store `.env` and `credentials.json` securely and avoid sharing them publicly.

---

This guide covers the essentials for players and admins. For further development, focus on fixing bugs (e.g., rate limiting, friendly ID issues) and implementing missing commands from the `/help` menu.
