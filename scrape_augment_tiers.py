#!/usr/bin/env python3
"""Scrape augment color tiers (prismatic/gold/silver) from arammayhem.com.

Source: https://arammayhem.com/augments/ (index table, fast) +
        https://arammayhem.com/augments/<slug>/ detail pages for gaps
        (meta description contains "<Name>: <Color> augment, ...").

Merges tier into data/augment_names.json as "tier": "prismatic"|"gold"|"silver".
Name matching is normalized (lowercase, alphanumerics only) to tolerate
apostrophe/spacing differences between sources.

Usage: python3 scrape_augment_tiers.py
"""
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
import html as htm

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
NAMES_PATH = os.path.join(DATA, "augment_names.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 30
BASE = "https://arammayhem.com"


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def page_text(html):
    t = htm.unescape(re.sub(r"<[^>]+>", "|", html))
    return re.sub(r"\|+", "|", t)


def norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


# mayhemmeta 与 arammayhem 的名字差异别名（归一化后）：quest/upgrade 前缀等
ALIASES = {
    "steelyourheart": "queststeelyourheart",
    "urfschampion": "questurfschampion",
    "woogletswitchcap": "questwoogletswitchcap",
}


def lookup_tier(tiers, key):
    n = norm(key)
    if n in tiers:
        return tiers[n]
    if n in ALIASES and ALIASES[n] in tiers:
        return tiers[ALIASES[n]]
    return None


def main():
    names = json.load(open(NAMES_PATH, encoding="utf-8"))
    norm_to_key = {}
    for k in names:
        norm_to_key.setdefault(norm(k), k)
    tiers = {}  # normalized name -> tier

    # --- pass 1: index table (fast) ---
    html = http_get(BASE + "/augments/")
    t = page_text(html)
    rows = re.findall(r"\|([^|]{1,60}?)\|(Gold|Prismatic|Silver)\|([\d.]+)%\|([A-D][+-]?)(?=\|)", t)
    for name, color, _pick, _pt in rows:
        name = name.strip()
        if name and not name.isdigit() and name != "New":
            tiers.setdefault(norm(name), color.lower())
    print(f"pass1 index table: {len(tiers)} tiers", flush=True)

    # --- pass 2: detail pages for gaps ---
    slugs = sorted(set(re.findall(r'href="(/augments/[a-z0-9-]+/)"', html)))
    print(f"detail pages to check: {len(slugs)}", flush=True)
    for i, slug in enumerate(slugs):
        try:
            d = http_get(BASE + slug)
        except Exception as e:
            print(f"  fetch fail {slug}: {e}", flush=True)
            continue
        m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', d)
        if not m:
            m = re.search(r'<meta[^>]+content="([^"]+)"[^>]+name="description"', d)
        if m:
            desc = htm.unescape(m.group(1))
            # 格式 "<Name>: <Color> augment, ..."；名字本身可含冒号（如 Transmute: Prismatic），
            # 用贪婪匹配取最后一个冒号之前的名字
            tm = re.search(r"^(.*):\s*(Gold|Prismatic|Silver)\s+augment", desc, re.I)
            if tm:
                nm = tm.group(1).strip()
                tiers.setdefault(norm(nm), tm.group(2).lower())
        if (i + 1) % 40 == 0:
            print(f"  ...{i + 1}/{len(slugs)}", flush=True)
        time.sleep(random.uniform(0.4, 0.9))

    # --- merge ---
    # 手工核实的映射（arammayhem 页面命名与 mayhemmeta 不一致时用）
    MANUAL = {
        "Steel Your Heart": "gold",          # Quest: Steel Your Heart
        "Urf's Champion": "prismatic",       # Quest: Urf's Champion
        "Wooglet's Witchcap": "prismatic",   # Quest: Wooglet's Witchcap
        "Transmute: Prismatic": "gold",      # 名字带 Prismatic 但颜色是金
        "Upgrade Stormsurge": "gold",        # Upgrade: Stormsurge
        "Upgrade Collector": "silver",
        "Upgrade Death's Dance": "silver",
        "Upgrade Immolate": "silver",
        "Upgrade Infinity Edge": "gold",
        "Upgrade Sheen": "gold",
        "Upgrade Zhonya's": "silver",
    }
    hit, miss = 0, []
    for key in names:
        tr = lookup_tier(tiers, key) or MANUAL.get(key)
        if tr:
            names[key]["tier"] = tr
            hit += 1
        else:
            miss.append(key)
    with open(NAMES_PATH, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"DONE: {hit}/{len(names)} have tier; missing: {len(miss)}")
    for m in miss:
        print("  MISSING:", m)
    from collections import Counter
    print("tier distribution:", Counter(v.get("tier") for v in names.values()))


if __name__ == "__main__":
    main()
