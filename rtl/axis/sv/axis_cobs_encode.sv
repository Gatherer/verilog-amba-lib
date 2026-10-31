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
 * AXI4-Stream consistent overhead byte stuffing (COBS) encoder
 * s_axis: 8 bit, tlast required, tuser optional (disabled = 0)
 * m_axis: 8 bit, tlast and tuser required, tuser[0] marks bad frames
 * tkeep, tstrb, tid, tdest are dropped
 */
module axis_cobs_encode #(
    // append zero for in band framing
    parameter bit APPEND_ZERO = 1'b1
) (
    input  wire    clk,
    input  wire    rst,

    axis_if.slave  s_axis,
    axis_if.master m_axis
);

localparam int DATA_WIDTH  = s_axis.DATA_WIDTH;
localparam bit LAST_ENABLE = s_axis.LAST_ENABLE;
localparam bit USER_ENABLE = s_axis.USER_ENABLE;

// parameter checks
if (DATA_WIDTH != 8 || !LAST_ENABLE) begin : g_s_check
    $error("axis_cobs_encode: s_axis needs DATA_WIDTH 8 and LAST_ENABLE");
end

if (m_axis.DATA_WIDTH != 8 || !m_axis.LAST_ENABLE || !m_axis.USER_ENABLE) begin : g_m_check
    $error("axis_cobs_encode: m_axis needs DATA_WIDTH 8, LAST_ENABLE and USER_ENABLE");
end

typedef enum logic [1:0] {
    INPUT_STATE_SEGMENT,
    INPUT_STATE_FINAL_ZERO,
    INPUT_STATE_APPEND_ZERO
} input_state_t;

typedef enum logic {
    OUTPUT_STATE_IDLE,
    OUTPUT_STATE_SEGMENT
} output_state_t;

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

input_state_t  input_state_reg, input_state_next;
output_state_t output_state_reg, output_state_next;

logic       fail_frame_reg, fail_frame_next;

// segment code, 1 at segment start
logic [7:0] input_count_reg, input_count_next;

// loaded before use, no reset
logic [7:0] output_count_reg, output_count_next;

// input, disabled tuser is 0
logic [7:0] s_tdata;
logic       s_tlast;
logic       s_tuser;
logic       s_axis_tready_mask;

// both FIFOs can take a byte
logic       fifo_in_tready;

// internal datapath
beat_t      m_beat_int;
logic       m_tvalid_int;
logic       m_ready_int_reg;
logic       m_ready_int_early;

// code and data FIFOs
axis_if #(.USER_ENABLE(1'b1)) code_fifo_in (), code_fifo_out ();
axis_if data_fifo_in (), data_fifo_out ();

// FIFO status, not used: overflow, bad frame, good frame
logic       code_pause_ack, data_pause_ack;
logic [8:0] code_depth, code_depth_commit, data_depth, data_depth_commit;
logic [2:0] code_status, data_status;

// not used by the encoder
/* verilator lint_off UNUSEDSIGNAL */
logic       unused;
/* verilator lint_on UNUSEDSIGNAL */

assign unused = ^{s_axis.tkeep, s_axis.tstrb, s_axis.tid, s_axis.tdest, s_axis.tuser,
                  s_axis.KEEP_ENABLE, s_axis.STRB_ENABLE, s_axis.ID_ENABLE, s_axis.DEST_ENABLE,
                  code_fifo_out.tkeep, code_fifo_out.tstrb, code_fifo_out.tid, code_fifo_out.tdest,
                  data_fifo_out.tkeep, data_fifo_out.tstrb, data_fifo_out.tid, data_fifo_out.tdest,
                  data_fifo_out.tuser,
                  code_pause_ack, code_depth, code_depth_commit, code_status,
                  data_pause_ack, data_depth, data_depth_commit, data_status};

assign s_tdata = s_axis.tdata;
assign s_tlast = s_axis.tlast;
assign s_tuser = USER_ENABLE ? s_axis.tuser[0] : 1'b0;

assign fifo_in_tready = code_fifo_in.tready && data_fifo_in.tready;
assign s_axis.tready  = fifo_in_tready && s_axis_tready_mask;

assign code_fifo_in.tkeep = '1;
assign code_fifo_in.tstrb = '1;
assign code_fifo_in.tid   = '0;
assign code_fifo_in.tdest = '0;

assign data_fifo_in.tkeep = '1;
assign data_fifo_in.tstrb = '1;
assign data_fifo_in.tid   = '0;
assign data_fifo_in.tdest = '0;
assign data_fifo_in.tuser = '0;

axis_fifo #(
    .DEPTH(256),
    .FRAME_FIFO(1'b0)
)
code_fifo_inst (
    .clk(clk),
    .rst(rst),
    .s_axis(code_fifo_in),
    .m_axis(code_fifo_out),
    .pause_req(1'b0),
    .pause_ack(code_pause_ack),
    .status_depth(code_depth),
    .status_depth_commit(code_depth_commit),
    .status_overflow(code_status[0]),
    .status_bad_frame(code_status[1]),
    .status_good_frame(code_status[2])
);

axis_fifo #(
    .DEPTH(256),
    .FRAME_FIFO(1'b0)
)
data_fifo_inst (
    .clk(clk),
    .rst(rst),
    .s_axis(data_fifo_in),
    .m_axis(data_fifo_out),
    .pause_req(1'b0),
    .pause_ack(data_pause_ack),
    .status_depth(data_depth),
    .status_depth_commit(data_depth_commit),
    .status_overflow(data_status[0]),
    .status_bad_frame(data_status[1]),
    .status_good_frame(data_status[2])
);

always_comb begin
    input_state_next = input_state_reg;
    input_count_next = input_count_reg;
    fail_frame_next  = fail_frame_reg;

    s_axis_tready_mask = 1'b0;

    code_fifo_in.tdata  = 8'd0;
    code_fifo_in.tvalid = 1'b0;
    code_fifo_in.tlast  = 1'b0;
    code_fifo_in.tuser  = 1'b0;

    data_fifo_in.tdata  = s_tdata;
    data_fifo_in.tvalid = 1'b0;
    data_fifo_in.tlast  = 1'b0;

    case (input_state_reg)
        INPUT_STATE_SEGMENT: begin
            // encode segment
            s_axis_tready_mask = 1'b1;
            fail_frame_next    = 1'b0;

            if (fifo_in_tready && s_axis.tvalid) begin
                if (s_tdata == 8'd0 || (s_tlast && s_tuser)) begin
                    // zero or propagated error, store code
                    code_fifo_in.tdata  = input_count_reg;
                    code_fifo_in.tvalid = 1'b1;
                    input_count_next    = 8'd1;
                    if (s_tlast) begin
                        // last byte, close out the frame
                        fail_frame_next  = s_tuser;
                        input_state_next = INPUT_STATE_FINAL_ZERO;
                    end
                end else begin
                    // store data and count
                    input_count_next    = input_count_reg + 8'd1;
                    data_fifo_in.tvalid = 1'b1;
                    if (input_count_reg == 8'd254 || s_tlast) begin
                        // full segment or last byte, store code
                        code_fifo_in.tdata  = input_count_reg + 8'd1;
                        code_fifo_in.tvalid = 1'b1;
                        input_count_next    = 8'd1;
                    end
                    if (s_tlast) begin
                        if (APPEND_ZERO) begin
                            // add a zero to end the frame
                            input_state_next = INPUT_STATE_APPEND_ZERO;
                        end else begin
                            data_fifo_in.tlast = 1'b1;
                        end
                    end
                end
            end
        end
        INPUT_STATE_FINAL_ZERO: begin
            // final zero code, error frames get a code without data
            if (code_fifo_in.tready) begin
                code_fifo_in.tdata  = fail_frame_reg ? 8'd2 : 8'd1;
                code_fifo_in.tuser  = fail_frame_reg;
                code_fifo_in.tvalid = 1'b1;
                if (APPEND_ZERO) begin
                    input_state_next = INPUT_STATE_APPEND_ZERO;
                end else begin
                    code_fifo_in.tlast = 1'b1;
                    fail_frame_next    = 1'b0;
                    input_state_next   = INPUT_STATE_SEGMENT;
                end
            end
        end
        INPUT_STATE_APPEND_ZERO: begin
            // frame termination code for zero framing
            if (code_fifo_in.tready) begin
                code_fifo_in.tdata  = 8'd0;
                code_fifo_in.tlast  = 1'b1;
                code_fifo_in.tuser  = fail_frame_reg;
                code_fifo_in.tvalid = 1'b1;
                fail_frame_next     = 1'b0;
                input_state_next    = INPUT_STATE_SEGMENT;
            end
        end
        default: begin
            input_state_next = INPUT_STATE_SEGMENT;
        end
    endcase
end

always_comb begin
    output_state_next = output_state_reg;
    output_count_next = output_count_reg;

    m_beat_int   = '0;
    m_tvalid_int = 1'b0;

    code_fifo_out.tready = 1'b0;
    data_fifo_out.tready = 1'b0;

    case (output_state_reg)
        OUTPUT_STATE_IDLE: begin
            if (m_ready_int_reg && code_fifo_out.tvalid) begin
                // code byte out, load counter
                m_beat_int.tdata     = code_fifo_out.tdata;
                m_beat_int.tlast     = code_fifo_out.tlast;
                m_beat_int.tuser     = code_fifo_out.tuser && code_fifo_out.tlast;
                m_tvalid_int         = 1'b1;
                output_count_next    = code_fifo_out.tdata - 8'd1;
                code_fifo_out.tready = 1'b1;
                // codes 0, 1 and error codes have no data
                if (code_fifo_out.tdata != 8'd0 && code_fifo_out.tdata != 8'd1 && !code_fifo_out.tuser) begin
                    output_state_next = OUTPUT_STATE_SEGMENT;
                end
            end
        end
        OUTPUT_STATE_SEGMENT: begin
            if (m_ready_int_reg && data_fifo_out.tvalid) begin
                // data byte out, decrement counter
                m_beat_int.tdata     = data_fifo_out.tdata;
                m_beat_int.tlast     = data_fifo_out.tlast;
                m_tvalid_int         = 1'b1;
                output_count_next    = output_count_reg - 8'd1;
                data_fifo_out.tready = 1'b1;
                if (output_count_reg == 8'd1) begin
                    // segment done, code byte next
                    output_state_next = OUTPUT_STATE_IDLE;
                end
            end
        end
        default: begin
            output_state_next = OUTPUT_STATE_IDLE;
        end
    endcase
end

always_ff @(posedge clk) begin
    if (rst) begin
        input_state_reg  <= INPUT_STATE_SEGMENT;
        output_state_reg <= OUTPUT_STATE_IDLE;
        input_count_reg  <= 8'd1;
        fail_frame_reg   <= 1'b0;
    end else begin
        input_state_reg  <= input_state_next;
        output_state_reg <= output_state_next;
        input_count_reg  <= input_count_next;
        fail_frame_reg   <= fail_frame_next;
    end
end

always_ff @(posedge clk) begin
    output_count_reg <= output_count_next;
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
