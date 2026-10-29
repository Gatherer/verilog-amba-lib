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
 * AXI4-Stream asynchronous FIFO
 * widths and enables are taken from s_axis
 * disabled tstrb follows tkeep, disabled tlast is 0
 * register names are used in the axis_async_fifo constraints
 */
module axis_async_fifo #(
    // FIFO depth in words
    // KEEP_WIDTH words per cycle if KEEP_ENABLE set
    // Rounded up to nearest power of 2 cycles
    parameter int DEPTH = 4096,
    // number of RAM pipeline registers
    parameter int RAM_PIPELINE = 1,
    // use output FIFO
    // When set, the RAM read enable and pipeline clock enables are removed
    parameter bit OUTPUT_FIFO_ENABLE = 1'b0,
    // Frame FIFO mode - operate on frames instead of cycles
    // When set, m_axis.tvalid will not be deasserted within a frame
    // Requires LAST_ENABLE set
    parameter bit FRAME_FIFO = 1'b0,
    // tuser value for bad frame marker, untyped: any width
    parameter USER_BAD_FRAME_VALUE = 1'b1,
    // tuser mask for bad frame marker, untyped: any width
    parameter USER_BAD_FRAME_MASK = 1'b1,
    // Drop frames larger than FIFO
    // Requires FRAME_FIFO set
    parameter bit DROP_OVERSIZE_FRAME = FRAME_FIFO,
    // Drop frames marked bad
    // Requires FRAME_FIFO and DROP_OVERSIZE_FRAME set
    parameter bit DROP_BAD_FRAME = 1'b0,
    // Drop incoming frames when full
    // When set, s_axis.tready is always asserted
    // Requires FRAME_FIFO and DROP_OVERSIZE_FRAME set
    parameter bit DROP_WHEN_FULL = 1'b0,
    // Mark incoming frames as bad frames when full
    // When set, s_axis.tready is always asserted
    // Requires FRAME_FIFO to be clear
    parameter bit MARK_WHEN_FULL = 1'b0,
    // Enable pause request input
    parameter bit PAUSE_ENABLE = 1'b0,
    // Pause between frames
    parameter bit FRAME_PAUSE = FRAME_FIFO
) (
    /*
     * AXI input
     */
    input  wire                    s_clk,
    input  wire                    s_rst,
    axis_if.slave                  s_axis,

    /*
     * AXI output
     */
    input  wire                    m_clk,
    input  wire                    m_rst,
    axis_if.master                 m_axis,

    /*
     * Pause
     */
    // unused without PAUSE_ENABLE
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire                    s_pause_req,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic                   s_pause_ack,
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire                    m_pause_req,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic                   m_pause_ack,

    /*
     * Status
     */
    output logic [$clog2(DEPTH):0] s_status_depth,
    output logic [$clog2(DEPTH):0] s_status_depth_commit,
    output logic                   s_status_overflow,
    output logic                   s_status_bad_frame,
    output logic                   s_status_good_frame,
    output logic [$clog2(DEPTH):0] m_status_depth,
    output logic [$clog2(DEPTH):0] m_status_depth_commit,
    output logic                   m_status_overflow,
    output logic                   m_status_bad_frame,
    output logic                   m_status_good_frame
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

// round up to full cycles
localparam int ADDR_WIDTH = (KEEP_ENABLE && KEEP_WIDTH > 1) ? $clog2((DEPTH+KEEP_WIDTH-1)/KEEP_WIDTH) : $clog2(DEPTH);
// words per FIFO entry
localparam int ENTRY_WORDS = (KEEP_ENABLE && KEEP_WIDTH > 1) ? KEEP_WIDTH : 1;

localparam int STATUS_WIDTH = $clog2(DEPTH) + 1;
// unsigned, for status multiply
localparam logic [STATUS_WIDTH-1:0] STATUS_WORDS = STATUS_WIDTH'(ENTRY_WORDS);

localparam int OUTPUT_FIFO_ADDR_WIDTH = RAM_PIPELINE < 2 ? 3 : $clog2(RAM_PIPELINE*2+7);
localparam int OUTPUT_FIFO_HALF       = 2**(OUTPUT_FIFO_ADDR_WIDTH-1);

typedef logic [ADDR_WIDTH:0] ptr_t;
typedef logic [USER_WIDTH-1:0] user_t;

// bad frame marker, sized to USER_WIDTH
localparam user_t BAD_VALUE = user_t'(USER_BAD_FRAME_VALUE);
localparam user_t BAD_MASK  = user_t'(USER_BAD_FRAME_MASK);

// parameter checks
if (ADDR_WIDTH < 1) begin : g_depth_check
    $error("axis_async_fifo: DEPTH too small, must hold at least 2 cycles");
end

if (FRAME_FIFO && !LAST_ENABLE) begin : g_frame_fifo_check
    $error("axis_async_fifo: FRAME_FIFO set requires LAST_ENABLE set");
end

if (DROP_OVERSIZE_FRAME && !FRAME_FIFO) begin : g_drop_oversize_check
    $error("axis_async_fifo: DROP_OVERSIZE_FRAME set requires FRAME_FIFO set");
end

if (DROP_BAD_FRAME && !(FRAME_FIFO && DROP_OVERSIZE_FRAME)) begin : g_drop_bad_check
    $error("axis_async_fifo: DROP_BAD_FRAME set requires FRAME_FIFO and DROP_OVERSIZE_FRAME set");
end

if (DROP_WHEN_FULL && !(FRAME_FIFO && DROP_OVERSIZE_FRAME)) begin : g_drop_full_check
    $error("axis_async_fifo: DROP_WHEN_FULL set requires FRAME_FIFO and DROP_OVERSIZE_FRAME set");
end

if ((DROP_BAD_FRAME || MARK_WHEN_FULL) && BAD_MASK == '0) begin : g_bad_mask_check
    $error("axis_async_fifo: invalid USER_BAD_FRAME_MASK value");
end

if (MARK_WHEN_FULL && FRAME_FIFO) begin : g_mark_frame_check
    $error("axis_async_fifo: MARK_WHEN_FULL is not compatible with FRAME_FIFO");
end

if (MARK_WHEN_FULL && !LAST_ENABLE) begin : g_mark_last_check
    $error("axis_async_fifo: MARK_WHEN_FULL set requires LAST_ENABLE set");
end

if (FRAME_PAUSE && !LAST_ENABLE) begin : g_frame_pause_check
    $error("axis_async_fifo: FRAME_PAUSE set requires LAST_ENABLE set");
end

if (m_axis.DATA_WIDTH  != DATA_WIDTH  || m_axis.KEEP_WIDTH  != KEEP_WIDTH  ||
    m_axis.KEEP_ENABLE != KEEP_ENABLE || m_axis.STRB_ENABLE != STRB_ENABLE ||
    m_axis.LAST_ENABLE != LAST_ENABLE ||
    m_axis.ID_ENABLE   != ID_ENABLE   || m_axis.ID_WIDTH    != ID_WIDTH    ||
    m_axis.DEST_ENABLE != DEST_ENABLE || m_axis.DEST_WIDTH  != DEST_WIDTH  ||
    m_axis.USER_ENABLE != USER_ENABLE || m_axis.USER_WIDTH  != USER_WIDTH) begin : g_m_check
    $error("axis_async_fifo: m_axis parameters differ from s_axis");
end

// packed FIFO entry, disabled fields are not stored
localparam int KEEP_OFFSET = DATA_WIDTH;
localparam int STRB_OFFSET = KEEP_OFFSET + (KEEP_ENABLE ? KEEP_WIDTH : 0);
localparam int LAST_OFFSET = STRB_OFFSET + (STRB_ENABLE ? KEEP_WIDTH : 0);
localparam int ID_OFFSET   = LAST_OFFSET + (LAST_ENABLE ? 1          : 0);
localparam int DEST_OFFSET = ID_OFFSET   + (ID_ENABLE   ? ID_WIDTH   : 0);
localparam int USER_OFFSET = DEST_OFFSET + (DEST_ENABLE ? DEST_WIDTH : 0);
localparam int WIDTH       = USER_OFFSET + (USER_ENABLE ? USER_WIDTH : 0);

// entry bits set on a terminated frame: tlast and bad frame marker
localparam logic [WIDTH-1:0] TERM_LAST     = LAST_ENABLE ? WIDTH'(1) << LAST_OFFSET : '0;
localparam logic [WIDTH-1:0] TERM_USER_SEL = USER_ENABLE ? WIDTH'(user_t'('1)) << USER_OFFSET : '0;
localparam logic [WIDTH-1:0] TERM_USER     = USER_ENABLE ? WIDTH'(BAD_VALUE) << USER_OFFSET : '0;

function automatic ptr_t bin2gray(input ptr_t b);
    return b ^ (b >> 1);
endfunction

function automatic ptr_t gray2bin(input ptr_t g);
    ptr_t b;
    for (int i = 0; i <= ADDR_WIDTH; i++) begin
        b[i] = ^(g >> i);
    end
    return b;
endfunction

// control registers
ptr_t wr_ptr_reg;
ptr_t wr_ptr_commit_reg;
ptr_t wr_ptr_gray_reg;
ptr_t wr_ptr_sync_commit_reg;
ptr_t rd_ptr_reg;
ptr_t rd_ptr_gray_reg;
ptr_t wr_ptr_conv_reg;
ptr_t rd_ptr_conv_reg;

(* SHREG_EXTRACT = "NO" *)
ptr_t wr_ptr_gray_sync1_reg;
(* SHREG_EXTRACT = "NO" *)
ptr_t wr_ptr_gray_sync2_reg;
(* SHREG_EXTRACT = "NO" *)
ptr_t wr_ptr_commit_sync_reg;
(* SHREG_EXTRACT = "NO" *)
ptr_t rd_ptr_gray_sync1_reg;
(* SHREG_EXTRACT = "NO" *)
ptr_t rd_ptr_gray_sync2_reg;

logic wr_ptr_update_valid_reg;
logic wr_ptr_update_reg;
(* SHREG_EXTRACT = "NO" *)
logic wr_ptr_update_sync1_reg;
(* SHREG_EXTRACT = "NO" *)
logic wr_ptr_update_sync2_reg;
(* SHREG_EXTRACT = "NO" *)
logic wr_ptr_update_sync3_reg;
(* SHREG_EXTRACT = "NO" *)
logic wr_ptr_update_ack_sync1_reg;
(* SHREG_EXTRACT = "NO" *)
logic wr_ptr_update_ack_sync2_reg;

// m_rst in s_clk domain, s_rst in m_clk domain
logic s_rst_sync;
logic m_rst_sync;

logic [RAM_PIPELINE:0] m_axis_tvalid_pipe_reg;

// datapath registers, no reset
(* ramstyle = "no_rw_check" *)
logic [WIDTH-1:0] mem[2**ADDR_WIDTH];

(* SHREG_EXTRACT = "NO" *)
logic [WIDTH-1:0] m_axis_pipe_reg[RAM_PIPELINE+1];

// full when first TWO MSBs do NOT match, but rest matches
// (gray code equivalent of first MSB different but rest same)
logic full;
// empty when pointers match exactly
logic empty;
// overflow within packet
logic full_wr;

assign full    = wr_ptr_gray_reg == (rd_ptr_gray_sync2_reg ^ {2'b11, {ADDR_WIDTH-1{1'b0}}});
assign empty   = FRAME_FIFO ? (rd_ptr_reg == wr_ptr_commit_sync_reg) : (rd_ptr_gray_reg == wr_ptr_gray_sync2_reg);
assign full_wr = wr_ptr_reg == (wr_ptr_commit_reg ^ {1'b1, {ADDR_WIDTH{1'b0}}});

// next pointers
ptr_t wr_ptr_inc;
ptr_t rd_ptr_inc;

assign wr_ptr_inc = wr_ptr_reg + 1;
assign rd_ptr_inc = rd_ptr_reg + 1;

// control signals
logic s_frame_reg;
logic m_frame_reg;

logic drop_frame_reg;
logic mark_frame_reg;
logic send_frame_reg;
logic overflow_reg;
logic bad_frame_reg;
logic good_frame_reg;

logic m_drop_frame_reg;
logic m_terminate_frame_reg;

ptr_t s_depth_reg;
ptr_t s_depth_commit_reg;
ptr_t m_depth_reg;
ptr_t m_depth_commit_reg;

logic overflow_sync1_reg;
(* SHREG_EXTRACT = "NO" *)
logic overflow_sync2_reg;
(* SHREG_EXTRACT = "NO" *)
logic overflow_sync3_reg;
logic overflow_sync4_reg;
logic bad_frame_sync1_reg;
(* SHREG_EXTRACT = "NO" *)
logic bad_frame_sync2_reg;
(* SHREG_EXTRACT = "NO" *)
logic bad_frame_sync3_reg;
logic bad_frame_sync4_reg;
logic good_frame_sync1_reg;
(* SHREG_EXTRACT = "NO" *)
logic good_frame_sync2_reg;
(* SHREG_EXTRACT = "NO" *)
logic good_frame_sync3_reg;
logic good_frame_sync4_reg;

logic             s_axis_tready_int;
logic             s_bad_frame;
logic [WIDTH-1:0] s_axis_entry;

assign s_axis_tready_int = (FRAME_FIFO ? (!full || (full_wr && DROP_OVERSIZE_FRAME) || DROP_WHEN_FULL) : (!full || MARK_WHEN_FULL)) && !s_rst_sync;
assign s_axis.tready = s_axis_tready_int;

// tuser matches bad frame marker
assign s_bad_frame = |(BAD_MASK & ~(s_axis.tuser ^ BAD_VALUE));

assign s_axis_entry[DATA_WIDTH-1:0] = s_axis.tdata;

if (KEEP_ENABLE) begin : g_s_keep
    assign s_axis_entry[KEEP_OFFSET +: KEEP_WIDTH] = s_axis.tkeep;
end

if (STRB_ENABLE) begin : g_s_strb
    assign s_axis_entry[STRB_OFFSET +: KEEP_WIDTH] = s_axis.tstrb;
end

if (LAST_ENABLE) begin : g_s_last
    assign s_axis_entry[LAST_OFFSET] = s_axis.tlast | mark_frame_reg;
end

if (ID_ENABLE) begin : g_s_id
    assign s_axis_entry[ID_OFFSET +: ID_WIDTH] = s_axis.tid;
end

if (DEST_ENABLE) begin : g_s_dest
    assign s_axis_entry[DEST_OFFSET +: DEST_WIDTH] = s_axis.tdest;
end

if (USER_ENABLE) begin : g_s_user
    assign s_axis_entry[USER_OFFSET +: USER_WIDTH] = mark_frame_reg ? BAD_VALUE : s_axis.tuser;
end

// RAM pipeline output, terminated frame gets tlast and bad frame marker
logic             m_axis_tready_pipe;
logic             m_axis_tvalid_pipe;
logic [WIDTH-1:0] m_axis_pipe;
logic             m_axis_tlast_pipe;

assign m_axis_tvalid_pipe = m_axis_tvalid_pipe_reg[RAM_PIPELINE];
assign m_axis_pipe = m_terminate_frame_reg ?
    (m_axis_pipe_reg[RAM_PIPELINE] & ~TERM_USER_SEL) | TERM_LAST | TERM_USER :
    m_axis_pipe_reg[RAM_PIPELINE];

if (LAST_ENABLE) begin : g_pipe_last
    assign m_axis_tlast_pipe = m_axis_pipe[LAST_OFFSET];
end else begin : g_pipe_no_last
    assign m_axis_tlast_pipe = 1'b1;
end

// output stage, before pause
logic             m_axis_tready_out;
logic             m_axis_tvalid_out;
logic [WIDTH-1:0] m_axis_out;

logic pipe_ready;

// unpacked output
logic [KEEP_WIDTH-1:0] m_tkeep;
logic                  m_tlast;

// in words, also correct for non power of 2 KEEP_WIDTH
assign s_status_depth        = STATUS_WIDTH'(s_depth_reg) * STATUS_WORDS;
assign s_status_depth_commit = STATUS_WIDTH'(s_depth_commit_reg) * STATUS_WORDS;
assign s_status_overflow     = overflow_reg;
assign s_status_bad_frame    = bad_frame_reg;
assign s_status_good_frame   = good_frame_reg;

assign m_status_depth        = STATUS_WIDTH'(m_depth_reg) * STATUS_WORDS;
assign m_status_depth_commit = STATUS_WIDTH'(m_depth_commit_reg) * STATUS_WORDS;
// toggle sync, events closer than sync latency can get lost
assign m_status_overflow     = overflow_sync3_reg ^ overflow_sync4_reg;
assign m_status_bad_frame    = bad_frame_sync3_reg ^ bad_frame_sync4_reg;
assign m_status_good_frame   = good_frame_sync3_reg ^ good_frame_sync4_reg;

// reset synchronization
sync_reset_cdc #(
    .N(2)
)
s_rst_cdc_inst (
    .src_clk(m_clk),
    .src_rst(m_rst),
    .dst_clk(s_clk),
    .out(s_rst_sync)
);

sync_reset_cdc #(
    .N(2)
)
m_rst_cdc_inst (
    .src_clk(s_clk),
    .src_rst(s_rst),
    .dst_clk(m_clk),
    .out(m_rst_sync)
);

// sync committed write pointer to read side, or flag it for later
task automatic commit_sync(input ptr_t ptr);
    if (wr_ptr_update_reg == wr_ptr_update_ack_sync2_reg) begin
        // no sync in progress; sync update
        wr_ptr_update_valid_reg <= 1'b0;
        wr_ptr_sync_commit_reg <= ptr;
        wr_ptr_update_reg <= !wr_ptr_update_ack_sync2_reg;
    end else begin
        // sync in progress; flag it for later
        wr_ptr_update_valid_reg <= 1'b1;
    end
endtask

// Write logic
always_ff @(posedge s_clk) begin
    overflow_reg <= 1'b0;
    bad_frame_reg <= 1'b0;
    good_frame_reg <= 1'b0;

    if (FRAME_FIFO && wr_ptr_update_valid_reg) begin
        // have updated pointer to sync
        commit_sync(wr_ptr_commit_reg);
    end

    if (s_axis_tready_int && s_axis.tvalid && LAST_ENABLE) begin
        // track input frame status
        s_frame_reg <= !s_axis.tlast;
    end

    if (s_rst_sync && s_frame_reg && LAST_ENABLE) begin
        // if sink side is reset during transfer, drop partial frame
        // (s_axis.tready is low during sink reset)
        drop_frame_reg <= 1'b1;
    end

    if (FRAME_FIFO) begin
        // frame FIFO mode
        if (s_axis_tready_int && s_axis.tvalid) begin
            // transfer in
            if ((full && DROP_WHEN_FULL) || (full_wr && DROP_OVERSIZE_FRAME) || drop_frame_reg) begin
                // full, packet overflow, or currently dropping frame
                // drop frame
                drop_frame_reg <= 1'b1;
                if (s_axis.tlast) begin
                    // end of frame, reset write pointer
                    wr_ptr_reg <= wr_ptr_commit_reg;
                    wr_ptr_gray_reg <= bin2gray(wr_ptr_commit_reg);
                    drop_frame_reg <= 1'b0;
                    overflow_reg <= 1'b1;
                end
            end else begin
                mem[wr_ptr_reg[ADDR_WIDTH-1:0]] <= s_axis_entry;
                wr_ptr_reg <= wr_ptr_inc;
                wr_ptr_gray_reg <= bin2gray(wr_ptr_inc);
                if (s_axis.tlast || (!DROP_OVERSIZE_FRAME && (full_wr || send_frame_reg))) begin
                    // end of frame or send frame
                    send_frame_reg <= !s_axis.tlast;
                    if (s_axis.tlast && DROP_BAD_FRAME && s_bad_frame) begin
                        // bad packet, reset write pointer
                        wr_ptr_reg <= wr_ptr_commit_reg;
                        wr_ptr_gray_reg <= bin2gray(wr_ptr_commit_reg);
                        bad_frame_reg <= 1'b1;
                    end else begin
                        // good packet or packet overflow, update write pointer
                        wr_ptr_commit_reg <= wr_ptr_inc;
                        commit_sync(wr_ptr_inc);
                        good_frame_reg <= s_axis.tlast;
                    end
                end
            end
        end else if (s_axis.tvalid && full_wr && !DROP_OVERSIZE_FRAME) begin
            // data valid with packet overflow
            // update write pointer
            send_frame_reg <= 1'b1;
            wr_ptr_commit_reg <= wr_ptr_reg;
            commit_sync(wr_ptr_reg);
        end
    end else begin
        // normal FIFO mode
        if (s_axis_tready_int && s_axis.tvalid) begin
            if (drop_frame_reg && LAST_ENABLE) begin
                // currently dropping frame
                if (s_axis.tlast) begin
                    // end of frame
                    if (!full && mark_frame_reg && MARK_WHEN_FULL) begin
                        // terminate marked frame
                        mark_frame_reg <= 1'b0;
                        mem[wr_ptr_reg[ADDR_WIDTH-1:0]] <= s_axis_entry;
                        wr_ptr_reg <= wr_ptr_inc;
                        wr_ptr_commit_reg <= wr_ptr_inc;
                        wr_ptr_gray_reg <= bin2gray(wr_ptr_inc);
                    end
                    // end of frame, clear drop flag
                    drop_frame_reg <= 1'b0;
                    overflow_reg <= 1'b1;
                end
            end else if ((full || mark_frame_reg) && MARK_WHEN_FULL) begin
                // full or marking frame
                // drop frame; mark if this isn't the first cycle
                drop_frame_reg <= 1'b1;
                mark_frame_reg <= mark_frame_reg || s_frame_reg;
                if (s_axis.tlast) begin
                    drop_frame_reg <= 1'b0;
                    overflow_reg <= 1'b1;
                end
            end else begin
                // transfer in
                mem[wr_ptr_reg[ADDR_WIDTH-1:0]] <= s_axis_entry;
                wr_ptr_reg <= wr_ptr_inc;
                wr_ptr_commit_reg <= wr_ptr_inc;
                wr_ptr_gray_reg <= bin2gray(wr_ptr_inc);
            end
        end else if ((!full && !drop_frame_reg && mark_frame_reg) && MARK_WHEN_FULL) begin
            // terminate marked frame
            mark_frame_reg <= 1'b0;
            mem[wr_ptr_reg[ADDR_WIDTH-1:0]] <= s_axis_entry;
            wr_ptr_reg <= wr_ptr_inc;
            wr_ptr_commit_reg <= wr_ptr_inc;
            wr_ptr_gray_reg <= bin2gray(wr_ptr_inc);
        end
    end

    if (s_rst_sync) begin
        wr_ptr_reg <= '0;
        wr_ptr_commit_reg <= '0;
        wr_ptr_gray_reg <= '0;
        wr_ptr_sync_commit_reg <= '0;

        wr_ptr_update_valid_reg <= 1'b0;
        wr_ptr_update_reg <= 1'b0;
    end

    if (s_rst) begin
        wr_ptr_reg <= '0;
        wr_ptr_commit_reg <= '0;
        wr_ptr_gray_reg <= '0;
        wr_ptr_sync_commit_reg <= '0;

        wr_ptr_update_valid_reg <= 1'b0;
        wr_ptr_update_reg <= 1'b0;

        s_frame_reg <= 1'b0;

        drop_frame_reg <= 1'b0;
        mark_frame_reg <= 1'b0;
        send_frame_reg <= 1'b0;
        overflow_reg <= 1'b0;
        bad_frame_reg <= 1'b0;
        good_frame_reg <= 1'b0;
    end
end

// Write-side status
always_ff @(posedge s_clk) begin
    rd_ptr_conv_reg <= gray2bin(rd_ptr_gray_sync2_reg);
    s_depth_reg <= wr_ptr_reg - rd_ptr_conv_reg;
    s_depth_commit_reg <= wr_ptr_commit_reg - rd_ptr_conv_reg;
end

// pointer synchronization
always_ff @(posedge s_clk) begin
    rd_ptr_gray_sync1_reg <= rd_ptr_gray_reg;
    rd_ptr_gray_sync2_reg <= rd_ptr_gray_sync1_reg;
    wr_ptr_update_ack_sync1_reg <= wr_ptr_update_sync3_reg;
    wr_ptr_update_ack_sync2_reg <= wr_ptr_update_ack_sync1_reg;

    if (s_rst) begin
        rd_ptr_gray_sync1_reg <= '0;
        rd_ptr_gray_sync2_reg <= '0;
        wr_ptr_update_ack_sync1_reg <= 1'b0;
        wr_ptr_update_ack_sync2_reg <= 1'b0;
    end
end

always_ff @(posedge m_clk) begin
    wr_ptr_gray_sync1_reg <= wr_ptr_gray_reg;
    wr_ptr_gray_sync2_reg <= wr_ptr_gray_sync1_reg;
    if (FRAME_FIFO && (wr_ptr_update_sync2_reg ^ wr_ptr_update_sync3_reg)) begin
        wr_ptr_commit_sync_reg <= wr_ptr_sync_commit_reg;
    end
    wr_ptr_update_sync1_reg <= wr_ptr_update_reg;
    wr_ptr_update_sync2_reg <= wr_ptr_update_sync1_reg;
    wr_ptr_update_sync3_reg <= wr_ptr_update_sync2_reg;

    if (FRAME_FIFO && m_rst_sync) begin
        // source reset, rd_ptr_reg is cleared too
        wr_ptr_gray_sync1_reg <= '0;
        wr_ptr_commit_sync_reg <= '0;
    end

    if (m_rst) begin
        wr_ptr_gray_sync1_reg <= '0;
        wr_ptr_gray_sync2_reg <= '0;
        wr_ptr_commit_sync_reg <= '0;
        wr_ptr_update_sync1_reg <= 1'b0;
        wr_ptr_update_sync2_reg <= 1'b0;
        wr_ptr_update_sync3_reg <= 1'b0;
    end
end

// status synchronization
always_ff @(posedge s_clk) begin
    overflow_sync1_reg <= overflow_sync1_reg ^ overflow_reg;
    bad_frame_sync1_reg <= bad_frame_sync1_reg ^ bad_frame_reg;
    good_frame_sync1_reg <= good_frame_sync1_reg ^ good_frame_reg;

    if (s_rst) begin
        overflow_sync1_reg <= 1'b0;
        bad_frame_sync1_reg <= 1'b0;
        good_frame_sync1_reg <= 1'b0;
    end
end

always_ff @(posedge m_clk) begin
    overflow_sync2_reg <= overflow_sync1_reg;
    overflow_sync3_reg <= overflow_sync2_reg;
    overflow_sync4_reg <= overflow_sync3_reg;
    bad_frame_sync2_reg <= bad_frame_sync1_reg;
    bad_frame_sync3_reg <= bad_frame_sync2_reg;
    bad_frame_sync4_reg <= bad_frame_sync3_reg;
    good_frame_sync2_reg <= good_frame_sync1_reg;
    good_frame_sync3_reg <= good_frame_sync2_reg;
    good_frame_sync4_reg <= good_frame_sync3_reg;

    if (m_rst) begin
        overflow_sync2_reg <= 1'b0;
        overflow_sync3_reg <= 1'b0;
        overflow_sync4_reg <= 1'b0;
        bad_frame_sync2_reg <= 1'b0;
        bad_frame_sync3_reg <= 1'b0;
        bad_frame_sync4_reg <= 1'b0;
        good_frame_sync2_reg <= 1'b0;
        good_frame_sync3_reg <= 1'b0;
        good_frame_sync4_reg <= 1'b0;
    end
end

// Read logic
always_ff @(posedge m_clk) begin
    if (m_axis_tready_pipe) begin
        // output ready; invalidate stage
        m_axis_tvalid_pipe_reg[RAM_PIPELINE] <= 1'b0;
        m_terminate_frame_reg <= 1'b0;
    end

    for (int j = RAM_PIPELINE; j > 0; j--) begin
        if (m_axis_tready_pipe || |(~m_axis_tvalid_pipe_reg >> j)) begin
            // output ready or bubble in pipeline; transfer down pipeline
            m_axis_tvalid_pipe_reg[j] <= m_axis_tvalid_pipe_reg[j-1];
            m_axis_pipe_reg[j] <= m_axis_pipe_reg[j-1];
            m_axis_tvalid_pipe_reg[j-1] <= 1'b0;
        end
    end

    if (m_axis_tready_pipe || !(&m_axis_tvalid_pipe_reg)) begin
        // output ready or bubble in pipeline; read new data from FIFO
        m_axis_tvalid_pipe_reg[0] <= 1'b0;
        m_axis_pipe_reg[0] <= mem[rd_ptr_reg[ADDR_WIDTH-1:0]];
        if (!empty && !m_rst_sync && !m_drop_frame_reg && pipe_ready) begin
            // not empty, increment pointer
            m_axis_tvalid_pipe_reg[0] <= 1'b1;
            rd_ptr_reg <= rd_ptr_inc;
            rd_ptr_gray_reg <= bin2gray(rd_ptr_inc);
        end
    end

    if (m_axis_tvalid_pipe && LAST_ENABLE) begin
        // track output frame status
        if (m_axis_tlast_pipe && m_axis_tready_pipe) begin
            m_frame_reg <= 1'b0;
        end else begin
            m_frame_reg <= 1'b1;
        end
    end

    if (m_drop_frame_reg && (OUTPUT_FIFO_ENABLE ? pipe_ready : (m_axis_tready_pipe || !m_axis_tvalid_pipe)) && LAST_ENABLE) begin
        // terminate frame
        // (only for frame transfers interrupted by source reset)
        m_axis_tvalid_pipe_reg[RAM_PIPELINE] <= 1'b1;
        m_terminate_frame_reg <= 1'b1;
        m_drop_frame_reg <= 1'b0;
    end

    if (m_rst_sync && LAST_ENABLE) begin
        // if source side is reset during transfer, drop partial frame

        // empty output pipeline, except for last stage
        for (int j = 0; j < RAM_PIPELINE; j++) begin
            m_axis_tvalid_pipe_reg[j] <= 1'b0;
        end

        if (m_frame_reg && (!m_axis_tvalid_pipe || (m_axis_tvalid_pipe && !m_axis_tlast_pipe)) &&
                !(m_drop_frame_reg || m_terminate_frame_reg)) begin
            // terminate frame
            m_drop_frame_reg <= 1'b1;
        end
    end

    if (m_rst_sync) begin
        rd_ptr_reg <= '0;
        rd_ptr_gray_reg <= '0;
    end

    if (m_rst) begin
        rd_ptr_reg <= '0;
        rd_ptr_gray_reg <= '0;
        m_axis_tvalid_pipe_reg <= '0;
        m_frame_reg <= 1'b0;
        m_drop_frame_reg <= 1'b0;
        m_terminate_frame_reg <= 1'b0;
    end
end

// Read-side status
always_ff @(posedge m_clk) begin
    wr_ptr_conv_reg <= gray2bin(wr_ptr_gray_sync2_reg);
    m_depth_reg <= wr_ptr_conv_reg - rd_ptr_reg;
    m_depth_commit_reg <= FRAME_FIFO ? wr_ptr_commit_sync_reg - rd_ptr_reg : wr_ptr_conv_reg - rd_ptr_reg;
end

if (!OUTPUT_FIFO_ENABLE) begin : g_no_out_fifo

    assign pipe_ready = 1'b1;

    assign m_axis_tready_pipe = m_axis_tready_out;
    assign m_axis_tvalid_out  = m_axis_tvalid_pipe;
    assign m_axis_out         = m_axis_pipe;

end else begin : g_out_fifo

    // control registers
    logic m_axis_tvalid_reg;

    logic [OUTPUT_FIFO_ADDR_WIDTH:0] out_fifo_wr_ptr_reg;
    logic [OUTPUT_FIFO_ADDR_WIDTH:0] out_fifo_rd_ptr_reg;
    logic [OUTPUT_FIFO_ADDR_WIDTH:0] out_fifo_count;
    logic out_fifo_half_full_reg;

    // datapath registers, no reset
    logic [WIDTH-1:0] m_axis_reg;

    logic out_fifo_full;
    logic out_fifo_empty;

    assign out_fifo_full  = out_fifo_wr_ptr_reg == (out_fifo_rd_ptr_reg ^ {1'b1, {OUTPUT_FIFO_ADDR_WIDTH{1'b0}}});
    assign out_fifo_empty = out_fifo_wr_ptr_reg == out_fifo_rd_ptr_reg;
    assign out_fifo_count = out_fifo_wr_ptr_reg - out_fifo_rd_ptr_reg;

    (* ram_style = "distributed", ramstyle = "no_rw_check, mlab" *)
    logic [WIDTH-1:0] out_fifo[2**OUTPUT_FIFO_ADDR_WIDTH];

    assign pipe_ready = !out_fifo_half_full_reg;

    assign m_axis_tready_pipe = 1'b1;
    assign m_axis_tvalid_out  = m_axis_tvalid_reg;
    assign m_axis_out         = m_axis_reg;

    always_ff @(posedge m_clk) begin
        m_axis_tvalid_reg <= m_axis_tvalid_reg && !m_axis_tready_out;

        out_fifo_half_full_reg <= int'(out_fifo_count) >= OUTPUT_FIFO_HALF;

        if (!out_fifo_full && m_axis_tvalid_pipe) begin
            out_fifo[out_fifo_wr_ptr_reg[OUTPUT_FIFO_ADDR_WIDTH-1:0]] <= m_axis_pipe;
            out_fifo_wr_ptr_reg <= out_fifo_wr_ptr_reg + 1;
        end

        if (!out_fifo_empty && (!m_axis_tvalid_reg || m_axis_tready_out)) begin
            m_axis_reg <= out_fifo[out_fifo_rd_ptr_reg[OUTPUT_FIFO_ADDR_WIDTH-1:0]];
            m_axis_tvalid_reg <= 1'b1;
            out_fifo_rd_ptr_reg <= out_fifo_rd_ptr_reg + 1;
        end

        if (m_rst) begin
            out_fifo_wr_ptr_reg <= '0;
            out_fifo_rd_ptr_reg <= '0;
            out_fifo_half_full_reg <= 1'b0;
            m_axis_tvalid_reg <= 1'b0;
        end
    end

end

// unpack output, disabled fields get constants
assign m_axis.tdata = m_axis_out[DATA_WIDTH-1:0];

if (KEEP_ENABLE) begin : g_m_keep
    assign m_tkeep = m_axis_out[KEEP_OFFSET +: KEEP_WIDTH];
end else begin : g_m_no_keep
    assign m_tkeep = '1;
end

assign m_axis.tkeep = m_tkeep;

if (STRB_ENABLE) begin : g_m_strb
    assign m_axis.tstrb = m_axis_out[STRB_OFFSET +: KEEP_WIDTH];
end else begin : g_m_no_strb
    assign m_axis.tstrb = m_tkeep;
end

if (LAST_ENABLE) begin : g_m_last
    assign m_tlast = m_axis_out[LAST_OFFSET];
end else begin : g_m_no_last
    // every beat ends a frame
    assign m_tlast = 1'b1;
end

assign m_axis.tlast = LAST_ENABLE && m_tlast;

if (ID_ENABLE) begin : g_m_id
    assign m_axis.tid = m_axis_out[ID_OFFSET +: ID_WIDTH];
end else begin : g_m_no_id
    assign m_axis.tid = '0;
end

if (DEST_ENABLE) begin : g_m_dest
    assign m_axis.tdest = m_axis_out[DEST_OFFSET +: DEST_WIDTH];
end else begin : g_m_no_dest
    assign m_axis.tdest = '0;
end

if (USER_ENABLE) begin : g_m_user
    assign m_axis.tuser = m_axis_out[USER_OFFSET +: USER_WIDTH];
end else begin : g_m_no_user
    assign m_axis.tuser = '0;
end

// block name used in constraints
if (PAUSE_ENABLE) begin : pause

    // Pause logic
    logic pause_reg;
    logic pause_frame_reg;

    logic s_pause_req_sync1_reg;
    (* SHREG_EXTRACT = "NO" *)
    logic s_pause_req_sync2_reg;
    (* SHREG_EXTRACT = "NO" *)
    logic s_pause_req_sync3_reg;
    logic s_pause_ack_sync1_reg;
    (* SHREG_EXTRACT = "NO" *)
    logic s_pause_ack_sync2_reg;
    (* SHREG_EXTRACT = "NO" *)
    logic s_pause_ack_sync3_reg;

    always_ff @(posedge s_clk) begin
        s_pause_req_sync1_reg <= s_pause_req;
        s_pause_ack_sync2_reg <= s_pause_ack_sync1_reg;
        s_pause_ack_sync3_reg <= s_pause_ack_sync2_reg;
    end

    always_ff @(posedge m_clk) begin
        s_pause_req_sync2_reg <= s_pause_req_sync1_reg;
        s_pause_req_sync3_reg <= s_pause_req_sync2_reg;
        s_pause_ack_sync1_reg <= pause_reg;
    end

    assign m_axis_tready_out = m_axis.tready && !pause_reg;
    assign m_axis.tvalid     = m_axis_tvalid_out && !pause_reg;

    assign s_pause_ack = s_pause_ack_sync3_reg;
    assign m_pause_ack = pause_reg;

    always_ff @(posedge m_clk) begin
        if (FRAME_PAUSE) begin
            if (pause_reg) begin
                // paused; update pause status
                pause_reg <= m_pause_req || s_pause_req_sync3_reg;
            end else if (m_axis_tvalid_out) begin
                // frame transfer; set frame bit
                pause_frame_reg <= 1'b1;
                if (m_axis.tready && m_tlast) begin
                    // end of frame; clear frame bit and update pause status
                    pause_frame_reg <= 1'b0;
                    pause_reg <= m_pause_req || s_pause_req_sync3_reg;
                end
            end else if (!pause_frame_reg) begin
                // idle; update pause status
                pause_reg <= m_pause_req || s_pause_req_sync3_reg;
            end
        end else begin
            pause_reg <= m_pause_req || s_pause_req_sync3_reg;
        end

        if (m_rst) begin
            pause_frame_reg <= 1'b0;
            pause_reg <= 1'b0;
        end
    end

end else begin : g_no_pause

    assign m_axis_tready_out = m_axis.tready;
    assign m_axis.tvalid     = m_axis_tvalid_out;

    assign s_pause_ack = 1'b0;
    assign m_pause_ack = 1'b0;

end

endmodule

`resetall
