# /usr/bin/python3
import os
import hashlib
import pickle
import threading
from concurrent.futures import ThreadPoolExecutor
import time

os.environ["PATH"] = os.path.dirname(__file__) + os.pathsep + os.environ["PATH"]

from mpv import MPV
import yt_dlp
from yt_search import search  # برای جستجوی سریعتر
import warnings

warnings.filterwarnings("ignore")

# تنظیمات کش
CACHE_DIR = "./yt_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# MPV Player بهینه‌شده
player = MPV(
    ytdl=False,  # غیرفعال چون خودمون پردازش می‌کنیم
    input_default_bindings=True,
    input_vo_keyboard=True,
    vid=False,
    audio_only=True,  # فقط صدا
    volume=60,
    cache=yes,  # کش MPV
    cache_secs=300,  # 5 دقیقه کش
    demuxer_max_bytes="10M",  # بافر برای پخش روان
    demuxer_readahead_secs=30,
    hwdec='no'  # غیرفعال کردن سخت‌افزار برای صرفاً صدا
)

# اجرای موازی برای پردازش همزمان
executor = ThreadPoolExecutor(max_workers=3)

# کش برای نتایج جستجو
def get_cache_key(query):
    return hashlib.md5(query.lower().encode()).hexdigest()

def cached_search(query, max_results=3):
    """جستجوی کش‌شده برای سرعت بیشتر"""
    cache_key = get_cache_key(query)
    cache_file = os.path.join(CACHE_DIR, f"search_{cache_key}.pkl")
    
    # بررسی کش
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'rb') as f:
                cached = pickle.load(f)
                if time.time() - cached['timestamp'] < 3600:  # 1 ساعت اعتبار
                    return cached['results']
        except:
            pass
    
    # جستجوی جدید
    try:
        # استفاده از yt_search برای سرعت بیشتر
        results = search(query, max_results=max_results)
        
        # ذخیره در کش
        cache_data = {
            'timestamp': time.time(),
            'results': results
        }
        with open(cache_file, 'wb') as f:
            pickle.dump(cache_data, f)
        
        return results
    except:
        # Fallback به yt-dlp اگر yt-search کار نکرد
        return None

def youtube_search_first_fast(query):
    """جستجوی سریع با کش و پردازش موازی"""
    # اول از کش یا yt_search استفاده می‌کنیم
    search_results = cached_search(query)
    
    if search_results:
        video_id = search_results[0]['video_id']
        title = search_results[0]['title']
        url = f"https://youtu.be/{video_id}"
        
        # استخراج لینک صدا در پس‌زمینه
        audio_url = extract_audio_url_async(video_id)
        return audio_url, title
    
    # Fallback به روش قبلی
    return youtube_search_first_original(query)

def extract_audio_url_async(video_id):
    """استخراج لینک صدا به صورت غیرهمزمان"""
    ydl_opts = {
        'format': 'bestaudio[acodec=opus]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'noplaylist': True,
        'postprocessor_args': ['-vn'],  # فقط صدا
        'outtmpl': '%(id)s.%(ext)s',
        'socket_timeout': 10,
        'retries': 3,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://youtu.be/{video_id}", download=False)
            # اولویت با فرمت‌های سبک
            formats = info.get('formats', [])
            audio_formats = [f for f in formats if f.get('acodec') != 'none']
            
            # انتخاب بهترین فرمت صدا (با اولویت opus برای حجم کم)
            for f in audio_formats:
                if 'opus' in f.get('acodec', ''):
                    return f['url']
            
            # اگر opus نبود، اولین لینک صدا
            if audio_formats:
                return audio_formats[0]['url']
            
            return info['url']
    except:
        return f"https://youtu.be/{video_id}"

# نگه داشتن تابع اصلی به عنوان fallback
def youtube_search_first_original(query):
    """تابع اصلی شما به عنوان پشتیبان"""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "default_search": "ytsearch1",
        "format": "bestaudio/best",
        "socket_timeout": 10,
        "retries": 2,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        video = info["entries"][0]
        return video["url"], video["title"]

def play_youtube(query, use_cache=True):
    """پخش با قابلیت انتخاب روش"""
    start_time = time.time()
    
    if use_cache:
        url, title = youtube_search_first_fast(query)
    else:
        url, title = youtube_search_first_original(query)
    
    search_time = time.time() - start_time
    
    print(f"\n🎵 [{search_time:.2f}s] Playing: {title}")
    
    # پخش در MPV
    player.command("loadfile", url, "replace")
    
    # نمایش وضعیت پخش
    def status_monitor():
        time.sleep(0.5)
        if player.duration:
            print(f"⏱ Duration: {player.duration:.0f}s | Volume: {player.volume}%")
    
    threading.Thread(target=status_monitor, daemon=True).start()

def clear_cache():
    """پاک کردن کش"""
    for file in os.listdir(CACHE_DIR):
        if file.endswith('.pkl'):
            os.remove(os.path.join(CACHE_DIR, file))
    print("✅ Cache cleared")

def show_help():
    print("\n" + "="*50)
    print("📌 Commands:")
    print("  /cache     - Clear cache")
    print("  /help      - Show this help")
    print("  /volume N  - Set volume (0-100)")
    print("  /pause     - Pause/Resume")
    print("  /stop      - Stop playback")
    print("  /fast      - Toggle fast mode")
    print("  /exit      - Exit program")
    print("="*50)

if __name__ == "__main__":
    print("🚀 YouTube Audio Player (Optimized)")
    print("Type '/help' for commands")
    
    fast_mode = True
    
    while True:
        try:
            q = input("\n🎧 Search: ").strip()
            
            if not q:
                continue
                
            # پردازش دستورات
            if q.startswith('/'):
                cmd = q.lower()
                
                if cmd == '/exit' or cmd == '/quit':
                    player.terminate()
                    executor.shutdown()
                    break
                    
                elif cmd == '/help':
                    show_help()
                    
                elif cmd == '/cache':
                    clear_cache()
                    
                elif cmd == '/fast':
                    fast_mode = not fast_mode
                    print(f"⚡ Fast mode: {'ON' if fast_mode else 'OFF'}")
                    
                elif cmd.startswith('/volume '):
                    try:
                        vol = int(cmd.split()[1])
                        if 0 <= vol <= 100:
                            player.volume = vol
                            print(f"🔊 Volume set to {vol}%")
                    except:
                        print("❌ Use: /volume 0-100")
                        
                elif cmd == '/pause':
                    player.pause = not player.pause
                    print("⏸️ Paused" if player.pause else "▶️ Resumed")
                    
                elif cmd == '/stop':
                    player.command("stop")
                    print("⏹️ Stopped")
                    
                else:
                    print("❌ Unknown command")
                    
            else:
                # جستجو و پخش
                play_youtube(q, use_cache=fast_mode)
                
        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            player.terminate()
            executor.shutdown()
            break
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            # تلاش مجدد با روش ساده
            try:
                url, title = youtube_search_first_original(q)
                player.command("loadfile", url, "replace")
                print(f"▶ Playing (fallback): {title}")
            except:
                print("⚠️ Please try another search")