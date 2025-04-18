import requests
currentAPIKey = "putyourRiotAPITokenhere"

def getPlayerPUUID(playerName,region): # This function will get a player unique identifier (PUUID, a totally unique identifier across regions) based on the requested RiotID and Region.
    #  It will intake two string variables. Output is a JSON string with the player's PUUID , ingame name, and region.
    # When referencing a specific player (to get stats, etc.) this will almost always be the first step.

    requestURLBeginning = "https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/" # This is the beginning of our API request URL. We add 
    # parameters to it to build the entire request. We will add our player name, region, API key, and other text into the final URL string

    convertPlayerName = playerName.replace(" ","%20") # Since we are working with a URL, no spaces are allowed. Thus, we replace space characters with %20.
    # There may be other letters we have to account for as well.

    finalString = requestURLBeginning + convertPlayerName + "/" + region + "?api_key=" + currentAPIKey # This is our final string that is sent as a URL to Riot's API.

    r = requests.get(finalString) # Finally, we use the Python "Requests" package to send the URL and receive a response. 

    return (r.json()['puuid']) # This is how we parse the JSON file. See below for more information.

    # This is the API reference for this particular API call: https://developer.riotgames.com/apis#account-v1/GET_getByPuuid
    # The way the response object works is you take the JSON of the response using x.json(), then the resulting text created by Python is a bunch of nested dictionaries and lists.
    # In the above example's case, the first key in the key-value pair listing is 'puuid', the second is "gameName", and the third is "tagLine".
    # Since it is a dictionary, accessing the "key" in the dictionary will return the "value" from the pair. In this case, we access
    # the key 'PUUID', which returns the actual PUUID we want. If we had instead chosen gameName instead, it would return our summoner name.
    # Because there are only three results and none of them are nested, this one is easy.

def getPlayerEncryptedSummonerID(PUUID): # This function will convert a PUUID into an encrypted summoner name
    # This is needed for other functions that do not use PUUIDs.

    # Note: The API call used here returns 2 pieces of data - id and accountId.
    # "Encrpyted Summoner Name" is the same as "id" in this case and is the desired return value.

    requestURLBeginning = "https://na1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/" # This is the beginning of our API request URL. We add 
    # parameters to it to build the entire request. We will add our PUUID and API key to the string to complete it.

    finalString = requestURLBeginning + PUUID + "?api_key=" + currentAPIKey # This is our final string that is sent as a URL to Riot's API.

    r = requests.get(finalString) # Finally, we use the Python "Requests" package to send the URL and receive a response. 

    return (r.json()['id']) # This is how we parse the JSON file. See the "getPlayerPUUID" function for more information.

def getPlayerRank(encryptedSummonerName): # This function will get a player's rank. This includes tier and division.
    # This same API call can also pull a lot of other player data, such as wins, losses, LP, etc.
    # If we need to reduce our API calls or improve performance, re-using this data could be something to look at.
    # IMPORTANT NOTE: If a player does not have any ranked games for this season, the returned data
    # will be an empty list. 

    requestURLBeginning = "https://na1.api.riotgames.com//lol/league/v4/entries/by-summoner/" # This is the beginning of our API request URL. We add 
    # parameters to it to build the entire request. We will add our encrypted summoner name and API key to the string to complete it.

    finalString = requestURLBeginning + encryptedSummonerName + "?api_key=" + currentAPIKey # This is our final string that is sent as a URL to Riot's API.

    r = requests.get(finalString) # Finally, we use the Python "Requests" package to send the URL and receive a response. 

    if r.json() == []:

        return "This summoner has not played a ranked game this split."

    else:

        return (r.json()[0]['tier']) + " " + (r.json()[0]['rank'])

def testAPIs(playerName,region):

    myPUUID = getPlayerPUUID(playerName,region)
    myEncryptedSummonerID = getPlayerEncryptedSummonerID(myPUUID)
    myRank = getPlayerRank(myEncryptedSummonerID)
    print("Final results:")
    print("This persons IGN is:")
    print(playerName + "#" + region)
    print("This persons PUUID is:")
    print(myPUUID)
    print("This persons Encrypted Summoner Name is:")
    print(myEncryptedSummonerID)
    print("This persons rank is:")
    print(myRank)

myInput = input("Enter a summoner name to test! This should be in the format Summoner name#NA1 or summonername#XYZ ")
nameAndRegion = myInput.split("#")
testAPIs(nameAndRegion[0],nameAndRegion[1])
