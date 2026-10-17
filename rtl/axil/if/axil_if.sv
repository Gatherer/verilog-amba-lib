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

interface axil_if #(
    // width of data bus in bits
    parameter DATA_WIDTH = 32,
    // width of address bus in bits
    parameter ADDR_WIDTH = 32
)
();

// write address channel
logic awready;
logic awvalid;
logic [ADDR_WIDTH -1 : 0] awaddr;
logic [2 : 0] awprot;
// write data channel
logic wready;
logic wvalid;
logic [DATA_WIDTH -1 : 0] wdata;
logic [(DATA_WIDTH / 8) -1 : 0] wstrb;
// write response channel
logic bready;
logic bvalid;
logic [1 : 0] bresp;
// read address channel
logic arvalid;
logic arready;
logic [ADDR_WIDTH -1 : 0] araddr;
logic [2 : 0] arprot;
// read data channel
logic rready;
logic rvalid;
logic [DATA_WIDTH -1 : 0] rdata;
logic [1 : 0] rresp;

modport slave (
    // write address channel
    output awready,
    input awvalid,
    input awaddr,
    input awprot,
    // write data channel
    output wready,
    input wvalid,
    input wdata,
    input wstrb,
    // write response channel
    input bready,
    output bvalid,
    output bresp,
    // read address channel
    input arvalid,
    output arready,
    output araddr,
    output arprot,
    // read data channel
    input rready,
    output rvalid,
    output rdata,
    output rresp
);

modport master (
    // write address channel
    input awready,
    output awvalid,
    output awaddr,
    output awprot,
    // write data channel
    input wready,
    output wvalid,
    output wdata,
    output wstrb,
    // write response channel
    output bready,
    input bvalid,
    input bresp,
    // read address channel
    output arvalid,
    input arready,
    input araddr,
    input arprot,
    // read data channel
    output rready,
    input rvalid,
    input rdata,
    input rresp
);

endinterface: axil_if

`resetall
