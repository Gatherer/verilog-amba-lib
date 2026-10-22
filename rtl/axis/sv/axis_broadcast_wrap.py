#!/usr/bin/env python3
"""
Generates an AXI Stream broadcast wrapper (SystemVerilog) with the specified number of ports
"""

import argparse
import sys

from jinja2 import Template


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("-p", "--ports", type=int, default=4, help="number of ports")
    parser.add_argument("-n", "--name", type=str, help="module name")
    parser.add_argument("-o", "--output", type=str, help="output file name")

    args = parser.parse_args()

    try:
        generate(**args.__dict__)
    except OSError as ex:
        print(ex)
        sys.exit(1)


def generate(ports=4, name=None, output=None):
    n = ports

    if name is None:
        name = f"axis_broadcast_wrap_{n}"

    if output is None:
        output = name + ".sv"

    print(f"Generating {n} port AXI stream broadcast wrapper {name}...")

    t = Template("""/*

Copyright (c) 2018-2021 Alex Forencich
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
 * AXI4-Stream {{n}} port broadcast (wrapper)
 * flat ports, maps to axis_if interfaces
 */
module {{name}} #(
    // width of AXI stream interfaces in bits
    parameter  int DATA_WIDTH  = 8,
    // propagate tkeep signal
    parameter  bit KEEP_ENABLE = (DATA_WIDTH > 8),
    // propagate tstrb signal
    parameter  bit STRB_ENABLE = 1'b0,
    // propagate tlast signal
    parameter  bit LAST_ENABLE = 1'b1,
    // propagate tid signal
    parameter  bit ID_ENABLE   = 1'b0,
    // tid signal width
    parameter  int ID_WIDTH    = 8,
    // propagate tdest signal
    parameter  bit DEST_ENABLE = 1'b0,
    // tdest signal width
    parameter  int DEST_WIDTH  = 8,
    // propagate tuser signal
    parameter  bit USER_ENABLE = 1'b1,
    // tuser signal width
    parameter  int USER_WIDTH  = 1,
    localparam int KEEP_WIDTH  = (DATA_WIDTH + 7) / 8,
    localparam int M_COUNT     = {{n}}
) (
    input  wire                  clk,
    input  wire                  rst,

    /*
     * AXI Stream input
     */
    input  wire [DATA_WIDTH-1:0] s_axis_tdata,
    input  wire [KEEP_WIDTH-1:0] s_axis_tkeep,
    input  wire [KEEP_WIDTH-1:0] s_axis_tstrb,
    input  wire                  s_axis_tvalid,
    output wire                  s_axis_tready,
    input  wire                  s_axis_tlast,
    input  wire [ID_WIDTH-1:0]   s_axis_tid,
    input  wire [DEST_WIDTH-1:0] s_axis_tdest,
    input  wire [USER_WIDTH-1:0] s_axis_tuser,

    /*
     * AXI Stream outputs
     */
{%- for p in range(n) %}
    output wire [DATA_WIDTH-1:0] m{{'%02d'%p}}_axis_tdata,
    output wire [KEEP_WIDTH-1:0] m{{'%02d'%p}}_axis_tkeep,
    output wire [KEEP_WIDTH-1:0] m{{'%02d'%p}}_axis_tstrb,
    output wire                  m{{'%02d'%p}}_axis_tvalid,
    input  wire                  m{{'%02d'%p}}_axis_tready,
    output wire                  m{{'%02d'%p}}_axis_tlast,
    output wire [ID_WIDTH-1:0]   m{{'%02d'%p}}_axis_tid,
    output wire [DEST_WIDTH-1:0] m{{'%02d'%p}}_axis_tdest,
    output wire [USER_WIDTH-1:0] m{{'%02d'%p}}_axis_tuser{% if not loop.last %},{% endif %}
{% endfor -%}
);

axis_if #(
    .DATA_WIDTH(DATA_WIDTH),
    .KEEP_WIDTH(KEEP_WIDTH),
    .KEEP_ENABLE(KEEP_ENABLE),
    .STRB_ENABLE(STRB_ENABLE),
    .LAST_ENABLE(LAST_ENABLE),
    .ID_ENABLE(ID_ENABLE),
    .ID_WIDTH(ID_WIDTH),
    .DEST_ENABLE(DEST_ENABLE),
    .DEST_WIDTH(DEST_WIDTH),
    .USER_ENABLE(USER_ENABLE),
    .USER_WIDTH(USER_WIDTH)
) s_axis (), m_axis [M_COUNT] ();

// slave interface
assign s_axis.tdata  = s_axis_tdata;
assign s_axis.tkeep  = s_axis_tkeep;
assign s_axis.tstrb  = s_axis_tstrb;
assign s_axis.tvalid = s_axis_tvalid;
assign s_axis.tlast  = s_axis_tlast;
assign s_axis.tid    = s_axis_tid;
assign s_axis.tdest  = s_axis_tdest;
assign s_axis.tuser  = s_axis_tuser;

assign s_axis_tready = s_axis.tready;
{% for p in range(n) %}
// master interface {{p}}
assign m{{'%02d'%p}}_axis_tdata  = m_axis[{{p}}].tdata;
assign m{{'%02d'%p}}_axis_tkeep  = m_axis[{{p}}].tkeep;
assign m{{'%02d'%p}}_axis_tstrb  = m_axis[{{p}}].tstrb;
assign m{{'%02d'%p}}_axis_tvalid = m_axis[{{p}}].tvalid;
assign m{{'%02d'%p}}_axis_tlast  = m_axis[{{p}}].tlast;
assign m{{'%02d'%p}}_axis_tid    = m_axis[{{p}}].tid;
assign m{{'%02d'%p}}_axis_tdest  = m_axis[{{p}}].tdest;
assign m{{'%02d'%p}}_axis_tuser  = m_axis[{{p}}].tuser;

assign m_axis[{{p}}].tready = m{{'%02d'%p}}_axis_tready;
{% endfor %}
axis_broadcast #(
    .M_COUNT(M_COUNT)
)
axis_broadcast_inst (
    .clk(clk),
    .rst(rst),
    .s_axis(s_axis),
    .m_axis(m_axis)
);

endmodule

`resetall

""")

    print(f"Writing file '{output}'...")

    with open(output, "w") as f:
        f.write(t.render(n=n, name=name))
        f.flush()

    print("Done")


if __name__ == "__main__":
    main()
