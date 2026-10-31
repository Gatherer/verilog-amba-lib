/*

Copyright (c) 2016-2018 Alex Forencich
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
 * AXI4-Stream consistent overhead byte stuffing (COBS) decoder
 * s_axis: 8 bit, tlast and tuser optional (disabled = 0)
 * m_axis: 8 bit, tlast and tuser required, tuser[0] marks bad frames
 * tkeep, tstrb, tid, tdest are dropped
 */
module axis_cobs_decode (
    input  wire    clk,
    input  wire    rst,

    axis_if.slave  s_axis,
    axis_if.master m_axis
);

localparam int DATA_WIDTH  = s_axis.DATA_WIDTH;
localparam bit LAST_ENABLE = s_axis.LAST_ENABLE;
localparam bit USER_ENABLE = s_axis.USER_ENABLE;

// parameter checks
if (DATA_WIDTH != 8) begin : g_s_check
    $error("axis_cobs_decode: s_axis DATA_WIDTH must be 8 (is %0d)", DATA_WIDTH);
end

if (m_axis.DATA_WIDTH != 8 || !m_axis.LAST_ENABLE || !m_axis.USER_ENABLE) begin : g_m_check
    $error("axis_cobs_decode: m_axis needs DATA_WIDTH 8, LAST_ENABLE and USER_ENABLE");
end

typedef enum logic [1:0] {
    STATE_IDLE,
    STATE_SEGMENT,
    STATE_NEXT_SEGMENT
} state_t;

// payload of one output transfer
typedef struct packed {
    logic [7:0] tdata;
    logic       tlast;
    logic       tuser;
} beat_t;

typedef enum logic [1:0] {
    STORE_NONE,
    STORE_INT_TO_OUT,
    STORE_INT_TO_TEMP,
    STORE_TEMP_TO_OUT
} store_t;

state_t state_reg, state_next;

logic       s_axis_tready_reg, s_axis_tready_next;
logic       temp_tvalid_reg, temp_tvalid_next;

// loaded before use, no reset
logic [7:0] count_reg, count_next;
logic       suppress_zero_reg, suppress_zero_next;
logic [7:0] temp_tdata_reg, temp_tdata_next;

// input, disabled tlast/tuser are 0
logic [7:0] s_tdata;
logic       s_tlast;
logic       s_tuser;
logic       s_xfer;

// FSM control
logic       load_code;
logic       fail;
logic       ready_force;
logic       ready_idle;

// internal datapath
beat_t      m_beat_int;
logic       m_tvalid_int;
logic       m_ready_int_reg;
logic       m_ready_int_early;

// not used by the decoder
/* verilator lint_off UNUSEDSIGNAL */
logic       unused;
/* verilator lint_on UNUSEDSIGNAL */

assign unused = ^{s_axis.tkeep, s_axis.tstrb, s_axis.tid, s_axis.tdest, s_axis.tuser, s_axis.tlast,
                  s_axis.KEEP_ENABLE, s_axis.STRB_ENABLE, s_axis.ID_ENABLE, s_axis.DEST_ENABLE};

assign s_tdata = s_axis.tdata;
assign s_tlast = LAST_ENABLE ? s_axis.tlast : 1'b0;
assign s_tuser = USER_ENABLE ? s_axis.tuser[0] : 1'b0;
assign s_xfer  = s_axis.tvalid && s_axis_tready_reg;

assign s_axis.tready = s_axis_tready_reg;

always_comb begin
    state_next = state_reg;

    count_next         = count_reg;
    suppress_zero_next = suppress_zero_reg;

    temp_tdata_next  = temp_tdata_reg;
    temp_tvalid_next = temp_tvalid_reg;

    m_beat_int   = '0;
    m_tvalid_int = 1'b0;

    load_code   = 1'b0;
    fail        = 1'b0;
    ready_force = 1'b0;
    ready_idle  = 1'b0;

    case (state_reg)
        STATE_IDLE: begin
            // output final byte
            m_beat_int.tdata = temp_tdata_reg;
            m_beat_int.tlast = temp_tvalid_reg;
            m_tvalid_int     = temp_tvalid_reg;
            temp_tvalid_next = temp_tvalid_reg && !m_ready_int_reg;

            // skip leading zeros, drop code byte with tlast
            if (s_xfer && s_tdata != 8'd0 && !s_tlast) begin
                load_code = 1'b1;
            end else begin
                ready_idle = 1'b1;
            end
        end
        STATE_SEGMENT: begin
            if (s_xfer) begin
                // store in temp, move temp to output
                temp_tdata_next  = s_tdata;
                temp_tvalid_next = 1'b1;
                m_beat_int.tdata = temp_tdata_reg;
                m_tvalid_int     = temp_tvalid_reg;
                count_next       = count_reg - 8'd1;
                if (s_tdata == 8'd0) begin
                    // zero inside segment
                    fail = 1'b1;
                end else if (s_tlast) begin
                    // end of frame, must be last byte of segment
                    if (count_reg == 8'd1 && !s_tuser) begin
                        state_next = STATE_IDLE;
                    end else begin
                        fail = 1'b1;
                    end
                end else if (count_reg == 8'd1) begin
                    state_next = STATE_NEXT_SEGMENT;
                end
            end
        end
        STATE_NEXT_SEGMENT: begin
            if (s_xfer) begin
                m_beat_int.tdata = temp_tdata_reg;
                if (!suppress_zero_reg) begin
                    // store zero in temp, move temp to output
                    temp_tdata_next  = 8'd0;
                    temp_tvalid_next = 1'b1;
                    m_tvalid_int     = temp_tvalid_reg;
                end
                // zero suppressed: keep last byte in temp, it may get tlast
                if (s_tdata == 8'd0) begin
                    // zero delimiter, end of frame
                    temp_tvalid_next = 1'b0;
                    m_tvalid_int     = temp_tvalid_reg;
                    m_beat_int.tuser = s_tuser;
                    m_beat_int.tlast = 1'b1;
                    ready_force      = 1'b1;
                    state_next       = STATE_IDLE;
                end else if (s_tlast) begin
                    // end of frame, must be code 1
                    if (s_tdata == 8'd1 && !s_tuser) begin
                        state_next = STATE_IDLE;
                    end else begin
                        fail = 1'b1;
                    end
                end else begin
                    load_code = 1'b1;
                end
            end
        end
        default: begin
            state_next = STATE_IDLE;
        end
    endcase

    if (load_code) begin
        // store count and zero suppress, code 1 has no data
        count_next         = s_tdata - 8'd1;
        suppress_zero_next = (s_tdata == 8'd255);
        state_next         = (s_tdata == 8'd1) ? STATE_NEXT_SEGMENT : STATE_SEGMENT;
    end

    if (fail) begin
        // mark frame as bad and re-sync
        temp_tvalid_next = 1'b0;
        m_tvalid_int     = 1'b1;
        m_beat_int.tuser = 1'b1;
        m_beat_int.tlast = 1'b1;
        ready_force      = 1'b1;
        state_next       = STATE_IDLE;
    end
end

// ready on re-sync, in idle also when temp is empty, else follow output
assign s_axis_tready_next = ready_force || m_ready_int_early || (ready_idle && !temp_tvalid_reg);

always_ff @(posedge clk) begin
    if (rst) begin
        state_reg         <= STATE_IDLE;
        temp_tvalid_reg   <= 1'b0;
        s_axis_tready_reg <= 1'b0;
    end else begin
        state_reg         <= state_next;
        temp_tvalid_reg   <= temp_tvalid_next;
        s_axis_tready_reg <= s_axis_tready_next;
    end
end

always_ff @(posedge clk) begin
    count_reg         <= count_next;
    suppress_zero_reg <= suppress_zero_next;
    temp_tdata_reg    <= temp_tdata_next;
end

// output skid buffer
logic   m_tvalid_reg, m_tvalid_next;
logic   temp_m_tvalid_reg, temp_m_tvalid_next;

// datapath registers, no reset
beat_t  out_reg;
beat_t  temp_m_reg;

store_t store;

assign m_axis.tdata  = out_reg.tdata;
assign m_axis.tkeep  = '1;
assign m_axis.tstrb  = '1;
assign m_axis.tlast  = out_reg.tlast;
assign m_axis.tid    = '0;
assign m_axis.tdest  = '0;
assign m_axis.tvalid = m_tvalid_reg;

// bad frame flag on tuser[0]
always_comb begin
    m_axis.tuser    = '0;
    m_axis.tuser[0] = out_reg.tuser;
end

// ready next cycle if output is ready or temp will not be filled (output empty or no input)
assign m_ready_int_early = m_axis.tready || (!temp_m_tvalid_reg && (!m_tvalid_reg || !m_tvalid_int));

always_comb begin
    m_tvalid_next      = m_tvalid_reg;
    temp_m_tvalid_next = temp_m_tvalid_reg;
    store              = STORE_NONE;

    if (m_ready_int_reg) begin
        if (m_axis.tready || !m_tvalid_reg) begin
            // output ready or not valid, input to output
            m_tvalid_next = m_tvalid_int;
            store = STORE_INT_TO_OUT;
        end else begin
            // output not ready, input to temp
            temp_m_tvalid_next = m_tvalid_int;
            store = STORE_INT_TO_TEMP;
        end
    end else if (m_axis.tready) begin
        // input not ready, output ready, temp to output
        m_tvalid_next      = temp_m_tvalid_reg;
        temp_m_tvalid_next = 1'b0;
        store = STORE_TEMP_TO_OUT;
    end
end

always_ff @(posedge clk) begin
    if (rst) begin
        m_tvalid_reg      <= 1'b0;
        m_ready_int_reg   <= 1'b0;
        temp_m_tvalid_reg <= 1'b0;
    end else begin
        m_tvalid_reg      <= m_tvalid_next;
        m_ready_int_reg   <= m_ready_int_early;
        temp_m_tvalid_reg <= temp_m_tvalid_next;
    end
end

// datapath
always_ff @(posedge clk) begin
    case (store)
        STORE_INT_TO_OUT:  out_reg    <= m_beat_int;
        STORE_INT_TO_TEMP: temp_m_reg <= m_beat_int;
        STORE_TEMP_TO_OUT: out_reg    <= temp_m_reg;
        STORE_NONE:        ;
        default:           ;
    endcase
end

endmodule

`resetall
