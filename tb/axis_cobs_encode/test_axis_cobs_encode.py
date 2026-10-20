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
import sys

import pytest

import cocotb
from cocotb.clock import Clock
from cocotb.handle import Immediate
from cocotb.triggers import RisingEdge
from cocotb_tools.runner import get_runner

from cocotbext.axi import AxiStreamBus, AxiStreamFrame, AxiStreamSink, AxiStreamSource


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


def prbs31(state=0x7FFFFFFF):
    while True:
        for _ in range(8):
            if bool(state & 0x08000000) ^ bool(state & 0x40000000):
                state = ((state & 0x3FFFFFFF) << 1) | 1
            else:
                state = (state & 0x3FFFFFFF) << 1
        yield state & 0xFF


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
        test_frame = AxiStreamFrame(test_data)
        await tb.source.send(test_frame)

    for test_data in test_frames:
        rx_frame = await tb.sink.recv()

        if append_zero:
            assert rx_frame.tdata == cobs_encode(test_data) + b"\x00"
            assert cobs_decode(rx_frame.tdata[:-1]) == test_data
        else:
            assert rx_frame.tdata == cobs_encode(test_data)
            assert cobs_decode(rx_frame.tdata) == test_data
        assert not rx_frame.tuser

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


def cycle_pause():
    return itertools.cycle([1, 1, 1, 0])


def size_list():
    return list(range(1, 33)) + list(range(253, 259)) + [512] + [1] * 64


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
        ("backpressure_inserter", [None, cycle_pause]),
    )

    run_test = cocotb.test(test_params(run_test))


# cocotb runner

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, "..", "..", "rtl", "axis", "v"))
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


@pytest.mark.parametrize("append_zero", [0, 1])
def test_axis_cobs_encode(request, append_zero):
    dut = "axis_cobs_encode"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(rtl_dir, f"{dut}.f"),
    ]

    verilog_sources = process_f_files(verilog_sources)

    parameters = {}

    parameters["APPEND_ZERO"] = append_zero

    extra_env = {f"PARAM_{k}": str(v) for k, v in parameters.items()}

    sim_build = os.path.join(results_dir, request.node.name.replace("[", "-").replace("]", ""))

    runner = get_runner("verilator")

    runner.build(
        sources=verilog_sources,
        hdl_toplevel=toplevel,
        parameters=parameters,
        build_args=["-Wno-SELRANGE", "-Wno-WIDTH", "-Wno-PINMISSING"],
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
