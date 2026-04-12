import os
import aiohttp
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import sqlite3
import time
from datetime import datetime, timezone
import asyncio
from playwright.async_api import async_playwright
import random
import json
import base64
import requests
from discord import app_commands, Interaction, ui
import math
import logging

DB_PATH = "/mnt/data/tfs.db" if os.path.exists("/mnt/data") else "tfs.db"

intents = discord.Intents.default()
intents.presences = True  # Required for rich presence
intents.message_content = True
intents.messages = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    discord_id TEXT PRIMARY KEY,
    instagram_username TEXT,
    points INTEGER DEFAULT 0,
    weekly_points INTEGER DEFAULT 0,
    monthly_points INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS posts (
    post_url TEXT PRIMARY KEY,
    post_timestamp REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS processed_comments (
    comment_id TEXT,
    post_url TEXT,
    instagram_username TEXT,
    comment_time REAL,
    PRIMARY KEY (comment_id, post_url)
)
""")

conn.commit()


# ---------------- CONFIG ----------------
GUILD_ID = 1165888939484254258
ADMIN_ID = 488015447417946151
INSTAGRAM_USERNAME = "teamfullsendslots01"
IG_CHANNEL_ID = 1492775284561154121
LOCKED_CHANNEL_ID = 1492776034893037638
POINTS_CHANNEL_ID = 1492776540147286126
WINNER_CHANNEL_ID = 1492776919253651497
INSTAGRAM_ROLE_ID = 1388719365687607316
post_timestamp = None
last_post_url = None
MAX_POINTS = 10
MIN_POINTS = 1
TRACK_DURATION = 259200  # 3 days
is_checking_comments = False
IG_EMOJI = "<:ig:1488008202217062401>"
TFS_COINS = "<:Coin:1418612841359081643>"
TFS_COIN_URL = "https://cdn.discordapp.com/emojis/1418612841359081643.png"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "dtrix381/TFS"
GITHUB_FILE_PATH = "leaderboard.json"
DATABASE_PATH = DB_PATH
MAX_LEADERBOARD = 500

last_push_time = 0

# ---------------- POINT SYSTEM ----------------
def calculate_points(post_time, comment_time):
    diff = comment_time - post_time

    if diff < 300:          # < 5 minutes
        return 10
    elif diff < 1800:       # < 30 minutes
        return 9
    elif diff < 3600:       # < 1 hour
        return 8
    elif diff < 14400:      # < 4 hours
        return 7
    elif diff < 21600:      # < 6 hours
        return 6
    elif diff < 43200:      # < 12 hours
        return 5
    elif diff < 86400:      # < 1 day
        return 4
    elif diff < 172800:     # < 2 days
        return 3
    elif diff < 259200:     # < 3 days
        return 2

    return 1  # fallback (edge cases only)

# ===== PUSH TO GITHUB =====
def push_to_github(data_json, commit_message="Update leaderboard", max_retries=5):
    global last_push_time
    if time.time() - last_push_time < 30:
        print("⏱ Skipping GitHub push (rate limit)")
        return
    last_push_time = time.time()

    encoded_content = base64.b64encode(json.dumps(data_json, indent=4).encode()).decode()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"  # <-- use this
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    for attempt in range(1, max_retries + 1):
        # Get SHA if file exists
        res = requests.get(url, headers=headers)
        sha = res.json().get("sha") if res.status_code == 200 else None

        payload = {"message": commit_message, "content": encoded_content}
        if sha:
            payload["sha"] = sha

        response = requests.put(url, json=payload, headers=headers)

        if response.status_code in [200, 201]:
            print(f"✅ {GITHUB_FILE_PATH} pushed to GitHub on attempt {attempt}")
            break
        else:
            print(f"⚠️ Attempt {attempt} failed ({response.status_code}): {response.json()}")
            if attempt < max_retries:
                wait_time = attempt * 5
                print(f"🔄 Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"❌ Failed to push {GITHUB_FILE_PATH} after {max_retries} attempts")

# ---------------- PLAYWRIGHT ----------------
async def get_browser():
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)  # ✅ change to True for stability

    context = await browser.new_context(
        storage_state="ig_session.json",
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
    page = await context.new_page()

    return p, browser, page

# ---------------- FETCH POSTS ----------------
async def fetch_posts(page):
    await page.goto(f"https://www.instagram.com/{INSTAGRAM_USERNAME}/")
    await page.wait_for_timeout(8000)

    elements = await page.query_selector_all("a[href*='/p/'], a[href*='/reel/']")
    print(f"🔎 Found {len(elements)} posts")

    results = []

    # ✅ extract safely first
    for el in elements[3:]:
        try:
            href = await el.get_attribute("href")
            if not href:
                continue

            full_url = f"https://www.instagram.com{href}"

            img_el = await el.query_selector("img")
            img_url = await img_el.get_attribute("src") if img_el else None

            results.append({
                "url": full_url,
                "image": img_url
            })

        except Exception as e:
            print("Post extract error:", e)

    final_posts = []

    # ✅ navigate AFTER extraction (prevents crash)
    for post in results:
        try:
            await page.goto(post["url"], timeout=60000)
            await page.wait_for_timeout(4000)

            time_el = await page.query_selector("time")
            if not time_el:
                continue

            dt = await time_el.get_attribute("datetime")
            timestamp = datetime.fromisoformat(dt.replace("Z", "+00:00")).timestamp()

            if time.time() - timestamp <= TRACK_DURATION:
                final_posts.append({
                    "url": post["url"],
                    "image": post["image"],
                    "timestamp": timestamp
                })

        except Exception as e:
            print("Timestamp error:", e)

    print(f"✅ Tracking {len(final_posts)} recent posts")
    return final_posts

# ---------------- FETCH COMMENTS (APIFY) ----------------
async def fetch_comments_playwright(post_urls):
    results = {}

    p, browser, page = await get_browser()

    try:
        for post_url in post_urls:
            await asyncio.sleep(random.uniform(10, 20))
            await page.goto(post_url, timeout=60000)
            await page.wait_for_timeout(5000)

            await page.screenshot(path="debug.png")
            print("🌐 Current URL:", page.url)
            print(f"🔍 Scraping comments: {post_url}")

            # 🔥 Wait until comments exist (VERY IMPORTANT)
            try:
                await page.wait_for_function("""
                () => document.querySelectorAll('time').length > 0
                """, timeout=15000)
            except:
                print("⚠️ No comment timestamps found")

            # 🔥 Scroll like human
            for _ in range(10):
                await page.mouse.wheel(0, 2000)
                await page.wait_for_timeout(1500)

            # 🔥 Load more comments
            for _ in range(10):
                try:
                    btn = await page.query_selector("text=comments")
                    if btn:
                        await btn.click()
                        await page.wait_for_timeout(2000)
                    else:
                        break
                except:
                    break

            # 🔥 USE TIME ELEMENTS (MOST RELIABLE)
            time_elements = await page.query_selector_all("time")

            post_comments = []
            seen_ids = set()

            for t in time_elements:
                try:
                    timestamp_raw = await t.get_attribute("datetime")
                    if not timestamp_raw:
                        continue

                    timestamp = datetime.fromisoformat(
                        timestamp_raw.replace("Z", "+00:00")
                    ).timestamp()

                    # 🔥 Find parent containing username
                    parent = await t.evaluate_handle("el => el.closest('li, div')")

                    username_el = await parent.query_selector("a[href^='/']")
                    if not username_el:
                        continue

                    username = (await username_el.inner_text()).strip().lower()

                    # 🔴 FILTER garbage
                    if not username or len(username) > 30:
                        continue

                    comment_id = f"{username}-{timestamp}"

                    if comment_id in seen_ids:
                        continue

                    seen_ids.add(comment_id)

                    post_comments.append({
                        "id": comment_id,
                        "username": username,
                        "timestamp": timestamp
                    })

                except Exception as e:
                    print("Parse error:", e)

            print(f"💬 Found {len(post_comments)} comments (FINAL)")
            results[post_url] = post_comments

    except Exception as e:
        print("Playwright comment fetch error:", e)

    finally:
        await browser.close()
        await p.stop()

    return results

# ---------------- INSTAGRAM CHECKER ----------------
@tasks.loop(minutes=10)
async def instagram_checker():
    print("🔄 Checking Instagram...")

    p = browser = page = None
    new_post_found = False  # track if new post exists

    try:
        p, browser, page = await get_browser()
        posts = await fetch_posts(page)

        channel = bot.get_channel(IG_CHANNEL_ID)

        for post in posts:
            cursor.execute("SELECT 1 FROM posts WHERE post_url=?", (post["url"],))
            if cursor.fetchone():
                continue

            # ✅ NEW POST
            new_post_found = True

            cursor.execute(
                "INSERT INTO posts VALUES (?, ?)",
                (post["url"], post["timestamp"])
            )
            conn.commit()

            # Mention Instagram role
            role_mention = f"<@&{INSTAGRAM_ROLE_ID}>"

            # ✅ CLEAN EMBED (NO MENTION INSIDE)
            embed = discord.Embed(
                title="TFS New Instagram Post!",
                url=post["url"],
                color=discord.Color.purple()
            )

            # ✅ KEEP IMAGE
            if post["image"]:
                embed.set_image(url=post["image"])

            # Button with IG emoji
            view = View()
            view.add_item(
                Button(
                    label="Engage to Earn Points",
                    url=post["url"],
                    style=discord.ButtonStyle.green
                )
            )

            # ✅ SEND MESSAGE WITH ROLE PING OUTSIDE EMBED
            await channel.send(
                content=f"{role_mention} Engage quickly to earn more {TFS_COINS} TFS Coins!",
                embed=embed,
                view=view
            )

            print("✅ New post:", post["url"])

        # 🚀 RUN COMMENT CHECKER IF NEW POST
        if new_post_found:
            print("⚡ Running instant comment check...")
            asyncio.create_task(run_comment_checker())

    except Exception as e:
        print("Instagram checker error:", e)

    finally:
        if browser:
            await browser.close()
        if p:
            await p.stop()

@tasks.loop(minutes=30)
async def comment_checker():
    await run_comment_checker()

async def run_comment_checker():
    global is_checking_comments

    if is_checking_comments:
        print("⏳ Comment checker already running, skipping...")
        return

    is_checking_comments = True

    try:
        print("🔄 Optimized comment check...")

        cursor.execute("SELECT post_url, post_timestamp FROM posts")
        posts = cursor.fetchall()

        active_posts = []

        # 🧹 remove expired posts
        for post_url, post_timestamp in posts:
            if time.time() - post_timestamp > TRACK_DURATION:
                cursor.execute("DELETE FROM posts WHERE post_url=?", (post_url,))
                conn.commit()
                print(f"🧹 Removed expired post: {post_url}")
            else:
                active_posts.append((post_url, post_timestamp))

        if not active_posts:
            return

        post_urls = [p[0] for p in active_posts[:10]]

        await asyncio.sleep(random.uniform(5, 10))
        comments_data = await fetch_comments_playwright(post_urls)

        for post_url, post_timestamp in active_posts:

            comments = comments_data.get(post_url, [])
            seen_users = set()

            for c in comments:
                comment_id = c["id"]
                username = c["username"]
                comment_time = c["timestamp"]

                if username == INSTAGRAM_USERNAME.lower():
                    continue

                if username in seen_users:
                    continue

                seen_users.add(username)

                cursor.execute(
                    "SELECT 1 FROM processed_comments WHERE comment_id=? AND post_url=?",
                    (comment_id, post_url)
                )
                if cursor.fetchone():
                    continue

                cursor.execute(
                    "SELECT 1 FROM processed_comments WHERE instagram_username=? AND post_url=?",
                    (username, post_url)
                )
                if cursor.fetchone():
                    continue

                cursor.execute(
                    "SELECT discord_id FROM users WHERE instagram_username=?",
                    (username,)
                )
                user_data = cursor.fetchone()

                if not user_data:
                    continue

                points = calculate_points(post_timestamp, comment_time)
                if points <= 0:
                    continue

                discord_id = int(user_data[0])

                cursor.execute(
                    """
                    UPDATE users 
                    SET 
                        points = points + ?, 
                        weekly_points = weekly_points + ?, 
                        monthly_points = monthly_points + ?
                    WHERE discord_id=?
                    """,
                    (points, points, points, discord_id)
                )

                cursor.execute(
                    "INSERT INTO processed_comments VALUES (?, ?, ?, ?)",
                    (comment_id, post_url, username, comment_time)
                )

                conn.commit()
                # 🚀 update leaderboard
                await export_leaderboard(bot)

                try:
                    user = await bot.fetch_user(discord_id)
                    channel = bot.get_channel(POINTS_CHANNEL_ID)
                    await channel.send(
                        f"{IG_EMOJI} {user.mention} just earned **+{points}** {TFS_COINS} for engaging on our latest post!"
                    )
                except:
                    pass

                print(f"✅ {username} +{points} ({post_url})")

    finally:
        is_checking_comments = False

# ---------- Modal for Instagram Input ----------
class InstagramModal(ui.Modal, title="Connect Your Instagram"):
    username = ui.TextInput(label="Instagram Username (small letters only)", placeholder="Enter your Instagram username (small letters only)")

    def __init__(self, member: discord.Member):
        super().__init__()
        self.member = member

    async def on_submit(self, interaction: Interaction):
        global conn, cursor

        try:
            # Save to DB
            cursor.execute("""
            INSERT INTO users (discord_id, instagram_username, points, weekly_points, monthly_points)
            VALUES (?, ?, 0, 0, 0)
            ON CONFLICT(discord_id) DO UPDATE SET instagram_username=excluded.instagram_username
            """, (str(self.member.id), self.username.value.lower()))
            conn.commit()
        except Exception as e:
            print("DB error:", e)
            await interaction.response.send_message("❌ Something went wrong with the database.", ephemeral=True)
            return

        try:
            # Give Instagram Role
            role = interaction.guild.get_role(INSTAGRAM_ROLE_ID)
            if role:
                await self.member.add_roles(role)
        except Exception as e:
            print("Role assign error:", e)
            # Don't return; continue to send confirmation

        # Success message
        await interaction.response.send_message(
            f"{IG_EMOJI} Your Instagram has been connected! You can now earn TFS Coins {TFS_COINS} and join Weekly & Monthly giveaways on https://www.teamfullsendslots.com/giveaways/",
            ephemeral=True
        )

# ---------- Button to Open Modal ----------
class ConnectButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # no timeout

    @ui.button(label="Connect Instagram", style=discord.ButtonStyle.green)
    async def connect(self, interaction: Interaction, button: ui.Button):
        modal = InstagramModal(interaction.user)
        await interaction.response.send_modal(modal)

# ---------- Admin Command ----------
@bot.tree.command(name="prompt_connect", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def prompt_connect(interaction: Interaction):
    """Send Instagram connect message in locked channel (Admin Only)"""
    if interaction.channel.id != LOCKED_CHANNEL_ID:
        await interaction.response.send_message("❌ This command can only be used in the designated channel.", ephemeral=True)
        return

    view = ConnectButton()
    await interaction.channel.send(
        f"📌 You must connect your Instagram account to earn TFS coins {TFS_COINS} and participate in Weekly & Monthly giveaways on https://www.teamfullsendslots.com/giveaways/",
        view=view
    )
    await interaction.response.send_message("Connect Instagram prompt sent!", ephemeral=True)

# ---------- Error Handler ----------
@prompt_connect.error
async def prompt_connect_error(interaction: Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Only admins can use this command.", ephemeral=True)

def pick_weighted_winner(users):
    total = sum(u["points"] for u in users)
    r = random.uniform(0, total)

    upto = 0
    for u in users:
        if upto + u["points"] >= r:
            return u
        upto += u["points"]

def load_giveaway_data():
    with open("giveaway_data.json", "r") as f:
        return json.load(f)

def save_giveaway_data(data):
    with open("giveaway_data.json", "w") as f:
        json.dump(data, f, indent=4)

async def run_giveaway(giveaway_type):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    column = "weekly_points" if giveaway_type == "weekly" else "monthly_points"

    cursor.execute(f"""
        SELECT discord_id, instagram_username, {column}
        FROM users
        WHERE {column} > 0
    """)
    rows = cursor.fetchall()

    users = [
        {"discord_id": r[0], "username": r[1], "points": r[2]}
        for r in rows
    ]

    if not users:
        print(f"No users for {giveaway_type}")
        return

    winner = pick_weighted_winner(users)

    # Load config
    data = load_giveaway_data()
    config = data[giveaway_type]

    title = config["title"]
    prize = config["prize"]
    thumbnail = config["thumbnail"]

    # Announce on Discord
    channel = bot.get_channel(WINNER_CHANNEL_ID)
    user = await bot.fetch_user(winner["discord_id"])

    embed = discord.Embed(
        title=f"🎉 {title} Winner!",
        description=f"🏆 {user.mention}\n🎁 Prize: ${prize}",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=thumbnail)
    await channel.send(embed=embed)

    # Update giveaway_data.json for website
    data[giveaway_type]["last_winner"] = winner["username"]
    data[giveaway_type]["last_entries"] = winner["points"]
    data[giveaway_type]["end_time"] = None

    # Ensure history exists and append winner
    if "history" not in data[giveaway_type]:
        data[giveaway_type]["history"] = []

    data[giveaway_type]["history"].append({
        "username": winner["username"],
        "discord_id": winner["discord_id"],
        "prize": prize,
        "chance": winner["points"],
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "title": title  # <- store the giveaway title here
    })

    save_giveaway_data(data)

    # Reset points in DB
    cursor.execute(f"UPDATE users SET {column} = 0")
    conn.commit()
    conn.close()

    # Export leaderboard so website reflects zeroed points
    await export_leaderboard(bot)

    # Push updated giveaway_data.json to GitHub
    push_giveaway_to_github()

    print(f"✅ {giveaway_type} giveaway completed. Winner: {winner['username']}")

@tasks.loop(minutes=1)
async def giveaway_checker():
    data = load_giveaway_data()
    now = datetime.now(timezone.utc)

    for gtype in ["weekly", "monthly"]:
        g = data[gtype]

        if g.get("end_time"):
            end = datetime.strptime(g["end_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

            if now >= end:
                print(f"Running {gtype} giveaway...")
                await run_giveaway(gtype)

# ===== EXPORT LEADERBOARD WITH DISCORD INFO =====
async def export_leaderboard(bot):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # fetch top users
        cursor.execute(f"""
            SELECT discord_id, instagram_username, weekly_points, monthly_points
            FROM users
            ORDER BY monthly_points DESC
            LIMIT {MAX_LEADERBOARD}
        """)
        rows = cursor.fetchall()

        leaderboard = []
        for r in rows:
            discord_id = int(r[0])
            insta = r[1]
            weekly = r[2]
            monthly = r[3]

            # fetch live Discord user info
            try:
                user = await bot.fetch_user(discord_id)
                username = str(user)  # discord username#discrim
                avatar_url = user.display_avatar.url
            except:
                username = f"Unknown ({discord_id})"
                avatar_url = None

            # get giveaway history for this user
            with open("giveaway_data.json", "r") as f:
                giveaways = json.load(f)

            history = []
            for gtype in ["weekly", "monthly"]:
                g = giveaways.get(gtype, {})
                hist = g.get("history", [])
                for h in hist:
                    if h["username"].lower() == insta.lower():
                        history.append({
                            "username": h["username"],
                            "prize": h["prize"],
                            "chance": h["chance"],
                            "time": h["time"],
                            "title": g.get("title", gtype.capitalize())
                        })
            leaderboard.append({
                "discord_username": username,
                "discord_avatar": avatar_url,
                "instagram_username": insta,
                "weekly": weekly,
                "monthly": monthly,
                "giveaway_history": history
            })

        # Build full JSON with emojis
        data_json = {
            "emojis": {
                "coin": "https://cdn.discordapp.com/emojis/1418612841359081643.png"
            },
            "users": leaderboard
        }

        # Save locally
        with open(GITHUB_FILE_PATH, "w") as f:
            json.dump(data_json, f, indent=4)

        print("📤 Exported leaderboard locally")

        # Push to GitHub
        push_to_github(data_json)

    except Exception as e:
        print("❌ Error exporting leaderboard:", e)

    finally:
        conn.close()

@bot.tree.command(name="update_weekly", description="Update weekly giveaway", guild=discord.Object(id=GUILD_ID))
async def update_weekly(interaction: discord.Interaction, title: str, prize: str, thumbnail: str, end_time: str):
    await interaction.response.defer(ephemeral=True)

    data = load_giveaway_data()

    old = data.get("weekly", {})

    data["weekly"] = {
        "title": title,
        "prize": prize,
        "thumbnail": thumbnail,
        "end_time": end_time,

        # ✅ PRESERVE THESE
        "history": old.get("history", []),
        "last_winner": old.get("last_winner"),
        "last_entries": old.get("last_entries", 0)
    }

    save_giveaway_data(data)
    push_giveaway_to_github()

    await interaction.followup.send("✅ Weekly giveaway updated!", ephemeral=True)

@bot.tree.command(name="update_monthly", description="Update monthly giveaway", guild=discord.Object(id=GUILD_ID))
async def update_monthly(interaction: discord.Interaction, title: str, prize: str, thumbnail: str, end_time: str):
    await interaction.response.defer(ephemeral=True)

    data = load_giveaway_data()

    old = data.get("monthly", {})

    data["monthly"] = {
        "title": title,
        "prize": prize,
        "thumbnail": thumbnail,
        "end_time": end_time,

        # ✅ PRESERVE
        "history": old.get("history", []),
        "last_winner": old.get("last_winner"),
        "last_entries": old.get("last_entries", 0)
    }

    save_giveaway_data(data)
    push_giveaway_to_github()

    await interaction.followup.send("✅ Monthly giveaway updated!", ephemeral=True)


def push_giveaway_to_github(max_retries=5):
    with open("giveaway_data.json", "r") as f:
        content = f.read()

    encoded_content = base64.b64encode(content.encode()).decode()
    file_path = "giveaway_data.json"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    for attempt in range(1, max_retries + 1):
        res = requests.get(url, headers=headers)
        sha = res.json().get("sha") if res.status_code == 200 else None

        payload = {"message": "Update giveaway data", "content": encoded_content}
        if sha:
            payload["sha"] = sha

        response = requests.put(url, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            print(f"🚀 Giveaway pushed to GitHub on attempt {attempt}")
            break
        else:
            print(f"⚠️ Attempt {attempt} failed ({response.status_code}): {response.json()}")
            if attempt < max_retries:
                wait_time = attempt * 5
                print(f"🔄 Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"❌ Failed to push giveaway_data.json after {max_retries} attempts")

@bot.tree.command(name="upload_session", description="Upload new Instagram session", guild=discord.Object(id=GUILD_ID))
async def upload_session(interaction: discord.Interaction, file: discord.Attachment):

    # 🔒 ADMIN CHECK
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    # ✅ Validate filename
    if file.filename != "ig_session.json":
        await interaction.followup.send("❌ File must be named ig_session.json", ephemeral=True)
        return

    try:
        # ✅ Save file
        await file.save("ig_session.json")

        # ✅ CONFIRM SAVE
        await interaction.followup.send("♻️ Session updated. Restarting scraper...", ephemeral=True)

        global is_checking_comments
        is_checking_comments = False

        asyncio.create_task(run_comment_checker())

        print("🔁 Session manually refreshed via Discord")

    except Exception as e:
        await interaction.followup.send(f"❌ Error saving file: {e}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

    if not instagram_checker.is_running():
        instagram_checker.start()

    if not comment_checker.is_running():
        # Run once immediately
        await run_comment_checker()
        comment_checker.start()

    giveaway_checker.start()

@bot.event
async def on_message(message: discord.Message):
    # Ignore bot messages
    if message.author.bot:
        return

    # ✅ Nickname verification channel
    if message.channel.id == 1380373571125252226:
        new_nick = message.content.strip()
        if 1 <= len(new_nick) <= 32:
            try:
                await message.author.edit(nick=new_nick)
                role = message.guild.get_role(1294538856514981970)
                if role:
                    await message.author.add_roles(role)

                await message.channel.send(
                    f"✅ {message.author.mention}, we'll need to verify if your Kick username is indeed **{new_nick}**. "
                    f"If it isn't, you'll need to verify again.\n\n"
                    f"If that's your Kick Username then go to <#1280392918573645887> "
                    f"and verify to Double Counter gain access to all channels."
                )
            except discord.Forbidden:
                await message.channel.send("❌ I don't have permission to change your nickname or assign the verification role.")
            except discord.HTTPException as e:
                await message.channel.send(f"❌ Couldn’t verify your Kick username. Error: `{e}`")
        else:
            await message.channel.send("❌ Please send your Kick username (1–32 characters) to complete verification.")
        return

    await bot.process_commands(message)





