import json
import os
from dotenv import load_dotenv
from pathlib import Path
import json


def parse_trajectory(traj_path):
    with open(traj_path) as f:
        traj = json.load(f)

    print(len(traj))
