# ============================================================
# 🌸✨ LiveStream Recorder - 30 Links - ALL AT ONCE! ✨🌸
# 💖 480p | 📦 5MB Parts | ⚡ 30 Parallel Record + Upload!
# 🎬 TELEGRAM MERGE - Telegram Part ටිකෙන් Full Video!
# 💾 100% SAFE - file_id Telegram + File දෙකේම Save!
# 🔄 Auto Merge After Restart!
# ☁️ Mixdrop Fix - https://ul.mixdrop.ag/api ✅
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
sent_parts = {}  # { "Title": [(part_num, file_id), ...] }
backup_task = None

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
    return f"🤖 Bot Alive! ✨<br>🎥 Recording: {len(recording_tasks)}/30<br>✅ Uploaded: {upload_stats['done']}<br>📦 Saved Titles: {len(sent_parts)}<br>⚡ Mode: 30 Parallel | 5MB | Telegram Merge | Auto-Restart"

@app_web.route('/health')
def health():
    return "OK ✅", 200

@app_web.route('/api/status')
def api_status():
    return jsonify({"done": upload_stats["done"], "recording": len(recording_tasks), "saved": len(sent_parts)})

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

# ============================================================
# 💾 PERSISTENCE - file_id ටික Save / Load / Telegram Backup!
# ============================================================
def save_sent_parts():
    try:
        with open("sent_parts.json", "w") as f:
            json.dump(sent_parts, f)
        print(f"💾 Saved sent_parts: {len(sent_parts)} titles")
    except Exception as e:
        print(f"❌ Save Failed: {e}")

def load_sent_parts():
    global sent_parts
    if os.path.exists("sent_parts.json"):
        try:
            with open("sent_parts.json") as f:
                data = json.load(f)
                sent_parts = {k: [(int(p), fid) for p, fid in v] for k, v in data.items()}
            print(f"💾 Loaded sent_parts: {len(sent_parts)} titles")
            for t, v in sent_parts.items():
                print(f"  🎬 {t} - {len(v)} Parts")
        except Exception as e:
            print(f"❌ Load Failed: {e}")
            sent_parts = {}

async def backup_to_telegram():
    # 📩 Telegram Channel එකට Backup JSON එක යවනවා! (10s පරක්කුවෙන්, Spam වෙන්නේ නෑ!)
    # එක දිගට Backup යවන්නේ නෑ! Last Backup එකෙන් තත්පර 30කට පස්සේ විතරයි!
    global backup_task
    if backup_task and not backup_task.done():
        return
    async def _do():
        await asyncio.sleep(30)
        try:
            save_sent_parts()
            if not sent_parts:
                return
            with open("sent_parts.json", "rb") as doc:
                await bot_app.bot.send_document(
                    chat_id=CHANNEL_ID,
                    document=doc,
                    filename="sent_parts_backup.json",
                    caption=f"💾 BACKUP DB 📦✨\n\n🎬 Titles: {len(sent_parts)}\n📦 Total Parts: {sum(len(v) for v in sent_parts.values())}\n\n⚠️ මේක Delete කරන්න එපා! Restart වුණොත් Full Video හදන්න ඕනේ File එක! 💖"
                )
            print("💾 Telegram Backup Sent!")
        except Exception as e:
            print(f"❌ Telegram Backup Failed: {e}")
    backup_task = asyncio.create_task(_do())

# ============================================================
# ☁️ MIXDROP UPLOAD - FIXED URL!
# ============================================================
def upload_to_mixdrop(file_path):
    try:
        print(f"☁️ Mixdrop Uploading: {file_path} | Size: {os.path.getsize(file_path)//1024}KB")
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            data = {'email': MIXDROP_EMAIL, 'key': MIXDROP_API_KEY}
            r = requests.post("https://ul.mixdrop.ag/api", files=files, data=data, timeout=600)
            print(f"☁️ Mixdrop Status: {r.status_code}")
            print(f"☁️ Mixdrop Response: {r.text[:500]}")
            res = r.json()
            if res.get('success'):
                link = f"https://mixdrop.ag/f/{res['result']['fileref']}"
                print(f"✅ Mixdrop OK: {link}")
                return link
            print(f"❌ Mixdrop Failed: {res}")
            return None
    except Exception as e:
        print(f"❌ Upload Failed: {e}")
        return None

# ============================================================
# 🚀 UPLOAD PART - Background! Telegram + Mixdrop!
# ============================================================
async def upload_part_now(file_path, title, part_num, is_last=False):
    print(f"📤 [Background] Uploading: {title} Part {part_num} | Size: {os.path.getsize(file_path)//1024}KB")
    try:
        link = await asyncio.to_thread(upload_to_mixdrop, file_path)
        print(f"☁️ Mixdrop Link Part {part_num}: {link}")
        try:
            with open(file_path, 'rb') as doc:
                msg = await bot_app.bot.send_document(
                    chat_id=CHANNEL_ID,
                    document=doc,
                    filename=f"{title}_Part{part_num}.ts",
                    caption=f"🎬 {title}\n\n⚡ Part {part_num} ✨\n💾 5MB | 🎥 480p | 🔴 LIVE RECORD\n\n☁️ Mixdrop: {link}\n\n❤️ Enjoy! 🍿"
                )
                if title not in sent_parts:
                    sent_parts[title] = []
                sent_parts[title].append((part_num, msg.document.file_id))
                sent_parts[title] = sorted(sent_parts[title])
                save_sent_parts()  # ✅ File එකේ Save!
                await backup_to_telegram()  # ✅ Telegram එකෙත් Backup!
                print(f"✅ Saved file_id Part {part_num} | Total: {len(sent_parts[title])}")
        except Exception as e:
            print(f"❌ Send Failed Part {part_num}: {e}")
            await safe_send(f"🎬 {title} - Part {part_num}\n☁️ Link: {link}")
        upload_stats["done"] += 1
        if is_last:
            await safe_send(f"🏁 LIVE ENDED! 🎬✨\n\n🎥 {title}\n\n✅ All Parts Uploaded! 💖\n🎬 Full Video හදනවා... ⏳")
    except Exception as e:
        print(f"❌ Upload Part Error {part_num}: {e}")
    finally:
        try:
            os.remove(file_path)
            print(f"🗑️ Deleted Local: {file_path}")
        except:
            pass

# ============================================================
# 🎬 TELEGRAM MERGE - Telegram Part ටිකෙන් Full Video!
# ============================================================
async def merge_from_telegram(title):
    if title not in sent_parts or len(sent_parts[title]) < 2:
        print(f"⚠️ Merge Skip: Parts අඩුයි! {title} - {len(sent_parts.get(title, []))}")
        return
    file_ids = sorted(sent_parts[title])
    print(f"🎬 Telegram Merge Start: {title} | Parts: {len(file_ids)}")
    await safe_send(f"🎬 Full Video හදනවා... ⏳✨\n\n🎥 {title}\n📦 Parts: {len(file_ids)}\n⏳ Telegram එකෙන් බාගෙන එකතු කරනවා... 💖")
    os.makedirs('merge', exist_ok=True)
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
    full_path = f"merge/{safe_title}_FULL.ts"
    try:
        with open(full_path, 'wb') as out:
            for part_num, fid in file_ids:
                try:
                    print(f"📥 Downloading Part {part_num} from Telegram...")
                    f = await bot_app.bot.get_file(fid)
                    tmp = f"merge/tmp_{part_num}.ts"
                    await f.download_to_drive(tmp)
                    with open(tmp, 'rb') as tf:
                        while True:
                            chunk = tf.read(1024*1024)
                            if not chunk:
                                break
                            out.write(chunk)
                    os.remove(tmp)
                    print(f"✅ Merged Part {part_num}")
                except Exception as e:
                    print(f"❌ Merge Part {part_num} Failed: {e}")
        size_mb = os.path.getsize(full_path) // 1024 // 1024
        print(f"✅ Full Video Ready: {size_mb}MB")
        link = await asyncio.to_thread(upload_to_mixdrop, full_path)
        print(f"☁️ Full Video Mixdrop Link: {link}")
        if link:
            await safe_send(f"🎬 FULL VIDEO READY! 🍿✨\n\n🎥 {title}\n📦 Total Parts: {len(file_ids)}\n💾 Size: {size_mb}MB\n\n☁️ Full Video Link:\n{link}\n\n❤️ Enjoy Full Video! 💖")
        else:
            await safe_send(f"❌ Full Video Mixdrop Upload Failed! 🎥 {title}\n📦 Parts: {len(file_ids)}\n⚠️ Mixdrop Email / Key Check කරන්න!")
    except Exception as e:
        print(f"❌ Telegram Merge Failed: {e}")
        await safe_send(f"❌ Full Video Failed: {title}\nError: {e}")
    finally:
        try:
            os.remove(full_path)
        except:
            pass
        sent_parts.pop(title, None)
        save_sent_parts()
        await backup_to_telegram()

# ============================================================
# 🔄 AUTO MERGE AFTER RESTART!
# ============================================================
async def auto_merge_after_restart():
    await asyncio.sleep(10)
    if not sent_parts:
        print("✅ No saved parts - No Auto Merge needed!")
        return
    print(f"🔄 Restart Detected! Checking {len(sent_parts)} titles for Auto Merge...")
    await safe_send(f"🔄 Bot Restart වුණා! 🤖✨\n\n📦 කලින් Part ටික Check කරනවා... ⏳\n🎬 Titles: {len(sent_parts)}")
    watchlist = load_watchlist()
    for title in list(sent_parts.keys()):
        url = None
        for item in watchlist:
            if title.lower() in item.get('title', '').lower() or item.get('title', '').lower() in title.lower() or title.lower()[:20] in item.get('title', '').lower():
                url = item['url']
                break
        is_live = False
        if url:
            try:
                is_live = get_m3u8_link(url) is not None
            except:
                is_live = False
        # Watchlist එකේ නැත්නම්, Title එකෙන්ම Live ද කියලා හොයන්න බෑ, ඒ නිසා Auto Merge කරනවා!
        # (Watchlist එකේ තියෙන ඒවා විතරක් Live Check කරනවා!)
        if not url:
            print(f"⚠️ URL Not Found for {title} -> Auto Merge (Safe)!")
            is_live = False
        if not is_live:
            print(f"🏁 Live Ended: {title} -> Auto Merge Start!")
            await safe_send(f"🏁 {title} Live ඉවරයි! 🎬\n\n📥 Telegram Part ටිකෙන් Full Video හදනවා... ⏳")
            await merge_from_telegram(title)
        else:
            print(f"🔴 Still Live: {title} -> Merge Skip, Record Continue!")

# ============================================================
# 🔴 RECORD - 30 Parallel!
# ============================================================
async def record_live_light(url, title):
    part_num = 0
    fail_count = 0
    part_file = None
    seen_segments = set()
    upload_tasks = []
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
        task = asyncio.create_task(upload_part_now(part_file, title, part_num, is_last=True))
        upload_tasks.append(task)
    print(f"⏳ Waiting for {len(upload_tasks)} Uploads: {title} ...")
    if upload_tasks:
        await asyncio.gather(*upload_tasks, return_exceptions=True)
    print(f"✅ All Uploads Done: {title}")
    await merge_from_telegram(title)
    print(f"✅ Record + Telegram Merge Finished: {title}")

# ============================================================
# 👀 MONITOR - 30ම එක පාර Check!
# ============================================================
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
                        print(f"🔴 Started: {title} | Total: {len(recording_tasks)}/30")
        except Exception as e:
            print(f"⚠️ Monitor Error: {e}")
        await asyncio.sleep(5)

# ============================================================
# 🤖 COMMANDS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! 🤖✨\n\n🎬 30 Links Auto Record Bot! 🍿\n\n"
        "⚡ 30 Parallel! | 5MB Parts | 🎥 480p\n"
        "⚡ Record + Upload Parallel!\n"
        "🎬 Telegram Merge - Full Video!\n"
        "💾 Auto Backup + Auto Merge After Restart!\n\n"
        "📋 Commands:\n📃 /list - List Links 👀\n📺 /live - Check Live 🔴\n🎬 /merge - Manual Merge\n💾 /backup - Backup Now"
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

async def merge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        titles = "\n".join([f"🎬 {t} - 📦 {len(v)} Parts" for t, v in sent_parts.items()])
        await update.message.reply_text(f"📋 Merge කරන්න පුළුවන්:\n\n{titles or '📭 තාම Part නෑ!'}\n\n👉 Use: /merge Title එක")
        return
    title_q = " ".join(context.args)
    found = None
    for t in sent_parts:
        if title_q.lower() in t.lower():
            found = t
            break
    if not found:
        await update.message.reply_text(f"❌ '{title_q}' හම්බුනේ නෑ!")
        return
    await merge_from_telegram(found)

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_sent_parts()
    try:
        with open("sent_parts.json", "rb") as doc:
            await update.message.reply_document(document=doc, filename="sent_parts_backup.json", caption=f"💾 Backup! 🎬 Titles: {len(sent_parts)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Backup Failed: {e}")

async def post_init(app):
    load_sent_parts()
    asyncio.create_task(monitor_loop())
    asyncio.create_task(auto_merge_after_restart())

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
    app.add_handler(CommandHandler("merge", merge_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    print(f"🤖 Bot Started! ✨ 30 Parallel | 5MB | Telegram Merge | Auto-Restart Merge | Mixdrop Fixed | Port {PORT} 🚀")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
