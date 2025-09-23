import os
import io
import math
import random
import time
import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
from PIL import Image, ImageDraw, ImageOps
from PIL import Image, ImageDraw, ImageFilter
import requests
import json
import re
from discord.ext import tasks
import aiohttp
from datetime import datetime, date, timezone, timedelta
from discord.ui import View, button
from PIL import ImageFilter
from PIL import ImageFont
import asyncio, time
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pathlib import Path


# Load .env file locally
load_dotenv()

# ===================== CONFIG =====================
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_BOT_TOKEN is not set in environment variables.")

DB_PATH = "/data/aaronjay.db"

# Project root directory (where your kick.py lives)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Images folder inside project
ASSETS_DIR = os.path.join(BASE_DIR, "images")
BOARD_IMAGE_PATH = os.path.join(ASSETS_DIR, "monopoly_board.png")
FONT_PATH = Path(__file__).parent / "fonts" / "Roboto-Bold.ttf"

# ===================== DISCORD BOT =====================
intents = discord.Intents.default()
intents.guilds = True
intents.presences = True
intents.message_content = True
intents.messages = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
# --- Testing cheat: force next roll ---
# maps guild_id -> (d1, d2) or guild_id -> total (we will store (d1,d2))
FORCED_NEXT_ROLL: Dict[int, Tuple[int, int]] = {}

def choose_dice_for_total(total: int) -> Optional[Tuple[int, int]]:
    """Return a random dice pair (d1,d2) with 1<=d<=6 that sums to total.
       If impossible, return None.
    """
    pairs = [(a,b) for a in range(1,7) for b in range(1,7) if a + b == total]
    if not pairs:
        return None
    return random.choice(pairs)

REDEEM_THRESHOLD = 10000
STARTING_COINS = 1500
REDEEM_CHANNEL_ID = 1419702679533523026  # 🔹 Change this to your announcement channel ID
ROLL_COOLDOWN_HOURS = 4
ROLL_COOLDOWN_SECONDS = ROLL_COOLDOWN_HOURS * 3600
TURN_DECISION_TIMEOUT = 60  # seconds for Buy/Pass
TAX_ANNOUNCE_CHANNEL_ID = 1419651787559796807
MONOPOLY_TRANSACTIONS_CHANNEL_ID = 1419653557774323763
GLOBAL_ROLL_LOCK = asyncio.Lock()
ADMIN_ID = 488015447417946151
GIVEAWAY_CHANNEL_ID = 1419644877712396339
ROLL_CHANNEL_ID = 1419646214848385106  # dedicated channel for monopoly rolls
ELIGIBLE_ROLE_ID = 1419593812501594195
WINNERS_COUNT = 5
LOG_CHANNEL_ID = 1419655999538597929
ALLOWED_CHANNEL_IDS = [1283632002322530314]

# Store the latest giveaway message so we can track reactions
current_giveaway_msg_id = None
ACTIVE_GIVEAWAYS = {}

# Colors
BOARD_BG = (18, 20, 24)
TILE_BG = (30, 33, 39)
TILE_BORDER = (80, 86, 100)
TEXT_COLOR = (235, 238, 245)
ACCENT = (120, 170, 255)
GROUP_COLORS = {
    "brown": (122, 88, 57),
    "lightblue": (148, 194, 255),
    "pink": (243, 168, 188),
    "orange": (255, 181, 94),
    "red": (255, 102, 102),
    "yellow": (255, 230, 102),
    "green": (120, 200, 120),
    "darkblue": (72, 118, 255),
    "provider": (160, 160, 160),  # railroads equivalent
    "utility": (200, 200, 200),
}

SLOT_BOARD: List[Dict] = [
    {"idx": 0, "type": "go", "name": "GO! Start Spinning", "image": "images/0.png"},
    {"idx": 1, "type": "property", "name": "RIP City", "price": 100, "rent": 15, "group": "brown", "image": "images/1.png"},
    {"idx": 2, "type": "chest", "name": "Bonus Chest", "image": "images/2.png"},
    {"idx": 3, "type": "property", "name": "The Dog House", "price": 90, "rent": 13.5, "group": "brown", "image": "images/3.png"},
    {"idx": 4, "type": "tax", "name": "Dead Spin Deduction", "amount": 200, "image": "images/4.png"},
    {"idx": 5, "type": "provider", "name": "Pragmatic Play", "price": 200, "rent": 25, "group": "provider", "image": "images/5.png"},
    {"idx": 6, "type": "property", "name": "Wild West Gold", "price": 130, "rent": 20.8, "group": "lightblue", "image": "images/6.png"},
    {"idx": 7, "type": "gamble", "name": "Bonus Gamble", "image": "images/7.png"},
    {"idx": 8, "type": "property", "name": "Chaos Crew", "price": 120, "rent": 18, "group": "lightblue", "image": "images/8.png"},
    {"idx": 9, "type": "property", "name": "Toshi Video Club", "price": 100, "rent": 15, "group": "lightblue", "image": "images/9.png"},

    {"idx": 10, "type": "jail", "name": "San Quentin Xways Jail", "image": "images/10.png"},
    {"idx": 11, "type": "property", "name": "Gates of Olympus", "price": 180, "rent": 30.6, "group": "pink", "image": "images/11.png"},
    {"idx": 12, "type": "utility", "name": "Money Train", "price": 150, "rent": 4, "group": "utility", "image": "images/12.png"},
    {"idx": 13, "type": "property", "name": "Zombie School Megaways", "price": 200, "rent": 30, "group": "pink", "image": "images/13.png"},
    {"idx": 14, "type": "property", "name": "Gemhalla", "price": 170, "rent": 27.2, "group": "pink", "image": "images/14.png"},
    {"idx": 15, "type": "provider", "name": "Hacksaw Gaming", "price": 200, "rent": 25, "group": "provider", "image": "images/15.png"},
    {"idx": 16, "type": "property", "name": "Deadwood R.I.P", "price": 190, "rent": 28.5, "group": "orange", "image": "images/16.png"},
    {"idx": 17, "type": "chest", "name": "Bonus Chest", "image": "images/17.png"},
    {"idx": 18, "type": "property", "name": "Gates of Hades", "price": 180, "rent": 27, "group": "orange", "image": "images/18.png"},
    {"idx": 19, "type": "property", "name": "Dragon's Domain", "price": 160, "rent": 24, "group": "orange", "image": "images/19.png"},

    {"idx": 20, "type": "free", "name": "Safe Spin Zone", "image": "images/20.png"},
    {"idx": 21, "type": "property", "name": "Club Tropicana", "price": 250, "rent": 45, "group": "red", "image": "images/21.png"},
    {"idx": 22, "type": "gamble", "name": "Bonus Gamble", "image": "images/22.png"},
    {"idx": 23, "type": "property", "name": "Gates of Valhalla", "price": 220, "rent": 33, "group": "red", "image": "images/23.png"},
    {"idx": 24, "type": "property", "name": "Sweet Kingdom", "price": 210, "rent": 33.6, "group": "red", "image": "images/24.png"},
    {"idx": 25, "type": "provider", "name": "NoLimit City", "price": 200, "rent": 25, "group": "provider", "image": "images/25.png"},
    {"idx": 26, "type": "property", "name": "Temple Tumble", "price": 200, "rent": 36, "group": "yellow", "image": "images/26.png"},
    {"idx": 27, "type": "property", "name": "Cursed Seas", "price": 220, "rent": 39.6, "group": "yellow", "image": "images/27.png"},
    {"idx": 28, "type": "utility", "name": "Mental", "price": 150, "rent": 4, "group": "utility", "image": "images/28.png"},
    {"idx": 29, "type": "property", "name": "Fighter Pit", "price": 240, "rent": 40.8, "group": "yellow", "image": "images/29.png"},

    {"idx": 30, "type": "gotojail", "name": "Go To San Quentin Jail", "image": "images/30.png"},
    {"idx": 31, "type": "property", "name": "Brick House Bonanza", "price": 320, "rent": 60.8, "group": "green", "image": "images/31.png"},
    {"idx": 32, "type": "property", "name": "Zombie Carnival", "price": 300, "rent": 51, "group": "green", "image": "images/32.png"},
    {"idx": 33, "type": "chest", "name": "Bonus Chest", "image": "images/33.png"},
    {"idx": 34, "type": "property", "name": "Devil's Crossroad", "price": 310, "rent": 55.8, "group": "green", "image": "images/34.png"},
    {"idx": 35, "type": "provider", "name": "B Gaming", "price": 200, "rent": 25, "group": "provider", "image": "images/35.png"},
    {"idx": 36, "type": "gamble", "name": "Bonus Gamble", "image": "images/36.png"},
    {"idx": 37, "type": "property", "name": "Clover Club", "price": 400, "rent": 80, "group": "darkblue", "image": "images/37.png"},
    {"idx": 38, "type": "tax", "name": "Scatter Tax", "amount": 100, "image": "images/38.png"},
    {"idx": 39, "type": "property", "name": "Space Zoo", "price": 350, "rent": 66.5, "group": "darkblue", "image": "images/39.png"},
]

PROPERTY_GROUPS: Dict[str, List[int]] = {}
for sq in SLOT_BOARD:
    if sq.get("type") in ("property", "provider", "utility"):
        grp = sq.get("group")
        PROPERTY_GROUPS.setdefault(grp, []).append(sq["idx"])

# Gamble / Chest cards (simple, flavorful)
GAMBLE_CARDS = [
    {
        "name": "Advance to GO — Starlight Princess",
        "desc": "To GO we go! Advance to GO — Starlight Princess grants you <:coin:1418612412885635206> $200 Coins!",
        "effect": "advance_go",
        "image": "images/starlight_princess.png"
    },
    {
        "name": "Advance to Olympus — Zeus's Blessing",
        "desc": "By Zeus’s blessing, advance to Olympus! Passing GO rewards you <:coin:1418612412885635206> $200 Coins!",
        "effect": "advance_olympus",
        "image": "images/ze_zeus.png"
    },
    {
        "name": "Advance to Sweet Kingdom — Sweet Bonanza",
        "desc": "You found a Lollipop from Sweet Bonanza, but it isn’t enough... travel to Sweet Kingdom to collect more sweets!",
        "effect": "advance_sweet",
        "image": "images/sweet_bonanza.png"
    },
    {
        "name": "Advance to Zombie Carnival — Rotten Horde",
        "desc": "Rotten zombie hordes drag you into Zombie Carnival! Passing GO rewards you <:coin:1418612412885635206> $200 Coins!",
        "effect": "advance_zombie",
        "image": "images/rotten.png"
    },
    {
        "name": "Advance to Nearest Provider — Dragon’s Flight",
        "desc": "Dragon Hero roars: 'Fly with me to the nearest Provider! Seize it if unowned, but if guarded, pay double rent as tribute!'",
        "effect": "nearest_provider",
        "image": "images/dragon_hero.png"
    },
    {
        "name": "Advance to Nearest Utility Realm — Madame Destiny’s Prophecy",
        "desc": "Madame Destiny declares: 'Fate guides you onward — whether to Money Train’s rails of fortune or the halls of madness in Mental! If free, claim it. If owned, roll dice ×10 AJ Coins as destiny’s toll.'",
        "effect": "nearest_utility",
        "image": "images/madame_destiny.png"
    },
    {
        "name": "Aztec Treasure Dividend — John Hunter’s Reward",
        "desc": "John Hunter grins: 'The treasures of the Aztecs are ours — I grant you <:coin:1418612412885635206> $125 Coins!'",
        "effect": 125,
        "image": "images/john_hunter.png"
    },
    {
        "name": "Get Out of Jail Free — Athena’s Token",
        "desc": "Athena says: 'I grant you this token of Wisdom — should fate lock you away, it will guide you out. A Wild Card of divine favor.'",
        "effect": "jail_card",
        "image": "images/athena.png"
    },
    {
        "name": "Backstep of Mischief — Loki’s Trick",
        "desc": "Loki Tricked you again! Roll a single die — move backward by its number, and taste my mischief!'",
        "effect": "back_dice",
        "image": "images/loki.png"
    },
    {
        "name": "Go To Jail — Cash Crew Snitch",
        "desc": "Cash Crew’s heist went wrong — your teammate got caught and ratted you out! You go straight to San Quentin xWays Jail!",
        "effect": "gotojail",
        "image": "images/cash_crew.png"
    },
    {
        "name": "Le Bandit’s Cut — Tribute Theft",
        "desc": "Le Bandit snickers: 'Looks like I’ll take $50 from every property you own — call it my cut!'",
        "effect": "letax",
        "image": "images/le_bandit.png"
    },
    {
        "name": "Pickle Bandits Ambush",
        "desc": "The Pickle Bandits ambush you: 'Hand over <:coin:1418612412885635206> $75 Coins — or we’ll sour your day!'",
        "effect": -75,
        "image": "images/pickle_bandits.png"
    },
    {
        "name": "Mustang Gold Respin",
        "desc": "The wild Mustang bursts forward — granting you another roll!",
        "effect": "extra_turn",
        "image": "images/mustang_gold.png"
    },
    {
        "name": "Pirate Treasure Split Tribute",
        "desc": "The Pirate Bonanza captain grins: ‘A fair share for all — pay <:coin:1418612412885635206> $10 Coins to each matey, the treasure must be divided!’",
        "effect": "pay_each",
        "image": "images/pirate_bonanza.png"
    },
    {
        "name": "Big Bass Catch",
        "desc": "You lend the fisherman a hand in Big Bass Bonanza — together you haul in a prize catch worth <:coin:1418612412885635206> $175 Coins!",
        "effect": 175,
        "image": "images/big_bass_bonanza.png"
    },
    {
        "name": "Lucky Penny’s Gift",
        "desc": "Lucky Penny beams with fortune: ‘Take 25% of the Slot Prize Pool — may luck keep shining on you!’",
        "effect": "slot_prize",
        "image": "images/lucky_penny.png"
    },
]
CHEST_CARDS = [
    {
        "name": "Elvis Frog Performance Bonus",
        "desc": "Elvis Frog thanks you for rocking the stage with him — you collect <:coin:1418612412885635206> $200 Coins as your share!",
        "effect": 200,
        "image": "images/elvis_frog.png"
    },
    {
        "name": "Cai Shen’s Hidden Chest",
        "desc": "Cai Shen smiles as a chest bursts open with fortune — you collect <:coin:1418612412885635206> $200 Coins!",
        "effect": 200,
        "image": "images/chests_of_cai_shen.png"
    },
    {
        "name": "Wanted Dead or a Wild — Bought Freedom",
        "desc": "The outlaws of Wanted Dead or a Wild drag you into the saloon — you pay <:coin:1418612412885635206> $50 Coins to buy your way out alive.",
        "effect": -50,
        "image": "images/wanted.png"
    },
    {
        "name": "Fire in the Hole Blast",
        "desc": "You help the miner set off the blast — the explosion reveals hidden gold, and you grab <:coin:1418612412885635206> $50 Coins from the freshly blasted stash!",
        "effect": 50,
        "image": "images/fire_in_the_hole.png"
    },
    {
        "name": "Evil Eyes Curse",
        "desc": "The Evil Eyes glare at the board: ‘Land on someone’s property and watch the curse! They’ll pay you the rent instead!’",
        "effect": "rent_reversal",
        "image": "images/evil_eyes.png"
    },
    {
        "name": "Tombstone RIP Dead Spin",
        "desc": "In *Tombstone RIP*, your spin flatlines… Lose <:coin:1418612412885635206> $100 Coins to resurrect your chances.",
        "effect": -100,
        "image": "images/tombstone_rip.png"
    },
    {
        "name": "Danny Dollar Payday",
        "desc": "Danny Dollar makes it rain: ‘The cash shower hits you this time — scoop up <:coin:1418612412885635206> $100 Coins from my dollar storm!’",
        "effect": 100,
        "image": "images/danny_dollar.png"
    },
    {
        "name": "Duck Hunter’s Buyback",
        "desc": "You hand over a duck to the Duck Hunter — he pays you <:coin:1418612412885635206> $20 Coins and awards you 1 entry into the $20 Weekly Bonus Buy! 🎟️ Open a ticket and tag us to claim your bonus.",
        "effect": 20,
        "image": "images/duck_hunter.png"
    },
    {
        "name": "Wild Beach Birthday Bash",
        "desc": "The Wild Beach Party turns into your Jackpot Birthday celebration — every player donates <:coin:1418612412885635206> $10 Coins to keep the party going!",
        "effect": "birthday",
        "image": "images/wild_beach_party.png"
    },
    {
        "name": "Snoop Dogg’s Chill Bonus",
        "desc": "Snoop Dogg leans back: ‘Thanks for ridin’ with me — take <:coin:1418612412885635206> $150 Coins for keepin’ it real.’",
        "effect": 150,
        "image": "images/snoop_dogg_dollars.png"
    },
    {
        "name": "Karen Maneater’s Greasy Bill",
        "desc": "Karen snarls: ‘Extra cheese, extra charge!’ — you’re stuck paying <:coin:1418612412885635206> $150 Coins for her junk-fueled feast.",
        "effect": -150,
        "image": "images/karen_maneater.png"
    },
    {
        "name": "Twisted Lab Experiment Fee",
        "desc": "The mad scientist from Twisted Lab demands: ‘Knowledge has a price!’ Pay <:coin:1418612412885635206> $75 Coins for his warped coaching session.",
        "effect": -125,
        "image": "images/twisted_lab.png"
    },
    {
        "name": "Fruit Party Sale Profit",
        "desc": "From your Fruit Party harvest, eager buyers snap up your fruits — you earn <:coin:1418612412885635206> $75 Coins!",
        "effect": 75,
        "image": "images/fruit_party.png"
    },
    {
        "name": "Infective Claim Bonus",
        "desc": "The virus spreads… but the lab grants you <:coin:1418612412885635206> $50 Coins per property owned as ‘hazard pay.’",
        "effect": "insurance",
        "image": "images/infective_wild.png"
    },
    {
        "name": "Frank’s Diner Pie Contest",
        "desc": "Farmer Frank chuckles at the diner: ‘You didn’t win, but your pie-eating skills impressed me!’ Collect <:coin:1418612412885635206> $25 Coins as second prize.",
        "effect": 25,
        "image": "images/franks_farm.png"
    },
    {
        "name": "Midas’s Golden Inheritance",
        "desc": "King Midas touches your fate: ‘All that glitters is now yours!’ You inherit <:coin:1418612412885635206> $175 Coins in pure gold.",
        "effect": 175,
        "image": "images/hand_of_midas.png"
    },
]

# ------------------ Database Setup ----------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
  guild_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  username TEXT,
  coins INTEGER NOT NULL DEFAULT 0,
  position INTEGER NOT NULL DEFAULT 0,
  jailed_until INTEGER DEFAULT 0,
  last_roll INTEGER DEFAULT 0,
  PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS properties (
  guild_id INTEGER NOT NULL,
  idx INTEGER NOT NULL,
  owner_id INTEGER,
  mortgaged INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild_id, idx)
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  amount INTEGER NOT NULL,
  reason TEXT,
  ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS game_state (
  guild_id INTEGER PRIMARY KEY,
  bank_pool INTEGER NOT NULL DEFAULT 0
);

-- 🔹 Giveaway table
CREATE TABLE IF NOT EXISTS daily_giveaway (
  guild_id INTEGER NOT NULL,
  message_id INTEGER NOT NULL,
  giveaway_date TEXT NOT NULL,
  PRIMARY KEY (guild_id, giveaway_date)
);
"""

async def init_db():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()

# ------------------ Board Image -------------------

def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        if FONT_PATH and os.path.exists(FONT_PATH):
            return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        pass
    return ImageFont.load_default()

def generate_dice_face(value: int, size: int = 100) -> Image.Image:
    """Generate a glowing red dice with white pips."""
    # Transparent base
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    margin = size // 10
    radius = size // 6
    pip_r = size // 10

    # ✨ Glow layer (blurred red behind dice)
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=radius,
        fill=(255, 50, 50, 160),  # soft red glow
    )
    glow = glow.filter(ImageFilter.GaussianBlur(size // 8))

    # 🎲 Dice body (solid red on top of glow)
    dice_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(dice_layer)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=radius,
        fill=(200, 0, 0, 255),  # red dice body
    )

    # ⚪ White pips
    positions = {
        1: [(0.5, 0.5)],
        2: [(0.25, 0.25), (0.75, 0.75)],
        3: [(0.25, 0.25), (0.5, 0.5), (0.75, 0.75)],
        4: [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)],
        5: [(0.25, 0.25), (0.75, 0.25), (0.5, 0.5), (0.25, 0.75), (0.75, 0.75)],
        6: [(0.25, 0.25), (0.75, 0.25), (0.25, 0.5), (0.75, 0.5), (0.25, 0.75), (0.75, 0.75)],
    }

    for (px, py) in positions[value]:
        cx, cy = int(px * size), int(py * size)
        draw.ellipse(
            (cx - pip_r, cy - pip_r, cx + pip_r, cy + pip_r),
            fill=(255, 255, 255, 255),  # white dots
        )

    # Merge glow + dice
    out = Image.alpha_composite(glow, dice_layer)
    return out

def board_coords(size: int, margin: int) -> Dict[int, Tuple[int, int, int, int]]:
    """
    Produce 40 non-overlapping tile rectangles around the board using an 11x11 grid.
    Grid approach: create 11 equal logical cells per side (grid_units=11),
    compute integer boundaries (rounded) and map perimeter cells to 40 tile rects.

    Returns mapping idx -> (x0, y0, x1, y1) for idx in 0..39.
    """
    coords: Dict[int, Tuple[int, int, int, int]] = {}

    # inner square (area where tiles live)
    inner = size - 2 * margin
    if inner <= 0:
        raise ValueError("size and margin result in non-positive inner area")

    grid_units = 11  # as you requested (11 logical steps per side)
    # cell size as float (we will round to integer boundaries)
    cell_f = inner / grid_units

    # compute integer boundary positions from left/top to right/bottom
    # accumulate float then round each boundary to avoid cumulative rounding drift
    bounds: List[int] = [margin]
    acc = margin
    for i in range(grid_units):
        acc += cell_f
        bounds.append(int(round(acc)))

    # bounds now has length grid_units + 1 (12)
    # bounding indexes: 0 .. grid_units  (0..11)

    # --- Bottom row: indices 0..9 (rightmost -> leftmost)
    # We'll follow the same index orientation as your SLOT_BOARD (0 is GO at bottom-right)
    for i in range(10):
        # index i maps to the i-th tile from the right edge moving left
        x0 = bounds[grid_units - (i + 1)]
        x1 = bounds[grid_units - i]
        y0 = bounds[grid_units - 1]
        y1 = bounds[grid_units]
        coords[i] = (x0, y0, x1, y1)

    # --- Left column: indices 10..19 (bottom -> top)
    for i in range(10):
        x0 = bounds[0]
        x1 = bounds[1]
        # i==0 => bottom-most left column tile, so use the same scheme as bottom
        y0 = bounds[grid_units - (i + 1)]
        y1 = bounds[grid_units - i]
        coords[10 + i] = (x0, y0, x1, y1)

    # --- Top row: indices 20..29 (left -> right)
    for i in range(10):
        x0 = bounds[i]
        x1 = bounds[i + 1]
        y0 = bounds[0]
        y1 = bounds[1]
        coords[20 + i] = (x0, y0, x1, y1)

    # --- Right column: indices 30..39 (top -> bottom)
    for i in range(10):
        x0 = bounds[grid_units - 1]
        x1 = bounds[grid_units]
        y0 = bounds[i]
        y1 = bounds[i + 1]
        coords[30 + i] = (x0, y0, x1, y1)

    # sanity check: ensure we produced all 40 indices
    missing = [i for i in range(40) if i not in coords]
    if missing:
        raise RuntimeError(f"board_coords did not produce indexes: {missing}")

    return coords


def generate_base_board(
    path: str = BOARD_IMAGE_PATH,
    size: int = 1600,
    margin: int = 80,
    center_override: str = None,
    include_center: bool = True,      # <-- new flag
) -> None:
    img = Image.new("RGB", (size, size), BOARD_BG)
    draw = ImageDraw.Draw(img)
    coords = board_coords(size, margin)
    title_font = load_font(56)
    name_font = load_font(20)

    # 🔹 Draw all tiles (no center art here)
    for sq in SLOT_BOARD:
        idx = sq["idx"]
        x0, y0, x1, y1 = coords[idx]
        draw.rectangle([x0, y0, x1, y1], fill=TILE_BG, outline=TILE_BORDER, width=3)

        # Group bar
        if sq["type"] in ("property", "provider", "utility"):
            gcol = GROUP_COLORS.get(sq.get("group", ""), (100, 100, 100))
            draw.rectangle([x0, y0, x1, y0 + 18], fill=gcol)

        # Slot/property name
        name = sq["name"]
        try:
            tw = draw.textlength(name, font=name_font)
        except Exception:
            tw = name_font.getsize(name)[0]
        name_x = x0 + (x1 - x0 - tw) / 2
        name_y = y0 + 22
        for ox in [-1, 1]:
            for oy in [-1, 1]:
                draw.text((name_x + ox, name_y + oy), name, font=name_font, fill=(0, 0, 0))
        draw.text((name_x, name_y), name, font=name_font, fill=(255, 215, 0))

        # Tile image (inside the tile rectangle)
        if "image" in sq and os.path.exists(sq["image"]):
            try:
                tile_img = Image.open(sq["image"]).convert("RGBA")
                padding = 4
                img_top = name_y + name_font.size + 6
                img_bottom = y1 - padding
                img_h = img_bottom - img_top
                img_w = max(1, (x1 - x0) - (padding * 2))
                # keep aspect handled by thumbnail/resizing
                tile_img = tile_img.resize((img_w, max(1, img_h)), Image.LANCZOS)
                img.paste(tile_img, (x0 + padding, img_top), tile_img)
            except Exception as e:
                print(f"Could not load image {sq['image']}: {e}")

    # 🔹 Center label (draw once, after tiles)
    title = ""
    try:
        tw = draw.textlength(title, font=title_font)
    except Exception:
        tw = title_font.getsize(title)[0]
    draw.text(((size - tw) / 2, size / 2 - 28), title, font=title_font, fill=ACCENT)

    # 🎨 Add center artwork (only if include_center True)
    if include_center:
        if center_override and os.path.exists(center_override):
            art_path = center_override
        else:
            art_path = os.path.join("images", "center_art.png")  # default fallback

        if os.path.exists(art_path):
            try:
                art_img = Image.open(art_path).convert("RGBA")
                art_img.thumbnail((size // 3, size // 3), Image.LANCZOS)
                ax = (size - art_img.width) // 2
                ay = (size - art_img.height) // 2
                img.paste(art_img, (ax, ay), art_img)
            except Exception as e:
                print(f"Could not load center artwork: {e}")

    # Save once
    img.save(path, format="PNG")
    print(f"✅ Board image saved at {path}")

def render_board_with_players(
    guild_players: List[Tuple[int, str, int]], size: int = 1600, margin: int = 80
) -> Image.Image:
    # 🔥 Always regenerate instead of loading old PNG
    generate_base_board(BOARD_IMAGE_PATH, size, margin)
    base = Image.open(BOARD_IMAGE_PATH).copy()
    draw = ImageDraw.Draw(base)
    coords = board_coords(size, margin)

    # 🎨 Deterministic token colors
    def token_color(uid: int) -> Tuple[int, int, int]:
        random.seed(uid)
        return (random.randint(60, 255), random.randint(60, 255), random.randint(60, 255))

    # 🔹 Group players by tile
    tiles: Dict[int, List[Tuple[int, str]]] = {}
    for uid, uname, pos in guild_players:
        tiles.setdefault(pos, []).append((uid, uname))

    # 🔹 Render players per tile
    for pos, players in tiles.items():
        x0, y0, x1, y1 = coords.get(pos, coords[0])
        w = x1 - x0
        h = y1 - y0

        if len(players) == 1:
            # 🎯 Single player token → smaller + centered
            uid, uname = players[0]
            cx = (x0 + x1) // 2
            cy = (y0 + y1) // 2
            r = min(w, h) // 12  # ⬅️ Smaller size
            color = token_color(uid)

            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=(10, 10, 10))

            initials = ("".join([p[0] for p in uname.split() if p])).upper()[:2] or "P"
            f = load_font(16)
            tw = draw.textlength(initials, font=f)
            draw.text((cx - tw / 2, cy - 9), initials, font=f, fill=(0, 0, 0))

        else:
            # 🔹 Multiple players → grid layout
            for i, (uid, uname) in enumerate(players):
                r = min(w, h) // 6
                ox = (i % 3) * (r + 6) + 10
                oy = (i // 3) * (r + 6) + 10
                cx = x0 + 20 + ox
                cy = y0 + 20 + oy
                color = token_color(uid)
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=(10, 10, 10))

                initials = ("".join([p[0] for p in uname.split() if p])).upper()[:2] or "P"
                f = load_font(16)
                tw = draw.textlength(initials, font=f)
                draw.text((cx - tw / 2, cy - 9), initials, font=f, fill=(0, 0, 0))

    return base

def human_now() -> int:
    return int(time.time())

# ------------------ Helpers -----------------------
async def get_db():
    return await aiosqlite.connect(DB_PATH)

async def ensure_guild_state(guild_id: int):
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO game_state (guild_id, bank_pool) VALUES (?, 0)",
            (guild_id,)
        )
        # seed properties rows
        for sq in SLOT_BOARD:
            await db.execute(
                "INSERT OR IGNORE INTO properties (guild_id, idx, owner_id, mortgaged) VALUES (?, ?, NULL, 0)",
                (guild_id, sq["idx"])
            )
        await db.commit()
    finally:
        await db.close()   # ✅ clean close instead of async with

async def get_player(db: aiosqlite.Connection, guild_id: int, user: discord.User) -> Optional[aiosqlite.Row]:
    db.row_factory = aiosqlite.Row
    async with db.execute("SELECT * FROM players WHERE guild_id=? AND user_id=?", (guild_id, user.id)) as cur:
        return await cur.fetchone()

async def add_tx(db: aiosqlite.Connection, guild_id: int, user_id: int, amount: int, reason: str):
    await db.execute("INSERT INTO transactions (guild_id, user_id, amount, reason, ts) VALUES (?, ?, ?, ?, ?)",
                    (guild_id, user_id, amount, reason, human_now()))

async def update_balance(
    db: aiosqlite.Connection,
    guild_id: int,
    user_id: int,
    delta: int,
    reason: str,
    bot: discord.Client = None
) -> int:
    # Update player's coin balance
    await db.execute(
        "UPDATE players SET coins = coins + ? WHERE guild_id=? AND user_id=?",
        (delta, guild_id, user_id)
    )
    await add_tx(db, guild_id, user_id, delta, reason)

    # Fetch updated balance
    async with db.execute(
        "SELECT coins FROM players WHERE guild_id=? AND user_id=?",
        (guild_id, user_id)
    ) as cur:
        row = await cur.fetchone()
        if not row:
            return 0
        balance = row[0]

    # 🔥 Auto-redeem if threshold is met
    if balance >= REDEEM_THRESHOLD:
        # Reset player's coins
        await db.execute(
            "UPDATE players SET coins = ? WHERE guild_id=? AND user_id=?",
            (STARTING_COINS, guild_id, user_id)
        )

        # Make all player's properties unowned
        await db.execute(
            "UPDATE properties SET owner_id = NULL WHERE guild_id=? AND owner_id=?",
            (guild_id, user_id)
        )

        # Save DB changes first
        await db.commit()

        # 🔥 Send an announcement
        announcement = (
            f"🎉 Congratulations <@{user_id}>! You've reached <:coin:1418612412885635206> **{REDEEM_THRESHOLD} Coins** "
            f"and redeemed your balance for a **$20 Bonus Buy**! Please open a <#1248876035077046385> to claim your prize! 🎁\n"
            f"💰 Balance reset to <:coin:1418612412885635206> **{STARTING_COINS}** Coins, and all your properties are now "
            f"back on the market for anyone to buy!"
        )

        # Get bot object dynamically if not passed
        if not bot:
            from discord.utils import get
            for task in asyncio.all_tasks():
                if hasattr(task, "get_coro"):
                    coro = task.get_coro()
                    if coro and hasattr(coro, "cr_frame"):
                        frame = coro.cr_frame
                        if frame and "self" in frame.f_locals:
                            potential_bot = frame.f_locals["self"]
                            if isinstance(potential_bot, discord.Client):
                                bot = potential_bot
                                break

        # Try sending announcement
        channel = None
        if bot:
            channel = bot.get_channel(REDEEM_CHANNEL_ID)
            if not channel:
                guild = bot.get_guild(guild_id)
                if guild:
                    channel = next(
                        (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
                        None
                    )

        if channel:
            await channel.send(announcement)
        else:
            print(f"[INFO] Would announce: {announcement}")

    else:
        await db.commit()

    return balance

async def log_transaction(guild, msg=None, embed=None, file=None):
    tx_channel = bot.get_channel(MONOPOLY_TRANSACTIONS_CHANNEL_ID)
    if tx_channel:
        if file:
            await tx_channel.send(content=msg, embed=embed, file=file)
        elif embed:
            await tx_channel.send(content=msg, embed=embed)
        else:
            await tx_channel.send(msg)

async def fetch_avatar(bot: discord.Client, user_id: int) -> Image.Image:
    """Fetch a user's Discord avatar and return as a PIL Image."""
    user = bot.get_user(user_id) or await bot.fetch_user(user_id)
    if not user:
        # Return a default placeholder
        img = Image.new("RGB", (64, 64), color=(128, 128, 128))
        return img

    url = user.display_avatar.url
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.read()

    avatar = Image.open(io.BytesIO(data)).convert("RGBA")
    return avatar


def circle_crop(im: Image.Image, size: int = 64) -> Image.Image:
    size = int(size)  # ✅ Ensure integer
    im = im.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    out = ImageOps.fit(im, (size, size), centering=(0.5, 0.5))
    out.putalpha(mask)
    return out

def generate_dice_face(value: int, size: int = 100) -> Image.Image:
    """Generate a dice face image with given value (1–6)."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))  # white dice
    draw = ImageDraw.Draw(img)

    # Draw border
    border = 6
    draw.rounded_rectangle([0, 0, size-1, size-1], radius=15, outline=(0, 0, 0), width=border, fill=(255, 255, 255))

    # Dot positions (normalized to grid)
    dot_positions = {
        1: [(0.5, 0.5)],
        2: [(0.25, 0.25), (0.75, 0.75)],
        3: [(0.25, 0.25), (0.5, 0.5), (0.75, 0.75)],
        4: [(0.25, 0.25), (0.25, 0.75), (0.75, 0.25), (0.75, 0.75)],
        5: [(0.25, 0.25), (0.25, 0.75), (0.5, 0.5), (0.75, 0.25), (0.75, 0.75)],
        6: [(0.25, 0.25), (0.25, 0.5), (0.25, 0.75), (0.75, 0.25), (0.75, 0.5), (0.75, 0.75)],
    }

    dot_r = size // 10
    for (x, y) in dot_positions[value]:
        cx, cy = int(x * size), int(y * size)
        draw.ellipse([cx-dot_r, cy-dot_r, cx+dot_r, cy+dot_r], fill=(0, 0, 0))

    return img

async def render_board_with_players_avatars(
    bot: commands.Bot,
    guild_players: List[Tuple[int, str, int]],
    size: int = 1600,
    margin: int = 80,
    center_tile_idx: Optional[int] = None,
    dice: Optional[Tuple[int, int]] = None,
    guild_id: Optional[int] = None,
    force_default_art: bool = False,   # 👈 NEW
) -> Image.Image:
    # Ensure board exists
    if not os.path.exists(BOARD_IMAGE_PATH):
        os.makedirs(ASSETS_DIR, exist_ok=True)
        generate_base_board(BOARD_IMAGE_PATH, size=size, margin=margin)

    base = Image.open(BOARD_IMAGE_PATH).convert("RGBA").copy()
    coords = board_coords(size, margin)
    draw = ImageDraw.Draw(base)

    # try to load a font (fallback to default)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    # 1) Collect owners for this guild in a single query (idx -> username)
    owners_by_idx: Dict[int, str] = {}
    if guild_id is not None:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                # join properties -> players to get owner username
                async with db.execute("""
                    SELECT pr.idx AS idx, p.username AS username
                    FROM properties pr
                    JOIN players p ON pr.owner_id = p.user_id
                    WHERE pr.guild_id=? AND pr.owner_id IS NOT NULL
                """, (guild_id,)) as cur:
                    rows = await cur.fetchall()
                for r in rows:
                    owners_by_idx[int(r["idx"])] = r["username"]
        except Exception as e:
            # if DB fails, just continue without owners
            print(f"[render_board] owner lookup failed: {e}")

    # 2) Draw avatars per tile (your existing logic)
    tiles: Dict[int, List[Tuple[int, str]]] = {}
    for uid, uname, pos in guild_players:
        tiles.setdefault(pos, []).append((uid, uname))

    for pos, players in tiles.items():
        x0, y0, x1, y1 = coords.get(pos, coords[0])
        w, h = x1 - x0, y1 - y0

        for i, (uid, _) in enumerate(players):
            member = bot.get_user(uid)
            avatar_url = getattr(member, "display_avatar", None)
            avatar_url = avatar_url.url if avatar_url else None
            if not avatar_url:
                continue

            # Fetch avatar bytes
            try:
                async with bot.http._HTTPClient__session.get(avatar_url) as resp:
                    avatar_bytes = await resp.read()
                avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            except Exception:
                continue

            # size & placement
            if len(players) == 1:
                token_size = int(min(w, h) * 0.5)
                px, py = (x0 + x1) // 2 - token_size // 2, (y0 + y1) // 2 - token_size // 2
            else:
                token_size = int(min(w, h) * 0.3)
                ox = (i % 2) * (token_size + 4)
                oy = (i // 2) * (token_size + 4)
                px, py = x0 + 8 + ox, y0 + 8 + oy

            avatar_img = avatar_img.resize((token_size, token_size), Image.LANCZOS)

            # make circular mask
            mask = Image.new("L", (token_size, token_size), 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.ellipse((0, 0, token_size, token_size), fill=255)
            avatar_img = ImageOps.fit(avatar_img, (token_size, token_size))
            avatar_img.putalpha(mask)

            # border
            border_size = 2
            border = Image.new("RGBA", (token_size + border_size * 2, token_size + border_size * 2), (0, 0, 0, 0))
            border_draw = ImageDraw.Draw(border)
            border_draw.ellipse(
                (0, 0, token_size + border_size * 2, token_size + border_size * 2),
                fill=(255, 215, 0, 255)
            )
            border.paste(avatar_img, (border_size, border_size), avatar_img)

            base.paste(border, (px - border_size, py - border_size), border)

    # 3) Draw owner names directly on tile (no background band)
    if owners_by_idx:
        for idx, owner in owners_by_idx.items():
            # guard in case coords missing
            if idx not in coords:
                continue
            x0, y0, x1, y1 = coords[idx]
            w, h = x1 - x0, y1 - y0

            # text: truncate if too long
            short = owner
            if len(short) > 16:
                short = short[:13] + "..."

            # position: centered horizontally, close to the top of the tile
            tx = (x0 + x1) // 2
            ty = y0 + 10  # adjust padding (smaller = higher)

            # draw outline for readability
            outline_color = (255, 255, 255)
            fill_color = (0, 0, 0)
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw.text((tx + ox, ty + oy), short, font=font, anchor="mm", fill=outline_color)
            draw.text((tx, ty), short, font=font, anchor="mm", fill=fill_color)

    # 4) Center artwork
    art_h = 0
    if force_default_art:
        # Always show default art (used by /monopoly_board)
        default_art = os.path.join("images", "default_center.png")
        if os.path.exists(default_art):
            try:
                art_img = Image.open(default_art).convert("RGBA")
                max_w, max_h = size // 3, size // 3
                art_img.thumbnail((max_w, max_h), Image.LANCZOS)
                ax = (size - art_img.width) // 2
                ay = (size - art_img.height) // 2
                base.paste(art_img, (ax, ay), art_img)
                art_h = art_img.height
            except Exception as e:
                print(f"[render_board] default art load failed: {e}")

    elif center_tile_idx is not None:
        # Only show landed tile art (used by /monopoly_roll)
        sq = SLOT_BOARD[center_tile_idx]
        tile_image = sq.get("image")
        if tile_image:
            abs_path = os.path.join(os.path.dirname(__file__), tile_image)
            if os.path.exists(abs_path):
                try:
                    art_img = Image.open(abs_path).convert("RGBA")
                    max_w, max_h = size // 3, size // 3
                    art_img.thumbnail((max_w, max_h), Image.LANCZOS)
                    ax = (size - art_img.width) // 2
                    ay = (size - art_img.height) // 2
                    base.paste(art_img, (ax, ay), art_img)
                    art_h = art_img.height
                except Exception as e:
                    print(f"[render_board] center art load failed: {e}")

    # 5) Dice overlay (unchanged logic but respects art_h)
    if dice:
        d1, d2 = dice
        dice_size = size // 12
        dice1 = generate_dice_face(d1, dice_size)
        dice2 = generate_dice_face(d2, dice_size)

        spacing = 20
        total_w = dice1.width + dice2.width + spacing
        dice_img = Image.new("RGBA", (total_w, max(dice1.height, dice2.height)), (0, 0, 0, 0))
        dice_img.paste(dice1, (0, 0), dice1)
        dice_img.paste(dice2, (dice1.width + spacing, 0), dice2)

        dx = (size - dice_img.width) // 2
        center_y = size // 2
        dy = center_y - (art_h // 2) - dice_img.height - 20
        if dy < margin + 8:
            dy = margin + 8

        base.paste(dice_img, (dx, dy), dice_img)

    return base

async def ensure_properties(db, guild_id: int):
    for sq in SLOT_BOARD:
        if sq["type"] in ("property", "provider", "utility"):
            await db.execute(
                "INSERT OR IGNORE INTO properties (guild_id, idx, owner_id, name) VALUES (?, ?, NULL, ?)",
                (guild_id, sq["idx"], sq["name"])
            )
    await db.commit()

async def set_position(db: aiosqlite.Connection, guild_id: int, user_id: int, pos: int):
    await db.execute("UPDATE players SET position=? WHERE guild_id=? AND user_id=?", (pos % 40, guild_id, user_id))

async def full_group_owned(db: aiosqlite.Connection, guild_id: int, group: str, owner_id: int) -> bool:
    idxs = PROPERTY_GROUPS.get(group, [])
    if not idxs:
        return False
    placeholders = ",".join(["?"] * len(idxs))
    async with db.execute(
        f"SELECT COUNT(*) FROM properties WHERE guild_id=? AND idx IN ({placeholders}) AND owner_id=?",
        (guild_id, *idxs, owner_id)
    ) as cur:
        c = (await cur.fetchone())[0]
    return c == len(idxs)

async def get_owner(db, guild_id: int, idx: int) -> Optional[int]:
    async with db.execute(
        "SELECT owner_id FROM properties WHERE guild_id=? AND idx=?",
        (guild_id, idx)
    ) as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        return row[0]  # can be NULL (no owner yet)


# ------------------ Views (Buttons) ---------------
class BuyPassView(discord.ui.View):
    def __init__(self, owner_user_id: int, timeout: Optional[float] = TURN_DECISION_TIMEOUT):
        super().__init__(timeout=timeout)
        self.owner_user_id = owner_user_id
        self.choice: Optional[str] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_user_id:
            await interaction.response.send_message("This prompt isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.success)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.choice = "buy"
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Pass", style=discord.ButtonStyle.danger)
    async def pass_(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.choice = "pass"
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

# ------------------ Core Turn Logic ---------------
async def process_landing(interaction, db, player_row, roll, double_rent: bool = False, utility_card: bool = False):
    guild_id = interaction.guild_id
    user = interaction.user
    pos = (player_row["position"] + roll) % 40


    # ✅ Save new position right away
    await set_position(db, guild_id, user.id, pos)
    await db.commit()

    # Pass GO handling
    passed_go = (player_row["position"] + roll) // 40 > 0
    if passed_go:
        new_bal = await update_balance(db, guild_id, user.id, 200, "Passed GO")

        # 👤 Show simple message in the rolling channel
        msg = (
            f"🏁 {user.mention} passed **GO** and collected <:coin:1418612412885635206> **$200 Coins**!\n"
            f"💳 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**"
        )
        await interaction.followup.send(msg)

        # 📜 Log to transactions channel (embed with tile artwork)
        embed = discord.Embed(
            title="🏁 Passed GO",
            description=(
                f"{user.mention} passed **GO** and collected <:coin:1418612412885635206> **$200 Coins**!\n\n"
                f"💳 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**"
            ),
            color=discord.Color.green()
        )

        # Tile artwork (GO tile is index 0 in your SLOT_BOARD)
        go_tile = SLOT_BOARD[0]
        tile_image = go_tile.get("image")
        if tile_image and os.path.exists(tile_image):
            file = discord.File(tile_image, filename="tile.png")
            embed.set_thumbnail(url="attachment://tile.png")
            await log_transaction(interaction.guild, embed=embed, file=file)
        else:
            await log_transaction(interaction.guild, embed=embed)


    sq = SLOT_BOARD[pos]

    # 🎨 Update board center artwork
    if sq["type"] in ("gamble", "chest"):
        # Don’t bake in default center art — keep board blank in the middle
        generate_base_board(BOARD_IMAGE_PATH, include_center=False)

    # 🚔 Jail / GotoJail
    if sq["type"] == "gotojail":
        # 🔹 Check if player has a Get Out of Jail Free card
        async with db.execute(
                "SELECT jail_free_cards FROM players WHERE guild_id=? AND user_id=?",
                (guild_id, user.id)
        ) as cur:
            row = await cur.fetchone()
            cards = row[0] if row else 0

        if cards > 0:
            # Consume one card and skip jail
            await db.execute(
                "UPDATE players SET jail_free_cards = jail_free_cards - 1 WHERE guild_id=? AND user_id=?",
                (guild_id, user.id)
            )
            await db.commit()
            await interaction.followup.send(
                f"🆓 {user.mention} used a **Get Out of Jail Free** card! You stay free. 🚀"
            )
            return

        # No card, go to jail
        await set_position(db, guild_id, user.id, 10)
        jailed_until = human_now() + 24 * 3600  # 24 hours
        await db.execute(
            "UPDATE players SET jailed_until=? WHERE guild_id=? AND user_id=?",
            (jailed_until, guild_id, user.id)
        )
        await db.commit()
        await interaction.followup.send(
            f"🚨 Go To Jail! {user.mention} is jailed for 24 hours (can't roll)."
        )
        return

    if sq["type"] == "tax":
        amt = -int(sq.get("amount", 100))
        new_bal = await update_balance(db, guild_id, user.id, amt, f"Tax: {sq['name']}")
        await db.commit()

        # 👤 Simple message in the rolling channel
        msg = (
            f"💸 {user.mention} paid <:coin:1418612412885635206> **${-amt} Coins** for **{sq['name']}**.\n"
            f"💰 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**"
        )
        await interaction.followup.send(msg)

        # 📜 Embed log with tile artwork
        embed = discord.Embed(
            title=f"💸 Tax Paid — {sq['name']}",
            description=(
                f"{user.mention} paid <:coin:1418612412885635206> **${-amt} Coins** for **{sq['name']}**.\n\n"
                f"💳 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**"
            ),
            color=discord.Color.red()
        )

        tile_image = sq.get("image")
        file = None
        if tile_image and os.path.exists(tile_image):
            file = discord.File(tile_image, filename="tile.png")
            embed.set_thumbnail(url="attachment://tile.png")

        await log_transaction(interaction.guild, embed=embed, file=file)
        return

    if sq["type"] == "free":
        await interaction.followup.send(f"🅿️ {user.mention} is chilling on **{sq['name']}**.")
        return

    if sq["type"] == "jail":
        await interaction.followup.send(f"👮 {user.mention} is just visiting **Jail**.")
        return

    if sq["type"] in ("gamble", "chest"):
        # Draw a card (dict style)
        card = random.choice(GAMBLE_CARDS if sq["type"] == "gamble" else CHEST_CARDS)
        desc = card["desc"]
        effect = card.get("effect")
        card_image = card.get("image")

        embed = discord.Embed(
            title=f"🎴 {sq['type'].title()} Card — {card['name']}",
            description=f"**{desc}**\n\n",
            color=discord.Color.purple() if sq["type"] == "gamble" else discord.Color.teal()
        )

        # Attach card artwork if available, otherwise tile image
        file = None
        if card_image and os.path.exists(card_image):
            file = discord.File(card_image, filename="card.png")
            embed.set_thumbnail(url="attachment://card.png")

        # 🔹 If effect is numeric → update balance
        if isinstance(effect, int):
            new_bal = await update_balance(db, guild_id, user.id, effect, f"{sq['type'].title()} Card")
            await db.commit()

            msg = (
                f"{embed.title}\n"  # 👈 copies "🎴 Chest Card — Bad RNG"
                f"{desc}\n\n"
                f"💰 {user.mention} {'gained' if effect > 0 else 'lost'} "
                f" <:coin:1418612412885635206> **${abs(effect)} Coins**.\n"
                f"💳 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**"
            )
            await interaction.followup.send(msg)

            embed.description += (
                f"💰 {user.mention} {'gained' if effect > 0 else 'lost'} <:coin:1418612412885635206> **${abs(effect)} Coins**.\n"
                f"💳 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**"
            )

            await log_transaction(interaction.guild, embed=embed, file=file)
            return

        # 🔹 Special effects
        if effect == "advance_go":
            await db.execute(
                "UPDATE players SET position=? WHERE guild_id=? AND user_id=?",
                (0, guild_id, user.id)
            )
            pos = 0
            new_bal = await update_balance(db, guild_id, user.id, 200, "Advance to GO")
            await db.commit()

            embed = discord.Embed(
                title="🎴 Gamble Card — Advance to GO!",
                description=(
                    f"✨ **Starlight Princess** moves {user.mention} straight to **GO**\n"
                    f"💰 Collected: <:coin:1418612412885635206> **$200 Coins**\n"
                    f"💳 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**"
                ),
                color=discord.Color.green()
            )

            card_path = os.path.join("images", "starlight_princess.png")

            # First send to the game channel
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)
            else:
                await interaction.followup.send(embed=embed)

            # Then log to transactions channel → reopen file
            if os.path.exists(card_path):
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await log_transaction(interaction.guild, embed=embed)

            return

        if effect == "advance_olympus":
            target_idx = 11  # Gates of Olympus tile
            old_pos = player_row["position"]

            # Move player to Olympus
            await db.execute(
                "UPDATE players SET position=? WHERE guild_id=? AND user_id=?",
                (target_idx, guild_id, user.id)
            )
            pos = target_idx

            # If wrapped around GO → award $200
            reward = 0
            if target_idx < old_pos:
                reward = 200
                new_bal = await update_balance(db, guild_id, user.id, reward, "Passed GO via Advance Olympus")
            else:
                # No reward, just fetch balance via update_balance(0)
                new_bal = await update_balance(db, guild_id, user.id, 0, "Advance Olympus")

            await db.commit()

            # --- Embed + image ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Advance to Olympus!",
                description=(
                    f"⚡ By Ze Zeus’s blessing, {user.mention} advances to **Gates of Olympus**!\n"
                    f"{'💰 Collected: <:coin:1418612412885635206> **$200 Coins** for Passing **GO**\n' if reward else ''}"
                    f"💳 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**"
                ),
                color=discord.Color.gold()
            )

            card_path = os.path.join("images", "ze_zeus.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)
            else:
                await interaction.followup.send(embed=embed)

            # Log to transaction channel (reopen file)
            if os.path.exists(card_path):
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await log_transaction(interaction.guild, embed=embed)

            # --- NEW: resolve the tile they were moved to (offer to buy / pay rent) ---
            # Fetch fresh player row (position is already updated above)
            player_row = await get_player(db, guild_id, user)
            if player_row:
                # Call process_landing again with roll=0 so the current tile gets resolved
                await process_landing(interaction, db, player_row, 0)
            return

        if effect == "advance_sweet":
            target_idx = 24  # Sweet Kingdom tile
            old_pos = player_row["position"]

            # Move player to Sweet Kingdom (no $200 reward, even if wrapped around GO)
            await db.execute(
                "UPDATE players SET position=? WHERE guild_id=? AND user_id=?",
                (target_idx, guild_id, user.id)
            )
            await update_balance(db, guild_id, user.id, 0, "Advance Sweet Kingdom")  # just fetch balance
            await db.commit()

            # --- Embed + image ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Advance to Sweet Kingdom!",
                description=(
                    f"🍭 {user.mention} found a Lollipop from **Sweet Bonanza**, "
                    f"but it isn’t enough... they travel to **Sweet Kingdom** for more sweets!"
                ),
                color=discord.Color.pink()
            )

            card_path = os.path.join("images", "sweet_bonanza.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)
            else:
                await interaction.followup.send(embed=embed)

            # Log to transaction channel (reopen file)
            if os.path.exists(card_path):
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await log_transaction(interaction.guild, embed=embed)

            # --- NEW: resolve tile logic (buy/rent etc) ---
            player_row = await get_player(db, guild_id, user)
            if player_row:
                await process_landing(interaction, db, player_row, 0)

            return

        if effect == "advance_zombie":
            target_idx = 32  # Gates of Olympus tile
            old_pos = player_row["position"]

            # Move player to Olympus
            await db.execute(
                "UPDATE players SET position=? WHERE guild_id=? AND user_id=?",
                (target_idx, guild_id, user.id)
            )
            pos = target_idx

            # If wrapped around GO → award $200
            reward = 0
            if target_idx < old_pos:
                reward = 200
                new_bal = await update_balance(db, guild_id, user.id, reward, "Passed GO via Rotten Horde")
            else:
                # No reward, just fetch balance via update_balance(0)
                new_bal = await update_balance(db, guild_id, user.id, 0, "Rotten Horde")

            await db.commit()

            # --- Embed + image ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Advance to Zombie Carnival!",
                description=(
                    f"🧟 Rotten zombie hordes drag {user.mention} into **Zombie Carnival**!\n"
                    f"{'💰 Collected: <:coin:1418612412885635206> **$200 Coins** for Passing **GO**\n' if reward else ''}"
                    f"💳 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**"
                ),
                color=discord.Color.gold()
            )

            card_path = os.path.join("images", "rotten.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)
            else:
                await interaction.followup.send(embed=embed)

            # Log to transaction channel (reopen file)
            if os.path.exists(card_path):
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await log_transaction(interaction.guild, embed=embed)

            # --- NEW: resolve the tile they were moved to (offer to buy / pay rent) ---
            # Fetch fresh player row (position is already updated above)
            player_row = await get_player(db, guild_id, user)
            if player_row:
                # Call process_landing again with roll=0 so the current tile gets resolved
                await process_landing(interaction, db, player_row, 0)
            return

        if effect == "nearest_provider":
            old_pos = player_row["position"]

            # 🔹 Define provider tiles (update with your board layout)
            provider_tiles = [5, 15, 25, 35]  # example positions, adjust to your Monopoly board

            # Find nearest provider going forward
            target_idx = None
            for step in range(1, 40):
                check_pos = (old_pos + step) % 40
                if check_pos in provider_tiles:
                    target_idx = check_pos
                    break

            if target_idx is None:
                await interaction.followup.send("⚠️ No provider tiles are set on this board!")
                return

            # Move player
            await db.execute(
                "UPDATE players SET position=? WHERE guild_id=? AND user_id=?",
                (target_idx, guild_id, user.id)
            )
            await db.commit()

            # --- Embed + image ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Advance to Nearest Provider!",
                description=(
                    f"🐲 Dragon Hero roars: 'Fly with me, {user.mention}, to the nearest **Provider**!\nSeize it if unowned, but if guarded, pay double rent as tribute!'\n"
                    f"You advance to **Tile {target_idx}**."
                ),
                color=discord.Color.red()
            )

            card_path = os.path.join("images", "dragon_hero.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)
            else:
                await interaction.followup.send(embed=embed)

            # Log transaction
            if os.path.exists(card_path):
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await log_transaction(interaction.guild, embed=embed)

            # --- Trigger normal landing logic (double rent applies) ---
            player_row = await get_player(db, guild_id, user)
            if player_row:
                await process_landing(interaction, db, player_row, 0, double_rent=True)

            return

        if effect == "nearest_utility":
            old_pos = player_row["position"]

            # Utility tile indices
            utility_tiles = [12, 28]

            # Find nearest utility going forward
            target_idx = None
            for step in range(1, 40):
                check_pos = (old_pos + step) % 40
                if check_pos in utility_tiles:
                    target_idx = check_pos
                    break

            if target_idx is None:
                await interaction.followup.send("⚠️ No utility tiles are set on this board!")
                return

            # Move player
            await db.execute(
                "UPDATE players SET position=? WHERE guild_id=? AND user_id=?",
                (target_idx, guild_id, user.id)
            )
            await db.commit()

            # --- Embed + image ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Advance to Nearest Utility!",
                description=(
                    f"🔮 Madame Destiny declares: '{user.mention}, Fate guides you onward — whether to **Money Train’s** rails of fortune or the halls of madness in **Mental**! If free, claim it. If owned, roll dice ×10 <:coin:1418612412885635206> Coins as destiny’s toll.!'\n"
                    f"You advance to **Tile {target_idx}**."
                ),
                color=discord.Color.purple()
            )

            card_path = os.path.join("images", "madame_destiny.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)
            else:
                await interaction.followup.send(embed=embed)

            # Log transaction
            if os.path.exists(card_path):
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await log_transaction(interaction.guild, embed=embed)

            # --- Trigger normal landing logic, but force special utility rent ---
            player_row = await get_player(db, guild_id, user)
            if player_row:
                # We’ll use a new flag to override rent calculation
                await process_landing(interaction, db, player_row, 0, utility_card=True)

            return

        if effect == "jail_card":
            await db.execute(
                "UPDATE players SET jail_free_cards = COALESCE(jail_free_cards, 0) + 1 WHERE guild_id=? AND user_id=?",
                (guild_id, user.id)
            )
            await db.commit()

            embed.description += f"🆓 {user.mention} got a **Get Out of Jail Free** card!"

            card_path = os.path.join("images", "athena.png")

            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)

                # re-open file for logging
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await interaction.followup.send(embed=embed)
                await log_transaction(interaction.guild, embed=embed)

            return

        if effect == "back_dice":
            # 🎲 Roll one die
            steps = random.randint(1, 6)
            target_idx = (player_row["position"] - steps) % 40

            # Move player
            await db.execute(
                "UPDATE players SET position=? WHERE guild_id=? AND user_id=?",
                (target_idx, guild_id, user.id)
            )
            await db.commit()

            # --- Embed + image ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Backstep of Mischief!",
                description=(
                    f"🃏 Loki tricks {user.mention}!\n"
                    f"You rolled a **{steps}** and are forced to step back...\n"
                    f"➡️ You land on **Tile {target_idx}**."
                ),
                color=discord.Color.dark_red()
            )

            card_path = os.path.join("images", "loki.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)

                # Re-open for logging
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await interaction.followup.send(embed=embed)
                await log_transaction(interaction.guild, embed=embed)

            # --- Trigger landing effect ---
            player_row = await get_player(db, guild_id, user)
            if player_row:
                await process_landing(interaction, db, player_row, 0)

            return

        if effect == "gotojail":
            jail_idx = 10  # San Quentin Jail tile index

            # 🔹 Check if player has a Get Out of Jail Free card
            async with db.execute(
                    "SELECT jail_free_cards FROM players WHERE guild_id=? AND user_id=?",
                    (guild_id, user.id)
            ) as cur:
                row = await cur.fetchone()
                cards = row[0] if row else 0

            if cards > 0:
                # Consume one card and skip jail
                await db.execute(
                    "UPDATE players SET jail_free_cards = jail_free_cards - 1 WHERE guild_id=? AND user_id=?",
                    (guild_id, user.id)
                )
                await db.commit()

                embed = discord.Embed(
                    title="🎴 Gamble Card — Cash Crew Snitch",
                    description=(
                        f"🚨 The Cash Crew tried to rat out {user.mention}, but Athena’s wisdom prevailed!\n\n"
                        f"🆓 You used a **Get Out of Jail Free** card from Athena and avoided capture."
                    ),
                    color=discord.Color.green()
                )
            else:
                # No card → send player to jail
                await set_position(db, guild_id, user.id, jail_idx)
                jailed_until = human_now() + 24 * 3600  # 24 hours
                await db.execute(
                    "UPDATE players SET jailed_until=? WHERE guild_id=? AND user_id=?",
                    (jailed_until, guild_id, user.id)
                )
                await db.commit()

                embed = discord.Embed(
                    title="🎴 Gamble Card — Cash Crew Snitch",
                    description=(
                        f"🚨 Cash Crew’s heist went wrong and {user.mention} got snitched on!\n"
                        f"You are sent **directly to San Quentin xWays Jail** for 24 hours.\n"
                        f"Do not pass GO, do not collect $200."
                    ),
                    color=discord.Color.red()
                )

            # --- Embed + image ---
            card_path = os.path.join("images", "cash_crew.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)

                # Re-open for logging
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await interaction.followup.send(embed=embed)
                await log_transaction(interaction.guild, embed=embed)

            return

        if effect == "letax":
            # Count properties owned by this player
            async with db.execute(
                    "SELECT COUNT(*) FROM properties WHERE guild_id=? AND owner_id=?",
                    (guild_id, user.id)
            ) as cur:
                owned_count = (await cur.fetchone())[0]

            tribute = owned_count * 50

            # Fetch current pool
            async with db.execute("SELECT slot_prize_pool FROM game_state WHERE guild_id=?", (guild_id,)) as cur:
                row = await cur.fetchone()
            pool = row[0] if row else 0

            if tribute > 0:
                # Deduct from player
                new_bal = await update_balance(
                    db, guild_id, user.id, -tribute,
                    f"Le Bandit’s Cut — Tribute Theft (${50} × {owned_count})"
                )

                # Add to prize pool
                new_pool = pool + tribute
                await db.execute(
                    "UPDATE game_state SET slot_prize_pool=? WHERE guild_id=?",
                    (new_pool, guild_id)
                )
                await db.commit()
            else:
                new_bal = await update_balance(
                    db, guild_id, user.id, 0,
                    "Le Bandit’s Cut — No properties to steal from"
                )
                new_pool = pool  # unchanged

            # --- Embed + image ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Le Bandit’s Cut!",
                description=(
                    f"🃏 Le Bandit snickers at {user.mention}!\n"
                    f"💸 He takes **$50** from each property you own.\n\n"
                    f"🏠 Properties owned: **{owned_count}**\n"
                    f"💰 Tribute Paid: <:coin:1418612412885635206> **${tribute:,} Coins**\n"
                    f"💳 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**\n"
                    f"🏦 Slot Prize Pool Updated: <:coin:1418612412885635206> **${new_pool:,} Coins**"
                ),
                color=discord.Color.dark_red()
            )

            card_path = os.path.join("images", "le_bandit.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)

                # Re-open for logging
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await interaction.followup.send(embed=embed)
                await log_transaction(interaction.guild, embed=embed)

            return

        if effect == "extra_turn":
            # Show card message
            embed = discord.Embed(
                title="🎴 Gamble Card — Mustang Gold Respin!",
                description=(
                    f"🐎 The wild Mustang bursts forward, blessing {user.mention}!\n\n"
                    "🎲 You gain an **extra turn** with a single dice roll!"
                ),
                color=discord.Color.gold()
            )

            card_path = os.path.join("images", "mustang_gold.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)
                # re-open file for logging
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await interaction.followup.send(embed=embed)
                await log_transaction(interaction.guild, embed=embed)

            # Roll 1 dice for the extra turn
            extra_roll = random.randint(1, 6)

            # Move player forward
            new_pos = (player_row["position"] + extra_roll) % 40
            await set_position(db, guild_id, user.id, new_pos)

            # Update last_roll for cooldowns etc.
            await db.execute(
                "UPDATE players SET last_roll=? WHERE guild_id=? AND user_id=?",
                (int(time.time()), guild_id, user.id)
            )
            await db.commit()

            # Announce movement
            await interaction.followup.send(
                f"🎲 {user.mention} rolls a **{extra_roll}** and moves to **Tile {new_pos}**!"
            )

            # Trigger the effect of the new tile
            player_row = await get_player(db, guild_id, user)
            if player_row:
                await process_landing(interaction, db, player_row, 0)

            return

        if effect == "pay_each":
            # Fetch all players in this guild
            async with db.execute(
                    "SELECT user_id, coins, jailed_until FROM players WHERE guild_id=?",
                    (guild_id,)
            ) as cur:
                all_players = await cur.fetchall()

            if not all_players or len(all_players) < 2:
                await interaction.followup.send(
                    f"⚠️ {user.mention}, you’re the only player here — no tribute to split."
                )
                return

            now = human_now()
            balances = {row[0]: row[1] for row in all_players}  # coins
            jailed_status = {row[0]: row[2] for row in all_players}

            total_tribute = 0
            tribute_lines = []

            for uid in balances.keys():
                if uid == user.id:
                    continue  # skip drawer

                if jailed_status.get(uid) and jailed_status[uid] > now:
                    tribute_lines.append(f"<@{uid}> ❌ (In Jail — No Tribute)")
                    continue  # skip jailed players

                # Active player → receive tribute
                balances[uid] += 10
                tribute_lines.append(f"<@{uid}> ✅ +10 → 💰 {balances[uid]} AJ")
                total_tribute += 10

            if total_tribute == 0:
                await interaction.followup.send(
                    f"⚠️ All other players are jailed, {user.mention}. No tribute to pay!"
                )
                return

            # Deduct from drawer
            balances[user.id] -= total_tribute

            # Write back to DB
            for uid, new_balance in balances.items():
                await db.execute(
                    "UPDATE players SET coins=? WHERE guild_id=? AND user_id=?",
                    (new_balance, guild_id, uid)
                )
            await db.commit()

            # --- Build Embed ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Pirate Treasure Split Tribute!",
                description=(
                        f"🏴‍☠️ {user.mention} must share the loot!\n\n"
                        f"💰 **Total Loot Shared:** <:coin:1418612412885635206> **{total_tribute} Coins** "
                        f"(10 AJ to each free matey)\n\n"
                        f"💸 Tribute Results:\n" + "\n".join(tribute_lines) +
                        f"\n\n📉 {user.mention} now has <:coin:1418612412885635206> **{balances[user.id]} Coins**."
                ),
                color=discord.Color.dark_gold()
            )

            card_path = os.path.join("images", "pirate_bonanza.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)

                # re-open for logging
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await interaction.followup.send(embed=embed)
                await log_transaction(interaction.guild, embed=embed)

            return

        if effect == "slot_prize":
            async with db.execute("SELECT slot_prize_pool FROM game_state WHERE guild_id=?", (guild_id,)) as cur:
                row = await cur.fetchone()
            pool = row[0] if row else 0

            # --- Embed setup ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Lucky Penny’s Gift!",
                description="🍀 Lucky Penny beams with fortune: *‘Take 25% of the Slot Prize Pool — may luck keep shining on you!’*\n",
                color=discord.Color.green()
            )

            if pool > 0:
                reward_percentage = 0.25
                reward = int(pool * reward_percentage)
                remaining = pool - reward

                # Update balance and fetch new balance
                new_balance = await update_balance(db, guild_id, user.id, reward, "Slot Rewards Prize")
                await db.execute(
                    "UPDATE game_state SET slot_prize_pool = ? WHERE guild_id=?",
                    (remaining, guild_id)
                )
                await db.commit()

                embed.description += (
                    f"\n💰 **Total Tax Prize Pool:** <:coin:1418612412885635206> ${pool} Coins\n"
                    f"🎰 {user.mention} claimed **{int(reward_percentage * 100)}% = <:coin:1418612412885635206> ${reward} Coins!**\n"
                    f"🏦 **Remaining Pool:** <:coin:1418612412885635206> ${remaining} Coins\n"
                    f"💳 **Updated Balance:** <:coin:1418612412885635206> ${new_balance} Coins"
                )
            else:
                embed.description += "\n🎰 The Slot Prize Pool is empty!"

            # --- Card artwork ---
            card_path = os.path.join("images", "lucky_penny.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)

                # re-open for logging
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await interaction.followup.send(embed=embed)
                await log_transaction(interaction.guild, embed=embed)

            return

        if effect == "rent_reversal":
            old_pos = player_row["position"]

            # --- Roll 2 dice ---
            die1, die2 = random.randint(1, 6), random.randint(1, 6)
            steps = die1 + die2
            target_idx = (old_pos + steps) % 40

            # Update position
            await db.execute(
                "UPDATE players SET position=? WHERE guild_id=? AND user_id=?",
                (target_idx, guild_id, user.id)
            )
            await db.commit()

            sq = SLOT_BOARD[target_idx]

            # --- First announcement (plain text) ---
            await interaction.followup.send(
                f"🎴 Gamble Card — Evil Eyes Curse!\n"
                f"👁️ The Evil Eyes glare upon {user.mention}...\n\n"
                f"🔮 Please roll another dice and watch the curse!"
            )

            # --- Dice roll + movement (embed) ---
            move_embed = discord.Embed(
                title="🎴 Gamble Card — Evil Eyes Curse!",
                description=(
                    f"👁️ The Evil Eyes glare upon {user.mention}...\n\n"
                    f"🎲 You rolled **{die1} + {die2} = {steps}** and moved to **{sq['name']} (Tile {target_idx})**.\n"
                    f"🔮 If it’s owned, the owner pays you instead!"
                ),
                color=discord.Color.dark_purple()
            )

            card_path = os.path.join("images", "evil_eyes.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                move_embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=move_embed, file=file1)

                # re-open for logging
                file2 = discord.File(card_path, filename="card.png")
                move_embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=move_embed, file=file2)
            else:
                await interaction.followup.send(embed=move_embed)
                await log_transaction(interaction.guild, embed=move_embed)

            # --- Handle tile logic ---
            if sq["type"] in ("property", "provider", "utility"):
                # Check if tile is owned
                async with db.execute(
                        "SELECT owner_id FROM properties WHERE guild_id=? AND idx=?",
                        (guild_id, target_idx)
                ) as cur:
                    row = await cur.fetchone()

                if row and row[0]:
                    owner_id = row[0]
                    if owner_id == user.id:
                        await interaction.followup.send(
                            f"👁️ The curse fizzles... {user.mention} already owns **{sq['name']}**!"
                        )
                    else:
                        # --- Reverse rent: owner pays roller ---
                        base_rent = sq.get("rent", 10)
                        rent = base_rent

                        # Full group multiplier
                        multiplier = 2 if await full_group_owned(db, guild_id, sq.get("group", ""), owner_id) else 1
                        rent *= multiplier

                        # Utility special rent
                        if sq["type"] == "utility":
                            util_die1, util_die2 = random.randint(1, 6), random.randint(1, 6)
                            util_roll = util_die1 + util_die2
                            idxs = PROPERTY_GROUPS.get("utility", [])
                            placeholders = ",".join(["?"] * len(idxs))
                            async with db.execute(
                                    f"SELECT COUNT(*) FROM properties WHERE guild_id=? AND idx IN ({placeholders}) AND owner_id=?",
                                    (guild_id, *idxs, owner_id)
                            ) as cur:
                                util_count = (await cur.fetchone())[0]
                            rent = 4 * util_roll if util_count == 1 else 10 * util_roll

                        # Transfer rent reversed
                        new_bal_user = await update_balance(
                            db, guild_id, user.id, rent,
                            f"Rent Reversal from {sq['name']}"
                        )
                        new_bal_owner = await update_balance(
                            db, guild_id, owner_id, -rent,
                            f"Rent Reversal payment on {sq['name']}"
                        )
                        await db.commit()

                        # --- Rent Reversal Embed ---
                        pay_embed = discord.Embed(
                            title="👁️ Evil Eyes Curse — Rent Reversal!",
                            description=(
                                f"<@{owner_id}> pays {user.mention} <:coin:1418612412885635206> **${rent} Coins** for landing on **{sq['name']}**!\n\n"
                                f"💳 {user.mention} Balance: <:coin:1418612412885635206> ${new_bal_user} Coins\n"
                                f"💳 <@{owner_id}> Balance: <:coin:1418612412885635206> ${new_bal_owner} Coins"
                            ),
                            color=discord.Color.dark_purple()
                        )

                        if os.path.exists(card_path):
                            file1 = discord.File(card_path, filename="card.png")
                            pay_embed.set_thumbnail(url="attachment://card.png")
                            await interaction.followup.send(embed=pay_embed, file=file1)

                            # re-open for logging
                            file2 = discord.File(card_path, filename="card.png")
                            pay_embed.set_thumbnail(url="attachment://card.png")
                            await log_transaction(interaction.guild, embed=pay_embed, file=file2)
                        else:
                            await interaction.followup.send(embed=pay_embed)
                            await log_transaction(interaction.guild, embed=pay_embed)
                else:
                    # Tile unowned → player can buy
                    await interaction.followup.send(
                        f"💎 {user.mention}, **{sq['name']}** is unowned!\n"
                        f"You may purchase it for <:coin:1418612412885635206> ${sq['price']} Coins."
                    )

            else:
                # --- Special tiles fallback ---
                player_row = await get_player(db, guild_id, user)
                if player_row:
                    await process_landing(interaction, db, player_row, 0)

            return

        if effect == "birthday":
            # Fetch all players in this guild
            async with db.execute(
                    "SELECT user_id, coins, jailed_until FROM players WHERE guild_id=?",
                    (guild_id,)
            ) as cur:
                all_players = await cur.fetchall()

            if not all_players or len(all_players) < 2:
                await interaction.followup.send(
                    f"⚠️ {user.mention}, you’re the only player here — no birthday donations."
                )
                return

            now = human_now()
            balances = {row[0]: row[1] for row in all_players}
            jailed_status = {row[0]: row[2] for row in all_players}

            total_donation = 0
            tribute_lines = []

            # Each player donates, except the birthday celebrant
            for uid in balances.keys():
                if uid == user.id:
                    continue  # skip birthday celebrant

                donation = 10
                if jailed_status.get(uid) and jailed_status[uid] > now:
                    donation = 20  # jailed players donate double

                balances[uid] -= donation
                balances[user.id] += donation
                total_donation += donation

                tribute_lines.append(
                    f"<@{uid}> 💸 -${donation} → 💰 {balances[uid]} AJ"
                    + (" (⚖️ Jailed x2)" if donation == 20 else "")
                )

            # Write updated balances back to DB
            for uid, new_balance in balances.items():
                await db.execute(
                    "UPDATE players SET coins=? WHERE guild_id=? AND user_id=?",
                    (new_balance, guild_id, uid)
                )
            await db.commit()

            # --- Build Embed ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Wild Beach Birthday Bash!",
                description=(
                        f"🎉 The Wild Beach Party becomes {user.mention}'s Jackpot Birthday!\n\n"
                        f"🥳 Every player donates to the celebration:\n"
                        + "\n".join(tribute_lines)
                        + f"\n\n🎁 {user.mention} received a total of <:coin:1418612412885635206> **${total_donation} Coins**!\n"
                          f"💳 Updated Balance: <:coin:1418612412885635206> **{balances[user.id]} Coins**"
                ),
                color=discord.Color.orange()
            )

            card_path = os.path.join("images", "wild_beach_party.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)

                # re-open for logging
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await interaction.followup.send(embed=embed)
                await log_transaction(interaction.guild, embed=embed)

            return

        if effect == "insurance":
            # Count player properties (property, provider, utility all count)
            async with db.execute(
                    "SELECT COUNT(*) FROM properties WHERE guild_id=? AND owner_id=?",
                    (guild_id, user.id)
            ) as cur:
                owned_count = (await cur.fetchone())[0]

            if owned_count == 0:
                await interaction.followup.send(
                    f"⚠️ {user.mention}, you don’t own any properties — no hazard pay awarded."
                )
                return

            # Fetch current slot prize pool
            async with db.execute("SELECT slot_prize_pool FROM game_state WHERE guild_id=?", (guild_id,)) as cur:
                row = await cur.fetchone()
            pool = row[0] if row else 0

            reward = 50 * owned_count

            if pool <= 0:
                await interaction.followup.send(
                    f"💀 {user.mention}, the Slot Prize Pool is empty — no hazard pay this time!"
                )
                return

            # Cap reward if pool is smaller than required
            actual_reward = min(reward, pool)
            remaining = pool - actual_reward

            # Apply balance update
            new_balance = await update_balance(db, guild_id, user.id, actual_reward, "Infective Claim Hazard Pay")
            await db.execute(
                "UPDATE game_state SET slot_prize_pool = ? WHERE guild_id=?",
                (remaining, guild_id)
            )
            await db.commit()

            # --- Build Embed ---
            embed = discord.Embed(
                title="🎴 Gamble Card — Infective Claim Bonus!",
                description=(
                    f"🦠 The lab pays hazard compensation to {user.mention}!\n\n"
                    f"🏠 Properties owned: **{owned_count}**\n"
                    f"💰 Hazard Pay: **${50} × {owned_count} = <:coin:1418612412885635206> ${reward} Coins**\n"
                    f"⚖️ Adjusted Payout (due to prize pool): <:coin:1418612412885635206> **${actual_reward} Coins**\n\n"
                    f"💳 Updated Balance: <:coin:1418612412885635206> **{new_balance} Coins**\n"
                    f"🏦 Slot Prize Pool Remaining: <:coin:1418612412885635206> **${remaining} Coins**"
                ),
                color=discord.Color.teal()
            )

            card_path = os.path.join("images", "infective_wild.png")
            if os.path.exists(card_path):
                file1 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file1)

                # re-open for logging
                file2 = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
                await log_transaction(interaction.guild, embed=embed, file=file2)
            else:
                await interaction.followup.send(embed=embed)
                await log_transaction(interaction.guild, embed=embed)

            return

    # Properties, Providers, Utilities
    if sq["type"] in ("property", "provider", "utility"):
        owner_id = await get_owner(db, guild_id, pos)

        # 🔹 Unowned property → Offer to buy
        if owner_id is None:
            price = sq.get("price", 100)
            view = BuyPassView(owner_user_id=user.id)

            await interaction.followup.send(
                f"🎲 {user.mention} rolled **{roll}** and landed on **{sq['name']}** (Price: ${price}).\n"
                f"Do you want to buy it?",
                view=view
            )
            await view.wait()
            choice = view.choice or "pass"

            if choice == "buy":
                # Deduct price (can go negative)
                new_bal = await update_balance(db, guild_id, user.id, -price, f"Bought {sq['name']}")
                await db.execute(
                    "UPDATE properties SET owner_id=? WHERE guild_id=? AND idx=?",
                    (user.id, guild_id, pos)
                )
                await db.commit()

                # 🔍 Calculate projected total weekly tax for all owners
                async with db.execute("""
                    SELECT pr.idx
                    FROM properties pr
                    WHERE pr.guild_id=? AND pr.owner_id IS NOT NULL
                """, (guild_id,)) as cur:
                    owned_props = await cur.fetchall()

                total_value = sum(
                    next((sq["price"] for sq in SLOT_BOARD if sq["idx"] == row["idx"]), 0)
                    for row in owned_props
                )
                projected_weekly_tax = int(total_value * 0.1)

                # 🎰 Projected prize pool (current pool + projected weekly tax)
                async with db.execute("SELECT slot_prize_pool FROM game_state WHERE guild_id=?", (guild_id,)) as cur:
                    row = await cur.fetchone()
                current_pool = row["slot_prize_pool"] if row else 0
                projected_pool = current_pool + projected_weekly_tax

                # 🎁 Claimable amount (25% of projected pool)
                claimable_share = int(projected_pool * 0.25)

                # 📜 Transaction embed
                embed = discord.Embed(
                    title=f"🏠 Property Bought — {sq['name']}",
                    description=(
                        f"{user.mention} purchased **{sq['name']}** for <:coin:1418612412885635206> **${price:,.2f} Coins**!\n\n"
                        f"💳 Updated Balance: <:coin:1418612412885635206> **${new_bal:,.2f} Coins**\n\n"
                        f"🏦 Server Projected Weekly Tax (10%): <:coin:1418612412885635206> **${projected_weekly_tax:,.2f} Coins**\n"
                        f"🎰 Slot Rewards Pool: <:coin:1418612412885635206> **${current_pool:,.2f} Coins**\n"
                    ),
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=user.display_avatar.url)

                # If property has tile artwork, attach it properly
                tile_image = sq.get("image")
                if tile_image and os.path.exists(tile_image):
                    file = discord.File(tile_image, filename="tile.png")
                    embed.set_thumbnail(url="attachment://tile.png")
                    await log_transaction(interaction.guild, embed=embed, file=file)
                else:
                    await log_transaction(interaction.guild, embed=embed)

            else:
                await interaction.followup.send(f"❌ {user.mention} passed on **{sq['name']}**.")
            return

        # 🔹 Player landed on their own property
        if owner_id == user.id:
            await interaction.followup.send(f"🏠 {user.mention} landed on their own Property **{sq['name']}**.")
            return

        # base rent + color group bonus
        base_rent = sq.get("rent", 10)
        multiplier = 2 if await full_group_owned(db, guild_id, sq.get("group", ""), owner_id) else 1
        rent = base_rent * multiplier

        # utility logic (overrides base rent)
        if sq["type"] == "utility":
            if utility_card:
                # Special rule: roll 2 dice × 10
                dice1 = random.randint(1, 6)
                dice2 = random.randint(1, 6)
                dice_total = dice1 + dice2
                rent = dice_total * 10

                await interaction.followup.send(
                    f"🎲 Madame Destiny rolls the dice for {user.mention}: **{dice1} + {dice2} = {dice_total}**\n"
                    f"🔮 Rent is <:coin:1418612412885635206> **{rent} Coins**!"
                )
            else:
                # Default Monopoly utility rent (based on roll & # of utilities owned)
                idxs = PROPERTY_GROUPS.get("utility", [])
                placeholders = ",".join(["?"] * len(idxs))
                async with db.execute(
                        f"SELECT COUNT(*) FROM properties WHERE guild_id=? AND idx IN ({placeholders}) AND owner_id=?",
                        (guild_id, *idxs, owner_id)
                ) as cur:
                    util_count = (await cur.fetchone())[0]

                rent = 4 * roll if util_count == 1 else 10 * roll

        # Provider logic: 1→25, 2→50, 3→100, 4→200
        if sq["type"] == "provider":
            idxs = PROPERTY_GROUPS.get("provider", [])
            placeholders = ",".join(["?"] * len(idxs))
            async with db.execute(
                    f"SELECT COUNT(*) FROM properties WHERE guild_id=? AND idx IN ({placeholders}) AND owner_id=?",
                    (guild_id, *idxs, owner_id)
            ) as cur:
                c = (await cur.fetchone())[0]
            rent = [0, 25, 50, 100, 200][min(c, 4)]

        if double_rent:
            rent *= 2

        # Apply rent transaction
        payer_bal = await update_balance(db, guild_id, user.id, -rent, f"Rent to {owner_id} for {sq['name']}")
        owner_bal = await update_balance(db, guild_id, owner_id, rent, f"Rent from {user.id} for {sq['name']}")
        await db.commit()

        # 👤 Only the payer sees this in the game channel
        payer_msg = (
            f"💰 {user.mention} landed on **{sq['name']}** and paid **${rent}** rent to <@{owner_id}>.\n"
            f"💳 Updated Balance: **${payer_bal:,.2f}**"
        )
        await interaction.followup.send(payer_msg)

        # 📜 Combined log for the transactions channel (embed w/ tile artwork)
        embed = discord.Embed(
            title=f"🏠 Rent Paid — {sq['name']}",
            description=(
                f"💸 <@{owner_id}> received **${rent:,.2f}** rent from {user.mention}.\n\n"
                f"**Updated Balances:**\n"
                f"💳 <@{owner_id}>: **${owner_bal:,.2f}**\n"
                f"💳 {user.mention}: **${payer_bal:,.2f}**"
            ),
            color=discord.Color.gold()
        )

        tile_image = sq.get("image")
        if tile_image and os.path.exists(tile_image):
            file = discord.File(tile_image, filename="tile.png")
            embed.set_thumbnail(url="attachment://tile.png")
            await log_transaction(interaction.guild, embed=embed, file=file)
        else:
            await log_transaction(interaction.guild, embed=embed)

        return

class GiveawayView(discord.ui.View):
    def __init__(self, guild_id, message_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.message_id = message_id
        self.entries = set()  # store user_ids

    @discord.ui.button(
        label="🎲 Join Giveaway",
        style=discord.ButtonStyle.green,
        custom_id="giveaway_join"
    )
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        role_ids = [r.id for r in member.roles]

        if ELIGIBLE_ROLE_ID not in role_ids:
            await interaction.response.send_message(
                "⚠️ You’re not eligible for this giveaway.",
                ephemeral=True
            )
            return

        if member.id in self.entries:
            await interaction.response.send_message(
                "✅ You’re already entered!",
                ephemeral=True
            )
            return

        # Add to memory + DB
        self.entries.add(member.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO giveaway_entries (guild_id, message_id, user_id) VALUES (?, ?, ?)",
                (self.guild_id, self.message_id, member.id)
            )
            await db.commit()

        # ✅ Tell the user right away
        await interaction.response.send_message(
            f"🎉 {member.mention} joined the giveaway!",
            ephemeral=True
        )

        # Update embed with entry count
        channel = interaction.client.get_channel(GIVEAWAY_CHANNEL_ID)
        try:
            msg = await channel.fetch_message(self.message_id)
            if msg.embeds:
                embed = msg.embeds[0]
                embed.set_footer(text=f"🎲 Entries: {len(self.entries)}")
                await msg.edit(embed=embed, view=self)
        except Exception as e:
            print(f"⚠️ Failed to update giveaway message: {e}")


def seconds_until_midnight_utc():
    now = datetime.now(timezone.utc)
    target = now.replace(hour=6, minute=05, second=00, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def seconds_until_draw():
    now = datetime.now(timezone.utc)
    target = now.replace(hour=6, minute=0, second=00, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()

async def scheduler_once():
    # wait until next target time (15:07:30 for testing, 00:00 UTC in prod)
    await asyncio.sleep(seconds_until_midnight_utc())
    await start_daily_giveaway()
    # schedule next run every 24h
    daily_giveaway_scheduler.start()

@tasks.loop(hours=24)
async def daily_giveaway_scheduler():
    await start_daily_giveaway()

async def start_daily_giveaway():
    channel = bot.get_channel(GIVEAWAY_CHANNEL_ID)
    if not channel:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()

        today = date.today().isoformat()
        async with db.execute(
            "SELECT message_id FROM daily_giveaway WHERE guild_id=? AND giveaway_date=?",
            (channel.guild.id, today)
        ) as cur:
            exists = await cur.fetchone()
        if exists:
            return  # already posted today

        embed = discord.Embed(
            title="🎉 Daily Free Roll Giveaway!",
            description=(
                f"Members with <@&{ELIGIBLE_ROLE_ID}> can join by clicking below!\n\n"
                f"🏆 **{WINNERS_COUNT} Winners** will each get **+1 Free Roll**!\n\n"
                f"⏰ Winners drawn automatically at **<t:1758585900:t>** tomorrow."
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="🎲 Entries: 0")

        view = GiveawayView(channel.guild.id, 0)
        msg = await channel.send(embed=embed, view=view)

        view.message_id = msg.id
        ACTIVE_GIVEAWAYS[channel.guild.id] = view

        await db.execute(
            "INSERT OR REPLACE INTO daily_giveaway (guild_id, message_id, giveaway_date) VALUES (?, ?, ?)",
            (channel.guild.id, msg.id, today)
        )
        await db.commit()

        # Schedule drawing at next midnight
        asyncio.create_task(draw_winners_at_midnight(channel.guild.id, msg.id))

async def draw_winners_at_midnight(guild_id, message_id):
    await asyncio.sleep(seconds_until_draw())

    guild = bot.get_guild(guild_id)
    if not guild:
        return
    channel = guild.get_channel(GIVEAWAY_CHANNEL_ID)
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return

    view = ACTIVE_GIVEAWAYS.get(guild_id)
    if not view:
        return

    entries = list(view.entries)
    if not entries:
        await channel.send("⚠️ No eligible participants in today’s giveaway.")
        return

    winners = random.sample(entries, min(WINNERS_COUNT, len(entries)))

    async with aiosqlite.connect(DB_PATH) as db:
        for winner_id in winners:
            await db.execute(
                "UPDATE players SET rolls_left = COALESCE(rolls_left, 0) + 1 WHERE guild_id=? AND user_id=?",
                (guild.id, winner_id)
            )
        await db.commit()

    winner_mentions = ", ".join(f"<@{w}>" for w in winners)
    await channel.send(
        f"🎉 Congratulations {winner_mentions}!\n"
        f"You each won **+1 Free Roll** from the daily giveaway! 🎲"
    )

    # Log winners + updated rolls
    if log_channel:
        async with aiosqlite.connect(DB_PATH) as db:
            lines = []
            for winner_id in winners:
                async with db.execute(
                    "SELECT rolls_left FROM players WHERE guild_id=? AND user_id=?",
                    (guild.id, winner_id)
                ) as cur:
                    row = await cur.fetchone()
                rolls = row[0] if row else 0
                lines.append(f"<@{winner_id}> → 🎲 Rolls Left: **{rolls}**")
            log_text = "\n".join(lines)

        log_embed = discord.Embed(
            title="📜 Daily Free Roll Winners",
            description=log_text,
            color=discord.Color.blue()
        )
        await log_channel.send(embed=log_embed)

    # Disable button after drawing
    for item in view.children:
        item.disabled = True
    try:
        msg = await channel.fetch_message(message_id)
        await msg.edit(view=view)
    except:
        pass

@tasks.loop(hours=168)  # every 7 days
async def collect_slot_owner_tax():
    now = int(datetime.now(timezone.utc).timestamp())  # Current UTC time

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT guild_id, last_tax_collection FROM game_state") as cur:
            guilds = await cur.fetchall()

        for g in guilds:
            guild_id = g["guild_id"]
            last_collected = g["last_tax_collection"] or 0

            # 🔥 Skip if tax collected less than 7 days ago
            if now - last_collected < 7 * 24 * 3600:
                print(f"⏩ Skipping tax for guild {guild_id}, already collected this week.")
                continue

            tax_total = 0
            tax_details = []
            repossessed = []  # Track repossessions

            async with db.execute(
                "SELECT user_id, coins FROM players WHERE guild_id=?", (guild_id,)
            ) as cur:
                players = await cur.fetchall()

            for p in players:
                user_id = p["user_id"]
                current_coins = p["coins"]

                # Get owned properties
                async with db.execute(
                    "SELECT idx FROM properties WHERE guild_id=? AND owner_id=?",
                    (guild_id, user_id),
                ) as cur:
                    owned = await cur.fetchall()

                if not owned:
                    continue

                # Calculate total property value & tax
                owned_idxs = [o["idx"] for o in owned]
                total_value = sum(
                    next((sq["price"] for sq in SLOT_BOARD if sq["idx"] == idx), 0)
                    for idx in owned_idxs
                )
                tax = int(total_value * 0.1)
                tax_total += tax
                prop_count = len(owned)

                if current_coins >= tax:
                    # ✅ Player can pay tax
                    await db.execute(
                        "UPDATE players SET coins = coins - ? WHERE guild_id=? AND user_id=?",
                        (tax, guild_id, user_id),
                    )
                    await add_tx(db, guild_id, user_id, -tax, "Weekly Slot Owner Tax")
                    tax_details.append((user_id, prop_count, tax))
                else:
                    # ❌ Player cannot pay → Repo all properties
                    # Pay player their total property value
                    await db.execute(
                        "UPDATE players SET coins = coins + ? WHERE guild_id=? AND user_id=?",
                        (total_value, guild_id, user_id),
                    )
                    await add_tx(db, guild_id, user_id, total_value, "Bank repossessed all properties")

                    # Remove ownership
                    await db.execute(
                        "UPDATE properties SET owner_id=NULL WHERE guild_id=? AND owner_id=?",
                        (guild_id, user_id),
                    )

                    # Deduct tax after repossession
                    await db.execute(
                        "UPDATE players SET coins = coins - ? WHERE guild_id=? AND user_id=?",
                        (tax, guild_id, user_id),
                    )
                    await add_tx(db, guild_id, user_id, -tax, "Weekly Slot Owner Tax (post-repo)")

                    # Track repossessed slots for announcement
                    slot_names = [sq["name"] for sq in SLOT_BOARD if sq["idx"] in owned_idxs]
                    repossessed.append((user_id, slot_names))
                    tax_details.append((user_id, prop_count, tax))

            # Add weekly tax to prize pool
            await db.execute(
                "UPDATE game_state SET slot_prize_pool = slot_prize_pool + ?, last_tax_collection=? WHERE guild_id=?",
                (tax_total, now, guild_id),
            )
            await db.commit()

            # Get updated total pool
            async with db.execute(
                "SELECT slot_prize_pool FROM game_state WHERE guild_id=?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
                total_pool = row["slot_prize_pool"] if row else tax_total

            # Build announcement
            breakdown_lines = [
                f"• <@{uid}> owns **{count} slots** — paid <:coin:1418612412885635206> **${tax} Coins**"
                for uid, count, tax in tax_details
            ]
            breakdown_msg = "\n".join(breakdown_lines) if breakdown_lines else "No slot owners were taxed this week."

            repo_lines = [
                f"💥 <@{uid}> had these properties repossessed: {', '.join(slots)}"
                for uid, slots in repossessed
            ]
            if repo_lines:
                repo_lines.append(
                    "\n🏷️ All these properties are now **available to purchase** for whoever lands on them first!")
            repo_msg = "\n".join(repo_lines) if repo_lines else ""

            channel = bot.get_channel(TAX_ANNOUNCE_CHANNEL_ID)
            if channel:
                claimable_share = int(total_pool * 0.25)  # 25% of updated pool

                await channel.send(
                    f"🏦 **Weekly Slot Owner Tax Collected!**\n"
                    f"💰 **This Week's Total Tax:** <:coin:1418612412885635206> ${tax_total:,.2f} Coins\n"
                    f"🎰 **Total Slot Rewards Prize Pool:** <:coin:1418612412885635206> ${total_pool:,.2f} Coins\n"
                    f"💵 **Claimable per Reward Card (25%):** <:coin:1418612412885635206> ${claimable_share:,.2f} Coins\n\n"
                    f"📜 **Breakdown:**\n{breakdown_msg}\n\n"
                    f"{repo_msg}"
                )


@collect_slot_owner_tax.before_loop
async def before_tax_loop():
    await bot.wait_until_ready()

    now = datetime.now(timezone.utc)  # ✅ Get current time in UTC

    # 🔥 Change target_day from 0 (Monday) to 1 (Tuesday)
    target_day = 0  # 0 = Monday, 1 = Tuesday, ..., 6 = Sunday
    days_ahead = (target_day - now.weekday()) % 7
    next_target = now + timedelta(days=days_ahead)
    next_target = next_target.replace(hour=0, minute=00, second=00, microsecond=0)

    wait_seconds = (next_target - now).total_seconds()
    print(f"⏳ Waiting {wait_seconds / 3600:.2f} hours until first tax collection...")
    await asyncio.sleep(wait_seconds)


@bot.tree.command(name="monopoly_join", description="Join Aaron Jay's Monopoly and receive starting AJ Coins.")
async def monopoly_join(interaction: discord.Interaction):
    allowed_channel_id = 1419677495271096470  # ✅ Monopoly join channel

    # Check if used in the correct channel
    if interaction.channel.id != allowed_channel_id:
        allowed_channel = interaction.guild.get_channel(allowed_channel_id)
        await interaction.response.send_message(
            f"⚠️ You can only join Monopoly in {allowed_channel.mention}.",
            ephemeral=True  # keep this private so it doesn’t spam other channels
        )
        return

    await interaction.response.defer()  # 👈 public response
    await ensure_guild_state(interaction.guild_id)

    async with aiosqlite.connect(DB_PATH) as db:
        # Insert if new
        await db.execute(
            "INSERT OR IGNORE INTO players (guild_id, user_id, username, coins, position, jailed_until, last_roll) "
            "VALUES (?, ?, ?, ?, 0, 0, 0)",
            (interaction.guild_id, interaction.user.id, str(interaction.user), STARTING_COINS)
        )
        # Update username on rejoin
        await db.execute(
            "UPDATE players SET username=? WHERE guild_id=? AND user_id=?",
            (str(interaction.user), interaction.guild_id, interaction.user.id)
        )
        await db.commit()

    # 🎭 Assign Monopoly role
    guild = interaction.guild
    role = guild.get_role(1419593812501594195)  # Monopoly role ID
    if role:
        try:
            await interaction.user.add_roles(role, reason="Joined Monopoly game")
        except Exception as e:
            print(f"⚠️ Could not assign role: {e}")

    # ✅ Public confirmation message in join channel
    await interaction.followup.send(
        f"🎲 {interaction.user.mention} joined the Monopoly game!\n"
        f"💰 Starting Balance: <:coin:1418612412885635206> **${STARTING_COINS:,.2f} Coins**\n"
        f"Use `/monopoly_roll` every 4 hours to play.",
    )

    # 📜 Also log to transactions channel
    embed = discord.Embed(
        title="🎉 Monopoly Join",
        description=(
            f"{interaction.user.mention} joined the Monopoly game!\n"
            f"💰 Starting Balance: <:coin:1418612412885635206> **${STARTING_COINS:,.2f} Coins**"
        ),
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    tx_channel = interaction.guild.get_channel(MONOPOLY_TRANSACTIONS_CHANNEL_ID)
    if tx_channel:
        await tx_channel.send(embed=embed)


@bot.tree.command(name="monopoly_roll", description="Roll the dice and take your turn.")
async def monopoly_roll(interaction: discord.Interaction):
    # ✅ Check if command used in the correct channel
    if interaction.channel_id != ROLL_CHANNEL_ID:
        await interaction.response.send_message(
            f"⚠️ You can’t roll here! Please go to <#{ROLL_CHANNEL_ID}> to use `/monopoly_roll`.",
            ephemeral=True
        )
        return

    if GLOBAL_ROLL_LOCK.locked():
        await interaction.response.send_message(
            "⚠️ Someone is rolling right now. Please wait a few seconds.", ephemeral=True
        )
        return

    async with GLOBAL_ROLL_LOCK:
        await interaction.response.defer()
        await ensure_guild_state(interaction.guild_id)

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            player = await get_player(db, interaction.guild_id, interaction.user)
            if not player:
                await interaction.followup.send("You are not in the game. Use `/monopoly_join` first.")
                return

            now = human_now()

            # 🚔 Jail check
            jailed_until = player["jailed_until"] if "jailed_until" in player.keys() else 0
            if jailed_until and jailed_until > now:
                mins = int((jailed_until - now) / 60)
                await interaction.followup.send(f"🚔 You're still locked up for **~{mins} minutes**. No rolls allowed!")
                return

            # 🎲 Rolls left (sqlite Row -> use keys())
            rolls_left = player["rolls_left"] if "rolls_left" in player.keys() else 0
            if rolls_left <= 0:
                await interaction.followup.send("🚫 You have **no rolls left**! Win a giveaway on Stream/Discord or a Rumble Game to earn a free roll.")
                return

            # ⏳ Cooldown check
            last_roll = player["last_roll"] or 0
            if now - last_roll < ROLL_COOLDOWN_SECONDS:
                left = ROLL_COOLDOWN_SECONDS - (now - last_roll)
                h, m, s = left // 3600, (left % 3600) // 60, left % 60
                await interaction.followup.send(f"⏳ Cooldown: **{h}h {m}m {s}s** remaining.")
                return

            # ✅ Deduct roll + set last_roll
            await db.execute(
                "UPDATE players SET rolls_left = rolls_left - 1, last_roll=? WHERE guild_id=? AND user_id=?",
                (now, interaction.guild_id, interaction.user.id)
            )
            await db.commit()

            # 🎲 Dice roll (honor forced test rolls if set)
            forced = None
            try:
                forced = FORCED_NEXT_ROLL.pop(interaction.guild_id, None)
            except Exception:
                forced = None

            if forced is not None:
                d1, d2 = forced
            else:
                d1, d2 = random.randint(1, 6), random.randint(1, 6)
            roll = d1 + d2

            old_pos = player["position"]
            # Save the tile they *landed on from the dice* — use this for the board center
            landed_idx = (old_pos + roll) % 40
            landed_tile_name = SLOT_BOARD[landed_idx]["name"]
            old_tile_name = SLOT_BOARD[old_pos]["name"]

            # Announce movement (dice result)
            await interaction.followup.send(
                f"🎲 {interaction.user.mention} rolled **{d1} + {d2} = {roll}**!\n"
                f"📍 Moving from **{old_pos} – {old_tile_name}** to **{landed_idx} – {landed_tile_name}**..."
            )

            # 🎁 Doubles reward (same logic as before)
            if d1 == d2:
                await db.execute(
                    "UPDATE players SET rolls_left = rolls_left + 1 WHERE guild_id=? AND user_id=?",
                    (interaction.guild_id, interaction.user.id),
                )
                await db.commit()
                await interaction.followup.send(
                    f"✨ {interaction.user.mention} rolled **doubles**! You earned **+1 Free Roll** 🎟️"
                )

            # Process the landing (this may move the player again via card effects)
            await process_landing(interaction, db, player, roll)

            # After landing logic is done, fetch the player's *final* position and updated stats
            async with db.execute(
                "SELECT position, rolls_left, jail_free_cards FROM players WHERE guild_id=? AND user_id=?",
                (interaction.guild_id, interaction.user.id)
            ) as cur:
                stats = await cur.fetchone()

            final_pos = stats["position"]
            rolls_left = stats["rolls_left"]
            jail_cards = stats["jail_free_cards"]

            final_tile_name = SLOT_BOARD[final_pos]["name"]

            # Build roll log: show initial landed tile and (if different) the final tile after card effects
            landed_line = f"📍 Landed on: **{landed_idx} – {landed_tile_name}**"
            if final_pos != landed_idx:
                landed_line += f" → moved to **{final_pos} – {final_tile_name}**"

            roll_embed = discord.Embed(
                title=f"🎲 Monopoly Roll — {interaction.user.display_name}",
                description=(
                    f"Rolled: **{d1} + {d2} = {roll}**\n"
                    f"{landed_line}\n\n"
                    f"🎟️ Rolls Left: **{rolls_left}**\n"
                    f"🆓 Get Out of Jail Free Cards: **{jail_cards}**"
                ),
                color=discord.Color.blue()
            )
            roll_embed.set_thumbnail(url=interaction.user.display_avatar.url)

            roll_channel = interaction.guild.get_channel(1419655999538597929)
            if roll_channel:
                await roll_channel.send(embed=roll_embed)

            # 🖼️ Updated board image — show the tile they *first landed on* (landed_idx)
            async with db.execute(
                "SELECT user_id, username, position FROM players WHERE guild_id=?",
                (interaction.guild_id,)
            ) as cur:
                guild_players = [(row[0], row[1], row[2]) for row in await cur.fetchall()]

            board_img = await render_board_with_players_avatars(
                bot, guild_players, center_tile_idx=landed_idx, dice=(d1, d2), guild_id=interaction.guild_id
            )

            buf = io.BytesIO()
            board_img.save(buf, format="PNG")
            buf.seek(0)

            await interaction.followup.send(
                f"📜 Current Monopoly board for {interaction.guild.name}:",
                file=discord.File(buf, filename="monopoly_board.png")
            )


@bot.tree.command(name="give_roll", description="(Admin) Give extra rolls to a player.")
@app_commands.describe(user="Player to give rolls to", quantity="Number of rolls to give")
async def give_roll(interaction: discord.Interaction, user: discord.Member, quantity: int):
    # 🔒 Admin check
    if interaction.user.id != 488015447417946151:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    if quantity <= 0:
        await interaction.response.send_message("❌ Quantity must be positive.", ephemeral=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # 🔍 Check if user exists in players
        async with db.execute(
            "SELECT rolls_left, jail_free_cards FROM players WHERE guild_id=? AND user_id=?",
            (interaction.guild_id, user.id)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            await interaction.response.send_message(
                f"⚠️ {user.mention} has **not joined the game yet**. They must use `/monopoly_join` first!"
            )
            return

        rolls_left, jail_free = row
        new_rolls = rolls_left + quantity

        # ✅ Update rolls
        await db.execute(
            "UPDATE players SET rolls_left = ? WHERE guild_id=? AND user_id=?",
            (new_rolls, interaction.guild_id, user.id)
        )
        await db.commit()

    # ✅ Reply to admin
    await interaction.response.send_message(
        f"✅ Gave **{quantity} free rolls** to {user.mention}.", ephemeral=False
    )

    # 🎲 Build log embed for rolls channel
    embed = discord.Embed(
        title="🎁 Extra Rolls Granted",
        description=(
            f"{user.mention} received **{quantity} Free Rolls**!\n\n"
            f"🎲 Rolls Left: **{new_rolls}**\n"
            f"🆓 Get Out of Jail Free Cards: **{jail_free}**"
        ),
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=user.display_avatar.url)

    rolls_channel = interaction.guild.get_channel(1281563200739082291)
    if rolls_channel:
        await rolls_channel.send(embed=embed)


@bot.tree.command(name="monopoly_board", description="Show the Aaron Jay's Monopoly board with player positions.")
async def monopoly_board(interaction: discord.Interaction):
    await interaction.response.defer()
    await ensure_guild_state(interaction.guild_id)

    # monopoly_board command
    if not os.path.exists(BOARD_IMAGE_PATH):
        generate_base_board(BOARD_IMAGE_PATH, include_center=True)
    else:
        generate_base_board(BOARD_IMAGE_PATH, include_center=True)  # force refresh

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, position FROM players WHERE guild_id=?",
            (interaction.guild_id,)
        ) as cur:
            players = await cur.fetchall()

    # ✅ Now it’s guaranteed to exist
    img = await render_board_with_players_avatars(
        bot, [(r[0], r[1], r[2]) for r in players], guild_id=interaction.guild_id, force_default_art=True
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    await interaction.followup.send(file=discord.File(buf, "monopoly_board.png"))


@bot.tree.command(name="monopoly_profile", description="Your AJ Coins, properties, and net worth.")
async def monopoly_profile(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    allowed_channel_id = 1419677495271096470  # ✅ Monopoly channel only

    # Channel restriction
    if interaction.channel.id != allowed_channel_id:
        allowed_channel = interaction.guild.get_channel(allowed_channel_id)
        await interaction.response.send_message(
            f"⚠️ You can only view Monopoly profiles in {allowed_channel.mention}.",
            ephemeral=True
        )
        return
    member = member or interaction.user
    await interaction.response.defer()
    await ensure_guild_state(interaction.guild_id)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        player = await get_player(db, interaction.guild_id, member)
        if not player:
            await interaction.followup.send("No profile found. Use `/monopoly_join`.", ephemeral=True)
            return

        async with db.execute(
            "SELECT idx FROM properties WHERE guild_id=? AND owner_id=? ORDER BY idx",
            (interaction.guild_id, member.id)
        ) as cur:
            owned = [r[0] for r in await cur.fetchall()]

    # Property details
    if owned:
        property_list = [SLOT_BOARD[i] for i in owned]
        names = ", ".join(p["name"] for p in property_list)
        total_income = sum(p.get("rent", 0) for p in property_list)
        total_tax = int(sum(p.get("price", 0) for p in property_list) * 0.1)
    else:
        names = "None"
        total_income = 0
        total_tax = 0

    # Build embed
    embed = discord.Embed(
        title=f"{member.display_name} — Aaron Jay's Monopoly",
        color=0x6aa6ff
    )
    embed.set_thumbnail(url=member.display_avatar.url)  # ✅ Avatar as thumbnail
    embed.add_field(name="💰 Monopoly Coins", value=f"<:coin:1418612412885635206> ${player['coins']}")
    embed.add_field(
        name="📍 Position",
        value=f"{player['position']} — {SLOT_BOARD[player['position']]['name']}",
        inline=False
    )
    embed.add_field(name="🏠 Properties", value=names, inline=False)
    embed.add_field(name="🎰 Slot Income", value=f"<:coin:1418612412885635206> ${total_income:,.2f}/visit", inline=True)
    embed.add_field(name="🏦 Weekly Tax", value=f"<:coin:1418612412885635206> ${total_tax:,.2f}/week", inline=True)

    await interaction.followup.send(embed=embed)


class LeaderboardView(View):
    def __init__(self, pages, author):
        super().__init__(timeout=120)  # auto-timeout after 2 minutes of no use
        self.pages = pages
        self.current_page = 0
        self.author = author

        # If more than 1 page, add dropdown
        if len(pages) > 1:
            options = [
                discord.SelectOption(label=f"Page {i+1}", value=str(i))
                for i in range(len(pages))
            ]
            self.add_item(PageSelect(options, self))

    async def update_page(self, interaction):
        await interaction.response.edit_message(
            embeds=self.pages[self.current_page],
            view=self
        )

    @button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ This isn’t your leaderboard to control.", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_page(interaction)
        else:
            await interaction.response.defer()

    @button(label="➡️ Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ This isn’t your leaderboard to control.", ephemeral=True)
            return
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await self.update_page(interaction)
        else:
            await interaction.response.defer()


class PageSelect(discord.ui.Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="📖 Jump to page...", options=options, row=1)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.author.id:
            await interaction.response.send_message("❌ This isn’t your leaderboard to control.", ephemeral=True)
            return

        self.parent_view.current_page = int(self.values[0])
        await self.parent_view.update_page(interaction)


@bot.tree.command(name="monopoly_leaderboard", description="Leaderboard: Top slot owners by Slot Income.")
async def monopoly_leaderboard(interaction: discord.Interaction):
    allowed_channel_id = 1419677495271096470  # ✅ Monopoly channel only

    # Channel restriction
    if interaction.channel.id != allowed_channel_id:
        allowed_channel = interaction.guild.get_channel(allowed_channel_id)
        await interaction.response.send_message(
            f"⚠️ You can only view Monopoly Leaderboard in {allowed_channel.mention}.",
            ephemeral=True
        )
        return
    await interaction.response.defer()
    await ensure_guild_state(interaction.guild_id)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("""
            SELECT user_id, coins FROM players
            WHERE guild_id=?
        """, (interaction.guild_id,)) as cur:
            players = await cur.fetchall()

        leaderboard_data = []
        for player in players:
            user_id = player["user_id"]
            coins = player["coins"]

            # Get owned properties
            async with db.execute("""
                SELECT idx FROM properties
                WHERE guild_id=? AND owner_id=?
            """, (interaction.guild_id, user_id)) as cur:
                owned_props = await cur.fetchall()

            prop_count = len(owned_props)
            total_income = 0
            total_tax = 0
            slot_names = []

            for row in owned_props:
                idx = row["idx"]
                slot = next((sq for sq in SLOT_BOARD if sq["idx"] == idx), None)
                if slot:
                    rent = slot.get("rent", 0)
                    price = slot.get("price", 0)

                    total_income += rent
                    total_tax += int(price * 0.1)  # ✅ 10% of buy cost
                    slot_names.append(f"{slot['name']} (${rent:,.2f})")

            leaderboard_data.append({
                "user_id": user_id,
                "coins": coins,
                "prop_count": prop_count,
                "slot_income": total_income,
                "weekly_tax": total_tax,  # ✅ Added this
                "slots": slot_names
            })

        # Sort by slot_income DESC, then coins DESC
        leaderboard_data.sort(key=lambda x: (x["slot_income"], x["coins"]), reverse=True)

        # Build embeds
        pages = []
        per_page = 10
        total_pages = math.ceil(len(leaderboard_data) / per_page)

        for page in range(total_pages):
            embeds = []
            chunk = leaderboard_data[page * per_page:(page + 1) * per_page]

            for i, p in enumerate(chunk, start=page * per_page + 1):
                user = interaction.guild.get_member(p["user_id"])
                avatar_url = None
                member = interaction.guild.get_member(p["user_id"])
                if member:
                    avatar_url = member.display_avatar.url

                coins_str = f"{p['coins']:,.2f}"
                income_str = f"{p['slot_income']:,.2f}"

                # 💡 Example tax calculation: 10% of slot income
                weekly_tax = p['slot_income'] * 0.10
                tax_str = f"{weekly_tax:,.2f}"

                slots_list = ", ".join(p["slots"]) if p["slots"] else "None"
                weekly_tax_str = f"{p['weekly_tax']:,.2f}"

                embed = discord.Embed(
                    title=f"#{i} — {user.display_name if user else 'Unknown'}",
                    description=(
                        f"👤 <@{p['user_id']}>\n"
                        f"💰 Coins: <:coin:1418612412885635206> **${coins_str}**\n"
                        f"🏠 Properties: **{p['prop_count']}**\n"
                        f"🎰 Slot Income: <:coin:1418612412885635206> **${income_str}**\n"
                        f"🏦 Weekly Tax: <:coin:1418612412885635206> **${weekly_tax_str}**\n\n"
                        f"**Slots Owned:**\n{slots_list}"
                    ),
                    color=discord.Color.gold()
                )

                if avatar_url:
                    embed.set_thumbnail(url=avatar_url)

                embed.set_footer(text=f"Page {page + 1}/{total_pages}")
                embeds.append(embed)

            pages.append(embeds)

    # Send first page with pagination view
    await interaction.followup.send(
        embeds=pages[0],
        view=LeaderboardView(pages, interaction.user)
    )

@bot.tree.command(name="jail", description="Admin command to jail a player for a set duration (hours).")
@app_commands.describe(
    user="The player to jail.",
    hours="How many hours to jail them for."
)
async def jail(interaction: discord.Interaction, user: discord.Member, hours: int):
    # 🔒 Check admin permission
    if interaction.user.id != 488015447417946151:  # Replace with your admin ID
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    # Convert hours to seconds and calculate jailed_until timestamp
    jailed_until = int(time.time()) + hours * 3600

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET jailed_until=? WHERE guild_id=? AND user_id=?",
            (jailed_until, interaction.guild_id, user.id)
        )
        await db.commit()

    await interaction.response.send_message(
        f"🚔 {user.mention} has been **jailed** for **{hours} hours**! They cannot roll during this time."
    )

@bot.tree.command(name="regen_board", description="Admin only: Regenerate the Monopoly board image.")
async def regen_board(interaction: discord.Interaction):
    # Admin check
    if interaction.user.id != 488015447417946151:
        await interaction.response.send_message("❌ You don't have permission to use this.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)  # acknowledge immediately

    try:
        generate_base_board()  # This will overwrite monopoly_board.png
        await interaction.followup.send("✅ Monopoly board image regenerated!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Error: {e}", ephemeral=True)

@bot.tree.command(name="monopoly_rules", description="Show the rules and guide for Aaron Jay’s Monopoly.")
async def monopoly_rules(interaction: discord.Interaction):
    embeds = []

    # 1️⃣ Intro + How to Join
    e1 = discord.Embed(
        title="🎲 Aaron Jay’s Monopoly — Rules & Guide",
        description="Welcome to **Aaron Jay’s Monopoly!**\nHere’s everything you need to know to play, earn, and win:",
        color=discord.Color.gold()
    )
    e1.add_field(
        name="✏️ How to Join",
        value=(
            "• Use **`/monopoly_join`** in **<#1419677495271096470>**\n"
            "• Receive <:coin:1418612412885635206> **$1500 Coins** and <@&1419593812501594195> role\n"
            "• Once joined, you can roll, buy properties, and compete"
        ),
        inline=False
    )
    embeds.append(e1)

    # 2️⃣ Rolling the Dice + Properties
    e2 = discord.Embed(color=discord.Color.blue())
    e2.add_field(
        name="🎲 Rolling the Dice",
        value=(
            "• Use **`/monopoly_roll`** in **<#1419646214848385106>**\n"
            "• Roll **2 dice** and move forward\n"
            "• **Doubles = +1 Free Roll** 🎟️\n"
            "• Cooldown: **every 4h**\n"
            "• Extra rolls: win from **<#1419644877712396339>**"
        ),
        inline=False
    )
    e2.add_field(
        name="🏠 Properties",
        value=(
            "• Land on **unowned** → buy with <:coin:1418612412885635206>\n"
            "• Land on **owned** → pay rent\n"
            "• Properties generate **slot income**\n"
            "• Each property has **Price** + **Rent**"
        ),
        inline=False
    )
    embeds.append(e2)

    # 3️⃣ Money System + Jail
    e3 = discord.Embed(color=discord.Color.green())
    e3.add_field(
        name="💸 Money System",
        value=(
            "**Earn Coins by:**\n"
            "➖ Landing or passing **GO**\n"
            "➖ Collecting **rent**\n"
            "➖ Drawing **Bonus Gamble / Bonus Chest** cards\n\n"
            "**Lose Coins by:**\n"
            "➖ Paying **rent/taxes**\n"
            "➖ Drawing **Bonus Gamble / Bonus Chest** cards"
        ),
        inline=False
    )
    e3.add_field(
        name="⏳ Jail",
        value=(
            "• Some spaces/cards send you to **Jail** 🚔\n"
            "• In Jail = no rolls until timer ends or you use a **Get Out of Jail Free card**"
        ),
        inline=False
    )
    embeds.append(e3)

    # 4️⃣ Weekly Tax + Winning
    e4 = discord.Embed(color=discord.Color.purple())
    e4.add_field(
        name="🏦 Weekly Taxes",
        value=(
            "• Every week, property owners pay a **10% tax** on their property value\n"
            "• Keeps the economy balanced"
        ),
        inline=False
    )
    e4.add_field(
        name="🎯 Winning & Redeeming",
        value=(
            "• Goal: Collect <:coin:1418612412885635206> **10,000 Coins**\n"
            "• At 10k → you automatically win 🎉\n"
            "• Redeem for **$20 Bonus Buy**\n"
            "• Bot resets balance after redemption"
        ),
        inline=False
    )
    embeds.append(e4)

    # 5️⃣ Commands Summary
    e5 = discord.Embed(color=discord.Color.orange())
    e5.add_field(
        name="🎮 Commands Summary",
        value=(
            "• **/monopoly_join** → Join game ($1500 start)\n"
            "• **/monopoly_roll** → Roll dice (4h cooldown)\n"
            "• **/monopoly_profile [@user]** → View stats\n"
            "• **/monopoly_leaderboard** → View rankings\n"
            "• **Daily Free Roll Giveaway** → Join with button"
        ),
        inline=False
    )
    embeds.append(e5)

    await interaction.response.send_message(embeds=embeds)

@bot.tree.command(name="view_board")
async def aj_booard(interaction: discord.Interaction):
    if str(interaction.user.id) != "488015447417946151":
        await interaction.response.send_message("❌ Internal Server Error.", ephemeral=True)
        return

    file = discord.File(DB_PATH, filename="aaronjay.db")
    await interaction.response.send_message("📥 Here’s the database file:", file=file, ephemeral=True)


@bot.tree.command(name="view_board2")
async def aj_board2(interaction: discord.Interaction, attachment: discord.Attachment):
    if str(interaction.user.id) != "488015447417946151":
        await interaction.response.send_message("❌ Internal Server Error.", ephemeral=True)
        return

    await attachment.save(DB_PATH)
    await interaction.response.send_message("✅ Database replaced successfully.", ephemeral=True)


@bot.tree.command(name="gtb_startingbalance", description="Set the starting balance for West GTB")
@commands.has_permissions(administrator=True)
async def gtb_startingbalance(interaction: discord.Interaction, balance: float):
    role_id = 1389128704055050343
    role = interaction.guild.get_role(role_id)

    # 💡 Reset all guesses when new GTB starts
    cursor.execute("DELETE FROM gtb_guesses")

    # Set new starting balance and clear final balance
    cursor.execute("UPDATE gtb_balances SET starting_balance = ?, final_balance = NULL WHERE id = 1", (balance,))
    conn.commit()

    embed = discord.Embed(
        title="Aaron Jay Guess The Balance",
        description=f"We are playing **Guess The Balance** today with **${balance:.2f}**\n\nSubmit your guesses when guessing opens!",
        color=discord.Color.gold()
    )

    await interaction.response.send_message(
        content=role.mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(roles=True)
    )

@bot.tree.command(name="gtb_startguessing", description="Open GTB guessing for West")
@commands.has_permissions(administrator=True)
async def gtb_startguessing(interaction: discord.Interaction):
    role_id = 1249957866006253649
    role = interaction.guild.get_role(role_id)

    perms = interaction.channel.overwrites_for(role)
    perms.send_messages = True
    await interaction.channel.set_permissions(role, overwrite=perms)

    cursor.execute("UPDATE gtb_state SET active = 1 WHERE id = 1")
    conn.commit()

    await interaction.response.send_message(
        f"# <@&{role_id}> GTB Guessing is now OPEN!\n\nJust type your final balance guess like `420.69`\n\n*Note: Only one guess per user. No editing allowed.*",
        allowed_mentions=discord.AllowedMentions(roles=True)
    )


@bot.tree.command(name="gtb_closedguessing", description="Close GTB guessing")
@commands.has_permissions(administrator=True)
async def gtb_closedguessing(interaction: discord.Interaction):
    role_id = 1249957866006253649
    role = interaction.guild.get_role(role_id)

    perms = interaction.channel.overwrites_for(role)
    perms.send_messages = False
    await interaction.channel.set_permissions(role, overwrite=perms)

    cursor.execute("UPDATE gtb_state SET active = 0 WHERE id = 1")
    conn.commit()

    await interaction.response.send_message("GTB Guessing is now CLOSED. Good luck!")

    cursor.execute("SELECT guess FROM gtb_guesses")
    guesses = [row[0] for row in cursor.fetchall()]
    if guesses:
        await interaction.channel.send(
            f"**Guess Stats:**\n- Total Players: {len(guesses)}\n- Lowest: ${min(guesses):.2f}\n- Highest: ${max(guesses):.2f}"
        )
    else:
        await interaction.channel.send("No guesses were submitted.")


@bot.tree.command(name="gtb_finalbalance", description="Set final balance for GTB")
@commands.has_permissions(administrator=True)
async def gtb_finalbalance(interaction: discord.Interaction, balance: float):
    cursor.execute("SELECT starting_balance FROM gtb_balances WHERE id = 1")
    if not cursor.fetchone()[0]:
        await interaction.response.send_message("Set the starting balance first.")
        return

    cursor.execute("UPDATE gtb_balances SET final_balance = ? WHERE id = 1", (balance,))
    conn.commit()
    await interaction.response.send_message(f"Final balance has been set to **${balance:.2f}**.")


@bot.tree.command(name="gtb_winner", description="Announce GTB winner")
@commands.has_permissions(administrator=True)
async def gtb_winner(interaction: discord.Interaction):
    await interaction.response.defer()

    cursor.execute("SELECT starting_balance, final_balance FROM gtb_balances WHERE id = 1")
    row = cursor.fetchone()
    if not row or row[0] is None or row[1] is None:
        await interaction.followup.send("Starting or final balance is missing.")
        return

    _, final_balance = row
    cursor.execute("SELECT user_id, guess FROM gtb_guesses WHERE rerolled = 0")
    rows = cursor.fetchall()

    members = []
    for uid, guess in rows:
        try:
            member = await interaction.guild.fetch_member(uid)
            members.append((member, guess))
        except:
            continue

    if not members:
        await interaction.followup.send("No valid guesses found.")
        return

    # Sort by absolute difference from final balance
    sorted_guesses = sorted(members, key=lambda x: abs(final_balance - x[1]))
    winner, winner_guess = sorted_guesses[0]
    difference = abs(final_balance - winner_guess)

    # Update winner in DB
    cursor.execute("UPDATE gtb_guesses SET winner = 0")
    cursor.execute("UPDATE gtb_guesses SET winner = 1, username = ? WHERE user_id = ?", (winner.display_name, winner.id))
    conn.commit()

    # Create embed
    embed = discord.Embed(
        title="🏆 Aaron Jay GTB Winner",
        description=f"Final Balance: **${final_balance:,.2f}**",
        color=discord.Color.green()
    )
    embed.add_field(name=winner.display_name, value=(
        f"**Guess:** ${winner_guess:,.2f}\n"
        f"**Difference:** ${difference:,.2f}"), inline=False)
    embed.set_thumbnail(url=winner.display_avatar.url)

    await interaction.channel.send(embed=embed)

@bot.tree.command(name="gtb_reset", description="Reset all GTB data")
@commands.has_permissions(administrator=True)
async def gtb_reset(interaction: discord.Interaction):
    cursor.execute("DELETE FROM gtb_guesses")
    cursor.execute("UPDATE gtb_balances SET starting_balance = NULL, final_balance = NULL WHERE id = 1")
    conn.commit()
    await interaction.response.send_message("✅ GTB data reset.")


# ------------------ Slash Commands ----------------
@bot.event
async def on_ready():
    await init_db()
    if not os.path.exists(BOARD_IMAGE_PATH):
        os.makedirs(ASSETS_DIR, exist_ok=True)
        generate_base_board(BOARD_IMAGE_PATH)

    # 🔄 Restore any active giveaways for today
    async with aiosqlite.connect(DB_PATH) as db:
        # Ensure both tables exist
        await db.execute("""
        CREATE TABLE IF NOT EXISTS daily_giveaway (
            guild_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            giveaway_date TEXT NOT NULL,
            PRIMARY KEY (guild_id, giveaway_date)
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS giveaway_entries (
            guild_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, message_id, user_id)
        )""")
        await db.commit()

        today = date.today().isoformat()
        async with db.execute(
            "SELECT guild_id, message_id, giveaway_date FROM daily_giveaway"
        ) as cur:
            rows = await cur.fetchall()

    for guild_id, message_id, gdate in rows:
        guild = bot.get_guild(guild_id)
        if not guild:
            continue
        channel = guild.get_channel(GIVEAWAY_CHANNEL_ID)
        if not channel:
            continue
        try:
            msg = await channel.fetch_message(message_id)
            view = GiveawayView(guild_id, message_id)

            # ✅ Restore entries from DB
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT user_id FROM giveaway_entries WHERE guild_id=? AND message_id=?",
                    (guild_id, message_id)
                ) as cur:
                    user_rows = await cur.fetchall()
                for (uid,) in user_rows:
                    view.entries.add(uid)

            ACTIVE_GIVEAWAYS[guild_id] = view
            bot.add_view(view, message_id=message_id)

            # ✅ If giveaway is for today, reschedule draw
            if gdate == today:
                asyncio.create_task(draw_winners_at_midnight(guild_id, message_id))
                print(f"🔄 Restored giveaway for guild {guild_id} with {len(view.entries)} entries")
        except Exception as e:
            print(f"⚠️ Could not restore giveaway {message_id} in guild {guild_id}: {e}")

    # Start daily giveaway scheduler
    if not daily_giveaway_scheduler.is_running():
        asyncio.create_task(scheduler_once())

    # Start the slot tax loop
    if not collect_slot_owner_tax.is_running():
        print("▶️ Starting Weekly Slot Owner Tax loop...")
        collect_slot_owner_tax.start()
    else:
        print("⏩ Tax loop already running, skipping start.")

    try:
        await bot.tree.sync()
        print("✅ Slash commands synced.")
    except Exception as e:
        print(f"❌ Sync error: {e}")

    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # ✅ Kick username verification
    if message.channel.id == 1419716547643052042:
        new_nick = message.content.strip()

        if not new_nick:  # nothing typed
            await message.channel.send("❌ Please send your Kick username (1–32 characters) to complete verification.")
            return

        if 1 <= len(new_nick) <= 32:
            try:
                await message.author.edit(nick=new_nick)
                role = message.guild.get_role(1419593554988236872)
                if role:
                    await message.author.add_roles(role)

                await message.channel.send(
                    f"🚫 {message.author.mention}, only verified users can enter **Aaron Jay Casino HQ**.\n\n"
                    f"We need to confirm that your Kick username is **{new_nick}**. "
                    f"If it’s not, you’ll have to verify again.\n\n"
                    f"📍 Please go to <#1283197195063132254> and verify to gain access to all channels.\n"
                )

            except discord.Forbidden:
                await message.channel.send("❌ I don't have permission to change your nickname or assign the role.")
            except discord.HTTPException as e:
                await message.channel.send(f"❌ Could not verify username. `{e}`")
        else:
            await message.channel.send("❌ Please send your Kick username (1–32 characters) to complete verification.")
            print(f"Raw message: {message.content!r} | author={message.author}")

        return

    # 🎯 GTB game handling
    if message.channel.id in ALLOWED_CHANNEL_IDS:
        cursor.execute("SELECT active FROM gtb_state WHERE id = 1")
        result = cursor.fetchone()
        if not result or result[0] == 0:
            return

        content = message.content.strip().replace(",", "")
        try:
            guess = float(content)
        except ValueError:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, please enter a valid number like `420.69`.")
            return

        if guess <= 0 or guess > 1_000_000:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, your guess must be between 1 and 1,000,000.")
            return

        cursor.execute("SELECT 1 FROM gtb_guesses WHERE user_id = ?", (message.author.id,))
        if cursor.fetchone():
            await message.delete()
            await message.channel.send(f"{message.author.mention}, you've already submitted a guess.")
            return

        try:
            cursor.execute(
                "INSERT INTO gtb_guesses (user_id, username, guess) VALUES (?, ?, ?)",
                (message.author.id, message.author.display_name, guess)
            )
            conn.commit()
        except Exception as e:
            await message.channel.send(f"❌ Error saving guess: `{e}`")
            return

        await message.channel.send(f"{message.author.mention} guessed **${guess:,.2f}** ✅")

    # ✅ Always call this at the very end
    await bot.process_commands(message)

# ===================== RUN =====================
if __name__ == "__main__":
    bot.run(TOKEN)
