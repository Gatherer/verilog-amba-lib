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

export S_COUNT ?= 4
export M_COUNT ?= 4

DUT      = axis_ram_switch
WRAPPER  = $(DUT)_wrap_$(S_COUNT)x$(M_COUNT)
COCOTB_TOPLEVEL     = $(WRAPPER)
COCOTB_TEST_MODULES = test_$(DUT)
VERILOG_SOURCES += $(RESULTS_DIR)/$(WRAPPER).v
VERILOG_SOURCES += ../../rtl/axis/v/$(DUT).f

# handle file list files
process_f_file = $(call process_f_files,$(addprefix $(dir $1),$(shell cat $1)))
process_f_files = $(foreach f,$1,$(if $(filter %.f,$f),$(call process_f_file,$f),$f))
uniq_base = $(if $1,$(call uniq_base,$(foreach f,$1,$(if $(filter-out $(notdir $(lastword $1)),$(notdir $f)),$f,))) $(lastword $1))
VERILOG_SOURCES := $(call uniq_base,$(call process_f_files,$(VERILOG_SOURCES)))

# module parameters
export PARAM_FIFO_DEPTH := 4096
export PARAM_CMD_FIFO_DEPTH := 32
export PARAM_SPEEDUP := 0
export PARAM_S_DATA_WIDTH := 8
export PARAM_S_KEEP_ENABLE := $(shell expr $(PARAM_S_DATA_WIDTH) \> 8 )
export PARAM_S_KEEP_WIDTH := $(shell expr \( $(PARAM_S_DATA_WIDTH) + 7 \) / 8 )
export PARAM_M_DATA_WIDTH := 8
export PARAM_M_KEEP_ENABLE := $(shell expr $(PARAM_M_DATA_WIDTH) \> 8 )
export PARAM_M_KEEP_WIDTH := $(shell expr \( $(PARAM_M_DATA_WIDTH) + 7 \) / 8 )
export PARAM_ID_ENABLE := 1
export PARAM_S_ID_WIDTH := 16
export PARAM_M_ID_WIDTH := $(shell python -c "print($(PARAM_S_ID_WIDTH) + ($(S_COUNT)-1).bit_length())")
export PARAM_M_DEST_WIDTH := 8
export PARAM_S_DEST_WIDTH := $(shell python -c "print($(PARAM_M_DEST_WIDTH) + ($(M_COUNT)-1).bit_length())")
export PARAM_USER_ENABLE := 1
export PARAM_USER_WIDTH := 1
export PARAM_USER_BAD_FRAME_VALUE := 1
export PARAM_USER_BAD_FRAME_MASK := 1
export PARAM_DROP_BAD_FRAME := 0
export PARAM_DROP_WHEN_FULL := 0
export PARAM_UPDATE_TID := 1
export PARAM_ARB_TYPE_ROUND_ROBIN := 1
export PARAM_ARB_LSB_HIGH_PRIORITY := 1
export PARAM_RAM_PIPELINE := 2

ifeq ($(SIM), icarus)
	COCOTB_PLUSARGS += -fst

	COMPILE_ARGS += $(foreach v,$(filter PARAM_%,$(.VARIABLES)),-P $(COCOTB_TOPLEVEL).$(subst PARAM_,,$(v))=$($(v)))

	ifeq ($(WAVES), 1)
		VERILOG_SOURCES += $(RESULTS_DIR)/iverilog_dump.v
		COMPILE_ARGS += -s iverilog_dump
	endif
else ifeq ($(SIM), verilator)
	COMPILE_ARGS += -Wno-SELRANGE -Wno-WIDTH -Wno-ASCRANGE -Wno-UNOPTFLAT

	COMPILE_ARGS += $(foreach v,$(filter PARAM_%,$(.VARIABLES)),-G$(subst PARAM_,,$(v))=$($(v)))

	ifeq ($(WAVES), 1)
		COMPILE_ARGS += --trace-fst
		SIM_ARGS += --trace --trace-file $(RESULTS_DIR)/$(COCOTB_TOPLEVEL).fst
	endif
endif

include $(shell cocotb-config --makefiles)/Makefile.sim

$(RESULTS_DIR)/$(WRAPPER).v: ../../rtl/axis/v/$(DUT)_wrap.py | $(SIM_BUILD)
	python3 $< -p $(S_COUNT) $(M_COUNT) -o $@

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
	@rm -rf $(RESULTS_DIR)/*_wrap_*.v
