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
import subprocess
import sys

import pytest

import cocotb
from cocotb.clock import Clock
from cocotb.handle import Immediate
from cocotb.triggers import FallingEdge, RisingEdge
from cocotb_tools.runner import get_runner

from cocotbext.axi import AxiStreamBus, AxiStreamFrame, AxiStreamSink, AxiStreamSource


class AxiStreamBusNoLast(AxiStreamBus):
    # tlast disabled: tb holds it at 0
    _optional_signals = ("tvalid", "tready", "tkeep", "tid", "tdest", "tuser")


class TB:
    def __init__(self, dut):
        self.dut = dut

        self.ports = ports = int(os.getenv("PORTS"))

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

        # tstrb and LAST_ENABLE only exist on the sv wrapper
        self.is_sv = hasattr(dut, "STRB_ENABLE")
        self.strb_enable = int(dut.STRB_ENABLE.value) if self.is_sv else 0
        self.last_enable = int(dut.LAST_ENABLE.value) if self.is_sv else 1

        self.source = []
        for k in range(ports):
            if self.last_enable:
                bus = AxiStreamBus.from_prefix(dut, f"s{k:02d}_axis")
            else:
                # every beat must be a frame without tlast
                bus = AxiStreamBusNoLast.from_prefix(dut, f"s{k:02d}_axis")
                getattr(dut, f"s{k:02d}_axis_tlast").value = Immediate(0)
            self.source.append(AxiStreamSource(bus, dut.clk, dut.rst))
            if self.is_sv:
                getattr(dut, f"s{k:02d}_axis_tstrb").value = Immediate(0)

        self.sink = AxiStreamSink(AxiStreamBus.from_prefix(dut, "m_axis"), dut.clk, dut.rst)

        dut.enable.value = Immediate(0)
        dut.select.value = Immediate(0)

        if self.is_sv:
            cocotb.start_soon(self._monitor())

    async def _monitor(self):
        # disabled tstrb follows tkeep, disabled tlast is 0
        dut = self.dut
        while True:
            await FallingEdge(dut.clk)
            if int(dut.m_axis_tvalid.value):
                if not self.strb_enable:
                    assert int(dut.m_axis_tstrb.value) == int(dut.m_axis_tkeep.value), "tstrb not tkeep"
                if not self.last_enable:
                    assert not int(dut.m_axis_tlast.value), "tlast set"

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

    # frames need tlast
    if not tb.last_enable:
        return

    id_count = 2 ** len(tb.source[port].bus.tid)

    cur_id = 1

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = []

    dut.enable.value = Immediate(1)
    dut.select.value = Immediate(port)

    # traffic on other ports, must not pass
    for k, source in enumerate(tb.source):
        if k != port:
            await source.send(AxiStreamFrame(incrementing_payload(4), tid=0xFF, tdest=0xFF))

    for test_data in [payload_data(x) for x in payload_lengths()]:
        test_frame = AxiStreamFrame(test_data)
        test_frame.tid = cur_id
        test_frame.tdest = cur_id
        test_frame.tuser = cur_id & 1

        test_frames.append(test_frame)
        await tb.source[port].send(test_frame)

        cur_id = (cur_id + 1) % id_count

    for test_frame in test_frames:
        rx_frame = await tb.sink.recv()

        assert rx_frame.tdata == test_frame.tdata
        assert rx_frame.tid == test_frame.tid
        assert rx_frame.tdest == test_frame.tdest
        assert rx_frame.tuser == test_frame.tuser

    for _ in range(16):
        await RisingEdge(dut.clk)

    assert tb.sink.empty()

    for k, source in enumerate(tb.source):
        if k != port:
            assert not source.idle()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_tuser_assert(dut, port=0):

    tb = TB(dut)

    # frames need tlast
    if not tb.last_enable:
        return

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


async def run_test_enable(dut):
    # no transfer while disabled or with out of range select

    tb = TB(dut)

    # frames need tlast
    if not tb.last_enable:
        return

    ports = len(tb.source)
    sel_count = 2 ** len(dut.select)

    await tb.reset()

    test_frame = AxiStreamFrame(incrementing_payload(8), tid=1, tdest=1)
    await tb.source[0].send(test_frame)

    dut.enable.value = 0
    dut.select.value = 0

    for _ in range(16):
        await RisingEdge(dut.clk)

    assert tb.sink.empty()
    assert not tb.source[0].idle()

    if sel_count > ports:
        dut.enable.value = 1
        dut.select.value = ports

        for _ in range(16):
            await RisingEdge(dut.clk)

        assert tb.sink.empty()
        assert not tb.source[0].idle()

    dut.enable.value = 1
    dut.select.value = 0

    rx_frame = await tb.sink.recv()

    assert rx_frame.tdata == test_frame.tdata
    assert rx_frame.tid == test_frame.tid

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_switch(dut, idle_inserter=None, backpressure_inserter=None):
    # random port per frame, enable toggling, select change mid frame

    tb = TB(dut)

    # frames need tlast
    if not tb.last_enable:
        return

    ports = len(tb.source)
    sel_count = 2 ** len(dut.select)

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    async def toggle_enable():
        while True:
            dut.enable.value = int(random.random() < 0.8)
            await RisingEdge(dut.clk)

    enable_cr = cocotb.start_soon(toggle_enable())

    test_frames = []

    for k in range(64):
        port = random.randrange(ports)
        length = random.randint(1, 3 * len(tb.source[port].bus.tkeep))
        test_frame = AxiStreamFrame(incrementing_payload(length))
        test_frame.tid = k
        test_frame.tdest = port
        test_frame.tuser = k & 1

        test_frames.append(test_frame)

        dut.select.value = port
        await tb.source[port].send(test_frame)

        # wait for first beat, then change select, must be ignored until next frame
        s_tvalid = getattr(dut, f"s{port:02d}_axis_tvalid")
        s_tready = getattr(dut, f"s{port:02d}_axis_tready")
        while True:
            await RisingEdge(dut.clk)
            if s_tvalid.value and s_tready.value:
                break
        dut.select.value = random.randrange(sel_count)
        await tb.source[port].wait()

    for test_frame in test_frames:
        rx_frame = await tb.sink.recv()

        assert rx_frame.tdata == test_frame.tdata
        assert rx_frame.tid == test_frame.tid
        assert rx_frame.tdest == test_frame.tdest
        assert rx_frame.tuser == test_frame.tuser

    for _ in range(16):
        await RisingEdge(dut.clk)

    assert tb.sink.empty()

    enable_cr.cancel()


async def run_test_enable_frame(dut, port=0):
    # sv: enable low pauses a running frame

    tb = TB(dut)

    if not tb.is_sv or not tb.last_enable:
        return

    s_tvalid = getattr(dut, f"s{port:02d}_axis_tvalid")
    s_tready = getattr(dut, f"s{port:02d}_axis_tready")

    await tb.reset()

    dut.enable.value = Immediate(1)
    dut.select.value = Immediate(port)

    test_frame = AxiStreamFrame(incrementing_payload(32 * len(tb.source[port].bus.tkeep)), tid=1, tdest=1)
    await tb.source[port].send(test_frame)

    # wait for first beat, then disable
    while True:
        await RisingEdge(dut.clk)
        if s_tvalid.value and s_tready.value:
            break
    dut.enable.value = 0

    await FallingEdge(dut.clk)
    for _ in range(16):
        assert not int(s_tready.value)
        await FallingEdge(dut.clk)

    assert not tb.source[port].idle()

    dut.enable.value = 1

    rx_frame = await tb.sink.recv()

    assert rx_frame.tdata == test_frame.tdata
    assert rx_frame.tid == test_frame.tid

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_tstrb(dut, idle_inserter=None, backpressure_inserter=None, port=0):
    # random tstrb per cycle, (tdata, tstrb) must reach the output unchanged

    tb = TB(dut)

    if not tb.strb_enable or not tb.last_enable:
        return

    s_prefix = f"s{port:02d}_axis"
    s_tstrb = getattr(dut, f"{s_prefix}_tstrb")
    strb_mask = 2 ** len(s_tstrb) - 1
    s_beats = []
    m_beats = []

    def beat(prefix):
        return (int(getattr(dut, f"{prefix}_tdata").value), int(getattr(dut, f"{prefix}_tstrb").value))

    async def drive():
        while True:
            await RisingEdge(dut.clk)
            s_tstrb.value = random.randint(0, strb_mask)

    async def capture():
        while True:
            await FallingEdge(dut.clk)
            if int(getattr(dut, f"{s_prefix}_tvalid").value) and int(getattr(dut, f"{s_prefix}_tready").value):
                s_beats.append(beat(s_prefix))
            if int(dut.m_axis_tvalid.value) and int(dut.m_axis_tready.value):
                m_beats.append(beat("m_axis"))

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    dut.enable.value = Immediate(1)
    dut.select.value = Immediate(port)

    cocotb.start_soon(drive())
    cocotb.start_soon(capture())

    test_frames = []

    for length in size_list():
        test_frame = AxiStreamFrame(incrementing_payload(length), tid=1, tdest=1, tuser=0)
        test_frames.append(test_frame)
        await tb.source[port].send(test_frame)

    for test_frame in test_frames:
        rx_frame = await tb.sink.recv()
        assert rx_frame.tdata == test_frame.tdata

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert m_beats == s_beats


async def run_test_no_last(dut, idle_inserter=None, backpressure_inserter=None):
    # every beat is a frame, port may change after each beat

    tb = TB(dut)

    if tb.last_enable:
        return

    lanes = len(dut.m_axis_tkeep)
    m_bytes = []

    async def capture():
        while True:
            await FallingEdge(dut.clk)
            if int(dut.m_axis_tvalid.value) and int(dut.m_axis_tready.value):
                data = int(dut.m_axis_tdata.value)
                m_bytes.extend((data >> (8 * n)) & 0xFF for n in range(lanes))

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    dut.enable.value = Immediate(1)

    cocotb.start_soon(capture())

    expected = []

    for k in range(32):
        port = random.randrange(tb.ports)
        # full words only
        data = incrementing_payload(lanes * random.randint(1, 4))
        expected.extend(data)

        dut.select.value = port
        await tb.source[port].send(AxiStreamFrame(data, tid=k, tdest=k, tuser=k & 1))
        await tb.source[port].wait()

    for _ in range(64):
        await RisingEdge(dut.clk)

    assert m_bytes == list(expected)


def cycle_pause():
    return itertools.cycle([1, 1, 1, 0])


def random_pause():
    while True:
        yield int(random.random() < 0.5)


def size_list():
    data_width = len(cocotb.top.m_axis_tdata)
    byte_width = data_width // 8
    return list(range(1, byte_width * 4 + 1)) + [512] + [1] * 64


def incrementing_payload(length):
    return bytearray(itertools.islice(itertools.cycle(range(256)), length))


if getattr(cocotb, "SIM_NAME", None):
    ports = int(os.getenv("PORTS"))

    test_params = cocotb.parametrize(
        ("payload_lengths", [size_list]),
        ("payload_data", [incrementing_payload]),
        ("idle_inserter", [None, cycle_pause]),
        ("backpressure_inserter", [None, cycle_pause, random_pause]),
        ("port", list(range(ports))),
    )

    run_test = cocotb.test(test_params(run_test))

    run_test_enable = cocotb.test(run_test_enable)

    run_test_switch = cocotb.test(
        cocotb.parametrize(
            ("idle_inserter", [None, cycle_pause]),
            ("backpressure_inserter", [None, random_pause]),
        )(run_test_switch)
    )

    test_params = cocotb.parametrize(
        ("port", list(range(ports))),
    )

    run_test_tuser_assert = cocotb.test(test_params(run_test_tuser_assert))

    run_test_enable_frame = cocotb.test(test_params(run_test_enable_frame))

    pause_params = cocotb.parametrize(
        ("idle_inserter", [None, cycle_pause]),
        ("backpressure_inserter", [None, random_pause]),
    )

    run_test_tstrb = cocotb.test(
        cocotb.parametrize(
            ("idle_inserter", [None, cycle_pause]),
            ("backpressure_inserter", [None, random_pause]),
            ("port", list(range(ports))),
        )(run_test_tstrb)
    )

    run_test_no_last = cocotb.test(pause_params(run_test_no_last))


# cocotb runner

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, "..", "..", "rtl", "axis"))
results_dir = os.path.abspath(os.path.join(tests_dir, "..", "results", os.path.basename(tests_dir)))

# simulation runs in results_dir, keep test module importable for cocotb
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)

# HDL variants: verilator build args
hdl_variants = {
    "v": ["-Wno-SELRANGE", "-Wno-WIDTH", "-Wno-ASCRANGE"],
    "sv": [],
}


def run_sim(request, hdl, ports, parameters):
    dut = "axis_mux"
    wrapper = f"{dut}_wrap_{ports}"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = wrapper

    # generate wrapper
    wrapper_file = os.path.join(results_dir, f"{wrapper}.{hdl}")
    if not os.path.exists(wrapper_file):
        os.makedirs(results_dir, exist_ok=True)
        subprocess.Popen(
            [sys.executable, os.path.join(rtl_dir, hdl, f"{dut}_wrap.py"), "-p", f"{ports}"], cwd=results_dir
        ).wait()

    verilog_sources = [wrapper_file]
    if hdl == "sv":
        verilog_sources.append(os.path.join(rtl_dir, "if", "axis_if.sv"))
    verilog_sources.append(os.path.join(rtl_dir, hdl, f"{dut}.{hdl}"))

    parameters.setdefault("DATA_WIDTH", 8)
    parameters["KEEP_ENABLE"] = int(parameters["DATA_WIDTH"] > 8)
    # sv wrapper: KEEP_WIDTH is a localparam
    if hdl == "v":
        parameters["KEEP_WIDTH"] = (parameters["DATA_WIDTH"] + 7) // 8
    parameters.setdefault("ID_ENABLE", 1)
    parameters.setdefault("ID_WIDTH", 8)
    parameters.setdefault("DEST_ENABLE", 1)
    parameters.setdefault("DEST_WIDTH", 8)
    parameters.setdefault("USER_ENABLE", 1)
    parameters.setdefault("USER_WIDTH", 1)

    extra_env = {f"PARAM_{k}": str(v) for k, v in parameters.items()}

    extra_env["PORTS"] = str(ports)

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

    runner.test(
        test_module=module,
        hdl_toplevel=toplevel,
        build_dir=sim_build,
        test_dir=sim_build,
        results_xml=os.path.join(sim_build, "results.xml"),
        extra_env=extra_env,
    )


@pytest.mark.parametrize("data_width", [8, 16, 32])
@pytest.mark.parametrize("ports", range(1, 5))
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_axis_mux(request, hdl, ports, data_width):
    run_sim(request, hdl, ports, {"DATA_WIDTH": data_width})


# parameters only the sv variant has
SV_CONFIGS = {
    "strb": {"STRB_ENABLE": 1},
    "no_last": {"LAST_ENABLE": 0},
}


@pytest.mark.parametrize("config", SV_CONFIGS)
@pytest.mark.parametrize("data_width", [8, 32])
@pytest.mark.parametrize("ports", [1, 3])
def test_axis_mux_sv(request, ports, data_width, config):
    run_sim(request, "sv", ports, {"DATA_WIDTH": data_width, **SV_CONFIGS[config]})
