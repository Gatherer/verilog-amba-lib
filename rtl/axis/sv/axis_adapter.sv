/*

Copyright (c) 2014-2023 Alex Forencich
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
 * AXI4-Stream bus width adapter
 * data and keep widths are taken from s_axis and m_axis,
 * all other parameters from s_axis
 * without tkeep the byte size equals the data width
 * disabled tstrb follows tkeep, disabled tlast is 0
 */
module axis_adapter (
    // unused in bypass
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire    clk,
    input  wire    rst,
    /* verilator lint_on UNUSEDSIGNAL */

    axis_if.slave  s_axis,
    axis_if.master m_axis
);

localparam int S_DATA_WIDTH = s_axis.DATA_WIDTH;
localparam int S_KEEP_WIDTH = s_axis.KEEP_WIDTH;
localparam int M_DATA_WIDTH = m_axis.DATA_WIDTH;
localparam int M_KEEP_WIDTH = m_axis.KEEP_WIDTH;
localparam bit KEEP_ENABLE  = s_axis.KEEP_ENABLE;
localparam bit STRB_ENABLE  = s_axis.STRB_ENABLE;
localparam bit LAST_ENABLE  = s_axis.LAST_ENABLE;
localparam bit ID_ENABLE    = s_axis.ID_ENABLE;
localparam int ID_WIDTH     = s_axis.ID_WIDTH;
localparam bit DEST_ENABLE  = s_axis.DEST_ENABLE;
localparam int DEST_WIDTH   = s_axis.DEST_WIDTH;
localparam bit USER_ENABLE  = s_axis.USER_ENABLE;
localparam int USER_WIDTH   = s_axis.USER_WIDTH;

// one keep bit per byte lane, single lane without tkeep
localparam int S_BYTE_LANES = KEEP_ENABLE ? S_KEEP_WIDTH : 1;
localparam int M_BYTE_LANES = KEEP_ENABLE ? M_KEEP_WIDTH : 1;

// bus byte sizes (must be identical)
localparam int S_BYTE_SIZE = S_DATA_WIDTH / S_BYTE_LANES;
localparam int M_BYTE_SIZE = M_DATA_WIDTH / M_BYTE_LANES;

// parameter checks
if (m_axis.KEEP_ENABLE != KEEP_ENABLE || m_axis.STRB_ENABLE != STRB_ENABLE ||
    m_axis.LAST_ENABLE != LAST_ENABLE ||
    m_axis.ID_ENABLE   != ID_ENABLE   || m_axis.ID_WIDTH    != ID_WIDTH    ||
    m_axis.DEST_ENABLE != DEST_ENABLE || m_axis.DEST_WIDTH  != DEST_WIDTH  ||
    m_axis.USER_ENABLE != USER_ENABLE || m_axis.USER_WIDTH  != USER_WIDTH) begin : g_m_check
    $error("axis_adapter: m_axis parameters differ from s_axis");
end

if (S_BYTE_SIZE * S_BYTE_LANES != S_DATA_WIDTH) begin : g_s_width_check
    $error("axis_adapter: s_axis data width not evenly divisible");
end

if (M_BYTE_SIZE * M_BYTE_LANES != M_DATA_WIDTH) begin : g_m_width_check
    $error("axis_adapter: m_axis data width not evenly divisible");
end

if (S_BYTE_SIZE != M_BYTE_SIZE) begin : g_byte_size_check
    $error("axis_adapter: byte size mismatch (s %0d, m %0d)", S_BYTE_SIZE, M_BYTE_SIZE);
end

if (S_BYTE_LANES % M_BYTE_LANES != 0 && M_BYTE_LANES % S_BYTE_LANES != 0) begin : g_ratio_check
    $error("axis_adapter: bus width ratio must be an integer");
end

// payload of one input or output transfer
typedef struct packed {
    logic [S_DATA_WIDTH-1:0] tdata;
    logic [S_BYTE_LANES-1:0] tkeep;
    logic [S_BYTE_LANES-1:0] tstrb;
    logic                    tlast;
    logic [ID_WIDTH-1:0]     tid;
    logic [DEST_WIDTH-1:0]   tdest;
    logic [USER_WIDTH-1:0]   tuser;
} s_beat_t;

typedef struct packed {
    logic [M_DATA_WIDTH-1:0] tdata;
    logic [M_BYTE_LANES-1:0] tkeep;
    logic [M_BYTE_LANES-1:0] tstrb;
    logic                    tlast;
    logic [ID_WIDTH-1:0]     tid;
    logic [DEST_WIDTH-1:0]   tdest;
    logic [USER_WIDTH-1:0]   tuser;
} m_beat_t;

typedef enum logic [1:0] {
    STORE_NONE,
    STORE_TO_OUT,
    STORE_TO_SKID
} store_t;

logic [S_BYTE_LANES-1:0] s_tkeep;
s_beat_t s_beat;
// disabled fields are unused
/* verilator lint_off UNUSEDSIGNAL */
m_beat_t m_beat;
/* verilator lint_on UNUSEDSIGNAL */

// input, disabled signals are constant
assign s_beat.tdata = s_axis.tdata;

if (KEEP_ENABLE) begin : g_s_keep
    assign s_tkeep = s_axis.tkeep;
end else begin : g_s_no_keep
    assign s_tkeep = '1;
end

assign s_beat.tkeep = s_tkeep;

if (STRB_ENABLE) begin : g_s_strb
    assign s_beat.tstrb = s_axis.tstrb[S_BYTE_LANES-1:0];
end else begin : g_s_no_strb
    assign s_beat.tstrb = s_tkeep;
end

if (LAST_ENABLE) begin : g_s_last
    assign s_beat.tlast = s_axis.tlast;
end else begin : g_s_no_last
    assign s_beat.tlast = 1'b0;
end

if (ID_ENABLE) begin : g_s_id
    assign s_beat.tid = s_axis.tid;
end else begin : g_s_no_id
    assign s_beat.tid = '0;
end

if (DEST_ENABLE) begin : g_s_dest
    assign s_beat.tdest = s_axis.tdest;
end else begin : g_s_no_dest
    assign s_beat.tdest = '0;
end

if (USER_ENABLE) begin : g_s_user
    assign s_beat.tuser = s_axis.tuser;
end else begin : g_s_no_user
    assign s_beat.tuser = '0;
end

// output
assign m_axis.tdata = m_beat.tdata;

if (KEEP_ENABLE) begin : g_m_keep
    assign m_axis.tkeep = m_beat.tkeep;
    assign m_axis.tstrb = m_beat.tstrb;
end else begin : g_m_no_keep
    // single lane, widen to interface width
    assign m_axis.tkeep = '1;
    assign m_axis.tstrb = {M_KEEP_WIDTH{m_beat.tstrb}};
end

if (LAST_ENABLE) begin : g_m_last
    assign m_axis.tlast = m_beat.tlast;
end else begin : g_m_no_last
    assign m_axis.tlast = 1'b0;
end

if (ID_ENABLE) begin : g_m_id
    assign m_axis.tid = m_beat.tid;
end else begin : g_m_no_id
    assign m_axis.tid = '0;
end

if (DEST_ENABLE) begin : g_m_dest
    assign m_axis.tdest = m_beat.tdest;
end else begin : g_m_no_dest
    assign m_axis.tdest = '0;
end

if (USER_ENABLE) begin : g_m_user
    assign m_axis.tuser = m_beat.tuser;
end else begin : g_m_no_user
    assign m_axis.tuser = '0;
end

if (M_BYTE_LANES == S_BYTE_LANES) begin : g_bypass
    // same width; bypass

    assign s_axis.tready = m_axis.tready;
    assign m_axis.tvalid = s_axis.tvalid;
    assign m_beat        = s_beat;

end else if (M_BYTE_LANES > S_BYTE_LANES) begin : g_upsize
    // output is wider; upsize

    // number of input beats per output word
    localparam int SEG_COUNT = M_BYTE_LANES / S_BYTE_LANES;
    localparam int SEG_WIDTH = $clog2(SEG_COUNT);
    localparam logic [SEG_WIDTH-1:0] SEG_LAST = SEG_WIDTH'(SEG_COUNT - 1);

    // control registers
    logic [SEG_WIDTH-1:0] seg_reg, seg_next;
    logic                 skid_valid_reg, skid_valid_next;
    logic                 m_axis_tvalid_reg, m_axis_tvalid_next;

    // datapath registers, no reset
    s_beat_t skid_reg;
    // tid, tdest and tuser are taken from the last input beat of a word
    m_beat_t out_reg;

    // beat for the next segment, skid buffer first
    s_beat_t cur;
    store_t  store;

    assign cur = skid_valid_reg ? skid_reg : s_beat;

    assign s_axis.tready = !skid_valid_reg;
    assign m_axis.tvalid = m_axis_tvalid_reg;
    assign m_beat        = out_reg;

    always_comb begin
        m_axis_tvalid_next = m_axis_tvalid_reg && !m_axis.tready;
        skid_valid_next    = skid_valid_reg;
        seg_next           = seg_reg;
        store              = STORE_NONE;

        if (!m_axis_tvalid_reg || m_axis.tready) begin
            // output register empty
            if (skid_valid_reg || s_axis.tvalid) begin
                skid_valid_next = 1'b0;
                store = STORE_TO_OUT;

                if (cur.tlast || seg_reg == SEG_LAST) begin
                    seg_next = '0;
                    m_axis_tvalid_next = 1'b1;
                end else begin
                    seg_next = seg_reg + 1'b1;
                end
            end
        end else if (s_axis.tvalid && !skid_valid_reg) begin
            // output full, store input in skid buffer
            skid_valid_next = 1'b1;
            store = STORE_TO_SKID;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            seg_reg           <= '0;
            skid_valid_reg    <= 1'b0;
            m_axis_tvalid_reg <= 1'b0;
        end else begin
            seg_reg           <= seg_next;
            skid_valid_reg    <= skid_valid_next;
            m_axis_tvalid_reg <= m_axis_tvalid_next;
        end
    end

    // datapath, skid buffer is only used with seg_reg 0
    always_ff @(posedge clk) begin
        case (store)
            STORE_TO_OUT: begin
                out_reg.tdata[seg_reg*S_DATA_WIDTH +: S_DATA_WIDTH] <= cur.tdata;
                if (seg_reg == '0) begin
                    // first segment, clear keep of upper segments
                    out_reg.tkeep <= M_BYTE_LANES'(cur.tkeep);
                    out_reg.tstrb <= M_BYTE_LANES'(cur.tstrb);
                end else begin
                    out_reg.tkeep[seg_reg*S_BYTE_LANES +: S_BYTE_LANES] <= cur.tkeep;
                    out_reg.tstrb[seg_reg*S_BYTE_LANES +: S_BYTE_LANES] <= cur.tstrb;
                end
                out_reg.tlast <= cur.tlast;
                out_reg.tid   <= cur.tid;
                out_reg.tdest <= cur.tdest;
                out_reg.tuser <= cur.tuser;
            end
            STORE_TO_SKID: skid_reg <= s_beat;
            default: ;
        endcase
    end

end else begin : g_downsize
    // output is narrower; downsize

    // control registers
    logic skid_valid_reg, skid_valid_next;
    logic m_axis_tvalid_reg, m_axis_tvalid_next;

    // datapath registers, no reset
    s_beat_t skid_reg;
    m_beat_t out_reg;

    // beat to send next, skid buffer first
    s_beat_t cur;
    // no data in upper segments, cur ends with this output beat
    logic    cur_done;
    store_t  store;

    assign cur      = skid_valid_reg ? skid_reg : s_beat;
    assign cur_done = (cur.tkeep >> M_BYTE_LANES) == '0;

    assign s_axis.tready = !skid_valid_reg;
    assign m_axis.tvalid = m_axis_tvalid_reg;
    assign m_beat        = out_reg;

    always_comb begin
        m_axis_tvalid_next = m_axis_tvalid_reg && !m_axis.tready;
        skid_valid_next    = skid_valid_reg;
        store              = STORE_NONE;

        if (!m_axis_tvalid_reg || m_axis.tready) begin
            // output register empty, send lowest segment, keep rest in skid buffer
            if (skid_valid_reg || s_axis.tvalid) begin
                m_axis_tvalid_next = 1'b1;
                skid_valid_next = !cur_done;
                store = STORE_TO_OUT;
            end
        end else if (s_axis.tvalid && !skid_valid_reg) begin
            // output full, store input in skid buffer
            skid_valid_next = 1'b1;
            store = STORE_TO_SKID;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            skid_valid_reg    <= 1'b0;
            m_axis_tvalid_reg <= 1'b0;
        end else begin
            skid_valid_reg    <= skid_valid_next;
            m_axis_tvalid_reg <= m_axis_tvalid_next;
        end
    end

    // datapath
    always_ff @(posedge clk) begin
        case (store)
            STORE_TO_OUT: begin
                out_reg.tdata <= cur.tdata[M_DATA_WIDTH-1:0];
                out_reg.tkeep <= cur.tkeep[M_BYTE_LANES-1:0];
                out_reg.tstrb <= cur.tstrb[M_BYTE_LANES-1:0];
                out_reg.tlast <= cur_done && cur.tlast;
                out_reg.tid   <= cur.tid;
                out_reg.tdest <= cur.tdest;
                out_reg.tuser <= cur.tuser;

                skid_reg       <= cur;
                skid_reg.tdata <= cur.tdata >> M_DATA_WIDTH;
                skid_reg.tkeep <= cur.tkeep >> M_BYTE_LANES;
                skid_reg.tstrb <= cur.tstrb >> M_BYTE_LANES;
            end
            STORE_TO_SKID: skid_reg <= s_beat;
            default: ;
        endcase
    end

end

endmodule

`resetall
