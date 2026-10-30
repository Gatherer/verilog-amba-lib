#!/usr/bin/env python3
"""
Generates an AXI Stream arbitrated mux wrapper (SystemVerilog) with the specified number of ports
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
        name = f"axis_arb_mux_wrap_{n}"

    if output is None:
        output = name + ".sv"

    print(f"Generating {n} port AXI stream arbitrated mux wrapper {name}...")

    cn = (n - 1).bit_length()

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
 * AXI4-Stream {{n}} port arbitrated mux (wrapper)
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
    // input tid signal width
    parameter  int S_ID_WIDTH  = 8,
    // output tid signal width
    parameter  int M_ID_WIDTH  = S_ID_WIDTH + {{cn}},
    // propagate tdest signal
    parameter  bit DEST_ENABLE = 1'b0,
    // tdest signal width
    parameter  int DEST_WIDTH  = 8,
    // propagate tuser signal
    parameter  bit USER_ENABLE = 1'b1,
    // tuser signal width
    parameter  int USER_WIDTH  = 1,
    // update tid with routing information
    parameter  bit UPDATE_TID  = 1'b0,
    // select round robin arbitration
    parameter  bit ARB_TYPE_ROUND_ROBIN  = 1'b0,
    // LSB priority selection
    parameter  bit ARB_LSB_HIGH_PRIORITY = 1'b1,
    localparam int KEEP_WIDTH  = (DATA_WIDTH + 7) / 8,
    localparam int S_COUNT     = {{n}}
) (
    input  wire                  clk,
    input  wire                  rst,

    /*
     * AXI Stream inputs
     */
{%- for p in range(n) %}
    input  wire [DATA_WIDTH-1:0] s{{'%02d'%p}}_axis_tdata,
    input  wire [KEEP_WIDTH-1:0] s{{'%02d'%p}}_axis_tkeep,
    input  wire [KEEP_WIDTH-1:0] s{{'%02d'%p}}_axis_tstrb,
    input  wire                  s{{'%02d'%p}}_axis_tvalid,
    output wire                  s{{'%02d'%p}}_axis_tready,
    input  wire                  s{{'%02d'%p}}_axis_tlast,
    input  wire [S_ID_WIDTH-1:0] s{{'%02d'%p}}_axis_tid,
    input  wire [DEST_WIDTH-1:0] s{{'%02d'%p}}_axis_tdest,
    input  wire [USER_WIDTH-1:0] s{{'%02d'%p}}_axis_tuser,
{% endfor %}
    /*
     * AXI Stream output
     */
    output wire [DATA_WIDTH-1:0] m_axis_tdata,
    output wire [KEEP_WIDTH-1:0] m_axis_tkeep,
    output wire [KEEP_WIDTH-1:0] m_axis_tstrb,
    output wire                  m_axis_tvalid,
    input  wire                  m_axis_tready,
    output wire                  m_axis_tlast,
    output wire [M_ID_WIDTH-1:0] m_axis_tid,
    output wire [DEST_WIDTH-1:0] m_axis_tdest,
    output wire [USER_WIDTH-1:0] m_axis_tuser
);

axis_if #(
    .DATA_WIDTH(DATA_WIDTH),
    .KEEP_WIDTH(KEEP_WIDTH),
    .KEEP_ENABLE(KEEP_ENABLE),
    .STRB_ENABLE(STRB_ENABLE),
    .LAST_ENABLE(LAST_ENABLE),
    .ID_ENABLE(ID_ENABLE),
    .ID_WIDTH(S_ID_WIDTH),
    .DEST_ENABLE(DEST_ENABLE),
    .DEST_WIDTH(DEST_WIDTH),
    .USER_ENABLE(USER_ENABLE),
    .USER_WIDTH(USER_WIDTH)
) s_axis [S_COUNT] ();

axis_if #(
    .DATA_WIDTH(DATA_WIDTH),
    .KEEP_WIDTH(KEEP_WIDTH),
    .KEEP_ENABLE(KEEP_ENABLE),
    .STRB_ENABLE(STRB_ENABLE),
    .LAST_ENABLE(LAST_ENABLE),
    .ID_ENABLE(ID_ENABLE),
    .ID_WIDTH(M_ID_WIDTH),
    .DEST_ENABLE(DEST_ENABLE),
    .DEST_WIDTH(DEST_WIDTH),
    .USER_ENABLE(USER_ENABLE),
    .USER_WIDTH(USER_WIDTH)
) m_axis ();
{% for p in range(n) %}
// slave interface {{p}}
assign s_axis[{{p}}].tdata  = s{{'%02d'%p}}_axis_tdata;
assign s_axis[{{p}}].tkeep  = s{{'%02d'%p}}_axis_tkeep;
assign s_axis[{{p}}].tstrb  = s{{'%02d'%p}}_axis_tstrb;
assign s_axis[{{p}}].tvalid = s{{'%02d'%p}}_axis_tvalid;
assign s_axis[{{p}}].tlast  = s{{'%02d'%p}}_axis_tlast;
assign s_axis[{{p}}].tid    = s{{'%02d'%p}}_axis_tid;
assign s_axis[{{p}}].tdest  = s{{'%02d'%p}}_axis_tdest;
assign s_axis[{{p}}].tuser  = s{{'%02d'%p}}_axis_tuser;

assign s{{'%02d'%p}}_axis_tready = s_axis[{{p}}].tready;
{% endfor %}
// master interface
assign m_axis_tdata  = m_axis.tdata;
assign m_axis_tkeep  = m_axis.tkeep;
assign m_axis_tstrb  = m_axis.tstrb;
assign m_axis_tvalid = m_axis.tvalid;
assign m_axis_tlast  = m_axis.tlast;
assign m_axis_tid    = m_axis.tid;
assign m_axis_tdest  = m_axis.tdest;
assign m_axis_tuser  = m_axis.tuser;

assign m_axis.tready = m_axis_tready;

axis_arb_mux #(
    .S_COUNT(S_COUNT),
    .UPDATE_TID(UPDATE_TID),
    .ARB_TYPE_ROUND_ROBIN(ARB_TYPE_ROUND_ROBIN),
    .ARB_LSB_HIGH_PRIORITY(ARB_LSB_HIGH_PRIORITY)
)
axis_arb_mux_inst (
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
        f.write(t.render(n=n, cn=cn, name=name))
        f.flush()

    print("Done")


if __name__ == "__main__":
    main()
