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
        self.has_strb = hasattr(dut, "STRB_ENABLE")
        self.strb_enable = int(dut.STRB_ENABLE.value) if self.has_strb else 0
        self.last_enable = int(dut.LAST_ENABLE.value) if hasattr(dut, "LAST_ENABLE") else 1

        if self.last_enable:
            bus = AxiStreamBus.from_prefix(dut, "s_axis")
        else:
            # every beat must be a frame without tlast
            bus = AxiStreamBusNoLast.from_prefix(dut, "s_axis")
            dut.s_axis_tlast.value = Immediate(0)

        self.source = AxiStreamSource(bus, dut.clk, dut.rst)
        self.sink = [
            AxiStreamSink(AxiStreamBus.from_prefix(dut, f"m{k:02d}_axis"), dut.clk, dut.rst) for k in range(ports)
        ]

        dut.enable.value = Immediate(0)
        dut.drop.value = Immediate(0)
        dut.select.value = Immediate(0)

        if self.has_strb:
            dut.s_axis_tstrb.value = Immediate(0)
            cocotb.start_soon(self._monitor())

    async def _monitor(self):
        # disabled tstrb follows tkeep, disabled tlast is 0
        dut = self.dut
        while True:
            await FallingEdge(dut.clk)
            for k in range(self.ports):
                if int(getattr(dut, f"m{k:02d}_axis_tvalid").value):
                    tkeep = int(getattr(dut, f"m{k:02d}_axis_tkeep").value)
                    if not self.strb_enable:
                        assert int(getattr(dut, f"m{k:02d}_axis_tstrb").value) == tkeep, "tstrb not tkeep"
                    if not self.last_enable:
                        assert not int(getattr(dut, f"m{k:02d}_axis_tlast").value), "tlast set"

    def set_idle_generator(self, generator=None):
        if generator:
            self.source.set_pause_generator(generator())

    def set_backpressure_generator(self, generator=None):
        if generator:
            for sink in self.sink:
                sink.set_pause_generator(generator())

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

    id_width = len(tb.source.bus.tid)
    id_count = 2**id_width

    dest_width = len(tb.sink[0].bus.tdest)
    dest_count = 2**dest_width
    dest_mask = dest_count - 1

    cur_id = 1

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = []

    dut.enable.value = Immediate(1)
    dut.drop.value = Immediate(0)
    dut.select.value = Immediate(port)

    for test_data in [payload_data(x) for x in payload_lengths()]:
        test_frame = AxiStreamFrame(test_data)
        test_frame.tid = cur_id
        test_frame.tdest = cur_id | (port << dest_width)
        test_frame.tuser = cur_id & 1

        test_frames.append(test_frame)
        await tb.source.send(test_frame)

        cur_id = (cur_id + 1) % id_count

    for test_frame in test_frames:
        rx_frame = await tb.sink[port].recv()

        assert rx_frame.tdata == test_frame.tdata
        assert rx_frame.tid == test_frame.tid
        assert rx_frame.tdest == (test_frame.tdest & dest_mask)
        assert rx_frame.tuser == test_frame.tuser

    for sink in tb.sink:
        assert sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_switch(dut, idle_inserter=None, backpressure_inserter=None):
    # random port per frame, invalid ports, drop, enable toggling, select change mid frame

    tb = TB(dut)

    if not tb.last_enable:
        return

    tdest_route = int(os.getenv("PARAM_TDEST_ROUTE"))

    dest_width = len(tb.sink[0].bus.tdest)
    route_count = 2 ** (len(tb.source.bus.tdest) - dest_width)
    sel_count = 2 ** len(dut.select)

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    async def toggle_enable():
        while True:
            dut.enable.value = int(random.random() < 0.8)
            await RisingEdge(dut.clk)

    enable_cr = cocotb.start_soon(toggle_enable())

    expected = [[] for _ in tb.sink]

    for k in range(64):
        length = random.randint(1, 3 * len(tb.source.bus.tkeep))
        test_frame = AxiStreamFrame(incrementing_payload(length))
        test_frame.tid = k
        test_frame.tuser = k & 1

        if tdest_route:
            port = random.randrange(route_count)
            drop = False
            test_frame.tdest = (port << dest_width) | k
            # ignored in tdest route mode
            dut.select.value = random.randrange(sel_count)
            dut.drop.value = random.randint(0, 1)
        else:
            port = random.randrange(sel_count)
            drop = random.random() < 0.2
            test_frame.tdest = k
            dut.select.value = port
            dut.drop.value = int(drop)

        if not drop and port < len(tb.sink):
            expected[port].append(test_frame)

        await tb.source.send(test_frame)

        if not tdest_route:
            # wait for first beat, then change select and drop, must be ignored until next frame
            while True:
                await RisingEdge(dut.clk)
                if dut.s_axis_tvalid.value and dut.s_axis_tready.value:
                    break
            dut.select.value = random.randrange(sel_count)
            dut.drop.value = random.randint(0, 1)
            await tb.source.wait()

    await tb.source.wait()

    for port, frames in enumerate(expected):
        for test_frame in frames:
            rx_frame = await tb.sink[port].recv()

            assert rx_frame.tdata == test_frame.tdata
            assert rx_frame.tid == test_frame.tid
            assert rx_frame.tdest == test_frame.tdest & (2**dest_width - 1)
            assert rx_frame.tuser == test_frame.tuser

    for _ in range(16):
        await RisingEdge(dut.clk)

    for sink in tb.sink:
        assert sink.empty()

    enable_cr.cancel()


async def run_test_tstrb(dut, idle_inserter=None, backpressure_inserter=None, port=0):
    # random tstrb per cycle, (tdata, tstrb) must reach the selected port unchanged

    tb = TB(dut)

    if not tb.strb_enable or not tb.last_enable:
        return

    dest_width = len(tb.sink[0].bus.tdest)
    strb_mask = 2 ** len(dut.s_axis_tstrb) - 1
    s_beats = []
    m_beats = []

    def beat(prefix):
        return (int(getattr(dut, f"{prefix}_tdata").value), int(getattr(dut, f"{prefix}_tstrb").value))

    async def drive():
        while True:
            await RisingEdge(dut.clk)
            dut.s_axis_tstrb.value = random.randint(0, strb_mask)

    async def capture():
        prefix = f"m{port:02d}_axis"
        while True:
            await FallingEdge(dut.clk)
            if int(dut.s_axis_tvalid.value) and int(dut.s_axis_tready.value):
                s_beats.append(beat("s_axis"))
            if int(getattr(dut, f"{prefix}_tvalid").value) and int(getattr(dut, f"{prefix}_tready").value):
                m_beats.append(beat(prefix))

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    dut.enable.value = Immediate(1)
    dut.select.value = Immediate(port)

    cocotb.start_soon(drive())
    cocotb.start_soon(capture())

    test_frames = []

    for length in size_list():
        test_frame = AxiStreamFrame(incrementing_payload(length), tid=1, tdest=port << dest_width, tuser=0)
        test_frames.append(test_frame)
        await tb.source.send(test_frame)

    for test_frame in test_frames:
        rx_frame = await tb.sink[port].recv()
        assert rx_frame.tdata == test_frame.tdata

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert m_beats == s_beats


async def run_test_no_last(dut, idle_inserter=None, backpressure_inserter=None):
    # every beat is a frame, port may change after each beat

    tb = TB(dut)

    if tb.last_enable:
        return

    dest_width = len(tb.sink[0].bus.tdest)
    lanes = len(dut.s_axis_tkeep)
    m_bytes = [[] for _ in tb.sink]

    async def capture():
        while True:
            await FallingEdge(dut.clk)
            for k in range(tb.ports):
                prefix = f"m{k:02d}_axis"
                if int(getattr(dut, f"{prefix}_tvalid").value) and int(getattr(dut, f"{prefix}_tready").value):
                    data = int(getattr(dut, f"{prefix}_tdata").value)
                    m_bytes[k].extend((data >> (8 * n)) & 0xFF for n in range(lanes))

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    dut.enable.value = Immediate(1)

    cocotb.start_soon(capture())

    expected = [[] for _ in tb.sink]

    for k in range(32):
        port = random.randrange(tb.ports)
        # full words only
        data = incrementing_payload(lanes * random.randint(1, 4))
        expected[port].extend(data)

        dut.select.value = port
        await tb.source.send(AxiStreamFrame(data, tid=k, tdest=(port << dest_width) | k, tuser=k & 1))
        await tb.source.wait()

    for _ in range(64):
        await RisingEdge(dut.clk)

    for k in range(tb.ports):
        assert m_bytes[k] == list(expected[k])


def cycle_pause():
    return itertools.cycle([1, 1, 1, 0])


def random_pause():
    # independent pattern per sink
    while True:
        yield int(random.random() < 0.5)


def size_list():
    data_width = len(cocotb.top.s_axis_tdata)
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

    pause_params = cocotb.parametrize(
        ("idle_inserter", [None, cycle_pause]),
        ("backpressure_inserter", [None, random_pause]),
    )

    run_test_switch = cocotb.test(pause_params(run_test_switch))

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
    "v": ["-Wno-SELRANGE", "-Wno-WIDTH", "-Wno-UNOPTFLAT"],
    "sv": [],
}


def run_sim(request, hdl, ports, parameters):
    dut = "axis_demux"
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
    parameters.setdefault("M_DEST_WIDTH", 8)
    parameters["S_DEST_WIDTH"] = parameters["M_DEST_WIDTH"] + (ports - 1).bit_length()
    parameters.setdefault("USER_ENABLE", 1)
    parameters.setdefault("USER_WIDTH", 1)
    parameters.setdefault("TDEST_ROUTE", 0)

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


@pytest.mark.parametrize("tdest_route", [0, 1])
@pytest.mark.parametrize("data_width", [8, 16, 32])
@pytest.mark.parametrize("ports", range(1, 5))
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_axis_demux(request, hdl, ports, data_width, tdest_route):
    run_sim(request, hdl, ports, {"DATA_WIDTH": data_width, "TDEST_ROUTE": tdest_route})


# parameters only the sv variant has
SV_CONFIGS = {
    "strb": {"STRB_ENABLE": 1},
    "strb_route": {"STRB_ENABLE": 1, "TDEST_ROUTE": 1},
    "no_last": {"LAST_ENABLE": 0},
    "no_last_route": {"LAST_ENABLE": 0, "TDEST_ROUTE": 1},
}


@pytest.mark.parametrize("config", SV_CONFIGS)
@pytest.mark.parametrize("data_width", [8, 32])
@pytest.mark.parametrize("ports", [1, 3])
def test_axis_demux_sv(request, ports, data_width, config):
    run_sim(request, "sv", ports, {"DATA_WIDTH": data_width, **SV_CONFIGS[config]})
