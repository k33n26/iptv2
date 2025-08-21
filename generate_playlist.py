
import os, re, requests, hashlib
from PIL import Image
from io import BytesIO

RAW_DIR = "raw_lists"
LOGO_DIR = "logos"
OUTPUT_FILE = "playlist.m3u"

LOGO_SIZES = {
    "small": (64, 64),
    "medium": (128, 128),
    "large": (256, 256),
}

# Klasörleri hazırla
for size in LOGO_SIZES.keys():
    os.makedirs(os.path.join(LOGO_DIR, size), exist_ok=True)

def clean_channel_name(link):
    return os.path.splitext(os.path.basename(link.split("?")[0]))[0]

def get_logo_url(channel_name):
    sources = [
        f"https://logo.clearbit.com/{channel_name}.com",
        f"https://www.google.com/s2/favicons?domain={channel_name}.com&sz=128",
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
    logo_url = get_logo_url(channel_name.lower())
    if not logo_url:
        return None
    try:
        r = requests.get(logo_url, timeout=10)
        if r.status_code == 200:
            img = Image.open(BytesIO(r.content)).convert("RGBA")
            safe_name = hashlib.md5(channel_name.encode()).hexdigest()
            saved_urls = {}
            for size, dims in LOGO_SIZES.items():
                resized = img.resize(dims, Image.LANCZOS)
                path = os.path.join(LOGO_DIR, size, f"{safe_name}.webp")
                resized.save(path, "WEBP")
                saved_urls[size] = f"https://raw.githubusercontent.com/k33n26/iptv2/main/logos/{size}/{safe_name}.webp"
            return saved_urls
    except:
        return None
    return None

def generate_playlist():
    m3u = ["#EXTM3U\n"]
    for fname in os.listdir(RAW_DIR):
        if not fname.endswith(".txt"):
            continue
        category = os.path.splitext(fname)[0]
        with open(os.path.join(RAW_DIR, fname)) as f:
            for line in f:
                url = line.strip()
                if not url:
                    continue
                channel = clean_channel_name(url)
                logos = download_and_save_logo(channel)
                if logos:
                    logo_attr = f'tvg-logo="{logos["medium"]}"'
                    extra_logos = " | ".join([f"{k}:{v}" for k, v in logos.items()])
                    extgrp = f'#EXTGRP:LOGOS {extra_logos}'
                else:
                    logo_attr = ""
                    extgrp = ""
                m3u.append(f'#EXTINF:-1 group-title="{category}" {logo_attr}, {channel}\n')
                if extgrp:
                    m3u.append(extgrp + "\n")
                m3u.append(f"{url}\n")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(m3u)

if __name__ == "__main__":
    generate_playlist()
