# Verilog and System Verilog AMBA Components Readme

[![Build Status](https://github.com/Gatherer/verilog-amba-lib/actions/workflows/regression-tests.yml/badge.svg?branch=main)](https://github.com/Gatherer/verilog-amba-lib/actions/workflows/regression-tests.yml)

The goal is to keeping the project with this license alive.
I will basically keep the .v version of the IP and add .sv variants with
over time on a need basis.


## Introduction

Collection of AXI4 and AXI4 lite bus components.  Most components are fully
parametrizable in interface widths.  Includes full cocotb testbenches that
utilize [cocotbext-axi](https://github.com/alexforencich/cocotbext-axi).

Original GitHub repository: https://github.com/alexforencich/verilog-axis and
GitHub repository: https://github.com/alexforencich/verilog-axi

This origianal repository is superseded by https://github.com/fpganinja/taxi.
All new features and bug fixes will be applied there, and commercial support is also available.
As a result, this repo is deprecated and will not receive any future maintenance or support.

## Documentation AXI

### `axi_adapter` module

AXI width adapter module with parametrizable data and address interface widths.
Supports INCR burst types and narrow bursts.  Wrapper for `axi_adapter_rd` and `axi_adapter_wr`.

### `axi_adapter_rd` module

AXI width adapter module with parametrizable data and address interface widths.
Supports INCR burst types and narrow bursts.

### `axi_adapter_wr` module

AXI width adapter module with parametrizable data and address interface widths.
Supports INCR burst types and narrow bursts.

### `axi_axil_adapter` module

AXI to AXI lite converter and width adapter module with parametrizable data
and address interface widths.  Supports INCR burst types and narrow bursts.
Wrapper for `axi_axil_adapter_rd` and `axi_axil_adapter_wr`.

### `axi_axil_adapter_rd` module

AXI to AXI lite converter and width adapter module with parametrizable data
and address interface widths.  Supports INCR burst types and narrow bursts.

### `axi_axil_adapter_wr` module

AXI to AXI lite converter and width adapter module with parametrizable data
and address interface widths.  Supports INCR burst types and narrow bursts.

### `axi_cdma` module

AXI to AXI DMA engine with parametrizable data and address interface widths.
Generates full-width INCR bursts only, with parametrizable maximum burst
length.  Supports unaligned transfers, which can be disabled via parameter
to save on resource consumption.

### `axi_cdma_desc_mux` module

Descriptor multiplexer/demultiplexer for AXI CDMA module.  Enables sharing the
AXI CDMA module between multiple request sources, interleaving requests and
distributing responses.

### `axi_crossbar` module

AXI nonblocking crossbar interconnect with parametrizable data and address
interface widths and master and slave interface counts.  Supports all burst
types.  Fully nonblocking with completely separate read and write paths;
ID-based transaction ordering protection logic; and per-port address decode,
admission control, and decode error handling.  Wrapper for `axi_crossbar_rd`
and `axi_crossbar_wr`.

Wrappers can generated with `axi_crossbar_wrap.py`.

### `axi_crossbar_addr` module

Address decode and admission control module for AXI nonblocking crossbar interconnect.

### `axi_crossbar_rd` module

AXI nonblocking crossbar interconnect with parametrizable data and address
interface widths and master and slave interface counts.  Read interface only.
Supports all burst types.  Fully nonblocking with completely separate read and
write paths; ID-based transaction ordering protection logic; and per-port
address decode, admission control, and decode error handling.

### `axi_crossbar_wr` module

AXI nonblocking crossbar interconnect with parametrizable data and address
interface widths and master and slave interface counts.  Write interface only.
Supports all burst types.  Fully nonblocking with completely separate read and
write paths; ID-based transaction ordering protection logic; and per-port
address decode, admission control, and decode error handling.

### `axi_dma` module

AXI to AXI stream DMA engine with parametrizable data and address interface
widths.  Generates full-width INCR bursts only, with parametrizable maximum
burst length.  Supports unaligned transfers, which can be disabled via
parameter to save on resource consumption.  Wrapper for `axi_dma_rd` and
`axi_dma_wr`.

### `axi_dma_desc_mux` module

Descriptor multiplexer/demultiplexer for AXI DMA module.  Enables sharing the
AXI DMA module between multiple request sources, interleaving requests and
distributing responses.

### `axi_dma_rd` module

AXI to AXI stream DMA engine with parametrizable data and address interface
widths.  Generates full-width INCR bursts only, with parametrizable maximum
burst length.  Supports unaligned transfers, which can be disabled via
parameter to save on resource consumption.

### `axi_dma_wr` module

AXI stream to AXI DMA engine with parametrizable data and address interface
widths.  Generates full-width INCR bursts only, with parametrizable maximum
burst length.  Supports unaligned transfers, which can be disabled via
parameter to save on resource consumption.

### `axi_dp_ram` module

AXI dual-port RAM with parametrizable data and address interface widths.
Supports FIXED and INCR burst types as well as narrow bursts.

### `axi_fifo` module

AXI FIFO with parametrizable data and address interface widths.  Supports all
burst types.  Optionally can delay the address channel until either the write
data is completely shifted into the FIFO or the read data FIFO has enough
capacity to fit the whole burst.  Wrapper for `axi_fifo_rd` and `axi_fifo_wr`.

### `axi_fifo_rd` module

AXI FIFO with parametrizable data and address interface widths.  AR and R
channels only.  Supports all burst types.  Optionally can delay the address
channel until either the read data FIFO is empty or has enough capacity to fit
the whole burst.

### `axi_fifo_wr` module

AXI FIFO with parametrizable data and address interface widths.  WR, W, and B
channels only.  Supports all burst types.  Optionally can delay the address
channel until the write data is shifted completely into the write data FIFO,
or the current burst completely fills the write data FIFO.

### `axi_interconnect` module

AXI shared interconnect with parametrizable data and address interface
widths and master and slave interface counts.  Supports all burst types.
Small in area, but does not support concurrent operations.

Wrappers can generated with `axi_interconnect_wrap.py`.

### `axi_ram` module

AXI RAM with parametrizable data and address interface widths.  Supports FIXED
and INCR burst types as well as narrow bursts.

### `axi_ram_rd_if` module

AXI RAM read interface with parametrizable data and address interface widths.
Handles bursts and presents a simplified internal memory interface.  Supports
FIXED and INCR burst types as well as narrow bursts.

### `axi_ram_wr_if` module

AXI RAM write interface with parametrizable data and address interface widths.
Handles bursts and presents a simplified internal memory interface.  Supports
FIXED and INCR burst types as well as narrow bursts.

### `axi_ram_wr_rd_if` module

AXI RAM read/write interface with parametrizable data and address interface
widths.  Handles bursts and presents a simplified internal memory interface.
Supports FIXED and INCR burst types as well as narrow bursts.  Wrapper for
`axi_ram_rd_if` and `axi_ram_wr_if`.

### `axi_register` module

AXI register with parametrizable data and address interface widths.  Supports
all burst types.  Inserts simple buffers or skid buffers into all channels.
Channel register types can be individually changed or bypassed.  Wrapper for
`axi_register_rd` and `axi_register_wr`.

### `axi_register_rd` module

AXI register with parametrizable data and address interface widths.  AR and R
channels only.  Supports all burst types.  Inserts simple buffers or skid
buffers into all channels.  Channel register types can be individually changed
or bypassed.

### `axi_register_wr` module

AXI register with parametrizable data and address interface widths.  WR, W,
and B channels only.  Supports all burst types.  Inserts simple buffers or
skid buffers into all channels.  Channel register types can be individually
changed or bypassed.

### `axil_adapter` module

AXI lite width adapter module with parametrizable data and address interface
widths.  Wrapper for `axi_adapter_rd` and `axi_adapter_wr`.

### `axil_adapter_rd` module

AXI lite width adapter module with parametrizable data and address interface
widths.

### `axil_adapter_wr` module

AXI lite width adapter module with parametrizable data and address interface
widths.

### `axil_cdc` module

AXI lite clock domain crossing module with parametrizable data and address
interface widths.  Wrapper for `axi_cdc_rd` and `axi_cdc_wr`.

### `axil_cdc_rd` module

AXI lite clock domain crossing module with parametrizable data and address
interface widths.

### `axil_cdc_wr` module

AXI lite clock domain crossing module with parametrizable data and address
interface widths.

### `axil_crossbar` module

AXI lite nonblocking crossbar interconnect with parametrizable data and address
interface widths and master and slave interface counts.  Fully nonblocking
with completely separate read and write paths; FIFO-based transaction ordering
protection logic; and per-port address decode, admission control, and decode
error handling.  Wrapper for `axil_crossbar_rd` and `axil_crossbar_wr`.

Wrappers can generated with `axil_crossbar_wrap.py`.

### `axil_crossbar_addr` module

Address decode and admission control module for AXI lite nonblocking crossbar interconnect.

### `axil_crossbar_rd` module

AXI lite nonblocking crossbar interconnect with parametrizable data and address
interface widths and master and slave interface counts.  Read interface only.
Fully nonblocking with completely separate read and write paths; FIFO-based
transaction ordering protection logic; and per-port address decode, admission
control, and decode error handling.

### `axil_crossbar_wr` module

AXI lite nonblocking crossbar interconnect with parametrizable data and address
interface widths and master and slave interface counts.  Write interface only.
Fully nonblocking with completely separate read and write paths; FIFO-based
transaction ordering protection logic; and per-port address decode, admission
control, and decode error handling.

### `axil_interconnect` module

AXI lite shared interconnect with parametrizable data and address interface
widths and master and slave interface counts.  Small in area, but does not
support concurrent operations.

Wrappers can generated with `axil_interconnect_wrap.py`.

### `axil_ram` module

AXI lite RAM with parametrizable data and address interface widths.

### `axil_reg_if` module

AXI lite register interface with parametrizable data and address interface
widths.  Can be used to assemble a set of control registers across multiple
modules and hierarchy levels without complicated arbitration logic.  Wrapper
for `axil_reg_if_rd` and `axil_reg_if_wr`.

### `axil_reg_if_rd` module

AXI lite register interface with parametrizable data and address interface
widths.  Read direction only.  Can be used to assemble a set of control
registers across multiple modules and hierarchy levels without complicated
arbitration logic.

### `axil_reg_if_wr` module

AXI lite register interface with parametrizable data and address interface
widths.  Write direction only.  Can be used to assemble a set of control
registers across multiple modules and hierarchy levels without complicated
arbitration logic.

### `axil_register` module

AXI lite register with parametrizable data and address interface widths.
Inserts skid buffers into all channels.  Channel registers can be individually
bypassed.  Wrapper for `axil_register_rd` and `axil_register_wr`.

### `axil_register_rd` module

AXI lite register with parametrizable data and address interface widths.  AR
and R channels only.  Inserts simple buffers into all channels.  Channel
registers can be individually bypassed.

### `axil_register_wr` module

AXI lite register with parametrizable data and address interface widths.  WR,
W, and B channels only.  Inserts simple buffers into all channels.  Channel
registers can be individually bypassed.

### Common signals

    awid     : Write address ID
    awaddr   : Write address
    awlen    : Write burst length
    awsize   : Write burst size
    awburst  : Write burst type
    awlock   : Write locking
    awcache  : Write cache handling
    awprot   : Write protection level
    awqos    : Write QoS setting
    awregion : Write region
    awuser   : Write user sideband signal
    awvalid  : Write address valid
    awready  : Write address ready (from slave)
    wdata    : Write data
    wstrb    : Write data strobe (byte select)
    wlast    : Write data last transfer in burst
    wuser    : Write data user sideband signal
    wvalid   : Write data valid
    wready   : Write data ready (from slave)
    bid      : Write response ID
    bresp    : Write response
    buser    : Write response user sideband signal
    bvalid   : Write response valid
    bready   : Write response ready (from master)
    arid     : Read address ID
    araddr   : Read address
    arlen    : Read burst length
    arsize   : Read burst size
    arburst  : Read burst type
    arlock   : Read locking
    arcache  : Read cache handling
    arprot   : Read protection level
    arqos    : Read QoS setting
    arregion : Read region
    aruser   : Read user sideband signal
    arvalid  : Read address valid
    arready  : Read address ready (from slave)
    rid      : Read data ID
    rdata    : Read data
    rresp    : Read response
    rlast    : Read data last transfer in burst
    ruser    : Read data user sideband signal
    rvalid   : Read response valid
    rready   : Read response ready (from master)

### Common parameters

    ADDR_WIDTH           : width of awaddr and araddr signals
    DATA_WIDTH           : width of wdata and rdata signals
    STRB_WIDTH           : width of wstrb signal
    ID_WIDTH             : width of *id signals
    AWUSER_ENABLE        : enable awuser signal
    AWUSER_WIDTH         : width of awuser signal
    WUSER_ENABLE         : enable wuser signal
    WUSER_WIDTH          : width of wuser signal
    BUSER_ENABLE         : enable buser signal
    BUSER_WIDTH          : width of buser signal
    ARUSER_ENABLE        : enable aruser signal
    ARUSER_WIDTH         : width of aruser signal
    RUSER_ENABLE         : enable ruser signal
    RUSER_WIDTH          : width of ruser signal

### Source Files

    rtl/common/v/arbiter.v              : Parametrizable arbiter
    rtl/axi/v/axi_adapter.v             : AXI lite width converter
    rtl/axi/v/axi_adapter_rd.v          : AXI lite width converter (read)
    rtl/axi/v/axi_adapter_wr.v          : AXI lite width converter (write)
    rtl/axi/v/axi_axil_adapter.v        : AXI to AXI lite converter
    rtl/axi/v/axi_axil_adapter_rd.v     : AXI to AXI lite converter (read)
    rtl/axi/v/axi_axil_adapter_wr.v     : AXI to AXI lite converter (write)
    rtl/axi/v/axi_cdma.v                : AXI central DMA engine
    rtl/axi/v/axi_cdma_desc_mux.v       : AXI CDMA descriptor mux
    rtl/axi/v/axi_crossbar.v            : AXI nonblocking crossbar interconnect
    rtl/axi/v/axi_crossbar_addr.v       : AXI crossbar address module
    rtl/axi/v/axi_crossbar_rd.v         : AXI crossbar interconnect (read)
    rtl/axi/v/axi_crossbar_wr.v         : AXI crossbar interconnect (write)
    rtl/axi/v/axi_dma.v                 : AXI DMA engine
    rtl/axi/v/axi_dma_desc_mux.v        : AXI DMA descriptor mux
    rtl/axi/v/axi_dma_rd.v              : AXI DMA engine (read)
    rtl/axi/v/axi_dma_wr.v              : AXI DMA engine (write)
    rtl/axi/v/axi_dp_ram.v              : AXI dual-port RAM
    rtl/axi/v/axi_fifo.v                : AXI FIFO
    rtl/axi/v/axi_fifo_rd.v             : AXI FIFO (read)
    rtl/axi/v/axi_fifo_wr.v             : AXI FIFO (write)
    rtl/axi/v/axi_interconnect.v        : AXI shared interconnect
    rtl/axi/v/axi_ram.v                 : AXI RAM
    rtl/axi/v/axi_ram_rd_if.v           : AXI RAM read interface
    rtl/axi/v/axi_ram_wr_if.v           : AXI RAM write interface
    rtl/axi/v/axi_ram_wr_rd_if.v        : AXI RAM read/write interface
    rtl/axi/v/axi_register.v            : AXI register
    rtl/axi/v/axi_register_rd.v         : AXI register (read)
    rtl/axi/v/axi_register_wr.v         : AXI register (write)
    rtl/axi/v/axil_adapter.v            : AXI lite width converter
    rtl/axi/v/axil_adapter_rd.v         : AXI lite width converter (read)
    rtl/axi/v/axil_adapter_wr.v         : AXI lite width converter (write)
    rtl/axi/v/axil_cdc.v                : AXI lite CDC
    rtl/axi/v/axil_cdc_rd.v             : AXI lite CDC (read)
    rtl/axi/v/axil_cdc_wr.v             : AXI lite CDC (write)
    rtl/axi/v/axil_crossbar.v           : AXI lite nonblocking crossbar interconnect
    rtl/axi/v/axil_crossbar_addr.v      : AXI lite crossbar address module
    rtl/axi/v/axil_crossbar_rd.v        : AXI lite crossbar interconnect (read)
    rtl/axi/v/axil_crossbar_wr.v        : AXI lite crossbar interconnect (write)
    rtl/axi/v/axil_interconnect.v       : AXI lite shared interconnect
    rtl/axi/v/axil_ram.v                : AXI lite RAM
    rtl/axi/v/axil_reg_if.v             : AXI lite register interface
    rtl/axi/v/axil_reg_if_rd.v          : AXI lite register interface (read)
    rtl/axi/v/axil_reg_if_wr.v          : AXI lite register interface (write)
    rtl/axi/v/axil_register.v           : AXI lite register
    rtl/axi/v/axil_register_rd.v        : AXI lite register (read)
    rtl/axi/v/axil_register_wr.v        : AXI lite register (write)
    rtl/common/v/priority_encoder.v     : Parametrizable priority encoder

### AXI4-Lite Interface Example

Write

                ___     ___     ___     ___     ___
    clk     ___/   \___/   \___/   \___/   \___/   \___
                _______
    awid    XXXX_ID____XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    awaddr  XXXX_ADDR__XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    awlen   XXXX_00____XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    awsize  XXXX_0_____XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    awburst XXXX_0_____XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    awprot  XXXX_PROT__XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    awvalid ___/       \_______________________________
            ___________         _______________________
    awready            \_______/
                _______________
    wdata   XXXX_DATA__________XXXXXXXXXXXXXXXXXXXXXXXX
                _______________
    wstrb   XXXX_STRB__________XXXXXXXXXXXXXXXXXXXXXXXX
                _______________
    wvalid  ___/               \_______________________
                        _______
    wready  ___________/       \_______________________
                                        _______
    bid     XXXXXXXXXXXXXXXXXXXXXXXXXXXX_ID____XXXXXXXX
                                        _______
    bresp   XXXXXXXXXXXXXXXXXXXXXXXXXXXX_RESP__XXXXXXXX
                                        _______
    bvalid  ___________________________/       \_______
            ___________________________________________
    bready


Read

                ___     ___     ___     ___     ___
    clk     ___/   \___/   \___/   \___/   \___/   \___
                _______
    arid    XXXX_ID____XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    araddr  XXXX_ADDR__XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    arlen   XXXX_00____XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    arsize  XXXX_0_____XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    arburst XXXX_0_____XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    arprot  XXXX_PROT__XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
                _______
    arvalid ___/       \_______________________________
            ___________________________________________
    arready
                                        _______
    rid     XXXXXXXXXXXXXXXXXXXXXXXXXXXX_ID____XXXXXXXX
                                        _______
    rdata   XXXXXXXXXXXXXXXXXXXXXXXXXXXX_DATA__XXXXXXXX
                                        _______
    rresp   XXXXXXXXXXXXXXXXXXXXXXXXXXXX_RESP__XXXXXXXX
                                        _______
    rvalid  ___________________________/       \_______
            ___________________________________________
    rready

## Documentation AXIS

### `arbiter` module

General-purpose parametrizable arbiter.  Supports priority and round-robin
arbitration.  Supports blocking until request release or acknowledge.

### `axis_adapter` module

The `axis_adapter` module bridges AXI stream buses of differing widths.  The
module is parametrizable, but there are certain restrictions.  First, the bus
word widths must be identical (e.g. one 8-bit lane and eight 8-bit lanes, but
not one 16-bit lane and one 32-bit lane).  Second, the bus widths must be
related by an integer multiple (e.g. 2 words and 6 words, but not 4 words
and 6 words).  Wait states will be inserted on the wider bus side when
necessary.

### `axis_arb_mux` module

Frame-aware AXI stream arbitrated multiplexer with parametrizable data width
and port count.  Supports priority and round-robin arbitration.

Wrappers can generated with `axis_arb_mux_wrap.py`.

### `axis_async_fifo` module

Configurable word-based or frame-based asynchronous FIFO with parametrizable
data width, depth, type, and bad frame detection.  Supports power of two
depths only.

### `axis_async_fifo_adapter` module

Configurable word-based or frame-based asynchronous FIFO with parametrizable
data width, depth, type, and bad frame detection.  Supports different input
and output data widths, inserting an axis_adapter instance appropriately.
Supports power of two depths only.

### `axis_broadcast` module

AXI stream broadcaster.  Duplicates one input stream across multiple output
streams.

### `axis_cobs_decode`

Consistent Overhead Byte Stuffing (COBS) decoder.  Fixed 8 bit width.

### `axis_cobs_encode`

Consistent Overhead Byte Stuffing (COBS) encoder.  Fixed 8 bit width.
Configurable zero insertion.

### `axis_crosspoint` module

Basic crosspoint switch.  `tready` signal not supported.  Parametrizable data
width.

Wrappers can generated with `axis_crosspoint_wrap.py`.

### `axis_demux` module

Frame-aware AXI stream demultiplexer with parametrizable data width and port
count.

### `axis_fifo` module

Configurable word-based or frame-based synchronous FIFO with parametrizable
data width, depth, type, and bad frame detection.  Supports power of two
depths only.

### `axis_fifo_adapter` module

Configurable word-based or frame-based synchronous FIFO with parametrizable
data width, depth, type, and bad frame detection.  Supports different input
and output data widths, inserting an axis_adapter instance appropriately.
Supports power of two depths only.

### `axis_frame_join` module

Frame joiner with optional tag and parametrizable port count.  8 bit data path
only.

Wrappers can generated with `axis_frame_join_wrap.py`.

### `axis_frame_length_adjust` module

Frame length adjuster module.  Truncates or pads frames as necessary to meet
the specified minimum and maximum length.  Reports the original and current
lengths as well as whether the packet was truncated or padded.  Length limits
are configurable at run time.

### `axis_frame_length_adjust_fifo` module

Frame length adjuster module with FIFO.  Truncates or pads frames as necessary
to meet the specified minimum and maximum length.  Reports the original and
current lengths as well as whether the packet was truncated or padded.  FIFOs
are used so that the status information can be read before the packet itself.
Length limits are configurable at run time.

### `axis_ll_bridge` module

AXI stream to LocalLink bridge.

### `axis_mux` module

Frame-aware AXI stream multiplexer with parametrizable data width and port
count.

Wrappers can generated with `axis_mux_wrap.py`.

### `axis_pipeline_fifo` module

Parametrizable register pipeline with output FIFO.  LENGTH parameter
determines number of register stages.  For a sufficient pipeline length and
bus width, consumes fewer resources than `axis_pipeline_register` while
providing full throughput.

### `axis_pipeline_register` module

Parametrizable register pipeline.  LENGTH parameter determines number of
register stages (instances of `axis_register`).

### `axis_ram_switch` module

Frame-aware AXI stream RAM switch with parametrizable data width, port count,
and FIFO size.  Uses block RAM for storing packets in transit, time-sharing
the RAM interface between ports.  Functionally equivalent to a combination of
per-port frame FIFOs and width converters connected to an AXI stream switch.

### `axis_rate_limit` module

Fractional rate limiter, supports word and frame modes.  Inserts wait states
to limit data rate to specified ratio.  Frame mode inserts wait states at end
of frames, word mode ignores frames and inserts wait states at any point.
Parametrizable data width.  Rate and mode are configurable at run time.

### `axis_register` module

Datapath register with parameter to select between skid buffer, simple buffer,
and bypass.  Use to improve timing for long routes.  Use `REG_TYPE` parameter
to select the type of register (bypass, simple, or skid buffer).

### `axis_srl_fifo` module

SRL-based FIFO.  Good for small FIFOs.  SRLs on Xilinx FPGAs have a very fast
input setup time, so this module can be used to aid in timing closure.

### `axis_srl_register` module

SRL-based register.  SRLs on Xilinx FPGAs have a very fast input setup time,
so this module can be used to aid in timing closure.

### `axis_stat_counter` module

Statistics counter module.  Counts bytes and frames passing through monitored
AXI stream interface.  Trigger signal used to reset and dump counts out of AXI
interface, along with tag value.  Use with `axis_frame_join` to form a single
monolithic frame from multiple monitored points with the same trigger.

### `axis_switch` module

Frame-aware AXI stream switch with parametrizable data width and port count.

Wrappers can generated with `axis_switch_wrap.py`.

### `axis_tap` module

AXI stream tap module.  Used to make a copy of an AXI stream bus without
affecting the bus.  Back-pressure on the output results in truncated frames
with `tuser` set.

### `ll_axis_bridge` module

LocalLink to AXI stream bridge.

### `priority_encoder` module

Parametrizable priority encoder.

### Common signals

    tdata   : Data (width generally DATA_WIDTH)
    tkeep   : Data word valid (width generally KEEP_WIDTH)
    tvalid  : Data valid
    tready  : Sink ready
    tlast   : End-of-frame
    tid     : Identifier tag (width generally ID_WIDTH)
    tdest   : Destination tag (width generally DEST_WIDTH)
    tuser   : User sideband signals (width generally USER_WIDTH)

### Common parameters

    DATA_WIDTH           : width of tdata signal
    KEEP_ENABLE          : enable tkeep signal (default DATA_WIDTH>8)
    KEEP_WIDTH           : width of tkeep signal (default (DATA_WIDTH+7)/8)
    LAST_ENABLE          : enable tlast signal
    ID_ENABLE            : enable tid signal
    ID_WIDTH             : width of tid signal
    DEST_ENABLE          : enable tdest signal
    DEST_WIDTH           : width of tdest signal
    USER_ENABLE          : enable tuser signal
    USER_WIDTH           : width of tuser signal
    USER_BAD_FRAME_VALUE : value of tuser indicating bad frame
    USER_BAD_FRAME_MASK  : bitmask for tuser bad frame indication

### Source Files

    rtl/common/v/arbiter.v                     : General-purpose parametrizable arbiter
    rtl/axis/v/axis_adapter.v                  : Parametrizable bus width adapter
    rtl/axis/v/axis_arb_mux.v                  : Parametrizable arbitrated multiplexer
    rtl/axis/v/axis_async_fifo.v               : Parametrizable asynchronous FIFO
    rtl/axis/v/axis_async_fifo_adapter.v       : FIFO/width adapter wrapper
    rtl/axis/v/axis_broadcast.v                : AXI stream broadcaster
    rtl/axis/v/axis_cobs_decode.v              : COBS decoder
    rtl/axis/v/axis_cobs_encode.v              : COBS encoder
    rtl/axis/v/axis_crosspoint.v               : Parametrizable crosspoint switch
    rtl/axis/v/axis_demux.v                    : Parametrizable demultiplexer
    rtl/axis/v/axis_fifo.v                     : Parametrizable synchronous FIFO
    rtl/axis/v/axis_fifo_adapter.v             : FIFO/width adapter wrapper
    rtl/axis/v/axis_frame_join.v               : Parametrizable frame joiner
    rtl/axis/v/axis_frame_length_adjust.v      : Frame length adjuster
    rtl/axis/v/axis_frame_length_adjust_fifo.v : Frame length adjuster with FIFO
    rtl/axis/v/axis_ll_bridge.v                : AXI stream to LocalLink bridge
    rtl/axis/v/axis_mux.v                      : Multiplexer generator
    rtl/axis/v/axis_pipeline_fifo.v            : AXI stream register pipeline with FIFO
    rtl/axis/v/axis_pipeline_register.v        : AXI stream register pipeline
    rtl/axis/v/axis_ram_switch.v               : AXI stream RAM switch
    rtl/axis/v/axis_rate_limit.v               : Fractional rate limiter
    rtl/axis/v/axis_register.v                 : AXI Stream register
    rtl/axis/v/axis_srl_fifo.v                 : SRL-based FIFO
    rtl/axis/v/axis_srl_register.v             : SRL-based register
    rtl/axis/v/axis_switch.v                   : Parametrizable AXI stream switch
    rtl/axis/v/axis_stat_counter.v             : Statistics counter
    rtl/axis/v/axis_tap.v                      : AXI stream tap
    rtl/axis/v/ll_axis_bridge.v                : LocalLink to AXI stream bridge
    rtl/common/v/priority_encoder.v            : Parametrizable priority encoder

### AXI Stream Interface Example

two byte transfer with sink pause after each byte

              __    __    __    __    __    __    __    __    __
    clk    __/  \__/  \__/  \__/  \__/  \__/  \__/  \__/  \__/  \__
                    _____ _________________
    tdata  XXXXXXXXX_D0__X_D1______________XXXXXXXXXXXXXXXXXXXXXXXX
                    _____ _________________
    tkeep  XXXXXXXXX_K0__X_K1______________XXXXXXXXXXXXXXXXXXXXXXXX
                    _______________________
    tvalid ________/                       \_______________________
           ______________             _____             ___________
    tready               \___________/     \___________/
                          _________________
    tlast  ______________/                 \_______________________

    tuser  ________________________________________________________


two back-to-back packets, no pauses

              __    __    __    __    __    __    __    __    __
    clk    __/  \__/  \__/  \__/  \__/  \__/  \__/  \__/  \__/  \__
                    _____ _____ _____ _____ _____ _____
    tdata  XXXXXXXXX_A0__X_A1__X_A2__X_B0__X_B1__X_B2__XXXXXXXXXXXX
                    _____ _____ _____ _____ _____ _____
    tkeep  XXXXXXXXX_K0__X_K1__X_K2__X_K0__X_K1__X_K2__XXXXXXXXXXXX
                    ___________________________________
    tvalid ________/                                   \___________
           ________________________________________________________
    tready
                                _____             _____
    tlast  ____________________/     \___________/     \___________

    tuser  ________________________________________________________


bad frame

              __    __    __    __    __    __
    clk    __/  \__/  \__/  \__/  \__/  \__/  \__
                    _____ _____ _____
    tdata  XXXXXXXXX_A0__X_A1__X_A2__XXXXXXXXXXXX
                    _____ _____ _____
    tkeep  XXXXXXXXX_K0__X_K1__X_K2__XXXXXXXXXXXX
                    _________________
    tvalid ________/                 \___________
           ______________________________________
    tready
                                _____
    tlast  ____________________/     \___________
                                _____
    tuser  ____________________/     \___________

## Testing

Running the included testbenches requires [Verilator](https://www.veripool.org/verilator/) in `PATH`.  Python dependencies ([cocotb](https://github.com/cocotb/cocotb), [cocotbext-axi](https://github.com/alexforencich/cocotbext-axi), pytest) are pinned in `tox.ini` and installed into `.venv` by the top-level Makefile.

    make                                      # create venv and run all tests
    make test TESTS=tb/axi_ram ARGS="-k 32"   # single testbench, filtered
    make test JOBS=auto                       # parallel regression
    make clean                                # remove simulation outputs

Alternatively run pytest via tox, or the cocotb makefile in `tb/<module>/`.
