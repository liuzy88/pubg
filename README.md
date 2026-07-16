# PUBG 每日战报

![最新战报](reports/latest.png)

## 使用

```bash
make install
make fetch
make report
```

开发检查：

```bash
make dev
make check
```

历史报告：

```bash
make report DAYS_AGO=2
make daily 2
```

`make daily 2` 表示抓取并生成前天的报告；数字 `N` 表示距今天 `N` 天。

服务器没有 Chrome 时可以只生成 HTML：

```bash
make report NO_SCREENSHOT=1
```

运行 `make help` 可以查看全部目标；`make daily` 会依次抓取数据并生成昨天的报告。

## 结构

- `fetch_matches.py`：调用 DAK.GG 页面使用的 JSON API 抓取比赛记录。
- `data/matches.csv`：唯一的原始比赛库；每行是一位玩家的一场比赛，首列为精确比赛时间，按 `match_id + steam_id` 去重，只追加新记录。
- `data/fetch_manifest.json`：记录本次采集目标时段、覆盖页数及抓取时间。
- `generate_report.py`：生成统计 JSON、HTML 战报和 PNG 截图。
- `run_daily_report.sh`：服务器每日采集、生成、提交和推送入口。
- `src/parser.py`：解析 DAK.GG 文本。
- `src/stats.py`：玩家统计及比赛维度去重。
- `src/awards.py`：确定性称号和评语。
- `src/renderer.py`：渲染独立 HTML。
- `src/templates/`、`src/static/`：HTML 模板和样式。
- `src/screenshot.py`：Chrome 截图。
- `src/pipeline.py`：主流程和文件输出。
- `tests/`：解析、统计、数据清单和 HTML 安全测试。

报告中的“实际比赛”和“吃鸡”按去重后的比赛计算；“人次”是所有玩家的比赛记录之和。“估算KD”不包含助攻，因此不再标记为 KDA。

数据采集会从第 1 页开始逐页检查精确比赛时间；当该玩家的数据已经覆盖目标报告时段起点时立即停止，不固定抓取 4 页。`dakgg.max_pages` 和 `make fetch PAGES=N` 仅作为异常情况下的安全上限。

CSV 适合当前数据模型，因为报告实际统计的是“某位玩家在某场比赛中的表现”。同一个真实比赛中有多位被跟踪玩家时，会有多行共享同一个 `match_id`；统计阶段仍会按 `match_id` 合并为一场实际比赛。
