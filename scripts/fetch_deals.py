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
import csv
import gzip
import hashlib
import html
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
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
    "Arc B580": 100, "Arc B570": 90,
}
CPU_PERF = {
    "Ryzen 5 5600": 78, "Ryzen 5 5600X": 82, "Ryzen 7 5700X": 90, "Ryzen 7 5800X3D": 112,
    "Ryzen 5 7500F": 100, "Ryzen 5 7600": 104, "Ryzen 5 7600X": 108, "Ryzen 7 7700": 112,
    "Ryzen 7 7800X3D": 140, "Ryzen 5 9600X": 114, "Ryzen 7 9700X": 124,
    "Ryzen 7 9800X3D": 162, "Ryzen 9 9900X": 140, "Ryzen 9 9950X3D": 175,
    "Core i5 12400F": 84, "Core i5 13400F": 92, "Core i5 14400F": 96,
    "Core i5 14600KF": 125, "Core i7 14700K": 150, "Core i7 14700KF": 150,
    "Core Ultra 5 245K": 118, "Core Ultra 5 250KF": 118,
    "Core Ultra 7 265K": 145, "Core Ultra 7 270K": 150,
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


def perf_and_tier(gpu, cpu):
    if not gpu or gpu not in GPU_PERF:
        return None, None
    perf = GPU_PERF[gpu] + 0.3 * CPU_PERF.get(cpu, DEFAULT_CPU_PERF)
    gp = GPU_PERF[gpu]
    tier = "entry" if gp <= 112 else "mid" if gp <= 165 else "high"
    return round(perf, 1), tier


def build_deal(source, key, title, body, url, thread, posted, retailer, extra=None):
    text_all = "%s %s" % (title, body)
    kind = classify(title) or classify(body[:300]) if body else classify(title)
    if not kind:
        return None
    specs = extract_specs(title)
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
    if price < 100 or price > 8000:
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
        row = {"title": "", "link": "", "body": "", "date": ""}
        for child in node:
            name = local(child.tag)
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


def run_rss(src):
    deals = []
    for e in read_feed_entries(fetch(src["url"])):
        ext = first_external_link(e["body"])
        thread = e["link"]
        url = ext or thread
        retailer = retailer_from_url(ext) if ext else retailer_from_text(e["title"])
        posted = parse_date(e["date"]) or now()
        deal = build_deal(src["name"], thread or e["title"], e["title"], strip_tags(e["body"]), url, thread, posted, retailer)
        if deal:
            deals.append(deal)
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
        deal = build_deal(src["name"], pid, "%s %s" % (title, price_text), "%s %s" % (cat, desc), link, None, stamp,
                          src.get("retailer") or row.get("merchant_name") or "", None)
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


class SkipSource(Exception):
    pass


RUNNERS = {"rss": run_rss, "awin_csv": run_awin_csv}


# ---------------------------------------------------------------- merge

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=os.path.join(ROOT, "sources.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "deals.json"))
    args = ap.parse_args()

    conf = load_json(args.sources, {"sources": []})
    previous = load_json(args.out, {"deals": [], "sources": []})
    was_sample = bool(previous.get("sample"))
    old = {} if was_sample else {d["id"]: d for d in previous.get("deals", [])}

    status, fetched = [], []
    for src in conf.get("sources", []):
        if not src.get("enabled", True):
            continue
        entry = {"name": src["name"], "ok": False, "count": 0, "error": ""}
        runner = RUNNERS.get(src.get("type"))
        try:
            if not runner:
                raise SkipSource("unknown source type %r" % src.get("type"))
            deals = runner(src)
            entry.update(ok=True, count=len(deals))
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

    ok_sources = {s["name"] for s in status if s["ok"]}
    stamp = now()
    cutoff = stamp - timedelta(days=KEEP_DAYS)

    merged = {}
    # keep old deals unless their source refreshed a full snapshot, or they are too old
    for d in old.values():
        if d.get("snapshot") and d["source"] in ok_sources:
            continue
        if (parse_date(d.get("posted")) or stamp) < cutoff:
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
            else:
                d["posted"] = prior.get("posted") or d["posted"]
        else:
            d["first_seen"] = iso(stamp)
        merged[d["id"]] = d

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
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print("Wrote %d deals." % len(out["deals"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
