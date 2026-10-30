#!/usr/bin/env python3
"""抓取 mayhemmeta.com 海克斯大乱斗（ARAM: Mayhem）数据。

mayhemmeta 只有全球数据，无地区切换。
patch 从首页 <option selected> 实时解析，不写死。

输出 data/mayhem.json：
{"meta": {"patch","patch_display","source":"mayhemmeta.com","mode":"aram_mayhem",
          "region":"world","scraped_at"},
 "ranking": [[slug,胜率,登场率,对局数,排名,分段], ...],   # 胜率降序
 "by_champion": {slug: {"rank","tier","winrate","pickrate","games",
                        "top_augments":[{"name","pick","win","diff"}, ...]}}}
top_augments 按胜率降序（页面已排好，100+ 对局过滤）。

173 个英雄页，礼貌间隔 1.2s，全程约 4 分钟。
"""
import json
import re
import sys
import time
import html as htmllib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/120.0 Safari/537.36")
BASE = "https://mayhemmeta.com"

# mayhemmeta slug -> 本站 slug
SLUG_FIX = {"monkeyking": "wukong"}

MIN_CHAMPS = 160


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def text_of(fragment):
    t = re.sub(r"<[^>]+>", "|", fragment)
    t = htmllib.unescape(t)
    return re.sub(r"\|+", " | ", t)


def parse_home():
    page = fetch(BASE + "/")
    m = re.search(
        r'<option value="([\d.]+)" selected="">Patch <!-- -->([\d.]+)</option>',
        page)
    if not m:
        raise RuntimeError("首页解析 patch 失败")
    patch, patch_display = m.group(1), m.group(2)
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S)
    rows = []
    for t in trs:
        if "/champions/" not in t:
            continue
        sm = re.search(r"/champions/([a-z0-9'\.]+)", t)
        if not sm:
            continue
        slug = SLUG_FIX.get(sm.group(1), sm.group(1))
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", t, re.S)
        clean = [htmllib.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in cells]
        # [#, 英雄名, 分段, 胜率, 登场率, ...]
        rank = int(clean[0])
        tier = clean[2]
        winrate = float(clean[3].replace("%", "").strip())
        pickrate = float(clean[4].replace("%", "").strip())
        rows.append((slug, rank, tier, winrate, pickrate))
    if len(rows) < MIN_CHAMPS:
        raise RuntimeError("首页英雄行仅 %d，低于下限" % len(rows))
    return patch, patch_display, rows


def parse_champion(slug, mayhem_slug):
    page = fetch("%s/champions/%s" % (BASE, mayhem_slug))
    tx = text_of(page)
    head = tx[:tx.find("Win-Rate Rank")] if "Win-Rate Rank" in tx else tx
    ranks = re.findall(r"#\s*\|\s*(\d+)", head)
    rank = int(ranks[-1]) if ranks else None
    m = re.search(r"Win-Rate Rank\s*\|\s*([\d.]+)\s*\|\s*%", tx)
    winrate = float(m.group(1)) if m else None
    m = re.search(r"Win Rate\s*\|\s*([\d.]+)\s*\|\s*%", tx)
    pickrate = float(m.group(1)) if m else None
    m = re.search(r"Pick Rate\s*\|\s*([\d,]+)\s*\|\s*Games", tx)
    games = int(m.group(1).replace(",", "")) if m else None
    if winrate is None or games is None:
        raise RuntimeError("头部胜率/对局数解析失败")

    # Best Augments 表
    idx = page.find("Best Augments")
    augments = []
    if idx >= 0:
        seg = page[idx:idx + 20000]
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", seg, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) != 3:
                continue
            name = htmllib.unescape(
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", tds[0]))).strip()
            if not name or name.lower() == "augment":
                continue
            pick = float(re.sub(r"[^\d.]", "", tds[1]) or 0)
            wm = re.search(r"([\d.]+)\s*%",
                           htmllib.unescape(re.sub(r"<[^>]+>", "", tds[2])))
            dm = re.search(r"\(\s*([+-])\s*([\d.]+)\s*\)",
                           htmllib.unescape(re.sub(r"<[^>]+>", "", tds[2])))
            if not wm:
                continue
            win = float(wm.group(1))
            diff = (1 if dm.group(1) == "+" else -1) * float(dm.group(2)) \
                if dm else 0.0
            augments.append({"name": name, "pick": pick,
                             "win": win, "diff": diff})
    return {"rank": rank, "winrate": winrate, "pickrate": pickrate,
            "games": games, "top_augments": augments}


def main():
    t0 = time.time()
    patch, patch_display, home_rows = parse_home()
    print("patch=%s（显示 %s），首页 %d 英雄" % (patch, patch_display,
                                                len(home_rows)), flush=True)
    home_map = {slug: (rank, tier, winrate, pickrate)
                for slug, rank, tier, winrate, pickrate in home_rows}
    # 反查 mayhem slug（处理 monkeyking 这类修正）
    rev_fix = {v: k for k, v in SLUG_FIX.items()}

    by_champion = {}
    failed = []
    for i, (slug, rank, tier, winrate, pickrate) in enumerate(home_rows):
        mayhem_slug = rev_fix.get(slug, slug)
        try:
            info = parse_champion(slug, mayhem_slug)
            info["tier"] = tier
            by_champion[slug] = info
        except Exception as e:
            failed.append("%s: %s" % (slug, e))
        if (i + 1) % 25 == 0:
            print("  英雄页进度 %d/%d" % (i + 1, len(home_rows)), flush=True)
        time.sleep(1.2)

    if failed:
        print("失败 %d 个：" % len(failed), flush=True)
        for f in failed[:10]:
            print("  - " + f, flush=True)
    if len(by_champion) < MIN_CHAMPS:
        sys.exit("成功仅 %d 英雄，低于下限 %d，中止" %
                 (len(by_champion), MIN_CHAMPS))

    ranking = []
    for slug, info in by_champion.items():
        ranking.append([slug, info["winrate"], info["pickrate"],
                        info["games"], info["rank"], info["tier"]])
    ranking.sort(key=lambda r: r[1], reverse=True)

    out = {
        "meta": {
            "patch": patch,
            "patch_display": patch_display,
            "source": "mayhemmeta.com",
            "mode": "aram_mayhem",
            "region": "world",
            "note": "海克斯大乱斗（ARAM: Mayhem）全球数据；该源无地区划分",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        },
        "ranking": ranking,
        "by_champion": by_champion,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "mayhem.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    n_aug = sum(len(v["top_augments"]) for v in by_champion.values())
    print("OK: %d 英雄，%d 条强化记录，耗时 %.0fs -> data/mayhem.json"
          % (len(by_champion), n_aug, time.time() - t0))


if __name__ == "__main__":
    main()
