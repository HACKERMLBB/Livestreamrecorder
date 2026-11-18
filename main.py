import os
import asyncio
import subprocess
import glob
import requests
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
MIXDROP_EMAIL = os.getenv("MIXDROP_EMAIL")
MIXDROP_KEY = os.getenv("MIXDROP_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ALLOWED_USERS = [7038888904]

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_BYTES = 500 * 1024 * 1024

def upload_mixdrop(file_path):
    print(f"Uploading {file_path} Size: {os.path.getsize(file_path)/1024/1024:.1f}MB", flush=True)
    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                r = requests.post(
                    "https://ul.mixdrop.ag/api",
                    data={"email": MIXDROP_EMAIL, "key": MIXDROP_KEY},
                    files={"file": f},
                    timeout=1200
                )
            print(f"Mixdrop Response: {r.text[:800]}", flush=True)
            data = r.json()
            if data.get("success"):
                fileref = data["result"]["fileref"]
                url = f"https://mixdrop.ag/f/{fileref}"
                print(f"Uploaded: {url}", flush=True)
                return url
            print(f"Mixdrop Failed: {data}", flush=True)
        except Exception as e:
            print(f"Upload Error attempt {attempt+1}: {e}", flush=True)
            time.sleep(5)
    return None

def get_video_url(url):
    result = subprocess.run(
        ["yt-dlp", "-g", "-f", "best[ext=mp4]/best", url],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().splitlines()[0]
    result = subprocess.run(["yt-dlp", "-g", url], capture_output=True, text=True, timeout=120)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().splitlines()[0]
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send a link to record")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("Not allowed")
        return
    url = update.message.text.strip()
    if "http" not in url:
        return
    msg = await update.message.reply_text(f"Recording Started...\n{url}")
    asyncio.create_task(process_stream(update, context, url, msg))

async def process_stream(update, context, url, msg):
    job_id = str(int(time.time()))[-6:]
    folder = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(folder, exist_ok=True)
    links = []
    thumb_path = os.path.join(folder, "thumb.jpg")
    highlight_path = os.path.join(folder, "highlight.mp4")
    ffmpeg_proc = None
    uploaded_files = set()

    try:
        await msg.edit_text("Getting stream URL...")
        stream_url = await asyncio.to_thread(get_video_url, url)
        if not stream_url:
            await msg.edit_text("Record Failed - No stream URL")
            return

        await msg.edit_text("Recording + Splitting + Uploading in parallel...")

        part_pattern = os.path.join(folder, "part_%03d.mp4")

        ffmpeg_cmd = [
            "ffmpeg", "-i", stream_url,
            "-c", "copy",
            "-map", "0",
            "-f", "segment",
            "-segment_time", "3600",
            "-segment_format", "mp4",
            "-reset_timestamps", "1",
            "-fs", str(MAX_BYTES),
            part_pattern
        ]

        ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        async def watcher():
            while True:
                parts = sorted(glob.glob(os.path.join(folder, "part_*.mp4")))
                active = ffmpeg_proc.poll() is None
                ready = parts[:-1] if active else parts
                for p in ready:
                    if p in uploaded_files:
                        continue
                    s1 = os.path.getsize(p)
                    await asyncio.sleep(2)
                    if not os.path.exists(p):
                        continue
                    s2 = os.path.getsize(p)
                    if s1 != s2:
                        continue
                    uploaded_files.add(p)
                    await msg.edit_text(f"Uploading {os.path.basename(p)}... Total uploaded: {len(links)}")
                    link = await asyncio.to_thread(upload_mixdrop, p)
                    if link:
                        links.append(link)
                    if os.path.exists(p):
                        os.remove(p)
                if not active:
                    break
                await asyncio.sleep(5)
            return

        watcher_task = asyncio.create_task(watcher())

        while ffmpeg_proc.poll() is None:
            await asyncio.sleep(5)

        await watcher_task

        remaining = sorted(glob.glob(os.path.join(folder, "part_*.mp4")))
        for p in remaining:
            if p not in uploaded_files:
                link = await asyncio.to_thread(upload_mixdrop, p)
                if link:
                    links.append(link)
                if os.path.exists(p):
                    os.remove(p)

        if not links:
            await msg.edit_text("Failed - No parts uploaded")
            return

        try:
            subprocess.run(["ffmpeg", "-i", stream_url, "-ss", "10", "-vframes", "1", "-y", thumb_path], capture_output=True, timeout=60)
        except Exception as e:
            print(f"Thumb error: {e}", flush=True)

        hl_link = None
        try:
            subprocess.run(["ffmpeg", "-i", stream_url, "-t", "300", "-c", "copy", "-y", highlight_path], capture_output=True, timeout=120)
            if os.path.exists(highlight_path):
                hl_link = await asyncio.to_thread(upload_mixdrop, highlight_path)
                os.remove(highlight_path)
        except Exception as e:
            print(f"Highlight error: {e}", flush=True)

        caption = f"NEW LIVE RECORDING\n\n{url}\n\n"
        for i, l in enumerate(links, 1):
            caption += f"Part {i}: {l}\n"
        if hl_link:
            caption += f"\nHighlights: {hl_link}\n"

        if os.path.exists(thumb_path):
            with open(thumb_path, "rb") as photo:
                await context.bot.send_photo(CHANNEL_ID, photo=photo, caption=caption)
            os.remove(thumb_path)
        else:
            await context.bot.send_message(CHANNEL_ID, caption)

        await msg.edit_text(f"Done! {len(links)} parts uploaded")

    except Exception as e:
        print(f"Error: {e}", flush=True)
        await msg.edit_text(f"Error: {e}")
    finally:
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            ffmpeg_proc.kill()

async def error_handler(update, context):
    print(f"Error: {context.error}", flush=True)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_error_handler(error_handler)
    print("Bot Started", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
