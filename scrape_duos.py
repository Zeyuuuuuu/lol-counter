#!/usr/bin/env python3
"""Scrape bot-lane duo win rates from data.nerfplz.com.

Stdlib only. Resumable via data/.progress_duos.json + data/.duo_cells/.
Usage: python3 scrape_duos.py
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
CELLS = os.path.join(DATA, ".duo_cells")
PROGRESS = os.path.join(DATA, ".progress_duos.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 30
RETRIES = 3
BASE = "https://data.nerfplz.com"

ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
DUO_HREF_RE = re.compile(r'href="duo-([a-z0-9]+)-([a-z0-9]+)\.html"')
SUP_HREF_RE = re.compile(r'href="champion-([a-z0-9]+)-(?:support|bot)\.html"')


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


def clean(s):
    return TAG_RE.sub(" ", s).replace("&middot;", " ").replace(
        "&#8594;", "").strip()


def parse_ranking(html):
    i = html.find('<tbody id="tb">')
    j = html.find("</tbody>", i)
    tbody = html[i:j]
    rows = []
    for m in ROW_RE.finditer(tbody):
        r = m.group(1)
        href = DUO_HREF_RE.search(r)
        if not href:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(cells) < 6:
            continue
        win = clean(cells[3]).replace("%", "")
        gm = re.search(r"([\d,]+)", clean(cells[5]))
        try:
            rows.append([href.group(1), href.group(2),
                         round(float(win), 1), int(gm.group(1).replace(",", ""))])
        except (ValueError, AttributeError):
            continue
    rows.sort(key=lambda r: -r[2])
    return rows


def parse_champion(html):
    out = {}
    for name, marker in (("best", "Best supports for"),
                         ("worst", "Worst supports for")):
        i = html.find(marker)
        if i < 0:
            return None
        seg = html[i:i + 30000]
        ul = re.search(r'<ul class="mlist">(.*?)</ul>', seg, re.S)
        if not ul:
            return None
        entries = []
        for li in re.findall(r"<li[^>]*>(.*?)</li>", ul.group(1), re.S):
            href = SUP_HREF_RE.search(li)
            txt = re.sub(r"\s+", " ", clean(li))
            wm = re.search(r"([\d.]+)%", txt)
            gm = re.search(r"([\d,]+)\s*games", txt)
            if not href or not wm or not gm:
                continue
            entries.append([href.group(1), round(float(wm.group(1)), 1),
                            int(gm.group(1).replace(",", ""))])
        entries.sort(key=lambda e: e[1], reverse=(name == "best"))
        out[name] = entries
    return out


def save_progress(prog):
    tmp = PROGRESS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(prog, f)
    os.replace(tmp, PROGRESS)


def main():
    os.makedirs(CELLS, exist_ok=True)
    prog = {"ranking_done": False, "ok": [], "missing": [],
            "unknown_slugs": []}
    if os.path.exists(PROGRESS):
        with open(PROGRESS) as f:
            prog.update(json.load(f))
    ok = set(prog["ok"])
    missing = list(prog["missing"])
    unknown = set(prog["unknown_slugs"])

    champions = json.load(open(os.path.join(DATA, "champions.json")))["champions"]
    champ_slugs = set(champions)

    # --- ranking page (once) ---
    ranking_path = os.path.join(CELLS, "__ranking__.json")
    if not prog["ranking_done"] or not os.path.exists(ranking_path):
        time.sleep(random.uniform(0.5, 1.0))
        status, html = fetch_with_retry(f"{BASE}/duos.html")
        if html is None:
            print("failed to fetch duos.html", file=sys.stderr)
            sys.exit(1)
        ranking = parse_ranking(html)
        with open(ranking_path, "w") as f:
            json.dump(ranking, f)
        pm = re.search(r"Patch\s+(\d+(?:\.\d+)*)", html)
        patch = pm.group(1) if pm else ""
        scope_m = re.search(r"(Silver\+[^<]{0,80})", html)
        scope_raw = re.sub(r"\s+", " ", clean(scope_m.group(1))).replace(
            "&middot;", "·") if scope_m else ""
        prog["ranking_done"] = True
        prog["patch"] = patch
        prog["patch_note_raw"] = scope_raw
        save_progress(prog)
    else:
        with open(ranking_path) as f:
            ranking = json.load(f)
        patch = prog.get("patch", "")
        scope_raw = prog.get("patch_note_raw", "")

    for b, s, _, _ in ranking:
        if b not in champ_slugs:
            unknown.add(b)
        if s not in champ_slugs:
            unknown.add(s)

    # --- per-champion pages ---
    slugs = sorted(champions)
    done = 0
    for slug in slugs:
        cell_path = os.path.join(CELLS, f"{slug}.json")
        if slug in ok and os.path.exists(cell_path):
            continue
        ok.discard(slug)
        time.sleep(random.uniform(0.5, 1.0))
        candidates = [slug] + (["monkeyking"] if slug == "wukong" else [])
        html = None
        for cand in candidates:
            status, html = fetch_with_retry(f"{BASE}/champion-{cand}-bot.html")
            if status != 404 and html is not None:
                break
            html = None
        if html is None:
            if slug not in missing:
                missing.append(slug)
            with open(cell_path, "w") as f:
                json.dump(None, f)
        else:
            parsed = parse_champion(html)
            with open(cell_path, "w") as f:
                json.dump(parsed, f)
            if parsed is None:
                if slug not in missing:
                    missing.append(slug)
        ok.add(slug)
        prog["ok"] = sorted(ok)
        prog["missing"] = sorted(missing)
        prog["unknown_slugs"] = sorted(unknown)
        save_progress(prog)
        done += 1
        if done % 25 == 0:
            print(f"progress: {len(ok)}/{len(slugs)} champions, "
                  f"{len(missing)} missing", flush=True)

    by_champion = {}
    champions_ok = 0
    for slug in slugs:
        with open(os.path.join(CELLS, f"{slug}.json")) as f:
            parsed = json.load(f)
        if parsed:
            by_champion[slug] = parsed
            champions_ok += 1

    scraped_at = datetime.now(timezone.utc).isoformat()
    patch_note = (f"nerfplz 自有版本编号（对应 16.21 数据周期）；"
                  f"{scope_raw}" if scope_raw
                  else "nerfplz 自有版本编号（对应 16.21 数据周期）；Silver+ 多地区")
    out = {"meta": {"patch": patch, "patch_note": patch_note,
                    "source": "data.nerfplz.com", "scraped_at": scraped_at,
                    "scope": "bot lane duos only",
                    "ranking_count": len(ranking),
                    "champions_ok": champions_ok,
                    "champions_total": len(slugs),
                    "missing": sorted(missing),
                    "unknown_slugs": sorted(unknown)},
           "ranking": ranking,
           "by_champion": by_champion}
    with open(os.path.join(DATA, "duos.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"DONE patch={patch} ranking_count={len(ranking)} "
          f"champions_ok={champions_ok}/{len(slugs)} "
          f"missing={len(missing)} unknown_slugs={len(unknown)} "
          f"scraped_at={scraped_at}")
    if unknown:
        print("UNKNOWN SLLUGS:", sorted(unknown))


if __name__ == "__main__":
    main()
