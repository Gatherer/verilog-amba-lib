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
 * AXI4-Stream arbitrated multiplexer
 * widths and enables are taken from s_axis[0], tid width of output from m_axis
 * disabled tstrb follows tkeep, disabled tlast is 0
 * without tlast every beat is arbitrated
 */
module axis_arb_mux #(
    // number of AXI stream inputs
    parameter  int S_COUNT               = 4,
    // update tid with routing information
    parameter  bit UPDATE_TID            = 1'b0,
    // select round robin arbitration
    parameter  bit ARB_TYPE_ROUND_ROBIN  = 1'b0,
    // LSB priority selection
    parameter  bit ARB_LSB_HIGH_PRIORITY = 1'b1
) (
    input  wire    clk,
    input  wire    rst,

    axis_if.slave  s_axis [S_COUNT],
    axis_if.master m_axis
);

localparam int CL_S_COUNT  = S_COUNT > 1 ? $clog2(S_COUNT) : 1;

localparam int DATA_WIDTH  = s_axis[0].DATA_WIDTH;
localparam int KEEP_WIDTH  = s_axis[0].KEEP_WIDTH;
localparam bit KEEP_ENABLE = s_axis[0].KEEP_ENABLE;
localparam bit STRB_ENABLE = s_axis[0].STRB_ENABLE;
localparam bit LAST_ENABLE = s_axis[0].LAST_ENABLE;
localparam bit ID_ENABLE   = s_axis[0].ID_ENABLE;
localparam int S_ID_WIDTH  = s_axis[0].ID_WIDTH;
localparam bit DEST_ENABLE = s_axis[0].DEST_ENABLE;
localparam int DEST_WIDTH  = s_axis[0].DEST_WIDTH;
localparam bit USER_ENABLE = s_axis[0].USER_ENABLE;
localparam int USER_WIDTH  = s_axis[0].USER_WIDTH;
localparam int M_ID_WIDTH  = m_axis.ID_WIDTH;

// parameter checks
if (S_COUNT < 1) begin : g_count_check
    $error("axis_arb_mux: S_COUNT must be at least 1 (is %0d)", S_COUNT);
end

for (genvar n = 1; n < S_COUNT; n++) begin : g_s_check
    if (s_axis[n].DATA_WIDTH  != DATA_WIDTH  || s_axis[n].KEEP_WIDTH  != KEEP_WIDTH  ||
        s_axis[n].KEEP_ENABLE != KEEP_ENABLE || s_axis[n].STRB_ENABLE != STRB_ENABLE ||
        s_axis[n].LAST_ENABLE != LAST_ENABLE ||
        s_axis[n].ID_ENABLE   != ID_ENABLE   || s_axis[n].ID_WIDTH    != S_ID_WIDTH  ||
        s_axis[n].DEST_ENABLE != DEST_ENABLE || s_axis[n].DEST_WIDTH  != DEST_WIDTH  ||
        s_axis[n].USER_ENABLE != USER_ENABLE || s_axis[n].USER_WIDTH  != USER_WIDTH) begin : g_err
        $error("axis_arb_mux: s_axis[%0d] parameters differ from s_axis[0]", n);
    end
end

// m_axis tid may be wider
if (m_axis.DATA_WIDTH  != DATA_WIDTH  || m_axis.KEEP_WIDTH  != KEEP_WIDTH  ||
    m_axis.KEEP_ENABLE != KEEP_ENABLE || m_axis.STRB_ENABLE != STRB_ENABLE ||
    m_axis.LAST_ENABLE != LAST_ENABLE || m_axis.ID_ENABLE   != ID_ENABLE   ||
    m_axis.DEST_ENABLE != DEST_ENABLE || m_axis.DEST_WIDTH  != DEST_WIDTH  ||
    m_axis.USER_ENABLE != USER_ENABLE || m_axis.USER_WIDTH  != USER_WIDTH) begin : g_m_check
    $error("axis_arb_mux: m_axis parameters differ from s_axis[0]");
end

if (M_ID_WIDTH < S_ID_WIDTH) begin : g_id_check
    $error("axis_arb_mux: m_axis ID_WIDTH %0d smaller than s_axis ID_WIDTH %0d", M_ID_WIDTH, S_ID_WIDTH);
end

if (UPDATE_TID && !ID_ENABLE) begin : g_update_tid_check
    $error("axis_arb_mux: UPDATE_TID requires ID_ENABLE");
end

if (UPDATE_TID && S_COUNT > 1 && M_ID_WIDTH < CL_S_COUNT) begin : g_update_tid_width_check
    $error("axis_arb_mux: m_axis ID_WIDTH too small for port count");
end

// payload of one input transfer
typedef struct packed {
    logic [DATA_WIDTH-1:0] tdata;
    logic [KEEP_WIDTH-1:0] tkeep;
    logic [KEEP_WIDTH-1:0] tstrb;
    logic                  tlast;
    logic [S_ID_WIDTH-1:0] tid;
    logic [DEST_WIDTH-1:0] tdest;
    logic [USER_WIDTH-1:0] tuser;
} s_beat_t;

// payload of one output transfer
typedef struct packed {
    logic [DATA_WIDTH-1:0] tdata;
    logic [KEEP_WIDTH-1:0] tkeep;
    logic [KEEP_WIDTH-1:0] tstrb;
    logic                  tlast;
    logic [M_ID_WIDTH-1:0] tid;
    logic [DEST_WIDTH-1:0] tdest;
    logic [USER_WIDTH-1:0] tuser;
} m_beat_t;

typedef enum logic [1:0] {
    STORE_NONE,
    STORE_IN_TO_OUT,
    STORE_IN_TO_TEMP,
    STORE_TEMP_TO_OUT
} store_t;

// arbiter
logic [S_COUNT-1:0]    request;
logic [S_COUNT-1:0]    acknowledge;
logic [S_COUNT-1:0]    grant;
logic                  grant_valid;
logic [CL_S_COUNT-1:0] grant_encoded;

// input registers to pipeline arbitration delay
logic [S_COUNT-1:0]    s_tvalid_reg;

// input datapath registers, no reset
s_beat_t               s_beat_reg [S_COUNT];

s_beat_t               s_beat [S_COUNT];
logic [S_COUNT-1:0]    s_tvalid;
logic [S_COUNT-1:0]    s_tready;
logic [S_COUNT-1:0]    s_last_reg;

// output control registers
logic m_axis_tvalid_reg, m_axis_tvalid_next;
logic temp_tvalid_reg, temp_tvalid_next;
logic m_ready_int_reg;

// output datapath registers, no reset
m_beat_t out_reg;
m_beat_t temp_reg;

store_t store;

m_beat_t               m_beat_int;
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
    assign s_axis[n].tready = s_tready[n];

    // without tlast every beat ends the grant
    assign s_last_reg[n] = LAST_ENABLE ? s_beat_reg[n].tlast : 1'b1;
end

assign s_tready = ~s_tvalid_reg | ({S_COUNT{m_ready_int_reg}} & grant);

arbiter #(
    .PORTS(S_COUNT),
    .ARB_TYPE_ROUND_ROBIN(ARB_TYPE_ROUND_ROBIN),
    .ARB_BLOCK(1'b1),
    .ARB_BLOCK_ACK(1'b1),
    .ARB_LSB_HIGH_PRIORITY(ARB_LSB_HIGH_PRIORITY)
) arb_inst (
    .clk(clk),
    .rst(rst),
    .request(request),
    .acknowledge(acknowledge),
    .grant(grant),
    .grant_valid(grant_valid),
    .grant_encoded(grant_encoded)
);

assign request     = s_tvalid | (s_tvalid_reg & ~grant);
assign acknowledge = grant & s_tvalid_reg & {S_COUNT{m_ready_int_reg}} & s_last_reg;

// selected input
assign m_beat_int.tdata = s_beat_reg[grant_encoded].tdata;
assign m_beat_int.tkeep = s_beat_reg[grant_encoded].tkeep;
assign m_beat_int.tstrb = s_beat_reg[grant_encoded].tstrb;
assign m_beat_int.tlast = s_beat_reg[grant_encoded].tlast;
assign m_beat_int.tdest = s_beat_reg[grant_encoded].tdest;
assign m_beat_int.tuser = s_beat_reg[grant_encoded].tuser;

if (UPDATE_TID && S_COUNT > 1) begin : g_update_tid
    // port number in tid msbs
    always_comb begin
        m_beat_int.tid = M_ID_WIDTH'(s_beat_reg[grant_encoded].tid);
        m_beat_int.tid[M_ID_WIDTH-1 -: CL_S_COUNT] = grant_encoded;
    end
end else begin : g_tid
    assign m_beat_int.tid = M_ID_WIDTH'(s_beat_reg[grant_encoded].tid);
end

assign m_tvalid_int = s_tvalid_reg[grant_encoded] && m_ready_int_reg && grant_valid;

always_ff @(posedge clk) begin
    if (rst) begin
        s_tvalid_reg <= '0;
    end else begin
        for (int i = 0; i < S_COUNT; i++) begin
            if (s_tready[i]) begin
                s_tvalid_reg[i] <= s_tvalid[i];
            end
        end
    end
end

// input datapath
always_ff @(posedge clk) begin
    for (int i = 0; i < S_COUNT; i++) begin
        if (s_tready[i]) begin
            s_beat_reg[i] <= s_beat[i];
        end
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

// output datapath
always_ff @(posedge clk) begin
    case (store)
        STORE_IN_TO_OUT:   out_reg  <= m_beat_int;
        STORE_IN_TO_TEMP:  temp_reg <= m_beat_int;
        STORE_TEMP_TO_OUT: out_reg  <= temp_reg;
        STORE_NONE: ;
        default: ;
    endcase
end

endmodule

`resetall
