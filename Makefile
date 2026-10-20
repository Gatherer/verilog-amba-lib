# Top-level Makefile: create Python venv and run cocotb tests (Verilator)
#
#   make            create venv (if needed) and run all tests
#   make venv       create/update venv from requirements.txt
#   make test TESTS=tb/axi_ram ARGS="-k 32"   serial, live output (default)
#   make test JOBS=auto                       parallel (regression), output only on failure
#   make lint       run ruff linter, check formatting
#   make format     format Python files with ruff
#   make clean      remove simulation build outputs
#   make distclean  clean + remove venv
#
#   update all test durations
#   make test JOBS=auto ARGS="--store-durations --clean-durations"

#   update only test durations for one test, in this example priority_encoder
#   make test JOBS=auto TESTS=tb/priority_encoder ARGS="--store-durations"

PYTHON ?= python3
VENV   ?= .venv
JOBS   ?= 0
TESTS  ?= tb
ARGS   ?=

# serial run (JOBS=0): disable output capturing for live simulation output
LIVE_OUT := $(if $(filter 0,$(JOBS)),-s)

# keep Python bytecode out of the source tree
export PYTHONPYCACHEPREFIX := $(abspath tb/results/__pycache__)

VENV_BIN   := $(VENV)/bin
VENV_STAMP := $(VENV)/.installed

.PHONY: all venv test lint format check-verilator clean distclean

all: test

venv: $(VENV_STAMP)

$(VENV_STAMP): requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -r requirements.txt
	touch $@

check-verilator:
	@command -v verilator >/dev/null || { echo "ERROR: verilator not found in PATH"; exit 1; }
	@verilator --version

test: $(VENV_STAMP) check-verilator
	PATH=$(abspath $(VENV_BIN)):$$PATH $(VENV_BIN)/pytest -n $(JOBS) $(LIVE_OUT) $(ARGS) $(TESTS)

lint: $(VENV_STAMP)
	$(VENV_BIN)/ruff check .
	$(VENV_BIN)/ruff format --check .

format: $(VENV_STAMP)
	$(VENV_BIN)/ruff format .

clean:
	rm -rf tb/results
	find tb -name sim_build -type d -prune -exec rm -rf {} +
	find tb -name results.xml -delete
	find tb -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -f tb/*/*_wrap_[0-9]*x[0-9]*.v

distclean: clean
	rm -rf $(VENV)
