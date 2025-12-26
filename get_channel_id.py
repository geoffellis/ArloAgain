import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SLACK_API_TOKEN = os.getenv("SLACK_API_TOKEN")

if not SLACK_API_TOKEN:
    print("Error: SLACK_API_TOKEN not found in .env file.")
    exit(1)

client = WebClient(token=SLACK_API_TOKEN)

try:
    print("Fetching channels...")
    # Call the conversations.list method using the WebClient
    response = client.conversations_list(types="public_channel,private_channel")
    
    print("\nAvailable Channels:")
    print("-" * 30)
    for channel in response["channels"]:
        print(f"Name: #{channel['name']}")
        print(f"ID:   {channel['id']}")
        print("-" * 30)
        
except SlackApiError as e:
    print(f"Error: {e}")
    print("Note: Ensure your Bot Token has the 'channels:read' scope.")