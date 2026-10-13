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

// Language: Verilog 2005

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Priority encoder module
 */
module priority_encoder #
(
    parameter WIDTH = 4,
    // LSB priority selection
    parameter LSB_HIGH_PRIORITY = 0
)
(
    input  wire [WIDTH-1:0]                           input_unencoded,
    output wire                                       output_valid,
    output wire [(WIDTH > 1 ? $clog2(WIDTH) : 1)-1:0] output_encoded,
    output wire [WIDTH-1:0]                           output_unencoded
);

localparam LEVELS = WIDTH > 2 ? $clog2(WIDTH) : 1;
localparam W = 2**LEVELS;
localparam ENC_W = WIDTH > 1 ? $clog2(WIDTH) : 1;

// pad input to even power of two
wire [W-1:0] input_padded = {{W-WIDTH{1'b0}}, input_unencoded};

wire [W/2-1:0] stage_valid[LEVELS-1:0];
wire [W/2-1:0] stage_enc[LEVELS-1:0];

generate
    genvar l, n;

    // process input bits; generate valid bit and encoded bit for each pair
    for (n = 0; n < W/2; n = n + 1) begin : loop_in
        assign stage_valid[0][n] = |input_padded[n*2+1:n*2];
        if (LSB_HIGH_PRIORITY) begin : g_lsb_high
            // bit 0 is highest priority
            assign stage_enc[0][n] = !input_padded[n*2+0];
        end else begin : g_msb_high
            // bit 0 is lowest priority
            assign stage_enc[0][n] = input_padded[n*2+1];
        end
    end

    // compress down to single valid bit and encoded bus
    for (l = 1; l < LEVELS; l = l + 1) begin : loop_levels
        for (n = 0; n < W/(2*2**l); n = n + 1) begin : loop_compress
            // encoded values of the lower and upper input pair
            wire [l-1:0] enc_lo = stage_enc[l-1][(n*2+1)*l-1:(n*2+0)*l];
            wire [l-1:0] enc_hi = stage_enc[l-1][(n*2+2)*l-1:(n*2+1)*l];
            wire [l:0]   enc_out;

            assign stage_valid[l][n] = |stage_valid[l-1][n*2+1:n*2];
            assign stage_enc[l][(n+1)*(l+1)-1:n*(l+1)] = enc_out;

            if (LSB_HIGH_PRIORITY) begin : g_lsb_high
                // bit 0 is highest priority
                assign enc_out = stage_valid[l-1][n*2+0] ? {1'b0, enc_lo} : {1'b1, enc_hi};
            end else begin : g_msb_high
                // bit 0 is lowest priority
                assign enc_out = stage_valid[l-1][n*2+1] ? {1'b1, enc_hi} : {1'b0, enc_lo};
            end
        end
    end
endgenerate

assign output_valid = stage_valid[LEVELS-1][0];
assign output_encoded = stage_enc[LEVELS-1][ENC_W-1:0];
assign output_unencoded = 1 << output_encoded;

endmodule

`resetall
