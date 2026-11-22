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
PORT = 10000
JSONBIN_API_KEY = os.getenv('JSONBIN_API_KEY')
JSONBIN_BIN_ID = os.getenv('JSONBIN_BIN_ID')

WEBSITE_URL = "https://livestreamrecorder-6nkc.onrender.com"

# ==============================
# 👇 YOUR LINKS HERE - EDIT THIS
# ==============================
LINKS = [  "https://www.cam4.com/gelai20",
    "https://bongacams.com/bellacutie69",
    "https://www.cam4.com/sexy_gale",
"https://bongacams.com/sweetpink061",
"https://bongacams.com/pinaysweetmommyxx",
]
# ==============================

WATCH_FILE = "watchlist.json"
recording_tasks = {}
bot_app = None

app_web = Flask(__name__)

# ==============================
# DASHBOARD - INDEX HTML
# ==============================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LiveStream Recorder</title>
<style>
* { box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
body { background: linear-gradient(180deg, #ffe3f3, #e0f7ff, #fff6d6); margin: 0; padding: 12px; min-height: 100vh; }
.header { text-align: center; background: white; border-radius: 25px; padding: 20px 10px; box-shadow: 0 5px 20px rgba(255,150,200,0.3); margin-bottom: 12px; }
.header h1 { margin: 0; font-size: 26px; }
.header p { margin: 5px 0 0 0; color: #ff6b9d; font-weight: bold; font-size: 13px; }
.badge { display: inline-block; background: #ff6b9d; color: white; padding: 5px 12px; border-radius: 20px; font-size: 12px; margin-top: 8px; }
.card { background: white; border-radius: 20px; padding: 15px; margin: 10px 0; box-shadow: 0 4px 15px rgba(0,0,0,0.07); }
.card h3 { margin: 0 0 8px 0; font-size: 16px; }
input { width: 100%; padding: 13px; border-radius: 15px; border: 2px solid #ffd6e7; background: #fff5f9; outline: none; font-size: 14px; }
input:focus { border-color: #ff6b9d; }
button { width: 100%; padding: 13px; border-radius: 15px; border: none; font-weight: bold; font-size: 15px; cursor: pointer; margin-top: 8px; }
.add-btn { background: linear-gradient(90deg, #ff6b9d, #ff9a8b); color: white; box-shadow: 0 4px 12px rgba(255,107,157,0.4); }
.refresh-btn { background: #aee7ff; color: #00695c; width: auto; padding: 8px 14px; font-size: 13px; }
.live { color: #ff1744; font-weight: bold; background: #ffe0e0; padding: 3px 10px; border-radius: 20px; font-size: 12px; }
.wait { color: #ff9800; font-weight: bold; background: #fff3e0; padding: 3px 10px; border-radius: 20px; font-size: 12px; }
.link { word-break: break-all; color: #7c9eff; font-size: 12px; }
.video-item { background: #fff5f9; border: 2px dashed #ffb3d1; border-radius: 18px; padding: 12px; margin: 8px 0; }
.video-item b { font-size: 14px; }
.watch-btn { background: linear-gradient(90deg, #a18cd1, #fbc2eb); color: white; text-decoration: none; display: block; text-align: center; padding: 10px; border-radius: 12px; font-weight: bold; margin-top: 8px; }
.time { color: #aaa; font-size: 11px; }
.tabs { display: flex; gap: 8px; }
.tab { flex: 1; background: white; text-align: center; padding: 10px; border-radius: 15px; font-weight: bold; font-size: 13px; box-shadow: 0 3px 10px rgba(0,0,0,0.08); }
.web-link { background: linear-gradient(90deg, #ff6b9d, #a18cd1); color: white; text-decoration: none; display: inline-block; padding: 8px 18px; border-radius: 20px; font-weight: bold; font-size: 13px; margin-top: 10px; }
</style>
</head>
<body>
<div class="header">
<h1>🌸🎬 LiveStream Recorder 🌸✨</h1>
<p>💖 Cute Auto Recorder 💖</p>
<span class="badge">🔴 LIVE = Auto Record</span>
<span class="badge" style="background:#7c9eff">📦 45MB Parts</span>
<span class="badge" style="background:#4caf50">☁️ Permanent Save</span>
<br>
<a class="web-link" href="__WEBSITE_URL__" target="_blank">🌐 Visit Website 💖</a>
<p style="font-size:11px; color:#888; margin-top:8px;">🔗 __WEBSITE_URL__</p>
</div>
<div class="tabs">
<div class="tab">🎀 Watchlist</div>
<div class="tab">🍿 Videos</div>
</div>
<div class="card">
<h3>➕ Add New Link 📌</h3>
<input id="newUrl" placeholder="Paste link here...">
<button class="add-btn" onclick="addLink()">🌸 Add Link 💖</button>
</div>
<div class="card">
<h3>👀 Watchlist 🎀 <button class="refresh-btn" onclick="loadAll()">🔄 Refresh</button></h3>
<div id="list">Loading...</div>
</div>
<div class="card">
<h3>🍿 Recorded Videos 💕</h3>
<div id="videos">Loading...</div>
</div>
<div class="card" style="text-align:center;">
<p style="font-size:13px; color:#ff6b9d; font-weight:bold;">🌸 LiveStream Recorder 🌸</p>
<a href="__WEBSITE_URL__" target="_blank" style="color:#7c9eff; font-size:12px; word-break:break-all;">__WEBSITE_URL__</a>
<p style="font-size:11px; color:#aaa;">💖 Made with Love | Auto Record Bot 💖</p>
</div>
<script>
async function loadAll(){
  let r = await fetch('/api/list');
  let data = await r.json();
  let html = '';
  if(data.length==0) html = 'No Links Yet! Add One!';
  data.forEach((item)=>{
    let st = item.recording ? '<span class=live>🔴 RECORDING</span>' : '<span class=wait>💤 Waiting...</span>';
    html += '<div class="video-item"><b>' + item.title + '</b><br>' + st + '<br><span class="link">' + item.url + '</span></div>';
  });
  document.getElementById('list').innerHTML = html;
  let r2 = await fetch('/api/videos');
  let vids = await r2.json();
  let vhtml = '';
  if(vids.length==0) vhtml = 'No videos yet! Wait for live to start...';
  vids.forEach(v=>{
    vhtml += '<div class="video-item"><b>' + v.title + '</b> <span class="time">' + v.time + '</span><br>Part ' + v.part + '<br><a class="watch-btn" href="' + v.link + '" target="_blank">Watch Now</a></div>';
  });
  document.getElementById('videos').innerHTML = vhtml;
}
async function addLink(){
  let url = document.getElementById('newUrl').value.trim();
  if(!url) return alert('Please paste a link!');
  await fetch('/api/add', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url})});
  document.getElementById('newUrl').value='';
  loadAll();
}
loadAll();
setInterval(loadAll, 10000);
</script>
</body>
</html>
"""

@app_web.route('/')
def home():
    return DASHBOARD_HTML.replace("__WEBSITE_URL__", WEBSITE_URL)

@app_web.route('/health')
def health():
    return "OK ✅", 200

@app_web.route('/ping')
def ping():
    return "Pong! 🏓 Bot Alive! ✨", 200

@app_web.route('/api/list')
def api_list():
    watchlist = load_watchlist()
    out = []
    for item in watchlist:
        out.append({
            'url': item['url'],
            'title': item.get('title', 'Live'),
            'recording': item['url'] in recording_tasks
        })
    return out

@app_web.route('/api/videos')
def api_videos():
    return {"videos": []}

@app_web.route('/api/add', methods=['POST'])
def api_add():
    from flask import request
    url = request.json.get('url', '').strip()
    if not url:
        return {'ok': False}
    watchlist = load_watchlist()
    for item in watchlist:
        if item['url'] == url:
            return {'ok': False, 'msg': 'Already Added'}
    title, _ = get_title(url)
    watchlist.append({'url': url, 'title': title})
    save_watchlist(watchlist)
    return {'ok': True}

def run_web():
    app_web.run(host="0.0.0.0", port=PORT)

# ==============================
# JSONBIN - PERMANENT STORAGE
# ==============================
_cache = {"watchlist": [], "loaded": False}

def _bin_headers():
    return {"Content-Type": "application/json", "X-Master-Key": JSONBIN_API_KEY}

def load_from_bin():
    if _cache["loaded"]:
        return _cache
    if not JSONBIN_API_KEY or not JSONBIN_BIN_ID:
        print("JSONBin Not Configured - Using Local File")
        _cache["loaded"] = True
        return _cache
    try:
        r = requests.get(f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest", headers=_bin_headers(), timeout=10)
        data = r.json().get("record", {})
        _cache["watchlist"] = data.get("watchlist", [])
        _cache["loaded"] = True
        print(f"Loaded from JSONBin: {len(_cache['watchlist'])} Links")
    except Exception as e:
        print(f"JSONBin Load Failed: {e}")
        _cache["loaded"] = True
    return _cache

def save_to_bin():
    if not JSONBIN_API_KEY or not JSONBIN_BIN_ID:
        return
    try:
        payload = {"watchlist": _cache["watchlist"]}
        requests.put(f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}", headers=_bin_headers(), json=payload, timeout=10)
        print("Saved to JSONBin")
    except Exception as e:
        print(f"JSONBin Save Failed: {e}")

def load_watchlist():
    data = load_from_bin()["watchlist"]
    if not data and os.path.exists(WATCH_FILE):
        try:
            with open(WATCH_FILE, 'r') as f:
                data = json.load(f)
                _cache["watchlist"] = data
        except:
            data = []
    seen = set(x['url'] for x in data)
    for url in LINKS:
        if url and url not in seen and "example.com" not in url:
            data.append({'url': url, 'title': 'Live'})
            seen.add(url)
    return data

def save_watchlist(data):
    _cache["watchlist"] = data
    with open(WATCH_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    save_to_bin()

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
                caption=f"🎬 {title}\n\n📦 Part {part_num} ✨\n💾 45MB | 🔴 LIVE RECORD\n\n❤️ Enjoy! 🍿\n\n🌐 Website: {WEBSITE_URL}"
            )
    except Exception as e:
        print(f"Telegram Upload Failed: {e}")
        try:
            with open(part_file, 'rb') as doc:
                await bot.send_document(chat_id=CHANNEL_ID, document=doc, caption=f"🎬 {title} - 📦 Part {part_num} ✨\n\n🌐 Website: {WEBSITE_URL}")
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
            await bot_app.bot.send_message(chat_id=CHANNEL_ID, text=f"🔴 LIVE STARTED! 🎬✨\n\n🎥 {title}\n\n⏺️ Auto Recording Started... 🚀\n📦 45MB Parts Coming Soon! 🍿\n⚡ Auto Reconnect: 3 Sec 🔄\n\n🌐 Website: {WEBSITE_URL}")
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
            '-fs', '45M',
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
        text += f"\n✨ Recording Complete! 🎉\n❤️ Thanks for Watching! 🍿\n\n🌐 Website: {WEBSITE_URL}"
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
        "🚀 Ready! Send /add to Start! ✨\n\n"
        f"🌐 Website: {WEBSITE_URL}"
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
    await msg.reply_text(f"✅ Added Successfully! 🎉\n\n🎬 {title}\n🔗 {url}\n\n🔴 Live Started = Auto Record! ⏺️✨\n\n🌐 Website: {WEBSITE_URL}")

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
    print(f"🤖 Bot Started on Port {PORT}... ✨")
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_loop())
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
