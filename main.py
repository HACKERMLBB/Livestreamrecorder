# ============================================================
# 🌸✨ LiveStream Recorder - 30 Links - ALL AT ONCE! ✨🌸
# 💖 480p | 📦 5MB Parts | ⚡ 30 Parallel Record + Upload!
# 🎬 Local Merge - Telegram එකෙන් බාන්නේ නෑ!
# ✅ .ts Direct | No Convert | No Missing!
# ============================================================

import os
import asyncio
import threading
import json
import requests
import subprocess
import logging
from flask import Flask, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
import yt_dlp

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
MIXDROP_API_KEY = os.getenv('MIXDROP_API_KEY')
MIXDROP_EMAIL = os.getenv('MIXDROP_EMAIL')
PORT = int(os.getenv('PORT', 10000))

LINKS = [
    "https://www.cam4.com/gelai20",
    "https://bongacams.com/bellacutie69",
    "https://www.cam4.com/sexy_gale",
"https://bongacams.com/sweetpink061",
"https://bongacams.com/pinaysweetmommyxx",
  "https://bongacams.com/1sweetasian",
"https://www.cam4.com/me_and_you",
"https://www.cam4.com/preggy_jerch2",
"https://www.cam4.com/sexyaubrey",
"https://www.cam4.com/sweeetmary",
"https://www.cam4.com/obsesssion_4u",
"https://bongacams.com/irissweety",
"https://bongacams.com/AlexaBrown12",
"https://bongacams.com/Luluupeach69",
"https://bongacams.com/RoxanneHill",
"https://bongacams.com/Bella-152",
"https://bongacams.com/MiiaaCarter",
"https://bongacams.com/Natashaa-",
"https://bongacams.com/Paola233",
"https://bongacams.com/HollyTegan",
"https://bongacams.com/MiliMattel",
"https://bongacams.com/-Sthef-castle-",
"https://bongacams.com/ChloeMontes",
"https://bongacams.com/RyderParker",
"https://www.cam4.com/Nemesis_hot608",
"https://www.cam4.com/Girl_hot_hot1",
"https://www.cam4.com/NatashaSloane",
"https://www.cam4.com/Malena_99",
"https://www.cam4.com/ximena_ruiz18",
]

MAX_CONCURRENT = 30
PART_SIZE = 5 * 1024 * 1024
CHECK_BATCH = 30

recording_tasks = {}
bot_app = None
upload_stats = {"done": 0}

app_web = Flask(__name__)

async def safe_send(text):
    if not bot_app:
        return
    for attempt in range(3):
        try:
            await bot_app.bot.send_message(chat_id=CHANNEL_ID, text=text)
            return
        except Exception as e:
            print(f"⚠️ Send Retry {attempt+1}/3: {e}")
            await asyncio.sleep(2)

@app_web.route('/')
def home():
    return f"🤖 Bot Alive! ✨<br>🎥 Recording: {len(recording_tasks)}/30<br>✅ Uploaded: {upload_stats['done']}<br>⚡ Mode: 30 Parallel | 5MB | Local Merge"

@app_web.route('/health')
def health():
    return "OK ✅", 200

@app_web.route('/api/status')
def api_status():
    return jsonify({"done": upload_stats["done"], "recording": len(recording_tasks)})

def run_web():
    app_web.run(host="0.0.0.0", port=PORT, threaded=True)

def load_watchlist():
    data = []
    seen = set()
    if os.path.exists("watchlist.json"):
        try:
            with open("watchlist.json") as f:
                data = json.load(f)
                for x in data:
                    seen.add(x['url'])
        except:
            data = []
    for url in LINKS:
        if url and url not in seen and "http" in url and "link" not in url:
            data.append({'url': url, 'title': 'Live'})
            seen.add(url)
    return data

def get_m3u8_link(url):
    try:
        result = subprocess.run(
            ['yt-dlp', '-g', '--no-warnings', '-f', 'best[height<=480]/best', url],
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
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True, 'format': 'best[height<=480]/best'}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title', 'Live'), None
    except:
        return "Live", None

def upload_to_mixdrop(file_path):
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            data = {'email': MIXDROP_EMAIL, 'key': MIXDROP_API_KEY}
            r = requests.post("https://api.mixdrop.ag/upload", files=files, data=data, timeout=600)
            res = r.json()
            if res.get('success'):
                return f"https://mixdrop.ag/f/{res['result']['fileref']}"
            print(f"❌ Mixdrop Failed: {res}")
            return None
    except Exception as e:
        print(f"❌ Upload Failed: {e}")
        return None

async def upload_part_now(file_path, title, part_num, is_last=False):
    print(f"📤 [Background] Uploading: {title} Part {part_num} | Size: {os.path.getsize(file_path)//1024}KB")
    try:
        link = await asyncio.to_thread(upload_to_mixdrop, file_path)
        print(f"☁️ Mixdrop Link Part {part_num}: {link}")
        try:
            with open(file_path, 'rb') as doc:
                await bot_app.bot.send_document(
                    chat_id=CHANNEL_ID,
                    document=doc,
                    filename=f"{title}_Part{part_num}.ts",
                    caption=f"🎬 {title}\n\n⚡ Part {part_num} ✨\n💾 5MB | 🎥 480p | 🔴 LIVE RECORD\n\n☁️ Mixdrop: {link}\n\n❤️ Enjoy! 🍿"
                )
        except Exception as e:
            print(f"❌ Send Failed Part {part_num}: {e}")
            await safe_send(f"🎬 {title} - Part {part_num}\n☁️ Link: {link}")
        upload_stats["done"] += 1
        if is_last:
            await safe_send(f"🏁 LIVE ENDED! 🎬✨\n\n🎥 {title}\n\n✅ All Parts Uploaded! 💖\n🎬 Full Video හදනවා... ⏳")
    except Exception as e:
        print(f"❌ Upload Part Error {part_num}: {e}")

async def merge_local_full_video(all_parts, title):
    if not all_parts or len(all_parts) < 2:
        print(f"⚠️ Merge Skip: Parts අඩුයි! {title} - {len(all_parts)}")
        for pf in all_parts:
            try: os.remove(pf)
            except: pass
        return
    print(f"🎬 Local Merge Start: {title} | Parts: {len(all_parts)}")
    await safe_send(f"🎬 Full Video හදනවා... ⏳✨\n\n🎥 {title}\n📦 Parts: {len(all_parts)}\n⏳ Local Part ටික එකතු කරනවා... 💖")
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
    full_path = f"downloads/{safe_title}_FULL.ts"
    try:
        with open(full_path, 'wb') as out:
            for pf in sorted(all_parts):
                if os.path.exists(pf):
                    with open(pf, 'rb') as f:
                        while True:
                            chunk = f.read(1024*1024)
                            if not chunk:
                                break
                            out.write(chunk)
                    print(f"  ✅ Added: {pf}")
        size = os.path.getsize(full_path) // 1024 // 1024
        print(f"✅ Full Video Ready: {size}MB")
        link = await asyncio.to_thread(upload_to_mixdrop, full_path)
        await safe_send(
            f"🎬 FULL VIDEO READY! 🍿✨\n\n"
            f"🎥 {title}\n📦 Total Parts: {len(all_parts)}\n💾 Size: {size}MB\n\n"
            f"☁️ Full Video Link:\n{link}\n\n❤️ Enjoy Full Video! 💖"
        )
    except Exception as e:
        print(f"❌ Merge Failed: {e}")
        await safe_send(f"❌ Full Video Failed: {title}")
    finally:
        try: os.remove(full_path)
        except: pass
        for pf in all_parts:
            try: os.remove(pf)
            except: pass

async def record_live_light(url, title):
    part_num = 0
    fail_count = 0
    part_file = None
    seen_segments = set()
    upload_tasks = []
    all_parts = []
    os.makedirs('downloads', exist_ok=True)
    print(f"🔴 Start Recording: {title}")
    await safe_send(f"🔴 LIVE STARTED! 🎬✨\n\n🎥 {title}\n\n⏺️ Recording... 🚀\n⚡ 5MB Parts | 🎥 480p | 📄 .ts Direct! 🍿")
    while True:
        m3u8_url = get_m3u8_link(url)
        if not m3u8_url:
            fail_count += 1
            if fail_count >= 10:
                print(f"🏁 Live Ended: {title}")
                break
            await asyncio.sleep(3)
            continue
        fail_count = 0
        try:
            r = requests.get(m3u8_url, timeout=10)
            playlist = r.text
        except:
            await asyncio.sleep(3)
            continue
        base = m3u8_url.rsplit('/', 1)[0]
        segments = []
        for line in playlist.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                segments.append(line if line.startswith('http') else base + '/' + line)
        for seg_url in segments:
            if seg_url in seen_segments:
                continue
            seen_segments.add(seg_url)
            if part_num == 0 or not part_file or not os.path.exists(part_file) or os.path.getsize(part_file) >= PART_SIZE:
                if part_num > 0 and part_file and os.path.exists(part_file):
                    all_parts.append(part_file)
                    task = asyncio.create_task(upload_part_now(part_file, title, part_num, is_last=False))
                    upload_tasks.append(task)
                    print(f"🚀 Part {part_num} Background Upload! Record Continuing... ⚡")
                part_num += 1
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
                part_file = f"downloads/{safe_title}_part{part_num}.ts"
                print(f"🎥 Recording Part {part_num} - {title}")
            try:
                seg = requests.get(seg_url, timeout=15, stream=True)
                with open(part_file, 'ab') as f:
                    for chunk in seg.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            except:
                continue
            await asyncio.sleep(0.02)
        await asyncio.sleep(2)
        if len(seen_segments) > 2000:
            seen_segments.clear()
    if part_num > 0 and part_file and os.path.exists(part_file) and os.path.getsize(part_file) > 100000:
        all_parts.append(part_file)
        task = asyncio.create_task(upload_part_now(part_file, title, part_num, is_last=True))
        upload_tasks.append(task)
    print(f"⏳ Waiting for {len(upload_tasks)} Uploads: {title} ...")
    if upload_tasks:
        await asyncio.gather(*upload_tasks, return_exceptions=True)
    print(f"✅ All Uploads Done: {title}")
    await merge_local_full_video(all_parts, title)
    print(f"✅ Record + Merge Finished: {title}")

async def monitor_loop():
    await asyncio.sleep(5)
    while True:
        try:
            if len(recording_tasks) < MAX_CONCURRENT:
                watchlist = load_watchlist()
                for item in watchlist[:CHECK_BATCH]:
                    if len(recording_tasks) >= MAX_CONCURRENT:
                        break
                    url = item['url']
                    if url in recording_tasks:
                        continue
                    m3u8 = get_m3u8_link(url)
                    if m3u8:
                        real_title, _ = get_title(url)
                        title = real_title if real_title and real_title != "Live" else item.get('title', 'Live')
                        task = asyncio.create_task(record_live_light(url, title))
                        recording_tasks[url] = task
                        task.add_done_callback(lambda t, u=url: recording_tasks.pop(u, None))
                        print(f"🔴 Started: {title} | Total Recording: {len(recording_tasks)}/30")
        except Exception as e:
            print(f"⚠️ Monitor Error: {e}")
        await asyncio.sleep(5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! 🤖✨\n\n🎬 30 Links Auto Record Bot! 🍿\n\n"
        "⚡ 30 Parallel! | 5MB Parts | 🎥 480p\n"
        "⚡ Record + Upload Parallel!\n"
        "🎬 Local Merge - Full Video!\n\n"
        "📋 Commands:\n📃 /list - List Links 👀\n📺 /live - Check Live 🔴"
    )

async def list_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    watchlist = load_watchlist()
    text = "📋 Watchlist: 👀✨\n\n"
    for i, item in enumerate(watchlist, 1):
        st = "🔴 RECORDING ⏺️" if item['url'] in recording_tasks else "⚪ Waiting... 💤"
        text += f"{i}. 🎬 {item.get('title', 'Live')}\n{st}\n\n"
    await update.message.reply_text(text or "📭 Empty!")

async def live_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    watchlist = load_watchlist()
    await update.message.reply_text("🔍 Checking 30 Live... ⏳✨")
    text = "📺 Live Status: 👀\n\n"
    for item in watchlist:
        m = get_m3u8_link(item['url'])
        text += f"{'🔴 LIVE' if m else '⚪ OFFLINE'} - 🎬 {item.get('title', 'Live')}\n"
    await update.message.reply_text(text)

async def post_init(app):
    asyncio.create_task(monitor_loop())

def main():
    global bot_app
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    threading.Thread(target=run_web, daemon=True).start()
    request = HTTPXRequest(connection_pool_size=100, connect_timeout=30.0, read_timeout=60.0, write_timeout=60.0, pool_timeout=30.0)
    app = ApplicationBuilder().token(TOKEN).request(request).post_init(post_init).build()
    bot_app = app
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_sites))
    app.add_handler(CommandHandler("live", live_now))
    print(f"🤖 Bot Started! ✨ 30 Parallel | 5MB | Local Merge | Port {PORT} 🚀")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
