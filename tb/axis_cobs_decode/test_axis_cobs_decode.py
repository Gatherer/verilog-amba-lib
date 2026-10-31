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

# sv only: s_axis without tlast/tuser, disabled inputs are ignored
NO_LAST = not int(os.getenv("PARAM_S_LAST_ENABLE", "1"))
NO_USER = not int(os.getenv("PARAM_S_USER_ENABLE", "1"))


def terminate(enc):
    # without tlast frames end at the zero delimiter
    return enc + b"\x00" if NO_LAST else enc


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


def cobs_encode_long(block):
    # valid, non-canonical: trailing code 1 also after a full 254 byte block
    enc = cobs_encode(block)
    if len(block) % 254 == 0 and 0 not in block[-254:]:
        enc += b"\x01"
    return enc


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


def random_tuser(data):
    # tuser on data beats must be ignored, zero and last beat carry frame status
    return [random.randrange(2) if b else 0 for b in data[:-1]] + [0]


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


async def run_test(
    dut, payload_lengths=None, payload_data=None, framing=None, idle_inserter=None, backpressure_inserter=None
):

    tb = TB(dut)

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = [payload_data(x) for x in payload_lengths()]

    if framing == "stream":
        # one AXI frame, zero delimited, leading zero skipped
        enc = b"\x00" + b"".join(cobs_encode(x) + b"\x00" for x in test_frames)
        await tb.source.send(AxiStreamFrame(enc, tuser=random_tuser(enc)))
    else:
        for test_data in test_frames:
            enc = cobs_encode(test_data)
            if framing == "zero":
                enc += b"\x00"
            await tb.source.send(AxiStreamFrame(enc, tuser=random_tuser(enc)))

    for test_data in test_frames:
        rx_frame = await tb.sink.recv()

        assert rx_frame.tdata == test_data
        assert not any(frame_tuser(rx_frame))

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_long(dut, framing=None, backpressure_inserter=None):
    # non-canonical trailing code 1 and empty frames

    tb = TB(dut)

    await tb.reset()

    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = [
        nonzero_incrementing_payload(254),
        prbs_payload(1),
        nonzero_incrementing_payload(508),
        nonzero_incrementing_payload(2),
    ]

    for test_data in test_frames:
        enc = cobs_encode_long(test_data)
        if framing == "zero":
            enc += b"\x00"
        await tb.source.send(AxiStreamFrame(enc))
        # empty frames, no output, code byte only needs tlast
        for empty in [b"\x01", b"\x01\x00", b"\x00", b"\x00\x00"]:
            if NO_LAST and not empty.endswith(b"\x00"):
                continue
            await tb.source.send(AxiStreamFrame(empty))

    for test_data in test_frames:
        rx_frame = await tb.sink.recv()

        assert rx_frame.tdata == test_data
        assert not any(frame_tuser(rx_frame))

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_error(dut, idle_inserter=None, backpressure_inserter=None):
    # bad frames mixed with good frames, one tuser flagged frame per bad frame

    tb = TB(dut)

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    data = bytes([0x41, 0x42, 0x00, 0x43, 0x44, 0x45, 0x00])
    enc = cobs_encode(data)  # 03 41 42 04 43 44 45 01
    enc_seg = enc[:-1]  # 03 41 42 04 43 44 45, ends in segment

    # (frame, tuser, needs tlast, needs tuser)
    bad_frames = [
        # tuser on tlast beat, end in segment and at code byte
        (enc_seg, [0] * (len(enc_seg) - 1) + [1], True, True),
        (enc, [0] * (len(enc) - 1) + [1], True, True),
        # tuser on zero delimiter
        (enc + b"\x00", [0] * len(enc) + [1], False, True),
        # tlast inside segment
        (enc[:2], None, True, False),
        (enc[:5], None, True, False),
        # tlast on code byte with missing data
        (enc[:4], None, True, False),
        (enc[:-1] + b"\x03", None, True, False),
        # zero inside segment
        (enc[:2] + b"\x00", None, False, False),
        (enc[:5] + b"\x00", None, False, False),
        # zero after code byte
        (enc[:4] + b"\x00", None, False, False),
    ]

    bad_frames = [
        (bad, tuser) for bad, tuser, last, user in bad_frames if not (last and NO_LAST) and not (user and NO_USER)
    ]

    good_frames = [prbs_payload(10), nonzero_incrementing_payload(300), zero_payload(3)]

    for bad, tuser in bad_frames:
        for good in good_frames:
            await tb.source.send(AxiStreamFrame(bad, tuser=tuser))
            await tb.source.send(AxiStreamFrame(terminate(cobs_encode(good))))

    for _ in bad_frames:
        for good in good_frames:
            rx_frame = await tb.sink.recv()

            # error flag only on last beat
            assert frame_tuser(rx_frame) == [0] * (len(rx_frame.tdata) - 1) + [1]

            rx_frame = await tb.sink.recv()

            assert rx_frame.tdata == good
            assert not any(frame_tuser(rx_frame))

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_lone_code(dut):
    # code byte with tlast, frame is dropped, next frame must be clean

    tb = TB(dut)

    await tb.reset()

    test_frames = [prbs_payload(5), nonzero_incrementing_payload(254), zero_payload(2)]

    for code in [0x02, 0x05, 0xFF]:
        for test_data in test_frames:
            await tb.source.send(AxiStreamFrame(bytes([code])))
            await tb.source.send(AxiStreamFrame(bytes([code]), tuser=1))
            await tb.source.send(AxiStreamFrame(cobs_encode(test_data)))

    for _ in range(3):
        for test_data in test_frames:
            rx_frame = await tb.sink.recv()

            assert rx_frame.tdata == test_data
            assert not any(frame_tuser(rx_frame))

    assert tb.sink.empty()

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


async def run_test_stall(dut):
    # blocked sink, input must stall without loss

    tb = TB(dut)

    await tb.reset()

    tb.sink.pause = True

    test_frames = [zero_payload(300), nonzero_incrementing_payload(300), prbs_payload(300)]

    for test_data in test_frames:
        await tb.source.send(AxiStreamFrame(terminate(cobs_encode(test_data))))

    for _ in range(200):
        await RisingEdge(dut.clk)

    assert not dut.s_axis_tready.value
    assert not tb.source.idle()
    assert tb.sink.empty()

    tb.sink.pause = False

    for test_data in test_frames:
        rx_frame = await tb.sink.recv()

        assert rx_frame.tdata == test_data
        assert not any(frame_tuser(rx_frame))

    assert tb.sink.empty()


async def run_test_reset(dut):
    # reset in the middle of a frame, next frames must be clean

    tb = TB(dut)

    await tb.reset()

    tb.set_backpressure_generator(cycle_pause)

    await tb.source.send(AxiStreamFrame(terminate(cobs_encode(prbs_payload(600)))))

    for _ in range(300):
        await RisingEdge(dut.clk)

    await tb.reset()

    tb.source.clear()
    tb.sink.clear()

    test_frames = [prbs_payload(x) for x in [1, 8, 254, 300]]

    for test_data in test_frames:
        await tb.source.send(AxiStreamFrame(terminate(cobs_encode(test_data))))

    for test_data in test_frames:
        rx_frame = await tb.sink.recv()

        assert rx_frame.tdata == test_data
        assert not any(frame_tuser(rx_frame))

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
        ("framing", ["zero", "stream"] if NO_LAST else ["tlast", "zero", "stream"]),
        ("idle_inserter", [None, cycle_pause]),
        ("backpressure_inserter", [None, cycle_pause, random_pause]),
    )

    run_test = cocotb.test(test_params(run_test))

    run_test_long = cocotb.test(
        cocotb.parametrize(
            ("framing", ["zero"] if NO_LAST else ["tlast", "zero"]),
            ("backpressure_inserter", [None, random_pause]),
        )(run_test_long)
    )

    run_test_error = cocotb.test(
        cocotb.parametrize(
            ("idle_inserter", [None, cycle_pause]),
            ("backpressure_inserter", [None, random_pause]),
        )(run_test_error)
    )

    # code byte with tlast, needs tlast
    if not NO_LAST:
        run_test_lone_code = cocotb.test(run_test_lone_code)

    run_test_stall = cocotb.test(run_test_stall)

    run_test_reset = cocotb.test(run_test_reset)


# cocotb runner

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, "..", "..", "rtl", "axis"))
results_dir = os.path.abspath(os.path.join(tests_dir, "..", "results", os.path.basename(tests_dir)))

# simulation runs in results_dir, keep test module importable for cocotb
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)

# HDL variants: verilator build args
hdl_variants = {
    "v": ["-Wno-SELRANGE", "-Wno-WIDTH"],
    "sv": [],
}


@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_axis_cobs_decode(request, hdl):
    run_sim(request, hdl)


# configurations not covered by the main test
EXTRA_CONFIGS = {
    # sv only: s_axis without tlast and/or tuser
    "no_last": {"S_LAST_ENABLE": 0},
    "no_user": {"S_USER_ENABLE": 0},
    "no_last_no_user": {"S_LAST_ENABLE": 0, "S_USER_ENABLE": 0},
}

# parameters only the sv variant has or supports
SV_ONLY_CONFIGS = {"no_last", "no_user", "no_last_no_user"}


@pytest.mark.parametrize("config", EXTRA_CONFIGS)
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_axis_cobs_decode_extra(request, hdl, config):
    if hdl == "v" and config in SV_ONLY_CONFIGS:
        pytest.skip("sv only")
    run_sim(request, hdl, **EXTRA_CONFIGS[config])


def run_sim(request, hdl, **overrides):

    dut = "axis_cobs_decode"
    module = os.path.splitext(os.path.basename(__file__))[0]

    if hdl == "sv":
        toplevel = f"{dut}_wrap"
        verilog_sources = [
            os.path.join(rtl_dir, "if", "axis_if.sv"),
            os.path.join(rtl_dir, hdl, f"{dut}.sv"),
            os.path.join(tests_dir, f"{toplevel}.sv"),
        ]
    else:
        toplevel = dut
        verilog_sources = [
            os.path.join(rtl_dir, hdl, f"{dut}.v"),
        ]

    parameters = {}

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
