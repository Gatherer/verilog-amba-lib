/*

Copyright (c) 2014-2021 Alex Forencich
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
 * Arbiter module
 */
module arbiter #(
    parameter  int unsigned PORTS                 = 4,
    // select round robin arbitration
    parameter  bit          ARB_TYPE_ROUND_ROBIN  = 1'b0,
    // blocking arbiter enable
    parameter  bit          ARB_BLOCK             = 1'b0,
    // block on acknowledge assert when nonzero, request deassert when 0
    parameter  bit          ARB_BLOCK_ACK         = 1'b1,
    // LSB priority selection
    parameter  bit          ARB_LSB_HIGH_PRIORITY = 1'b0,
    localparam int unsigned ENC_W                 = PORTS > 1 ? $clog2(PORTS) : 1
) (
    input  wire              clk,
    input  wire              rst,

    input  wire  [PORTS-1:0] request,
    input  wire  [PORTS-1:0] acknowledge,

    output logic [PORTS-1:0] grant,
    output logic             grant_valid,
    output logic [ENC_W-1:0] grant_encoded
);

if (PORTS < 1) begin : g_param_check
    $error("arbiter: PORTS must be >= 1 (is %0d)", PORTS);
end

logic [PORTS-1:0] grant_next;
logic             grant_valid_next;
logic [ENC_W-1:0] grant_encoded_next;

// current grant is kept
logic             hold;

logic             request_valid;
logic [ENC_W-1:0] request_index;
logic [PORTS-1:0] request_mask;

// request selected for the next grant
logic [ENC_W-1:0] select_index;
logic [PORTS-1:0] select_mask;

priority_encoder #(
    .WIDTH(PORTS),
    .LSB_HIGH_PRIORITY(ARB_LSB_HIGH_PRIORITY)
) priority_encoder_inst (
    .input_unencoded(request),
    .output_valid(request_valid),
    .output_encoded(request_index),
    .output_unencoded(request_mask)
);

// blocking on acknowledge: granted request not yet acknowledged; hold it
// blocking on request: granted request still asserted; hold it
assign hold = ARB_BLOCK && (ARB_BLOCK_ACK ? grant_valid && !(|(grant & acknowledge))
                                          : |(grant & request));

if (ARB_TYPE_ROUND_ROBIN) begin : g_round_robin
    logic [PORTS-1:0] mask_reg, mask_next;
    logic [PORTS-1:0] request_masked;

    logic             masked_request_valid;
    logic [ENC_W-1:0] masked_request_index;
    logic [PORTS-1:0] masked_request_mask;

    // requests of lower priority than the last granted port
    assign request_masked = request & mask_reg;

    priority_encoder #(
        .WIDTH(PORTS),
        .LSB_HIGH_PRIORITY(ARB_LSB_HIGH_PRIORITY)
    ) priority_encoder_masked (
        .input_unencoded(request_masked),
        .output_valid(masked_request_valid),
        .output_encoded(masked_request_index),
        .output_unencoded(masked_request_mask)
    );

    // wrap around to the highest priority request when no masked request is left
    assign select_index = masked_request_valid ? masked_request_index : request_index;
    assign select_mask  = masked_request_valid ? masked_request_mask  : request_mask;

    always_comb begin
        mask_next = mask_reg;

        if (!hold && request_valid) begin
            if (ARB_LSB_HIGH_PRIORITY) begin
                mask_next = {PORTS{1'b1}} << (int'(select_index) + 1);
            end else begin
                mask_next = {PORTS{1'b1}} >> (PORTS - int'(select_index));
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            mask_reg <= '0;
        end else begin
            mask_reg <= mask_next;
        end
    end
end else begin : g_fixed_priority
    assign select_index = request_index;
    assign select_mask  = request_mask;
end

always_comb begin
    grant_next = '0;
    grant_valid_next = 1'b0;
    grant_encoded_next = '0;

    if (hold) begin
        grant_valid_next = grant_valid;
        grant_next = grant;
        grant_encoded_next = grant_encoded;
    end else if (request_valid) begin
        grant_valid_next = 1'b1;
        grant_next = select_mask;
        grant_encoded_next = select_index;
    end
end

always_ff @(posedge clk) begin
    if (rst) begin
        grant <= '0;
        grant_valid <= 1'b0;
        grant_encoded <= '0;
    end else begin
        grant <= grant_next;
        grant_valid <= grant_valid_next;
        grant_encoded <= grant_encoded_next;
    end
end

endmodule

`resetall
