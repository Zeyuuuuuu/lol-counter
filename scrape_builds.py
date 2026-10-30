#!/usr/bin/env python3
"""Scrape per-champion per-lane builds from lolalytics build pages.

Stdlib only. Resumable via data/.progress_builds.json + data/.build_cells/.
Requires data/counters.json (for games-weighted win rates).
Usage: python3 scrape_builds.py
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
CELLS = os.path.join(DATA, ".build_cells")
PROGRESS = os.path.join(DATA, ".progress_builds.json")
COUNTERS = os.path.join(DATA, "counters.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 30
LANES = ["top", "jungle", "middle", "bottom", "support"]
RETRIES = 3

SCRIPT_RE = re.compile(r"<script.*?</script>", re.S | re.I)
ITEM_RE = re.compile(r"cdn5\.lolalytics\.com/item\d+/(\d+)\.webp")
RUNE_RE = re.compile(r'<img[^>]*cdn5\.lolalytics\.com/rune\d+/(\d+)\.webp[^>]*>')


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, r.read().decode("utf-8", errors="replace")


def fetch_with_retry(url):
    for attempt in range(RETRIES + 1):
        try:
            return http_get(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, None
        except Exception:
            pass
        if attempt < RETRIES:
            time.sleep((2 ** attempt) + random.random())
    return None, None


def parse_items(html, item_zh, boots_ids):
    start = html.find("Core Build")
    if start < 0:
        return []
    block = html[start:]
    seen = []
    for m in ITEM_RE.finditer(block):
        iid = m.group(1)
        if iid not in seen:
            seen.append(iid)
    non_boots = [i for i in seen if i not in boots_ids]
    return [item_zh.get(i, i) for i in non_boots[:3]]


def parse_runes(html, rune_zh):
    i = html.find("Primary Runes")
    if i < 0:
        return None
    j = html.find("Secondary", i)
    if j < 0:
        return None
    k = html.find("Stat Mods", j)
    primary_block = html[i:j]
    secondary_block = html[j:k if k > 0 else len(html)]

    def selected(block):
        out = []
        for m in RUNE_RE.finditer(block):
            if "grayscale" not in m.group(0):
                rid = m.group(1)
                out.append(rune_zh.get(rid, rid))
        return out

    prim = selected(primary_block)
    sec = selected(secondary_block)
    if len(prim) != 4 or len(sec) != 2:
        return None
    return {"keystone": prim[0], "primary": prim[1:], "secondary": sec}


def weighted_wr(rows):
    tot_g = sum(r[2] for r in rows)
    if not tot_g:
        return None
    return round(sum(r[1] * r[2] for r in rows) / tot_g, 1)


def main():
    if not os.path.exists(COUNTERS):
        print("counters.json not found; run scraper.py first", file=sys.stderr)
        sys.exit(1)
    os.makedirs(CELLS, exist_ok=True)
    prog = {"ok": [], "missing": [], "flagged": []}
    if os.path.exists(PROGRESS):
        with open(PROGRESS) as f:
            prog.update(json.load(f))
    ok = set(prog["ok"])
    missing = list(prog["missing"])
    flagged = list(prog["flagged"])

    counters = json.load(open(COUNTERS))
    patch = counters["meta"]["patch"]

    version = json.loads(
        fetch_with_retry("https://ddragon.leagueoflegends.com/api/versions.json")[1])[0]
    item_zh = json.loads(fetch_with_retry(
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/item.json")[1])["data"]
    item_en = json.loads(fetch_with_retry(
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json")[1])["data"]
    boots_ids = {iid for iid, info in item_en.items() if "Boots" in info["name"]}
    item_zh_names = {iid: info["name"] for iid, info in item_zh.items()}

    rune_trees = json.loads(fetch_with_retry(
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/runesReforged.json")[1])
    rune_zh = {}
    for t in rune_trees:
        for slot in t["slots"]:
            for r in slot["runes"]:
                rune_zh[str(r["id"])] = r["name"]

    champions = json.load(open(os.path.join(DATA, "champions.json")))["champions"]
    slugs = sorted(champions)
    total = len(slugs) * len(LANES)
    slug_to_id = {}
    # rebuild slug->id for fallback
    en_ch = json.loads(fetch_with_retry(
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json")[1])["data"]
    for cid in en_ch:
        slug_to_id["wukong" if cid == "MonkeyKing" else cid.lower()] = cid

    done = 0
    for slug in slugs:
        for lane in LANES:
            cell = f"{slug}:{lane}"
            cell_path = os.path.join(CELLS, f"{slug}__{lane}.json")
            if cell in ok and os.path.exists(cell_path):
                continue
            ok.discard(cell)
            time.sleep(random.uniform(0.5, 1.0))
            url = f"https://lolalytics.com/lol/{slug}/build/?lane={lane}&tier=all"
            status, html = fetch_with_retry(url)
            if status == 404:
                fallback = re.sub(r"[^a-z0-9]", "", slug_to_id[slug].lower())
                if fallback != slug:
                    time.sleep(random.uniform(0.5, 1.0))
                    status, html = fetch_with_retry(
                        f"https://lolalytics.com/lol/{fallback}/build/?lane={lane}&tier=all")
            if status == 404 or html is None:
                if cell not in missing:
                    missing.append(cell)
                with open(cell_path, "w") as f:
                    json.dump(None, f)
                ok.add(cell)
            else:
                html_ns = SCRIPT_RE.sub("", html)
                items = parse_items(html_ns, item_zh_names, boots_ids)
                runes = parse_runes(html_ns, rune_zh)
                if runes is None:
                    with open(cell_path, "w") as f:
                        json.dump(None, f)
                    flag = f"{cell}:runes"
                    if flag not in flagged:
                        flagged.append(flag)
                else:
                    wr = weighted_wr(counters["data"][slug][lane])
                    if wr is None:
                        # 该位置无对局样本：出装/符文为噪声，直接记 null
                        with open(cell_path, "w") as f:
                            json.dump(None, f)
                    else:
                        cell_data = {"wr": wr, "items": items,
                                     "keystone": runes["keystone"],
                                     "primary": runes["primary"],
                                     "secondary": runes["secondary"]}
                        with open(cell_path, "w") as f:
                            json.dump(cell_data, f, ensure_ascii=False)
                ok.add(cell)
            prog["ok"] = sorted(ok)
            prog["missing"] = sorted(missing)
            prog["flagged"] = sorted(flagged)
            tmp = PROGRESS + ".tmp"
            with open(tmp, "w") as f:
                json.dump(prog, f)
            os.replace(tmp, PROGRESS)
            done += 1
            if done % 50 == 0:
                print(f"progress: {len(ok)}/{total} ok, {len(missing)} missing, "
                      f"{len(flagged)} flagged", flush=True)

    data = {}
    ok_cells = 0
    for slug in slugs:
        entry = {}
        for lane in LANES:
            with open(os.path.join(CELLS, f"{slug}__{lane}.json")) as f:
                cell_data = json.load(f)
            entry[lane] = cell_data
            if cell_data is not None:
                ok_cells += 1
        data[slug] = entry

    scraped_at = datetime.now(timezone.utc).isoformat()
    out = {"meta": {"patch": patch, "tier": "all", "source": "lolalytics",
                    "scraped_at": scraped_at,
                    "wr_method": ("games-weighted mean of matchup win rates "
                                  "from counters.json"),
                    "ok_cells": ok_cells, "total_cells": total,
                    "missing": sorted(missing), "flagged": sorted(flagged)},
           "data": data}
    with open(os.path.join(DATA, "builds.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False)

    errors = []
    tk = data.get("tahmkench", {}).get("top")
    if not tk:
        errors.append("tahmkench/top is null")
    else:
        if tk["keystone"] != "不灭之握":
            errors.append(f"keystone={tk['keystone']!r}, expected 不灭之握")
        for need in ["爆破", "复苏之风", "过度生长"]:
            if need not in tk["primary"]:
                errors.append(f"primary missing {need}: {tk['primary']}")
        if not tk["items"] or tk["items"][0] != "心之钢":
            errors.append(f"items[0]={tk['items'][:1]!r}, expected 心之钢")

    print(f"DONE patch={patch} ok_cells={ok_cells}/{total} "
          f"missing={len(missing)} flagged={len(flagged)} scraped_at={scraped_at}")
    if errors:
        print("SELFCHECK ERRORS:", errors)
    else:
        print("SELFCHECK OK")


if __name__ == "__main__":
    main()
