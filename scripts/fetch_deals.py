#!/usr/bin/env python3
"""HeyYoUpgrade fetcher.

Reads sources.json, pulls every enabled source, turns posts and feed rows into
gaming PC and PC bundle deals, and writes deals.json next to index.html.
Uses only the Python standard library, so there is nothing to install.

Usage:
    python scripts/fetch_deals.py
    python scripts/fetch_deals.py --sources other.json --out other_deals.json
"""
import argparse
import base64
import csv
import gzip
import hashlib
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_AGENT = "HeyYoUpgradeBot/1.0 (UK gaming PC deal finder)"
KEEP_DAYS = 14      # community posts older than this are dropped
MAX_DEALS = 300

# Rough relative performance, RTX 5060 = 100. Indicative only, not benchmarks.
GPU_PERF = {
    "RTX 5090": 330, "RTX 5080": 232, "RTX 5070 Ti": 192, "RTX 5070": 146,
    "RTX 5060 Ti": 126, "RTX 5060": 100, "RTX 5050": 80,
    "RTX 4090": 270, "RTX 4080 Super": 205, "RTX 4080": 195,
    "RTX 4070 Ti Super": 170, "RTX 4070 Ti": 150, "RTX 4070 Super": 140,
    "RTX 4070": 120, "RTX 4060 Ti": 105, "RTX 4060": 90,
    "RTX 3070": 100, "RTX 3060 Ti": 88, "RTX 3060": 78, "RTX 3050": 55,
    "RX 9070 XT": 178, "RX 9070": 160, "RX 9060 XT": 118,
    "RX 7900 XTX": 190, "RX 7900 XT": 170, "RX 7800 XT": 135,
    "RX 7700 XT": 118, "RX 7600 XT": 90, "RX 7600": 85, "RX 6600": 70,
    "Arc B580": 100, "Arc B570": 90, "RX 9070 GRE": 150, "RTX 3080": 150, "RTX 3090": 170,
    "RTX 3060 Ti 8GB": 88, "RTX 3050 6GB": 50, "GT 1030": 15, "RX 6700 XT": 105, "RX 6800": 125,
}
CPU_PERF = {
    "Ryzen 5 5600": 78, "Ryzen 5 5600X": 82, "Ryzen 7 5700X": 90, "Ryzen 7 5800X3D": 112,
    "Ryzen 5 7500F": 100, "Ryzen 5 7600": 104, "Ryzen 5 7600X": 108, "Ryzen 7 7700": 112,
    "Ryzen 7 7800X3D": 140, "Ryzen 5 9600X": 114, "Ryzen 7 9700X": 124,
    "Ryzen 7 9800X3D": 162, "Ryzen 9 9900X": 140, "Ryzen 9 9950X3D": 175,
    "Core i5 12400F": 84, "Core i5 13400F": 92, "Core i5 14400F": 96,
    "Core i5 14600KF": 125, "Core i7 14700K": 150, "Core i7 14700KF": 150,
    "Ryzen 5 5500": 75, "Ryzen 5 8400F": 98, "Ryzen 5 8500F": 100, "Core i7 14700": 150,
    "Core Ultra 5 245K": 118, "Core Ultra 5 250KF": 118,
    "Core Ultra 7 265K": 145, "Core Ultra 7 270K": 150,
    "Core i3 12100F": 62, "Core i5 12600K": 100, "Core i5 13600K": 118, "Core i5 13600KF": 118,
    "Core i7 13700K": 140, "Core i7 12700K": 120, "Core i9 14900K": 175, "Core i9 14900KF": 175,
    "Ryzen 5 5600G": 72, "Ryzen 7 5700G": 85, "Ryzen 5 5600X3D": 100, "Ryzen 9 5900X": 120,
    "Ryzen 7 5800X": 100, "Ryzen 9 7900X": 135, "Ryzen 9 7950X": 160, "Ryzen 9 7950X3D": 168,
    "Ryzen 5 8600G": 98, "Ryzen 7 8700G": 110, "Ryzen 9 9950X": 165, "Ryzen 7 7700X": 116,
    "Ryzen 9 7900": 130, "Ryzen 5 9600": 108, "Ryzen 9 5950X": 140, "Ryzen 5 4500": 65, "Ryzen 7 9850X3D": 170,
}
BOARD_TIER = {
    "x870e": 130, "x870": 120, "b850": 105, "b650e": 100, "b650": 92, "a620": 70, "x670e": 125, "x670": 118,
    "z890": 125, "b860": 100, "h810": 60, "z790": 112, "b760": 90, "h770": 85, "h610": 55,
    "b840": 80, "b550": 75, "x570": 90, "a520": 55, "b450": 55, "z690": 100, "b660": 80, "h670": 80,
}
DEFAULT_CPU_PERF = 95

DOMAINS = {
    "overclockers.co.uk": "Overclockers UK", "scan.co.uk": "Scan (3XS)",
    "cclonline.com": "CCL Computers", "box.co.uk": "Box.co.uk", "ebuyer.com": "Ebuyer",
    "pcspecialist.co.uk": "PC Specialist", "chillblast.com": "Chillblast",
    "awd-it.co.uk": "AWD-IT", "novatech.co.uk": "Novatech", "aria.co.uk": "Aria PC",
    "cyberpowersystem.co.uk": "CyberPowerPC UK", "meshcomputers.com": "Mesh Computers",
    "currys.co.uk": "Currys", "argos.co.uk": "Argos", "amazon.co.uk": "Amazon UK",
    "laptopsdirect.co.uk": "Laptops Direct", "very.co.uk": "Very",
    "fiercepc.co.uk": "FiercePC", "inside-tech.co.uk": "Inside-Tech", "quietpc.com": "QuietPC",
    "palicomp.co.uk": "Palicomp", "dell.com": "Dell UK", "ebay.co.uk": "eBay UK",
    "johnlewis.com": "John Lewis", "game.co.uk": "GAME", "pcworld.com": "PC World",
}
SKIP_HOSTS = ("reddit.com", "redd.it", "redditmedia.com", "redditstatic.com", "imgur.com")


# ---------------------------------------------------------------- helpers

def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def strip_tags(markup):
    text = re.sub(r"<[^>]+>", " ", html.unescape(markup or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def host_of(url):
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def retailer_from_url(url):
    host = host_of(url)
    for domain, name in DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return name
    if not host:
        return ""
    label = host.split(".")[-3] if host.endswith(".co.uk") and len(host.split(".")) >= 3 else host.split(".")[0]
    return label.replace("-", " ").title()


def retailer_from_text(text):
    low = text.lower()
    for domain, name in DOMAINS.items():
        stem = domain.split(".")[0]
        if name.lower() in low or (len(stem) > 4 and stem in low):
            return name
    return ""


def first_external_link(markup):
    for href in re.findall(r'href="(https?://[^"]+)"', html.unescape(markup or "")):
        href = html.unescape(href)
        if not any(h in host_of(href) for h in SKIP_HOSTS):
            return href
    return ""


# ---------------------------------------------------------------- parsing

def norm_gpu(text):
    m = re.search(r"\b(?:geforce\s+)?rtx\s*-?\s*(\d{4})\s*(ti\s*super|ti|super)?(?![a-z0-9])", text, re.I)
    if m:
        suffix = re.sub(r"\s+", " ", (m.group(2) or "").lower())
        suffix = {"ti": " Ti", "super": " Super", "ti super": " Ti Super"}.get(suffix, "")
        return "RTX %s%s" % (m.group(1), suffix)
    m = re.search(r"\b(?:radeon\s+)?rx\s*-?\s*(\d{4})\s*(xtx|xt|gre)?(?![a-z0-9])", text, re.I)
    if m:
        return "RX %s%s" % (m.group(1), " " + m.group(2).upper() if m.group(2) else "")
    m = re.search(r"\barc\s*(b\d{3})(?![a-z0-9])", text, re.I)
    if m:
        return "Arc " + m.group(1).upper()
    return None


def norm_cpu(text):
    m = re.search(r"\bcore\s*ultra\s*([3579])\s*(\d{3})([a-z]{0,2})(?![a-z0-9])", text, re.I)
    if m:
        return "Core Ultra %s %s%s" % (m.group(1), m.group(2), m.group(3).upper())
    m = re.search(r"\bryzen\s*([3579])\s*(\d{4,5})\s*(x3d|xt|x|f|g|gt)?(?![a-z0-9])", text, re.I)
    if m:
        return "Ryzen %s %s%s" % (m.group(1), m.group(2), (m.group(3) or "").upper())
    m = re.search(r"\b(?:core\s*)?i([3579])[-\s]*(\d{4,5})([a-z]{0,2})(?![a-z0-9])", text, re.I)
    if m:
        return "Core i%s %s%s" % (m.group(1), m.group(2), m.group(3).upper())
    return None


def norm_ram(text):
    m = re.search(r"(\d{1,3})\s?gb\s*(?:of\s*)?(ddr[45])", text, re.I)
    if m:
        return "%sGB %s" % (m.group(1), m.group(2).upper())
    m = re.search(r"(ddr[45])\D{0,12}(\d{1,3})\s?gb", text, re.I)
    if m:
        return "%sGB %s" % (m.group(2), m.group(1).upper())
    m = re.search(r"\b(8|16|32|48|64|96|128)\s?gb\s*(?:ram|memory)\b", text, re.I)
    if m:
        return "%sGB" % m.group(1)
    return None


def storage_kind(word):
    word = (word or "").lower().replace(".", "")
    return {"nvme": "NVMe", "ssd": "SSD", "m2": "NVMe", "hdd": "HDD"}.get(word, "")


def norm_storage(text):
    m = re.search(r"\b(\d(?:\.\d)?)\s?tb\b\s*(nvme|ssd|m\.?2|hdd)?", text, re.I)
    if m:
        return ("%sTB %s" % (m.group(1), storage_kind(m.group(2)))).strip()
    m = re.search(r"\b(256|480|500|512|960)\s?gb\s*(nvme|ssd|m\.?2)", text, re.I)
    if m:
        return "%sGB %s" % (m.group(1), storage_kind(m.group(2)) or "SSD")
    return None


def extract_specs(text):
    return {"cpu": norm_cpu(text), "gpu": norm_gpu(text), "ram": norm_ram(text), "sto": norm_storage(text)}


def extract_prices(text):
    """Returns (price, was). Looks only at pound amounts."""
    vals = []
    for m in re.finditer(r"£\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?", text):
        whole = int(m.group(1).replace(",", ""))
        pence = int((m.group(2) or "0").ljust(2, "0"))
        vals.append(whole + pence / 100.0)
    vals = [v for v in vals if v >= 1]
    if not vals:
        return None, None
    if len(vals) >= 2 and re.search(r"\b(was|rrp|from|reduced|down from|usually)\b", text, re.I):
        return min(vals), max(vals)
    return vals[0], None


EXCLUDE = re.compile(r"\b(laptop|notebook|macbook|chromebook|steam deck|monitor|keyboard|mouse|headset|console|handheld|nas)\b", re.I)
BUNDLE = re.compile(r"\b(bundle|combo|cpu\s*\+\s*(?:mobo|motherboard)|build kit|pc build|upgrade kit|barebones?)\b", re.I)
PREBUILT = re.compile(r"(pre[-\s]?built|gaming pc|gaming desktop|desktop pc|tower pc|\[pc\]|\[desktop\]|\[system\])", re.I)


def classify(text):
    if EXCLUDE.search(text):
        return None
    if BUNDLE.search(text):
        return "bundle"
    if PREBUILT.search(text):
        return "prebuilt"
    return None


MOBO = re.compile(r"\b(mobo|motherboard|b650|b850|x870|x670|a620|b760|z790|z890|b550)\b", re.I)


def infer_kind(title, specs):
    """No keyword matched. A title naming a CPU and a graphics card is a whole system,
    and a CPU with a motherboard is a bundle. Single parts stay excluded."""
    if EXCLUDE.search(title):
        return None
    if specs.get("cpu") and specs.get("gpu"):
        return "prebuilt"
    if specs.get("cpu") and MOBO.search(title) and not specs.get("gpu"):
        return "bundle"
    return None


PART_RULES = [
    ("psu", re.compile(r"\[psu\]|\bpsu\b|power supply|\b\d{3,4}\s?w\b.{0,30}(?:80\+?|gold|bronze|platinum|modular)", re.I)),
    ("cooling", re.compile(r"\[(?:cooling|cooler|aio)\]|\b(?:cpu cooler|aio|liquid cooler|air cooler|case fans?|thermal paste)\b", re.I)),
    ("case", re.compile(r"\[case\]|\b(?:pc case|gaming case|mid[-\s]?tower|full[-\s]?tower|mini[-\s]?itx case|atx case)\b", re.I)),
    ("motherboard", re.compile(r"\[(?:mobo|motherboard)\]|\b(?:motherboard|mobo)\b", re.I)),
    ("gpu", re.compile(r"\[gpu\]|\b(?:graphics card|geforce|rtx\s*\d{4}|gtx\s*\d{3,4}|radeon|rx\s*\d{4}|arc\s*[ab]\d{3})\b", re.I)),
    ("memory", re.compile(r"\[(?:ram|memory)\]|\b(?:ddr[45]|ram kit|desktop memory)\b", re.I)),
    ("cpu", re.compile(r"\[cpu\]|\b(?:ryzen\s*[3579]|core\s*i[3579]|core\s*ultra|processor)\b", re.I)),
]


def part_cat(title):
    """Single component posts (a graphics card, some RAM) go to the matching section tab."""
    if EXCLUDE.search(title):
        return None
    for cat, rx in PART_RULES:
        if rx.search(title):
            return cat
    return None


def part_perf(cat, title):
    """Rough performance points for a single part, so price-to-performance can be scored.
    Only comparable between parts of the same type. None when the part is not recognised."""
    t = re.sub("[\u2122\u00ae]", "", title or "")
    low = t.lower()
    if cat == "gpu":
        g = norm_gpu(t)
        if not g and re.search(r"\bgt\s*1030\b", low):
            g = "GT 1030"
        return GPU_PERF.get(g)
    if cat == "cpu":
        c = norm_cpu(t)
        return CPU_PERF.get(c) if c else None
    if cat == "memory":
        m = re.search(r"(\d{1,3})\s?gb", t, re.I)
        kit = re.search(r"(\d)\s?x\s?(\d{1,3})\s?gb", t, re.I)
        gb = int(kit.group(1)) * int(kit.group(2)) if kit else int(m.group(1)) if m else None
        gen = 5 if "ddr5" in low else 4 if "ddr4" in low else None
        if not gb or not gen:
            return None
        sp = re.search(r"(\d{4,5})\s?(?:mt/s|mhz|mts)", t, re.I) or re.search(r"\b(?:ddr[45][- ]?)(\d{4,5})\b", t, re.I)
        speed = int(sp.group(1)) if sp else (3200 if gen == 4 else 5600)
        return round(gb * (speed / (6000.0 if gen == 5 else 3200.0)) * (1.0 if gen == 5 else 0.75), 1)
    if cat == "motherboard":
        for chip, pts in BOARD_TIER.items():
            if re.search(r"\b%s" % chip, low):
                return pts + (6 if "wifi" in low or "wi-fi" in low else 0) + (4 if "ddr5" in low else 0)
        return None
    if cat == "psu":
        w = re.search(r"(\d{3,4})\s?w\b", t, re.I)
        if not w:
            return None
        eff = 1.2 if "titanium" in low else 1.1 if "platinum" in low else 1.0 if "gold" in low else 0.9 if "silver" in low else 0.85 if "bronze" in low else 0.8
        return round(int(w.group(1)) * eff * (1.05 if "modular" in low else 1.0) / 5.0, 1)
    if cat == "case":
        pts = 50 + (10 if "glass" in low else 0) + (10 if re.search(r"mesh|flow|airflow", low) else 0)
        f = re.search(r"(\d)\s?(?:x\s?)?(?:fans?|f\b)", low)
        pts += 5 * min(int(f.group(1)), 6) if f else 0
        pts += 5 if re.search(r"mid[- ]?tower|full[- ]?tower", low) else 0
        return pts
    if cat == "cooling":
        size = re.search(r"\b(120|140|240|280|360|420)\b", t)
        aio = re.search(r"\baio\b|liquid|cryo|kraken|water", low)
        if aio and size:
            return {"120": 70, "140": 78, "240": 100, "280": 120, "360": 140, "420": 150}[size.group(1)]
        if aio:
            return 100
        return 60 + (12 if re.search(r"dual|twin|dual-tower|dual tower", low) else 0) + (8 if re.search(r"tower|dark rock|assassin|peerless|phantom", low) else 0)
    return None


def bundle_perf(d):
    cpu = norm_cpu("%s %s" % (d.get("cpu") or "", d.get("title") or ""))
    if not cpu or cpu not in CPU_PERF:
        return None
    low = (d.get("title") or "").lower()
    tier = 0
    for chip, pts in BOARD_TIER.items():
        if re.search(r"\b%s" % chip, low):
            tier = pts
            break
    ram = re.search(r"(\d{1,3})\s?gb", "%s %s" % (d.get("ram") or "", d.get("title") or ""), re.I)
    return round(CPU_PERF[cpu] + 0.3 * tier + (int(ram.group(1)) if ram else 0), 1)


def ensure_perf(d):
    if d.get("perf") is not None:
        return
    if d.get("t") == "part":
        d["perf"] = part_perf(d.get("cat"), d.get("title"))
    elif d.get("t") == "bundle":
        d["perf"] = bundle_perf(d)


def perf_and_tier(gpu, cpu):
    if not gpu or gpu not in GPU_PERF:
        return None, None
    perf = GPU_PERF[gpu] + 0.3 * CPU_PERF.get(cpu, DEFAULT_CPU_PERF)
    gp = GPU_PERF[gpu]
    tier = "entry" if gp <= 112 else "mid" if gp <= 165 else "high"
    return round(perf, 1), tier


def build_deal(source, key, title, body, url, thread, posted, retailer, extra=None, parts=False):
    kind = classify(title) or (classify(body[:300]) if body else None)
    specs = extract_specs(title)
    if not kind:
        kind = infer_kind(title, specs)
    pcat = None
    if not kind and parts:
        pcat = part_cat(title)
        kind = "part" if pcat else None
    if not kind:
        return None
    fallback = extract_specs(body[:600]) if body else {}
    for k, v in fallback.items():
        if not specs.get(k):
            specs[k] = v
    price, was = extract_prices(title)
    if price is None and body:
        price, was = extract_prices(body[:400])
    if price is None:
        return None
    if kind == "prebuilt" and not (specs["gpu"] or specs["cpu"]):
        return None
    if price < (15 if kind == "part" else 100) or price > 8000:
        return None
    perf, tier = perf_and_tier(specs["gpu"], specs["cpu"]) if kind == "prebuilt" else (None, None)
    deal = {
        "id": hashlib.sha1(("%s|%s" % (source, key)).encode()).hexdigest()[:12],
        "source": source,
        "retailer": retailer or "Unknown retailer",
        "url": url,
        "thread": thread or None,
        "t": kind,
        "title": re.sub(r"\s+", " ", title).strip(),
        "cpu": specs["cpu"], "gpu": specs["gpu"], "ram": specs["ram"], "sto": specs["sto"],
        "p": round(price, 2), "was": round(was, 2) if was and was > price else None,
        "del": None, "stock": "unknown", "fin": None,
        "posted": iso(posted),
        "perf": perf, "tier": tier,
    }
    if pcat:
        deal["cat"] = pcat
    if extra:
        deal.update(extra)
    return deal


# ---------------------------------------------------------------- sources

def local(tag):
    return tag.rsplit("}", 1)[-1]


def read_feed_entries(xml_bytes):
    root = ET.fromstring(xml_bytes)
    entries = []
    for node in root.iter():
        if local(node.tag) not in ("entry", "item"):
            continue
        row = {"title": "", "link": "", "body": "", "date": "", "img": ""}
        for child in node:
            name = local(child.tag)
            if name in ("thumbnail", "content", "enclosure") and child.attrib.get("url"):
                if not row["img"] and re.match(r"https?://", child.attrib["url"]):
                    row["img"] = child.attrib["url"]
                continue
            if name == "title":
                row["title"] = (child.text or "").strip()
            elif name == "link":
                row["link"] = child.attrib.get("href") or (child.text or "").strip() or row["link"]
            elif name in ("content", "description", "summary"):
                if not row["body"]:
                    row["body"] = child.text or ""
            elif name in ("updated", "pubDate", "published"):
                if not row["date"]:
                    row["date"] = (child.text or "").strip()
        entries.append(row)
    return entries


INFO = {}


def run_rss(src):
    deals = []
    entries = read_feed_entries(fetch(src["url"]))
    skipped = []
    INFO[src["name"]] = {"seen": len(entries), "examples": skipped}
    for e in entries:
        ext = first_external_link(e["body"])
        thread = e["link"]
        url = ext or thread
        retailer = retailer_from_url(ext) if ext else retailer_from_text(e["title"])
        posted = parse_date(e["date"]) or now()
        deal = build_deal(src["name"], thread or e["title"], e["title"], strip_tags(e["body"]), url, thread, posted, retailer,
                          {"img": e.get("img") or None}, parts=src.get("parts", True))
        if deal:
            deals.append(deal)
        elif len(skipped) < 4:
            skipped.append(re.sub(r"\s+", " ", e["title"]).strip()[:80])
    return deals


def run_awin_csv(src):
    url = os.environ.get(src.get("url_env", ""), "").strip() or src.get("url", "").strip()
    if not url:
        raise SkipSource("no feed URL set (secret %s is empty)" % src.get("url_env", "?"))
    raw = fetch(url).decode("utf-8", errors="replace")
    deals = []
    stamp = now()
    for row in csv.DictReader(io.StringIO(raw)):
        title = row.get("product_name") or row.get("title") or ""
        desc = strip_tags(row.get("description", ""))
        cat = row.get("merchant_category") or row.get("category_name") or ""
        if (row.get("currency") or "GBP").upper() != "GBP":
            continue
        link = row.get("aw_deep_link") or row.get("merchant_deep_link") or row.get("link") or ""
        pid = row.get("aw_product_id") or row.get("merchant_product_id") or link or title
        price_text = "£%s" % (row.get("search_price") or row.get("store_price") or row.get("price") or "").replace("£", "")
        img = ""
        for col in ("merchant_image_url", "aw_image_url", "large_image", "alternate_image", "image_url"):
            if (row.get(col) or "").strip():
                img = row[col].strip()
                break
        deal = build_deal(src["name"], pid, "%s %s" % (title, price_text), "%s %s" % (cat, desc), link, None, stamp,
                          src.get("retailer") or row.get("merchant_name") or "", {"img": img or None}, parts=src.get("parts", False))
        if not deal:
            continue
        try:
            rrp = float(row.get("rrp_price") or 0)
        except ValueError:
            rrp = 0
        if rrp > deal["p"]:
            deal["was"] = round(rrp, 2)
        try:
            deal["del"] = float(row.get("delivery_cost")) if row.get("delivery_cost") not in (None, "") else None
        except ValueError:
            pass
        stock = (row.get("stock_status") or row.get("in_stock") or "").strip().lower()
        if stock in ("1", "true", "yes", "in stock", "in_stock"):
            deal["stock"] = "in"
        elif stock in ("0", "false", "no", "out of stock", "out_of_stock"):
            continue
        deal["snapshot"] = True
        deals.append(deal)
    return deals



# ---------------------------------------------------------------- tracked product pages
PREV = {}
ROBOTS = {}


def robots_allows(url):
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        return True
    rp = ROBOTS.get(parts.netloc)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.parse(fetch("%s://%s/robots.txt" % (parts.scheme, parts.netloc)).decode("utf-8", errors="replace").splitlines())
        except urllib.error.HTTPError as exc:
            rp.parse(["User-agent: *", "Disallow: /"] if exc.code >= 500 else [])
        except Exception:
            rp.parse([])
        ROBOTS[parts.netloc] = rp
    return rp.can_fetch(USER_AGENT, url)


def iter_ld(node):
    if isinstance(node, list):
        for n in node:
            for x in iter_ld(n):
                yield x
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "itemListElement", "item", "mainEntity"):
            if key in node:
                for x in iter_ld(node[key]):
                    yield x


def to_price(value):
    if value in (None, ""):
        return None
    text = re.sub(r"[^\d.,]", "", str(value))
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".") if re.search(r",\d{1,2}$", text) else text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def stock_from(text):
    low = (text or "").lower().replace("_", "").replace(" ", "")
    if not low:
        return "unknown"
    if any(w in low for w in ("outofstock", "soldout", "discontinued", "unavailable")):
        return "out"
    if "limited" in low or "lowstock" in low:
        return "low"
    if any(w in low for w in ("preorder", "backorder", "madetoorder", "builttoorder")):
        return "preorder"
    if "instock" in low or low in ("in", "available"):
        return "in"
    return "unknown"


def meta_map(page):
    out = {}
    for tag in re.findall(r"<meta\b[^>]*>", page, re.I):
        attrs = {}
        for k, v1, v2 in re.findall(r'([\w:.-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', tag):
            attrs[k.lower()] = html.unescape(v1 or v2)
        key = attrs.get("property") or attrs.get("name") or attrs.get("itemprop")
        if key and "content" in attrs:
            out.setdefault(key.lower(), attrs["content"])
    return out


def parse_product_page(page):
    """Reads price, stock, image and name from schema.org JSON-LD, falling back to meta tags."""
    info = {"name": None, "price": None, "currency": None, "stock": "unknown", "image": None}
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except ValueError:
            continue
        for node in iter_ld(data):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if "Product" not in types:
                continue
            info["name"] = info["name"] or node.get("name")
            img = node.get("image")
            if isinstance(img, list) and img:
                img = img[0]
            if isinstance(img, dict):
                img = img.get("url")
            info["image"] = info["image"] or (img if isinstance(img, str) else None)
            offers = node.get("offers")
            for offer in (offers if isinstance(offers, list) else [offers]):
                if not isinstance(offer, dict) or info["price"] is not None:
                    continue
                price = to_price(offer.get("price") or offer.get("lowPrice"))
                if price:
                    info["price"] = price
                    info["currency"] = offer.get("priceCurrency")
                    info["stock"] = stock_from(str(offer.get("availability") or ""))
    meta = meta_map(page)
    if info["price"] is None:
        for key in ("product:price:amount", "og:price:amount", "product:sale_price:amount", "price"):
            if to_price(meta.get(key)):
                info["price"] = to_price(meta[key])
                info["currency"] = info["currency"] or meta.get("product:price:currency") or meta.get("og:price:currency") or meta.get("pricecurrency")
                break
    if info["stock"] == "unknown":
        info["stock"] = stock_from(meta.get("product:availability") or meta.get("og:availability") or meta.get("availability") or "")
    info["name"] = info["name"] or meta.get("og:title")
    info["image"] = info["image"] or meta.get("og:image")
    return info


def run_product_pages(src):
    deals, problems, refreshed, hidden = [], [], 0, 0
    items = src.get("items", [])
    for n, item in enumerate(items):
        url = item["url"]
        did = hashlib.sha1(url.encode()).hexdigest()[:12]
        try:
            if not robots_allows(url):
                raise RuntimeError("blocked by robots.txt")
            info = parse_product_page(fetch(url).decode("utf-8", errors="replace"))
            if not info["price"]:
                raise RuntimeError("no price found on the page")
            if info["currency"] and info["currency"].upper() != "GBP":
                raise RuntimeError("price is not in GBP")
        except Exception as exc:
            problems.append("%s (%s)" % (host_of(url) or "file", str(exc)[:50]))
            if did in PREV:
                deals.append(PREV[did])
            continue
        finally:
            if url.startswith("http") and n < len(items) - 1:
                time.sleep(1.5)
        refreshed += 1
        if info["stock"] == "out":
            hidden += 1
            continue
        title = item.get("title") or info["name"] or ""
        specs = extract_specs("%s %s" % (title, item.get("specs", "")))
        cat = item.get("cat") or "deals"
        kind = "part" if cat != "deals" else (item.get("type") or classify(title) or infer_kind(title, specs) or "prebuilt")
        perf, tier = perf_and_tier(specs["gpu"], specs["cpu"]) if kind == "prebuilt" else (None, None)
        prior = PREV.get(did, {})
        deals.append({
            "id": did, "source": src["name"], "retailer": item.get("retailer") or retailer_from_url(url) or "Unknown retailer",
            "url": url, "thread": None, "t": kind, "title": re.sub(r"\s+", " ", title).strip(),
            "cpu": specs["cpu"], "gpu": specs["gpu"], "ram": specs["ram"], "sto": specs["sto"],
            "p": round(info["price"], 2), "was": None,
            "del": item.get("delivery", prior.get("del")), "stock": item.get("stock") or (info["stock"] if info["stock"] != "unknown" else prior.get("stock", "unknown")),
            "fin": None, "posted": iso(now()), "perf": perf, "tier": tier,
            "img": info["image"] or item.get("img") or prior.get("img"),
            "note": item.get("note", ""), "snapshot": True,
            "cat": cat, "rank": item.get("rank"), "rank_by": item.get("rank_by"), "verified": iso(now()),
        })
    if items and not refreshed:
        raise RuntimeError("could not read any tracked page: %s" % "; ".join(problems[:3]))
    note = "Refreshed %d of %d tracked pages." % (refreshed, len(items))
    if hidden:
        note += " %d out of stock and hidden." % hidden
    if problems:
        note += " Could not read: %s." % "; ".join(problems[:3])
    INFO[src["name"]] = {"note": note}
    return deals


def walk_jsonld(node, out):
    if isinstance(node, list):
        for x in node:
            walk_jsonld(x, out)
    elif isinstance(node, dict):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if "Product" in types:
            out.append(node)
        for v in node.values():
            if isinstance(v, (list, dict)):
                walk_jsonld(v, out)


def run_jsonld(src):
    """Reads schema.org Product data embedded in a retailer category page.
    Works only where the page puts products in its HTML. Pages that build their
    list with JavaScript show up as 0 deals."""
    url = src["url"]
    if not robots_allows(url):
        raise SkipSource("the site's robots.txt does not allow automated reads of this page")
    page = fetch(url).decode("utf-8", errors="replace")
    products = []
    blocks = re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, flags=re.S | re.I)
    for raw in blocks:
        try:
            walk_jsonld(json.loads(raw.strip()), products)
        except ValueError:
            continue
    INFO[src["name"]] = {"seen": len(products), "examples": []}
    deals, stamp = [], now()
    for prod in products:
        offers = prod.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = offers.get("price") or offers.get("lowPrice")
        if price in (None, "") or (offers.get("priceCurrency") or "GBP").upper() != "GBP":
            continue
        avail = str(offers.get("availability") or "")
        if "OutOfStock" in avail or "Discontinued" in avail:
            continue
        link = prod.get("url") or offers.get("url") or url
        if link.startswith("/"):
            parts = urlparse(url)
            link = "%s://%s%s" % (parts.scheme, parts.netloc, link)
        img = prod.get("image")
        if isinstance(img, list):
            img = img[0] if img else ""
        if isinstance(img, dict):
            img = img.get("url", "")
        name = prod.get("name") or ""
        deal = build_deal(src["name"], link, "%s £%s" % (name, price), prod.get("description") or "", link, None, stamp,
                          src.get("retailer") or retailer_from_url(link), {"img": img or None})
        if not deal:
            if len(INFO[src["name"]]["examples"]) < 4:
                INFO[src["name"]]["examples"].append(name[:80])
            continue
        deal["stock"] = "in" if "InStock" in avail else "unknown"
        deal["snapshot"] = True
        deals.append(deal)
    return deals


def itemlist_products(node, out):
    """Collects Product objects from schema.org ItemList / Product markup, in page order."""
    if isinstance(node, list):
        for x in node:
            itemlist_products(x, out)
    elif isinstance(node, dict):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if "Product" in types:
            out.append(node)
            return
        if "ListItem" in types and isinstance(node.get("item"), dict):
            itemlist_products(node["item"], out)
            return
        for v in node.values():
            if isinstance(v, (list, dict)):
                itemlist_products(v, out)


def run_category_pages(src):
    """Top N products from each retailer's component category page, in the shop's own
    order (Recommended / Most Popular). A page that cannot be read keeps its previous
    results, so a tab never goes empty because one shop had a bad minute."""
    top = int(src.get("top", 10))
    deals, problems, read = [], [], 0
    pages = src.get("pages", [])
    for n, pg in enumerate(pages):
        url, cat = pg["url"], pg["cat"]
        try:
            if not robots_allows(url):
                raise RuntimeError("robots.txt")
            html = fetch(url).decode("utf-8", errors="replace")
            found = []
            for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, flags=re.S | re.I):
                try:
                    itemlist_products(json.loads(raw.strip()), found)
                except ValueError:
                    continue
            got = []
            for prod in found:
                offers = prod.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                price = to_price(offers.get("price") or offers.get("lowPrice"))
                link = prod.get("url") or offers.get("url")
                name = prod.get("name") or ""
                if not (price and link and name):
                    continue
                if (offers.get("priceCurrency") or "GBP").upper() != "GBP":
                    continue
                if re.search(r"OutOfStock|Discontinued", str(offers.get("availability") or "")):
                    continue
                if re.search(r"laptop|sodimm|notebook", name, re.I):
                    continue
                if link.startswith("/"):
                    u = urlparse(url)
                    link = "%s://%s%s" % (u.scheme, u.netloc, link)
                img = prod.get("image")
                img = img[0] if isinstance(img, list) and img else img
                img = img.get("url") if isinstance(img, dict) else img
                got.append((name, price, link, img))
            if not got:
                raise RuntimeError("no products readable (page may be built by JavaScript)")
            read += 1
            for rank, (name, price, link, img) in enumerate(got[:top], 1):
                did = hashlib.sha1(link.encode()).hexdigest()[:12]
                prior = PREV.get(did, {})
                deals.append({
                    "id": did, "source": src["name"], "retailer": pg.get("retailer") or retailer_from_url(link) or "Unknown retailer",
                    "url": link, "thread": None, "t": "part", "cat": cat, "title": re.sub(r"\s+", " ", name).strip(),
                    "cpu": None, "gpu": None, "ram": None, "sto": None, "p": round(price, 2), "was": prior.get("was"),
                    "del": None, "stock": "in", "fin": None, "posted": iso(now()), "perf": None, "tier": None,
                    "img": img or prior.get("img"), "note": "", "snapshot": True,
                    "rank": rank, "rank_by": pg.get("rank_by") or "Recommended", "page": url, "verified": iso(now()),
                })
        except Exception as exc:
            problems.append("%s %s (%s)" % (host_of(url), cat, str(exc)[:45]))
            deals.extend(d for d in PREV.values() if d.get("source") == src["name"] and d.get("page") == url)
        finally:
            if n < len(pages) - 1:
                time.sleep(1.5)
    if pages and not read:
        INFO[src["name"]] = {"note": "No page could be read yet. Showing the last saved lists. Problems: %s." % "; ".join(problems[:3])}
    else:
        INFO[src["name"]] = {"note": "Read %d of %d category pages.%s" % (read, len(pages), (" Could not read: %s." % "; ".join(problems[:4])) if problems else "")}
    return deals


def run_reddit_api(src):
    """r/buildapcsalesuk through Reddit's official API (free for small, non-commercial use).
    Needs two repository secrets, REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET."""
    cid, secret = os.environ.get("REDDIT_CLIENT_ID", "").strip(), os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
    if not (cid and secret):
        raise SkipSource("add the REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET secrets (see SETUP.md)")
    auth = base64.b64encode(("%s:%s" % (cid, secret)).encode()).decode()
    req = urllib.request.Request("https://www.reddit.com/api/v1/access_token", data=b"grant_type=client_credentials",
                                 headers={"User-Agent": USER_AGENT, "Authorization": "Basic " + auth})
    with urllib.request.urlopen(req, timeout=30) as resp:
        token = json.loads(resp.read().decode()).get("access_token")
    if not token:
        raise RuntimeError("Reddit did not give an access token. Check the two secrets.")
    sub = src.get("subreddit", "buildapcsalesuk")
    req = urllib.request.Request("https://oauth.reddit.com/r/%s/new?limit=100&raw_json=1" % sub,
                                 headers={"User-Agent": USER_AGENT, "Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        posts = [c["data"] for c in json.loads(resp.read().decode()).get("data", {}).get("children", [])]
    skipped = []
    INFO[src["name"]] = {"seen": len(posts), "examples": skipped}
    deals = []
    for d in posts:
        if d.get("stickied") or d.get("removed_by_category"):
            continue
        title = d.get("title", "")
        thread = "https://www.reddit.com" + d.get("permalink", "")
        link = d.get("url_overridden_by_dest") or d.get("url") or ""
        if not link.startswith("http") or "reddit.com" in host_of(link):
            link = first_external_link(html.escape(d.get("selftext", ""))) or thread
        retailer = retailer_from_url(link) if link != thread else retailer_from_text(title)
        retailer = retailer or retailer_from_text(title)
        deal = build_deal(src["name"], thread, title, d.get("selftext", ""), link, thread,
                          datetime.fromtimestamp(d.get("created_utc", 0), timezone.utc), retailer, None, parts=True)
        if deal:
            deals.append(deal)
        elif len(skipped) < 4:
            skipped.append(title[:80])
    return deals


def _first_list(node):
    """The API's envelope is not documented, so find the first list of objects in the reply."""
    if isinstance(node, list):
        return node if node and isinstance(node[0], dict) else []
    if isinstance(node, dict):
        for key in ("data", "threads", "items", "results"):
            if key in node:
                got = _first_list(node[key])
                if got:
                    return got
        for v in node.values():
            got = _first_list(v)
            if got:
                return got
    return []


def _text(v):
    if isinstance(v, dict):
        return str(v.get("name") or v.get("title") or v.get("display") or "")
    return str(v or "")


def _image(v):
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for k in ("uri", "url", "src", "path"):
            if isinstance(v.get(k), str):
                return v[k]
        base = v.get("base_uri") or v.get("base") or ""
        name = v.get("name") or v.get("file") or ""
        return (base + name) if base and name else ""
    return ""


def run_pepper_api(src):
    """Hottest deals from the documented Pepper Public API v2 (the platform behind HotUKDeals).
    The docs do not say how access works, so the first run shows whether it is open.
    One search per section, a couple of seconds apart, sorted by temperature."""
    base = src.get("base", "https://www.hotukdeals.com/rest_api/v2").rstrip("/")
    queries = src.get("queries", [])
    top = int(src.get("top", 10))
    deals, problems, read = [], [], 0
    stamp = now()
    for n, q in enumerate(queries):
        cat = q["cat"]
        url = "%s/thread/search?%s" % (base, urllib.parse.urlencode({"query": q["query"], "order_by": "hot", "limit": 30}))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                rows = _first_list(json.loads(resp.read().decode("utf-8", errors="replace")))
            if not rows:
                raise RuntimeError("reply had no threads")
            read += 1
            rank = 0
            for t in rows:
                if t.get("is_expired") or t.get("expired"):
                    continue
                exp = t.get("expiry_date")
                if isinstance(exp, (int, float)) and exp and exp < stamp.timestamp():
                    continue
                title = _text(t.get("title"))
                try:
                    price = float(t.get("price"))
                except (TypeError, ValueError):
                    continue
                link = t.get("link_uri") or t.get("visit_uri") or t.get("deal_uri") or t.get("short_uri") or ""
                thread = t.get("deal_uri") or t.get("short_uri") or link
                if not (title and link.startswith("http")):
                    continue
                merchant = _text(t.get("merchant_name_display") or t.get("merchant")) or retailer_from_url(link) or "Unknown retailer"
                sub = t.get("submitted")
                posted = datetime.fromtimestamp(sub, timezone.utc) if isinstance(sub, (int, float)) and sub else stamp
                extra = {"img": _image(t.get("image")) or None, "note": "HotUKDeals temperature %s" % t.get("temperature_rating") if t.get("temperature_rating") is not None else ""}
                if cat == "deals":
                    deal = build_deal(src["name"], thread, "%s \u00a3%s" % (title, price), "", link, thread, posted, merchant, extra)
                    if not deal:
                        continue
                else:
                    if price < 15 or price > 8000:
                        continue
                    rank += 1
                    if rank > top:
                        break
                    deal = {"id": hashlib.sha1(("%s|%s" % (src["name"], thread)).encode()).hexdigest()[:12], "source": src["name"],
                            "retailer": merchant, "url": link, "thread": thread, "t": "part", "cat": cat,
                            "title": re.sub(r"\s+", " ", title).strip(), "cpu": None, "gpu": None, "ram": None, "sto": None,
                            "p": round(price, 2), "was": None, "del": None, "stock": "unknown", "fin": None, "posted": iso(posted),
                            "perf": None, "tier": None, "rank": rank, "rank_by": "Hottest on HotUKDeals", "verified": iso(now())}
                    deal.update(extra)
                    try:
                        nb = float(t.get("next_best_price"))
                        if nb > price:
                            deal["was"] = round(nb, 2)
                    except (TypeError, ValueError):
                        pass
                deal["snapshot"] = True
                deal["page"] = "pepper:" + cat
                deals.append(deal)
        except urllib.error.HTTPError as exc:
            problems.append("%s (HTTP %s)" % (cat, exc.code))
            deals.extend(d for d in PREV.values() if d.get("source") == src["name"] and d.get("page") == "pepper:" + cat)
        except Exception as exc:
            problems.append("%s (%s)" % (cat, str(exc)[:40]))
            deals.extend(d for d in PREV.values() if d.get("source") == src["name"] and d.get("page") == "pepper:" + cat)
        finally:
            if n < len(queries) - 1:
                time.sleep(2)
    if queries and not read:
        raise RuntimeError("API did not answer: %s. It may need credentials the docs do not describe." % "; ".join(problems[:3]))
    INFO[src["name"]] = {"note": "Read %d of %d searches.%s" % (read, len(queries), (" Problems: %s." % "; ".join(problems[:4])) if problems else "")}
    return deals


def run_shopify(src):
    """Small UK shops built on Shopify publish their catalogue as JSON at
    /collections/<name>/products.json. No scraping of page layouts needed.
    Each shop: {"retailer", "base", "collections": [{"handle", "cat", "rank_by"}]}"""
    top = int(src.get("top", 10))
    deals, problems, read = [], [], 0
    jobs = [(shop, col) for shop in src.get("shops", []) for col in shop.get("collections", [])]
    for n, (shop, col) in enumerate(jobs):
        base = shop["base"].rstrip("/")
        page = "%s/collections/%s" % (base, col["handle"])
        try:
            if not robots_allows(page + "/products.json"):
                raise RuntimeError("robots.txt")
            data = json.loads(fetch(page + "/products.json?limit=60").decode("utf-8", errors="replace"))
            products = data.get("products") or []
            if not products:
                raise RuntimeError("no products in reply")
            read += 1
            rank = 0
            for pr in products:
                variants = [v for v in pr.get("variants", []) if v.get("available", True)]
                if not variants:
                    continue
                v = variants[0]
                try:
                    price = float(v.get("price"))
                except (TypeError, ValueError):
                    continue
                title = pr.get("title") or ""
                if not title or price < 15 or re.search(r"laptop|sodimm|notebook", title, re.I):
                    continue
                link = "%s/products/%s" % (base, pr.get("handle"))
                imgs = pr.get("images") or []
                img = imgs[0].get("src") if imgs and isinstance(imgs[0], dict) else None
                try:
                    cmp_at = float(v.get("compare_at_price")) if v.get("compare_at_price") else None
                except (TypeError, ValueError):
                    cmp_at = None
                cat = col["cat"]
                if cat == "deals":
                    deal = build_deal(src["name"], link, "%s \u00a3%s" % (title, price), strip_tags(pr.get("body_html", ""))[:400], link, None, now(),
                                      shop["retailer"], {"img": img})
                    if not deal:
                        continue
                    if cmp_at and cmp_at > price:
                        deal["was"] = round(cmp_at, 2)
                else:
                    rank += 1
                    if rank > top:
                        break
                    deal = {"id": hashlib.sha1(link.encode()).hexdigest()[:12], "source": src["name"], "retailer": shop["retailer"], "url": link,
                            "thread": None, "t": "part", "cat": cat, "title": re.sub(r"\s+", " ", title).strip(), "cpu": None, "gpu": None,
                            "ram": None, "sto": None, "p": round(price, 2), "was": round(cmp_at, 2) if cmp_at and cmp_at > price else None,
                            "del": None, "stock": "in", "fin": None, "posted": iso(now()), "perf": None, "tier": None, "img": img, "note": "",
                            "rank": rank, "rank_by": col.get("rank_by") or "Shop order"}
                deal.update(snapshot=True, page=page, verified=iso(now()))
                deals.append(deal)
        except Exception as exc:
            problems.append("%s %s (%s)" % (shop["retailer"], col["handle"], str(exc)[:40]))
            deals.extend(d for d in PREV.values() if d.get("source") == src["name"] and d.get("page") == page)
        finally:
            if n < len(jobs) - 1:
                time.sleep(1.5)
    if jobs and not read:
        raise RuntimeError("no shop answered: %s" % "; ".join(problems[:3]))
    INFO[src["name"]] = {"note": "Read %d of %d collections.%s" % (read, len(jobs), (" Problems: %s." % "; ".join(problems[:4])) if problems else "")}
    return deals


class SkipSource(Exception):
    pass


RUNNERS = {"rss": run_rss, "awin_csv": run_awin_csv, "product_pages": run_product_pages, "jsonld": run_jsonld, "category_pages": run_category_pages, "reddit_api": run_reddit_api, "pepper_api": run_pepper_api, "shopify_json": run_shopify}


# ---------------------------------------------------------------- merge

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_feed(deals, path):
    """feed.xml: new deals and fresh price drops, for any RSS reader."""
    from xml.sax.saxutils import escape
    repo = os.environ.get("GITHUB_REPOSITORY", "daneloldane/heyyoupgrade")
    owner, name = repo.split("/", 1)
    site = "https://%s.github.io/%s/" % (owner.lower(), name)
    cutoff = now() - timedelta(hours=48)
    picks = []
    for d in deals:
        dropped = parse_date(d.get("dropped_at"))
        fresh = parse_date(d.get("first_seen"))
        save = round((1 - d["p"] / d["was"]) * 100) if d.get("was") and d["was"] > d["p"] else 0
        if (dropped and dropped > cutoff) or (d.get("t") != "part" and fresh and fresh > cutoff) or save >= 20:
            picks.append((dropped or fresh or now(), save, d))
    picks.sort(key=lambda x: x[0], reverse=True)
    items = []
    for when, save, d in picks[:40]:
        label = "Price drop" if d.get("dropped_at") and (parse_date(d["dropped_at"]) or now()) > cutoff else ("%d%% off" % save if save >= 20 else "New")
        title = "%s: %s \u00a3%.2f at %s" % (label, d["title"][:110], d["p"], d["retailer"])
        items.append("<item><title>%s</title><link>%s</link><guid isPermaLink=\"false\">%s-%s</guid><pubDate>%s</pubDate><description>%s</description></item>" % (
            escape(title), escape(d["url"]), d["id"], d["p"], when.strftime("%a, %d %b %Y %H:%M:%S +0000"),
            escape("%s at %s for \u00a3%.2f. Check the shop page before you buy." % (d["title"], d["retailer"], d["p"]))))
    xml = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>HeyYoUpgrade deals</title><link>%s</link>'
           '<description>New UK gaming PC and PC part deals and price drops.</description>%s</channel></rss>\n') % (site, "".join(items))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(xml)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=os.path.join(ROOT, "sources.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "deals.json"))
    args = ap.parse_args()

    conf = load_json(args.sources, {"sources": []})
    previous = load_json(args.out, {"deals": [], "sources": []})
    was_sample = bool(previous.get("sample"))
    old = {} if was_sample else {d["id"]: d for d in previous.get("deals", [])}
    PREV.update(old)
    prev_status = {s["name"]: s for s in previous.get("sources", [])}
    configured = {s["name"] for s in conf.get("sources", []) if s.get("enabled", True)}

    status, fetched, refreshed = [], [], set()
    for src in conf.get("sources", []):
        if not src.get("enabled", True):
            continue
        last = parse_date(prev_status.get(src["name"], {}).get("checked"))
        if (src.get("hourly") and last and not was_sample and now() - last < timedelta(minutes=50)
                and os.environ.get("GITHUB_EVENT_NAME") == "schedule"):
            status.append(prev_status[src["name"]])
            print("%-28s not due this run" % src["name"])
            continue
        entry = {"name": src["name"], "ok": False, "count": 0, "error": ""}
        runner = RUNNERS.get(src.get("type"))
        try:
            if not runner:
                raise SkipSource("unknown source type %r" % src.get("type"))
            deals = runner(src)
            entry.update(ok=True, count=len(deals))
            refreshed.add(src["name"])
            entry["checked"] = iso(now())
            entry.update(INFO.get(src["name"], {}))
            fetched.extend(deals)
        except SkipSource as exc:
            entry["error"] = "Skipped: %s" % exc
            entry["skipped"] = True
        except urllib.error.HTTPError as exc:
            entry["error"] = "HTTP %s" % exc.code
        except Exception as exc:  # keep going, record the problem
            entry["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:120])
        status.append(entry)
        print("%-28s %s %s" % (src["name"], "ok" if entry["ok"] else "FAILED", entry["error"] or "%d deals" % entry["count"]))

    ok_sources = refreshed
    stamp = now()
    cutoff = stamp - timedelta(days=KEEP_DAYS)

    merged = {}
    # keep old deals unless their source refreshed a full snapshot, or they are too old
    for d in old.values():
        if d.get("snapshot"):
            if d["source"] in ok_sources or d["source"] not in configured:
                continue
        elif (parse_date(d.get("posted")) or stamp) < cutoff:
            continue
        merged[d["id"]] = d

    for d in fetched:
        prior = old.get(d["id"])
        if prior:
            d["first_seen"] = prior.get("first_seen") or prior.get("posted")
            if prior["p"] > d["p"]:
                d["prev_p"], d["dropped_at"] = prior["p"], iso(stamp)
            elif prior.get("prev_p") and prior.get("prev_p") > d["p"]:
                d["prev_p"], d["dropped_at"] = prior["prev_p"], prior.get("dropped_at")
            if not d.get("snapshot"):
                d["posted"] = prior["posted"]
            elif prior["p"] != d["p"]:
                d["posted"] = iso(stamp)
            else:
                d["posted"] = prior.get("posted") or d["posted"]
            if not d.get("was") and prior.get("was") and prior["p"] == d["p"]:
                d["was"] = prior["was"]
        else:
            d["first_seen"] = iso(stamp)
        merged[d["id"]] = d

    today = stamp.strftime("%Y-%m-%d")
    keep_from = (stamp - timedelta(days=90)).strftime("%Y-%m-%d")
    fetched_ids = {f["id"] for f in fetched}
    for d in merged.values():
        ensure_perf(d)
        hist = [list(x) for x in (old.get(d["id"], {}).get("ph") or d.get("ph") or []) if x[0] >= keep_from]
        if d["id"] in fetched_ids or not hist:
            last = hist[-1] if hist else None
            if last and last[0] == today:
                last[1] = min(last[1], d["p"])
            elif not last or abs(last[1] - d["p"]) > 0.004 or (stamp.date() - datetime.strptime(last[0], "%Y-%m-%d").date()).days >= 3:
                hist.append([today, d["p"]])
        d["ph"] = hist

    deals = sorted(merged.values(), key=lambda d: d["posted"], reverse=True)[:MAX_DEALS]

    if was_sample and not deals:
        # nothing real yet, keep showing the example data but report source health
        out = dict(previous)
        out["sources"] = status
    else:
        out = {"sample": False, "updated": previous.get("updated") or iso(stamp), "sources": status, "deals": deals}

    comparable = lambda o: json.dumps({"s": o.get("sample"), "src": o.get("sources"), "d": o.get("deals")}, sort_keys=True)
    if comparable(out) == comparable(previous):
        print("No changes.")
        return 0
    out["updated"] = iso(stamp)
    try:
        write_feed(out["deals"], os.path.join(os.path.dirname(os.path.abspath(args.out)), "feed.xml"))
    except Exception as exc:
        print("feed.xml not written: %s" % exc)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print("Wrote %d deals." % len(out["deals"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
