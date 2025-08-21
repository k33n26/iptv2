#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
from urllib.parse import urlparse
import requests
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import re
import time

# --- AYARLAR ---
RAW_DIR = "raw_lists"                  # m3u8 linklerinin olduğu .txt dosyaları burada
OUTPUT_FILE = "playlist.m3u"           # tek birleştirilmiş dosya
CATEGORY_FILE = "categories.json"      # otomatik öğrenen kategori sözlüğü
LOGO_CACHE_FILE = "logo_cache.json"    # logo cache zamanları (timestamp)

# Cache ve temizlik
CACHE_SECONDS = 7 * 24 * 60 * 60             # 7 gün aynı logoyu yeniden indirme
OLD_LOGO_DELETE_SECONDS = 30 * 24 * 60 * 60  # 30 gün dokunulmadıysa logoyu sil

# Çoklu logo boyut & kalite (small/medium/large)
LOGO_SIZES = {
    "small":  (32, 32, 60),
    "medium": (64, 64, 80),
    "large":  (128, 128, 90)
}

# GitHub raw base (BU REPO İÇİN sabit)
RAW_BASE = "https://raw.githubusercontent.com/k33n26/iptv2/main"

# Klasörleri oluştur
for size in LOGO_SIZES.keys():
    os.makedirs(os.path.join("logos", size), exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

# Kategori sözlüğü
if os.path.exists(CATEGORY_FILE):
    with open(CATEGORY_FILE, "r", encoding="utf-8") as f:
        CATEGORIES = json.load(f)
else:
    CATEGORIES = {}

# Logo cache
if os.path.exists(LOGO_CACHE_FILE):
    with open(LOGO_CACHE_FILE, "r", encoding="utf-8") as f:
        LOGO_CACHE = json.load(f)
else:
    LOGO_CACHE = {}

def clean_channel_name(name: str) -> str:
    # URL’den okunaklı kanal adı çıkar
    s = name.strip()
    s = re.sub(r'https?://', '', s, flags=re.I)
    s = re.sub(r'www\.', '', s, flags=re.I)
    s = s.split('/')[0]  # domain’i al
    s = re.sub(r'\..*$', '', s)          # .com .tv vs kaldır
    s = re.sub(r'[_\-]+', ' ', s)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'\d+', '', s).strip()
    return s.title() or "Channel"

def clean_category_name(name: str) -> str:
    s = re.sub(r'[_\-]+', ' ', name)
    s = re.sub(r'\d+', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return (s.title() or "Unknown")

def compute_similarity(category_keywords: dict, line: str, filename: str) -> int:
    score = 0
    line_lower = line.lower()
    filename_lower = filename.lower()
    for kw, kw_score in category_keywords.items():
        if kw in line_lower:
            score += kw_score
        if kw in filename_lower:
            score += kw_score * 2
    return score

def score_category(filename: str, line: str) -> str:
    scores = {}
    for category, data in CATEGORIES.items():
        score = compute_similarity(data.get("keywords", {}), line, filename)
        score += data.get("score", 0)
        if score > 0:
            scores[category] = score
    if not scores:
        host = (urlparse(line).hostname or "unknown").split('.')[0]
        if host not in CATEGORIES:
            CATEGORIES[host] = {"keywords": {host: 2}, "score": 0}
        return host
    best = max(scores, key=scores.get)
    CATEGORIES[best]["score"] = CATEGORIES[best].get("score", 0) + 1
    return best

def clean_old_logos():
    now = time.time()
    removed = []
    for safe_name, ts in list(LOGO_CACHE.items()):
        if now - ts > OLD_LOGO_DELETE_SECONDS:
            for size in LOGO_SIZES.keys():
                p = os.path.join("logos", size, f"{safe_name}.webp")
                if os.path.exists(p):
                    os.remove(p)
            removed.append(safe_name)
            del LOGO_CACHE[safe_name]
    if removed:
        with open(LOGO_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(LOGO_CACHE, f)
        print(f"[CLEAN] Eski logolar silindi: {removed}")

def safe_logo_name(hostname: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]+', '_', hostname).strip('_').lower() or "logo"

def download_and_convert_logo(stream_url: str) -> str:
    """
    İndirilebildiyse tüm boyutları (small/medium/large) .webp olarak kaydeder.
    Başarılıysa 'safe_name' döner, yoksa "".
    """
    host = (urlparse(stream_url).hostname or "unknown").split('.')[0]
    safe_name = safe_logo_name(host)
    now = time.time()

    # Cache kontrolü
    if safe_name in LOGO_CACHE and (now - LOGO_CACHE[safe_name] < CACHE_SECONDS):
        return safe_name

    # Denenecek logo kaynakları
    trial_urls = [
        f"https://raw.githubusercontent.com/channel-logos/{host}.png",
        f"https://{host}/favicon.ico",
        f"https://{host}/favicon.png"
    ]

    for url in trial_urls:
        try:
            r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and r.content:
                try:
                    img = Image.open(BytesIO(r.content))
                except UnidentifiedImageError:
                    continue
                # Alfa kanalı varsa RGBA, yoksa RGB
                img = img.convert("RGBA" if img.mode in ("RGBA", "LA") else "RGB")
                for size, (w, h, quality) in LOGO_SIZES.items():
                    logo_path = os.path.join("logos", size, f"{safe_name}.webp")
                    resized = img.copy()
                    resized.thumbnail((w, h))
                    resized.save(logo_path, format="WEBP", optimize=True, quality=quality)
                LOGO_CACHE[safe_name] = now
                with open(LOGO_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(LOGO_CACHE, f)
                return safe_name
        except Exception:
            continue

    # başarısız
    return ""

def write_m3u_file(filename: str, categorized_links: dict):
    lines = ["#EXTM3U\n"]
    for category in sorted(categorized_links.keys(), key=lambda c: clean_category_name(c)):
        clean_cat = clean_category_name(category)
        links = sorted(categorized_links[category])
        lines.append(f"\n#--- {clean_cat} ---\n")
        for link in links:
            safe_name = download_and_convert_logo(link)
            channel_name = clean_channel_name(link)

            if safe_name:
                logos = {
                    size: f"{RAW_BASE}/logos/{size}/{safe_name}.webp"
                    for size in LOGO_SIZES.keys()
                }
                tvg_logo = f'tvg-logo="{logos["medium"]}"'
                extgrp = f'#EXTGRP:LOGOS ' + " | ".join([f"{k}:{v}" for k, v in logos.items()])
            else:
                tvg_logo = ""
                extgrp = ""

            # #EXTINF
            if tvg_logo:
                lines.append(f'#EXTINF:-1 {tvg_logo}, {channel_name}\n')
            else:
                lines.append(f'#EXTINF:-1 , {channel_name}\n')

            # Ek grup satırı (opsiyonel)
            if extgrp:
                lines.append(extgrp + "\n")

            # Akış URL’i
            lines.append(f"{link}\n")

    with open(filename, "w", encoding="utf-8") as f:
        f.writelines(lines)

def main():
    # Klasörlerde bozuk dosya varsa temizle (açmayı dener, olmazsa siler)
    for size in LOGO_SIZES.keys():
        folder = os.path.join("logos", size)
        for fn in os.listdir(folder):
            if not fn.endswith(".webp"):
                try:
                    os.remove(os.path.join(folder, fn))
                except Exception:
                    pass

    clean_old_logos()

    all_links = set()
    categorized_links = {}

    # raw_lists içindeki tüm .txt dosyalarından linkleri topla
    for filename in os.listdir(RAW_DIR):
        if filename.endswith(".txt"):
            path = os.path.join(RAW_DIR, filename)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("http") and ".m3u8" in line and line not in all_links:
                        all_links.add(line)
                        category = score_category(filename, line)
                        categorized_links.setdefault(category, []).append(line)

    # Ana playlist
    write_m3u_file(OUTPUT_FILE, categorized_links)

    # Kategori bazlı dosyalar
    for category, links in categorized_links.items():
        write_m3u_file(f"{category}.m3u", {category: links})

    # Kategori sözlüğünü kaydet
    with open(CATEGORY_FILE, "w", encoding="utf-8") as f:
        json.dump(CATEGORIES, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
