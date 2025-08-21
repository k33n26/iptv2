import os, requests, hashlib, json
from PIL import Image
from io import BytesIO

RAW_DIR = "raw_lists"
LOGO_DIR = "logos"
OUTPUT_FILE = "playlist.m3u"
CACHE_FILE = "cache.json"

LOGO_SIZES = {
    "small": (64, 64),
    "medium": (128, 128),
    "large": (256, 256),
}

# Klasörleri hazırla
for size in LOGO_SIZES.keys():
    os.makedirs(os.path.join(LOGO_DIR, size), exist_ok=True)

# Cache yükle
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}

def safe_filename(channel_name):
    return hashlib.md5(channel_name.encode()).hexdigest()

def get_logo_url(channel_name):
    sources = [
        f"https://logo.clearbit.com/{channel_name.replace(' ', '').lower()}.com",
        f"https://www.google.com/s2/favicons?domain={channel_name.replace(' ', '').lower()}.com&sz=128",
    ]
    for url in sources:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200 and r.content:
                return url
        except:
            pass
    return None

def download_and_save_logo(channel_name):
    safe_name = safe_filename(channel_name)

    # Önce cache kontrolü
    if channel_name in cache:
        return cache[channel_name]  # bulunduysa direkt döndür (bulunmadıysa None döner)

    logo_url = get_logo_url(channel_name)
    if not logo_url:
        cache[channel_name] = None
        return None

    try:
        r = requests.get(logo_url, timeout=10)
        if r.status_code == 200:
            img = Image.open(BytesIO(r.content)).convert("RGBA")
            saved_urls = {}
            for size, dims in LOGO_SIZES.items():
                resized = img.resize(dims, Image.LANCZOS)
                path = os.path.join(LOGO_DIR, size, f"{safe_name}.webp")
                resized.save(path, "WEBP")
                saved_urls[size] = f"https://raw.githubusercontent.com/k33n26/iptv2/main/logos/{size}/{safe_name}.webp"

            # Cache'e kaydet
            cache[channel_name] = saved_urls
            return saved_urls
    except:
        cache[channel_name] = None
        return None
    return None

def generate_playlist():
    m3u = ["#EXTM3U\n"]

    for fname in os.listdir(RAW_DIR):
        if not fname.endswith(".txt"):
            continue
        category = os.path.splitext(fname)[0]
        with open(os.path.join(RAW_DIR, fname), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "," not in line:
                    continue
                channel_name, url = line.split(",", 1)
                logos = download_and_save_logo(channel_name)
                if logos:
                    logo_attr = f'tvg-logo="{logos["medium"]}"'
                else:
                    logo_attr = ""
                m3u.append(f'#EXTINF:-1 group-title="{category}" {logo_attr},{channel_name}\n')
                m3u.append(f"{url}\n")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(m3u)

    # Cache güncelle
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    generate_playlist()
