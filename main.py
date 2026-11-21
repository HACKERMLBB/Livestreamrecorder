import os
import asyncio
import threading
import glob
import requests
import subprocess
import logging
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
MIXDROP_API_KEY = os.getenv('MIXDROP_API_KEY')
MIXDROP_EMAIL = os.getenv('MIXDROP_EMAIL')
PORT = int(os.environ.get("PORT", 10000))

# Flask Web Server - Render Web Service එකට ඕනේ මේක!
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is Alive! 🤖"

@app_web.route('/health')
def health():
    return "OK", 200

@app_web.route('/ping')
def ping():
    return "Pong! Bot Alive!", 200

def run_web():
    app_web.run(host="0.0.0.0", port=PORT)

def get_m3u8_link(url):
    try:
        # yt-dlp -g "url" -> Get m3u8 Direct Link
        result = subprocess.run(
            ['yt-dlp', '-g', '--no-warnings', '-f', 'best[height<=720]/best', url],
            capture_output=True, text=True, timeout=60
        )
        m3u8 = result.stdout.strip().split('\n')[0]
        print(f"m3u8 Found: {m3u8[:120]}")
        return m3u8
    except Exception as e:
        print(f"m3u8 Get Failed: {e}")
        return None

def get_title(url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title', 'Video'), info.get('thumbnail', None)
    except:
        return "Video", None

def download_from_m3u8(m3u8_url, output_file):
    cmd = ['ffmpeg', '-y', '-i', m3u8_url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', output_file]
    print(f"Downloading from m3u8...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    return os.path.exists(output_file)

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
    msg = update.message
    if not msg:
        return
    await msg.reply_text(
        "👋 Welcome! 🤖✨\n\n"
        "📥 Send Any Live / Video Link!\n\n"
        "🔍 Get m3u8 with yt-dlp -g\n"
        "⬇️ Download from m3u8\n"
        "✂️ Split 48MB\n"
        "☁️ Upload MixDrop\n"
        "📢 Post All Parts to Channel\n\n"
        "🚀 Send a link!"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg or not msg.text:
        return
    url = msg.text.strip()
    if not url.startswith('http'):
        return

    status = await msg.reply_text("🔍 Getting m3u8 Link... ⏳")
    os.makedirs('downloads', exist_ok=True)

    try:
        m3u8_url = get_m3u8_link(url)
        if not m3u8_url:
            await status.edit_text("❌ m3u8 Not Found! Try Another Link!")
            return

        await status.edit_text(f"✅ m3u8 Found!\n🔗 {m3u8_url[:60]}...\n⬇️ Downloading from m3u8... 🚀")

        title, thumb_url = get_title(url)
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
        video_file = f"downloads/{safe_title}.mp4"

        success = download_from_m3u8(m3u8_url, video_file)
        if not success:
            await status.edit_text("❌ Download Failed from m3u8!")
            return

        thumb = None
        if thumb_url:
            try:
                thumb = "downloads/thumb.jpg"
                r = requests.get(thumb_url, timeout=20)
                open(thumb, 'wb').write(r.content)
            except:
                thumb = None

        await status.edit_text("✂️ Splitting into 48MB Parts... 📦")
        parts = split_video(video_file)
        total = len(parts)

        await status.edit_text(f"☁️ Uploading {total} Parts... 🚀")
        mix_links = []
        for idx, part in enumerate(parts):
            part_num = idx + 1
            link = upload_to_mixdrop(part)
            if link:
                mix_links.append(link)

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

        await status.edit_text(f"✅ All Done! 🎉\n\n🎬 {title}\n📦 {total} Parts Posted!")

    except Exception as e:
        try:
            await status.edit_text(f"❌ Error: {str(e)[:400]}")
        except:
            pass

def main():
    # Flask Web Server එක වෙන Thread එකක Run කරනවා
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.UpdateType.CHANNEL_POST, handle_link))
    print(f"Bot Started on Port {PORT}...")
    logger.info("Bot Started - Polling...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
