#!/usr/bin/env python3
"""抓取 u.gg 下路组合（adc_supp）数据，按地区。

URL: https://stats2.u.gg/lol/1.5/duos/{region}/{patch}/ranked_solo_5x5/emerald_plus/{ver}.json
patch 与版本号从 https://u.gg/lol/tier-list 页面实时解析，不写死。
region: world / kr / na1 / euw1。请求带 Referer: https://u.gg/ 头。

行格式: [adc_id,3,adc_wins,adc_games,supp_id,2,supp_wins,supp_games,
          duo_wins,duo_games,?,null,null]
英雄数字 ID 经 Data Dragon 映射到 slug（monkeyking->wukong 修正）。

输出 data/duos.json：
{"meta": {"patch","source":"u.gg","tier":"emerald_plus","tier_note":"翡翠及以上",
          "scope":"ranked_solo_5x5","regions":[...],"scraped_at"},
 "regions": {region: {"ranking": [[adc,supp,胜率%,局数],...top50],
                       "by_champion": {slug: {"best":[[搭档,胜率%,局数]x5],
                                              "worst":[...]}}}}}
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/120.0 Safari/537.36")
REGIONS = ["world", "kr", "na1", "euw1"]
SLUG_FIX = {"monkeyking": "wukong"}
TOP_N = 50
PER_CHAMP_N = 5


def fetch(url, referer="https://u.gg/"):
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def resolve_patch_ver():
    page = fetch("https://u.gg/lol/tier-list").decode("utf-8", errors="ignore")
    m = re.search(
        r"champion_ranking/world/([\d_]+)/ranked_solo_5x5/emerald_plus/"
        r"([\d.]+)\.json", page)
    if not m:
        raise RuntimeError("u.gg tier-list 页面解析 patch/版本号失败")
    return m.group(1), m.group(2)


def id2slug_map():
    vers = json.loads(fetch(
        "https://ddragon.leagueoflegends.com/api/versions.json").decode())
    v = vers[0]
    dd = json.loads(fetch(
        "https://ddragon.leagueoflegends.com/cdn/%s/data/en_US/champion.json"
        % v).decode())
    return {info["key"]: SLUG_FIX.get(k.lower(), k.lower())
            for k, info in dd["data"].items()}


def main():
    patch, ver = resolve_patch_ver()
    print("patch=%s, api版本=%s" % (patch, ver), flush=True)
    id2slug = id2slug_map()
    print("Data Dragon 英雄映射 %d 个" % len(id2slug), flush=True)

    regions_out = {}
    for rg in REGIONS:
        url = ("https://stats2.u.gg/lol/1.5/duos/%s/%s/ranked_solo_5x5/"
               "emerald_plus/%s.json" % (rg, patch, ver))
        raw = fetch(url)
        d = json.loads(raw.decode("utf-8", errors="ignore"))
        rows = d[0]["adc_supp"]
        pairs = []
        unknown = set()
        for r in rows:
            a = id2slug.get(str(r[0]))
            s = id2slug.get(str(r[4]))
            if a is None:
                unknown.add(str(r[0]))
            if s is None:
                unknown.add(str(r[4]))
            if a is None or s is None:
                continue
            duo_games = r[9]
            duo_wr = r[8] / duo_games * 100 if duo_games else 0
            pairs.append((a, s, duo_wr, duo_games))
        if unknown:
            print("  %s 未知英雄ID: %s" % (rg, sorted(unknown)), flush=True)
        pairs.sort(key=lambda x: x[2], reverse=True)
        ranking = [[a, s, round(wr, 2), g] for a, s, wr, g in pairs[:TOP_N]]

        per = {}
        for a, s, wr, g in pairs:
            per.setdefault(a, []).append((s, wr, g))
            per.setdefault(s, []).append((a, wr, g))
        by_champion = {}
        for slug, lst in per.items():
            desc = sorted(lst, key=lambda x: x[1], reverse=True)
            asc = sorted(lst, key=lambda x: x[1])
            by_champion[slug] = {
                "best": [[p, round(w, 2), gg] for p, w, gg in desc[:PER_CHAMP_N]],
                "worst": [[p, round(w, 2), gg] for p, w, gg in asc[:PER_CHAMP_N]],
            }
        regions_out[rg] = {"ranking": ranking, "by_champion": by_champion}
        print("  %s: %d 对组合，%d 个英雄有搭档数据"
              % (rg, len(pairs), len(by_champion)), flush=True)

    if not regions_out.get("world", {}).get("ranking"):
        sys.exit("world 地区无组合数据，中止")

    out = {
        "meta": {
            "patch": patch.replace("_", "."),
            "source": "u.gg",
            "tier": "emerald_plus",
            "tier_note": "翡翠及以上",
            "scope": "ranked_solo_5x5",
            "regions": REGIONS,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        },
        "regions": regions_out,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "duos.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("OK -> data/duos.json")


if __name__ == "__main__":
    main()
