#!/usr/bin/env python3
"""LOL 大乱斗(ARAM)胜率抓取：u.gg normal_aram 数据，按地区抓取。

URL 里的 patch 号(16_21)与末尾版本号(1.5.0)会变：
先从 https://u.gg/lol/aram-tier-list 的 HTML 里用正则解析出当前真实的
stats URL，再把 /world/ 替换成各 region 抓取。
stats2.u.gg 必须带 Referer: https://u.gg/ 头，否则 403。

数据格式：[{"none":[["50",[],wins,games,...],...]}, {"total_matches":N}, ...]
"50" 是 Data Dragon 数字 ID（如 50=Swain），胜率 = wins/games。

输出 data/aram.json：
{"meta":{"patch","source":"u.gg","mode":"normal_aram","scraped_at","regions":[...]},
 "regions":{"world":[[slug,wr,games],...], "kr":[...], ...}}  # wr 降序

仅用标准库。可重复运行（直接覆盖输出）。
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
DATA = ROOT + "/data"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 30
RETRIES = 3
REGIONS = ["world", "kr", "na1", "euw1"]
STATS_URL_RE = re.compile(
    r"https://stats2\.u\.gg/lol/1\.5/champion_ranking/world/"
    r"[\w.]+/normal_aram/overall/[\w.]+\.json")


def http_get(url, referer=None):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, r.read().decode("utf-8", errors="replace")


def fetch_with_retry(url, referer=None):
    for attempt in range(RETRIES + 1):
        try:
            return http_get(url, referer)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, None
        except Exception:
            pass
        if attempt < RETRIES:
            time.sleep(2 ** attempt)
    return None, None


def main():
    # 1. 从 tier-list 页面解析出当前真实的 stats URL（patch/版本号不写死）
    status, html = fetch_with_retry("https://u.gg/lol/aram-tier-list")
    if not html:
        print("抓取 aram-tier-list 页面失败", file=sys.stderr)
        sys.exit(1)
    urls = sorted(set(STATS_URL_RE.findall(html)))
    if not urls:
        print("未在页面中找到 normal_aram stats URL", file=sys.stderr)
        sys.exit(1)
    base_url = urls[0]
    print("stats URL:", base_url, flush=True)
    m = re.search(r"/(\d+_\d+)/normal_aram/", base_url)
    patch = m.group(1).replace("_", ".") if m else "unknown"

    # 2. Data Dragon 数字 ID -> slug
    version = json.loads(
        fetch_with_retry("https://ddragon.leagueoflegends.com/api/versions.json")[1])[0]
    dd = json.loads(fetch_with_retry(
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json")[1])["data"]
    id_to_slug = {}
    for cid, info in dd.items():
        slug = "wukong" if cid == "MonkeyKing" else cid.lower()
        id_to_slug[info["key"]] = slug

    # 3. 按地区抓取
    regions = {}
    for region in REGIONS:
        url = base_url.replace("/world/", f"/{region}/", 1)
        time.sleep(1)
        status, text = fetch_with_retry(url, referer="https://u.gg/")
        if not text:
            print(f"WARN {region}: 抓取失败，跳过", flush=True)
            continue
        payload = json.loads(text)
        rows = payload[0]["none"]
        out = []
        unknown = 0
        for r in rows:
            champ_id, wins, games = str(r[0]), r[2], r[3]
            slug = id_to_slug.get(champ_id)
            if slug is None:
                unknown += 1
                continue
            if games <= 0:
                continue
            out.append([slug, round(wins / games * 100, 2), games])
        out.sort(key=lambda x: (-x[1], x[0]))
        regions[region] = out
        print(f"{region}: {len(out)} 英雄，unknown_id={unknown}", flush=True)

    if not regions.get("world"):
        print("world 数据缺失，拒绝输出", file=sys.stderr)
        sys.exit(1)

    scraped_at = datetime.now(timezone.utc).isoformat()
    result = {
        "meta": {"patch": patch, "source": "u.gg", "mode": "normal_aram",
                 "tier": "overall", "scraped_at": scraped_at,
                 "regions": sorted(regions.keys())},
        "regions": regions,
    }
    with open(DATA + "/aram.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    # 4. selfcheck
    errors = []
    w = regions["world"]
    if len(w) < 150:
        errors.append(f"world 行数过少: {len(w)}")
    top3 = [r[0] for r in w[:5]]
    # 大乱斗常年强势：swain/zilean/zyra 等应在前列（宽松检查）
    if not any(s in top3 for s in ("swain", "zilean", "zyra", "missfortune", "ziggs")):
        errors.append(f"world 前5异常: {top3}")
    for rg, rows in regions.items():
        for r in rows:
            if not (0 < r[1] <= 100) or r[2] <= 0:
                errors.append(f"{rg} 非法行: {r}")
                break
    print(f"DONE patch={patch} regions={sorted(regions)} scraped_at={scraped_at}")
    if errors:
        print("SELFCHECK ERRORS:", errors)
    else:
        print("SELFCHECK OK")


if __name__ == "__main__":
    main()
