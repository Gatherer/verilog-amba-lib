/*

Copyright (c) 2018 Alex Forencich
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
 * AXI4-Stream demultiplexer
 * widths and enables are taken from s_axis, output tdest width from m_axis
 * output tdest is the lower part of input tdest
 * disabled tstrb follows tkeep, disabled tlast is 0
 * without tlast every beat is a frame
 */
module axis_demux #(
    // number of AXI stream outputs
    parameter  int M_COUNT     = 4,
    // route via upper tdest bits, select and drop are ignored
    parameter  bit TDEST_ROUTE = 1'b0,
    localparam int CL_M_COUNT  = M_COUNT > 1 ? $clog2(M_COUNT) : 1
) (
    input  wire                  clk,
    input  wire                  rst,

    axis_if.slave                s_axis,
    axis_if.master               m_axis [M_COUNT],

    /*
     * Control
     */
    input  wire                  enable,
    // unused with TDEST_ROUTE
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire                  drop,
    input  wire [CL_M_COUNT-1:0] select
    /* verilator lint_on UNUSEDSIGNAL */
);

localparam int DATA_WIDTH   = s_axis.DATA_WIDTH;
localparam int KEEP_WIDTH   = s_axis.KEEP_WIDTH;
localparam bit KEEP_ENABLE  = s_axis.KEEP_ENABLE;
localparam bit STRB_ENABLE  = s_axis.STRB_ENABLE;
localparam bit LAST_ENABLE  = s_axis.LAST_ENABLE;
localparam bit ID_ENABLE    = s_axis.ID_ENABLE;
localparam int ID_WIDTH     = s_axis.ID_WIDTH;
localparam bit DEST_ENABLE  = s_axis.DEST_ENABLE;
localparam int S_DEST_WIDTH = s_axis.DEST_WIDTH;
localparam int M_DEST_WIDTH = m_axis[0].DEST_WIDTH;
localparam bit USER_ENABLE  = s_axis.USER_ENABLE;
localparam int USER_WIDTH   = s_axis.USER_WIDTH;

// parameter checks
if (M_COUNT < 1) begin : g_count_check
    $error("axis_demux: M_COUNT must be at least 1 (is %0d)", M_COUNT);
end

for (genvar n = 0; n < M_COUNT; n++) begin : g_m_check
    if (m_axis[n].DATA_WIDTH  != DATA_WIDTH  || m_axis[n].KEEP_WIDTH  != KEEP_WIDTH  ||
        m_axis[n].KEEP_ENABLE != KEEP_ENABLE || m_axis[n].STRB_ENABLE != STRB_ENABLE ||
        m_axis[n].LAST_ENABLE != LAST_ENABLE ||
        m_axis[n].ID_ENABLE   != ID_ENABLE   || m_axis[n].ID_WIDTH    != ID_WIDTH    ||
        m_axis[n].DEST_ENABLE != DEST_ENABLE || m_axis[n].DEST_WIDTH  != M_DEST_WIDTH ||
        m_axis[n].USER_ENABLE != USER_ENABLE || m_axis[n].USER_WIDTH  != USER_WIDTH) begin : g_err
        $error("axis_demux: m_axis[%0d] parameters differ from s_axis", n);
    end
end

if (TDEST_ROUTE && !DEST_ENABLE) begin : g_route_dest_check
    $error("axis_demux: TDEST_ROUTE set requires DEST_ENABLE set");
end

if (S_DEST_WIDTH < M_DEST_WIDTH) begin : g_dest_width_check
    $error("axis_demux: s_axis tdest smaller than m_axis tdest (%0d < %0d)", S_DEST_WIDTH, M_DEST_WIDTH);
end

if (TDEST_ROUTE && S_DEST_WIDTH < M_DEST_WIDTH + $clog2(M_COUNT)) begin : g_route_width_check
    $error("axis_demux: s_axis tdest too small for m_axis tdest and port count (is %0d)", S_DEST_WIDTH);
end

// payload of one transfer
typedef struct packed {
    logic [DATA_WIDTH-1:0]   tdata;
    logic [KEEP_WIDTH-1:0]   tkeep;
    logic [KEEP_WIDTH-1:0]   tstrb;
    logic                    tlast;
    logic [ID_WIDTH-1:0]     tid;
    logic [M_DEST_WIDTH-1:0] tdest;
    logic [USER_WIDTH-1:0]   tuser;
} beat_t;

typedef enum logic [1:0] {
    STORE_NONE,
    STORE_IN_TO_OUT,
    STORE_IN_TO_TEMP,
    STORE_TEMP_TO_OUT
} store_t;

// control registers
logic [CL_M_COUNT-1:0] select_reg;
logic                  drop_reg;
logic                  frame_reg;
logic                  s_axis_tready_reg;

logic [CL_M_COUNT-1:0] route_select;
logic                  route_drop;
logic [CL_M_COUNT-1:0] select_ctl;
logic                  drop_ctl;
logic                  s_axis_tready_int;
logic                  s_xfer;
logic                  s_last;
logic                  s_start;

// output control registers
logic [M_COUNT-1:0] m_axis_tvalid_reg, m_axis_tvalid_next;
logic [M_COUNT-1:0] temp_tvalid_reg, temp_tvalid_next;
logic               m_ready_int_reg;

// datapath registers, no reset
beat_t out_reg;
beat_t temp_reg;

store_t store;

// upper bits only used with TDEST_ROUTE
/* verilator lint_off UNUSEDSIGNAL */
logic [S_DEST_WIDTH-1:0] s_tdest;
/* verilator lint_on UNUSEDSIGNAL */

beat_t                 s_beat;
logic [M_COUNT-1:0]    m_tvalid_int;
logic [M_COUNT-1:0]    m_axis_tready;
logic                  m_axis_tready_all;
logic                  m_ready_int_early;
logic [KEEP_WIDTH-1:0] m_tkeep;

assign s_beat.tdata = s_axis.tdata;
assign s_beat.tkeep = s_axis.tkeep;
assign s_beat.tstrb = s_axis.tstrb;
assign s_beat.tlast = s_axis.tlast;
assign s_beat.tid   = s_axis.tid;
assign s_tdest      = s_axis.tdest;
assign s_beat.tdest = s_tdest[M_DEST_WIDTH-1:0];
assign s_beat.tuser = s_axis.tuser;

// output port per frame, out of range ports are dropped
localparam bit [CL_M_COUNT:0] PORT_LIMIT = (CL_M_COUNT+1)'(M_COUNT);

if (!TDEST_ROUTE) begin : g_route_select
    assign route_select = select;
    assign route_drop   = drop || {1'b0, select} >= PORT_LIMIT;
end else if (M_COUNT > 1) begin : g_route_tdest
    assign route_select = s_tdest[S_DEST_WIDTH-1 -: CL_M_COUNT];
    assign route_drop   = {1'b0, route_select} >= PORT_LIMIT;
end else begin : g_route_single
    assign route_select = '0;
    assign route_drop   = 1'b0;
end

assign s_axis_tready_int = s_axis_tready_reg && enable;
assign s_axis.tready     = s_axis_tready_int;

assign s_xfer  = s_axis.tvalid && s_axis_tready_int;
assign s_last  = LAST_ENABLE ? s_axis.tlast : 1'b1;
assign s_start = s_xfer && !frame_reg;

// take select and drop on first beat, hold until end of frame
assign select_ctl = s_start ? route_select : select_reg;
assign drop_ctl   = s_start ? route_drop   : drop_reg;

assign m_tvalid_int = M_COUNT'(s_xfer && !drop_ctl) << select_ctl;

always_ff @(posedge clk) begin
    if (rst) begin
        select_reg        <= '0;
        drop_reg          <= 1'b0;
        frame_reg         <= 1'b0;
        s_axis_tready_reg <= 1'b0;
    end else begin
        s_axis_tready_reg <= m_ready_int_early || drop_ctl;

        if (s_xfer) begin
            if (s_last) begin
                frame_reg <= 1'b0;
                drop_reg  <= 1'b0;
            end else if (!frame_reg) begin
                // multi beat frame, keep selection
                frame_reg  <= 1'b1;
                select_reg <= select_ctl;
                drop_reg   <= drop_ctl;
            end
        end
    end
end

assign m_tkeep = KEEP_ENABLE ? out_reg.tkeep : '1;

for (genvar n = 0; n < M_COUNT; n++) begin : g_m_axis
    assign m_axis_tready[n] = m_axis[n].tready;

    assign m_axis[n].tdata  = out_reg.tdata;
    assign m_axis[n].tkeep  = m_tkeep;
    assign m_axis[n].tstrb  = STRB_ENABLE ? out_reg.tstrb : m_tkeep;
    assign m_axis[n].tlast  = LAST_ENABLE ? out_reg.tlast : 1'b0;
    assign m_axis[n].tid    = ID_ENABLE   ? out_reg.tid   : '0;
    assign m_axis[n].tdest  = DEST_ENABLE ? out_reg.tdest : '0;
    assign m_axis[n].tuser  = USER_ENABLE ? out_reg.tuser : '0;
    assign m_axis[n].tvalid = m_axis_tvalid_reg[n];
end

// selected output accepts pending data, also true if no output is valid
assign m_axis_tready_all = &(m_axis_tready | ~m_axis_tvalid_reg);

// ready next cycle if output is ready or temp will not be filled (no input)
assign m_ready_int_early = m_axis_tready_all || (!(|temp_tvalid_reg) && !(|m_tvalid_int));

always_comb begin
    m_axis_tvalid_next = m_axis_tvalid_reg;
    temp_tvalid_next   = temp_tvalid_reg;
    store              = STORE_NONE;

    if (m_ready_int_reg) begin
        if (m_axis_tready_all) begin
            // output ready or not valid, input to output
            m_axis_tvalid_next = m_tvalid_int;
            store = STORE_IN_TO_OUT;
        end else begin
            // output not ready, input to temp
            temp_tvalid_next = m_tvalid_int;
            store = STORE_IN_TO_TEMP;
        end
    end else if (m_axis_tready_all) begin
        // input not ready, output ready, temp to output
        m_axis_tvalid_next = temp_tvalid_reg;
        temp_tvalid_next   = '0;
        store = STORE_TEMP_TO_OUT;
    end
end

always_ff @(posedge clk) begin
    if (rst) begin
        m_axis_tvalid_reg <= '0;
        temp_tvalid_reg   <= '0;
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
        STORE_IN_TO_OUT:   out_reg  <= s_beat;
        STORE_IN_TO_TEMP:  temp_reg <= s_beat;
        STORE_TEMP_TO_OUT: out_reg  <= temp_reg;
        STORE_NONE: ;
        default: ;
    endcase
end

endmodule

`resetall
