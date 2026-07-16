PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
RUFF ?= ruff

DAYS_AGO ?= 1
PAGES ?=
PLAYER ?=
CONFIG ?= conf.json
NO_SCREENSHOT ?=

DAY_TARGETS := 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30
REQUESTED_DAY := $(filter $(DAY_TARGETS),$(MAKECMDGOALS))

ifneq ($(strip $(REQUESTED_DAY)),)
DAYS_AGO := $(lastword $(REQUESTED_DAY))
endif

FETCH_ARGS := --config $(CONFIG)
REPORT_ARGS := --config $(CONFIG) --days-ago $(DAYS_AGO)

ifneq ($(strip $(PAGES)),)
FETCH_ARGS += --pages $(PAGES)
endif

FETCH_ARGS += --days-ago $(DAYS_AGO)

ifneq ($(strip $(PLAYER)),)
FETCH_ARGS += --player $(PLAYER)
endif

ifneq ($(strip $(NO_SCREENSHOT)),)
REPORT_ARGS += --no-screenshot
endif

.PHONY: help install dev lint test compile check fetch report daily clean $(DAY_TARGETS)

help:
	@echo "PUBG 每日战报"
	@echo "  make install                         安装运行依赖"
	@echo "  make dev                             安装开发依赖"
	@echo "  make check                           运行 lint、测试和编译检查"
	@echo "  make fetch                           抓取全部玩家数据"
	@echo "  make fetch DAYS_AGO=2                按历史目标时段抓取"
	@echo "  make fetch PAGES=10 PLAYER=steam_id  指定安全页数上限或玩家"
	@echo "  make report                          生成昨天的报告"
	@echo "  make report DAYS_AGO=2               生成历史报告"
	@echo "  make report NO_SCREENSHOT=1          不生成 PNG"
	@echo "  make daily                           抓取并生成昨天的报告"
	@echo "  make daily 2                         抓取并生成前天的报告"
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
	$(PYTHON) -m compileall -q src generate_report.py fetch_matches.py tests
	bash -n run_daily_report.sh

check: lint test compile

fetch:
	$(PYTHON) fetch_matches.py $(FETCH_ARGS)

report:
	$(PYTHON) generate_report.py $(REPORT_ARGS)

daily: fetch report

$(DAY_TARGETS):
	@:

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
