PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
RUFF ?= ruff

DAYS_AGO ?= 1
PAGES ?=
PLAYER ?=
CONFIG ?= conf.json
NO_SCREENSHOT ?=

FETCH_ARGS := --config $(CONFIG)
REPORT_ARGS := --config $(CONFIG) --days-ago $(DAYS_AGO)

ifneq ($(strip $(PAGES)),)
FETCH_ARGS += --pages $(PAGES)
endif

ifneq ($(strip $(PLAYER)),)
FETCH_ARGS += --player $(PLAYER)
endif

ifneq ($(strip $(NO_SCREENSHOT)),)
REPORT_ARGS += --no-screenshot
endif

.PHONY: help install dev lint test compile check fetch report daily clean

help:
	@echo "PUBG 每日战报"
	@echo "  make install                         安装运行依赖"
	@echo "  make dev                             安装开发依赖"
	@echo "  make check                           运行 lint、测试和编译检查"
	@echo "  make fetch                           抓取全部玩家数据"
	@echo "  make fetch PAGES=4 PLAYER=steam_id   指定页数或玩家"
	@echo "  make report                          生成昨天的报告"
	@echo "  make report DAYS_AGO=2               生成历史报告"
	@echo "  make report NO_SCREENSHOT=1          不生成 PNG"
	@echo "  make daily                           抓取并生成昨天的报告"
	@echo "  make clean                           清理 Python 缓存"

install:
	$(PIP) install -r requirements.txt

dev:
	$(PIP) install -r requirements-dev.txt

lint:
	$(RUFF) check .

test:
	$(PYTHON) -m unittest discover -s tests -v

compile:
	$(PYTHON) -m compileall -q pubg_report pubg_daily_report.py fetch_data.py tests
	bash -n run_daily.sh

check: lint test compile

fetch:
	$(PYTHON) fetch_data.py $(FETCH_ARGS)

report:
	$(PYTHON) pubg_daily_report.py $(REPORT_ARGS)

daily: fetch report

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
