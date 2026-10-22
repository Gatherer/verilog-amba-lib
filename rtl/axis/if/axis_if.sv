/*

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

interface axis_if #(
    // width of AXI stream interfaces
    parameter int DATA_WIDTH  = 8,
    // tkeep signal width
    parameter int KEEP_WIDTH  = ((DATA_WIDTH + 7) / 8),
    // use tkeep signal
    parameter bit KEEP_ENABLE = KEEP_WIDTH > 1,
    // use tstrb signal
    parameter bit STRB_ENABLE = 1'b0,
    // use tlast signal
    parameter bit LAST_ENABLE = 1'b1,
    // use tid signal
    parameter bit ID_ENABLE   = 1'b0,
    // tid signal width
    parameter int ID_WIDTH    = 8,
    // use tdest signal
    parameter bit DEST_ENABLE = 1'b0,
    // tdest signal width
    parameter int DEST_WIDTH  = 8,
    // use tuser signal
    parameter bit USER_ENABLE = 1'b0,
    // tuser signal width
    parameter int USER_WIDTH  = 1
)
();

logic [DATA_WIDTH -1 : 0] tdata;
logic [KEEP_WIDTH -1 : 0] tkeep;
logic [KEEP_WIDTH -1 : 0] tstrb;
logic [ID_WIDTH -1 : 0] tid;
logic [DEST_WIDTH -1 : 0] tdest;
logic [USER_WIDTH -1 : 0] tuser;
logic tlast;
logic tvalid;
logic tready;

modport master (
    output tdata,
    output tkeep,
    output tstrb,
    output tid,
    output tdest,
    output tuser,
    output tlast,
    output tvalid,
    input  tready
);

modport slave (
    input  tdata,
    input  tkeep,
    input  tstrb,
    input  tid,
    input  tdest,
    input  tuser,
    input  tlast,
    input  tvalid,
    output tready
);

modport monitor (
    input  tdata,
    input  tkeep,
    input  tstrb,
    input  tid,
    input  tdest,
    input  tuser,
    input  tlast,
    input  tvalid,
    input  tready
);

endinterface: axis_if

`resetall
