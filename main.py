import os
import subprocess
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== CONFIG - FILL YOUR DETAILS HERE =====
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
MIXDROP_EMAIL = "YOUR_MIXDROP_EMAIL"
MIXDROP_KEY = "YOUR_MIXDROP_API_KEY"
CHANNEL_ID = "@YOUR_CHANNEL_USERNAME"
# ============================================

def upload_mixdrop(file_path):
    print(f"Uploading {file_path} to Mixdrop...")
    with open(file_path, "rb") as f:
        response = requests.post(
            "https://api.mixdrop.ag/upload",
            files={"file": f},
            data={"email": MIXDROP_EMAIL, "key": MIXDROP_KEY},
            timeout=600
        )
    data = response.json()
    print(data)
    result = data.get("result", {})
    return result.get("url") or data.get("url")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! Send your Live stream link chaturbate/cam4/camsoda/bongacams/ stripchat not working , I will record it, upload to Mixdrop and post the link to the channel."
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "http" not in url:
        return

    await update.message.reply_text("Recording live... Uploading to Mixdrop, please wait.")

    try:
        # 1. Download in 480p
        subprocess.run(
            ["yt-dlp", "-f", "best[height<=480]", "-o", "full.mp4", url],
            check=True
        )

        # 2. Create thumbnail from 10th second
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "10", "-i", "full.mp4", "-vframes", "1", "thumb.jpg"],
            check=True
        )

        # 3. Create 5 minute highlights from start
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "0", "-i", "full.mp4", "-t", "300", "-c", "copy", "highlights.mp4"],
            check=True
        )

        await update.message.reply_text("Uploading to Mixdrop...")

        # 4. Upload to Mixdrop
        full_link = upload_mixdrop("full.mp4")
        highlights_link = upload_mixdrop("highlights.mp4")

        # 5. Post to Telegram Channel
        caption = (
            "NEW LIVE RECORDING\n\n"
            f"Full Video (480p): {full_link}\n"
            f"Highlights (5 Min): {highlights_link}\n\n"
            "#Live #Recorded"
        )

        with open("thumb.jpg", "rb") as photo:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo,
                caption=caption
            )

        await update.message.reply_text(
            f"Done! Posted to channel.\nFull: {full_link}"
        )

        # 6. Delete local files to save phone storage
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
