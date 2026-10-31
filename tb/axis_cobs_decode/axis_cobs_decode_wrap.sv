/*

Copyright (c) 2026 Thomas Glatte

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

*/

// Language: SystemVerilog

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * AXI4-Stream COBS decoder (wrapper)
 * flat ports for simulation, maps to axis_if interfaces
 */
module axis_cobs_decode_wrap #(
    // use s_axis tlast signal
    parameter bit S_LAST_ENABLE = 1'b1,
    // use s_axis tuser signal
    parameter bit S_USER_ENABLE = 1'b1
) (
    input  wire        clk,
    input  wire        rst,

    /*
     * AXI Stream input
     */
    input  wire  [7:0] s_axis_tdata,
    input  wire        s_axis_tvalid,
    output logic       s_axis_tready,
    input  wire        s_axis_tlast,
    input  wire        s_axis_tuser,

    /*
     * AXI Stream output
     */
    output logic [7:0] m_axis_tdata,
    output logic       m_axis_tvalid,
    input  wire        m_axis_tready,
    output logic       m_axis_tlast,
    output logic       m_axis_tuser
);

axis_if #(
    .DATA_WIDTH(8),
    .LAST_ENABLE(S_LAST_ENABLE),
    .USER_ENABLE(S_USER_ENABLE),
    .USER_WIDTH(1)
) s_axis ();

axis_if #(
    .DATA_WIDTH(8),
    .LAST_ENABLE(1'b1),
    .USER_ENABLE(1'b1),
    .USER_WIDTH(1)
) m_axis ();

// m_axis signals without flat port
/* verilator lint_off UNUSEDSIGNAL */
logic unused;
/* verilator lint_on UNUSEDSIGNAL */

assign unused = ^{m_axis.tkeep, m_axis.tstrb, m_axis.tid, m_axis.tdest};

// slave interface
assign s_axis.tdata  = s_axis_tdata;
assign s_axis.tkeep  = '1;
assign s_axis.tstrb  = '1;
assign s_axis.tvalid = s_axis_tvalid;
assign s_axis.tlast  = s_axis_tlast;
assign s_axis.tid    = '0;
assign s_axis.tdest  = '0;
assign s_axis.tuser  = s_axis_tuser;

assign s_axis_tready = s_axis.tready;

// master interface
assign m_axis_tdata  = m_axis.tdata;
assign m_axis_tvalid = m_axis.tvalid;
assign m_axis_tlast  = m_axis.tlast;
assign m_axis_tuser  = m_axis.tuser;

assign m_axis.tready = m_axis_tready;

axis_cobs_decode axis_cobs_decode_inst (
    .clk(clk),
    .rst(rst),
    .s_axis(s_axis),
    .m_axis(m_axis)
);

endmodule

`resetall
