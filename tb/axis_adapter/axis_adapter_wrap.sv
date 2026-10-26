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
 * AXI4-Stream bus width adapter (wrapper)
 * flat ports for simulation, maps to axis_if interfaces
 */
module axis_adapter_wrap #(
    // width of input AXI stream interface in bits
    parameter int S_DATA_WIDTH  = 8,
    // propagate tkeep signal on input interface
    parameter bit S_KEEP_ENABLE = (S_DATA_WIDTH > 8),
    // tkeep signal width on input interface
    parameter int S_KEEP_WIDTH  = ((S_DATA_WIDTH + 7) / 8),
    // width of output AXI stream interface in bits
    parameter int M_DATA_WIDTH  = 8,
    // propagate tkeep signal on output interface
    parameter bit M_KEEP_ENABLE = (M_DATA_WIDTH > 8),
    // tkeep signal width on output interface
    parameter int M_KEEP_WIDTH  = ((M_DATA_WIDTH + 7) / 8),
    // propagate tstrb signal
    parameter bit STRB_ENABLE   = 1'b0,
    // propagate tlast signal
    parameter bit LAST_ENABLE   = 1'b1,
    // propagate tid signal
    parameter bit ID_ENABLE     = 1'b0,
    // tid signal width
    parameter int ID_WIDTH      = 8,
    // propagate tdest signal
    parameter bit DEST_ENABLE   = 1'b0,
    // tdest signal width
    parameter int DEST_WIDTH    = 8,
    // propagate tuser signal
    parameter bit USER_ENABLE   = 1'b1,
    // tuser signal width
    parameter int USER_WIDTH    = 1
) (
    input  wire                     clk,
    input  wire                     rst,

    /*
     * AXI Stream input
     */
    input  wire [S_DATA_WIDTH-1:0]  s_axis_tdata,
    input  wire [S_KEEP_WIDTH-1:0]  s_axis_tkeep,
    input  wire [S_KEEP_WIDTH-1:0]  s_axis_tstrb,
    input  wire                     s_axis_tvalid,
    output logic                    s_axis_tready,
    input  wire                     s_axis_tlast,
    input  wire [ID_WIDTH-1:0]      s_axis_tid,
    input  wire [DEST_WIDTH-1:0]    s_axis_tdest,
    input  wire [USER_WIDTH-1:0]    s_axis_tuser,

    /*
     * AXI Stream output
     */
    output logic[M_DATA_WIDTH-1:0]  m_axis_tdata,
    output logic[M_KEEP_WIDTH-1:0]  m_axis_tkeep,
    output logic[M_KEEP_WIDTH-1:0]  m_axis_tstrb,
    output logic                    m_axis_tvalid,
    input  wire                     m_axis_tready,
    output logic                    m_axis_tlast,
    output logic[ID_WIDTH-1:0]      m_axis_tid,
    output logic[DEST_WIDTH-1:0]    m_axis_tdest,
    output logic[USER_WIDTH-1:0]    m_axis_tuser
);

axis_if #(
    .DATA_WIDTH(S_DATA_WIDTH),
    .KEEP_WIDTH(S_KEEP_WIDTH),
    .KEEP_ENABLE(S_KEEP_ENABLE),
    .STRB_ENABLE(STRB_ENABLE),
    .LAST_ENABLE(LAST_ENABLE),
    .ID_ENABLE(ID_ENABLE),
    .ID_WIDTH(ID_WIDTH),
    .DEST_ENABLE(DEST_ENABLE),
    .DEST_WIDTH(DEST_WIDTH),
    .USER_ENABLE(USER_ENABLE),
    .USER_WIDTH(USER_WIDTH)
) s_axis ();

axis_if #(
    .DATA_WIDTH(M_DATA_WIDTH),
    .KEEP_WIDTH(M_KEEP_WIDTH),
    .KEEP_ENABLE(M_KEEP_ENABLE),
    .STRB_ENABLE(STRB_ENABLE),
    .LAST_ENABLE(LAST_ENABLE),
    .ID_ENABLE(ID_ENABLE),
    .ID_WIDTH(ID_WIDTH),
    .DEST_ENABLE(DEST_ENABLE),
    .DEST_WIDTH(DEST_WIDTH),
    .USER_ENABLE(USER_ENABLE),
    .USER_WIDTH(USER_WIDTH)
) m_axis ();

// slave interface
assign s_axis.tdata  = s_axis_tdata;
assign s_axis.tkeep  = s_axis_tkeep;
assign s_axis.tstrb  = s_axis_tstrb;
assign s_axis.tvalid = s_axis_tvalid;
assign s_axis.tlast  = s_axis_tlast;
assign s_axis.tid    = s_axis_tid;
assign s_axis.tdest  = s_axis_tdest;
assign s_axis.tuser  = s_axis_tuser;

assign s_axis_tready = s_axis.tready;

// master interface
assign m_axis_tdata  = m_axis.tdata;
assign m_axis_tkeep  = m_axis.tkeep;
assign m_axis_tstrb  = m_axis.tstrb;
assign m_axis_tvalid = m_axis.tvalid;
assign m_axis_tlast  = m_axis.tlast;
assign m_axis_tid    = m_axis.tid;
assign m_axis_tdest  = m_axis.tdest;
assign m_axis_tuser  = m_axis.tuser;

assign m_axis.tready = m_axis_tready;

axis_adapter
axis_adapter_inst (
    .clk(clk),
    .rst(rst),
    .s_axis(s_axis),
    .m_axis(m_axis)
);

endmodule

`resetall
