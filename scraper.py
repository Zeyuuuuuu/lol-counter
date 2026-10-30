#!/usr/bin/env python3
"""LOL counter scraper: lolalytics matchup data for all champions x 5 lanes.

Stdlib only. Resumable via data/.progress.json + data/.cells/*.json.
Usage: python3 scraper.py
"""
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CELLS = os.path.join(DATA, ".cells")
PROGRESS = os.path.join(DATA, ".progress.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 30
LANES = ["top", "jungle", "middle", "bottom", "support"]
RETRIES = 3

WR_RE = re.compile(
    r'<div class="text-center text-xs text-green-300"><!--t=[^>]*?-->'
    r'([\d.]+)<!---->%<div class="text-cyan-200">VS</div></div>')
SCRIPT_RE = re.compile(r"<script.*?</script>", re.S | re.I)
ALT_RE = re.compile(r'alt="([^"]+)"')
GAMES_RE = re.compile(r"([\d,]+) Games")


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, r.read().decode("utf-8", errors="replace")


def fetch_with_retry(url):
    """Return (status, html) or (404, None) or (None, None) after retries."""
    for attempt in range(RETRIES + 1):
        try:
            return http_get(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, None
            # retryable
        except Exception:
            pass
        if attempt < RETRIES:
            time.sleep((2 ** attempt) + random.random())
    return None, None


def parse_counters(html, name_to_slug):
    """Return list of (opp_slug, wr, games)."""
    html = SCRIPT_RE.sub("", html)
    rows = []
    for m in WR_RE.finditer(html):
        wr = round(float(m.group(1)), 2)
        seg = html[m.end():m.end() + 2000]
        alt = ALT_RE.search(seg)
        g = GAMES_RE.search(seg)
        if not alt or not g:
            continue
        name = alt.group(1)
        slug = name_to_slug.get(name)
        if slug is None:
            continue
        games = int(g.group(1).replace(",", ""))
        rows.append((slug, wr, games))
    rows.sort(key=lambda r: (r[1], r[0]))
    return [[s, w, g] for s, w, g in rows]


def load_progress():
    if os.path.exists(PROGRESS):
        with open(PROGRESS) as f:
            return json.load(f)
    return {"ok": [], "missing": [], "patch": None, "slugs": {}}


def save_progress(p):
    tmp = PROGRESS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(p, f)
    os.replace(tmp, PROGRESS)


def main():
    os.makedirs(CELLS, exist_ok=True)
    prog = load_progress()
    ok = set(prog.get("ok", []))
    missing = list(prog.get("missing", []))

    # --- metadata ---
    version = fetch_with_retry("https://ddragon.leagueoflegends.com/api/versions.json")[1]
    version = json.loads(version)[0]
    patch = version.rsplit(".", 1)[0]

    zh = json.loads(fetch_with_retry(
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/champion.json")[1])["data"]
    en = json.loads(fetch_with_retry(
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json")[1])["data"]

    champions = {}
    name_to_slug = {}
    slug_to_id = {}
    for cid, info in en.items():
        slug = "wukong" if cid == "MonkeyKing" else cid.lower()
        # DD zh_CN 字段是反的：title=真名（如塔姆），name=称号（如河流之王）
        champions[slug] = {"en": info["name"], "zh": zh[cid]["title"], "alias": zh[cid]["name"]}
        name_to_slug[info["name"]] = slug
        slug_to_id[slug] = cid

    scraped_at = datetime.now(timezone.utc).isoformat()

    # --- champions.json ---
    with open(os.path.join(DATA, "champions.json"), "w") as f:
        json.dump({"patch": patch, "scraped_at": scraped_at,
                   "champions": champions}, f, ensure_ascii=False)

    total_cells = len(champions) * len(LANES)
    done = 0
    for slug in sorted(champions):
        for lane in LANES:
            cell = f"{slug}:{lane}"
            cell_path = os.path.join(CELLS, f"{slug}__{lane}.json")
            if cell in ok and os.path.exists(cell_path):
                continue
            # stale/missing-ok entry: re-check
            if cell in ok:
                ok.discard(cell)
            time.sleep(random.uniform(0.5, 1.0))
            primary = slug
            url = f"https://lolalytics.com/lol/{primary}/counters/?lane={lane}&tier=all"
            status, html = fetch_with_retry(url)
            if status == 404:
                # one fallback: strip special chars from original ID, lowercase
                fallback = re.sub(r"[^a-z0-9]", "", slug_to_id[slug].lower())
                if fallback != primary:
                    url2 = (f"https://lolalytics.com/lol/{fallback}/counters/"
                            f"?lane={lane}&tier=all")
                    time.sleep(random.uniform(0.5, 1.0))
                    status, html = fetch_with_retry(url2)
            if status == 404 or html is None:
                if cell not in missing:
                    missing.append(cell)
                prog["ok"] = sorted(ok)
                prog["missing"] = sorted(missing)
                save_progress(prog)
                print(f"MISSING {cell}", flush=True)
                continue
            rows = parse_counters(html, name_to_slug)
            with open(cell_path, "w") as f:
                json.dump(rows, f)
            ok.add(cell)
            prog["ok"] = sorted(ok)
            prog["missing"] = sorted(missing)
            save_progress(prog)
            done += 1
            if done % 50 == 0:
                print(f"progress: {len(ok)}/{total_cells} ok, {len(missing)} missing",
                      flush=True)

    # --- assemble outputs ---
    ok_cells = 0
    data_all = {}
    lanes_data = {lane: {} for lane in LANES}
    for slug in sorted(champions):
        entry = {}
        for lane in LANES:
            cell_path = os.path.join(CELLS, f"{slug}__{lane}.json")
            if os.path.exists(cell_path):
                with open(cell_path) as f:
                    rows = json.load(f)
                ok_cells += 1
            else:
                rows = []
            entry[lane] = rows
            lanes_data[lane][slug] = rows
        data_all[slug] = entry

    final_at = datetime.now(timezone.utc).isoformat()
    meta = {"patch": patch, "tier": "all", "source": "lolalytics",
            "scraped_at": final_at, "ok_cells": ok_cells,
            "total_cells": total_cells, "missing": sorted(missing)}

    with open(os.path.join(DATA, "counters.json"), "w") as f:
        json.dump({"meta": meta, "data": data_all}, f)
    for lane in LANES:
        with open(os.path.join(DATA, "lanes", f"{lane}.json"), "w") as f:
            json.dump({"meta": meta, "data": lanes_data[lane]}, f)

    # --- self checks ---
    errors = []
    champ_slugs = set(champions)
    tk_top = data_all.get("tahmkench", {}).get("top", [])
    yor = [r for r in tk_top if r[0] == "yorick"]
    if not yor or not (42 <= yor[0][1] <= 44) or yor[0][2] <= 1000:
        errors.append(f"tahmkench/top yorick check failed: {yor[:1]}")
    if not data_all.get("akali", {}).get("middle"):
        errors.append("akali/middle is empty")
    for slug, entry in data_all.items():
        for lane, rows in entry.items():
            if rows:
                bad = [r[0] for r in rows if r[0] not in champ_slugs]
                if bad:
                    errors.append(f"{slug}:{lane} unknown slugs: {bad[:5]}")

    print(f"DONE patch={patch} ok_cells={ok_cells}/{total_cells} "
          f"missing={len(missing)} scraped_at={final_at}")
    if errors:
        print("SELFCHECK ERRORS:", errors)
    else:
        print("SELFCHECK OK")


if __name__ == "__main__":
    os.makedirs(os.path.join(DATA, "lanes"), exist_ok=True)
    main()
