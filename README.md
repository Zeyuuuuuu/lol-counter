# LOL counter 速查

手机端快速查询英雄联盟英雄克制关系的单页应用。BP 时 10 秒内可查。

- `docs/`：可直接部署的站点文件（GitHub Pages 用）
- `web/src/`：前端源码，`web/build.py` 构建到 `dist/`
- `scraper.py` / `scrape_builds.py` / `scrape_duos.py`：数据抓取脚本
- `data/`：数据集（lolalytics，global，all tiers）

数据每 3 天自动更新。
