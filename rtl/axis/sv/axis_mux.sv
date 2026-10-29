/*

Copyright (c) 2014-2018 Alex Forencich
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
 * AXI4-Stream multiplexer
 * widths and enables are taken from s_axis[0]
 * select is taken at frame start, enable gates tready
 * disabled tstrb follows tkeep, disabled tlast is 0
 * without tlast every beat is a frame
 */
module axis_mux #(
    // number of AXI stream inputs
    parameter  int S_COUNT    = 4,
    localparam int CL_S_COUNT = S_COUNT > 1 ? $clog2(S_COUNT) : 1
) (
    input  wire                  clk,
    input  wire                  rst,

    axis_if.slave                s_axis [S_COUNT],
    axis_if.master               m_axis,

    /*
     * Control
     */
    input  wire                  enable,
    input  wire [CL_S_COUNT-1:0] select
);

localparam int DATA_WIDTH  = s_axis[0].DATA_WIDTH;
localparam int KEEP_WIDTH  = s_axis[0].KEEP_WIDTH;
localparam bit KEEP_ENABLE = s_axis[0].KEEP_ENABLE;
localparam bit STRB_ENABLE = s_axis[0].STRB_ENABLE;
localparam bit LAST_ENABLE = s_axis[0].LAST_ENABLE;
localparam bit ID_ENABLE   = s_axis[0].ID_ENABLE;
localparam int ID_WIDTH    = s_axis[0].ID_WIDTH;
localparam bit DEST_ENABLE = s_axis[0].DEST_ENABLE;
localparam int DEST_WIDTH  = s_axis[0].DEST_WIDTH;
localparam bit USER_ENABLE = s_axis[0].USER_ENABLE;
localparam int USER_WIDTH  = s_axis[0].USER_WIDTH;

// parameter checks
if (S_COUNT < 1) begin : g_count_check
    $error("axis_mux: S_COUNT must be at least 1 (is %0d)", S_COUNT);
end

for (genvar n = 1; n < S_COUNT; n++) begin : g_s_check
    if (s_axis[n].DATA_WIDTH  != DATA_WIDTH  || s_axis[n].KEEP_WIDTH  != KEEP_WIDTH  ||
        s_axis[n].KEEP_ENABLE != KEEP_ENABLE || s_axis[n].STRB_ENABLE != STRB_ENABLE ||
        s_axis[n].LAST_ENABLE != LAST_ENABLE ||
        s_axis[n].ID_ENABLE   != ID_ENABLE   || s_axis[n].ID_WIDTH    != ID_WIDTH    ||
        s_axis[n].DEST_ENABLE != DEST_ENABLE || s_axis[n].DEST_WIDTH  != DEST_WIDTH  ||
        s_axis[n].USER_ENABLE != USER_ENABLE || s_axis[n].USER_WIDTH  != USER_WIDTH) begin : g_err
        $error("axis_mux: s_axis[%0d] parameters differ from s_axis[0]", n);
    end
end

if (m_axis.DATA_WIDTH  != DATA_WIDTH  || m_axis.KEEP_WIDTH  != KEEP_WIDTH  ||
    m_axis.KEEP_ENABLE != KEEP_ENABLE || m_axis.STRB_ENABLE != STRB_ENABLE ||
    m_axis.LAST_ENABLE != LAST_ENABLE ||
    m_axis.ID_ENABLE   != ID_ENABLE   || m_axis.ID_WIDTH    != ID_WIDTH    ||
    m_axis.DEST_ENABLE != DEST_ENABLE || m_axis.DEST_WIDTH  != DEST_WIDTH  ||
    m_axis.USER_ENABLE != USER_ENABLE || m_axis.USER_WIDTH  != USER_WIDTH) begin : g_m_check
    $error("axis_mux: m_axis parameters differ from s_axis[0]");
end

// payload of one transfer
typedef struct packed {
    logic [DATA_WIDTH-1:0] tdata;
    logic [KEEP_WIDTH-1:0] tkeep;
    logic [KEEP_WIDTH-1:0] tstrb;
    logic                  tlast;
    logic [ID_WIDTH-1:0]   tid;
    logic [DEST_WIDTH-1:0] tdest;
    logic [USER_WIDTH-1:0] tuser;
} beat_t;

typedef enum logic [1:0] {
    STORE_NONE,
    STORE_IN_TO_OUT,
    STORE_IN_TO_TEMP,
    STORE_TEMP_TO_OUT
} store_t;

// control registers
logic [CL_S_COUNT-1:0] select_reg;
logic                  frame_reg;
logic [S_COUNT-1:0]    s_axis_tready_reg;

logic [CL_S_COUNT-1:0] select_next;
logic                  frame_next;

// output control registers
logic m_axis_tvalid_reg, m_axis_tvalid_next;
logic temp_tvalid_reg, temp_tvalid_next;
logic m_ready_int_reg;

// datapath registers, no reset
beat_t out_reg;
beat_t temp_reg;

store_t store;

beat_t                 s_beat [S_COUNT];
logic [S_COUNT-1:0]    s_tvalid;
logic [S_COUNT-1:0]    s_tready;
logic                  s_xfer;
logic                  s_last;
logic                  s_start;
logic                  m_tvalid_int;
logic                  m_ready_int_early;
logic [KEEP_WIDTH-1:0] m_tkeep;

for (genvar n = 0; n < S_COUNT; n++) begin : g_s_axis
    assign s_beat[n].tdata = s_axis[n].tdata;
    assign s_beat[n].tkeep = s_axis[n].tkeep;
    assign s_beat[n].tstrb = s_axis[n].tstrb;
    assign s_beat[n].tlast = s_axis[n].tlast;
    assign s_beat[n].tid   = s_axis[n].tid;
    assign s_beat[n].tdest = s_axis[n].tdest;
    assign s_beat[n].tuser = s_axis[n].tuser;

    assign s_tvalid[n]      = s_axis[n].tvalid;
    assign s_tready[n]      = s_axis_tready_reg[n] && enable;
    assign s_axis[n].tready = s_tready[n];
end

// selected input
assign s_xfer  = s_tvalid[select_reg] && s_tready[select_reg];
assign s_last  = LAST_ENABLE ? s_beat[select_reg].tlast : 1'b1;
// start of frame, selected input has data
assign s_start = !frame_reg && enable && |(s_tvalid & (S_COUNT'(1) << select));

assign m_tvalid_int = s_xfer && frame_reg;

always_comb begin
    select_next = select_reg;
    frame_next  = frame_reg;

    if (s_xfer && s_last) begin
        frame_next = 1'b0;
    end

    if (s_start) begin
        frame_next  = 1'b1;
        select_next = select;
    end
end

always_ff @(posedge clk) begin
    if (rst) begin
        select_reg        <= '0;
        frame_reg         <= 1'b0;
        s_axis_tready_reg <= '0;
    end else begin
        select_reg        <= select_next;
        frame_reg         <= frame_next;
        s_axis_tready_reg <= S_COUNT'(m_ready_int_early && frame_next) << select_next;
    end
end

assign m_tkeep = KEEP_ENABLE ? out_reg.tkeep : '1;

assign m_axis.tdata  = out_reg.tdata;
assign m_axis.tkeep  = m_tkeep;
assign m_axis.tstrb  = STRB_ENABLE ? out_reg.tstrb : m_tkeep;
assign m_axis.tlast  = LAST_ENABLE ? out_reg.tlast : 1'b0;
assign m_axis.tid    = ID_ENABLE   ? out_reg.tid   : '0;
assign m_axis.tdest  = DEST_ENABLE ? out_reg.tdest : '0;
assign m_axis.tuser  = USER_ENABLE ? out_reg.tuser : '0;
assign m_axis.tvalid = m_axis_tvalid_reg;

// ready next cycle if output is ready or temp will not be filled (output empty or no input)
assign m_ready_int_early = m_axis.tready || (!temp_tvalid_reg && (!m_axis_tvalid_reg || !m_tvalid_int));

always_comb begin
    m_axis_tvalid_next = m_axis_tvalid_reg;
    temp_tvalid_next   = temp_tvalid_reg;
    store              = STORE_NONE;

    if (m_ready_int_reg) begin
        if (m_axis.tready || !m_axis_tvalid_reg) begin
            // output ready or not valid, input to output
            m_axis_tvalid_next = m_tvalid_int;
            store = STORE_IN_TO_OUT;
        end else begin
            // output not ready, input to temp
            temp_tvalid_next = m_tvalid_int;
            store = STORE_IN_TO_TEMP;
        end
    end else if (m_axis.tready) begin
        // input not ready, output ready, temp to output
        m_axis_tvalid_next = temp_tvalid_reg;
        temp_tvalid_next   = 1'b0;
        store = STORE_TEMP_TO_OUT;
    end
end

always_ff @(posedge clk) begin
    if (rst) begin
        m_axis_tvalid_reg <= 1'b0;
        temp_tvalid_reg   <= 1'b0;
        m_ready_int_reg   <= 1'b0;
    end else begin
        m_axis_tvalid_reg <= m_axis_tvalid_next;
        temp_tvalid_reg   <= temp_tvalid_next;
        m_ready_int_reg   <= m_ready_int_early;
    end
end

// datapath
always_ff @(posedge clk) begin
    case (store)
        STORE_IN_TO_OUT:   out_reg  <= s_beat[select_reg];
        STORE_IN_TO_TEMP:  temp_reg <= s_beat[select_reg];
        STORE_TEMP_TO_OUT: out_reg  <= temp_reg;
        STORE_NONE: ;
        default: ;
    endcase
end

endmodule

`resetall
