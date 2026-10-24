# Copyright (c) 2020 Alex Forencich
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

# reset clock domain crossing timing constraints

foreach inst [get_cells -hier -filter {(ORIG_REF_NAME == sync_reset_cdc || REF_NAME == sync_reset_cdc)}] {
    puts "Inserting timing constraints for sync_reset_cdc instance $inst"

    set src_ff [get_cells "$inst/src_reg_reg"]
    set sync_ffs [get_cells -quiet -hier -regexp ".*/sync_reg_reg\\\[\\d+\\\]" -filter "PARENT == $inst"]

    set_property ASYNC_REG TRUE $sync_ffs

    # src register to first sync register, one src clock period
    set src_clk [get_clocks -of_objects $src_ff]
    set src_clk_period [if {[llength $src_clk]} {get_property -min PERIOD $src_clk} {expr 1.0}]

    set_max_delay -from $src_ff -to [get_cells "$inst/sync_reg_reg[0]"] -datapath_only $src_clk_period
}
