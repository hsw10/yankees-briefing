#!/usr/bin/env python3
"""Fetch the newest five Yankees posts for the local digest."""
from __future__ import annotations

import email.utils
import html as html_lib
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) YankeesBlogDigest/1.0"}

SITES = [
    {"name": "Pinstripe Alley", "url": "https://www.pinstripealley.com/", "feed": "https://www.pinstripealley.com/rss/index.xml", "logo": "https://cdn.vox-cdn.com/uploads/chorus_asset/file/23493847/PinstripeAlley.png", "kind": "feed", "accent": "#d4a72c"},
    {"name": "Bronx Pinstripes", "url": "https://bronxpinstripes.com/", "logo": "https://bronxpinstripes.com/favicon.ico", "kind": "bronx", "accent": "#c9a227"},
    {"name": "MLB Trade Rumors", "url": "https://www.mlbtraderumors.com/new-york-yankees", "feed": "https://www.mlbtraderumors.com/new-york-yankees/feed", "logo": "https://www.mlbtraderumors.com/favicon.ico", "kind": "feed", "accent": "#df3b31"},
    {"name": "Yanks Go Yard", "url": "https://yanksgoyard.com/", "feed": "https://yanksgoyard.com/feed/", "logo": "https://yanksgoyard.com/favicon.ico", "kind": "feed", "accent": "#1c4d8c"},
    {"name": "Official New York Yankees", "url": "https://www.mlb.com/yankees", "feed": "https://www.mlb.com/yankees/feeds/news/rss.xml", "logo": "https://www.mlbstatic.com/team-logos/147.svg", "kind": "feed", "accent": "#0c2340"},
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read().decode("utf-8", "replace")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_lib.unescape(text or ""))).strip()


def date_value(raw: str) -> str:
    raw = (raw or "").strip()
    try:
        return email.utils.parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return raw


def image_from_item(item: ET.Element, desc: str) -> str:
    for el in item.iter():
        tag = el.tag.lower()
        if tag.endswith("thumbnail") or tag.endswith("content"):
            val = el.attrib.get("url") or el.attrib.get("href")
            if val and val.startswith("http"):
                return val
    match = re.search(r"<img[^>]+src=[\"']([^\"']+)", desc or "", re.I)
    return match.group(1) if match else ""


def feed_posts(site: dict) -> list[dict]:
    root = ET.fromstring(fetch(site["feed"]))
    entries = [el for el in root.iter() if el.tag.lower().endswith(("item", "entry"))]
    posts = []
    for item in entries[:5]:
        vals = {}
        for el in list(item):
            key = el.tag.rsplit("}", 1)[-1].lower()
            vals.setdefault(key, el.text or "")
        title = clean(vals.get("title", "Untitled"))
        link = vals.get("link", "")
        if not link:
            for el in list(item):
                if el.tag.lower().endswith("link") and el.attrib.get("href"):
                    link = el.attrib["href"]
                    break
        description = vals.get("description") or vals.get("summary") or vals.get("encoded") or ""
        posts.append({"title": title, "url": link.strip(), "published": date_value(vals.get("pubdate") or vals.get("published") or vals.get("updated") or vals.get("date") or ""), "excerpt": clean(description)[:220], "image": image_from_item(item, description)})
    return posts


def bronx_posts(site: dict) -> list[dict]:
    page = fetch("https://bronxpinstripes.com/articles")
    # Next.js cards: href then an image, category/title and time within the same card.
    chunks = re.findall(r'<a[^>]+href="(/articles/[^"]+)"[^>]*>(.*?)</a>', page, re.S)
    posts = []
    for href, block in chunks:
        title_match = re.findall(r'<h3[^>]*>(.*?)</h3>', block, re.S)
        if not title_match:
            continue
        image_match = re.search(r'<img[^>]+(?:src|srcSet)="([^"]+)', block, re.I)
        time_match = re.search(r'<time[^>]*>(.*?)</time>', block, re.S)
        desc_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        posts.append({"title": clean(title_match[-1]), "url": urllib.parse.urljoin(site["url"], href), "published": clean(time_match.group(1)) if time_match else "", "excerpt": clean(desc_match.group(1))[:220] if desc_match else "", "image": image_match.group(1).replace("&amp;", "&") if image_match else ""})
        if len(posts) == 5:
            break
    if len(posts) < 5:
        raise RuntimeError("Bronx Pinstripes article cards were not parsed")
    return posts


def main() -> None:
    results_by_name, errors = {}, []
    def collect(site: dict) -> dict:
        posts = bronx_posts(site) if site["kind"] == "bronx" else feed_posts(site)
        if len(posts) < 5:
            raise RuntimeError(f"only parsed {len(posts)} posts")
        return {**site, "posts": posts[:5], "status": "ok"}
    with ThreadPoolExecutor(max_workers=len(SITES)) as pool:
        futures = {pool.submit(collect, site): site for site in SITES}
        for future in as_completed(futures):
            site = futures[future]
            try:
                results_by_name[site["name"]] = future.result()
            except Exception as exc:
                errors.append(f"{site['name']}: {exc}")
                results_by_name[site["name"]] = {**site, "posts": [], "status": "error", "error": str(exc)}
    results = [results_by_name[site["name"]] for site in SITES]
    payload = {"refreshedAt": datetime.now().astimezone().isoformat(), "sites": results, "errors": errors}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"sites": len(results), "successful": len(results) - len(errors), "errors": errors}))
    if errors:
        sys.exit(1)

if __name__ == "__main__":
    main()
