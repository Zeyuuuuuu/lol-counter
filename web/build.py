#!/usr/bin/env python3
"""构建 LOL counter 速查单文件页面。

读取数据目录（默认 ../data，可用 --data-dir 指定）下的四个 JSON：
  champions.json / counters.json / builds.json / duos.json，
把 CSS / JS / 数据全部内联，输出 ../dist/index.html。
单文件、零外部请求，file:// 直接打开可用。

任一数据集缺失或契约不合规时报错退出（exit 1），说明缺什么，
绝不静默产出空页面。仅用标准库。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # lol-counter/
SRC = ROOT / "web" / "src"
DIST = ROOT / "dist"

DATASETS = ("champions.json", "counters.json", "builds.json", "duos.json",
            "aram.json")
LANES = ("top", "jungle", "middle", "bottom", "support")

PLACEHOLDERS = {
    "<!--INLINE_CSS-->": SRC / "style.css",
    "<!--INLINE_JS-->": SRC / "app.js",
}


def fail(msg):
    print("构建失败：" + msg, file=sys.stderr)
    sys.exit(1)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail("%s 不是合法 JSON：%s" % (path.name, e))


def check_builds(b):
    """builds.json 契约：
    {"meta":{"patch","tier","source","scraped_at",...},
     "data":{slug:{"top":build|null,"jungle":..., "middle":..., "bottom":..., "support":...}}}
    build = {"wr":数字, "items":[非空字符串...], "keystone":非空字符串,
             "primary":[字符串...], "secondary":[字符串...]}
    """
    errs = []
    if not isinstance(b, dict):
        return ["顶层不是对象"]
    meta = b.get("meta")
    if not isinstance(meta, dict):
        errs.append("缺少 meta 对象")
    else:
        for k in ("patch", "source", "scraped_at"):
            if not meta.get(k):
                errs.append("meta 缺少字段 " + k)
    data = b.get("data")
    if not isinstance(data, dict) or not data:
        errs.append("缺少非空 data 对象")
    else:
        for slug, lanes in data.items():
            where = "data." + str(slug)
            if not isinstance(lanes, dict):
                errs.append(where + " 不是对象")
                continue
            if set(lanes.keys()) != set(LANES):
                errs.append(where + " 的 lane 键必须恰为 " + "/".join(LANES) +
                            "（实际：" + ",".join(sorted(lanes.keys())) + "）")
            for lane, v in lanes.items():
                if lane not in LANES or v is None:
                    continue
                w2 = "%s.%s" % (where, lane)
                if not isinstance(v, dict):
                    errs.append(w2 + " 既不是 null 也不是对象")
                    continue
                if not isinstance(v.get("wr"), (int, float)):
                    errs.append(w2 + ".wr 不是数字")
                items = v.get("items")
                if (not isinstance(items, list) or not items or
                        not all(isinstance(x, str) and x for x in items)):
                    errs.append(w2 + ".items 必须是非空字符串数组")
                if not isinstance(v.get("keystone"), str) or not v.get("keystone"):
                    errs.append(w2 + ".keystone 必须是非空字符串")
                for k in ("primary", "secondary"):
                    rk = v.get(k)
                    if not isinstance(rk, list) or \
                            not all(isinstance(x, str) for x in rk):
                        errs.append(w2 + "." + k + " 必须是字符串数组")
    return errs


def check_aram(a):
    """aram.json 契约：
    {"meta":{"patch","source","mode","scraped_at","regions",...},
     "regions":{region:[[slug,胜率数字,对局数整数],...], ...}}
    胜率降序排列。
    """
    errs = []
    if not isinstance(a, dict):
        return ["顶层不是对象"]
    meta = a.get("meta")
    if not isinstance(meta, dict):
        errs.append("缺少 meta 对象")
    else:
        for k in ("patch", "source", "scraped_at"):
            if not meta.get(k):
                errs.append("meta 缺少字段 " + k)
    regions = a.get("regions")
    if not isinstance(regions, dict) or not regions:
        errs.append("缺少非空 regions 对象")
    else:
        if "world" not in regions:
            errs.append("regions 缺少 world")
        for rg, rows in regions.items():
            if not isinstance(rows, list) or not rows:
                errs.append("regions.%s 不是非空数组" % rg)
                continue
            for i, r in enumerate(rows):
                if not (isinstance(r, (list, tuple)) and len(r) == 3 and
                        isinstance(r[0], str) and
                        isinstance(r[1], (int, float)) and
                        isinstance(r[2], int)):
                    errs.append("regions.%s[%d] 必须是 [slug, 胜率数字, 对局数整数]"
                                % (rg, i))
                    break
                if not (0 < r[1] <= 100) or r[2] <= 0:
                    errs.append("regions.%s[%d] 胜率/对局数非法" % (rg, i))
                    break
    return errs


def check_duos(d):
    """duos.json 契约：
    {"meta":{"patch","patch_note","source","scraped_at","scope",...},
     "ranking":[[slugA,slugB,胜率数字,局数整数],...],
     "by_champion":{slug:{"best":[[slug,胜率数字,局数整数],...],
                             "worst":[[...],...]}}}
    """
    errs = []
    if not isinstance(d, dict):
        return ["顶层不是对象"]
    meta = d.get("meta")
    if not isinstance(meta, dict):
        errs.append("缺少 meta 对象")
    else:
        for k in ("patch", "patch_note", "source", "scraped_at", "scope"):
            if not meta.get(k):
                errs.append("meta 缺少字段 " + k)
    rk = d.get("ranking")
    if not isinstance(rk, list) or not rk:
        errs.append("缺少非空 ranking 数组")
    else:
        for i, t in enumerate(rk):
            if not (isinstance(t, (list, tuple)) and len(t) == 4 and
                    isinstance(t[0], str) and isinstance(t[1], str) and
                    isinstance(t[2], (int, float)) and isinstance(t[3], int)):
                errs.append("ranking[%d] 必须是 [slugA, slugB, 胜率数字, 局数整数]" % i)
    bc = d.get("by_champion")
    if not isinstance(bc, dict) or not bc:
        errs.append("缺少非空 by_champion 对象")
    else:
        for slug, v in bc.items():
            where = "by_champion." + str(slug)
            if not isinstance(v, dict):
                errs.append(where + " 不是对象")
                continue
            for k in ("best", "worst"):
                lst = v.get(k)
                if not isinstance(lst, list):
                    errs.append(where + " 缺少 " + k + " 数组")
                    continue
                for i, t in enumerate(lst):
                    if not (isinstance(t, (list, tuple)) and len(t) == 3 and
                            isinstance(t[0], str) and
                            isinstance(t[1], (int, float)) and
                            isinstance(t[2], int)):
                        errs.append("%s.%s[%d] 必须是 [slug, 胜率数字, 局数整数]"
                                    % (where, k, i))
    return errs


def dump(obj):
    # 紧凑 JSON；防 </script> 注入（名字里理论上不会有，但保险）
    return json.dumps(obj, ensure_ascii=False,
                      separators=(",", ":")).replace("</", "<\\/")


def main():
    ap = argparse.ArgumentParser(description="构建 LOL counter 速查单文件页面")
    ap.add_argument("--data-dir", default=str(ROOT / "data"),
                    help="数据目录，默认 ../data（相对路径按当前工作目录解析）")
    args = ap.parse_args()
    data_dir = Path(args.data_dir)

    # 1. 数据文件必须齐全（缺哪个说哪个）
    paths = {name: data_dir / name for name in DATASETS}
    missing = [str(p) for name, p in paths.items() if not p.is_file()]
    if missing:
        print("缺少数据文件（--data-dir=%s）：" % data_dir, file=sys.stderr)
        for p in missing:
            print("  - " + p, file=sys.stderr)
        fail("数据集不完整，未生成任何页面")

    # 2. 源码模板必须存在
    template_path = SRC / "index.html"
    for p in [template_path, SRC / "style.css", SRC / "app.js"]:
        if not p.is_file():
            fail("缺少源码文件：" + str(p))

    template = template_path.read_text(encoding="utf-8")
    css = (SRC / "style.css").read_text(encoding="utf-8")
    js = (SRC / "app.js").read_text(encoding="utf-8")

    # 3. 校验数据契约
    champions = load_json(paths["champions.json"])
    counters = load_json(paths["counters.json"])
    builds = load_json(paths["builds.json"])
    duos = load_json(paths["duos.json"])
    aram = load_json(paths["aram.json"])
    if not isinstance(champions.get("champions"), dict) or not champions["champions"]:
        fail("champions.json 缺少非空 champions 字段")
    if not isinstance(counters.get("data"), dict):
        fail("counters.json 缺少 data 字段")
    if not isinstance(counters.get("meta"), dict):
        fail("counters.json 缺少 meta 字段")
    errs = check_builds(builds)
    if errs:
        fail("builds.json 契约不合规：\n  - " + "\n  - ".join(errs))
    errs = check_duos(duos)
    if errs:
        fail("duos.json 契约不合规：\n  - " + "\n  - ".join(errs))
    errs = check_aram(aram)
    if errs:
        fail("aram.json 契约不合规：\n  - " + "\n  - ".join(errs))

    # 3b. 外号表并入 champions（data/nicknames.json 为人工维护的静态文件）
    nick_path = data_dir / "nicknames.json"
    if not nick_path.is_file():
        fail("缺少 data/nicknames.json")
    nicks = load_json(nick_path)
    if not isinstance(nicks, dict):
        fail("nicknames.json 顶层不是对象")
    champ_map = champions["champions"]
    bad_nicks = [s for s in nicks if s not in champ_map]
    if bad_nicks:
        fail("nicknames.json 含未知 slug：" + ",".join(sorted(bad_nicks)))
    n_merged = 0
    for slug, ns in nicks.items():
        if not isinstance(ns, list) or not all(isinstance(x, str) and x for x in ns):
            fail("nicknames.json[%s] 必须是非空字符串数组" % slug)
        champ_map[slug]["nicks"] = ns
        n_merged += 1

    # 4. 内联
    data_js = (
        "window.__CHAMPIONS__ = " + dump(champions) + ";\n"
        "window.__COUNTERS__ = " + dump(counters) + ";\n"
        "window.__BUILDS__ = " + dump(builds) + ";\n"
        "window.__DUOS__ = " + dump(duos) + ";\n"
        "window.__ARAM__ = " + dump(aram) + ";"
    )

    html = template
    for ph, src_file in PLACEHOLDERS.items():
        if ph not in html:
            fail("模板缺少占位符 " + ph + "（" + str(template_path) + "）")
        content = src_file.read_text(encoding="utf-8")
        tag = "style" if src_file.suffix == ".css" else "script"
        html = html.replace(ph, "<%s>\n%s\n</%s>" % (tag, content, tag))
    if "<!--INLINE_DATA-->" not in html:
        fail("模板缺少占位符 <!--INLINE_DATA-->（" + str(template_path) + "）")
    html = html.replace("<!--INLINE_DATA-->", "<script>\n" + data_js + "\n</script>")

    # 5. 输出
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / "index.html"
    out.write_text(html, encoding="utf-8")

    n_champs = len(champions["champions"])
    n_rows = sum(len(rows) for c in counters["data"].values() for rows in c.values())
    n_builds = sum(1 for lanes in builds["data"].values()
                   for v in lanes.values() if v)
    print(
        "OK: %s (%d bytes)，英雄 %d（含外号 %d），counter 数据行 %d，builds 条目 %d，"
        "duo 全榜 %d 行，duo by_champion 英雄 %d，大乱斗地区 %s"
        % (out, out.stat().st_size, n_champs, n_merged, n_rows, n_builds,
           len(duos["ranking"]), len(duos["by_champion"]),
           ",".join(sorted(aram["regions"].keys())))
    )


if __name__ == "__main__":
    main()
