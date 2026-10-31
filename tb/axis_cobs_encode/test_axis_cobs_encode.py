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

# sv only: s_axis without tuser, error marker is ignored
NO_USER = not int(os.getenv("PARAM_S_USER_ENABLE", "1"))


def cobs_encode(block):
    block = bytearray(block)
    enc = bytearray()

    seg = bytearray()
    code = 1

    new_data = True

    for b in block:
        if b == 0:
            enc.append(code)
            enc.extend(seg)
            code = 1
            seg = bytearray()
            new_data = True
        else:
            code += 1
            seg.append(b)
            new_data = True
            if code == 255:
                enc.append(code)
                enc.extend(seg)
                code = 1
                seg = bytearray()
                new_data = False

    if new_data:
        enc.append(code)
        enc.extend(seg)

    return bytes(enc)


def cobs_decode(block):
    block = bytearray(block)
    dec = bytearray()

    code = 0

    i = 0

    if 0 in block:
        return None

    while i < len(block):
        code = block[i]
        i += 1
        if i + code - 1 > len(block):
            return None
        dec.extend(block[i : i + code - 1])
        i += code - 1
        if code < 255 and i < len(block):
            dec.append(0)

    return bytes(dec)


def cobs_encode_error(block):
    # last byte dropped, open segment closed, invalid code 2 terminates frame
    return cobs_encode(bytes(block[:-1]) + b"\x00")[:-1] + b"\x02"


def prbs31(state=0x7FFFFFFF):
    while True:
        for _ in range(8):
            if bool(state & 0x08000000) ^ bool(state & 0x40000000):
                state = ((state & 0x3FFFFFFF) << 1) | 1
            else:
                state = (state & 0x3FFFFFFF) << 1
        yield state & 0xFF


def frame_tuser(frame):
    tuser = frame.tuser
    if isinstance(tuser, list):
        return tuser
    return [tuser or 0] * len(frame.tdata)


class TB:
    def __init__(self, dut):
        self.dut = dut

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

        self.source = AxiStreamSource(AxiStreamBus.from_prefix(dut, "s_axis"), dut.clk, dut.rst)
        self.sink = AxiStreamSink(AxiStreamBus.from_prefix(dut, "m_axis"), dut.clk, dut.rst)

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

    append_zero = int(os.getenv("PARAM_APPEND_ZERO"))

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = [payload_data(x) for x in payload_lengths()]

    for test_data in test_frames:
        # tuser on non-last beats must be ignored
        tuser = [random.randrange(2) for _ in test_data[:-1]] + [0]
        test_frame = AxiStreamFrame(test_data, tuser=tuser)
        await tb.source.send(test_frame)

    for test_data in test_frames:
        rx_frame = await tb.sink.recv()

        if append_zero:
            assert rx_frame.tdata == cobs_encode(test_data) + b"\x00"
            assert cobs_decode(rx_frame.tdata[:-1]) == test_data
        else:
            assert rx_frame.tdata == cobs_encode(test_data)
            assert cobs_decode(rx_frame.tdata) == test_data
        assert not any(frame_tuser(rx_frame))

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_error(dut, idle_inserter=None, backpressure_inserter=None):
    # tuser on last beat marks bad frame, mixed with good frames

    tb = TB(dut)

    append_zero = int(os.getenv("PARAM_APPEND_ZERO"))

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = []
    for length in [1, 2, 3, 253, 254, 255, 256, 508, 509]:
        for payload in [nonzero_incrementing_payload, zero_payload, prbs_payload]:
            for last in [0x00, 0x5A]:
                for error in [1, 0]:
                    test_data = payload(length)
                    test_data[-1] = last
                    test_frames.append((bytes(test_data), error))

    for test_data, error in test_frames:
        tuser = [0] * (len(test_data) - 1) + [error]
        await tb.source.send(AxiStreamFrame(test_data, tuser=tuser))

    for test_data, error in test_frames:
        rx_frame = await tb.sink.recv()

        exp_error = error and not NO_USER

        if exp_error:
            expected = cobs_encode_error(test_data)
        else:
            expected = cobs_encode(test_data)

        if append_zero:
            expected += b"\x00"

        assert rx_frame.tdata == expected
        # error flag only on last beat
        assert frame_tuser(rx_frame) == [0] * (len(expected) - 1) + [exp_error]

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_stall(dut):
    # blocked sink, both FIFOs fill up, input must stall without loss

    tb = TB(dut)

    append_zero = int(os.getenv("PARAM_APPEND_ZERO"))

    await tb.reset()

    tb.sink.pause = True

    # zero frame fills code FIFO, nonzero frame fills data FIFO
    test_frames = [zero_payload(600), nonzero_incrementing_payload(600), prbs_payload(600)]

    for test_data in test_frames:
        await tb.source.send(AxiStreamFrame(test_data))

    for _ in range(2000):
        await RisingEdge(dut.clk)

    assert not dut.s_axis_tready.value
    assert not tb.source.idle()
    assert tb.sink.empty()

    tb.sink.pause = False

    for test_data in test_frames:
        rx_frame = await tb.sink.recv()

        expected = cobs_encode(test_data)
        if append_zero:
            expected += b"\x00"

        assert rx_frame.tdata == expected
        assert not any(frame_tuser(rx_frame))

    assert tb.sink.empty()


async def run_test_reset(dut):
    # reset in the middle of a frame, next frames must be clean

    tb = TB(dut)

    append_zero = int(os.getenv("PARAM_APPEND_ZERO"))

    await tb.reset()

    tb.set_backpressure_generator(cycle_pause)

    await tb.source.send(AxiStreamFrame(prbs_payload(600)))

    for _ in range(300):
        await RisingEdge(dut.clk)

    await tb.reset()

    tb.source.clear()
    tb.sink.clear()

    test_frames = [prbs_payload(x) for x in [1, 8, 254, 300]]

    for test_data in test_frames:
        await tb.source.send(AxiStreamFrame(test_data))

    for test_data in test_frames:
        rx_frame = await tb.sink.recv()

        expected = cobs_encode(test_data)
        if append_zero:
            expected += b"\x00"

        assert rx_frame.tdata == expected

    assert tb.sink.empty()


def cycle_pause():
    return itertools.cycle([1, 1, 1, 0])


def random_pause():
    while True:
        yield int(random.random() < 0.5)


def size_list():
    return list(range(1, 33)) + list(range(253, 259)) + [508, 509, 512] + [1] * 64


def zero_payload(length):
    return bytearray(length)


def incrementing_payload(length):
    return bytearray(itertools.islice(itertools.cycle(range(256)), length))


def nonzero_incrementing_payload(length):
    return bytearray(itertools.islice(itertools.cycle(range(1, 256)), length))


def nonzero_incrementing_payload_zero_framed(length):
    return bytearray([0, *list(itertools.islice(itertools.cycle(range(1, 256)), length)), 0])


def prbs_payload(length):
    gen = prbs31()
    return bytearray([next(gen) for x in range(length)])


if getattr(cocotb, "SIM_NAME", None):
    test_params = cocotb.parametrize(
        ("payload_lengths", [size_list]),
        (
            "payload_data",
            [zero_payload, nonzero_incrementing_payload, nonzero_incrementing_payload_zero_framed, prbs_payload],
        ),
        ("idle_inserter", [None, cycle_pause]),
        ("backpressure_inserter", [None, cycle_pause, random_pause]),
    )

    run_test = cocotb.test(test_params(run_test))

    run_test_error = cocotb.test(
        cocotb.parametrize(
            ("idle_inserter", [None, cycle_pause]),
            ("backpressure_inserter", [None, random_pause]),
        )(run_test_error)
    )

    run_test_stall = cocotb.test(run_test_stall)

    run_test_reset = cocotb.test(run_test_reset)


# cocotb runner

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, "..", "..", "rtl", "axis"))
results_dir = os.path.abspath(os.path.join(tests_dir, "..", "results", os.path.basename(tests_dir)))

# simulation runs in results_dir, keep test module importable for cocotb
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)


def process_f_files(files):
    lst = {}
    for f in files:
        if f[-2:].lower() == ".f":
            with open(f) as fp:
                names = fp.read().split()
            for sub in process_f_files([os.path.join(os.path.dirname(f), x) for x in names]):
                lst[os.path.basename(sub)] = sub
        else:
            lst[os.path.basename(f)] = f
    return list(lst.values())


# HDL variants: verilator build args
hdl_variants = {
    "v": ["-Wno-SELRANGE", "-Wno-WIDTH"],
    "sv": [],
}


@pytest.mark.parametrize("append_zero", [0, 1])
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_axis_cobs_encode(request, hdl, append_zero):
    run_sim(request, hdl, APPEND_ZERO=append_zero)


# configurations not covered by the main test
EXTRA_CONFIGS = {
    # sv only: s_axis without tuser
    "no_user": {"S_USER_ENABLE": 0},
    "no_user_no_zero": {"S_USER_ENABLE": 0, "APPEND_ZERO": 0},
}

# parameters only the sv variant has or supports
SV_ONLY_CONFIGS = {"no_user", "no_user_no_zero"}


@pytest.mark.parametrize("config", EXTRA_CONFIGS)
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_axis_cobs_encode_extra(request, hdl, config):
    if hdl == "v" and config in SV_ONLY_CONFIGS:
        pytest.skip("sv only")
    run_sim(request, hdl, **EXTRA_CONFIGS[config])


def run_sim(request, hdl, **overrides):

    dut = "axis_cobs_encode"
    module = os.path.splitext(os.path.basename(__file__))[0]

    if hdl == "sv":
        toplevel = f"{dut}_wrap"
        verilog_sources = [
            os.path.join(rtl_dir, "if", "axis_if.sv"),
            os.path.join(rtl_dir, hdl, "axis_fifo.sv"),
            os.path.join(rtl_dir, hdl, f"{dut}.sv"),
            os.path.join(tests_dir, f"{toplevel}.sv"),
        ]
    else:
        toplevel = dut
        verilog_sources = process_f_files([os.path.join(rtl_dir, hdl, f"{dut}.f")])

    parameters = {}

    parameters["APPEND_ZERO"] = 1

    parameters.update(overrides)

    extra_env = {f"PARAM_{k}": str(v) for k, v in parameters.items()}

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
