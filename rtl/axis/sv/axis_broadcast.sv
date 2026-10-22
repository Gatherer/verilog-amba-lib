/*

Copyright (c) 2019 Alex Forencich
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
 * AXI4-Stream broadcaster
 * widths and enables are taken from s_axis
 * disabled tstrb follows tkeep
 */
module axis_broadcast #(
    // number of AXI stream outputs
    parameter int M_COUNT = 4
) (
    input  wire    clk,
    input  wire    rst,

    axis_if.slave  s_axis,
    axis_if.master m_axis [M_COUNT]
);

localparam int DATA_WIDTH  = s_axis.DATA_WIDTH;
localparam int KEEP_WIDTH  = s_axis.KEEP_WIDTH;
localparam bit KEEP_ENABLE = s_axis.KEEP_ENABLE;
localparam bit STRB_ENABLE = s_axis.STRB_ENABLE;
localparam bit LAST_ENABLE = s_axis.LAST_ENABLE;
localparam bit ID_ENABLE   = s_axis.ID_ENABLE;
localparam int ID_WIDTH    = s_axis.ID_WIDTH;
localparam bit DEST_ENABLE = s_axis.DEST_ENABLE;
localparam int DEST_WIDTH  = s_axis.DEST_WIDTH;
localparam bit USER_ENABLE = s_axis.USER_ENABLE;
localparam int USER_WIDTH  = s_axis.USER_WIDTH;

// parameter checks
if (M_COUNT < 1) begin : g_count_check
    $error("axis_broadcast: M_COUNT must be at least 1 (is %0d)", M_COUNT);
end

for (genvar n = 0; n < M_COUNT; n++) begin : g_m_check
    if (m_axis[n].DATA_WIDTH  != DATA_WIDTH  || m_axis[n].KEEP_WIDTH  != KEEP_WIDTH  ||
        m_axis[n].KEEP_ENABLE != KEEP_ENABLE || m_axis[n].STRB_ENABLE != STRB_ENABLE ||
        m_axis[n].LAST_ENABLE != LAST_ENABLE ||
        m_axis[n].ID_ENABLE   != ID_ENABLE   || m_axis[n].ID_WIDTH    != ID_WIDTH    ||
        m_axis[n].DEST_ENABLE != DEST_ENABLE || m_axis[n].DEST_WIDTH  != DEST_WIDTH  ||
        m_axis[n].USER_ENABLE != USER_ENABLE || m_axis[n].USER_WIDTH  != USER_WIDTH) begin : g_err
        $error("axis_broadcast: m_axis[%0d] parameters differ from s_axis", n);
    end
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
logic               s_axis_tready_reg;
logic [M_COUNT-1:0] m_axis_tvalid_reg, m_axis_tvalid_next;
logic               temp_tvalid_reg, temp_tvalid_next;

// datapath registers, no reset
beat_t out_reg;
beat_t temp_reg;

store_t store;

beat_t              s_beat;
logic [M_COUNT-1:0] m_axis_tready;
logic               m_axis_tready_all;
logic               s_axis_tready_early;
logic [KEEP_WIDTH-1:0] m_tkeep;

assign s_beat.tdata = s_axis.tdata;
assign s_beat.tkeep = s_axis.tkeep;
assign s_beat.tstrb = s_axis.tstrb;
assign s_beat.tlast = s_axis.tlast;
assign s_beat.tid   = s_axis.tid;
assign s_beat.tdest = s_axis.tdest;
assign s_beat.tuser = s_axis.tuser;

assign s_axis.tready = s_axis_tready_reg;

assign m_tkeep = KEEP_ENABLE ? out_reg.tkeep : '1;

for (genvar n = 0; n < M_COUNT; n++) begin : g_m_axis
    assign m_axis_tready[n] = m_axis[n].tready;

    assign m_axis[n].tdata  = out_reg.tdata;
    assign m_axis[n].tkeep  = m_tkeep;
    assign m_axis[n].tstrb  = STRB_ENABLE ? out_reg.tstrb : m_tkeep;
    assign m_axis[n].tlast  = LAST_ENABLE ? out_reg.tlast : 1'b1;
    assign m_axis[n].tid    = ID_ENABLE   ? out_reg.tid   : '0;
    assign m_axis[n].tdest  = DEST_ENABLE ? out_reg.tdest : '0;
    assign m_axis[n].tuser  = USER_ENABLE ? out_reg.tuser : '0;
    assign m_axis[n].tvalid = m_axis_tvalid_reg[n];
end

// all outputs with pending data accept it, also true if no output is valid
assign m_axis_tready_all = &(m_axis_tready | ~m_axis_tvalid_reg);

// ready next cycle if output is ready or temp will not be filled (no input)
assign s_axis_tready_early = m_axis_tready_all || (!temp_tvalid_reg && !s_axis.tvalid);

always_comb begin
    m_axis_tvalid_next = m_axis_tvalid_reg & ~m_axis_tready;
    temp_tvalid_next   = temp_tvalid_reg;
    store              = STORE_NONE;

    if (s_axis_tready_reg) begin
        if (m_axis_tready_all) begin
            // output ready or not valid, input to output
            m_axis_tvalid_next = {M_COUNT{s_axis.tvalid}};
            store = STORE_IN_TO_OUT;
        end else begin
            // output not ready, input to temp
            temp_tvalid_next = s_axis.tvalid;
            store = STORE_IN_TO_TEMP;
        end
    end else if (m_axis_tready_all) begin
        // input not ready, output ready, temp to output
        m_axis_tvalid_next = {M_COUNT{temp_tvalid_reg}};
        temp_tvalid_next   = 1'b0;
        store = STORE_TEMP_TO_OUT;
    end
end

always_ff @(posedge clk) begin
    if (rst) begin
        s_axis_tready_reg <= 1'b0;
        m_axis_tvalid_reg <= '0;
        temp_tvalid_reg   <= 1'b0;
    end else begin
        s_axis_tready_reg <= s_axis_tready_early;
        m_axis_tvalid_reg <= m_axis_tvalid_next;
        temp_tvalid_reg   <= temp_tvalid_next;
    end
end

// datapath
always_ff @(posedge clk) begin
    case (store)
        STORE_IN_TO_OUT:   out_reg  <= s_beat;
        STORE_IN_TO_TEMP:  temp_reg <= s_beat;
        STORE_TEMP_TO_OUT: out_reg  <= temp_reg;
        default: ;
    endcase
end

endmodule

`resetall
