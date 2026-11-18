import os
import asyncio
import subprocess
import glob
import requests
import time
import re
import json
import shutil
import threading
import gc
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
MIXDROP_EMAIL = os.getenv("MIXDROP_EMAIL")
MIXDROP_KEY = os.getenv("MIXDROP_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ALLOWED_USERS = [7038888904]

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_BYTES = 400 * 1024 * 1024

# ================= KEEP ALIVE FOR RENDER WEB SERVICE =================

PORT = int(os.getenv("PORT", 10000))

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Alive!")
    def log_message(self, format, *args):
        return

def start_keep_alive():
    try:
        server = HTTPServer(("0.0.0.0", PORT), KeepAliveHandler)
        print(f"KeepAlive Server Started on Port {PORT}", flush=True)
        server.serve_forever()
    except Exception as e:
        print(f"KeepAlive Error: {e}", flush=True)

# ================= MIXDROP UPLOAD - LOW RAM =================

def upload_mixdrop(file_path):
    size_mb = os.path.getsize(file_path) / 1024 / 1024
    print(f"📤 Uploading {file_path} Size: {size_mb:.1f}MB", flush=True)
    if size_mb > 500:
        print(f"⚠️ File too big {size_mb:.1f}MB > 500MB, skipping", flush=True)
        return None
    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                r = requests.post(
                    "https://ul.mixdrop.ag/api",
                    data={"email": MIXDROP_EMAIL, "key": MIXDROP_KEY},
                    files={"file": f},
                    timeout=1200
                )
            print(f"📩 Mixdrop Response: {r.text[:800]}", flush=True)
            data = r.json()
            if data.get("success"):
                fileref = data["result"]["fileref"]
                url = f"https://mixdrop.ag/f/{fileref}"
                print(f"✅ Uploaded: {url}", flush=True)
                gc.collect()
                return url
            print(f"❌ Mixdrop Failed: {data}", flush=True)
            if r.status_code == 400:
                print(f"⚠️ 400 Error - stopping retries for this file", flush=True)
                break
        except Exception as e:
            print(f"⚠️ Upload Error attempt {attempt+1}: {e}", flush=True)
            gc.collect()
            time.sleep(5)
    gc.collect()
    return None

# ✨ LOW RAM SPLIT - 8MB Chunks Only, Never Load Full 400MB To RAM
def split_large_file(file_path, chunk_mb=400):
    parts = []
    chunk_size = chunk_mb * 1024 * 1024
    buffer_size = 8 * 1024 * 1024
    base = file_path.replace(".mp4", "")
    with open(file_path, "rb") as f:
        idx = 1
        while True:
            out = f"{base}_split{idx:03d}.mp4"
            written = 0
            with open(out, "wb") as o:
                while written < chunk_size:
                    to_read = min(buffer_size, chunk_size - written)
                    data = f.read(to_read)
                    if not data:
                        break
                    o.write(data)
                    written += len(data)
            if written == 0:
                if os.path.exists(out):
                    os.remove(out)
                break
            parts.append(out)
            print(f"✂️ Split Part {idx} Done: {written / 1024 / 1024:.1f}MB", flush=True)
            idx += 1
            gc.collect()
            if written < chunk_size:
                break
    gc.collect()
    return parts

# ================= M3U8 FINDER =================

def find_m3u8_in_page(url):
    try:
        print(f"🔍 Searching M3U8 in page: {url}", flush=True)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        r = requests.get(url, headers=headers, timeout=30)
        html = r.text
        found = re.findall(r'https?://[^\s"\'\\]+\.m3u8[^\s"\'\\]*', html)
        if found:
            print(f"✅ Found M3U8 in HTML: {found[0][:120]}", flush=True)
            return found[0]
        found2 = re.findall(r'https?:\\/\\/[^\\s"\'\\\\]+\.m3u8[^\\s"\'\\\\]*', html)
        if found2:
            clean = found2[0].replace("\\/", "/")
            print(f"✅ Found Escaped M3U8: {clean[:120]}", flush=True)
            return clean
        found3 = re.findall(r'(?:file|source|src)\s*[:=]\s*["\'](https?://[^"\']+)', html)
        for f in found3:
            if ".m3u8" in f or "m3u8" in f or ".mp4" in f:
                print(f"✅ Found Source M3U8: {f[:120]}", flush=True)
                return f
    except Exception as e:
        print(f"⚠️ M3U8 Page Search Error: {e}", flush=True)
    return None

def get_m3u8_via_ytdlp_json(url):
    try:
        print(f"🔍 Trying yt-dlp JSON for M3U8...", flush=True)
        result = subprocess.run(["yt-dlp", "-j", "--no-playlist", "--no-check-certificates", url], capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip().splitlines()[0])
            if data.get("url") and ".m3u8" in data["url"]:
                return data["url"]
            for fmt in data.get("formats", []):
                u = fmt.get("url", "")
                if ".m3u8" in u:
                    print(f"✅ Found M3U8 in JSON formats: {u[:120]}", flush=True)
                    return u
                if fmt.get("protocol") in ["m3u8", "m3u8_native"]:
                    print(f"✅ Found M3U8 protocol: {u[:120]}", flush=True)
                    return u
            if data.get("url"):
                return data["url"]
    except Exception as e:
        print(f"⚠️ JSON M3U8 Error: {e}", flush=True)
    return None

# ================= FFMPEG + STREAMLINK HELPERS =================

def check_ffmpeg_m3u8(m3u8_url):
    try:
        if not m3u8_url or not m3u8_url.startswith("http"):
            return None
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1", "-i", m3u8_url],
            capture_output=True, text=True, timeout=30
        )
        if ".m3u8" in m3u8_url:
            print(f"✅ FFmpeg Accept M3U8: {m3u8_url[:120]}", flush=True)
            return m3u8_url
        if result.returncode == 0:
            return m3u8_url
    except Exception as e:
        print(f"⚠️ FFprobe Check Error: {e}", flush=True)
    return None

def get_url_via_streamlink(url, quality="best"):
    try:
        if not shutil.which("streamlink"):
            return None
        print(f"🔍 Trying Streamlink Quality: {quality}", flush=True)
        result = subprocess.run(
            ["streamlink", "--stream-url", "--stream-types", "hls,http", url, quality],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            stream = result.stdout.strip().splitlines()[0]
            if stream.startswith("http"):
                print(f"✅ Streamlink {quality} Success: {stream[:90]}", flush=True)
                return stream
        print(f"❌ Streamlink {quality} Failed: {result.stderr[:300]}", flush=True)
    except Exception as e:
        print(f"⚠️ Streamlink Error {quality}: {e}", flush=True)
    return None

def get_m3u8_via_streamlink_json(url):
    try:
        if not shutil.which("streamlink"):
            return None
        print(f"🔍 Trying Streamlink JSON for M3U8...", flush=True)
        result = subprocess.run(["streamlink", "--json", url], capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            streams = data.get("streams", {})
            for q in ["best", "1080p", "720p", "480p", "360p", "worst"]:
                if q in streams:
                    u = streams[q].get("url", "")
                    if u.startswith("http"):
                        print(f"✅ Streamlink JSON {q}: {u[:120]}", flush=True)
                        return u
            for q, info in streams.items():
                u = info.get("url", "")
                if ".m3u8" in u:
                    return u
    except Exception as e:
        print(f"⚠️ Streamlink JSON Error: {e}", flush=True)
    return None

def get_m3u8_then_ffmpeg(url):
    m3u8 = get_m3u8_via_ytdlp_json(url)
    if m3u8:
        valid = check_ffmpeg_m3u8(m3u8)
        if valid:
            return valid
    m3u8_2 = find_m3u8_in_page(url)
    if m3u8_2:
        valid2 = check_ffmpeg_m3u8(m3u8_2)
        if valid2:
            return valid2
    return None

def get_m3u8_then_streamlink(url):
    m3u8 = get_m3u8_via_ytdlp_json(url)
    if m3u8 and ".m3u8" in m3u8:
        s = get_url_via_streamlink(m3u8, "best")
        if s:
            return s
        return m3u8
    return None

# ================= YT-DLP ALL METHODS =================

def get_video_url(url):
    base_opts = ["--no-check-certificates", "--no-warnings", "--ignore-errors", "--retries", "10", "--fragment-retries", "10", "--retry-sleep", "2", "--socket-timeout", "30"]
    methods = [
        ["yt-dlp", "-g", "-f", "best[ext=mp4]/best"] + base_opts + ["--impersonate", "chrome", url],
        ["yt-dlp", "-g", "-f", "best"] + base_opts + ["--impersonate", "chrome", url],
        ["yt-dlp", "-g", "-f", "best[ext=mp4]/best"] + base_opts + ["--impersonate", "safari", url],
        ["yt-dlp", "-g", "-f", "best"] + base_opts + ["--impersonate", "firefox", url],
        ["yt-dlp", "-g", "-f", "best[ext=mp4]/best", "--live-from-start"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--live-from-start"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--live-from-start", "--impersonate", "chrome"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--hls-prefer-native"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--hls-prefer-ffmpeg"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--extractor-args", "generic:impersonate"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best[ext=mp4]/best", "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", "--add-header", "Referer:https://www.google.com/"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--user-agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--concurrent-fragments", "2"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best", "--no-playlist"] + base_opts + [url],
        ["yt-dlp", "-g", url],
        ["yt-dlp", "-g", "-f", "best", url],
        ["yt-dlp", "-g", "-f", "best", "--no-check-certificates", url],
        ["yt-dlp", "-g", "-f", "best", "-o", "%(title)s.%(ext)s", url],
        ["yt-dlp", "-g", "-f", "best[protocol=m3u8]/best", "--hls-prefer-native"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best[protocol=m3u8]/best", "--hls-prefer-ffmpeg"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "all", "--no-playlist"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--live-from-start", "--hls-prefer-native"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--impersonate", "chrome", "--hls-prefer-native"] + base_opts + [url],
        ["yt-dlp", "--get-url", "--no-playlist", "--no-check-certificates", url],
        ["yt-dlp", "-g", "-f", "best", "--wait-for-video", "10"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--no-live-from-start"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--hls-use-mpegts", "--hls-prefer-native"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--hls-use-mpegts", "--live-from-start"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--extractor-args", "youtube:player_client=android"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--extractor-args", "youtube:player_client=ios"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--live-from-start", "--extractor-args", "youtube:player_client=tv"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--fragment-retries", "infinite", "--concurrent-fragments", "2", "--retry-sleep", "5"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--cookies", "cookies.txt"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--geo-bypass", "--geo-bypass-country", "US"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--force-ipv4"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best[height<=720]/best"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "worst"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--downloader", "ffmpeg"] + base_opts + [url],
        ["yt-dlp", "-g", "-f", "best", "--live-from-start", "--extractor-args", "generic:impersonate"] + base_opts + [url],
    ]
    total = len(methods)
    for i, cmd in enumerate(methods, 1):
        try:
            print(f"🔍 Trying yt-dlp Method {i}/{total}...", flush=True)
            if "--cookies" in cmd and not os.path.exists("cookies.txt"):
                print(f"⏭️ Method {i} Skipped: cookies.txt not found", flush=True)
                continue
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and result.stdout.strip():
                stream = result.stdout.strip().splitlines()[0]
                if stream.startswith("http"):
                    print(f"✅ Method {i} Success: {stream[:90]}", flush=True)
                    return stream
            print(f"❌ Method {i} Failed: {result.stderr[:300]}", flush=True)
        except Exception as e:
            print(f"⚠️ Method {i} Error: {e}", flush=True)
            continue
    print(f"🔍 Trying M3U8 Hunter - Page Search...", flush=True)
    m3u8 = find_m3u8_in_page(url)
    if m3u8:
        return m3u8
    print(f"🔍 Trying M3U8 Hunter - JSON Search...", flush=True)
    m3u8_2 = get_m3u8_via_ytdlp_json(url)
    if m3u8_2:
        return m3u8_2
    print(f"🔍 Trying Streamlink Methods...", flush=True)
    for q in ["best", "1080p", "720p", "480p", "360p", "worst"]:
        s = get_url_via_streamlink(url, q)
        if s:
            return s
    s_json = get_m3u8_via_streamlink_json(url)
    if s_json:
        return s_json
    try:
        if shutil.which("streamlink"):
            result = subprocess.run(["streamlink", "--stream-url", "--http-header", "User-Agent=Mozilla/5.0", "--http-header", "Referer=https://www.google.com/", url, "best"], capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and result.stdout.strip().startswith("http"):
                return result.stdout.strip().splitlines()[0]
    except Exception as e:
        print(f"⚠️ Streamlink Header Error: {e}", flush=True)
    print(f"🔍 Trying YT-DLP M3U8 -> FFmpeg...", flush=True)
    m3u8_ffmpeg = get_m3u8_then_ffmpeg(url)
    if m3u8_ffmpeg:
        return m3u8_ffmpeg
    print(f"🔍 Trying YT-DLP M3U8 -> Streamlink...", flush=True)
    m3u8_streamlink = get_m3u8_then_streamlink(url)
    if m3u8_streamlink:
        return m3u8_streamlink
    print(f"🔍 Trying FFmpeg Direct Probe...", flush=True)
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv", "-i", url], capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and "video" in result.stdout:
            return url
    except Exception as e:
        print(f"⚠️ FFmpeg Probe Error: {e}", flush=True)
    return None

# ================= AUTO WAIT FOR LIVE =================
# ✨ Checks Every 2 Minutes If Live Is Started
# ✨ If Live Is Not Started, It Keeps Waiting Forever - No Time Limit
# ✨ When Live Starts, It Returns True And Recording Begins

def check_is_live_quick(url):
    try:
        result = subprocess.run(
            ["yt-dlp", "-g", "-f", "best", "--no-playlist", "--no-check-certificates", "--no-warnings", url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and result.stdout.strip().startswith("http"):
            return True
        result2 = subprocess.run(
            ["yt-dlp", "-j", "--no-playlist", "--no-check-certificates", "--no-warnings", url],
            capture_output=True, text=True, timeout=60
        )
        if result2.returncode == 0 and result2.stdout.strip():
            try:
                data = json.loads(result2.stdout.strip().splitlines()[0])
                if data.get("is_live") is True:
                    return True
                if data.get("live_status") in ["is_live", "is_upcoming"]:
                    if data.get("live_status") == "is_live":
                        return True
            except:
                pass
        return False
    except Exception as e:
        print(f"⚠️ Live Check Error: {e}", flush=True)
        return False

# ================= TERMUX METHOD - LOW RAM =================

def termux_method_download(url, folder):
    try:
        print(f"🔥 Trying TERMUX METHOD - bestvideo+bestaudio/best...", flush=True)
        out_template = os.path.join(folder, "%(title)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "-c",
            "-f", "bestvideo+bestaudio/best",
            "-o", out_template,
            "--no-check-certificates",
            "--no-playlist",
            "--live-from-start",
            "--merge-output-format", "mp4",
            "--concurrent-fragments", "2",
            "--buffer-size", "16K",
            "--http-chunk-size", "5M",
            "--retries", "10",
            "--fragment-retries", "10",
            url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=14400)
        print(f"Termux Method Output: {result.stdout[-500:]} {result.stderr[-500:]}", flush=True)
        gc.collect()
        files = sorted(glob.glob(os.path.join(folder, "*.*")))
        files = [f for f in files if not f.endswith(".jpg") and not f.endswith(".part") and not f.endswith(".ytdl") and os.path.getsize(f) > 1000]
        if files:
            print(f"✅ Termux Method Success: {files[0]}", flush=True)
            return files[0]
    except Exception as e:
        print(f"Termux Method Error: {e}", flush=True)
    gc.collect()
    return None

def direct_download_fallback(url, folder):
    try:
        print(f"🔥 Trying Direct Download - bestvideo+bestaudio/best...", flush=True)
        out_template = os.path.join(folder, "%(title)s.%(ext)s")
        cmd = ["yt-dlp", "-c", "-f", "bestvideo+bestaudio/best", "-o", out_template, "--no-check-certificates", "--no-playlist", "--merge-output-format", "mp4", "--concurrent-fragments", "2", "--buffer-size", "16K", url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        print(f"yt-dlp Download Output: {result.stdout[-500:]} {result.stderr[-500:]}", flush=True)
        gc.collect()
        files = sorted(glob.glob(os.path.join(folder, "*.*")))
        files = [f for f in files if not f.endswith(".jpg") and os.path.getsize(f) > 1000]
        if files:
            print(f"✅ Direct Download Success: {files[0]}", flush=True)
            return files[0]
    except Exception as e:
        print(f"Direct Download bestvideo+bestaudio Error: {e}", flush=True)
    try:
        print(f"🔥 Trying Direct Download Fallback - yt-dlp best...", flush=True)
        out_template = os.path.join(folder, "%(title)s.%(ext)s")
        cmd = ["yt-dlp", "-o", out_template, "-f", "best[ext=mp4]/best", "--no-check-certificates", "--no-playlist", "--concurrent-fragments", "2", url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        files = sorted(glob.glob(os.path.join(folder, "*.*")))
        files = [f for f in files if not f.endswith(".jpg")]
        if files:
            return files[0]
    except Exception as e:
        print(f"Direct Download yt-dlp Error: {e}", flush=True)
    try:
        print(f"🔥 Trying Direct Download Fallback - Streamlink...", flush=True)
        if shutil.which("streamlink"):
            out_file = os.path.join(folder, "streamlink_live.mp4")
            result = subprocess.run(["streamlink", "-o", out_file, url, "best"], capture_output=True, text=True, timeout=3600)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                return out_file
    except Exception as e:
        print(f"Direct Download Streamlink Error: {e}", flush=True)
    try:
        print(f"🔥 Trying Direct Download Fallback - FFmpeg M3U8...", flush=True)
        m3u8 = get_m3u8_then_ffmpeg(url)
        if m3u8:
            out_file = os.path.join(folder, "ffmpeg_live.mp4")
            result = subprocess.run(["ffmpeg", "-threads", "1", "-i", m3u8, "-c", "copy", "-t", "3600", "-y", out_file], capture_output=True, text=True, timeout=3600)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                return out_file
    except Exception as e:
        print(f"Direct Download FFmpeg Error: {e}", flush=True)
    gc.collect()
    return None

# ================= BOT COMMANDS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hey! Welcome Baby! 💖\n\n"
        "🎬 Just Send Me A Live Link\n"
        "📥 I Will Record + Upload To Mixdrop\n"
        "📺 And Send All Parts To Your Channel ✨\n\n"
        "🔥 YT-DLP + Streamlink + FFmpeg + M3U8 Methods Active!\n"
        "✂️ 400MB Split Active!\n"
        "💾 512MB RAM Optimized!\n"
        "⏳ Auto Wait For Live Active! Just Send Link Early, I Will Wait & Auto Record 🔴"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("🚫 Sorry Baby, You Are Not Allowed! 🥺")
        return
    url = update.message.text.strip()
    if "http" not in url:
        return
    msg = await update.message.reply_text(f"🎬 Link Received Baby... 💖\n\n🔗 {url}\n\n⏳ Checking Live Status...")
    asyncio.create_task(process_stream(update, context, url, msg))

# ================= MAIN RECORD PROCESS =================

async def process_stream(update, context, url, msg):
    job_id = str(int(time.time()))[-6:]
    folder = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(folder, exist_ok=True)
    links = []
    thumb_path = os.path.join(folder, "thumb.jpg")
    highlight_path = os.path.join(folder, "highlight.mp4")
    ffmpeg_proc = None
    uploaded_files = set()
    try:
        # ===== AUTO WAIT FOR LIVE - NO TIME LIMIT =====
        wait_count = 0
        is_live_now = await asyncio.to_thread(check_is_live_quick, url)
        while not is_live_now:
            wait_count += 1
            try:
                await msg.edit_text(
                    f"⏳ Waiting For Live Baby... 💖\n\n"
                    f"🔗 {url}\n\n"
                    f"🔴 Live Not Started Yet...\n"
                    f"🔄 Checked: {wait_count} Times\n"
                    f"⏰ Next Check In 2 Minutes...\n\n"
                    f"✨ Don't Worry, I Will Auto Start When Live Begins!"
                )
            except:
                pass
            print(f"⏳ Waiting For Live... Check {wait_count} - Not Live Yet", flush=True)
            gc.collect()
            await asyncio.sleep(120)
            is_live_now = await asyncio.to_thread(check_is_live_quick, url)

        await msg.edit_text("🔴 Live Started Baby! 💖\n\n🎬 Starting Recording... ✨")

        # ===== METHOD 0 - TERMUX METHOD FIRST =====
        await msg.edit_text("🔥 Termux Method Trying Baby... 💖\n\n🎬 yt-dlp bestvideo+bestaudio/best\n⏳ Downloading Until Live Ends...\nPlease Wait...")
        termux_file = await asyncio.to_thread(termux_method_download, url, folder)
        if termux_file and os.path.exists(termux_file):
            await msg.edit_text("✅ Termux Method Success Baby! 💖\n\n✂️ Splitting To 400MB & Uploading... ✨")
            to_upload = [termux_file]
            if os.path.getsize(termux_file) > MAX_BYTES:
                to_upload = split_large_file(termux_file)
                os.remove(termux_file)
            for f in to_upload:
                link = await asyncio.to_thread(upload_mixdrop, f)
                if link:
                    links.append(link)
                if os.path.exists(f):
                    os.remove(f)
                gc.collect()
            if links:
                caption = f"🎬✨ NEW RECORDING ✨🎬\n\n🔗 {url}\n\n📦 Total Parts: {len(links)}\n━━━━━━━━━━━━━━━\n\n"
                for i, l in enumerate(links, 1):
                    caption += f"▶️ Part {i}: {l}\n"
                caption += f"\n💖 Enjoy Baby! ✨"
                await context.bot.send_message(CHANNEL_ID, caption)
                await msg.edit_text(f"🎉 Done Baby! 💖✨\n\n✅ Termux Method Uploaded! {len(links)} Parts")
                return
            await msg.edit_text("⚠️ Upload Failed, Trying Old Methods Baby... ✨")

        # ===== OLD METHODS - IF TERMUX METHOD FAILS =====
        await msg.edit_text("🔍 Getting Stream URL Baby... ✨\n\n🔥 Trying YT-DLP + Streamlink + FFmpeg + M3U8 Methods...\n⏳ Please Wait...")
        stream_url = await asyncio.to_thread(get_video_url, url)
        if not stream_url:
            await msg.edit_text("🔥 All Methods Failed...\n\n📥 Trying Direct Download Baby... ✨\n⏳ Please Wait...")
            direct_file = await asyncio.to_thread(direct_download_fallback, url, folder)
            if direct_file and os.path.exists(direct_file):
                to_upload = [direct_file]
                if os.path.getsize(direct_file) > MAX_BYTES:
                    await msg.edit_text("✂️ File Big Baby, Splitting To 400MB... ✨")
                    to_upload = split_large_file(direct_file)
                    os.remove(direct_file)
                for f in to_upload:
                    link = await asyncio.to_thread(upload_mixdrop, f)
                    if link:
                        links.append(link)
                    if os.path.exists(f):
                        os.remove(f)
                    gc.collect()
                if links:
                    caption = f"🎬✨ NEW RECORDING ✨🎬\n\n🔗 {url}\n\n📦 Total Parts: {len(links)}\n━━━━━━━━━━━━━━━\n\n"
                    for i, l in enumerate(links, 1):
                        caption += f"▶️ Part {i}: {l}\n"
                    caption += f"\n💖 Enjoy Baby! ✨"
                    await context.bot.send_message(CHANNEL_ID, caption)
                    await msg.edit_text(f"🎉 Done Baby! 💖✨\n\n✅ Direct Download Uploaded! {len(links)} Parts")
                    return
            await msg.edit_text("❌ Record Failed Baby 🥺\n\nNo Stream URL Found!\nAll Methods Failed!\nPlease Try Another Link 💖")
            return
        await msg.edit_text("🔴 LIVE Recording Started... 🎬\n\n✂️ 400MB Split + 📤 Uploading In Parallel...\n\n⏳ Please Wait Baby 💖")
        part_pattern = os.path.join(folder, "part_%03d.mp4")
        ffmpeg_cmd = [
            "ffmpeg",
            "-threads", "1",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-i", stream_url,
            "-c", "copy",
            "-map", "0",
            "-f", "segment",
            "-segment_time", "3600",
            "-segment_format", "mp4",
            "-reset_timestamps", "1",
            "-fs", str(MAX_BYTES),
            part_pattern
        ]
        ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        async def watcher():
            while True:
                parts = sorted(glob.glob(os.path.join(folder, "part_*.mp4")))
                active = ffmpeg_proc.poll() is None
                ready = parts[:-1] if active else parts
                for p in ready:
                    if p in uploaded_files:
                        continue
                    s1 = os.path.getsize(p)
                    await asyncio.sleep(2)
                    if not os.path.exists(p):
                        continue
                    s2 = os.path.getsize(p)
                    if s1 != s2:
                        continue
                    uploaded_files.add(p)
                    upload_list = [p]
                    if os.path.getsize(p) > MAX_BYTES:
                        upload_list = split_large_file(p)
                        os.remove(p)
                    for up in upload_list:
                        await msg.edit_text(f"📤 Uploading {os.path.basename(up)} Baby... 💖\n\n✅ Uploaded: {len(links)} Parts\n⏳ Recording Continues... 🔴")
                        link = await asyncio.to_thread(upload_mixdrop, up)
                        if link:
                            links.append(link)
                        else:
                            print(f"⚠️ Upload failed, trying smaller split for {up}", flush=True)
                            if os.path.exists(up) and os.path.getsize(up) > 100*1024*1024:
                                small_parts = split_large_file(up, chunk_mb=100)
                                for sp in small_parts:
                                    l2 = await asyncio.to_thread(upload_mixdrop, sp)
                                    if l2:
                                        links.append(l2)
                                    if os.path.exists(sp):
                                        os.remove(sp)
                                    gc.collect()
                        if os.path.exists(up):
                            os.remove(up)
                        gc.collect()
                if not active:
                    break
                await asyncio.sleep(5)
            return
        watcher_task = asyncio.create_task(watcher())
        while ffmpeg_proc.poll() is None:
            await asyncio.sleep(5)
        await watcher_task
        remaining = sorted(glob.glob(os.path.join(folder, "part_*.mp4")))
        for p in remaining:
            if p not in uploaded_files:
                upload_list = [p]
                if os.path.getsize(p) > MAX_BYTES:
                    upload_list = split_large_file(p)
                    os.remove(p)
                for up in upload_list:
                    link = await asyncio.to_thread(upload_mixdrop, up)
                    if link:
                        links.append(link)
                    if os.path.exists(up):
                        os.remove(up)
                    gc.collect()
        if not links:
            await msg.edit_text("❌ Failed Baby 🥺\n\nNo Parts Uploaded!")
            return
        await msg.edit_text("🖼️ Making Thumbnail + Highlights Baby... ✨")
        try:
            subprocess.run(["ffmpeg", "-threads", "1", "-i", stream_url, "-ss", "10", "-vframes", "1", "-y", thumb_path], capture_output=True, timeout=60)
        except Exception as e:
            print(f"Thumb error: {e}", flush=True)
        hl_link = None
        try:
            subprocess.run(["ffmpeg", "-threads", "1", "-i", stream_url, "-t", "300", "-c", "copy", "-y", highlight_path], capture_output=True, timeout=120)
            if os.path.exists(highlight_path):
                if os.path.getsize(highlight_path) > MAX_BYTES:
                    hl_parts = split_large_file(highlight_path)
                    os.remove(highlight_path)
                    for hp in hl_parts:
                        hl_link = await asyncio.to_thread(upload_mixdrop, hp)
                        if os.path.exists(hp):
                            os.remove(hp)
                        break
                else:
                    hl_link = await asyncio.to_thread(upload_mixdrop, highlight_path)
                    os.remove(highlight_path)
        except Exception as e:
            print(f"Highlight error: {e}", flush=True)
        gc.collect()
        caption = f"🎬✨ NEW LIVE RECORDING ✨🎬\n\n🔗 {url}\n\n📦 Total Parts: {len(links)} (400MB Each)\n━━━━━━━━━━━━━━━\n\n"
        for i, l in enumerate(links, 1):
            caption += f"▶️ Part {i}: {l}\n"
        if hl_link:
            caption += f"\n🔥 Highlights (5 Min): {hl_link}\n"
        caption += f"\n💖 Enjoy Baby! ✨"
        if os.path.exists(thumb_path):
            with open(thumb_path, "rb") as photo:
                await context.bot.send_photo(CHANNEL_ID, photo=photo, caption=caption)
            os.remove(thumb_path)
        else:
            await context.bot.send_message(CHANNEL_ID, caption)
        await msg.edit_text(f"🎉 Done Baby! 💖✨\n\n✅ {len(links)} Parts Uploaded (400MB Each)\n📺 Sent To Channel!")
    except Exception as e:
        print(f"Error: {e}", flush=True)
        await msg.edit_text(f"❌ Error Baby 🥺\n\n{e}")
    finally:
        gc.collect()
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            ffmpeg_proc.kill()

async def error_handler(update, context):
    print(f"Error: {context.error}", flush=True)

def run_bot():
    while True:
        try:
            app = ApplicationBuilder().token(BOT_TOKEN).build()
            app.add_handler(CommandHandler("start", start))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
            app.add_error_handler(error_handler)
            print("🤖 Bot Started 💖", flush=True)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(app.run_polling(drop_pending_updates=True))
        except Exception as e:
            print(f"💥 Bot Crashed, Restarting in 5s: {e}", flush=True)
            time.sleep(5)
            continue
        break

def main():
    threading.Thread(target=start_keep_alive, daemon=True).start()
    run_bot()

if __name__ == "__main__":
    main()
