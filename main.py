import os
import asyncio
import threading
import glob
import json
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
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
PORT = 10000

# ==============================
# 👇 YOUR LINKS HERE - EDIT THIS
# ==============================
LINKS = [
    "https://www.cam4.com/gelai20",
    "https://bongacams.com/bellacutie69",
    "https://www.cam4.com/sexy_gale",
]
# ==============================

WATCH_FILE = "watchlist.json"
recording_tasks = {}
bot_app = None

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "🤖 Bot is Alive! ✨"

@app_web.route('/health')
def health():
    return "OK ✅", 200

@app_web.route('/ping')
def ping():
    return "Pong! 🏓 Bot Alive! ✨", 200

def run_web():
    app_web.run(host="0.0.0.0", port=PORT)

def is_owner(update: Update):
    try:
        return update.effective_user and update.effective_user.id == OWNER_ID
    except:
        return False

def load_watchlist():
    data = []
    seen = set()
    if os.path.exists(WATCH_FILE):
        try:
            with open(WATCH_FILE, 'r') as f:
                data = json.load(f)
                for item in data:
                    seen.add(item['url'])
        except:
            data = []
    for url in LINKS:
        if url and url not in seen and "example.com" not in url:
            data.append({'url': url, 'title': 'Live'})
            seen.add(url)
    return data

def save_watchlist(data):
    with open(WATCH_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_m3u8_link(url):
    try:
        result = subprocess.run(
            ['yt-dlp', '-g', '--no-warnings', '-f', 'best[height<=720]/best', url],
            capture_output=True, text=True, timeout=30
        )
        out = result.stdout.strip()
        if not out:
            return None
        m3u8 = out.split('\n')[0]
        return m3u8 if m3u8.startswith('http') else None
    except:
        return None

def get_title(url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title', 'Live'), info.get('thumbnail', None)
    except:
        return "Live", None

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

async def upload_part(bot, title, part_file, part_num):
    link = upload_to_mixdrop(part_file)
    try:
        with open(part_file, 'rb') as vid:
            await bot.send_video(
                chat_id=CHANNEL_ID,
                video=vid,
                caption=f"🎬 {title}\n\n📦 Part {part_num} ✨\n💾 50MB | 🔴 LIVE RECORD\n\n❤️ Enjoy! 🍿"
            )
    except Exception as e:
        print(f"Telegram Upload Failed: {e}")
        try:
            with open(part_file, 'rb') as doc:
                await bot.send_document(chat_id=CHANNEL_ID, document=doc, caption=f"🎬 {title} - 📦 Part {part_num} ✨")
        except:
            pass
    return link

async def upload_part_with_cleanup(bot, title, part_file, part_num, mix_links):
    try:
        link = await upload_part(bot, title, part_file, part_num)
        if link:
            mix_links.append((part_num, link))
    except Exception as e:
        print(f"Upload Task Failed Part {part_num}: {e}")
    finally:
        try:
            if os.path.exists(part_file):
                os.remove(part_file)
        except:
            pass

async def record_live(url, title):
    part_num = 0
    mix_links = []
    fail_count = 0
    upload_tasks = []
    os.makedirs('downloads', exist_ok=True)
    print(f"🔴 Recording Started: {title}")

    if bot_app:
        try:
            await bot_app.bot.send_message(chat_id=CHANNEL_ID, text=f"🔴 LIVE STARTED! 🎬✨\n\n🎥 {title}\n\n⏺️ Auto Recording Started... 🚀\n📦 50MB Parts Coming Soon! 🍿\n⚡ Auto Reconnect: 3 Sec 🔄")
        except:
            pass

    while True:
        m3u8 = get_m3u8_link(url)
        if not m3u8:
            fail_count += 1
            print(f"⚠️ m3u8 Not Found! Retry {fail_count}/10 in 3 sec - {title}")
            if fail_count >= 10:
                print(f"🏁 Live Ended: {title}")
                break
            await asyncio.sleep(3)
            continue

        fail_count = 0
        part_num += 1
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        part_file = f"downloads/{safe_title}_part{part_num}.mp4"

        cmd = [
            'ffmpeg', '-y',
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '3',
            '-i', m3u8,
            '-fs', '50M',
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            part_file
        ]
        print(f"🎥 Recording Part {part_num}...")
        try:
            subprocess.run(cmd, capture_output=True, timeout=7200)
        except subprocess.TimeoutExpired:
            print(f"⏰ Part {part_num} Timeout")

        if not os.path.exists(part_file) or os.path.getsize(part_file) < 100000:
            print(f"⚠️ Part {part_num} Empty! Retrying in 3 sec... 🔄")
            if os.path.exists(part_file):
                try:
                    os.remove(part_file)
                except:
                    pass
            part_num -= 1
            await asyncio.sleep(3)
            continue

        task = asyncio.create_task(upload_part_with_cleanup(bot_app.bot, title, part_file, part_num, mix_links))
        upload_tasks.append(task)

        await asyncio.sleep(1)

    if upload_tasks:
        await asyncio.gather(*upload_tasks, return_exceptions=True)

    if bot_app:
        text = f"🏁 LIVE ENDED! 🎬✨\n\n🎥 {title}\n\n📦 Total Parts: {part_num} 📁\n💾 50MB Each\n\n"
        if mix_links:
            mix_links_sorted = sorted(mix_links, key=lambda x: x[0])
            text += "🔗 MixDrop Links: 📥\n\n"
            for part_no, link in mix_links_sorted:
                text += f"▶️ Part {part_no}: {link}\n"
        text += "\n✨ Recording Complete! 🎉\n❤️ Thanks for Watching! 🍿"
        try:
            await bot_app.bot.send_message(chat_id=CHANNEL_ID, text=text)
        except:
            pass
    print(f"✅ Recording Finished: {title} - {part_num} Parts")

async def monitor_loop():
    await asyncio.sleep(10)
    while True:
        try:
            watchlist = load_watchlist()
            for item in watchlist:
                url = item['url']
                title = item.get('title', 'Live')
                if url in recording_tasks:
                    continue
                m3u8 = get_m3u8_link(url)
                if m3u8:
                    real_title, _ = get_title(url)
                    if real_title and real_title != "Live":
                        title = real_title
                    task = asyncio.create_task(record_live(url, title))
                    recording_tasks[url] = task
                    task.add_done_callback(lambda t, u=url: recording_tasks.pop(u, None))
        except Exception as e:
            print(f"Monitor Error: {e}")
        await asyncio.sleep(10)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return

async def add_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    msg = update.message
    if not msg or not context.args:
        return
    url = context.args[0].strip()
    watchlist = load_watchlist()
    for item in watchlist:
        if item['url'] == url:
            await msg.reply_text("⚠️ Already Added! 👀")
            return
    title, _ = get_title(url)
    watchlist.append({'url': url, 'title': title})
    save_watchlist(watchlist)
    await msg.reply_text(f"✅ Added! 🎉\n\n🎬 {title}\n🔗 {url}")

async def list_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    msg = update.message
    watchlist = load_watchlist()
    if not watchlist:
        await msg.reply_text("📭 No Sites Added! 😅")
        return
    text = "📋 Watchlist: 👀✨\n\n"
    for i, item in enumerate(watchlist, 1):
        status = "🔴 RECORDING ⏺️" if item['url'] in recording_tasks else "⚪ Waiting... 💤"
        text += f"{i}. 🎬 {item.get('title','Live')}\n{status}\n🔗 {item['url']}\n\n"
    await msg.reply_text(text)

async def remove_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    msg = update.message
    if not msg or not context.args:
        return
    url = context.args[0].strip()
    watchlist = load_watchlist()
    new_list = [x for x in watchlist if x['url'] != url]
    if len(new_list) == len(watchlist):
        await msg.reply_text("❌ Not Found! 😅")
        return
    save_watchlist(new_list)
    await msg.reply_text(f"✅ Removed! 🗑️\n🔗 {url}")

async def live_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    msg = update.message
    watchlist = load_watchlist()
    if not watchlist:
        await msg.reply_text("📭 Watchlist Empty! 😅")
        return
    await msg.reply_text("🔍 Checking Live... ⏳✨")
    text = "📺 Live Status: 👀\n\n"
    for item in watchlist:
        m3u8 = get_m3u8_link(item['url'])
        if m3u8:
            text += f"🔴 LIVE - 🎬 {item.get('title','Live')}\n"
        else:
            text += f"⚪ OFFLINE - 🎬 {item.get('title','Live')}\n"
    await msg.reply_text(text)

async def ignore_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return

def main():
    global bot_app
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    bot_app = app
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_site))
    app.add_handler(CommandHandler("list", list_sites))
    app.add_handler(CommandHandler("remove", remove_site))
    app.add_handler(CommandHandler("live", live_now))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ignore_all))
    print(f"🤖 Bot Started on Port {PORT}... ✨")
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_loop())
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main() 
