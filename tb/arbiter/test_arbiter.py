#!/usr/bin/env python
"""

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

import logging
import os
import random
import sys

import pytest

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from cocotb_tools.runner import get_runner


class TB:
    def __init__(self, dut):
        self.dut = dut

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        self.ports = len(dut.request)
        self.round_robin = int(os.getenv("PARAM_ARB_TYPE_ROUND_ROBIN"))
        self.block = int(os.getenv("PARAM_ARB_BLOCK"))
        self.block_ack = int(os.getenv("PARAM_ARB_BLOCK_ACK"))
        self.lsb_high_priority = int(os.getenv("PARAM_ARB_LSB_HIGH_PRIORITY"))

        cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

        self.model_reset()

    def model_reset(self):
        self.grant = 0
        self.grant_valid = 0
        self.grant_encoded = 0
        self.mask = 0

    def select(self, value):
        # index of the highest priority bit
        if self.lsb_high_priority:
            return (value & -value).bit_length()-1
        return value.bit_length()-1

    def model(self, request, acknowledge):
        # advance reference model by one clock cycle
        ones = 2**self.ports-1

        if self.block and not self.block_ack and self.grant & request:
            # granted request still asserted; hold it
            return
        if self.block and self.block_ack and self.grant_valid and not self.grant & acknowledge:
            # granted request not yet acknowledged; hold it
            return

        self.grant = 0
        self.grant_valid = 0
        self.grant_encoded = 0

        if request == 0:
            return

        if self.round_robin and request & self.mask:
            index = self.select(request & self.mask)
        else:
            index = self.select(request)

        self.grant = 1 << index
        self.grant_valid = 1
        self.grant_encoded = index

        if self.round_robin:
            if self.lsb_high_priority:
                self.mask = (ones << (index+1)) & ones
            else:
                self.mask = ones >> (self.ports-index)

    async def init(self):
        self.dut.rst.value = 1
        self.dut.request.value = 0
        self.dut.acknowledge.value = 0

        for _ in range(4):
            await RisingEdge(self.dut.clk)
        self.dut.rst.value = 0
        await FallingEdge(self.dut.clk)

        self.model_reset()
        self.check(0, 0)

    def check(self, request, acknowledge):
        state = f"request {request:#x} acknowledge {acknowledge:#x}"

        assert int(self.dut.grant_valid.value) == self.grant_valid, \
            f"{state}: grant_valid {int(self.dut.grant_valid.value)} != {self.grant_valid}"
        assert int(self.dut.grant.value) == self.grant, \
            f"{state}: grant {int(self.dut.grant.value):#x} != {self.grant:#x}"
        if self.grant_valid:
            assert int(self.dut.grant_encoded.value) == self.grant_encoded, \
                f"{state}: grant_encoded {int(self.dut.grant_encoded.value)} != {self.grant_encoded}"

    async def cycle(self, request, acknowledge=0):
        # inputs change on falling edge, outputs are checked one cycle later
        self.dut.request.value = request
        self.dut.acknowledge.value = acknowledge
        await RisingEdge(self.dut.clk)
        self.model(request, acknowledge)
        await FallingEdge(self.dut.clk)

        self.check(request, acknowledge)

        return int(self.dut.grant.value)


async def run_test_idle(dut):

    tb = TB(dut)

    await tb.init()

    for _ in range(8):
        await tb.cycle(0)


async def run_test_single(dut):

    tb = TB(dut)

    await tb.init()

    # every port alone: request, acknowledge, release
    for i in range(tb.ports):
        await tb.cycle(1 << i)
        await tb.cycle(1 << i, 1 << i)
        await tb.cycle(0)
        await tb.cycle(0)


async def run_test_all(dut):

    tb = TB(dut)

    await tb.init()

    # all ports requesting, granted port acknowledges every cycle
    # (blocking on request: granted port releases by dropping its request)
    ones = 2**tb.ports-1
    release_request = tb.block and not tb.block_ack
    grants = []
    grant = 0

    for _ in range(3*tb.ports):
        grant = await tb.cycle(ones & ~grant if release_request else ones, grant)
        grants.append(grant)

    first = 1 << tb.select(ones)
    second = 1 << tb.select(ones & ~first)

    if tb.round_robin:
        # every port is granted once per round
        for k in range(0, len(grants), tb.ports):
            assert sorted(grants[k:k+tb.ports]) == [1 << i for i in range(tb.ports)], \
                f"round robin grant sequence {[hex(g) for g in grants]}"
    elif release_request:
        # highest priority port wins whenever it is requesting
        assert set(grants[0::2]) == {first} and set(grants[1::2]) == {second}, \
            f"fixed priority grant sequence {[hex(g) for g in grants]}"
    else:
        # highest priority port always wins
        assert set(grants) == {first}, \
            f"fixed priority grant sequence {[hex(g) for g in grants]}"


async def run_test_hold(dut):

    tb = TB(dut)

    await tb.init()

    # granted port keeps requesting without acknowledge, others compete
    ones = 2**tb.ports-1

    for i in range(tb.ports):
        await tb.cycle(1 << i)
        for _ in range(4):
            await tb.cycle(ones)
        await tb.cycle(ones, ones)
        await tb.cycle(0, ones)
        await tb.cycle(0)


async def run_stress_test(dut):

    tb = TB(dut)

    await tb.init()

    for _ in range(1024):
        await tb.cycle(random.getrandbits(tb.ports), random.getrandbits(tb.ports))

    # reset during operation
    tb.dut.rst.value = 1
    await tb.init()

    for _ in range(256):
        await tb.cycle(random.getrandbits(tb.ports), tb.grant if random.random() < 0.5 else 0)


if getattr(cocotb, "SIM_NAME", None):

    run_test_idle = cocotb.test(run_test_idle)
    run_test_single = cocotb.test(run_test_single)
    run_test_all = cocotb.test(run_test_all)
    run_test_hold = cocotb.test(run_test_hold)
    run_stress_test = cocotb.test(run_stress_test)


# cocotb runner

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, '..', '..', 'rtl', 'common'))
results_dir = os.path.abspath(os.path.join(tests_dir, '..', 'results', os.path.basename(tests_dir)))

# simulation runs in results_dir, keep test module importable for cocotb
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)


# HDL variants: source file extension and verilator build args
hdl_variants = {
    "v": ["-Wno-SELRANGE", "-Wno-WIDTH", "-Wno-UNOPTFLAT"],
    "sv": [],
}


@pytest.mark.parametrize("arb_lsb_high_priority", [0, 1])
@pytest.mark.parametrize(("arb_block", "arb_block_ack"), [(0, 0), (1, 0), (1, 1)])
@pytest.mark.parametrize("arb_type_round_robin", [0, 1])
@pytest.mark.parametrize("ports", [2, 3, 5, 8])
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_arbiter(request, hdl, ports, arb_type_round_robin, arb_block, arb_block_ack, arb_lsb_high_priority):
    dut = "arbiter"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(rtl_dir, hdl, f"{dut}.{hdl}"),
        os.path.join(rtl_dir, hdl, f"priority_encoder.{hdl}"),
    ]

    parameters = {}

    parameters['PORTS'] = ports
    parameters['ARB_TYPE_ROUND_ROBIN'] = arb_type_round_robin
    parameters['ARB_BLOCK'] = arb_block
    parameters['ARB_BLOCK_ACK'] = arb_block_ack
    parameters['ARB_LSB_HIGH_PRIORITY'] = arb_lsb_high_priority

    extra_env = {f'PARAM_{k}': str(v) for k, v in parameters.items()}

    sim_build = os.path.join(results_dir,
        request.node.name.replace('[', '-').replace(']', ''))

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
