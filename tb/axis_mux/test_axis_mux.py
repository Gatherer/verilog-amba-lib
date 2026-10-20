"""

Copyright (c) 2021 Alex Forencich
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
import subprocess
import sys

import pytest

import cocotb
from cocotb.clock import Clock
from cocotb.handle import Immediate
from cocotb.triggers import RisingEdge
from cocotb_tools.runner import get_runner

from cocotbext.axi import AxiStreamBus, AxiStreamFrame, AxiStreamSink, AxiStreamSource


class TB:
    def __init__(self, dut):
        self.dut = dut

        ports = len(dut.axis_mux_inst.s_axis_tvalid)

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

        self.source = [
            AxiStreamSource(AxiStreamBus.from_prefix(dut, f"s{k:02d}_axis"), dut.clk, dut.rst) for k in range(ports)
        ]
        self.sink = AxiStreamSink(AxiStreamBus.from_prefix(dut, "m_axis"), dut.clk, dut.rst)

        dut.enable.value = Immediate(0)
        dut.select.value = Immediate(0)

    def set_idle_generator(self, generator=None):
        if generator:
            for source in self.source:
                source.set_pause_generator(generator())

    def set_backpressure_generator(self, generator=None):
        if generator:
            self.sink.set_pause_generator(generator())

    async def reset(self):
        self.dut.rst.value = Immediate(0)
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)
        self.dut.rst.value = 1
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)
        self.dut.rst.value = 0
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)


async def run_test(
    dut, payload_lengths=None, payload_data=None, idle_inserter=None, backpressure_inserter=None, port=0
):

    tb = TB(dut)

    id_count = 2 ** len(tb.source[port].bus.tid)

    cur_id = 1

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = []

    dut.enable.value = Immediate(1)
    dut.select.value = Immediate(port)

    for test_data in [payload_data(x) for x in payload_lengths()]:
        test_frame = AxiStreamFrame(test_data)
        test_frame.tid = cur_id
        test_frame.tdest = cur_id

        test_frames.append(test_frame)
        await tb.source[port].send(test_frame)

        cur_id = (cur_id + 1) % id_count

    for test_frame in test_frames:
        rx_frame = await tb.sink.recv()

        assert rx_frame.tdata == test_frame.tdata
        assert rx_frame.tid == test_frame.tid
        assert rx_frame.tdest == test_frame.tdest
        assert not rx_frame.tuser

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_tuser_assert(dut, port=0):

    tb = TB(dut)

    await tb.reset()

    dut.enable.value = Immediate(1)
    dut.select.value = Immediate(port)

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 32))
    test_frame = AxiStreamFrame(test_data, tuser=1)
    await tb.source[port].send(test_frame)

    rx_frame = await tb.sink.recv()

    assert rx_frame.tdata == test_data
    assert rx_frame.tuser

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


def cycle_pause():
    return itertools.cycle([1, 1, 1, 0])


def size_list():
    data_width = len(cocotb.top.m_axis_tdata)
    byte_width = data_width // 8
    return list(range(1, byte_width * 4 + 1)) + [512] + [1] * 64


def incrementing_payload(length):
    return bytearray(itertools.islice(itertools.cycle(range(256)), length))


if getattr(cocotb, "SIM_NAME", None):
    ports = len(cocotb.top.axis_mux_inst.s_axis_tvalid)

    test_params = cocotb.parametrize(
        ("payload_lengths", [size_list]),
        ("payload_data", [incrementing_payload]),
        ("idle_inserter", [None, cycle_pause]),
        ("backpressure_inserter", [None, cycle_pause]),
        ("port", list(range(ports))),
    )

    run_test = cocotb.test(test_params(run_test))

    test_params = cocotb.parametrize(
        ("port", list(range(ports))),
    )

    run_test_tuser_assert = cocotb.test(test_params(run_test_tuser_assert))


# cocotb runner

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, "..", "..", "rtl", "axis", "v"))
results_dir = os.path.abspath(os.path.join(tests_dir, "..", "results", os.path.basename(tests_dir)))

# simulation runs in results_dir, keep test module importable for cocotb
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)


@pytest.mark.parametrize("data_width", [8, 16, 32])
@pytest.mark.parametrize("ports", [1, 4])
def test_axis_mux(request, ports, data_width):
    dut = "axis_mux"
    wrapper = f"{dut}_wrap_{ports}"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = wrapper

    # generate wrapper
    wrapper_file = os.path.join(results_dir, f"{wrapper}.v")
    if not os.path.exists(wrapper_file):
        os.makedirs(results_dir, exist_ok=True)
        subprocess.Popen(
            [sys.executable, os.path.join(rtl_dir, f"{dut}_wrap.py"), "-p", f"{ports}"], cwd=results_dir
        ).wait()

    verilog_sources = [
        wrapper_file,
        os.path.join(rtl_dir, f"{dut}.v"),
    ]

    parameters = {}

    parameters["DATA_WIDTH"] = data_width
    parameters["KEEP_ENABLE"] = int(parameters["DATA_WIDTH"] > 8)
    parameters["KEEP_WIDTH"] = (parameters["DATA_WIDTH"] + 7) // 8
    parameters["ID_ENABLE"] = 1
    parameters["ID_WIDTH"] = 8
    parameters["DEST_ENABLE"] = 1
    parameters["DEST_WIDTH"] = 8
    parameters["USER_ENABLE"] = 1
    parameters["USER_WIDTH"] = 1

    extra_env = {f"PARAM_{k}": str(v) for k, v in parameters.items()}

    extra_env["PORTS"] = str(ports)

    sim_build = os.path.join(results_dir, request.node.name.replace("[", "-").replace("]", ""))

    runner = get_runner("verilator")

    runner.build(
        sources=verilog_sources,
        hdl_toplevel=toplevel,
        parameters=parameters,
        build_args=["-Wno-SELRANGE", "-Wno-WIDTH", "-Wno-ASCRANGE"],
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
