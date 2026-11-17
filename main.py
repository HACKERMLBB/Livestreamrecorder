import os
import threading
import subprocess
import requests
import json
import asyncio
import uuid
import shutil
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ======================================================
# 🌐 FAKE WEB SERVER FOR RENDER - KEEPS BOT ALIVE
# ======================================================
app_web = Flask(__name__)

@app_web.route("/")
def home():
    return "✅ Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# ======================================================

# 🔑 CONFIG - FROM RENDER ENV VARIABLES
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MIXDROP_EMAIL = os.environ.get("MIXDROP_EMAIL")
MIXDROP_KEY = os.environ.get("MIXDROP_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
ALLOWED_USERS = [7038888904]  # 👤 Put Your Telegram ID Here

# 📥 UPLOAD QUEUE - Upload One By One
upload_queue = asyncio.Queue()

# ======================================================
# ☁️ UPLOAD TO MIXDROP
# ======================================================
def upload_mixdrop(file_path):
    size_mb = os.path.getsize(file_path) / 1024 / 1024
    print(f"☁️ Uploading {file_path} - {size_mb:.1f} MB", flush=True)
    with open(file_path, "rb") as f:
        response = requests.post(
            "https://api.mixdrop.ag/upload",
            files={"file": f},
            data={"email": MIXDROP_EMAIL, "key": MIXDROP_KEY},
            timeout=3600
        )
    print(f"📩 Mixdrop Response: {response.text[:500]}", flush=True)
    try:
        data = response.json()
    except:
        return None
    result = data.get("result", {})
    return result.get("url") or data.get("url")

# ======================================================
# ⏱️ GET VIDEO DURATION
# ======================================================
def get_duration(file_path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", file_path],
            capture_output=True, text=True
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except:
        return 0

def run_cmd(cmd):
    subprocess.run(cmd, check=True)

# ======================================================
# 📥 YT-DLP - TRY ALL METHODS ONE BY ONE
# ======================================================
def download_with_ytdlp(url, folder):
    out = os.path.join(folder, "%(title)s.%(ext)s")

    attempts = [
        # 1️⃣ SIMPLEST - Just yt-dlp "link"
        ["yt-dlp", "-o", out, url],

        # 2️⃣ LIVE - From Start, Convert To MP4
        ["yt-dlp", "--no-playlist", "--live-from-start", "--merge-output-format", "mp4",
         "--remux-video", "mp4", "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
         "-o", out, url],

        # 3️⃣ BEST MP4 ONLY - For YouTube / Facebook Live
        ["yt-dlp", "--no-playlist", "-f", "best[ext=mp4]/best",
         "--merge-output-format", "mp4",
         "-o", out, url],

        # 4️⃣ BEST ANY FORMAT - For TikTok / Instagram / Reels
        ["yt-dlp", "--no-playlist", "-f", "best",
         "-o", out, url],

        # 5️⃣ BYPASS BLOCK - Chrome + Android Player
        ["yt-dlp", "--no-playlist", "--impersonate", "chrome",
         "--extractor-args", "youtube:player_client=android",
         "-f", "best[height<=720]/best",
         "-o", out, url],

        # 6️⃣ RAW - No Checks, Last Try
        ["yt-dlp", "--no-playlist", "--no-check-certificates",
         "-o", out, url],
    ]

    for i, cmd in enumerate(attempts):
        print(f"🔄 Trying yt-dlp Method {i+1}...", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        files = [f for f in os.listdir(folder) if f.endswith((".mp4", ".mkv", ".webm", ".ts", ".mov"))]
        if files and result.returncode == 0:
            print(f"✅ Success With Method {i+1}", flush=True)
            return True
        print(f"❌ Method {i+1} Failed", flush=True)

    print("❌ All yt-dlp Methods Failed", flush=True)
    return False

# ======================================================
# ☁️ UPLOAD WORKER - ONE UPLOAD AT A TIME
# ======================================================
async def upload_worker(app):
    print("🚀 Upload Worker Started", flush=True)
    while True:
        job = await upload_queue.get()
        job_id = job["job_id"]
        folder = job["folder"]
        bot = app.bot
        user_id = job["user_id"]
        try:
            print(f"[{job_id}] ☁️ Starting Upload...", flush=True)
            await bot.send_message(chat_id=user_id, text=f"[{job_id}] ☁️ Upload Started...")

            full_path = os.path.join(folder, "full.mp4")
            total_size_mb = os.path.getsize(full_path) / 1024 / 1024
            duration = get_duration(full_path)

            # 🖼️ THUMBNAIL - Frame At 10s
            thumb_path = os.path.join(folder, "thumb.jpg")
            await asyncio.to_thread(run_cmd, ["ffmpeg", "-y", "-ss", "10", "-i", full_path, "-vframes", "1", thumb_path])

            # ✨ HIGHLIGHTS - First 5 Minutes
            highlights_path = os.path.join(folder, "highlights.mp4")
            await asyncio.to_thread(run_cmd, ["ffmpeg", "-y", "-ss", "0", "-i", full_path, "-t", "300", "-c", "copy", highlights_path])

            # ✂️ SPLIT TO 500MB PARTS
            if total_size_mb <= 500:
                parts = [full_path]
            else:
                segment_time = int(duration * 500 / total_size_mb)
                if segment_time < 60:
                    segment_time = 60
                print(f"[{job_id}] ✂️ Splitting To 500MB, Segment = {segment_time}s", flush=True)
                await asyncio.to_thread(run_cmd, ["ffmpeg", "-y", "-i", full_path, "-c", "copy", "-map", "0", "-segment_time", str(segment_time), "-f", "segment", "-reset_timestamps", "1", os.path.join(folder, "part_%03d.mp4")])
                os.remove(full_path)
                parts = sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.startswith("part_") and f.endswith(".mp4")])

            # 📤 UPLOAD PARTS ONE BY ONE
            part_links = []
            for i, part in enumerate(parts):
                link = await asyncio.to_thread(upload_mixdrop, part)
                part_links.append(f"📦 Part {i+1}: {link}")
                if os.path.exists(part):
                    os.remove(part)

            # 📤 UPLOAD HIGHLIGHTS
            highlights_link = await asyncio.to_thread(upload_mixdrop, highlights_path)

            # 📝 CAPTION
            caption = (
                "🎬 NEW LIVE RECORDING - FULL VIDEO\n\n"
                f"{chr(10).join(part_links)}\n\n"
                f"✨ Highlights (5 Min): {highlights_link}\n\n"
                "#Live #Recorded"
            )

            # 📢 SEND TO CHANNEL
            with open(thumb_path, "rb") as photo:
                await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=caption)

            await bot.send_message(chat_id=user_id, text=f"[{job_id}] ✅ Done! Sent To Channel.\n{chr(10).join(part_links)}")

        except Exception as e:
            print(f"[{job_id}] ❌ Upload Error: {e}", flush=True)
            try:
                await bot.send_message(chat_id=user_id, text=f"[{job_id}] ❌ Upload Error: {e}")
            except:
                pass
        finally:
            if os.path.exists(folder):
                shutil.rmtree(folder, ignore_errors=True)
            upload_queue.task_done()

# ======================================================
# 🔴 RECORD WORKER - MANY RECORDS AT SAME TIME
# ======================================================
async def record_job(url, user_id, job_id, app):
    folder = f"job_{job_id}"
    os.makedirs(folder, exist_ok=True)
    try:
        print(f"[{job_id}] 🔴 Recording Started: {url}", flush=True)
        await app.bot.send_message(chat_id=user_id, text=f"[{job_id}] 🔴 Recording Started...")

        success = await asyncio.to_thread(download_with_ytdlp, url, folder)
        if not success:
            await app.bot.send_message(chat_id=user_id, text=f"[{job_id}] ❌ Download Failed - All yt-dlp Methods Failed.")
            shutil.rmtree(folder, ignore_errors=True)
            return

        downloaded_file = None
        for f in os.listdir(folder):
            if f.endswith((".mp4", ".mkv", ".webm", ".ts", ".mov")):
                downloaded_file = os.path.join(folder, f)
                break

        if not downloaded_file:
            await app.bot.send_message(chat_id=user_id, text=f"[{job_id}] ❌ Download Failed.")
            shutil.rmtree(folder, ignore_errors=True)
            return

        full_path = os.path.join(folder, "full.mp4")
        if downloaded_file != full_path:
            os.rename(downloaded_file, full_path)

        print(f"[{job_id}] ✅ Recording Done, Added To Upload Queue", flush=True)
        await app.bot.send_message(chat_id=user_id, text=f"[{job_id}] ✅ Record Done! Added To Upload Queue.")
        
        await upload_queue.put({"job_id": job_id, "folder": folder, "user_id": user_id})

    except Exception as e:
        print(f"[{job_id}] ❌ Record Error: {e}", flush=True)
        await app.bot.send_message(chat_id=user_id, text=f"[{job_id}] ❌ Record Error: {e}")
        if os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)

# ======================================================
# 🤖 TELEGRAM HANDLERS
# ======================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Sorry, This Bot Is Private.")
        return
    await update.message.reply_text("👋 Hi! Send Links, I Will Record All At Same Time, Upload One By One To Mixdrop. 🎬")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Sorry, This Bot Is Private.")
        return
    url = update.message.text.strip()
    if "http" not in url:
        return
    
    job_id = str(uuid.uuid4())[:6]
    asyncio.create_task(record_job(url, update.effective_user.id, job_id, context.application))
    await update.message.reply_text(f"[{job_id}] ✅ Link Received! Recording Started. 🔴")

async def post_init(app):
    asyncio.create_task(upload_worker(app))

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    print("🤖 Bot Is Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
