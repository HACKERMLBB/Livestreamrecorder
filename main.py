import os
import asyncio
import threading
import json
import requests
import subprocess
import logging
import re
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
MIXDROP_API_KEY = os.getenv('MIXDROP_API_KEY')
MIXDROP_EMAIL = os.getenv('MIXDROP_EMAIL')
PORT = int(os.getenv('PORT', 10000))

# ==============================
# 👇 YOUR LINKS HERE - EDIT THIS
# ==============================
LINKS = [
    "https://www.cam4.com/gelai20",
    "https://bongacams.com/bellacutie69",
    "https://www.cam4.com/sexy_gale",
         "https://chaturbate.com/veola_sexy",
         "https://chaturbate.com/sweet_savii",
         "https://chaturbate.com/your_lovely_kai",
         "https://chaturbate.com/sweety_dianne28",
"https://bongacams.com/sweetpink061",
"https://bongacams.com/pinaysweetmommyxx",
"https://chaturbate.com/sweet_candice97",
"https://chaturbate.com/lovelyasian_babe",
"https://chaturbate.com/asuna_charming",

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

# =========================================================
# 👇 yt-dlp -F + -g වලින් වැඩ කරන Quality + m3u8 හොයනවා!
# =========================================================
def list_formats(url):
    try:
        result = subprocess.run(
            ['yt-dlp', '-F', '--no-warnings', '--no-playlist', url],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout
    except:
        return ""

def parse_formats(f_output):
    videos = []
    audios = []
    combined = []
    for line in f_output.split('\n'):
        line = line.strip()
        if not line or line.startswith('[') or line.startswith('ID') or line.startswith('---'):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        fid = parts[0]
        if not re.match(r'^[a-zA-Z0-9_\-\.]+$', fid):
            continue
        low = line.lower()
        if 'audio only' in low:
            audios.append(fid)
            continue
        m = re.search(r'(\d+)x(\d+)', line)
        if not m:
            continue
        height = int(m.group(2))
        if 'video only' in low:
            videos.append((fid, height))
        else:
            combined.append((fid, height))
    return videos, audios, combined

def pick_best_format(url):
    f_out = list_formats(url)
    if f_out:
        videos, audios, combined = parse_formats(f_out)
        combined_720 = [x for x in combined if x[1] <= 720]
        if combined_720:
            combined_720.sort(key=lambda x: x[1], reverse=True)
            best = combined_720[0]
            print(f"✅ Format Found via -F: Combined {best[0]} ({best[1]}p)")
            return best[0]
        videos_720 = [x for x in videos if x[1] <= 720]
        if videos_720:
            videos_720.sort(key=lambda x: x[1], reverse=True)
            v_id = videos_720[0][0]
            v_h = videos_720[0][1]
            if audios:
                a_id = audios[-1]
                print(f"✅ Format Found via -F: Video {v_id} ({v_h}p) + Audio {a_id}")
                return f"{v_id}+{a_id}"
            else:
                print(f"✅ Format Found via -F: Video Only {v_id} ({v_h}p)")
                return v_id
        if videos:
            videos.sort(key=lambda x: x[1])
            v_id = videos[0][0]
            if audios:
                return f"{v_id}+{audios[-1]}"
            return v_id
        if combined:
            combined.sort(key=lambda x: x[1])
            return combined[0][0]
    print(f"⚠️ -F Parse Failed, Using Fallback Format")
    return "bestvideo[height<=720]+bestaudio/best[height<=720]/best"

def get_streams(url):
    fmt = pick_best_format(url)
    try:
        result = subprocess.run(
            ['yt-dlp', '-g', '--no-warnings', '--no-playlist', '-f', fmt, url],
            capture_output=True, text=True, timeout=30
        )
        out = result.stdout.strip()
        if not out:
            return (None, None)
        lines = [l.strip() for l in out.split('\n') if l.strip().startswith('http')]
        if not lines:
            return (None, None)
        if len(lines) >= 2:
            print(f"✅ Got m3u8 via -g: Video + Audio (2 Links)")
            return (lines[0], lines[1])
        else:
            print(f"✅ Got m3u8 via -g: Single Link")
            return (lines[0], None)
    except Exception as e:
        print(f"❌ -g Failed: {e}")
        return (None, None)

def get_m3u8_link(url):
    v, a = get_streams(url)
    return v

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
    thumb_file = part_file.replace(".mp4", "_thumb.jpg")
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-ss', '2', '-i', part_file, '-vframes', '1', '-q:v', '3', thumb_file],
            capture_output=True, timeout=20
        )
        if not os.path.exists(thumb_file):
            thumb_file = None
    except:
        thumb_file = None
    try:
        with open(part_file, 'rb') as vid:
            thumb = open(thumb_file, 'rb') if thumb_file else None
            await bot.send_video(
                chat_id=CHANNEL_ID,
                video=vid,
                thumbnail=thumb,
                supports_streaming=True,
                caption=f"🎬 {title}\n\n📦 Part {part_num} ✨\n💾 45MB | 🔴 LIVE RECORD\n\n❤️ Enjoy! 🍿"
            )
            if thumb:
                thumb.close()
    except Exception as e:
        print(f"Telegram Upload Failed: {e}")
        try:
            with open(part_file, 'rb') as doc:
                await bot.send_document(chat_id=CHANNEL_ID, document=doc, caption=f"🎬 {title} - 📦 Part {part_num} ✨")
        except:
            pass
    if thumb_file and os.path.exists(thumb_file):
        try:
            os.remove(thumb_file)
        except:
            pass
    return link

async def record_live(url, title):
    part_num = 0
    mix_links = []
    fail_count = 0
    os.makedirs('downloads', exist_ok=True)
    print(f"🔴 Recording Started: {title}")
    if bot_app:
        try:
            await bot_app.bot.send_message(chat_id=CHANNEL_ID, text=f"🔴 LIVE STARTED! 🎬✨\n\n🎥 {title}\n\n⏺️ Auto Recording Started... 🚀\n📦 45MB Parts Coming Soon! 🍿\n⚡ Auto Reconnect: 3 Sec 🔄")
        except:
            pass
    while True:
        video_url, audio_url = get_streams(url)
        if not video_url:
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
        if audio_url:
            print(f"🎥 Recording Part {part_num}... [Video+Audio Merge] 🔊")
            cmd = [
                'ffmpeg', '-y',
                '-reconnect', '1',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '3',
                '-i', video_url,
                '-reconnect', '1',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '3',
                '-i', audio_url,
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-fs', '45M',
                '-c', 'copy',
                '-bsf:a', 'aac_adtstoasc',
                '-movflags', '+faststart',
                '-shortest',
                part_file
            ]
        else:
            print(f"🎥 Recording Part {part_num}... [Single Stream]")
            cmd = [
                'ffmpeg', '-y',
                '-reconnect', '1',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '3',
                '-i', video_url,
                '-fs', '45M',
                '-c', 'copy',
                '-bsf:a', 'aac_adtstoasc',
                '-movflags', '+faststart',
                part_file
            ]
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
        link = await upload_part(bot_app.bot, title, part_file, part_num)
        if link:
            mix_links.append(link)
        try:
            os.remove(part_file)
        except:
            pass
        await asyncio.sleep(3)
    if bot_app:
        text = f"🏁 LIVE ENDED! 🎬✨\n\n🎥 {title}\n\n📦 Total Parts: {part_num} 📁\n💾 45MB Each\n\n"
        if mix_links:
            text += "🔗 MixDrop Links: 📥\n\n"
            for i, link in enumerate(mix_links, 1):
                text += f"▶️ Part {i}: {link}\n"
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

async def on_startup(app):
    # 👇 PTB 21.0 එකට: Bot Start වෙන ගමන් Monitor එක Start වෙනවා!
    asyncio.create_task(monitor_loop())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    await msg.reply_text(
        "👋 Welcome! 🤖✨\n\n"
        "🎬 Cartoon Live Auto Record Bot! 🍿\n\n"
        "📋 Commands:\n"
        "➕ /add <link> - Add Site 📌\n"
        "📃 /list - List Sites 👀\n"
        "➖ /remove <link> - Remove Site 🗑️\n"
        "📺 /live - Check Live 🔴\n\n"
        "🔴 Live Started = Auto Record! ⏺️\n"
        "📦 45MB Parts = MixDrop + Channel! ☁️📢\n"
        "⚡ Broken? 3 Sec Auto Reconnect! 🔄\n"
        "🏁 Live End = Auto Stop! ✅\n\n"
        "🚀 Ready! Send /add to Start! ✨"
    )

async def add_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not context.args:
        await msg.reply_text("❌ Usage: /add <link> 📌\n\nEx: /add https://example.com/live 🔗")
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
    await msg.reply_text(f"✅ Added Successfully! 🎉\n\n🎬 {title}\n🔗 {url}\n\n🔴 Live Started = Auto Record! ⏺️✨")

async def list_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    watchlist = load_watchlist()
    if not watchlist:
        await msg.reply_text("📭 No Sites Added Yet! 😅\n\n➕ /add <link> to Add! 📌")
        return
    text = "📋 Watchlist: 👀✨\n\n"
    for i, item in enumerate(watchlist, 1):
        status = "🔴 RECORDING ⏺️" if item['url'] in recording_tasks else "⚪ Waiting... 💤"
        text += f"{i}. 🎬 {item.get('title','Live')}\n{status}\n🔗 {item['url']}\n\n"
    await msg.reply_text(text)

async def remove_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not context.args:
        await msg.reply_text("❌ Usage: /remove <link> 🗑️")
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
    # 👇 PTB 21.0 Fix: post_init එකෙන් Monitor Start කරනවා
    app.post_init = on_startup
    print(f"🤖 Bot Started on Port {PORT}... ✨")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
