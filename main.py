import os
import asyncio
import threading
import glob
import requests
import subprocess
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
MIXDROP_API_KEY = os.getenv('MIXDROP_API_KEY')
MIXDROP_EMAIL = os.getenv('MIXDROP_EMAIL')
PORT = int(os.environ.get("PORT", 10000))

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is Alive!"

def run_web():
    app_web.run(host="0.0.0.0", port=PORT)

def upload_to_mixdrop(file_path):
    try:
        url = "https://api.mixdrop.ag/upload"
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            data = {'email': MIXDROP_EMAIL, 'key': MIXDROP_API_KEY}
            r = requests.post(url, files=files, data=data, timeout=600)
            res = r.json()
            if res.get('success'):
                return f"https://mixdrop.ag/f/{res['result']['fileref']}"
            return None
    except Exception as e:
        print(f"Upload Failed: {e}")
        return None

def split_video(input_file):
    file_size = os.path.getsize(input_file)
    chunk = 48 * 1024 * 1024
    if file_size <= chunk:
        return [input_file]
    base = os.path.splitext(input_file)[0]
    subprocess.run(['split', '-b', '48m', input_file, f'{base}_split_'], check=True)
    split_files = sorted(glob.glob(f'{base}_split_*'))
    final = []
    for idx, sf in enumerate(split_files):
        new_name = f"{base}_part{idx+1}.mp4"
        os.rename(sf, new_name)
        final.append(new_name)
    return final

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! 🤖✨\n\n"
        "📥 Send Any Video Link!\n\n"
        "🔍 Find m3u8\n"
        "✂️ Split 48MB\n"
        "☁️ Upload MixDrop\n"
        "📢 Post All Parts to Channel\n\n"
        "🚀 Send a link!"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith('http'):
        await update.message.reply_text("❌ Please send a valid link!")
        return

    status = await update.message.reply_text("🔍 Finding Stream... ⏳")
    os.makedirs('downloads', exist_ok=True)

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'format': 'best[height<=720]/best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'writethumbnail': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'ios', 'mweb']}}
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Video')
            files = glob.glob('downloads/*')
            video_file = max(files, key=os.path.getctime) if files else ""
            thumbs = glob.glob('downloads/*.jpg') + glob.glob('downloads/*.webp') + glob.glob('downloads/*.png')
            thumb = thumbs[0] if thumbs else None
            print(f"m3u8 URL: {info.get('url', '')[:100]}")

        await status.edit_text("✂️ Splitting into 48MB Parts... 📦")
        parts = split_video(video_file)
        total = len(parts)

        await status.edit_text(f"☁️ Uploading {total} Parts... 🚀")

        mix_links = []
        for idx, part in enumerate(parts):
            part_num = idx + 1

            # 1. Upload to MixDrop
            link = upload_to_mixdrop(part)
            if link:
                mix_links.append(link)

            # 2. Send Part Video to Telegram Channel
            with open(part, 'rb') as vid:
                await context.bot.send_video(
                    chat_id=CHANNEL_ID,
                    video=vid,
                    caption=f"🎬 {title}\n\n📦 Part {part_num}/{total}\n✨ Enjoy! ❤️"
                )

            await status.edit_text(f"✅ Part {part_num}/{total} Done! MixDrop + Telegram! 🎉")

            try:
                os.remove(part)
            except:
                pass

        # 3. Send Thumbnail + All Links to Channel
        caption = f"🎬 *{title}*\n\n"
        caption += f"📦 Total Parts: {total}\n"
        caption += f"📁 Size: 48MB Each\n\n"
        caption += "🔗 *MixDrop Links:*\n"
        for i, link in enumerate(mix_links, 1):
            caption += f"▶️ Part {i}: {link}\n"
        caption += "\n✨ Enjoy! ❤️"

        if thumb and os.path.exists(thumb):
            with open(thumb, 'rb') as photo:
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=caption, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=caption, parse_mode="Markdown")

        for f in glob.glob('downloads/*'):
            try:
                os.remove(f)
            except:
                pass

        await status.edit_text(f"✅ All Done! 🎉\n\n🎬 {title}\n📦 {total} Parts Posted to MixDrop + Telegram!")

    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)[:400]}")

def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    print(f"Bot Started on Port {PORT}...")
    app.run_polling()

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
