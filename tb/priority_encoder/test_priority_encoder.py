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
from cocotb.triggers import Timer
from cocotb_tools.runner import get_runner


class TB(object):
    def __init__(self, dut):
        self.dut = dut

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        self.width = len(dut.input_unencoded)
        self.lsb_high_priority = int(os.getenv("PARAM_LSB_HIGH_PRIORITY"))

    def model(self, value):
        # expected (valid, encoded, unencoded) for given input
        enc_width = (self.width-1).bit_length()

        if value == 0:
            # current RTL behavior: LSB mode selects upper half on every level
            if self.lsb_high_priority:
                encoded = 2**enc_width-1
            else:
                encoded = 0
            return 0, encoded, (1 << encoded) & (2**self.width-1)

        if self.lsb_high_priority:
            encoded = (value & -value).bit_length()-1
        else:
            encoded = value.bit_length()-1
        return 1, encoded, 1 << encoded

    async def init(self):
        self.dut.input_unencoded.value = 0
        await Timer(10, unit='ns')

    async def check(self, value):
        self.dut.input_unencoded.value = value
        await Timer(10, unit='ns')

        valid, encoded, unencoded = self.model(value)

        assert int(self.dut.output_valid.value) == valid, \
            f"input {value:#x}: output_valid {int(self.dut.output_valid.value)} != {valid}"
        assert int(self.dut.output_encoded.value) == encoded, \
            f"input {value:#x}: output_encoded {int(self.dut.output_encoded.value)} != {encoded}"
        assert int(self.dut.output_unencoded.value) == unencoded, \
            f"input {value:#x}: output_unencoded {int(self.dut.output_unencoded.value):#x} != {unencoded:#x}"


async def run_test_zero(dut):

    tb = TB(dut)

    await tb.init()

    await tb.check(0)


async def run_test_one_bit(dut):

    tb = TB(dut)

    await tb.init()

    for i in range(tb.width):
        await tb.check(1 << i)


async def run_test_two_bits(dut):

    tb = TB(dut)

    await tb.init()

    for i in range(tb.width):
        for j in range(tb.width):
            await tb.check((1 << i) | (1 << j))


async def run_test_ones(dut):

    tb = TB(dut)

    await tb.init()

    # contiguous ones from either end
    for i in range(1, tb.width+1):
        await tb.check(2**i-1)
        await tb.check((2**tb.width-1) ^ (2**(tb.width-i)-1))


async def run_stress_test(dut):

    tb = TB(dut)

    await tb.init()

    for k in range(1024):
        await tb.check(random.getrandbits(tb.width))


if getattr(cocotb, "SIM_NAME", None):

    run_test_zero = cocotb.test(run_test_zero)
    run_test_one_bit = cocotb.test(run_test_one_bit)
    run_test_two_bits = cocotb.test(run_test_two_bits)
    run_test_ones = cocotb.test(run_test_ones)
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


@pytest.mark.parametrize("lsb_high_priority", [0, 1])
@pytest.mark.parametrize("width", [2, 3, 5, 8, 32, 64])
@pytest.mark.parametrize("hdl", list(hdl_variants))
def test_priority_encoder(request, hdl, width, lsb_high_priority):
    dut = "priority_encoder"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(rtl_dir, hdl, f"{dut}.{hdl}"),
    ]

    parameters = {}

    parameters['WIDTH'] = width
    parameters['LSB_HIGH_PRIORITY'] = lsb_high_priority

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
