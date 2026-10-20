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

from cocotbext.axi import AxiBus, AxiMaster, AxiRam


class TB:
    def __init__(self, dut):
        self.dut = dut

        s_count = len(dut.axi_crossbar_inst.s_axi_awvalid)
        m_count = len(dut.axi_crossbar_inst.m_axi_awvalid)

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

        self.axi_master = [AxiMaster(AxiBus.from_prefix(dut, f"s{k:02d}_axi"), dut.clk, dut.rst) for k in range(s_count)]
        self.axi_ram = [AxiRam(AxiBus.from_prefix(dut, f"m{k:02d}_axi"), dut.clk, dut.rst, size=2**16) for k in range(m_count)]

        for ram in self.axi_ram:
            # prevent X propagation from screwing things up - "anything but X!"
            # (X on bid and rid can propagate X to ready/valid)
            ram.write_if.b_channel.bus.bid.value = Immediate(0)
            ram.read_if.r_channel.bus.rid.value = Immediate(0)

    def set_idle_generator(self, generator=None):
        if generator:
            for master in self.axi_master:
                master.write_if.aw_channel.set_pause_generator(generator())
                master.write_if.w_channel.set_pause_generator(generator())
                master.read_if.ar_channel.set_pause_generator(generator())
            for ram in self.axi_ram:
                ram.write_if.b_channel.set_pause_generator(generator())
                ram.read_if.r_channel.set_pause_generator(generator())

    def set_backpressure_generator(self, generator=None):
        if generator:
            for master in self.axi_master:
                master.write_if.b_channel.set_pause_generator(generator())
                master.read_if.r_channel.set_pause_generator(generator())
            for ram in self.axi_ram:
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


async def run_test_write(dut, data_in=None, idle_inserter=None, backpressure_inserter=None, size=None, s=0, m=0):

    tb = TB(dut)

    byte_lanes = tb.axi_master[s].write_if.byte_lanes
    max_burst_size = tb.axi_master[s].write_if.max_burst_size

    if size is None:
        size = max_burst_size

    await tb.cycle_reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    for length in list(range(1, byte_lanes*2))+[1024]:
        for offset in list(range(byte_lanes, byte_lanes*2))+list(range(4096-byte_lanes, 4096)):
            tb.log.info("length %d, offset %d, size %d", length, offset, size)
            ram_addr = offset+0x1000
            addr = ram_addr + m*0x1000000
            test_data = bytearray([x % 256 for x in range(length)])

            tb.axi_ram[m].write(ram_addr-128, b'\xaa'*(length+256))

            await tb.axi_master[s].write(addr, test_data, size=size)

            tb.log.debug("%s", tb.axi_ram[m].hexdump_str((ram_addr & ~0xf)-16, (((ram_addr & 0xf)+length-1) & ~0xf)+48))

            assert tb.axi_ram[m].read(ram_addr, length) == test_data
            assert tb.axi_ram[m].read(ram_addr-1, 1) == b'\xaa'
            assert tb.axi_ram[m].read(ram_addr+length, 1) == b'\xaa'

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_read(dut, data_in=None, idle_inserter=None, backpressure_inserter=None, size=None, s=0, m=0):

    tb = TB(dut)

    byte_lanes = tb.axi_master[s].write_if.byte_lanes
    max_burst_size = tb.axi_master[s].write_if.max_burst_size

    if size is None:
        size = max_burst_size

    await tb.cycle_reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    for length in list(range(1, byte_lanes*2))+[1024]:
        for offset in list(range(byte_lanes, byte_lanes*2))+list(range(4096-byte_lanes, 4096)):
            tb.log.info("length %d, offset %d, size %d", length, offset, size)
            ram_addr = offset+0x1000
            addr = ram_addr + m*0x1000000
            test_data = bytearray([x % 256 for x in range(length)])

            tb.axi_ram[m].write(ram_addr, test_data)

            data = await tb.axi_master[s].read(addr, length, size=size)

            assert data.data == test_data

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_stress_test(dut, idle_inserter=None, backpressure_inserter=None):

    tb = TB(dut)

    await tb.cycle_reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    async def worker(master, offset, aperture, count=16):
        for k in range(count):
            m = random.randrange(len(tb.axi_ram))
            length = random.randint(1, min(512, aperture))
            addr = offset+random.randint(0, aperture-length) + m*0x1000000
            test_data = bytearray([x % 256 for x in range(length)])

            await Timer(random.randint(1, 100), unit='ns')

            await master.write(addr, test_data)

            await Timer(random.randint(1, 100), unit='ns')

            data = await master.read(addr, length)
            assert data.data == test_data

    workers = []

    for k in range(16):
        workers.append(cocotb.start_soon(worker(tb.axi_master[k % len(tb.axi_master)], k*0x1000, 0x1000, count=16)))

    while workers:
        await workers.pop(0)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


def cycle_pause():
    return itertools.cycle([1, 1, 1, 0])


if getattr(cocotb, "SIM_NAME", None):

    s_count = len(cocotb.top.axi_crossbar_inst.s_axi_awvalid)
    m_count = len(cocotb.top.axi_crossbar_inst.m_axi_awvalid)

    data_width = len(cocotb.top.s00_axi_wdata)
    byte_lanes = data_width // 8
    max_burst_size = (byte_lanes-1).bit_length()

    test_params = cocotb.parametrize(
        ("idle_inserter", [None, cycle_pause]),
        ("backpressure_inserter", [None, cycle_pause]),
        # ("size", [None]+list(range(max_burst_size)))
        ("s", range(min(s_count, 2))),
        ("m", range(min(m_count, 2))),
    )

    run_test_write = cocotb.test(test_params(run_test_write))
    run_test_read = cocotb.test(test_params(run_test_read))

    run_stress_test = cocotb.test(run_stress_test)


# cocotb runner

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, '..', '..', 'rtl', 'axi', 'v'))
common_dir = os.path.abspath(os.path.join(tests_dir, '..', '..', 'rtl', 'common', 'v'))
results_dir = os.path.abspath(os.path.join(tests_dir, '..', 'results', os.path.basename(tests_dir)))

# simulation runs in results_dir, keep test module importable for cocotb
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)


@pytest.mark.parametrize("data_width", [8, 16, 32])
@pytest.mark.parametrize("m_count", [1, 4])
@pytest.mark.parametrize("s_count", [1, 4])
def test_axi_crossbar(request, s_count, m_count, data_width):
    dut = "axi_crossbar"
    wrapper = f"{dut}_wrap_{s_count}x{m_count}"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = wrapper

    # generate wrapper
    wrapper_file = os.path.join(results_dir, f"{wrapper}.v")
    if not os.path.exists(wrapper_file):
        os.makedirs(results_dir, exist_ok=True)
        subprocess.Popen(
            [sys.executable, os.path.join(rtl_dir, f"{dut}_wrap.py"), "-p", f"{s_count}", f"{m_count}"],
            cwd=results_dir
        ).wait()

    verilog_sources = [
        wrapper_file,
        os.path.join(rtl_dir, f"{dut}.v"),
        os.path.join(rtl_dir, f"{dut}_addr.v"),
        os.path.join(rtl_dir, f"{dut}_rd.v"),
        os.path.join(rtl_dir, f"{dut}_wr.v"),
        os.path.join(rtl_dir, "axi_register_rd.v"),
        os.path.join(rtl_dir, "axi_register_wr.v"),
        os.path.join(common_dir, "arbiter.v"),
        os.path.join(common_dir, "priority_encoder.v"),
    ]

    parameters = {}

    parameters['DATA_WIDTH'] = data_width
    parameters['ADDR_WIDTH'] = 32
    parameters['STRB_WIDTH'] = parameters['DATA_WIDTH'] // 8
    parameters['S_ID_WIDTH'] = 8
    parameters['M_ID_WIDTH'] = parameters['S_ID_WIDTH'] + (s_count-1).bit_length()
    parameters['AWUSER_ENABLE'] = 0
    parameters['AWUSER_WIDTH'] = 1
    parameters['WUSER_ENABLE'] = 0
    parameters['WUSER_WIDTH'] = 1
    parameters['BUSER_ENABLE'] = 0
    parameters['BUSER_WIDTH'] = 1
    parameters['ARUSER_ENABLE'] = 0
    parameters['ARUSER_WIDTH'] = 1
    parameters['RUSER_ENABLE'] = 0
    parameters['RUSER_WIDTH'] = 1
    parameters['M_REGIONS'] = 1

    extra_env = {f'PARAM_{k}': str(v) for k, v in parameters.items()}

    sim_build = os.path.join(results_dir,
        request.node.name.replace('[', '-').replace(']', ''))

    runner = get_runner("verilator")

    runner.build(
        sources=verilog_sources,
        hdl_toplevel=toplevel,
        parameters=parameters,
        build_args=["-Wno-SELRANGE", "-Wno-WIDTH", "-Wno-UNSIGNED", "-Wno-CASEINCOMPLETE", "-Wno-INITIALDLY", "-Wno-UNOPTFLAT", "-Wno-ASCRANGE"],
        build_dir=sim_build,
        timescale=("1ns", "1ps"),
    )

    runner.test(
        test_module=module,
        hdl_toplevel=toplevel,
        build_dir=sim_build,
        test_dir=sim_build,
        results_xml=os.path.join(sim_build, "results.xml"),
        extra_env=extra_env,
    )
