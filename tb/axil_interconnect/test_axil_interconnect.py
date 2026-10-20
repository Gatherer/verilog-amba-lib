"""

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

"""

import itertools
import logging
import os
import random
import subprocess
import sys

import pytest

import cocotb
from cocotb.clock import Clock
from cocotb.handle import Immediate
from cocotb.triggers import RisingEdge, Timer
from cocotb_tools.runner import get_runner

from cocotbext.axi import AxiLiteBus, AxiLiteMaster, AxiLiteRam, AxiProt, AxiResp


def port_count(dut, prefix):
    # count wrapper ports, works for v and sv variant
    n = 0
    while hasattr(dut, f"{prefix}{n:02d}_axil_awvalid"):
        n += 1
    return n


class TB:
    def __init__(self, dut):
        self.dut = dut

        s_count = port_count(dut, "s")
        m_count = port_count(dut, "m")

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

        self.axil_master = [
            AxiLiteMaster(AxiLiteBus.from_prefix(dut, f"s{k:02d}_axil"), dut.clk, dut.rst) for k in range(s_count)
        ]
        self.axil_ram = [
            AxiLiteRam(AxiLiteBus.from_prefix(dut, f"m{k:02d}_axil"), dut.clk, dut.rst, size=2**16)
            for k in range(m_count)
        ]

    def set_idle_generator(self, generator=None):
        if generator:
            for master in self.axil_master:
                master.write_if.aw_channel.set_pause_generator(generator())
                master.write_if.w_channel.set_pause_generator(generator())
                master.read_if.ar_channel.set_pause_generator(generator())
            for ram in self.axil_ram:
                ram.write_if.b_channel.set_pause_generator(generator())
                ram.read_if.r_channel.set_pause_generator(generator())

    def set_backpressure_generator(self, generator=None):
        if generator:
            for master in self.axil_master:
                master.write_if.b_channel.set_pause_generator(generator())
                master.read_if.r_channel.set_pause_generator(generator())
            for ram in self.axil_ram:
                ram.write_if.aw_channel.set_pause_generator(generator())
                ram.write_if.w_channel.set_pause_generator(generator())
                ram.read_if.ar_channel.set_pause_generator(generator())

    async def cycle_reset(self):
        self.dut.rst.value = Immediate(0)
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)
        self.dut.rst.value = 1
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)
        self.dut.rst.value = 0
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)


async def run_test_write(dut, data_in=None, idle_inserter=None, backpressure_inserter=None, s=0, m=0):

    tb = TB(dut)

    byte_lanes = tb.axil_master[s].write_if.byte_lanes

    await tb.cycle_reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    for length in range(1, byte_lanes * 2):
        for offset in range(byte_lanes):
            tb.log.info("length %d, offset %d", length, offset)
            ram_addr = offset + 0x1000
            addr = ram_addr + m * 0x1000000
            test_data = bytearray([x % 256 for x in range(length)])

            tb.axil_ram[m].write(ram_addr - 128, b"\xaa" * (length + 256))

            resp = await tb.axil_master[s].write(addr, test_data)

            assert resp.resp == AxiResp.OKAY

            tb.log.debug(
                "%s", tb.axil_ram[m].hexdump_str((ram_addr & ~0xF) - 16, (((ram_addr & 0xF) + length - 1) & ~0xF) + 48)
            )

            assert tb.axil_ram[m].read(ram_addr, length) == test_data
            assert tb.axil_ram[m].read(ram_addr - 1, 1) == b"\xaa"
            assert tb.axil_ram[m].read(ram_addr + length, 1) == b"\xaa"

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_read(dut, data_in=None, idle_inserter=None, backpressure_inserter=None, s=0, m=0):

    tb = TB(dut)

    byte_lanes = tb.axil_master[s].write_if.byte_lanes

    await tb.cycle_reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    for length in range(1, byte_lanes * 2):
        for offset in range(byte_lanes):
            tb.log.info("length %d, offset %d", length, offset)
            ram_addr = offset + 0x1000
            addr = ram_addr + m * 0x1000000
            test_data = bytearray([x % 256 for x in range(length)])

            tb.axil_ram[m].write(ram_addr, test_data)

            data = await tb.axil_master[s].read(addr, length)

            assert data.data == test_data
            assert data.resp == AxiResp.OKAY

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_decode_error(dut, idle_inserter=None, backpressure_inserter=None, s=0):

    tb = TB(dut)

    byte_lanes = tb.axil_master[s].write_if.byte_lanes
    m_count = len(tb.axil_ram)

    await tb.cycle_reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    # first address behind the last master region
    bad_addr = m_count * 0x1000000

    for k in range(4):
        tb.log.info("decode error %d", k)

        test_data = bytearray([0x55] * byte_lanes)

        resp = await tb.axil_master[s].write(bad_addr + k * byte_lanes, test_data)
        assert resp.resp == AxiResp.DECERR

        data = await tb.axil_master[s].read(bad_addr + k * byte_lanes, byte_lanes)
        assert data.resp == AxiResp.DECERR
        assert data.data == bytearray(byte_lanes)

        # interconnect must recover for a valid access
        resp = await tb.axil_master[s].write(0x1000, test_data)
        assert resp.resp == AxiResp.OKAY
        data = await tb.axil_master[s].read(0x1000, byte_lanes)
        assert data.resp == AxiResp.OKAY
        assert data.data == test_data

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_prot(dut, s=0, m=0):

    tb = TB(dut)

    byte_lanes = tb.axil_master[s].write_if.byte_lanes

    await tb.cycle_reset()

    seen = {"aw": [], "ar": []}

    async def monitor(ch):
        valid = getattr(dut, f"m{m:02d}_axil_{ch}valid")
        ready = getattr(dut, f"m{m:02d}_axil_{ch}ready")
        prot = getattr(dut, f"m{m:02d}_axil_{ch}prot")
        while True:
            await RisingEdge(dut.clk)
            if valid.value and ready.value:
                seen[ch].append(int(prot.value))

    cocotb.start_soon(monitor("aw"))
    cocotb.start_soon(monitor("ar"))

    addr = 0x1000 + m * 0x1000000

    for prot in range(8):
        tb.log.info("prot %d", prot)
        await tb.axil_master[s].write(addr, bytearray(byte_lanes), prot=AxiProt(prot))
        await tb.axil_master[s].read(addr, byte_lanes, prot=AxiProt(prot))

    await RisingEdge(dut.clk)

    assert seen["aw"] == list(range(8))
    assert seen["ar"] == list(range(8))


async def run_stress_test(dut, idle_inserter=None, backpressure_inserter=None):

    tb = TB(dut)

    await tb.cycle_reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    async def worker(master, offset, aperture, count=16):
        for _ in range(count):
            m = random.randrange(len(tb.axil_ram))
            length = random.randint(1, min(32, aperture))
            addr = offset + random.randint(0, aperture - length) + m * 0x1000000
            test_data = bytearray([x % 256 for x in range(length)])

            await Timer(random.randint(1, 100), unit="ns")

            resp = await master.write(addr, test_data)
            assert resp.resp == AxiResp.OKAY

            await Timer(random.randint(1, 100), unit="ns")

            data = await master.read(addr, length)
            assert data.data == test_data
            assert data.resp == AxiResp.OKAY

    workers = []

    for k in range(16):
        workers.append(cocotb.start_soon(worker(tb.axil_master[k % len(tb.axil_master)], k * 0x1000, 0x1000, count=16)))

    while workers:
        await workers.pop(0)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_addr_width(dut):

    tb = TB(dut)

    m_count = len(tb.axil_ram)
    addr_width = int(os.environ["PARAM_ADDR_WIDTH"])
    if_addr_width = [int(os.environ.get(f"PARAM_M{k:02d}_IF_ADDR_WIDTH", addr_width)) for k in range(m_count)]

    # port widths
    for k in range(m_count):
        for ch in ["aw", "ar"]:
            assert len(getattr(dut, f"m{k:02d}_axil_{ch}addr")) == if_addr_width[k]

    # sv only: upper address bits are zero at the full width m_axil interfaces
    if not hasattr(dut, "m_axil"):
        return

    byte_lanes = tb.axil_master[0].write_if.byte_lanes

    await tb.cycle_reset()

    for m in range(m_count):
        addr = 0x1000 + m * 0x1000000

        await tb.axil_master[0].write(addr, bytearray(byte_lanes))
        for k in range(m_count):
            assert int(dut.m_axil[k].awaddr.value) == addr & (2 ** if_addr_width[k] - 1)

        await tb.axil_master[0].read(addr, byte_lanes)
        for k in range(m_count):
            assert int(dut.m_axil[k].araddr.value) == addr & (2 ** if_addr_width[k] - 1)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


def cycle_pause():
    return itertools.cycle([1, 1, 1, 0])


if getattr(cocotb, "SIM_NAME", None):
    s_count = port_count(cocotb.top, "s")
    m_count = port_count(cocotb.top, "m")

    test_params = cocotb.parametrize(
        ("idle_inserter", [None, cycle_pause]),
        ("backpressure_inserter", [None, cycle_pause]),
        ("s", range(min(s_count, 2))),
        ("m", range(min(m_count, 2))),
    )

    run_test_write = cocotb.test(test_params(run_test_write))
    run_test_read = cocotb.test(test_params(run_test_read))

    run_test_decode_error = cocotb.test(
        cocotb.parametrize(
            ("idle_inserter", [None, cycle_pause]),
            ("backpressure_inserter", [None, cycle_pause]),
            ("s", range(min(s_count, 2))),
        )(run_test_decode_error)
    )

    run_test_prot = cocotb.test(
        cocotb.parametrize(
            ("s", range(min(s_count, 2))),
            ("m", range(min(m_count, 2))),
        )(run_test_prot)
    )

    run_test_addr_width = cocotb.test(run_test_addr_width)

    # no pauses and full pauses only, keeps runtime low
    run_stress_test = cocotb.test(
        cocotb.parametrize(
            (("idle_inserter", "backpressure_inserter"), [(None, None), (cycle_pause, cycle_pause)]),
        )(run_stress_test)
    )


# cocotb runner

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, "..", "..", "rtl", "axil"))
common_dir = os.path.abspath(os.path.join(tests_dir, "..", "..", "rtl", "common"))
results_dir = os.path.abspath(os.path.join(tests_dir, "..", "results", os.path.basename(tests_dir)))

# simulation runs in results_dir, keep test module importable for cocotb
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)


# HDL variants: source file extension and verilator build args
hdl_variants = {
    "v": ["-Wno-SELRANGE", "-Wno-WIDTH", "-Wno-UNSIGNED", "-Wno-CASEINCOMPLETE", "-Wno-UNOPTFLAT", "-Wno-ASCRANGE"],
    "sv": [],
}


def build(request, hdl, s_count, m_count, data_width, extra_params=None):
    dut = "axil_interconnect"
    wrapper = f"{dut}_wrap_{s_count}x{m_count}"
    toplevel = wrapper

    # generate wrapper
    wrapper_file = os.path.join(results_dir, f"{wrapper}.{hdl}")
    if not os.path.exists(wrapper_file):
        os.makedirs(results_dir, exist_ok=True)
        subprocess.Popen(
            [sys.executable, os.path.join(rtl_dir, hdl, f"{dut}_wrap.py"), "-p", f"{s_count}", f"{m_count}"],
            cwd=results_dir,
        ).wait()

    verilog_sources = [wrapper_file]
    if hdl == "sv":
        verilog_sources.append(os.path.join(rtl_dir, "if", "axil_if.sv"))
    verilog_sources += [
        os.path.join(rtl_dir, hdl, f"{dut}.{hdl}"),
        os.path.join(common_dir, hdl, f"arbiter.{hdl}"),
        os.path.join(common_dir, hdl, f"priority_encoder.{hdl}"),
    ]

    parameters = {}

    parameters["DATA_WIDTH"] = data_width
    parameters["ADDR_WIDTH"] = 32
    # sv wrapper: STRB_WIDTH and M_REGIONS are localparams
    if hdl == "v":
        parameters["STRB_WIDTH"] = parameters["DATA_WIDTH"] // 8
        parameters["M_REGIONS"] = 1
    parameters.update(extra_params or {})

    sim_build = os.path.join(results_dir, request.node.name.replace("[", "-").replace("]", ""))

    runner = get_runner("verilator")

    runner.build(
        sources=verilog_sources,
        hdl_toplevel=toplevel,
        parameters=parameters,
        build_args=hdl_variants[hdl],
        build_dir=sim_build,
        timescale=("1ns", "1ps"),
    )

    return runner, toplevel, sim_build, parameters


def run(request, hdl, s_count, m_count, data_width, extra_params=None):
    module = os.path.splitext(os.path.basename(__file__))[0]

    runner, toplevel, sim_build, parameters = build(request, hdl, s_count, m_count, data_width, extra_params)

    extra_env = {f"PARAM_{k}": str(v) for k, v in parameters.items()}

    runner.test(
        test_module=module,
        hdl_toplevel=toplevel,
        build_dir=sim_build,
        test_dir=sim_build,
        results_xml=os.path.join(sim_build, "results.xml"),
        extra_env=extra_env,
    )


# sv only: master port address width per port, 16 bit regions at m*0x1000000
def narrow_params(if_addr_widths):
    params = {}
    for k, width in enumerate(if_addr_widths):
        params[f"M{k:02d}_BASE_ADDR"] = f"64'h{k * 0x1000000:x}"
        params[f"M{k:02d}_ADDR_WIDTH"] = 16
        params[f"M{k:02d}_IF_ADDR_WIDTH"] = width
    return params


@pytest.mark.parametrize("data_width", [8, 16, 32])
@pytest.mark.parametrize("m_count", [1, 4])
@pytest.mark.parametrize("s_count", [1, 4])
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_axil_interconnect(request, hdl, s_count, m_count, data_width):
    run(request, hdl, s_count, m_count, data_width)


@pytest.mark.parametrize("s_count", [1, 4])
def test_axil_interconnect_narrow(request, s_count):
    run(request, "sv", s_count, 4, 32, narrow_params([16, 20, 24, 32]))


def test_axil_interconnect_narrow_error(request):
    # region width 16 > port address width 12 must fail
    with pytest.raises(RuntimeError):
        build(request, "sv", 1, 4, 32, narrow_params([16, 12, 16, 16]))
