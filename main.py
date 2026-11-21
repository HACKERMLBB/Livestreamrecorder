import subprocess
import requests
import os
import time
import glob
import json
import threading
import asyncio
import shutil
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MIXDROP_KEY = os.getenv("MIXDROP_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is missing in Railway Variables!")
# ==========================================

USERNAMES_FILE = "usernames.json"
MAX_TELEGRAM_SIZE = 50 * 1024 * 1024

# ================= PLATFORMS - ONLY 3 =================
PLATFORMS = {
    "twitch": "https://twitch.tv/{id}",
    "kick": "https://kick.com/{id}",
    # Nimo: Streamlink එකට www ඕන, Browser එකට m ඕන - දෙකම Try කරනවා
    "nimo": "https://www.nimo.tv/{id}",
}

def parse_entry(entry):
    entry = entry.lower().replace("@", "").strip()
    if ":" in entry:
        platform, uid = entry.split(":", 1)
        platform = platform.strip()
        uid = uid.strip()
        if platform not in PLATFORMS:
            platform = "twitch"
    else:
        platform = "twitch"
        uid = entry
    return platform, uid

def make_entry(platform, uid):
    return f"{platform}:{uid}"

def get_url(entry):
    platform, uid = parse_entry(entry)
    return PLATFORMS[platform].format(id=uid)

def get_all_urls(entry):
    # Nimo එකට URL 2ක් Return කරනවා, අනිත් ඒවට 1යි
    platform, uid = parse_entry(entry)
    if platform == "nimo":
        return [
            f"https://www.nimo.tv/{uid}",
            f"https://www.nimo.tv/live/{uid}",
            f"https://m.nimo.tv/live/{uid}",
        ]
    return [get_url(entry)]

def display_name(entry):
    platform, uid = parse_entry(entry)
    return f"@{uid} [{platform}]"

if os.path.exists(USERNAMES_FILE):
    try:
        USERNAMES = json.load(open(USERNAMES_FILE))
        migrated = []
        for u in USERNAMES:
            if ":" not in str(u):
                migrated.append(make_entry("twitch", str(u)))
            else:
                migrated.append(str(u).lower())
        USERNAMES = migrated
    except:
        USERNAMES = []
else:
    USERNAMES = []

RECORDING = set()

def save_usernames():
    with open(USERNAMES_FILE, "w") as f:
        json.dump(USERNAMES, f)

# ================= BOT COMMANDS =================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "🎬 Welcome to Yoon Auto Recorder 🎬\n\n"
        "📌 Commands:\n"
        "/add username - ➕ Add Twitch account\n"
        "/add kick:username - ➕ Add Kick\n"
        "/add nimo:RoomID - ➕ Add Nimo (Room ID only!)\n"
        "/remove username - ➖ Remove an account\n"
        "/list - 📋 Show all accounts\n"
        "/status - 🔴 Check recording status\n\n"
        "🎞️ Quality: 360p\n"
        "✂️ Split: 50MB Parts\n"
        "☁️ Upload: Mixdrop + Telegram\n\n"
        "🌐 Platforms: ONLY 3\n"
        "twitch, kick, nimo\n\n"
        "💡 Examples:\n"
        "/add yoon_gaming1\n"
        "/add kick:yoon_live\n"
        "/add nimo:818540864"
    )
    await update.message.reply_text(message)

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /add username OR /add kick:username OR /add nimo:RoomID\n💡 Example: /add nimo:818540864")
        return
    raw = " ".join(context.args).lower().strip()
    platform, uid = parse_entry(raw)
    entry = make_entry(platform, uid)
    if entry not in USERNAMES:
        USERNAMES.append(entry)
        save_usernames()
        await update.message.reply_text(
            f"✅ Added: {display_name(entry)}\n"
            f"🔴 Auto Record is now ON - 360p\n"
            f"📁 File will be uploaded after live ends."
        )
    else:
        await update.message.reply_text(f"ℹ️ {display_name(entry)} is already added.")

async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /remove username OR /remove kick:username OR /remove nimo:RoomID\n💡 Example: /remove nimo:818540864")
        return
    raw = " ".join(context.args).lower().strip()
    platform, uid = parse_entry(raw)
    entry = make_entry(platform, uid)
    if entry in USERNAMES:
        USERNAMES.remove(entry)
        save_usernames()
        if entry in RECORDING:
            RECORDING.discard(entry)
        await update.message.reply_text(
            f"🗑️ Removed: {display_name(entry)}\n"
            f"⛔ Auto Record is now OFF for this account."
        )
    else:
        await update.message.reply_text(f"❌ Not Found: {display_name(entry)}\n📋 Use /list to see all accounts.")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not USERNAMES:
        await update.message.reply_text("📭 No accounts added yet.\n➕ Use /add username to add one.")
        return
    text = "👀 Watching Accounts:\n\n"
    for user in USERNAMES:
        status = "🔴 REC" if user in RECORDING else "⏳ Waiting"
        text += f"{display_name(user)} - {status}\n"
    text += "\n🎞️ Quality: 360p\n✂️ Split: 50MB"
    await update.message.reply_text(text)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not RECORDING:
        await update.message.reply_text("😴 No one is live right now.")
        return
    text = "🔴 Currently Recording:\n\n"
    for user in RECORDING:
        text += f"🎥 Live: {display_name(user)} - 360p\n"
    await update.message.reply_text(text)

# ================= HELPERS =================

def upload_to_mixdrop(file_path):
    try:
        with open(file_path, "rb") as f:
            response = requests.post(
                "https://ul.mixdrop.ag/api",
                data={"key": MIXDROP_KEY},
                files={"file": f},
                timeout=3600
            ).json()
        if response.get("success"):
            return response["result"]["url"]
    except Exception as e:
        print(f"Mixdrop Error: {e}")
    return None

def is_live(entry):
    # Nimo එකට URL 3ක්ම Try කරනවා
    for url in get_all_urls(entry):
        result = subprocess.run(
            ["streamlink", url, "--json"],
            capture_output=True, text=True
        )
        # Streamlink එකේ JSON එකේ streams තියෙනවද බලනවා
        if result.returncode == 0 and "No playable streams" not in result.stdout and "streams" in result.stdout and '"streams": {}' not in result.stdout:
            print(f"is_live TRUE via streamlink: {url}")
            return True
        # yt-dlp එකෙනුත් Try කරනවා
        result2 = subprocess.run(
            ["yt-dlp", url, "--skip-download", "--quiet"],
            capture_output=True
        )
        if result2.returncode == 0:
            print(f"is_live TRUE via yt-dlp: {url}")
            return True
    print(f"is_live FALSE: {entry}")
    return False

def record_stream(entry, output_path):
    # Nimo එකට URL 3ක්ම, අනිත් ඒවට URL 1යි - හැම URL එකටම 360p -> 360p30 Try කරනවා
    for url in get_all_urls(entry):
        print(f"Trying Streamlink 360p for {entry} via {url}...")
        subprocess.run(["streamlink", url, "360p", "-o", output_path])
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True
        if os.path.exists(output_path):
            os.remove(output_path)
        print(f"Trying Streamlink 360p30 for {entry} via {url}...")
        subprocess.run(["streamlink", url, "360p30", "-o", output_path])
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True
        if os.path.exists(output_path):
            os.remove(output_path)
        print(f"Trying yt-dlp for {entry} via {url}...")
        subprocess.run(["yt-dlp", url, "-f", "best[height<=360]", "-o", output_path, "--no-part"])
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True
        if os.path.exists(output_path):
            os.remove(output_path)
    return False

async def upload_and_send(entry, base_name, full_path, app):
    file_size_mb = os.path.getsize(full_path) / (1024 * 1024)
    await app.bot.send_message(
        CHANNEL_ID,
        f"🏁 Live Ended: {display_name(entry)}\n"
        f"📦 File Size: {file_size_mb:.1f} MB (360p)\n"
        f"✂️ Splitting into 50MB parts...\n"
        f"🔄 Next Live can record now - Upload is in background."
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", full_path,
        "-fs", str(MAX_TELEGRAM_SIZE),
        "-c", "copy",
        f"{base_name}_part%03d.mp4"
    ])
    parts = sorted(glob.glob(f"{base_name}_part*.mp4"))
    total_parts = len(parts)
    for index, part_path in enumerate(parts, 1):
        await app.bot.send_message(CHANNEL_ID, f"☁️ Uploading Part {index}/{total_parts} to Mixdrop... {display_name(entry)}")
        mixdrop_link = upload_to_mixdrop(part_path)
        if not mixdrop_link:
            mixdrop_link = "Upload Failed"
            await app.bot.send_message(CHANNEL_ID, f"❌ Mixdrop Upload Failed - Part {index}/{total_parts}: {display_name(entry)}")
        else:
            await app.bot.send_message(
                CHANNEL_ID,
                f"✅ Mixdrop Done - Part {index}/{total_parts}\n"
                f"{display_name(entry)}\n"
                f"🔗 Full Part Link: {mixdrop_link}"
            )
        caption = (
            f"🎬 Live Replay: {display_name(entry)} [360p]\n"
            f"📂 Part {index}/{total_parts}\n"
            f"🔗 Mixdrop Part {index}: {mixdrop_link}\n"
            f"▶️ Part {index} - Watch Here"
        )
        with open(part_path, "rb") as video:
            await app.bot.send_video(
                CHANNEL_ID,
                video=video,
                caption=caption,
                supports_streaming=True
            )
        os.remove(part_path)
        await asyncio.sleep(2)
    if os.path.exists(full_path):
        os.remove(full_path)
    await app.bot.send_message(
        CHANNEL_ID,
        f"🎉 Completed: {display_name(entry)}\n"
        f"📂 Total Parts: {total_parts} x 50MB\n"
        f"🎞️ Quality: 360p\n"
        f"✅ Enjoy!"
    )

async def process_stream(entry, app):
    platform, uid = parse_entry(entry)
    base_name = f"{platform}_{uid}_{int(time.time())}"
    full_path = f"{base_name}_full.mp4"
    await app.bot.send_message(CHANNEL_ID, f"🔴 LIVE Detected!\n{display_name(entry)}\n🎥 Recording Started... [360p]")
    success = record_stream(entry, full_path)
    if not success:
        await app.bot.send_message(CHANNEL_ID, f"❌ Recording Failed: {display_name(entry)}")
        RECORDING.discard(entry)
        return
    RECORDING.discard(entry)
    await upload_and_send(entry, base_name, full_path, app)

def check_loop(app):
    while True:
        for username in list(USERNAMES):
            if username not in RECORDING and is_live(username):
                RECORDING.add(username)
                def run_task(user=username):
                    asyncio.run(process_stream(user, app))
                    RECORDING.discard(user)
                threading.Thread(target=run_task, daemon=True).start()
        time.sleep(60)

def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN missing! Check Railway Variables")
        return
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(read_timeout=600, write_timeout=600, connect_timeout=60, pool_timeout=600)
    app = Application.builder().token(BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("remove", remove_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("status", status_command))
    threading.Thread(target=check_loop, args=(app,), daemon=True).start()
    print("Bot Running - 360p Mode... [Streamlink + yt-dlp]")
    app.run_polling()

if __name__ == "__main__":
    main()
