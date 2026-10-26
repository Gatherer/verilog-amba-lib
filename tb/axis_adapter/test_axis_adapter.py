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
import random
import sys

import pytest

import cocotb
from cocotb.clock import Clock
from cocotb.handle import Immediate
from cocotb.triggers import RisingEdge
from cocotb_tools.runner import get_runner

from cocotbext.axi import AxiStreamBus, AxiStreamFrame, AxiStreamSink, AxiStreamSource


class AxiStreamBusNoKeep(AxiStreamBus):
    # tkeep disabled: byte size equals data width
    _optional_signals = ("tvalid", "tready", "tlast", "tid", "tdest", "tuser")


class TB:
    def __init__(self, dut):
        self.dut = dut

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

        if dut.S_KEEP_ENABLE.value:
            self.source = AxiStreamSource(AxiStreamBus.from_prefix(dut, "s_axis"), dut.clk, dut.rst)
        else:
            bus = AxiStreamBusNoKeep.from_prefix(dut, "s_axis")
            self.source = AxiStreamSource(bus, dut.clk, dut.rst, byte_lanes=1)

        if dut.M_KEEP_ENABLE.value:
            self.sink = AxiStreamSink(AxiStreamBus.from_prefix(dut, "m_axis"), dut.clk, dut.rst)
        else:
            bus = AxiStreamBusNoKeep.from_prefix(dut, "m_axis")
            self.sink = AxiStreamSink(bus, dut.clk, dut.rst, byte_lanes=1)

        # tkeep disabled: drive zeros to verify it is ignored
        if not dut.S_KEEP_ENABLE.value:
            dut.s_axis_tkeep.value = 0

    def set_idle_generator(self, generator=None):
        if generator:
            self.source.set_pause_generator(generator())

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


async def run_test(dut, payload_lengths=None, payload_data=None, idle_inserter=None, backpressure_inserter=None):

    tb = TB(dut)

    id_count = 2 ** len(tb.source.bus.tid)

    cur_id = 1

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = []

    for test_data in [payload_data(x) for x in payload_lengths()]:
        test_frame = AxiStreamFrame(test_data)
        test_frame.tid = cur_id
        test_frame.tdest = cur_id
        test_frame.tuser = cur_id & 1

        test_frames.append(test_frame)
        await tb.source.send(test_frame)

        cur_id = (cur_id + 1) % id_count

    for test_frame in test_frames:
        rx_frame = await tb.sink.recv()

        assert list(rx_frame.tdata) == list(test_frame.tdata)
        assert rx_frame.tid == test_frame.tid
        assert rx_frame.tdest == test_frame.tdest
        assert rx_frame.tuser == test_frame.tuser

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_tuser_assert(dut):

    tb = TB(dut)

    await tb.reset()

    test_data = incrementing_payload(32)
    test_frame = AxiStreamFrame(test_data, tuser=1)
    await tb.source.send(test_frame)

    rx_frame = await tb.sink.recv()

    assert list(rx_frame.tdata) == test_data
    assert rx_frame.tuser

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_stress_test(dut, idle_inserter=None, backpressure_inserter=None):

    tb = TB(dut)

    byte_lanes = max(tb.source.byte_lanes, tb.sink.byte_lanes)
    id_count = 2 ** len(tb.source.bus.tid)

    cur_id = 1

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = []

    for _ in range(128):
        length = random.randint(1, byte_lanes * 16)
        test_data = incrementing_payload(length)
        test_frame = AxiStreamFrame(test_data)
        test_frame.tid = cur_id
        test_frame.tdest = cur_id

        test_frames.append(test_frame)
        await tb.source.send(test_frame)

        cur_id = (cur_id + 1) % id_count

    for test_frame in test_frames:
        rx_frame = await tb.sink.recv()

        assert list(rx_frame.tdata) == list(test_frame.tdata)
        assert rx_frame.tid == test_frame.tid
        assert rx_frame.tdest == test_frame.tdest
        assert not rx_frame.tuser

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


def cycle_pause():
    return itertools.cycle([1, 1, 1, 0])


def random_pause():
    while True:
        yield int(random.random() < 0.5)


def byte_size():
    dut = cocotb.top
    lanes = len(dut.s_axis_tkeep) if dut.S_KEEP_ENABLE.value else 1
    return len(dut.s_axis_tdata) // lanes


def size_list():
    data_width = max(len(cocotb.top.s_axis_tdata), len(cocotb.top.m_axis_tdata))
    byte_width = data_width // byte_size()
    return list(range(1, byte_width * 4 + 1)) + [512] + [1] * 64


def incrementing_payload(length):
    # fills upper bits too if bytes are wider than 8 bit
    mask = 2 ** byte_size() - 1
    return [(k * 0x0101) & mask for k in range(length)]


if getattr(cocotb, "SIM_NAME", None):
    test_params = cocotb.parametrize(
        ("payload_lengths", [size_list]),
        ("payload_data", [incrementing_payload]),
        ("idle_inserter", [None, cycle_pause, random_pause]),
        ("backpressure_inserter", [None, cycle_pause, random_pause]),
    )

    run_test = cocotb.test(test_params(run_test))

    run_test_tuser_assert = cocotb.test(run_test_tuser_assert)

    test_params = cocotb.parametrize(
        ("idle_inserter", [None, cycle_pause, random_pause]),
        ("backpressure_inserter", [None, cycle_pause, random_pause]),
    )

    run_stress_test = cocotb.test(test_params(run_stress_test))


# cocotb runner

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, "..", "..", "rtl", "axis", "v"))
results_dir = os.path.abspath(os.path.join(tests_dir, "..", "results", os.path.basename(tests_dir)))

# simulation runs in results_dir, keep test module importable for cocotb
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)


def run_sim(request, parameters):
    dut = "axis_adapter"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(rtl_dir, f"{dut}.v"),
    ]

    parameters["ID_ENABLE"] = 1
    parameters["ID_WIDTH"] = 8
    parameters["DEST_ENABLE"] = 1
    parameters["DEST_WIDTH"] = 8
    parameters["USER_ENABLE"] = 1
    parameters["USER_WIDTH"] = 1

    extra_env = {f"PARAM_{k}": str(v) for k, v in parameters.items()}

    sim_build = os.path.join(results_dir, request.node.name.replace("[", "-").replace("]", ""))

    runner = get_runner("verilator")

    runner.build(
        sources=verilog_sources,
        hdl_toplevel=toplevel,
        parameters=parameters,
        build_args=["-Wno-SELRANGE", "-Wno-WIDTH"],
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


# 24 bit gives a ratio of 3, skip non-integer ratios
data_widths = [8, 16, 24, 32, 64]
width_pairs = [(s, m) for s in data_widths for m in data_widths if s % m == 0 or m % s == 0]


@pytest.mark.parametrize(("s_data_width", "m_data_width"), width_pairs)
def test_axis_adapter(request, s_data_width, m_data_width):
    parameters = {}

    parameters["S_DATA_WIDTH"] = s_data_width
    parameters["S_KEEP_ENABLE"] = int(parameters["S_DATA_WIDTH"] > 8)
    parameters["S_KEEP_WIDTH"] = (parameters["S_DATA_WIDTH"] + 7) // 8
    parameters["M_DATA_WIDTH"] = m_data_width
    parameters["M_KEEP_ENABLE"] = int(parameters["M_DATA_WIDTH"] > 8)
    parameters["M_KEEP_WIDTH"] = (parameters["M_DATA_WIDTH"] + 7) // 8

    run_sim(request, parameters)


# 16 bit bytes, tkeep disabled on one side, KEEP_WIDTH left at default
@pytest.mark.parametrize(
    ("s_data_width", "s_keep_enable", "m_data_width", "m_keep_enable"),
    [(16, 0, 16, 0), (16, 0, 32, 1), (16, 0, 64, 1), (32, 1, 16, 0), (64, 1, 16, 0)],
)
def test_axis_adapter_byte16(request, s_data_width, s_keep_enable, m_data_width, m_keep_enable):
    parameters = {}

    parameters["S_DATA_WIDTH"] = s_data_width
    parameters["S_KEEP_ENABLE"] = s_keep_enable
    parameters["S_KEEP_WIDTH"] = s_data_width // 16 if s_keep_enable else (s_data_width + 7) // 8
    parameters["M_DATA_WIDTH"] = m_data_width
    parameters["M_KEEP_ENABLE"] = m_keep_enable
    parameters["M_KEEP_WIDTH"] = m_data_width // 16 if m_keep_enable else (m_data_width + 7) // 8

    run_sim(request, parameters)
