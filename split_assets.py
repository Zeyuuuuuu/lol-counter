"""Split inline window.__*__ data blocks out of dist/index.html into dist/assets/.

Idempotent: if dist/index.html no longer contains inline blocks (already split),
does nothing. Run after web/build.py regenerates the single-file index.html.

Byte-identical extraction is verified; each output passes node --check when
node is available.
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "dist", "index.html")
ASSETS = os.path.join(ROOT, "dist", "assets")
BLOCKS = ["CHAMPIONS", "COUNTERS", "BUILDS", "DUOS", "ARAM"]


def main():
    html = open(SRC, encoding="utf-8").read()
    if "window.__COUNTERS__ =" not in html:
        print("already split, nothing to do")
        return
    os.makedirs(ASSETS, exist_ok=True)
    for name in BLOCKS:
        m = re.search(r"window\.__" + name + r"__\s*=\s*", html)
        assert m, name
        val_start = m.end()
        obj, end = json.JSONDecoder().raw_decode(html[val_start:])
        abs_end = val_start + end
        assert html[abs_end] == ";", f"{name}: expected ;"
        stmt = html[m.start():abs_end + 1]
        fname = os.path.join(ASSETS, f"data-{name.lower()}.js")
        with open(fname, "w", encoding="utf-8") as fh:
            fh.write(stmt)
        assert open(fname, encoding="utf-8").read() == stmt
        tag = f'<script src="assets/data-{name.lower()}.js"></script>'
        html = html[:m.start()] + tag + html[abs_end + 1:]
        print(f"{name}: {len(stmt)} chars -> {fname}", flush=True)
    # 去掉包裹 data 标签的外层空 <script> 壳：
    # 若残留，浏览器会把里面的 src 标签当成脚本"文本内容"而不执行，
    # 导致全部数据未加载（2026-10-29 全站搜索失效事故的根因）。
    html, n = re.subn(
        r'<script>\s*((?:<script src="assets/data-[a-z]+\.js"></script>\s*)+)</script>',
        r"\1",
        html,
    )
    assert n == 1, f"外层空 script 壳清理异常，匹配数={n}"
    print("外层空 script 壳已移除")
    with open(SRC, "w", encoding="utf-8") as fh:
        fh.write(html)
    if shutil.which("node"):
        for name in BLOCKS:
            subprocess.run(
                ["node", "--check", os.path.join(ASSETS, f"data-{name.lower()}.js")],
                check=True)
        print("node --check OK")
    print("index.html bytes:", len(html))


if __name__ == "__main__":
    sys.exit(main())
