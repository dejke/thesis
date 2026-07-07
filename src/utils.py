import json
import os
from dotenv import load_dotenv
from pathlib import Path


def set_up_cc():

    load_dotenv()
    target_path = Path(__file__).resolve().parent/'target'
    claude_path = Path(target_path,'.claude')
    cc_settings = None

    if 'settings.json' not in os.listdir(claude_path):

        with open(Path(claude_path,'claude_settings.json')) as f:
            cc_settings = json.load(f)
        
        cc_settings["env"]["ANTHROPIC_AUTH_TOKEN"] = os.getenv('API_KEY')

        with open(Path(claude_path,'settings.json'), "w") as f:
            json.dump(cc_settings,f,indent=4)
        
        print("Created .claude/settings.json and inserted API key")


