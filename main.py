import os
import threading
import subprocess
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== FAKE WEB SERVER FOR RENDER FREE WEB SERVICE =====
app_web = Flask(__name__)

@app_web.route("/")
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# =======================================================

# ===== CONFIG FROM RENDER ENV VARS =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MIXDROP_EMAIL = os.environ.get("MIXDROP_EMAIL")
MIXDROP_KEY = os.environ.get("MIXDROP_KEY")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
# ========================================

# ===== PRIVATE LOCK - ONLY YOU CAN USE BOT =====
ALLOWED_USERS = [7038888904]
# ================================================

def upload_mixdrop(file_path):
    print(f"Uploading {file_path} to Mixdrop...")
    with open(file_path, "rb") as f:
        response = requests.post(
            "https://api.mixdrop.ag/upload",
            files={"file": f},
            data={"email": MIXDROP_EMAIL, "key": MIXDROP_KEY},
            timeout=1200
        )
    data = response.json()
    print(data)
    result = data.get("result", {})
    return result.get("url") or data.get("url")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("Sorry, this bot is private.")
        return
    await update.message.reply_text(
        "Hi! Send any Live link, I will record it, upload to Mixdrop and post the link to the channel."
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("Sorry, this bot is private.")
        return

    url = update.message.text.strip()
    if "http" not in url:
        return

    await update.message.reply_text("Recording live... Uploading to Mixdrop, please wait.")

    try:
        # ===== SAME AS TERMUX - NO -f, BEST AVAILABLE QUALITY =====
        subprocess.run(
            ["yt-dlp", "-o", "%(title)s.%(ext)s", url],
            check=True
        )

        # Find downloaded file
        downloaded_file = None
        for f in os.listdir("."):
            if f.endswith((".mp4", ".mkv", ".webm", ".ts")):
                downloaded_file = f
                break

        if not downloaded_file:
            await update.message.reply_text("Download failed, file not found.")
            return

        # Rename to full.mp4 for next steps
        if downloaded_file != "full.mp4":
            os.rename(downloaded_file, "full.mp4")

        subprocess.run(
            ["ffmpeg", "-y", "-ss", "10", "-i", "full.mp4", "-vframes", "1", "thumb.jpg"],
            check=True
        )

        subprocess.run(
            ["ffmpeg", "-y", "-ss", "0", "-i", "full.mp4", "-t", "300", "-c", "copy", "highlights.mp4"],
            check=True
        )

        await update.message.reply_text("Uploading to Mixdrop...")

        full_link = upload_mixdrop("full.mp4")
        highlights_link = upload_mixdrop("highlights.mp4")

        caption = (
            "NEW LIVE RECORDING\n\n"
            f"Full Video: {full_link}\n"
            f"Highlights (5 Min): {highlights_link}\n\n"
            "#Live #Recorded"
        )

        with open("thumb.jpg", "rb") as photo:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo,
                caption=caption
            )

        await update.message.reply_text(f"Done! Posted to channel.\nFull: {full_link}")

        for file_name in ["full.mp4", "highlights.mp4", "thumb.jpg"]:
            if os.path.exists(file_name):
                os.remove(file_name)

    except Exception as e:
        await update.message.reply_text(f"Error occurred: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
