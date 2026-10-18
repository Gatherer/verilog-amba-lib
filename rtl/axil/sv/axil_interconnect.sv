/*

Copyright (c) 2018 Alex Forencich
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
 * AXI4 lite interconnect
 * data and address width are taken from s_axil[0]
 */
module axil_interconnect #(
    // number of AXI inputs (slave interfaces)
    parameter int               S_COUNT                          = 4,
    // number of AXI outputs (master interfaces)
    parameter int               M_COUNT                          = 4,
    // number of regions per master interface
    parameter int               M_REGIONS                        = 1,
    // master interface base addresses, truncated to address width
    // all zero for default addressing based on M_ADDR_WIDTH
    parameter logic [63:0]      M_BASE_ADDR [M_COUNT][M_REGIONS] = '{default: '0},
    // master interface address widths, zero disables the region
    parameter int               M_ADDR_WIDTH[M_COUNT][M_REGIONS] = '{default: 24},
    // read connections, one bit per slave interface
    parameter bit [S_COUNT-1:0] M_CONNECT_READ [M_COUNT]         = '{default: '1},
    // write connections, one bit per slave interface
    parameter bit [S_COUNT-1:0] M_CONNECT_WRITE[M_COUNT]         = '{default: '1},
    // secure master (fail operations based on awprot/arprot)
    parameter bit [M_COUNT-1:0] M_SECURE                         = '0
) (
    input  wire    clk,
    input  wire    rst,

    axil_if.slave  s_axil [S_COUNT],
    axil_if.master m_axil [M_COUNT]
);

localparam int DATA_WIDTH = s_axil[0].DATA_WIDTH;
localparam int ADDR_WIDTH = s_axil[0].ADDR_WIDTH;
localparam int STRB_WIDTH = DATA_WIDTH / 8;

localparam int CL_S_COUNT = $clog2(S_COUNT);
localparam int CL_M_COUNT = $clog2(M_COUNT);
// select widths, at least 1 bit
localparam int S_SEL_W = CL_S_COUNT > 0 ? CL_S_COUNT : 1;
localparam int M_SEL_W = CL_M_COUNT > 0 ? CL_M_COUNT : 1;

localparam int REGION_COUNT = M_COUNT * M_REGIONS;

// parameter checks
if (ADDR_WIDTH > 64) begin : g_addr_width_check
    $error("axil_interconnect: address width must be <= 64 (is %0d)", ADDR_WIDTH);
end

if (DATA_WIDTH % 8 != 0) begin : g_data_width_check
    $error("axil_interconnect: data width must be a multiple of 8 (is %0d)", DATA_WIDTH);
end

for (genvar n = 1; n < S_COUNT; n++) begin : g_s_width_check
    if (s_axil[n].DATA_WIDTH != DATA_WIDTH || s_axil[n].ADDR_WIDTH != ADDR_WIDTH) begin : g_err
        $error("axil_interconnect: s_axil[%0d] width differs from s_axil[0]", n);
    end
end

for (genvar n = 0; n < M_COUNT; n++) begin : g_m_width_check
    if (m_axil[n].DATA_WIDTH != DATA_WIDTH || m_axil[n].ADDR_WIDTH != ADDR_WIDTH) begin : g_err
        $error("axil_interconnect: m_axil[%0d] width differs from s_axil[0]", n);
    end
end

typedef logic [ADDR_WIDTH-1:0] addr_t;
// packed, so functions can return it as constant
typedef addr_t [M_COUNT-1:0][M_REGIONS-1:0] region_addr_t;

// address mask of a region with given width
function automatic addr_t width_mask(int width);
    return {ADDR_WIDTH{1'b1}} >> (ADDR_WIDTH - width);
endfunction

// base addresses; user values or default addressing
function automatic region_addr_t calc_base_addrs();
    region_addr_t addrs;
    addr_t base = '0;
    addr_t mask;
    bit user = 1'b0;

    for (int mi = 0; mi < M_COUNT; mi++) begin
        for (int ri = 0; ri < M_REGIONS; ri++) begin
            addrs[mi][ri] = addr_t'(M_BASE_ADDR[mi][ri]);
            user |= M_BASE_ADDR[mi][ri] != 0;
        end
    end

    if (!user) begin
        for (int mi = 0; mi < M_COUNT; mi++) begin
            for (int ri = 0; ri < M_REGIONS; ri++) begin
                mask = width_mask(M_ADDR_WIDTH[mi][ri]);
                addrs[mi][ri] = '0;
                if (M_ADDR_WIDTH[mi][ri] > 0) begin
                    if ((base & mask) != 0) begin
                        base = base + mask + 1'b1 - (base & mask); // align
                    end
                    addrs[mi][ri] = base;
                    base = base + mask + 1'b1; // increment
                end
            end
        end
    end

    return addrs;
endfunction

function automatic region_addr_t calc_masks();
    region_addr_t masks;
    for (int mi = 0; mi < M_COUNT; mi++) begin
        for (int ri = 0; ri < M_REGIONS; ri++) begin
            masks[mi][ri] = width_mask(M_ADDR_WIDTH[mi][ri]);
        end
    end
    return masks;
endfunction

localparam region_addr_t M_BASE_ADDR_INT = calc_base_addrs();
localparam region_addr_t M_MASK_INT      = calc_masks();

// region helpers for config check, k = mi * M_REGIONS + ri
function automatic int region_width(int k);
    return M_ADDR_WIDTH[k / M_REGIONS][k % M_REGIONS];
endfunction

function automatic addr_t region_base(int k);
    return M_BASE_ADDR_INT[k / M_REGIONS][k % M_REGIONS];
endfunction

function automatic addr_t region_mask(int k);
    return M_MASK_INT[k / M_REGIONS][k % M_REGIONS];
endfunction

task automatic print_region(int k);
    $display("%2d (%2d): %x / %2d -- %x-%x",
        k / M_REGIONS, k % M_REGIONS,
        region_base(k),
        region_width(k),
        region_base(k) & ~region_mask(k),
        region_base(k) | region_mask(k)
    );
endtask

// check configuration
initial begin
    for (int i = 0; i < REGION_COUNT; i++) begin
        if (region_width(i) != 0 && (region_width(i) < $clog2(STRB_WIDTH) || region_width(i) > ADDR_WIDTH)) begin
            $fatal(1, "Error: address width out of range (instance %m)");
        end
    end

    $display("Addressing configuration for axil_interconnect instance %m");
    for (int i = 0; i < REGION_COUNT; i++) begin
        if (region_width(i) != 0) begin
            print_region(i);
        end
    end

    for (int i = 0; i < REGION_COUNT; i++) begin
        if ((region_base(i) & region_mask(i)) != 0) begin
            $display("Region not aligned:");
            print_region(i);
            $fatal(1, "Error: address range not aligned (instance %m)");
        end
    end

    for (int i = 0; i < REGION_COUNT; i++) begin
        for (int j = i+1; j < REGION_COUNT; j++) begin
            if (region_width(i) != 0 && region_width(j) != 0
                    && (region_base(i) & ~region_mask(i)) <= (region_base(j) | region_mask(j))
                    && (region_base(j) & ~region_mask(j)) <= (region_base(i) | region_mask(i))) begin
                $display("Overlapping regions:");
                print_region(i);
                print_region(j);
                $fatal(1, "Error: address ranges overlap (instance %m)");
            end
        end
    end
end

typedef enum {
    STATE_IDLE,
    STATE_DECODE,
    STATE_WRITE,
    STATE_WRITE_RESP,
    STATE_WRITE_DROP,
    STATE_READ,
    STATE_WAIT_IDLE
} state_t;

state_t state_reg, state_next;

logic [M_SEL_W-1:0]    m_select_reg, m_select_next;
addr_t                 axil_addr_reg, axil_addr_next;
logic                  axil_addr_valid_reg, axil_addr_valid_next;
logic [2:0]            axil_prot_reg, axil_prot_next;
logic [DATA_WIDTH-1:0] axil_data_reg, axil_data_next;
logic [STRB_WIDTH-1:0] axil_wstrb_reg, axil_wstrb_next;
logic [1:0]            axil_resp_reg, axil_resp_next;

logic [S_COUNT-1:0] s_axil_awready_reg, s_axil_awready_next;
logic [S_COUNT-1:0] s_axil_wready_reg, s_axil_wready_next;
logic [S_COUNT-1:0] s_axil_bvalid_reg, s_axil_bvalid_next;
logic [S_COUNT-1:0] s_axil_arready_reg, s_axil_arready_next;
logic [S_COUNT-1:0] s_axil_rvalid_reg, s_axil_rvalid_next;

logic [M_COUNT-1:0] m_axil_awvalid_reg, m_axil_awvalid_next;
logic [M_COUNT-1:0] m_axil_wvalid_reg, m_axil_wvalid_next;
logic [M_COUNT-1:0] m_axil_bready_reg, m_axil_bready_next;
logic [M_COUNT-1:0] m_axil_arvalid_reg, m_axil_arvalid_next;
logic [M_COUNT-1:0] m_axil_rready_reg, m_axil_rready_next;

// slave interface signals
addr_t                 s_axil_awaddr [S_COUNT];
logic [2:0]            s_axil_awprot [S_COUNT];
logic [S_COUNT-1:0]    s_axil_awvalid;
logic [DATA_WIDTH-1:0] s_axil_wdata  [S_COUNT];
logic [STRB_WIDTH-1:0] s_axil_wstrb  [S_COUNT];
logic [S_COUNT-1:0]    s_axil_wvalid;
logic [S_COUNT-1:0]    s_axil_bready;
addr_t                 s_axil_araddr [S_COUNT];
logic [2:0]            s_axil_arprot [S_COUNT];
logic [S_COUNT-1:0]    s_axil_arvalid;
logic [S_COUNT-1:0]    s_axil_rready;

// master interface signals
logic [M_COUNT-1:0]    m_axil_awready;
logic [M_COUNT-1:0]    m_axil_wready;
logic [1:0]            m_axil_bresp  [M_COUNT];
logic [M_COUNT-1:0]    m_axil_bvalid;
logic [M_COUNT-1:0]    m_axil_arready;
logic [DATA_WIDTH-1:0] m_axil_rdata  [M_COUNT];
logic [1:0]            m_axil_rresp  [M_COUNT];
logic [M_COUNT-1:0]    m_axil_rvalid;

for (genvar n = 0; n < S_COUNT; n++) begin : g_s_axil
    assign s_axil_awaddr[n]  = s_axil[n].awaddr;
    assign s_axil_awprot[n]  = s_axil[n].awprot;
    assign s_axil_awvalid[n] = s_axil[n].awvalid;
    assign s_axil_wdata[n]   = s_axil[n].wdata;
    assign s_axil_wstrb[n]   = s_axil[n].wstrb;
    assign s_axil_wvalid[n]  = s_axil[n].wvalid;
    assign s_axil_bready[n]  = s_axil[n].bready;
    assign s_axil_araddr[n]  = s_axil[n].araddr;
    assign s_axil_arprot[n]  = s_axil[n].arprot;
    assign s_axil_arvalid[n] = s_axil[n].arvalid;
    assign s_axil_rready[n]  = s_axil[n].rready;

    assign s_axil[n].awready = s_axil_awready_reg[n];
    assign s_axil[n].wready  = s_axil_wready_reg[n];
    assign s_axil[n].bresp   = axil_resp_reg;
    assign s_axil[n].bvalid  = s_axil_bvalid_reg[n];
    assign s_axil[n].arready = s_axil_arready_reg[n];
    assign s_axil[n].rdata   = axil_data_reg;
    assign s_axil[n].rresp   = axil_resp_reg;
    assign s_axil[n].rvalid  = s_axil_rvalid_reg[n];
end

for (genvar n = 0; n < M_COUNT; n++) begin : g_m_axil
    assign m_axil[n].awaddr  = axil_addr_reg;
    assign m_axil[n].awprot  = axil_prot_reg;
    assign m_axil[n].awvalid = m_axil_awvalid_reg[n];
    assign m_axil[n].wdata   = axil_data_reg;
    assign m_axil[n].wstrb   = axil_wstrb_reg;
    assign m_axil[n].wvalid  = m_axil_wvalid_reg[n];
    assign m_axil[n].bready  = m_axil_bready_reg[n];
    assign m_axil[n].araddr  = axil_addr_reg;
    assign m_axil[n].arprot  = axil_prot_reg;
    assign m_axil[n].arvalid = m_axil_arvalid_reg[n];
    assign m_axil[n].rready  = m_axil_rready_reg[n];

    assign m_axil_awready[n] = m_axil[n].awready;
    assign m_axil_wready[n]  = m_axil[n].wready;
    assign m_axil_bresp[n]   = m_axil[n].bresp;
    assign m_axil_bvalid[n]  = m_axil[n].bvalid;
    assign m_axil_arready[n] = m_axil[n].arready;
    assign m_axil_rdata[n]   = m_axil[n].rdata;
    assign m_axil_rresp[n]   = m_axil[n].rresp;
    assign m_axil_rvalid[n]  = m_axil[n].rvalid;
end

// slave side mux
logic [S_SEL_W-1:0] s_select;

logic [ADDR_WIDTH-1:0] current_s_axil_awaddr;
logic [2:0]            current_s_axil_awprot;
logic [DATA_WIDTH-1:0] current_s_axil_wdata;
logic [STRB_WIDTH-1:0] current_s_axil_wstrb;
logic                  current_s_axil_wvalid;
logic                  current_s_axil_wready;
logic [ADDR_WIDTH-1:0] current_s_axil_araddr;
logic [2:0]            current_s_axil_arprot;

assign current_s_axil_awaddr = s_axil_awaddr[s_select];
assign current_s_axil_awprot = s_axil_awprot[s_select];
assign current_s_axil_wdata  = s_axil_wdata[s_select];
assign current_s_axil_wstrb  = s_axil_wstrb[s_select];
assign current_s_axil_wvalid = s_axil_wvalid[s_select];
assign current_s_axil_wready = s_axil_wready_reg[s_select];
assign current_s_axil_araddr = s_axil_araddr[s_select];
assign current_s_axil_arprot = s_axil_arprot[s_select];

// master side mux
logic [1:0]            current_m_axil_bresp;
logic                  current_m_axil_bvalid;
logic                  current_m_axil_bready;
logic [DATA_WIDTH-1:0] current_m_axil_rdata;
logic [1:0]            current_m_axil_rresp;
logic                  current_m_axil_rvalid;
logic                  current_m_axil_rready;

assign current_m_axil_bresp  = m_axil_bresp[m_select_reg];
assign current_m_axil_bvalid = m_axil_bvalid[m_select_reg];
assign current_m_axil_bready = m_axil_bready_reg[m_select_reg];
assign current_m_axil_rdata  = m_axil_rdata[m_select_reg];
assign current_m_axil_rresp  = m_axil_rresp[m_select_reg];
assign current_m_axil_rvalid = m_axil_rvalid[m_select_reg];
assign current_m_axil_rready = m_axil_rready_reg[m_select_reg];

// arbiter instance
logic [S_COUNT*2-1:0] request;
logic [S_COUNT*2-1:0] acknowledge;
logic [S_COUNT*2-1:0] grant;
logic                 grant_valid;
logic [CL_S_COUNT:0]  grant_encoded;

// grant_encoded = {slave index, read}
logic                  read;

assign read = grant_encoded[0];

if (S_COUNT > 1) begin : g_s_select
    assign s_select = grant_encoded[CL_S_COUNT:1];
end else begin : g_s_select_one
    assign s_select = 1'b0;
end

arbiter #(
    .PORTS(S_COUNT*2),
    .ARB_TYPE_ROUND_ROBIN(1),
    .ARB_BLOCK(1),
    .ARB_BLOCK_ACK(1),
    .ARB_LSB_HIGH_PRIORITY(1)
) arb_inst (
    .clk(clk),
    .rst(rst),
    .request(request),
    .acknowledge(acknowledge),
    .grant(grant),
    .grant_valid(grant_valid),
    .grant_encoded(grant_encoded)
);

// request and acknowledge generation
for (genvar n = 0; n < S_COUNT; n++) begin : g_req
    assign request[2*n]   = s_axil_awvalid[n];
    assign request[2*n+1] = s_axil_arvalid[n];

    assign acknowledge[2*n]   = grant[2*n]   && s_axil_bvalid_reg[n] && s_axil_bready[n];
    assign acknowledge[2*n+1] = grant[2*n+1] && s_axil_rvalid_reg[n] && s_axil_rready[n];
end

always_comb begin
    logic match;

    state_next = STATE_IDLE;

    match = 1'b0;

    m_select_next = m_select_reg;
    axil_addr_next = axil_addr_reg;
    axil_addr_valid_next = axil_addr_valid_reg;
    axil_prot_next = axil_prot_reg;
    axil_data_next = axil_data_reg;
    axil_wstrb_next = axil_wstrb_reg;
    axil_resp_next = axil_resp_reg;

    s_axil_awready_next = '0;
    s_axil_wready_next = '0;
    s_axil_bvalid_next = s_axil_bvalid_reg & ~s_axil_bready;
    s_axil_arready_next = '0;
    s_axil_rvalid_next = s_axil_rvalid_reg & ~s_axil_rready;

    m_axil_awvalid_next = m_axil_awvalid_reg & ~m_axil_awready;
    m_axil_wvalid_next = m_axil_wvalid_reg & ~m_axil_wready;
    m_axil_bready_next = '0;
    m_axil_arvalid_next = m_axil_arvalid_reg & ~m_axil_arready;
    m_axil_rready_next = '0;

    case (state_reg)
        STATE_IDLE: begin
            // idle state; wait for arbitration

            if (grant_valid) begin

                axil_addr_valid_next = 1'b1;

                if (read) begin
                    // reading
                    axil_addr_next = current_s_axil_araddr;
                    axil_prot_next = current_s_axil_arprot;
                    s_axil_arready_next[s_select] = 1'b1;
                end else  begin
                    // writing
                    axil_addr_next = current_s_axil_awaddr;
                    axil_prot_next = current_s_axil_awprot;
                    s_axil_awready_next[s_select] = 1'b1;
                end

                state_next = STATE_DECODE;
            end else begin
                state_next = STATE_IDLE;
            end
        end
        STATE_DECODE: begin
            // decode state; determine master interface

            // region enabled, secure check, connection allowed, address hit
            for (int mi = 0; mi < M_COUNT; mi++) begin
                for (int ri = 0; ri < M_REGIONS; ri++) begin
                    if (M_ADDR_WIDTH[mi][ri] != 0
                            && (!M_SECURE[mi] || !axil_prot_reg[1])
                            && (read ? M_CONNECT_READ[mi][s_select] : M_CONNECT_WRITE[mi][s_select])
                            && (axil_addr_reg & ~M_MASK_INT[mi][ri]) == (M_BASE_ADDR_INT[mi][ri] & ~M_MASK_INT[mi][ri])) begin
                        m_select_next = M_SEL_W'(unsigned'(mi));
                        match = 1'b1;
                    end
                end
            end

            if (match) begin
                if (read) begin
                    // reading
                    m_axil_rready_next[m_select_next] = 1'b1;
                    state_next = STATE_READ;
                end else begin
                    // writing
                    s_axil_wready_next[s_select] = 1'b1;
                    state_next = STATE_WRITE;
                end
            end else begin
                // no match; return decode error
                axil_data_next = '0;
                axil_resp_next = 2'b11;
                if (read) begin
                    // reading
                    s_axil_rvalid_next[s_select] = 1'b1;
                    state_next = STATE_WAIT_IDLE;
                end else begin
                    // writing
                    s_axil_wready_next[s_select] = 1'b1;
                    state_next = STATE_WRITE_DROP;
                end
            end
        end
        STATE_WRITE: begin
            // write state; store and forward write data
            s_axil_wready_next[s_select] = 1'b1;

            if (axil_addr_valid_reg) begin
                m_axil_awvalid_next[m_select_reg] = 1'b1;
            end
            axil_addr_valid_next = 1'b0;

            if (current_s_axil_wready && current_s_axil_wvalid) begin
                s_axil_wready_next[s_select] = 1'b0;
                axil_data_next = current_s_axil_wdata;
                axil_wstrb_next = current_s_axil_wstrb;
                m_axil_wvalid_next[m_select_reg] = 1'b1;
                m_axil_bready_next[m_select_reg] = 1'b1;
                state_next = STATE_WRITE_RESP;
            end else begin
                state_next = STATE_WRITE;
            end
        end
        STATE_WRITE_RESP: begin
            // write response state; store and forward write response
            m_axil_bready_next[m_select_reg] = 1'b1;

            if (current_m_axil_bready && current_m_axil_bvalid) begin
                m_axil_bready_next[m_select_reg] = 1'b0;
                axil_resp_next = current_m_axil_bresp;
                s_axil_bvalid_next[s_select] = 1'b1;
                state_next = STATE_WAIT_IDLE;
            end else begin
                state_next = STATE_WRITE_RESP;
            end
        end
        STATE_WRITE_DROP: begin
            // write drop state; drop write data
            s_axil_wready_next[s_select] = 1'b1;

            axil_addr_valid_next = 1'b0;

            if (current_s_axil_wready && current_s_axil_wvalid) begin
                s_axil_wready_next[s_select] = 1'b0;
                s_axil_bvalid_next[s_select] = 1'b1;
                state_next = STATE_WAIT_IDLE;
            end else begin
                state_next = STATE_WRITE_DROP;
            end
        end
        STATE_READ: begin
            // read state; store and forward read response
            m_axil_rready_next[m_select_reg] = 1'b1;

            if (axil_addr_valid_reg) begin
                m_axil_arvalid_next[m_select_reg] = 1'b1;
            end
            axil_addr_valid_next = 1'b0;

            if (current_m_axil_rready && current_m_axil_rvalid) begin
                m_axil_rready_next[m_select_reg] = 1'b0;
                axil_data_next = current_m_axil_rdata;
                axil_resp_next = current_m_axil_rresp;
                s_axil_rvalid_next[s_select] = 1'b1;
                state_next = STATE_WAIT_IDLE;
            end else begin
                state_next = STATE_READ;
            end
        end
        STATE_WAIT_IDLE: begin
            // wait for idle state; wait until grant valid is deasserted

            if (!grant_valid || |acknowledge) begin
                state_next = STATE_IDLE;
            end else begin
                state_next = STATE_WAIT_IDLE;
            end
        end
        default: begin
            state_next = STATE_IDLE;
        end
    endcase
end

always_ff @(posedge clk) begin
    if (rst) begin
        state_reg <= STATE_IDLE;

        axil_addr_valid_reg <= 1'b0;

        s_axil_awready_reg <= '0;
        s_axil_wready_reg <= '0;
        s_axil_bvalid_reg <= '0;
        s_axil_arready_reg <= '0;
        s_axil_rvalid_reg <= '0;

        m_axil_awvalid_reg <= '0;
        m_axil_wvalid_reg <= '0;
        m_axil_bready_reg <= '0;
        m_axil_arvalid_reg <= '0;
        m_axil_rready_reg <= '0;
    end else begin
        state_reg <= state_next;

        axil_addr_valid_reg <= axil_addr_valid_next;

        s_axil_awready_reg <= s_axil_awready_next;
        s_axil_wready_reg <= s_axil_wready_next;
        s_axil_bvalid_reg <= s_axil_bvalid_next;
        s_axil_arready_reg <= s_axil_arready_next;
        s_axil_rvalid_reg <= s_axil_rvalid_next;

        m_axil_awvalid_reg <= m_axil_awvalid_next;
        m_axil_wvalid_reg <= m_axil_wvalid_next;
        m_axil_bready_reg <= m_axil_bready_next;
        m_axil_arvalid_reg <= m_axil_arvalid_next;
        m_axil_rready_reg <= m_axil_rready_next;
    end

    m_select_reg <= m_select_next;
    axil_addr_reg <= axil_addr_next;
    axil_prot_reg <= axil_prot_next;
    axil_data_reg <= axil_data_next;
    axil_wstrb_reg <= axil_wstrb_next;
    axil_resp_reg <= axil_resp_next;
end

endmodule

`resetall
