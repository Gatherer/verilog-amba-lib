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
 * AXI4-Stream asynchronous FIFO (wrapper)
 * flat ports for simulation, maps to axis_if interfaces
 */
module axis_async_fifo_wrap #(
    // FIFO depth in words
    parameter  int DEPTH                = 4096,
    // width of AXI stream interfaces in bits
    parameter  int DATA_WIDTH           = 8,
    // propagate tkeep signal
    parameter  bit KEEP_ENABLE          = (DATA_WIDTH > 8),
    // propagate tstrb signal
    parameter  bit STRB_ENABLE          = 1'b0,
    // propagate tlast signal
    parameter  bit LAST_ENABLE          = 1'b1,
    // propagate tid signal
    parameter  bit ID_ENABLE            = 1'b0,
    // tid signal width
    parameter  int ID_WIDTH             = 8,
    // propagate tdest signal
    parameter  bit DEST_ENABLE          = 1'b0,
    // tdest signal width
    parameter  int DEST_WIDTH           = 8,
    // propagate tuser signal
    parameter  bit USER_ENABLE          = 1'b1,
    // tuser signal width
    parameter  int USER_WIDTH           = 1,
    // number of RAM pipeline registers
    parameter  int RAM_PIPELINE         = 1,
    // use output FIFO
    parameter  bit OUTPUT_FIFO_ENABLE   = 1'b0,
    // frame FIFO mode
    parameter  bit FRAME_FIFO           = 1'b0,
    // tuser value for bad frame marker
    parameter      USER_BAD_FRAME_VALUE = 1'b1,
    // tuser mask for bad frame marker
    parameter      USER_BAD_FRAME_MASK  = 1'b1,
    // drop frames larger than FIFO
    parameter  bit DROP_OVERSIZE_FRAME  = FRAME_FIFO,
    // drop frames marked bad
    parameter  bit DROP_BAD_FRAME       = 1'b0,
    // drop incoming frames when full
    parameter  bit DROP_WHEN_FULL       = 1'b0,
    // mark incoming frames as bad frames when full
    parameter  bit MARK_WHEN_FULL       = 1'b0,
    // enable pause request input
    parameter  bit PAUSE_ENABLE         = 1'b0,
    // pause between frames
    parameter  bit FRAME_PAUSE          = FRAME_FIFO,
    localparam int KEEP_WIDTH           = (DATA_WIDTH + 7) / 8
) (
    /*
     * AXI Stream input
     */
    input  wire                    s_clk,
    input  wire                    s_rst,
    input  wire [DATA_WIDTH-1:0]   s_axis_tdata,
    input  wire [KEEP_WIDTH-1:0]   s_axis_tkeep,
    input  wire [KEEP_WIDTH-1:0]   s_axis_tstrb,
    input  wire                    s_axis_tvalid,
    output logic                   s_axis_tready,
    input  wire                    s_axis_tlast,
    input  wire [ID_WIDTH-1:0]     s_axis_tid,
    input  wire [DEST_WIDTH-1:0]   s_axis_tdest,
    input  wire [USER_WIDTH-1:0]   s_axis_tuser,

    /*
     * AXI Stream output
     */
    input  wire                    m_clk,
    input  wire                    m_rst,
    output logic[DATA_WIDTH-1:0]   m_axis_tdata,
    output logic[KEEP_WIDTH-1:0]   m_axis_tkeep,
    output logic[KEEP_WIDTH-1:0]   m_axis_tstrb,
    output logic                   m_axis_tvalid,
    input  wire                    m_axis_tready,
    output logic                   m_axis_tlast,
    output logic[ID_WIDTH-1:0]     m_axis_tid,
    output logic[DEST_WIDTH-1:0]   m_axis_tdest,
    output logic[USER_WIDTH-1:0]   m_axis_tuser,

    /*
     * Pause
     */
    input  wire                    s_pause_req,
    output logic                   s_pause_ack,
    input  wire                    m_pause_req,
    output logic                   m_pause_ack,

    /*
     * Status
     */
    output logic[$clog2(DEPTH):0]  s_status_depth,
    output logic[$clog2(DEPTH):0]  s_status_depth_commit,
    output logic                   s_status_overflow,
    output logic                   s_status_bad_frame,
    output logic                   s_status_good_frame,
    output logic[$clog2(DEPTH):0]  m_status_depth,
    output logic[$clog2(DEPTH):0]  m_status_depth_commit,
    output logic                   m_status_overflow,
    output logic                   m_status_bad_frame,
    output logic                   m_status_good_frame
);

axis_if #(
    .DATA_WIDTH(DATA_WIDTH),
    .KEEP_WIDTH(KEEP_WIDTH),
    .KEEP_ENABLE(KEEP_ENABLE),
    .STRB_ENABLE(STRB_ENABLE),
    .LAST_ENABLE(LAST_ENABLE),
    .ID_ENABLE(ID_ENABLE),
    .ID_WIDTH(ID_WIDTH),
    .DEST_ENABLE(DEST_ENABLE),
    .DEST_WIDTH(DEST_WIDTH),
    .USER_ENABLE(USER_ENABLE),
    .USER_WIDTH(USER_WIDTH)
) s_axis (), m_axis ();

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

axis_async_fifo #(
    .DEPTH(DEPTH),
    .RAM_PIPELINE(RAM_PIPELINE),
    .OUTPUT_FIFO_ENABLE(OUTPUT_FIFO_ENABLE),
    .FRAME_FIFO(FRAME_FIFO),
    .USER_BAD_FRAME_VALUE(USER_BAD_FRAME_VALUE),
    .USER_BAD_FRAME_MASK(USER_BAD_FRAME_MASK),
    .DROP_OVERSIZE_FRAME(DROP_OVERSIZE_FRAME),
    .DROP_BAD_FRAME(DROP_BAD_FRAME),
    .DROP_WHEN_FULL(DROP_WHEN_FULL),
    .MARK_WHEN_FULL(MARK_WHEN_FULL),
    .PAUSE_ENABLE(PAUSE_ENABLE),
    .FRAME_PAUSE(FRAME_PAUSE)
)
axis_async_fifo_inst (
    .s_clk(s_clk),
    .s_rst(s_rst),
    .s_axis(s_axis),
    .m_clk(m_clk),
    .m_rst(m_rst),
    .m_axis(m_axis),
    .s_pause_req(s_pause_req),
    .s_pause_ack(s_pause_ack),
    .m_pause_req(m_pause_req),
    .m_pause_ack(m_pause_ack),
    .s_status_depth(s_status_depth),
    .s_status_depth_commit(s_status_depth_commit),
    .s_status_overflow(s_status_overflow),
    .s_status_bad_frame(s_status_bad_frame),
    .s_status_good_frame(s_status_good_frame),
    .m_status_depth(m_status_depth),
    .m_status_depth_commit(m_status_depth_commit),
    .m_status_overflow(m_status_overflow),
    .m_status_bad_frame(m_status_bad_frame),
    .m_status_good_frame(m_status_good_frame)
);

endmodule

`resetall
