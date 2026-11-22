# ============================================================
# 🌸✨ LiveStream Recorder - 30 Links ✨🌸
# 💖 480p | 📦 15MB Parts | 🚀 Direct Upload - NO QUEUE!
# 🔥 FIXED: Python 3.14 + Telegram Timeout + .ts -> Real .mp4
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

# ============================================================
# ⚙️ CONFIG
# ============================================================
TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
MIXDROP_API_KEY = os.getenv('MIXDROP_API_KEY')
MIXDROP_EMAIL = os.getenv('MIXDROP_EMAIL')
PORT = int(os.getenv('PORT', 10000))

# ============================================================
# 🔗 YOUR 30 LINKS HERE - EDIT THIS 💖
# ============================================================
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
# ============================================================

MAX_CONCURRENT = 30
PART_SIZE = 15 * 1024 * 1024  # 📦 15MB
CHECK_BATCH = 5               # 👀 Check 5 By 5

recording_tasks = {}
bot_app = None
upload_stats = {"done": 0}

app_web = Flask(__name__)

# ============================================================
# 🛡️ SAFE SEND - Timeout Unaath Bot Crash Wenne Na! 💖
# ============================================================
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
    print("❌ Send Failed After 3 Retries, But Bot Still Alive!")

# ============================================================
# 🔥 FFmpeg: .ts -> Real .mp4 Convert!
# ============================================================
def convert_to_mp4(ts_path):
    mp4_path = ts_path.replace(".ts", ".mp4")
    try:
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', ts_path, '-c', 'copy', '-movflags', '+faststart', mp4_path],
            capture_output=True, text=True, timeout=120
        )
        if os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 100000:
            os.remove(ts_path)
            print(f"✅ Converted to Real MP4: {mp4_path} | Size: {os.path.getsize(mp4_path)//1024}KB")
            return mp4_path
        else:
            print(f"⚠️ FFmpeg Failed: {result.stderr[:500] if result.stderr else 'No Output'}")
            return ts_path
    except Exception as e:
        print(f"⚠️ FFmpeg Error: {e}")
        return ts_path

# ============================================================
# 🌐 WEB DASHBOARD
# ============================================================
@app_web.route('/')
def home():
    return f"🤖 Bot Alive! ✨<br>🎥 Recording: {len(recording_tasks)}/30<br>✅ Uploaded: {upload_stats['done']}"

@app_web.route('/health')
def health():
    return "OK ✅", 200

@app_web.route('/api/list')
def api_list():
    watchlist = load_watchlist()
    out = [{'url': i['url'], 'title': i.get('title', 'Live'), 'recording': i['url'] in recording_tasks} for i in watchlist]
    return jsonify(out)

@app_web.route('/api/status')
def api_status():
    return jsonify({"done": upload_stats["done"], "recording": len(recording_tasks)})

def run_web():
    app_web.run(host="0.0.0.0", port=PORT, threaded=True)

# ============================================================
# 📋 WATCHLIST
# ============================================================
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

# ============================================================
# 🎬 GET 480p STREAM URL
# ============================================================
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
        with yt_dlp.YoutubeDL({
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'format': 'best[height<=480]/best',
        }) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title', 'Live'), None
    except:
        return "Live", None

# ============================================================
# ☁️ MIXDROP UPLOAD
# ============================================================
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

# ============================================================
# 🚀 DIRECT UPLOAD - No Queue! Part Piruna Gaman Upload! 💖
# ============================================================
async def upload_part_now(file_path, title, part_num, is_last=False):
    print(f"📤 Direct Uploading: {title} Part {part_num}")
    try:
        link = await asyncio.to_thread(upload_to_mixdrop, file_path)
        print(f"☁️ Mixdrop Link: {link}")

        sent = False
        try:
            with open(file_path, 'rb') as vid:
                await bot_app.bot.send_video(
                    chat_id=CHANNEL_ID,
                    video=vid,
                    caption=f"🎬 {title}\n\n📦 Part {part_num} ✨\n💾 15MB | 🎥 480p | 🔴 LIVE RECORD\n\n☁️ Mixdrop: {link}\n\n❤️ Enjoy! 🍿"
                )
            sent = True
            print(f"✅ Video Sent: {title} Part {part_num}")
        except Exception as e:
            print(f"⚠️ Send Video Failed, Trying Document: {e}")
            try:
                with open(file_path, 'rb') as doc:
                    await bot_app.bot.send_document(chat_id=CHANNEL_ID, document=doc, caption=f"🎬 {title} - 📦 Part {part_num} ✨\n\n☁️ Mixdrop: {link}")
                sent = True
                print(f"✅ Document Sent: {title} Part {part_num}")
            except Exception as e2:
                print(f"❌ Send Document Also Failed: {e2}")
                await safe_send(f"🎬 {title} - 📦 Part {part_num} ✨\n\n☁️ Mixdrop Link: {link}\n\n⚠️ Telegram Video Failed, Use Mixdrop Link! 💖")

        upload_stats["done"] += 1
        print(f"✅ Done: {title} Part {part_num} | Link: {link} | Sent: {sent}")

        if is_last:
            await safe_send(f"🏁 LIVE ENDED! 🎬✨\n\n🎥 {title}\n\n✅ All Parts Uploaded! 💖\n❤️ Thanks for Watching! 🍿")
    except Exception as e:
        print(f"❌ Upload Part Error: {e}")
    finally:
        try:
            os.remove(file_path)
        except:
            pass

# ============================================================
# 🔴 RECORD - 15MB -> Convert -> Direct Upload -> Continue! 🚀
# ============================================================
async def record_live_light(url, title):
    part_num = 0
    fail_count = 0
    part_file = None
    seen_segments = set()
    os.makedirs('downloads', exist_ok=True)
    print(f"🔴 Start Recording: {title}")

    await safe_send(f"🔴 LIVE STARTED! 🎬✨\n\n🎥 {title}\n\n⏺️ Recording... 🚀\n📦 15MB Parts | 🎥 480p | 🚀 Direct Upload! 🍿")

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

            # 📦 15MB Reached? -> Convert & Direct Upload!
            if part_num == 0 or not part_file or not os.path.exists(part_file) or os.path.getsize(part_file) >= PART_SIZE:
                if part_num > 0 and part_file and os.path.exists(part_file):
                    part_file = await asyncio.to_thread(convert_to_mp4, part_file)
                    await upload_part_now(part_file, title, part_num, is_last=False)
                    print(f"✅ Part {part_num} Uploaded! Continuing... 🚀")

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

    # 📦 Last Part -> Convert & Direct Upload!
    if part_num > 0 and part_file and os.path.exists(part_file) and os.path.getsize(part_file) > 100000:
        part_file = await asyncio.to_thread(convert_to_mp4, part_file)
        await upload_part_now(part_file, title, part_num, is_last=True)
        print(f"📦 Uploaded Last Part: {title} Part {part_num}")
    print(f"✅ Record Finished: {title}")

# ============================================================
# 👀 MONITOR - 30 Links = 5 By 5 Check! No CPU Spike! 💖
# ============================================================
async def monitor_loop():
    await asyncio.sleep(5)
    check_index = 0
    while True:
        try:
            if len(recording_tasks) < MAX_CONCURRENT:
                watchlist = load_watchlist()
                batch = []
                for _ in range(CHECK_BATCH):
                    if watchlist:
                        batch.append(watchlist[check_index % len(watchlist)])
                        check_index += 1
                for item in batch:
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
        except Exception as e:
            print(f"⚠️ Monitor Error: {e}")
        await asyncio.sleep(5)

# ============================================================
# 🤖 TELEGRAM COMMANDS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! 🤖✨\n\n"
        "🎬 30 Links Auto Record Bot! 🍿\n\n"
        "📦 15MB Parts | 🎥 480p\n"
        "🚀 Direct Upload - No Queue!\n\n"
        "📋 Commands:\n"
        "📃 /list - List Links 👀\n"
        "📺 /live - Check Live 🔴"
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
    await update.message.reply_text("🔍 Checking Live... ⏳✨")
    text = "📺 Live Status: 👀\n\n"
    for item in watchlist:
        m = get_m3u8_link(item['url'])
        text += f"{'🔴 LIVE' if m else '⚪ OFFLINE'} - 🎬 {item.get('title', 'Live')}\n"
    await update.message.reply_text(text)

# ============================================================
# 🚀 MAIN - FIXED! 🔥
# ============================================================
async def post_init(app):
    asyncio.create_task(monitor_loop())

def main():
    global bot_app
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    threading.Thread(target=run_web, daemon=True).start()

    request = HTTPXRequest(
        connection_pool_size=50,
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=30.0,
    )

    app = ApplicationBuilder().token(TOKEN).request(request).post_init(post_init).build()
    bot_app = app
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_sites))
    app.add_handler(CommandHandler("live", live_now))
    print(f"🤖 Bot Started! ✨ Direct Upload Mode | 480p | 30 Links | Port {PORT} 🚀")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
