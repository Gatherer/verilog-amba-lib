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
 * Reset clock domain crossing, based on sync_reset
 * src_rst sets a src_clk register asynchronously,
 * then N registers sync it into dst_clk
 * out is synchronous to dst_clk, also on assertion
 */
module sync_reset_cdc #(
    // depth of synchronizer in dst_clk
    parameter int N = 2
) (
    input  wire  src_clk,
    input  wire  src_rst,
    input  wire  dst_clk,
    output logic out
);

if (N < 2) begin : g_n_check
    $error("sync_reset_cdc: N must be at least 2");
end

(* srl_style = "register" *)
logic src_reg;

(* srl_style = "register" *)
logic [N-1:0] sync_reg;

assign out = sync_reg[N-1];

// src_rst is often also used as sync reset by the parent, intended
/* verilator lint_off SYNCASYNCNET */
always_ff @(posedge src_clk or posedge src_rst) begin
    if (src_rst) begin
        src_reg <= 1'b1;
    end else begin
        src_reg <= 1'b0;
    end
end
/* verilator lint_on SYNCASYNCNET */

always_ff @(posedge dst_clk) begin
    sync_reg <= {sync_reg[N-2:0], src_reg};
end

endmodule

`resetall
