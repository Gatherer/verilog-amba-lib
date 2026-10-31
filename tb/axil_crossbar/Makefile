# Copyright (c) 2021 Alex Forencich
# Copyright (c) 2026 Thomas Glatte
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

TOPLEVEL_LANG = verilog

SIM = verilator
WAVES ?= 0

# all generated files go to tb/results/<test>/
RESULTS_DIR         = ../results/$(notdir $(CURDIR))
SIM_BUILD           = $(RESULTS_DIR)/sim_build
COCOTB_RESULTS_FILE = $(RESULTS_DIR)/results.xml
export PYTHONPYCACHEPREFIX = $(abspath $(RESULTS_DIR))/__pycache__

COCOTB_HDL_TIMEUNIT = 1ns
COCOTB_HDL_TIMEPRECISION = 1ps

S_COUNT := 4
M_COUNT := 4

DUT      = axil_crossbar
WRAPPER  = $(DUT)_wrap_$(S_COUNT)x$(M_COUNT)
COCOTB_TOPLEVEL     = $(WRAPPER)
COCOTB_TEST_MODULES = test_$(DUT)
VERILOG_SOURCES += $(RESULTS_DIR)/$(WRAPPER).v
VERILOG_SOURCES += ../../rtl/axil/v/$(DUT).v
VERILOG_SOURCES += ../../rtl/axil/v/$(DUT)_addr.v
VERILOG_SOURCES += ../../rtl/axil/v/$(DUT)_rd.v
VERILOG_SOURCES += ../../rtl/axil/v/$(DUT)_wr.v
VERILOG_SOURCES += ../../rtl/axil/v/axil_register_rd.v
VERILOG_SOURCES += ../../rtl/axil/v/axil_register_wr.v
VERILOG_SOURCES += ../../rtl/common/v/arbiter.v
VERILOG_SOURCES += ../../rtl/common/v/priority_encoder.v

# module parameters
export PARAM_DATA_WIDTH := 32
export PARAM_ADDR_WIDTH := 32
export PARAM_STRB_WIDTH := $(shell expr $(PARAM_DATA_WIDTH) / 8 )
export PARAM_M_REGIONS := 1

COMPILE_ARGS += -Wno-SELRANGE -Wno-WIDTH -Wno-UNSIGNED -Wno-CASEINCOMPLETE -Wno-UNOPTFLAT -Wno-ASCRANGE

COMPILE_ARGS += $(foreach v,$(filter PARAM_%,$(.VARIABLES)),-G$(subst PARAM_,,$(v))=$($(v)))

ifeq ($(WAVES), 1)
	COMPILE_ARGS += --trace-fst
	SIM_ARGS += --trace --trace-file $(RESULTS_DIR)/$(COCOTB_TOPLEVEL).fst
endif

include $(shell cocotb-config --makefiles)/Makefile.sim

$(RESULTS_DIR)/$(WRAPPER).v: ../../rtl/axil/v/$(DUT)_wrap.py | $(SIM_BUILD)
	python3 $< -p $(S_COUNT) $(M_COUNT) -o $@

clean::
	@rm -rf $(RESULTS_DIR)/$(COCOTB_TOPLEVEL).fst
	@rm -rf $(RESULTS_DIR)/__pycache__
	@rm -rf $(RESULTS_DIR)/*_wrap_*.v
