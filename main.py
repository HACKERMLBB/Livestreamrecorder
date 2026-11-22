import os
import asyncio
import threading
import json
import requests
import subprocess
import logging
import re
import datetime
from flask import Flask, request
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
JSONBIN_API_KEY = os.getenv('JSONBIN_API_KEY')
JSONBIN_BIN_ID = os.getenv('JSONBIN_BIN_ID')

# WEBSITE LINK - හැමතැනම මේක වැටෙනවා!
WEBSITE_URL = "https://livestreamrecorder-n6e0.onrender.com"
WEBSITE_NAME = "🌸 LiveStream Recorder 🌸"

LINKS = [
    "https://www.cam4.com/gelai20",
    "https://bongacams.com/bellacutie69",
    "https://www.cam4.com/sexy_gale",
"https://bongacams.com/sweetpink061",
"https://bongacams.com/pinaysweetmommyxx",
]

recording_tasks = {}
bot_app = None
app_web = Flask(__name__)

# ==============================
# JSONBIN - PERMANENT STORAGE
# ==============================
_cache = {"watchlist": [], "videos": [], "loaded": False}

def _bin_headers():
    return {"Content-Type": "application/json", "X-Master-Key": JSONBIN_API_KEY}

def load_from_bin():
    if _cache["loaded"]:
        return _cache
    if not JSONBIN_API_KEY or not JSONBIN_BIN_ID:
        print("JSONBin Not Configured - Using Local Memory")
        _cache["loaded"] = True
        return _cache
    try:
        r = requests.get(f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest", headers=_bin_headers(), timeout=10)
        data = r.json().get("record", {})
        _cache["watchlist"] = data.get("watchlist", [])
        _cache["videos"] = data.get("videos", [])
        _cache["loaded"] = True
        print(f"Loaded from JSONBin: {len(_cache['watchlist'])} Links, {len(_cache['videos'])} Videos")
    except Exception as e:
        print(f"JSONBin Load Failed: {e}")
        _cache["loaded"] = True
    return _cache

def save_to_bin():
    if not JSONBIN_API_KEY or not JSONBIN_BIN_ID:
        return
    try:
        payload = {"watchlist": _cache["watchlist"], "videos": _cache["videos"]}
        requests.put(f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}", headers=_bin_headers(), json=payload, timeout=10)
        print("Saved to JSONBin ✅")
    except Exception as e:
        print(f"JSONBin Save Failed: {e}")

def load_watchlist():
    data = load_from_bin()["watchlist"]
    seen = set(x['url'] for x in data)
    for url in LINKS:
        if url and url not in seen and "example.com" not in url:
            data.append({'url': url, 'title': 'Live'})
            seen.add(url)
    return data

def save_watchlist(data):
    _cache["watchlist"] = data
    save_to_bin()

def load_videos():
    return load_from_bin()["videos"]

def save_video(title, part_num, mix_link):
    videos = load_from_bin()["videos"]
    videos.insert(0, {
        'title': title,
        'part': part_num,
        'link': mix_link,
        'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    _cache["videos"] = videos[:100]
    save_to_bin()

# ==============================
# WEBSITE - Cute Dashboard
# ==============================
DASHBOARD_HTML = f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LiveStream Recorder</title>
<style>
* {{ box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }}
body {{ background: linear-gradient(180deg, #ffe3f3, #e0f7ff, #fff6d6); margin: 0; padding: 12px; min-height: 100vh; }}
.header {{ text-align: center; background: white; border-radius: 25px; padding: 20px 10px; box-shadow: 0 5px 20px rgba(255,150,200,0.3); margin-bottom: 12px; }}
.header h1 {{ margin: 0; font-size: 26px; }}
.header p {{ margin: 5px 0 0 0; color: #ff6b9d; font-weight: bold; font-size: 13px; }}
.badge {{ display: inline-block; background: #ff6b9d; color: white; padding: 5px 12px; border-radius: 20px; font-size: 12px; margin-top: 8px; }}
.card {{ background: white; border-radius: 20px; padding: 15px; margin: 10px 0; box-shadow: 0 4px 15px rgba(0,0,0,0.07); }}
.card h3 {{ margin: 0 0 8px 0; font-size: 16px; }}
input {{ width: 100%; padding: 13px; border-radius: 15px; border: 2px solid #ffd6e7; background: #fff5f9; outline: none; font-size: 14px; }}
input:focus {{ border-color: #ff6b9d; }}
button {{ width: 100%; padding: 13px; border-radius: 15px; border: none; font-weight: bold; font-size: 15px; cursor: pointer; margin-top: 8px; }}
.add-btn {{ background: linear-gradient(90deg, #ff6b9d, #ff9a8b); color: white; box-shadow: 0 4px 12px rgba(255,107,157,0.4); }}
.refresh-btn {{ background: #aee7ff; color: #00695c; width: auto; padding: 8px 14px; font-size: 13px; }}
.live {{ color: #ff1744; font-weight: bold; background: #ffe0e0; padding: 3px 10px; border-radius: 20px; font-size: 12px; }}
.wait {{ color: #ff9800; font-weight: bold; background: #fff3e0; padding: 3px 10px; border-radius: 20px; font-size: 12px; }}
.link {{ word-break: break-all; color: #7c9eff; font-size: 12px; }}
.video-item {{ background: #fff5f9; border: 2px dashed #ffb3d1; border-radius: 18px; padding: 12px; margin: 8px 0; }}
.video-item b {{ font-size: 14px; }}
.watch-btn {{ background: linear-gradient(90deg, #a18cd1, #fbc2eb); color: white; text-decoration: none; display: block; text-align: center; padding: 10px; border-radius: 12px; font-weight: bold; margin-top: 8px; }}
.time {{ color: #aaa; font-size: 11px; }}
.tabs {{ display: flex; gap: 8px; }}
.tab {{ flex: 1; background: white; text-align: center; padding: 10px; border-radius: 15px; font-weight: bold; font-size: 13px; box-shadow: 0 3px 10px rgba(0,0,0,0.08); }}
.web-link {{ background: linear-gradient(90deg, #ff6b9d, #a18cd1); color: white; text-decoration: none; display: inline-block; padding: 8px 18px; border-radius: 20px; font-weight: bold; font-size: 13px; margin-top: 10px; }}
</style>
</head>
<body>
<div class="header">
<h1>🌸🎬 LiveStream Recorder 🌸✨</h1>
<p>💖 Cute Auto Recorder 💖</p>
<span class="badge">🔴 LIVE = Auto Record ⏺️</span>
<span class="badge" style="background:#7c9eff">📦 45MB Parts</span>
<span class="badge" style="background:#4caf50">☁️ Permanent Save ✅</span>
<br>
<a class="web-link" href="{WEBSITE_URL}" target="_blank">🌐 Visit Website 💖</a>
<p style="font-size:11px; color:#888; margin-top:8px;">🔗 {WEBSITE_URL}</p>
</div>
<div class="tabs">
<div class="tab">🎀 Watchlist</div>
<div class="tab">🍿 Videos</div>
</div>
<div class="card">
<h3>➕ ✨ Add New Link ✨📌</h3>
<input id="newUrl" placeholder="Paste link here... 🔗💕">
<button class="add-btn" onclick="addLink()">🌸 Add Link 💖✨</button>
</div>
<div class="card">
<h3>👀 Watchlist 🎀 <button class="refresh-btn" onclick="loadAll()">🔄 Refresh</button></h3>
<div id="list">Loading... 🍭⏳</div>
</div>
<div class="card">
<h3>🍿🎬 Recorded Videos 💕</h3>
<div id="videos">Loading... 🍓⏳</div>
</div>
<div class="card" style="text-align:center;">
<p style="font-size:13px; color:#ff6b9d; font-weight:bold;">🌸 LiveStream Recorder 🌸</p>
<a href="{WEBSITE_URL}" target="_blank" style="color:#7c9eff; font-size:12px; word-break:break-all;">{WEBSITE_URL}</a>
<p style="font-size:11px; color:#aaa;">💖 Made with Love | Auto Record Bot 💖</p>
</div>
<script>
async function loadAll(){{
  let r = await fetch('/api/list');
  let data = await r.json();
  let html = '';
  if(data.length==0) html = '📭 No Links Yet! Add One! 🥺💕';
  data.forEach((item,i)=>{{
    let st = item.recording ? '<span class=live>🔴 RECORDING ⏺️</span>' : '<span class=wait>💤 Waiting... 🌙</span>';
    html += `<div class="video-item"><b>🎬 ${{item.title}}</b><br>${{st}}<br><span class="link">🔗 ${{item.url}}</span></div>`;
  }});
  document.getElementById('list').innerHTML = html;
  let r2 = await fetch('/api/videos');
  let vids = await r2.json();
  let vhtml = '';
  if(vids.length==0) vhtml = '🥺 No videos yet! Wait for live to start... 🎀';
  vids.forEach(v=>{{
    vhtml += `<div class="video-item"><b>🎬 ${{v.title}}</b> <span class="time">🕒 ${{v.time}}</span><br>📦 Part ${{v.part}} ✨<br><a class="watch-btn" href="${{v.link}}" target="_blank">▶️ Watch Now 🍿💖</a></div>`;
  }});
  document.getElementById('videos').innerHTML = vhtml;
}}
async function addLink(){{
  let url = document.getElementById('newUrl').value.trim();
  if(!url) return alert('Please paste a link! 🥺🔗');
  await fetch('/api/add', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{url}})}});
  document.getElementById('newUrl').value='';
  loadAll();
}}
loadAll();
setInterval(loadAll, 10000);
</script>
</body>
</html>
"""

@app_web.route('/')
def home():
    return DASHBOARD_HTML

@app_web.route('/health')
def health():
    return "OK", 200

@app_web.route('/ping')
def ping():
    return "Pong! Bot Alive!", 200

@app_web.route('/api/list')
def api_list():
    watchlist = load_watchlist()
    out = []
    for item in watchlist:
        out.append({
            'url': item['url'],
            'title': item.get('title','Live'),
            'recording': item['url'] in recording_tasks
        })
    return out

@app_web.route('/api/videos')
def api_videos():
    return load_videos()

@app_web.route('/api/add', methods=['POST'])
def api_add():
    url = request.json.get('url','').strip()
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

# =========================================================
# yt-dlp -F + -g - Quality + m3u8
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
    for line in f_output.split('\\n'):
        line = line.strip()
        if not line or line.startswith('[') or line.startswith('ID') or line.startswith('---'):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        fid = parts[0]
        if not re.match(r'^[a-zA-Z0-9_\\-\\.]+$', fid):
            continue
        low = line.lower()
        if 'audio only' in low:
            audios.append(fid)
            continue
        m = re.search(r'(\\d+)x(\\d+)', line)
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
            print(f"Format Found via -F: Combined {best[0]} ({best[1]}p)")
            return best[0]
        videos_720 = [x for x in videos if x[1] <= 720]
        if videos_720:
            videos_720.sort(key=lambda x: x[1], reverse=True)
            v_id = videos_720[0][0]
            v_h = videos_720[0][1]
            if audios:
                a_id = audios[-1]
                print(f"Format Found via -F: Video {v_id} ({v_h}p) + Audio {a_id}")
                return f"{v_id}+{a_id}"
            else:
                print(f"Format Found via -F: Video Only {v_id} ({v_h}p)")
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
    print(f"-F Parse Failed, Using Fallback Format")
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
        lines = [l.strip() for l in out.split('\\n') if l.strip().startswith('http')]
        if not lines:
            return (None, None)
        if len(lines) >= 2:
            print(f"Got m3u8 via -g: Video + Audio (2 Links)")
            return (lines[0], lines[1])
        else:
            print(f"Got m3u8 via -g: Single Link")
            return (lines[0], None)
    except Exception as e:
        print(f"-g Failed: {e}")
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
                caption=f"🎬 {title}\\n\\n📦 Part {part_num} ✨\\n💾 45MB | 🔴 LIVE RECORD\\n\\n🌸 {WEBSITE_NAME}\\n🌐 Website: {WEBSITE_URL}\\n\\n❤️ Enjoy! 🍿"
            )
            if thumb:
                thumb.close()
    except Exception as e:
        print(f"Telegram Upload Failed: {e}")
        try:
            with open(part_file, 'rb') as doc:
                await bot.send_document(chat_id=CHANNEL_ID, document=doc, caption=f"🎬 {title} - 📦 Part {part_num} ✨\\n\\n🌸 {WEBSITE_NAME}\\n🌐 {WEBSITE_URL}")
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
    print(f"Recording Started: {title}")
    if bot_app:
        try:
            await bot_app.bot.send_message(chat_id=CHANNEL_ID, text=f"🔴 LIVE STARTED! 🎬✨\\n\\n🎥 {title}\\n\\n⏺️ Auto Recording Started... 🚀\\n📦 45MB Parts Coming Soon! 🍿\\n⚡ Auto Reconnect: 3 Sec 🔄\\n\\n🌸 {WEBSITE_NAME}\\n🌐 Website: {WEBSITE_URL}")
        except:
            pass
    while True:
        video_url, audio_url = get_streams(url)
        if not video_url:
            fail_count += 1
            print(f"m3u8 Not Found! Retry {fail_count}/10 in 3 sec - {title}")
            if fail_count >= 10:
                print(f"Live Ended: {title}")
                break
            await asyncio.sleep(3)
            continue
        fail_count = 0
        part_num += 1
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        part_file = f"downloads/{safe_title}_part{part_num}.mp4"
        if audio_url:
            print(f"Recording Part {part_num}... [Video+Audio Merge]")
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
            print(f"Recording Part {part_num}... [Single Stream]")
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
            print(f"Part {part_num} Timeout")
        if not os.path.exists(part_file) or os.path.getsize(part_file) < 100000:
            print(f"Part {part_num} Empty! Retrying in 3 sec...")
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
            save_video(title, part_num, link)
        try:
            os.remove(part_file)
        except:
            pass
        await asyncio.sleep(3)
    if bot_app:
        text = f"🏁 LIVE ENDED! 🎬✨\\n\\n🎥 {title}\\n\\n📦 Total Parts: {part_num} 📁\\n💾 45MB Each\\n\\n"
        if mix_links:
            text += "🔗 MixDrop Links: 📥\\n\\n"
            for i, link in enumerate(mix_links, 1):
                text += f"▶️ Part {i}: {link}\\n"
        text += f"\\n✨ Recording Complete! 🎉\\n❤️ Thanks for Watching! 🍿\\n\\n🌸 {WEBSITE_NAME}\\n🌐 Website: {WEBSITE_URL}"
        try:
            await bot_app.bot.send_message(chat_id=CHANNEL_ID, text=text)
        except:
            pass
    print(f"Recording Finished: {title} - {part_num} Parts")

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
    asyncio.create_task(monitor_loop())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    await msg.reply_text(
        "👋 Welcome! 🤖✨\\n\\n"
        f"🌸 {WEBSITE_NAME} 🌸\\n"
        f"🌐 Website: {WEBSITE_URL}\\n\\n"
        "🎬 Cartoon Live Auto Record Bot! 🍿\\n\\n"
        "📋 Commands:\\n"
        "➕ /add <link> - Add Site 📌\\n"
        "📃 /list - List Sites 👀\\n"
        "📺 /live - Check Live 🔴\\n\\n"
        "🔴 Live Started = Auto Record! ⏺️\\n"
        "📦 45MB Parts = MixDrop + Channel! ☁️📢\\n"
        "⚡ Broken? 3 Sec Auto Reconnect! 🔄\\n"
        "🏁 Live End = Auto Stop! ✅\\n"
        "☁️ Permanent Save - Restart Safe! ✅\\n\\n"
        f"🌐 Watch All Videos Here:\\n{WEBSITE_URL}\\n\\n"
        "🚀 Ready! Send /add to Start! ✨"
    )

async def add_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not context.args:
        await msg.reply_text("❌ Usage: /add <link> 📌\\n\\nEx: /add https://example.com/live 🔗")
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
    await msg.reply_text(f"✅ Added Successfully! 🎉\\n\\n🎬 {title}\\n🔗 {url}\\n\\n🔴 Live Started = Auto Record! ⏺️✨\\n\\n🌸 {WEBSITE_NAME}\\n🌐 {WEBSITE_URL}")

async def list_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    watchlist = load_watchlist()
    if not watchlist:
        await msg.reply_text("📭 No Sites Added Yet! 😅\\n\\n➕ /add <link> to Add! 📌")
        return
    text = "📋 Watchlist: 👀✨\\n\\n"
    for i, item in enumerate(watchlist, 1):
        status = "🔴 RECORDING ⏺️" if item['url'] in recording_tasks else "⚪ Waiting... 💤"
        text += f"{i}. 🎬 {item.get('title','Live')}\\n{status}\\n🔗 {item['url']}\\n\\n"
    text += f"\\n🌸 {WEBSITE_NAME}\\n🌐 {WEBSITE_URL}"
    await msg.reply_text(text)

async def live_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    watchlist = load_watchlist()
    if not watchlist:
        await msg.reply_text("📭 Watchlist Empty! 😅")
        return
    await msg.reply_text("🔍 Checking Live... ⏳✨")
    text = "📺 Live Status: 👀\\n\\n"
    for item in watchlist:
        m3u8 = get_m3u8_link(item['url'])
        if m3u8:
            text += f"🔴 LIVE - 🎬 {item.get('title','Live')}\\n"
        else:
            text += f"⚪ OFFLINE - 🎬 {item.get('title','Live')}\\n"
    text += f"\\n🌐 Website: {WEBSITE_URL}"
    await msg.reply_text(text)

def main():
    global bot_app
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    bot_app = app
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_site))
    app.add_handler(CommandHandler("list", list_sites))
    app.add_handler(CommandHandler("live", live_now))
    app.post_init = on_startup
    print(f"Bot Started on Port {PORT}... ✨")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
