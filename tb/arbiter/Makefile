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

DUT      = arbiter
COCOTB_TOPLEVEL     = $(DUT)
COCOTB_TEST_MODULES = test_$(DUT)
VERILOG_SOURCES += ../../rtl/common/v/$(DUT).v
VERILOG_SOURCES += ../../rtl/common/v/priority_encoder.v

# module parameters
export PARAM_PORTS := 4
export PARAM_ARB_TYPE_ROUND_ROBIN := 1
export PARAM_ARB_BLOCK := 1
export PARAM_ARB_BLOCK_ACK := 1
export PARAM_ARB_LSB_HIGH_PRIORITY := 0

COMPILE_ARGS += -Wno-SELRANGE -Wno-WIDTH -Wno-UNOPTFLAT

COMPILE_ARGS += $(foreach v,$(filter PARAM_%,$(.VARIABLES)),-G$(subst PARAM_,,$(v))=$($(v)))

ifeq ($(WAVES), 1)
	COMPILE_ARGS += --trace-fst
	SIM_ARGS += --trace --trace-file $(RESULTS_DIR)/$(COCOTB_TOPLEVEL).fst
endif

include $(shell cocotb-config --makefiles)/Makefile.sim

clean::
	@rm -rf $(RESULTS_DIR)/$(COCOTB_TOPLEVEL).fst
	@rm -rf $(RESULTS_DIR)/__pycache__
