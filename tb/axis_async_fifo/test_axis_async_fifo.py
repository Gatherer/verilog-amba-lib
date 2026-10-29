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
    # sv: disabled tlast is 0, sink ends a frame on every beat
    _optional_signals = ("tvalid", "tready", "tkeep", "tid", "tdest", "tuser")


class TB:
    def __init__(self, dut):
        self.dut = dut

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        s_clk = int(os.getenv("S_CLK", "10"))
        m_clk = int(os.getenv("M_CLK", "11"))

        cocotb.start_soon(Clock(dut.s_clk, s_clk, unit="ns").start())
        cocotb.start_soon(Clock(dut.m_clk, m_clk, unit="ns").start())

        # tstrb only exists on the sv wrapper
        self.has_strb = hasattr(dut, "STRB_ENABLE")
        self.strb_enable = int(dut.STRB_ENABLE.value) if self.has_strb else 0
        self.last_enable = int(dut.LAST_ENABLE.value)
        self.sv_no_last = self.has_strb and not self.last_enable

        m_bus = (AxiStreamBusNoLast if self.sv_no_last else AxiStreamBus).from_prefix(dut, "m_axis")
        self.source = AxiStreamSource(AxiStreamBus.from_prefix(dut, "s_axis"), dut.s_clk, dut.s_rst)
        self.sink = AxiStreamSink(m_bus, dut.m_clk, dut.m_rst)

        dut.s_pause_req.value = Immediate(0)
        dut.m_pause_req.value = Immediate(0)

        self.byte_lanes = self.source.byte_lanes
        self.keep_enable = int(dut.KEEP_ENABLE.value)
        # DEPTH counts beats without tkeep
        self.depth = int(dut.DEPTH.value) * (1 if self.keep_enable else self.byte_lanes)
        self.id_enable = int(dut.ID_ENABLE.value)
        self.dest_enable = int(dut.DEST_ENABLE.value)
        self.user_enable = int(dut.USER_ENABLE.value)
        self.user_bad = int(dut.USER_BAD_FRAME_VALUE.value)
        self.frame_fifo = int(dut.FRAME_FIFO.value)
        self.drop_oversize_frame = int(dut.DROP_OVERSIZE_FRAME.value)
        self.drop_bad_frame = int(dut.DROP_BAD_FRAME.value)
        self.drop_when_full = int(dut.DROP_WHEN_FULL.value)
        self.mark_when_full = int(dut.MARK_WHEN_FULL.value)
        self.pause_enable = int(dut.PAUSE_ENABLE.value)
        self.frame_pause = int(dut.FRAME_PAUSE.value)
        if self.has_strb:
            dut.s_axis_tstrb.value = Immediate(0)

        self.clear_status()
        cocotb.start_soon(self._monitor_s())
        cocotb.start_soon(self._monitor_m())

    def clear_status(self):
        # s_* counted in s_clk domain, m_* in m_clk domain
        self.s_good_frames = 0
        self.s_bad_frames = 0
        self.s_overflows = 0
        self.m_good_frames = 0
        self.m_bad_frames = 0
        self.m_overflows = 0
        self.out_beats = 0
        self.out_in_frame = False

    async def _monitor_s(self):
        # sample mid cycle, values are stable
        dut = self.dut
        while True:
            await FallingEdge(dut.s_clk)
            if int(dut.s_rst.value) or int(dut.m_rst.value):
                continue
            self.s_good_frames += int(dut.s_status_good_frame.value)
            self.s_bad_frames += int(dut.s_status_bad_frame.value)
            self.s_overflows += int(dut.s_status_overflow.value)
            if not self.pause_enable:
                assert not int(dut.s_pause_ack.value)

    async def _monitor_m(self):
        dut = self.dut
        while True:
            await FallingEdge(dut.m_clk)
            if int(dut.s_rst.value) or int(dut.m_rst.value):
                continue
            self.m_good_frames += int(dut.m_status_good_frame.value)
            self.m_bad_frames += int(dut.m_status_bad_frame.value)
            self.m_overflows += int(dut.m_status_overflow.value)
            if int(dut.m_axis_tvalid.value) and int(dut.m_axis_tready.value):
                self.out_beats += 1
                # without tlast every beat is a frame
                self.out_in_frame = self.last_enable and not int(dut.m_axis_tlast.value)
                if self.sv_no_last:
                    assert not int(dut.m_axis_tlast.value), "tlast set"
                if self.has_strb and not self.strb_enable:
                    assert int(dut.m_axis_tstrb.value) == int(dut.m_axis_tkeep.value), "tstrb not tkeep"
            if self.pause_enable and self.frame_pause and int(dut.m_pause_ack.value):
                assert not self.out_in_frame, "pause inside frame"
            if not self.pause_enable:
                assert not int(dut.m_pause_ack.value)

    def check_status(self, good, bad, overflow):
        assert (self.s_good_frames, self.s_bad_frames, self.s_overflows) == (good, bad, overflow)
        # toggle sync: close events merge in pairs, parity is kept
        for s_cnt, m_cnt in [
            (self.s_good_frames, self.m_good_frames),
            (self.s_bad_frames, self.m_bad_frames),
            (self.s_overflows, self.m_overflows),
        ]:
            assert m_cnt <= s_cnt
            assert (s_cnt - m_cnt) % 2 == 0

    def pipe_beats(self):
        # max beats outside RAM: pipeline and output FIFO
        ram_pipeline = int(self.dut.RAM_PIPELINE.value)
        beats = ram_pipeline + 1
        if int(self.dut.OUTPUT_FIFO_ENABLE.value):
            # same as OUTPUT_FIFO_ADDR_WIDTH in RTL
            out_fifo_aw = 3 if ram_pipeline < 2 else (ram_pipeline * 2 + 6).bit_length()
            beats += 2**out_fifo_aw + 1
        return beats

    @staticmethod
    def last_user(frame):
        # bad frame marker is set on the last beat
        tuser = frame.tuser
        return tuser[-1] if isinstance(tuser, list) else (tuser or 0)

    def frame_len(self, length):
        # without tkeep only full beats are transferred
        if self.keep_enable:
            return length
        return -(-length // self.byte_lanes) * self.byte_lanes

    def check_frame(self, rx_frame, test_frame):
        assert rx_frame.tdata == test_frame.tdata
        assert rx_frame.tid == (test_frame.tid if self.id_enable else 0)
        assert rx_frame.tdest == (test_frame.tdest if self.dest_enable else 0)
        assert rx_frame.tuser == ((test_frame.tuser or 0) if self.user_enable else 0)

    async def wait_empty(self):
        # let pointers and status pulses cross both domains
        for _ in range(16):
            await RisingEdge(self.dut.s_clk)
            await RisingEdge(self.dut.m_clk)
        assert int(self.dut.s_status_depth.value) == 0
        assert int(self.dut.s_status_depth_commit.value) == 0
        assert int(self.dut.m_status_depth.value) == 0
        assert int(self.dut.m_status_depth_commit.value) == 0

    def set_idle_generator(self, generator=None):
        if generator:
            self.source.set_pause_generator(generator())

    def set_backpressure_generator(self, generator=None):
        if generator:
            self.sink.set_pause_generator(generator())

    async def reset(self):
        self.dut.m_rst.value = Immediate(0)
        self.dut.s_rst.value = Immediate(0)
        for _ in range(10):
            await RisingEdge(self.dut.s_clk)
        self.dut.m_rst.value = 1
        self.dut.s_rst.value = 1
        for _ in range(10):
            await RisingEdge(self.dut.s_clk)
        self.dut.m_rst.value = 0
        self.dut.s_rst.value = 0
        for _ in range(10):
            await RisingEdge(self.dut.s_clk)
        # drop data left over from a failed test, drained before reset
        while not self.sink.empty():
            self.sink.recv_nowait()
        self.clear_status()

    async def reset_source(self):
        self.dut.s_rst.value = Immediate(0)
        for _ in range(10):
            await RisingEdge(self.dut.s_clk)
        self.dut.s_rst.value = 1
        for _ in range(10):
            await RisingEdge(self.dut.s_clk)
        self.dut.s_rst.value = 0
        for _ in range(10):
            await RisingEdge(self.dut.s_clk)

    async def reset_sink(self):
        self.dut.m_rst.value = Immediate(0)
        for _ in range(10):
            await RisingEdge(self.dut.m_clk)
        self.dut.m_rst.value = 1
        for _ in range(10):
            await RisingEdge(self.dut.m_clk)
        self.dut.m_rst.value = 0
        for _ in range(10):
            await RisingEdge(self.dut.m_clk)


async def run_test(dut, payload_lengths=None, payload_data=None, idle_inserter=None, backpressure_inserter=None):

    tb = TB(dut)

    id_count = 2 ** len(tb.source.bus.tid)

    cur_id = 1

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = []

    for test_data in [payload_data(tb.frame_len(x)) for x in payload_lengths()]:
        test_frame = AxiStreamFrame(test_data)
        test_frame.tid = cur_id
        test_frame.tdest = cur_id
        # bad frames are dropped with DROP_BAD_FRAME
        test_frame.tuser = 0 if tb.drop_bad_frame else cur_id & 1

        test_frames.append(test_frame)
        await tb.source.send(test_frame)

        cur_id = (cur_id + 1) % id_count

    for test_frame in test_frames:
        rx_frame = await tb.sink.recv()

        tb.check_frame(rx_frame, test_frame)

    assert tb.sink.empty()

    await tb.wait_empty()

    tb.check_status(len(test_frames) if tb.frame_fifo else 0, 0, 0)


async def run_test_tuser_assert(dut):

    tb = TB(dut)

    await tb.reset()

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 32))
    test_frame = AxiStreamFrame(test_data, tuser=tb.user_bad)
    await tb.source.send(test_frame)

    if tb.drop_bad_frame:
        for _ in range(64):
            await RisingEdge(dut.s_clk)

    else:
        rx_frame = await tb.sink.recv()

        assert rx_frame.tdata == test_data
        assert tb.last_user(rx_frame) == (tb.user_bad if tb.user_enable else 0)

    assert tb.sink.empty()

    await tb.wait_empty()

    tb.check_status(int(tb.frame_fifo and not tb.drop_bad_frame), tb.drop_bad_frame, 0)


async def run_test_bad_frame_mix(dut, backpressure_inserter=None):

    tb = TB(dut)

    await tb.reset()

    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = []

    for k in range(32):
        test_data = bytearray(itertools.islice(itertools.cycle(range(k, k + 256)), tb.frame_len(8 + k)))
        test_frame = AxiStreamFrame(test_data, tid=k, tdest=k, tuser=tb.user_bad if k % 3 == 1 else 0)
        test_frames.append(test_frame)
        await tb.source.send(test_frame)

    for test_frame in test_frames:
        if tb.drop_bad_frame and test_frame.tuser:
            continue
        rx_frame = await tb.sink.recv()
        tb.check_frame(rx_frame, test_frame)

    assert tb.sink.empty()

    await tb.wait_empty()

    bad = sum(1 for f in test_frames if f.tuser) if tb.drop_bad_frame else 0
    tb.check_status(len(test_frames) - bad if tb.frame_fifo else 0, bad, 0)


async def run_test_status_depth(dut):

    tb = TB(dut)

    beat_words = tb.byte_lanes if tb.keep_enable else 1
    pipe_beats = tb.pipe_beats()

    await tb.reset()

    tb.sink.pause = True

    beats = 64
    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), beats * tb.byte_lanes))
    test_frame = AxiStreamFrame(test_data)
    await tb.source.send(test_frame)

    for _ in range(beats * 2):
        await RisingEdge(dut.s_clk)
        await RisingEdge(dut.m_clk)

    # words in RAM, rest is in output pipeline
    depth = int(dut.s_status_depth.value)
    assert depth % beat_words == 0
    assert (beats - pipe_beats) * beat_words <= depth <= beats * beat_words
    assert int(dut.s_status_depth_commit.value) == depth
    assert int(dut.m_status_depth.value) == depth
    assert int(dut.m_status_depth_commit.value) == depth

    tb.sink.pause = False

    rx_frame = await tb.sink.recv()
    assert rx_frame.tdata == test_data

    await tb.wait_empty()


async def run_test_tstrb(dut):

    tb = TB(dut)

    if not tb.has_strb:
        return

    strb_mask = 2 ** len(dut.s_axis_tstrb) - 1
    s_strb = []
    m_strb = []

    async def drive():
        # new random tstrb each cycle, sampled on handshake
        while True:
            await RisingEdge(dut.s_clk)
            dut.s_axis_tstrb.value = random.randint(0, strb_mask)

    async def capture_s():
        while True:
            await FallingEdge(dut.s_clk)
            if int(dut.s_axis_tvalid.value) and int(dut.s_axis_tready.value):
                s_strb.append(int(dut.s_axis_tstrb.value))

    async def capture_m():
        while True:
            await FallingEdge(dut.m_clk)
            if int(dut.m_axis_tvalid.value) and int(dut.m_axis_tready.value):
                m_strb.append(int(dut.m_axis_tstrb.value))

    await tb.reset()

    cocotb.start_soon(drive())
    cocotb.start_soon(capture_s())
    cocotb.start_soon(capture_m())

    test_frames = []

    for k in range(8):
        test_data = bytearray(itertools.islice(itertools.cycle(range(256)), tb.frame_len(16 + k)))
        test_frame = AxiStreamFrame(test_data, tid=k, tdest=k, tuser=0)
        test_frames.append(test_frame)
        await tb.source.send(test_frame)

    for test_frame in test_frames:
        rx_frame = await tb.sink.recv()
        tb.check_frame(rx_frame, test_frame)

    await tb.wait_empty()

    assert len(m_strb) == len(s_strb)
    if tb.strb_enable:
        assert m_strb == s_strb


async def run_test_init_sink_pause(dut):

    tb = TB(dut)

    await tb.reset()

    tb.sink.pause = True

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 32))
    test_frame = AxiStreamFrame(test_data)
    await tb.source.send(test_frame)

    for _ in range(64):
        await RisingEdge(dut.s_clk)

    tb.sink.pause = False

    rx_frame = await tb.sink.recv()

    assert rx_frame.tdata == test_data
    assert not rx_frame.tuser

    assert tb.sink.empty()

    await RisingEdge(dut.s_clk)
    await RisingEdge(dut.s_clk)


async def run_test_init_sink_pause_reset(dut):

    tb = TB(dut)

    await tb.reset()

    tb.sink.pause = True

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 32))
    test_frame = AxiStreamFrame(test_data)
    await tb.source.send(test_frame)

    for _ in range(64):
        await RisingEdge(dut.s_clk)

    await tb.reset()

    tb.sink.pause = False

    for _ in range(64):
        await RisingEdge(dut.s_clk)

    assert tb.sink.idle()
    assert tb.sink.empty()

    await tb.wait_empty()


async def run_test_init_sink_pause_source_reset(dut):

    tb = TB(dut)

    await tb.reset()

    tb.sink.pause = True

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 512))
    test_frame = AxiStreamFrame(test_data)
    await tb.source.send(test_frame)

    for _ in range(1024):
        await RisingEdge(dut.s_clk)

    await tb.reset_source()

    tb.sink.pause = False

    for _ in range(64):
        await RisingEdge(dut.s_clk)

    rx_frame = await tb.sink.recv()

    assert tb.last_user(rx_frame) == (tb.user_bad if tb.user_enable else 0)

    assert tb.sink.idle()

    await RisingEdge(dut.s_clk)
    await RisingEdge(dut.s_clk)


async def run_test_init_sink_pause_sink_reset(dut):

    tb = TB(dut)

    await tb.reset()

    tb.sink.pause = True

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 32))
    test_frame = AxiStreamFrame(test_data)
    await tb.source.send(test_frame)

    for _ in range(64):
        await RisingEdge(dut.s_clk)

    await tb.reset_sink()

    tb.sink.pause = False

    for _ in range(64):
        await RisingEdge(dut.s_clk)

    assert tb.sink.idle()

    await RisingEdge(dut.s_clk)
    await RisingEdge(dut.s_clk)


async def run_test_source_reset_after_frames(dut):

    tb = TB(dut)

    await tb.reset()

    # odd and even number of commits, the commit toggle ends at 1 and 0
    for count in [1, 2]:
        for _ in range(count):
            test_frame = AxiStreamFrame(bytearray(range(8 * tb.byte_lanes)))
            await tb.source.send(test_frame)
            rx_frame = await tb.sink.recv()
            assert rx_frame.tdata == test_frame.tdata
            for _ in range(32):
                await RisingEdge(dut.s_clk)

        await tb.reset_source()

        for _ in range(64):
            await RisingEdge(dut.s_clk)

        # no stale data after reset
        assert tb.sink.empty()
        assert tb.sink.idle()

    # FIFO still works
    test_frame = AxiStreamFrame(bytearray(range(8 * tb.byte_lanes)))
    await tb.source.send(test_frame)
    rx_frame = await tb.sink.recv()
    assert rx_frame.tdata == test_frame.tdata

    await tb.wait_empty()


async def run_test_shift_in_source_reset(dut):

    tb = TB(dut)

    await tb.reset()

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 256))
    test_frame = AxiStreamFrame(test_data)
    await tb.source.send(test_frame)

    for _ in range(8):
        await RisingEdge(dut.s_clk)

    await tb.reset_source()

    for _ in range(64):
        await RisingEdge(dut.s_clk)

    if dut.FRAME_FIFO.value:
        assert tb.sink.empty()
    else:
        rx_frame = await tb.sink.recv()

        assert tb.last_user(rx_frame) == (tb.user_bad if tb.user_enable else 0)

        assert tb.sink.empty()
    assert tb.sink.idle()

    await RisingEdge(dut.s_clk)
    await RisingEdge(dut.s_clk)


async def run_test_shift_in_sink_reset(dut):

    tb = TB(dut)

    await tb.reset()

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 256))
    test_frame = AxiStreamFrame(test_data)
    await tb.source.send(test_frame)

    for _ in range(8):
        await RisingEdge(dut.s_clk)

    await tb.reset_sink()

    for _ in range(64):
        await RisingEdge(dut.s_clk)

    assert tb.sink.idle()

    await RisingEdge(dut.s_clk)
    await RisingEdge(dut.s_clk)


async def run_test_shift_out_source_reset(dut):

    tb = TB(dut)

    await tb.reset()

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 256))
    test_frame = AxiStreamFrame(test_data)
    await tb.source.send(test_frame)

    await RisingEdge(dut.m_axis_tvalid)

    for _ in range(8):
        await RisingEdge(dut.s_clk)

    await tb.reset_source()

    for _ in range(64):
        await RisingEdge(dut.s_clk)

    rx_frame = await tb.sink.recv()

    assert tb.last_user(rx_frame) == (tb.user_bad if tb.user_enable else 0)

    assert tb.sink.idle()

    await RisingEdge(dut.s_clk)
    await RisingEdge(dut.s_clk)


async def run_test_shift_out_sink_reset(dut):

    tb = TB(dut)

    await tb.reset()

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 256))
    test_frame = AxiStreamFrame(test_data)
    await tb.source.send(test_frame)

    await RisingEdge(dut.m_axis_tvalid)

    for _ in range(8):
        await RisingEdge(dut.s_clk)

    await tb.reset_sink()

    for _ in range(64):
        await RisingEdge(dut.s_clk)

    assert tb.sink.idle()

    await RisingEdge(dut.s_clk)
    await RisingEdge(dut.s_clk)


async def run_test_pause(dut):

    tb = TB(dut)

    byte_lanes = tb.source.byte_lanes

    await tb.reset()

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), 16 * byte_lanes))
    test_frame = AxiStreamFrame(test_data)

    for _ in range(16):
        await tb.source.send(test_frame)

    for _ in range(60):
        await RisingEdge(dut.s_clk)

    for req in [dut.m_pause_req, dut.s_pause_req]:
        req.value = 1

        for _ in range(64):
            await RisingEdge(dut.s_clk)

        if tb.pause_enable:
            assert int(dut.m_pause_ack.value)
            assert int(dut.s_pause_ack.value)
            if tb.frame_pause:
                assert tb.sink.idle()

            # no transfer while paused
            beats = tb.out_beats
            for _ in range(16):
                await RisingEdge(dut.m_clk)
            assert tb.out_beats == beats

        req.value = 0

        for _ in range(60):
            await RisingEdge(dut.s_clk)

    for _ in range(16):
        rx_frame = await tb.sink.recv()

        assert rx_frame.tdata == test_data
        assert not rx_frame.tuser

    assert tb.sink.empty()

    await tb.wait_empty()

    assert not int(dut.m_pause_ack.value)
    assert not int(dut.s_pause_ack.value)


async def run_test_overflow(dut):

    tb = TB(dut)

    depth = tb.depth
    byte_lanes = tb.source.byte_lanes

    await tb.reset()

    tb.sink.pause = True

    size = 16 * byte_lanes
    count = depth * 2 // size

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), size))
    test_frame = AxiStreamFrame(test_data)
    for _ in range(count):
        await tb.source.send(test_frame)

    for _ in range((depth // byte_lanes) * 3):
        await RisingEdge(dut.s_clk)

    if dut.DROP_WHEN_FULL.value or dut.MARK_WHEN_FULL.value:
        assert tb.source.idle()
    else:
        assert not tb.source.idle()

    tb.sink.pause = False

    if dut.DROP_WHEN_FULL.value or dut.MARK_WHEN_FULL.value:
        for _ in range((depth // byte_lanes) * 3):
            await RisingEdge(dut.s_clk)

        rx_count = 0

        while not tb.sink.empty():
            rx_frame = await tb.sink.recv()

            if dut.MARK_WHEN_FULL.value and rx_frame.tuser:
                continue

            assert rx_frame.tdata == test_data
            assert not rx_frame.tuser

            rx_count += 1

        assert rx_count < count

        await tb.wait_empty()

        # every frame is received or reported as overflow
        tb.check_status(tb.s_good_frames, 0, count - rx_count)

    else:
        for _ in range(count):
            rx_frame = await tb.sink.recv()

            assert rx_frame.tdata == test_data
            assert not rx_frame.tuser

        await tb.wait_empty()

        tb.check_status(count if tb.frame_fifo else 0, 0, 0)

    assert tb.sink.empty()


async def run_test_oversize(dut):

    tb = TB(dut)

    depth = tb.depth
    byte_lanes = tb.source.byte_lanes

    await tb.reset()

    tb.sink.pause = True

    test_data = bytearray(itertools.islice(itertools.cycle(range(256)), depth * 2))
    test_frame = AxiStreamFrame(test_data)
    await tb.source.send(test_frame)

    for _ in range((depth // byte_lanes) * 2):
        await RisingEdge(dut.s_clk)

    tb.sink.pause = False

    if dut.DROP_OVERSIZE_FRAME.value:
        for _ in range((depth // byte_lanes) * 2):
            await RisingEdge(dut.s_clk)

    else:
        rx_frame = await tb.sink.recv()

        if dut.MARK_WHEN_FULL.value:
            assert tb.last_user(rx_frame) == (tb.user_bad if tb.user_enable else 0)
        else:
            assert rx_frame.tdata == test_data
            assert not rx_frame.tuser

    assert tb.sink.empty()

    await tb.wait_empty()

    overflows = int(tb.drop_oversize_frame or tb.mark_when_full)
    good = int(tb.frame_fifo and not tb.drop_oversize_frame)
    tb.check_status(good, 0, overflows)


async def run_stress_test(dut, idle_inserter=None, backpressure_inserter=None):

    tb = TB(dut)

    byte_lanes = tb.source.byte_lanes
    id_count = 2 ** len(tb.source.bus.tid)

    cur_id = 1

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    test_frames = []

    for _ in range(512):
        length = tb.frame_len(random.randint(1, byte_lanes * 16))
        test_data = bytearray(itertools.islice(itertools.cycle(range(256)), length))
        test_frame = AxiStreamFrame(test_data)
        test_frame.tid = cur_id
        test_frame.tdest = cur_id
        # marked frames carry tuser, keep good frames clean in drop/mark modes
        if not (tb.drop_bad_frame or tb.drop_when_full or tb.mark_when_full):
            test_frame.tuser = random.randint(0, 1)

        test_frames.append(test_frame)
        await tb.source.send(test_frame)

        cur_id = (cur_id + 1) % id_count

    if dut.DROP_WHEN_FULL.value or dut.MARK_WHEN_FULL.value:
        cycles = 0
        while cycles < 100:
            cycles += 1
            if (
                not tb.source.idle()
                or int(dut.s_axis_tvalid.value)
                or int(dut.m_axis_tvalid.value)
                or int(dut.m_status_depth.value)
            ):
                cycles = 0
            await RisingEdge(dut.m_clk)

        while not tb.sink.empty():
            rx_frame = await tb.sink.recv()

            if dut.MARK_WHEN_FULL.value and rx_frame.tuser:
                continue

            assert not rx_frame.tuser

            assert len(test_frames) > 0

            while True:
                test_frame = test_frames.pop(0)
                if (
                    rx_frame.tid == test_frame.tid
                    and rx_frame.tdest == test_frame.tdest
                    and rx_frame.tdata == test_frame.tdata
                ):
                    break

        assert len(test_frames) < 512

    else:
        for test_frame in test_frames:
            rx_frame = await tb.sink.recv()

            tb.check_frame(rx_frame, test_frame)

    assert tb.sink.empty()

    await tb.wait_empty()

    overflows = tb.s_overflows if tb.drop_when_full or tb.mark_when_full else 0
    tb.check_status(tb.s_good_frames, 0, overflows)
    if tb.frame_fifo:
        assert tb.s_good_frames == 512 - overflows


async def recv_beats(tb, count):
    # without tlast every beat is a frame
    beats = []
    for _ in range(count):
        rx_frame = await tb.sink.recv()
        beats.append((bytes(rx_frame.tdata), rx_frame.tid, rx_frame.tdest, rx_frame.tuser))
    return beats


def check_beats(rx_beats, expected):
    # report first mismatch, lists are long
    for k, (rx, exp) in enumerate(zip(rx_beats, expected, strict=False)):
        assert rx == exp, f"beat {k}: {rx} != {exp}"
    assert len(rx_beats) == len(expected)


def split_beats(tb, test_frame):
    # expected output beats, sideband repeated on every beat
    tid = (test_frame.tid or 0) if tb.id_enable else 0
    tdest = (test_frame.tdest or 0) if tb.dest_enable else 0
    tuser = (test_frame.tuser or 0) if tb.user_enable else 0
    data = bytes(test_frame.tdata)
    lanes = tb.byte_lanes
    return [(data[k : k + lanes], tid, tdest, tuser) for k in range(0, len(data), lanes)]


async def run_test_no_last(dut, idle_inserter=None, backpressure_inserter=None):

    tb = TB(dut)

    id_count = 2 ** len(tb.source.bus.tid)

    await tb.reset()

    tb.set_idle_generator(idle_inserter)
    tb.set_backpressure_generator(backpressure_inserter)

    expected = []

    for k in range(64):
        length = tb.frame_len(random.randint(1, tb.byte_lanes * 4))
        test_data = bytearray(itertools.islice(itertools.cycle(range(k, k + 256)), length))
        test_frame = AxiStreamFrame(test_data, tid=k % id_count, tdest=k % id_count, tuser=k & 1)
        expected += split_beats(tb, test_frame)
        await tb.source.send(test_frame)

    check_beats(await recv_beats(tb, len(expected)), expected)

    assert tb.sink.empty()

    await tb.wait_empty()

    tb.check_status(0, 0, 0)


async def run_test_no_last_status_depth(dut):

    tb = TB(dut)

    beat_words = tb.byte_lanes if tb.keep_enable else 1
    pipe_beats = tb.pipe_beats()

    await tb.reset()

    tb.sink.pause = True

    beats = 64
    test_frame = AxiStreamFrame(bytearray(itertools.islice(itertools.cycle(range(256)), beats * tb.byte_lanes)))
    await tb.source.send(test_frame)

    for _ in range(beats * 2):
        await RisingEdge(dut.s_clk)
        await RisingEdge(dut.m_clk)

    depth = int(dut.s_status_depth.value)
    assert (beats - pipe_beats) * beat_words <= depth <= beats * beat_words
    assert int(dut.m_status_depth.value) == depth

    tb.sink.pause = False

    check_beats(await recv_beats(tb, beats), split_beats(tb, test_frame))

    await tb.wait_empty()


async def run_test_no_last_pause(dut):

    tb = TB(dut)

    await tb.reset()

    test_frame = AxiStreamFrame(bytearray(itertools.islice(itertools.cycle(range(256)), 256 * tb.byte_lanes)))
    await tb.source.send(test_frame)

    for req in [dut.m_pause_req, dut.s_pause_req]:
        for _ in range(20):
            await RisingEdge(dut.s_clk)

        req.value = 1

        for _ in range(16):
            await RisingEdge(dut.s_clk)

        # cycle pause, stops within the stream
        assert int(dut.m_pause_ack.value)
        beats = tb.out_beats
        for _ in range(16):
            await RisingEdge(dut.m_clk)
        assert tb.out_beats == beats

        req.value = 0

    check_beats(await recv_beats(tb, 256), split_beats(tb, test_frame))

    await tb.wait_empty()


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
    # frame based tests need tlast
    no_last = not int(os.getenv("PARAM_LAST_ENABLE", "1"))
    frame_test = cocotb.test(skip=no_last)

    test_params = cocotb.parametrize(
        ("payload_lengths", [size_list]),
        ("payload_data", [incrementing_payload]),
        ("idle_inserter", [None, cycle_pause]),
        ("backpressure_inserter", [None, cycle_pause, random_pause]),
    )

    run_test = frame_test(test_params(run_test))

    run_test_bad_frame_mix = frame_test(
        cocotb.parametrize(("backpressure_inserter", [None, random_pause]))(run_test_bad_frame_mix)
    )
    run_test_status_depth = frame_test(run_test_status_depth)
    run_test_source_reset_after_frames = frame_test(run_test_source_reset_after_frames)

    run_test_tuser_assert = frame_test(run_test_tuser_assert)
    run_test_tstrb = frame_test(run_test_tstrb)
    run_test_init_sink_pause = frame_test(run_test_init_sink_pause)
    run_test_init_sink_pause_reset = cocotb.test(run_test_init_sink_pause_reset)
    run_test_init_sink_pause_source_reset = frame_test(run_test_init_sink_pause_source_reset)
    run_test_init_sink_pause_sink_reset = cocotb.test(run_test_init_sink_pause_sink_reset)
    run_test_shift_in_source_reset = frame_test(run_test_shift_in_source_reset)
    run_test_shift_in_sink_reset = frame_test(run_test_shift_in_sink_reset)
    run_test_shift_out_source_reset = frame_test(run_test_shift_out_source_reset)
    run_test_shift_out_sink_reset = frame_test(run_test_shift_out_sink_reset)
    run_test_pause = frame_test(run_test_pause)
    run_test_overflow = frame_test(run_test_overflow)
    run_test_oversize = frame_test(run_test_oversize)

    test_params = cocotb.parametrize(
        ("idle_inserter", [None, cycle_pause]),
        ("backpressure_inserter", [None, cycle_pause, random_pause]),
    )

    run_stress_test = frame_test(test_params(run_stress_test))

    # LAST_ENABLE = 0 only
    no_last_test = cocotb.test(skip=not no_last)

    run_test_no_last = no_last_test(test_params(run_test_no_last))
    run_test_no_last_status_depth = no_last_test(run_test_no_last_status_depth)
    run_test_no_last_pause = no_last_test(run_test_no_last_pause)


# cocotb runner

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, "..", "..", "rtl"))
results_dir = os.path.abspath(os.path.join(tests_dir, "..", "results", os.path.basename(tests_dir)))

# simulation runs in results_dir, keep test module importable for cocotb
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)

# HDL variants: verilator build args
hdl_variants = {
    "v": ["-Wno-SELRANGE", "-Wno-WIDTH"],
    "sv": [],
}


def hdl_sources(hdl):
    # sources and toplevel per HDL variant
    dut = "axis_async_fifo"
    if hdl == "sv":
        toplevel = f"{dut}_wrap"
        sources = [
            os.path.join(rtl_dir, "axis", "if", "axis_if.sv"),
            os.path.join(rtl_dir, "common", "sv", "sync_reset_cdc.sv"),
            os.path.join(rtl_dir, "axis", "sv", f"{dut}.sv"),
            os.path.join(tests_dir, f"{toplevel}.sv"),
        ]
    else:
        toplevel = dut
        sources = [os.path.join(rtl_dir, "axis", "v", f"{dut}.v")]
    return toplevel, sources


@pytest.mark.parametrize(("s_clk", "m_clk"), [(10, 10), (10, 11), (11, 10)])
@pytest.mark.parametrize(
    ("frame_fifo", "drop_oversize_frame", "drop_bad_frame", "drop_when_full", "mark_when_full"),
    [(0, 0, 0, 0, 0), (1, 0, 0, 0, 0), (1, 1, 0, 0, 0), (1, 1, 1, 0, 0), (1, 1, 1, 1, 0), (0, 0, 0, 0, 1)],
)
@pytest.mark.parametrize(("ram_pipeline", "output_fifo"), [(0, 0), (1, 0), (4, 0), (0, 1), (1, 1), (4, 1)])
@pytest.mark.parametrize("data_width", [8, 16, 32, 64])
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_axis_async_fifo(
    request,
    hdl,
    data_width,
    ram_pipeline,
    output_fifo,
    frame_fifo,
    drop_oversize_frame,
    drop_bad_frame,
    drop_when_full,
    mark_when_full,
    s_clk,
    m_clk,
):

    run_sim(
        request,
        hdl,
        s_clk,
        m_clk,
        DATA_WIDTH=data_width,
        RAM_PIPELINE=ram_pipeline,
        OUTPUT_FIFO_ENABLE=output_fifo,
        FRAME_FIFO=frame_fifo,
        DROP_OVERSIZE_FRAME=drop_oversize_frame,
        DROP_BAD_FRAME=drop_bad_frame,
        DROP_WHEN_FULL=drop_when_full,
        MARK_WHEN_FULL=mark_when_full,
    )


FRAME = {"FRAME_FIFO": 1, "DROP_OVERSIZE_FRAME": 1}
USER_MASK = {"USER_WIDTH": 4, "USER_BAD_FRAME_VALUE": 2, "USER_BAD_FRAME_MASK": 2}
NO_LAST = {"LAST_ENABLE": 0, "FRAME_PAUSE": 0}

# configurations not covered by the main matrix
EXTRA_CONFIGS = {
    # non power of 2 tkeep width and depth
    "w24": {"DATA_WIDTH": 24, "DEPTH": 3000, **FRAME, "DROP_BAD_FRAME": 1},
    "w24_out_fifo": {"DATA_WIDTH": 24, "DEPTH": 1000, "RAM_PIPELINE": 2, "OUTPUT_FIFO_ENABLE": 1},
    "depth_npot": {"DATA_WIDTH": 32, "DEPTH": 3000, "MARK_WHEN_FULL": 1},
    "no_keep": {"DATA_WIDTH": 32, "KEEP_ENABLE": 0, "DEPTH": 1024, **FRAME},
    "no_id_dest_user": {"DATA_WIDTH": 16, "ID_ENABLE": 0, "DEST_ENABLE": 0, "USER_ENABLE": 0},
    "drop_when_full_only": {"DATA_WIDTH": 8, **FRAME, "DROP_WHEN_FULL": 1},
    "no_pause": {"DATA_WIDTH": 8, "PAUSE_ENABLE": 0},
    "cycle_pause": {"DATA_WIDTH": 16, **FRAME, "FRAME_PAUSE": 0},
    # bad frame marker with mask, tuser wider than 1 bit
    "user_mask": {"DATA_WIDTH": 8, **USER_MASK, **FRAME, "DROP_BAD_FRAME": 1},
    "user_mask_mark": {"DATA_WIDTH": 8, **USER_MASK, "MARK_WHEN_FULL": 1},
    # large clock ratio, both directions
    "s_fast": {"DATA_WIDTH": 8, **FRAME, "clk": (4, 10)},
    "m_fast": {"DATA_WIDTH": 8, "clk": (10, 4)},
    "s_fast_out_fifo": {"DATA_WIDTH": 32, "RAM_PIPELINE": 2, "OUTPUT_FIFO_ENABLE": 1, "clk": (3, 10)},
    "m_fast_frame": {"DATA_WIDTH": 32, **FRAME, "DROP_BAD_FRAME": 1, "clk": (10, 3)},
    # no tlast, no packet mode allowed
    "no_last": {"DATA_WIDTH": 8, **NO_LAST},
    "no_last_w32": {"DATA_WIDTH": 32, **NO_LAST, "RAM_PIPELINE": 2},
    "no_last_out_fifo": {"DATA_WIDTH": 16, **NO_LAST, "RAM_PIPELINE": 4, "OUTPUT_FIFO_ENABLE": 1, "clk": (10, 4)},
    # sv only: tstrb stored
    "strb": {"DATA_WIDTH": 32, "STRB_ENABLE": 1, **FRAME},
    "strb_out_fifo": {"DATA_WIDTH": 32, "STRB_ENABLE": 1, "RAM_PIPELINE": 2, "OUTPUT_FIFO_ENABLE": 1, "clk": (10, 4)},
    # sv only: wide tuser, bad frame marker wider than 32 bit
    "wide_user": {
        "DATA_WIDTH": 16,
        "USER_WIDTH": 40,
        "USER_BAD_FRAME_VALUE": "40'h1",
        "USER_BAD_FRAME_MASK": "40'h1",
        **FRAME,
        "DROP_BAD_FRAME": 1,
    },
}

# parameters only the sv variant has or supports
SV_ONLY_CONFIGS = {"strb", "strb_out_fifo", "wide_user"}


@pytest.mark.parametrize("config", EXTRA_CONFIGS)
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_axis_async_fifo_extra(request, hdl, config):
    if hdl == "v" and config in SV_ONLY_CONFIGS:
        pytest.skip("sv only")
    params = dict(EXTRA_CONFIGS[config])
    s_clk, m_clk = params.pop("clk", (10, 11))
    run_sim(request, hdl, s_clk, m_clk, **params)


# invalid with LAST_ENABLE = 0: (parameters, expected error)
CONFIG_ERRORS = {
    "frame_fifo": ({"FRAME_FIFO": 1}, "FRAME_FIFO set requires LAST_ENABLE"),
    "drop_oversize": ({"DROP_OVERSIZE_FRAME": 1}, "DROP_OVERSIZE_FRAME set requires FRAME_FIFO"),
    "drop_bad": ({"DROP_BAD_FRAME": 1}, "DROP_BAD_FRAME set requires FRAME_FIFO"),
    "drop_when_full": ({"DROP_WHEN_FULL": 1}, "DROP_WHEN_FULL set requires FRAME_FIFO"),
    "mark_when_full": ({"MARK_WHEN_FULL": 1}, "MARK_WHEN_FULL set requires LAST_ENABLE"),
    "frame_pause": ({"FRAME_PAUSE": 1}, "FRAME_PAUSE set requires LAST_ENABLE"),
}


@pytest.mark.parametrize("config", CONFIG_ERRORS)
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_axis_async_fifo_config_error(request, hdl, config):
    params, message = CONFIG_ERRORS[config]
    params = {**NO_LAST, **params}
    toplevel, sources = hdl_sources(hdl)
    gparams = [f"-G{k}={v}" for k, v in params.items()]
    if hdl == "sv":
        # sv: config checks fail at elaboration
        cmd = ["verilator", "--lint-only", *gparams, "--top-module", toplevel, *sources]
        res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    else:
        # v: config checks run at sim start, plain verilator binary is enough
        build_dir = os.path.join(results_dir, request.node.name.replace("[", "-").replace("]", ""))
        os.makedirs(build_dir, exist_ok=True)
        cmd = ["verilator", "--binary", "-Wno-fatal", *hdl_variants[hdl], "--Mdir", build_dir]
        cmd += [*gparams, "--top-module", toplevel, "-o", "sim", *sources]
        subprocess.run(cmd, check=True, capture_output=True)
        res = subprocess.run([os.path.join(build_dir, "sim")], check=False, capture_output=True, text=True)
    assert res.returncode != 0
    assert message in res.stdout + res.stderr


def run_sim(request, hdl, s_clk, m_clk, **overrides):

    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel, verilog_sources = hdl_sources(hdl)

    data_width = overrides.get("DATA_WIDTH", 8)
    keep_width = (data_width + 7) // 8

    parameters = {}

    parameters["DATA_WIDTH"] = data_width
    parameters["KEEP_ENABLE"] = int(data_width > 8)
    parameters["KEEP_WIDTH"] = keep_width
    parameters["DEPTH"] = 1024 * keep_width
    parameters["LAST_ENABLE"] = 1
    parameters["ID_ENABLE"] = 1
    parameters["ID_WIDTH"] = 8
    parameters["DEST_ENABLE"] = 1
    parameters["DEST_WIDTH"] = 8
    parameters["USER_ENABLE"] = 1
    parameters["USER_WIDTH"] = 1
    parameters["RAM_PIPELINE"] = 1
    parameters["OUTPUT_FIFO_ENABLE"] = 0
    parameters["FRAME_FIFO"] = 0
    parameters["USER_BAD_FRAME_VALUE"] = 1
    parameters["USER_BAD_FRAME_MASK"] = 1
    parameters["DROP_OVERSIZE_FRAME"] = 0
    parameters["DROP_BAD_FRAME"] = 0
    parameters["DROP_WHEN_FULL"] = 0
    parameters["MARK_WHEN_FULL"] = 0
    parameters["PAUSE_ENABLE"] = 1
    parameters["FRAME_PAUSE"] = 1

    parameters.update(overrides)

    # sv wrapper: KEEP_WIDTH is a localparam
    if hdl == "sv":
        del parameters["KEEP_WIDTH"]

    extra_env = {f"PARAM_{k}": str(v) for k, v in parameters.items()}

    extra_env["S_CLK"] = str(s_clk)
    extra_env["M_CLK"] = str(m_clk)

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
