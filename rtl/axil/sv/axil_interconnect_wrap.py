#!/usr/bin/env python3
"""
Generates an AXI lite interconnect wrapper (SystemVerilog) with the specified number of ports
"""

import argparse
import sys

from jinja2 import Template


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("-p", "--ports", type=int, default=[4], nargs="+", help="number of ports")
    parser.add_argument("-r", "--regions", type=int, default=1, help="number of regions per master interface")
    parser.add_argument("-n", "--name", type=str, help="module name")
    parser.add_argument("-o", "--output", type=str, help="output file name")

    args = parser.parse_args()

    try:
        generate(**args.__dict__)
    except OSError as ex:
        print(ex)
        sys.exit(1)


def generate(ports=4, regions=1, name=None, output=None):
    if type(ports) is int:
        m = n = ports
    elif len(ports) == 1:
        m = n = ports[0]
    else:
        m, n = ports

    if name is None:
        name = f"axil_interconnect_wrap_{m}x{n}"

    if output is None:
        output = name + ".sv"

    print(f"Generating {m}x{n} port AXI lite interconnect wrapper {name}...")

    t = Template("""/*

Copyright (c) 2020 Alex Forencich
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
 * AXI4 lite {{m}}x{{n}} interconnect (wrapper)
 * flat ports, maps to axil_if interfaces
 * Mxx_IF_ADDR_WIDTH: address width of master port xx, upper bits dropped
 */
module {{name}} #(
    parameter  int DATA_WIDTH = 32,
    parameter  int ADDR_WIDTH = 16,
    localparam int STRB_WIDTH = DATA_WIDTH / 8,
    localparam int S_COUNT    = {{m}},
    localparam int M_COUNT    = {{n}},
    localparam int M_REGIONS  = {{r}},
{%- for p in range(n) %}
    parameter logic [M_REGIONS-1:0][63:0] M{{'%02d'%p}}_BASE_ADDR     = '0,
    parameter logic [M_REGIONS-1:0][31:0] M{{'%02d'%p}}_ADDR_WIDTH    = {M_REGIONS{32'd24}},
    parameter int                         M{{'%02d'%p}}_IF_ADDR_WIDTH = ADDR_WIDTH,
    parameter bit   [S_COUNT-1:0]         M{{'%02d'%p}}_CONNECT_READ  = '1,
    parameter bit   [S_COUNT-1:0]         M{{'%02d'%p}}_CONNECT_WRITE = '1,
    parameter bit                         M{{'%02d'%p}}_SECURE        = 1'b0{% if not loop.last %},{% endif %}
{%- endfor %}
) (
    input  wire                     clk,
    input  wire                     rst,

    /*
     * AXI lite slave interfaces
     */
{%- for p in range(m) %}
    input  wire [ADDR_WIDTH-1:0]    s{{'%02d'%p}}_axil_awaddr,
    input  wire [2:0]               s{{'%02d'%p}}_axil_awprot,
    input  wire                     s{{'%02d'%p}}_axil_awvalid,
    output wire                     s{{'%02d'%p}}_axil_awready,
    input  wire [DATA_WIDTH-1:0]    s{{'%02d'%p}}_axil_wdata,
    input  wire [STRB_WIDTH-1:0]    s{{'%02d'%p}}_axil_wstrb,
    input  wire                     s{{'%02d'%p}}_axil_wvalid,
    output wire                     s{{'%02d'%p}}_axil_wready,
    output wire [1:0]               s{{'%02d'%p}}_axil_bresp,
    output wire                     s{{'%02d'%p}}_axil_bvalid,
    input  wire                     s{{'%02d'%p}}_axil_bready,
    input  wire [ADDR_WIDTH-1:0]    s{{'%02d'%p}}_axil_araddr,
    input  wire [2:0]               s{{'%02d'%p}}_axil_arprot,
    input  wire                     s{{'%02d'%p}}_axil_arvalid,
    output wire                     s{{'%02d'%p}}_axil_arready,
    output wire [DATA_WIDTH-1:0]    s{{'%02d'%p}}_axil_rdata,
    output wire [1:0]               s{{'%02d'%p}}_axil_rresp,
    output wire                     s{{'%02d'%p}}_axil_rvalid,
    input  wire                     s{{'%02d'%p}}_axil_rready,
{% endfor %}
    /*
     * AXI lite master interfaces
     */
{%- for p in range(n) %}
    output wire [M{{'%02d'%p}}_IF_ADDR_WIDTH-1:0] m{{'%02d'%p}}_axil_awaddr,
    output wire [2:0]               m{{'%02d'%p}}_axil_awprot,
    output wire                     m{{'%02d'%p}}_axil_awvalid,
    input  wire                     m{{'%02d'%p}}_axil_awready,
    output wire [DATA_WIDTH-1:0]    m{{'%02d'%p}}_axil_wdata,
    output wire [STRB_WIDTH-1:0]    m{{'%02d'%p}}_axil_wstrb,
    output wire                     m{{'%02d'%p}}_axil_wvalid,
    input  wire                     m{{'%02d'%p}}_axil_wready,
    input  wire [1:0]               m{{'%02d'%p}}_axil_bresp,
    input  wire                     m{{'%02d'%p}}_axil_bvalid,
    output wire                     m{{'%02d'%p}}_axil_bready,
    output wire [M{{'%02d'%p}}_IF_ADDR_WIDTH-1:0] m{{'%02d'%p}}_axil_araddr,
    output wire [2:0]               m{{'%02d'%p}}_axil_arprot,
    output wire                     m{{'%02d'%p}}_axil_arvalid,
    input  wire                     m{{'%02d'%p}}_axil_arready,
    input  wire [DATA_WIDTH-1:0]    m{{'%02d'%p}}_axil_rdata,
    input  wire [1:0]               m{{'%02d'%p}}_axil_rresp,
    input  wire                     m{{'%02d'%p}}_axil_rvalid,
    output wire                     m{{'%02d'%p}}_axil_rready{% if not loop.last %},{% endif %}
{% endfor -%}
);

// interconnect parameters, typed localparams (verilator needs them for unpacked arrays)
localparam logic [63:0] M_BASE_ADDR [M_COUNT][M_REGIONS] = '{
{%- for p in range(n) %}
    '{ {% for k in range(r) %}M{{'%02d'%p}}_BASE_ADDR[{{k}}]{% if not loop.last %}, {% endif %}{% endfor %} }{% if not loop.last %},{% endif %}
{%- endfor %}
};

localparam int M_ADDR_WIDTH [M_COUNT][M_REGIONS] = '{
{%- for p in range(n) %}
    '{ {% for k in range(r) %}int'(M{{'%02d'%p}}_ADDR_WIDTH[{{k}}]){% if not loop.last %}, {% endif %}{% endfor %} }{% if not loop.last %},{% endif %}
{%- endfor %}
};

localparam bit [S_COUNT-1:0] M_CONNECT_READ [M_COUNT] = '{
    {% for p in range(n) %}M{{'%02d'%p}}_CONNECT_READ{% if not loop.last %}, {% endif %}{% endfor %}
};

localparam bit [S_COUNT-1:0] M_CONNECT_WRITE [M_COUNT] = '{
    {% for p in range(n) %}M{{'%02d'%p}}_CONNECT_WRITE{% if not loop.last %}, {% endif %}{% endfor %}
};

localparam bit [M_COUNT-1:0] M_SECURE = { {% for p in range(n-1,-1,-1) %}M{{'%02d'%p}}_SECURE{% if not loop.last %}, {% endif %}{% endfor %} };

localparam int M_IF_ADDR_WIDTH [M_COUNT] = '{
    {% for p in range(n) %}M{{'%02d'%p}}_IF_ADDR_WIDTH{% if not loop.last %}, {% endif %}{% endfor %}
};

// port address width must fit into ADDR_WIDTH
{%- for p in range(n) %}
if (M{{'%02d'%p}}_IF_ADDR_WIDTH > ADDR_WIDTH) begin : g_m{{'%02d'%p}}_if_check
    $error("{{name}}: M{{'%02d'%p}}_IF_ADDR_WIDTH (%0d) > ADDR_WIDTH (%0d)", M{{'%02d'%p}}_IF_ADDR_WIDTH, ADDR_WIDTH);
end
{%- endfor %}

axil_if #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH)) s_axil [S_COUNT] ();
axil_if #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH)) m_axil [M_COUNT] ();
{% for p in range(m) %}
// slave interface {{p}}
assign s_axil[{{p}}].awaddr  = s{{'%02d'%p}}_axil_awaddr;
assign s_axil[{{p}}].awprot  = s{{'%02d'%p}}_axil_awprot;
assign s_axil[{{p}}].awvalid = s{{'%02d'%p}}_axil_awvalid;
assign s_axil[{{p}}].wdata   = s{{'%02d'%p}}_axil_wdata;
assign s_axil[{{p}}].wstrb   = s{{'%02d'%p}}_axil_wstrb;
assign s_axil[{{p}}].wvalid  = s{{'%02d'%p}}_axil_wvalid;
assign s_axil[{{p}}].bready  = s{{'%02d'%p}}_axil_bready;
assign s_axil[{{p}}].araddr  = s{{'%02d'%p}}_axil_araddr;
assign s_axil[{{p}}].arprot  = s{{'%02d'%p}}_axil_arprot;
assign s_axil[{{p}}].arvalid = s{{'%02d'%p}}_axil_arvalid;
assign s_axil[{{p}}].rready  = s{{'%02d'%p}}_axil_rready;

assign s{{'%02d'%p}}_axil_awready = s_axil[{{p}}].awready;
assign s{{'%02d'%p}}_axil_wready  = s_axil[{{p}}].wready;
assign s{{'%02d'%p}}_axil_bresp   = s_axil[{{p}}].bresp;
assign s{{'%02d'%p}}_axil_bvalid  = s_axil[{{p}}].bvalid;
assign s{{'%02d'%p}}_axil_arready = s_axil[{{p}}].arready;
assign s{{'%02d'%p}}_axil_rdata   = s_axil[{{p}}].rdata;
assign s{{'%02d'%p}}_axil_rresp   = s_axil[{{p}}].rresp;
assign s{{'%02d'%p}}_axil_rvalid  = s_axil[{{p}}].rvalid;
{% endfor %}
{%- for p in range(n) %}
// master interface {{p}}
// upper address bits are zero, see M_IF_ADDR_WIDTH
/* verilator lint_off UNUSEDSIGNAL */
assign m{{'%02d'%p}}_axil_awaddr  = m_axil[{{p}}].awaddr[M{{'%02d'%p}}_IF_ADDR_WIDTH-1:0];
assign m{{'%02d'%p}}_axil_awprot  = m_axil[{{p}}].awprot;
assign m{{'%02d'%p}}_axil_awvalid = m_axil[{{p}}].awvalid;
assign m{{'%02d'%p}}_axil_wdata   = m_axil[{{p}}].wdata;
assign m{{'%02d'%p}}_axil_wstrb   = m_axil[{{p}}].wstrb;
assign m{{'%02d'%p}}_axil_wvalid  = m_axil[{{p}}].wvalid;
assign m{{'%02d'%p}}_axil_bready  = m_axil[{{p}}].bready;
assign m{{'%02d'%p}}_axil_araddr  = m_axil[{{p}}].araddr[M{{'%02d'%p}}_IF_ADDR_WIDTH-1:0];
/* verilator lint_on UNUSEDSIGNAL */
assign m{{'%02d'%p}}_axil_arprot  = m_axil[{{p}}].arprot;
assign m{{'%02d'%p}}_axil_arvalid = m_axil[{{p}}].arvalid;
assign m{{'%02d'%p}}_axil_rready  = m_axil[{{p}}].rready;

assign m_axil[{{p}}].awready = m{{'%02d'%p}}_axil_awready;
assign m_axil[{{p}}].wready  = m{{'%02d'%p}}_axil_wready;
assign m_axil[{{p}}].bresp   = m{{'%02d'%p}}_axil_bresp;
assign m_axil[{{p}}].bvalid  = m{{'%02d'%p}}_axil_bvalid;
assign m_axil[{{p}}].arready = m{{'%02d'%p}}_axil_arready;
assign m_axil[{{p}}].rdata   = m{{'%02d'%p}}_axil_rdata;
assign m_axil[{{p}}].rresp   = m{{'%02d'%p}}_axil_rresp;
assign m_axil[{{p}}].rvalid  = m{{'%02d'%p}}_axil_rvalid;
{% endfor %}
axil_interconnect #(
    .S_COUNT(S_COUNT),
    .M_COUNT(M_COUNT),
    .M_REGIONS(M_REGIONS),
    .M_BASE_ADDR(M_BASE_ADDR),
    .M_ADDR_WIDTH(M_ADDR_WIDTH),
    .M_IF_ADDR_WIDTH(M_IF_ADDR_WIDTH),
    .M_CONNECT_READ(M_CONNECT_READ),
    .M_CONNECT_WRITE(M_CONNECT_WRITE),
    .M_SECURE(M_SECURE)
)
axil_interconnect_inst (
    .clk(clk),
    .rst(rst),
    .s_axil(s_axil),
    .m_axil(m_axil)
);

endmodule

`resetall

""")

    print(f"Writing file '{output}'...")

    with open(output, "w") as f:
        f.write(t.render(m=m, n=n, r=regions, name=name))
        f.flush()

    print("Done")


if __name__ == "__main__":
    main()
