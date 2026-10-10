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

SIM ?= verilator
WAVES ?= 0

# all generated files go to tb/results/<test>/
RESULTS_DIR         = ../results/$(notdir $(CURDIR))
SIM_BUILD           = $(RESULTS_DIR)/sim_build
COCOTB_RESULTS_FILE = $(RESULTS_DIR)/results.xml
export PYTHONPYCACHEPREFIX = $(abspath $(RESULTS_DIR))/__pycache__

COCOTB_HDL_TIMEUNIT = 1ns
COCOTB_HDL_TIMEPRECISION = 1ps

DUT      = axis_frame_length_adjust_fifo
COCOTB_TOPLEVEL     = $(DUT)
COCOTB_TEST_MODULES = test_$(DUT)
VERILOG_SOURCES += ../../rtl/axis/v/$(DUT).f

# handle file list files
process_f_file = $(call process_f_files,$(addprefix $(dir $1),$(shell cat $1)))
process_f_files = $(foreach f,$1,$(if $(filter %.f,$f),$(call process_f_file,$f),$f))
uniq_base = $(if $1,$(call uniq_base,$(foreach f,$1,$(if $(filter-out $(notdir $(lastword $1)),$(notdir $f)),$f,))) $(lastword $1))
VERILOG_SOURCES := $(call uniq_base,$(call process_f_files,$(VERILOG_SOURCES)))

# module parameters
export PARAM_DATA_WIDTH := 8
export PARAM_KEEP_ENABLE := $(shell expr $(PARAM_DATA_WIDTH) \> 8 )
export PARAM_KEEP_WIDTH := $(shell expr \( $(PARAM_DATA_WIDTH) + 7 \) / 8 )
export PARAM_ID_ENABLE := 1
export PARAM_ID_WIDTH := 8
export PARAM_DEST_ENABLE := 1
export PARAM_DEST_WIDTH := 8
export PARAM_USER_ENABLE := 1
export PARAM_USER_WIDTH := 1
export PARAM_FRAME_FIFO_DEPTH := 1024
export PARAM_HEADER_FIFO_DEPTH := 8

ifeq ($(SIM), icarus)
	COCOTB_PLUSARGS += -fst

	COMPILE_ARGS += $(foreach v,$(filter PARAM_%,$(.VARIABLES)),-P $(COCOTB_TOPLEVEL).$(subst PARAM_,,$(v))=$($(v)))

	ifeq ($(WAVES), 1)
		VERILOG_SOURCES += $(RESULTS_DIR)/iverilog_dump.v
		COMPILE_ARGS += -s iverilog_dump
	endif
else ifeq ($(SIM), verilator)
	COMPILE_ARGS += -Wno-SELRANGE -Wno-WIDTH -Wno-PINMISSING -Wno-CASEINCOMPLETE -Wno-LATCH -Wno-UNOPTFLAT

	COMPILE_ARGS += $(foreach v,$(filter PARAM_%,$(.VARIABLES)),-G$(subst PARAM_,,$(v))=$($(v)))

	ifeq ($(WAVES), 1)
		COMPILE_ARGS += --trace-fst
		SIM_ARGS += --trace --trace-file $(RESULTS_DIR)/$(COCOTB_TOPLEVEL).fst
	endif
endif

include $(shell cocotb-config --makefiles)/Makefile.sim

$(RESULTS_DIR)/iverilog_dump.v: | $(SIM_BUILD)
	echo 'module iverilog_dump();' > $@
	echo 'initial begin' >> $@
	echo '    $$dumpfile("$(RESULTS_DIR)/$(COCOTB_TOPLEVEL).fst");' >> $@
	echo '    $$dumpvars(0, $(COCOTB_TOPLEVEL));' >> $@
	echo 'end' >> $@
	echo 'endmodule' >> $@

clean::
	@rm -rf $(RESULTS_DIR)/iverilog_dump.v
	@rm -rf $(RESULTS_DIR)/$(COCOTB_TOPLEVEL).fst
	@rm -rf $(RESULTS_DIR)/__pycache__
