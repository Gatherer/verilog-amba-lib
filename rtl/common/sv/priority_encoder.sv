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
 * Priority encoder module
 */
module priority_encoder #(
    parameter  int unsigned WIDTH             = 4,
    // LSB priority selection
    parameter  bit          LSB_HIGH_PRIORITY = 1'b0,
    localparam int unsigned ENC_W             = WIDTH > 1 ? $clog2(WIDTH) : 1
) (
    input  wire  [WIDTH-1:0] input_unencoded,
    output logic             output_valid,
    output logic [ENC_W-1:0] output_encoded,
    output logic [WIDTH-1:0] output_unencoded
);

localparam int unsigned LEVELS = WIDTH > 2 ? $clog2(WIDTH) : 1;
localparam int unsigned W      = 2**LEVELS;

if (WIDTH < 1) begin : g_param_check
    $error("priority_encoder: WIDTH must be >= 1 (is %0d)", WIDTH);
end

// pad input to even power of two
logic [W-1:0] input_padded;

assign input_padded[WIDTH-1:0] = input_unencoded;

if (W > WIDTH) begin : g_pad
    assign input_padded[W-1:WIDTH] = '0;
end

// one node row per tree level; separate signals per level avoid UNOPTFLAT
for (genvar l = 0; l < LEVELS; l++) begin : g_level
    localparam int unsigned N  = W >> (l+1);  // nodes in this level
    localparam int unsigned EW = l + 1;       // encoded width per node

    logic [N-1:0]    valid;
    logic [N*EW-1:0] enc;

    for (genvar n = 0; n < N; n++) begin : g_node
        localparam int unsigned I = n;  // node index
        // select upper input of the pair
        logic sel_hi;

        if (l == 0) begin : g_leaf
            // process input bits; generate valid bit and encoded bit for each pair
            assign sel_hi   = LSB_HIGH_PRIORITY ? !input_padded[I*2] : input_padded[I*2+1];
            assign valid[I] = |input_padded[I*2 +: 2];
            assign enc[I]   = sel_hi;
        end else begin : g_merge
            // compress down to single valid bit and encoded bus
            assign sel_hi   = LSB_HIGH_PRIORITY ? !g_level[l-1].valid[I*2] : g_level[l-1].valid[I*2+1];
            assign valid[I] = |g_level[l-1].valid[I*2 +: 2];
            assign enc[I*EW +: EW] = sel_hi ? {1'b1, g_level[l-1].enc[(I*2+1)*(EW-1) +: EW-1]}
                                            : {1'b0, g_level[l-1].enc[(I*2+0)*(EW-1) +: EW-1]};
        end
    end
end

assign output_valid     = g_level[LEVELS-1].valid[0];
assign output_encoded   = g_level[LEVELS-1].enc[ENC_W-1:0];
assign output_unencoded = WIDTH'(1'b1) << output_encoded;

endmodule

`resetall
