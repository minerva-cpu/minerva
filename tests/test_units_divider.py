import unittest

from amaranth import *
from amaranth.sim import *

from minerva.units.divider import *
from minerva.isa import Funct3


def test_op(funct3, src1, src2, result):
    def test(self):
        sim = Simulator(self.dut)

        async def testbench(ctx):
            ctx.set(self.dut.x_op, funct3)
            ctx.set(self.dut.x_src1, src1)
            ctx.set(self.dut.x_src2, src2)
            ctx.set(self.dut.x_valid, 1)
            ctx.set(self.dut.x_ready, 1)
            await ctx.tick()
            ctx.set(self.dut.x_valid, 0)
            await ctx.tick()
            while ctx.get(self.dut.m_busy):
                await ctx.tick()
            self.assertEqual(ctx.get(self.dut.m_result), result)

        sim.add_clock(1e-6)
        sim.add_testbench(testbench)
        with sim.write_vcd(vcd_file="dump.vcd"):
            sim.run()

    return test


class DividerTestCase(unittest.TestCase):
    def setUp(self):
        self.dut = Divider()

    # Test cases are taken from the riscv-compliance testbench:
    # https://github.com/riscv/riscv-compliance/tree/master/riscv-test-suite/rv32im

    # DIV ------------------------------------------------------------------------

    test_div_0   = test_op(Funct3.DIV,  0x00000000, 0x00000000, result=0xffffffff)
    test_div_1   = test_op(Funct3.DIV,  0x00000000, 0x00000001, result=0x00000000)
    test_div_2   = test_op(Funct3.DIV,  0x00000000, 0xffffffff, result=0x00000000)
    test_div_3   = test_op(Funct3.DIV,  0x00000000, 0x7fffffff, result=0x00000000)
    test_div_4   = test_op(Funct3.DIV,  0x00000000, 0x80000000, result=0x00000000)

    test_div_5   = test_op(Funct3.DIV,  0x00000001, 0x00000000, result=0xffffffff)
    test_div_6   = test_op(Funct3.DIV,  0x00000001, 0x00000001, result=0x00000001)
    test_div_7   = test_op(Funct3.DIV,  0x00000001, 0xffffffff, result=0xffffffff)
    test_div_8   = test_op(Funct3.DIV,  0x00000001, 0x7fffffff, result=0x00000000)
    test_div_9   = test_op(Funct3.DIV,  0x00000001, 0x80000000, result=0x00000000)

    test_div_10  = test_op(Funct3.DIV,  0xffffffff, 0x00000000, result=0xffffffff)
    test_div_11  = test_op(Funct3.DIV,  0xffffffff, 0x00000001, result=0xffffffff)
    test_div_12  = test_op(Funct3.DIV,  0xffffffff, 0xffffffff, result=0x00000001)
    test_div_13  = test_op(Funct3.DIV,  0xffffffff, 0x7fffffff, result=0x00000000)
    test_div_14  = test_op(Funct3.DIV,  0xffffffff, 0x80000000, result=0x00000000)

    test_div_15  = test_op(Funct3.DIV,  0x7fffffff, 0x00000000, result=0xffffffff)
    test_div_16  = test_op(Funct3.DIV,  0x7fffffff, 0x00000001, result=0x7fffffff)
    test_div_17  = test_op(Funct3.DIV,  0x7fffffff, 0xffffffff, result=0x80000001)
    test_div_18  = test_op(Funct3.DIV,  0x7fffffff, 0x7fffffff, result=0x00000001)
    test_div_19  = test_op(Funct3.DIV,  0x7fffffff, 0x80000000, result=0x00000000)

    test_div_20  = test_op(Funct3.DIV,  0x80000000, 0x00000000, result=0xffffffff)
    test_div_21  = test_op(Funct3.DIV,  0x80000000, 0x00000001, result=0x80000000)
    test_div_22  = test_op(Funct3.DIV,  0x80000000, 0xffffffff, result=0x80000000)
    test_div_23  = test_op(Funct3.DIV,  0x80000000, 0x7fffffff, result=0xffffffff)
    test_div_24  = test_op(Funct3.DIV,  0x80000000, 0x80000000, result=0x00000001)

    # DIVU -----------------------------------------------------------------------

    test_divu_0  = test_op(Funct3.DIVU, 0x00000000, 0x00000000, result=0xffffffff)
    test_divu_1  = test_op(Funct3.DIVU, 0x00000000, 0x00000001, result=0x00000000)
    test_divu_2  = test_op(Funct3.DIVU, 0x00000000, 0xffffffff, result=0x00000000)
    test_divu_3  = test_op(Funct3.DIVU, 0x00000000, 0x7fffffff, result=0x00000000)
    test_divu_4  = test_op(Funct3.DIVU, 0x00000000, 0x80000000, result=0x00000000)

    test_divu_5  = test_op(Funct3.DIVU, 0x00000001, 0x00000000, result=0xffffffff)
    test_divu_6  = test_op(Funct3.DIVU, 0x00000001, 0x00000001, result=0x00000001)
    test_divu_7  = test_op(Funct3.DIVU, 0x00000001, 0xffffffff, result=0x00000000)
    test_divu_8  = test_op(Funct3.DIVU, 0x00000001, 0x7fffffff, result=0x00000000)
    test_divu_9  = test_op(Funct3.DIVU, 0x00000001, 0x80000000, result=0x00000000)

    test_divu_10 = test_op(Funct3.DIVU, 0xffffffff, 0x00000000, result=0xffffffff)
    test_divu_11 = test_op(Funct3.DIVU, 0xffffffff, 0x00000001, result=0xffffffff)
    test_divu_12 = test_op(Funct3.DIVU, 0xffffffff, 0xffffffff, result=0x00000001)
    test_divu_13 = test_op(Funct3.DIVU, 0xffffffff, 0x7fffffff, result=0x00000002)
    test_divu_14 = test_op(Funct3.DIVU, 0xffffffff, 0x80000000, result=0x00000001)

    test_divu_15 = test_op(Funct3.DIVU, 0x7fffffff, 0x00000000, result=0xffffffff)
    test_divu_16 = test_op(Funct3.DIVU, 0x7fffffff, 0x00000001, result=0x7fffffff)
    test_divu_17 = test_op(Funct3.DIVU, 0x7fffffff, 0xffffffff, result=0x00000000)
    test_divu_18 = test_op(Funct3.DIVU, 0x7fffffff, 0x7fffffff, result=0x00000001)
    test_divu_19 = test_op(Funct3.DIVU, 0x7fffffff, 0x80000000, result=0x00000000)

    test_divu_20 = test_op(Funct3.DIVU, 0x80000000, 0x00000000, result=0xffffffff)
    test_divu_21 = test_op(Funct3.DIVU, 0x80000000, 0x00000001, result=0x80000000)
    test_divu_22 = test_op(Funct3.DIVU, 0x80000000, 0xffffffff, result=0x00000000)
    test_divu_23 = test_op(Funct3.DIVU, 0x80000000, 0x7fffffff, result=0x00000001)
    test_divu_24 = test_op(Funct3.DIVU, 0x80000000, 0x80000000, result=0x00000001)

    # REM ------------------------------------------------------------------------

    test_rem_0   = test_op(Funct3.REM,  0x00000000, 0x00000000, result=0x00000000)
    test_rem_1   = test_op(Funct3.REM,  0x00000000, 0x00000001, result=0x00000000)
    test_rem_2   = test_op(Funct3.REM,  0x00000000, 0xffffffff, result=0x00000000)
    test_rem_3   = test_op(Funct3.REM,  0x00000000, 0x7fffffff, result=0x00000000)
    test_rem_4   = test_op(Funct3.REM,  0x00000000, 0x80000000, result=0x00000000)

    test_rem_5   = test_op(Funct3.REM,  0x00000001, 0x00000000, result=0x00000001)
    test_rem_6   = test_op(Funct3.REM,  0x00000001, 0x00000001, result=0x00000000)
    test_rem_7   = test_op(Funct3.REM,  0x00000001, 0xffffffff, result=0x00000000)
    test_rem_8   = test_op(Funct3.REM,  0x00000001, 0x7fffffff, result=0x00000001)
    test_rem_9   = test_op(Funct3.REM,  0x00000001, 0x80000000, result=0x00000001)

    test_rem_10  = test_op(Funct3.REM,  0xffffffff, 0x00000000, result=0xffffffff)
    test_rem_11  = test_op(Funct3.REM,  0xffffffff, 0x00000001, result=0x00000000)
    test_rem_12  = test_op(Funct3.REM,  0xffffffff, 0xffffffff, result=0x00000000)
    test_rem_13  = test_op(Funct3.REM,  0xffffffff, 0x7fffffff, result=0xffffffff)
    test_rem_14  = test_op(Funct3.REM,  0xffffffff, 0x80000000, result=0xffffffff)

    test_rem_15  = test_op(Funct3.REM,  0x7fffffff, 0x00000000, result=0x7fffffff)
    test_rem_16  = test_op(Funct3.REM,  0x7fffffff, 0x00000001, result=0x00000000)
    test_rem_17  = test_op(Funct3.REM,  0x7fffffff, 0xffffffff, result=0x00000000)
    test_rem_18  = test_op(Funct3.REM,  0x7fffffff, 0x7fffffff, result=0x00000000)
    test_rem_19  = test_op(Funct3.REM,  0x7fffffff, 0x80000000, result=0x7fffffff)

    test_rem_20  = test_op(Funct3.REM,  0x80000000, 0x00000000, result=0x80000000)
    test_rem_21  = test_op(Funct3.REM,  0x80000000, 0x00000001, result=0x00000000)
    test_rem_22  = test_op(Funct3.REM,  0x80000000, 0xffffffff, result=0x00000000)
    test_rem_23  = test_op(Funct3.REM,  0x80000000, 0x7fffffff, result=0xffffffff)
    test_rem_24  = test_op(Funct3.REM,  0x80000000, 0x80000000, result=0x00000000)

    # REMU -----------------------------------------------------------------------

    test_remu_0  = test_op(Funct3.REMU, 0x00000000, 0x00000000, result=0x00000000)
    test_remu_1  = test_op(Funct3.REMU, 0x00000000, 0x00000001, result=0x00000000)
    test_remu_2  = test_op(Funct3.REMU, 0x00000000, 0xffffffff, result=0x00000000)
    test_remu_3  = test_op(Funct3.REMU, 0x00000000, 0x7fffffff, result=0x00000000)
    test_remu_4  = test_op(Funct3.REMU, 0x00000000, 0x80000000, result=0x00000000)

    test_remu_5  = test_op(Funct3.REMU, 0x00000001, 0x00000000, result=0x00000001)
    test_remu_6  = test_op(Funct3.REMU, 0x00000001, 0x00000001, result=0x00000000)
    test_remu_7  = test_op(Funct3.REMU, 0x00000001, 0xffffffff, result=0x00000001)
    test_remu_8  = test_op(Funct3.REMU, 0x00000001, 0x7fffffff, result=0x00000001)
    test_remu_9  = test_op(Funct3.REMU, 0x00000001, 0x80000000, result=0x00000001)

    test_remu_10 = test_op(Funct3.REMU, 0xffffffff, 0x00000000, result=0xffffffff)
    test_remu_11 = test_op(Funct3.REMU, 0xffffffff, 0x00000001, result=0x00000000)
    test_remu_12 = test_op(Funct3.REMU, 0xffffffff, 0xffffffff, result=0x00000000)
    test_remu_13 = test_op(Funct3.REMU, 0xffffffff, 0x7fffffff, result=0x00000001)
    test_remu_14 = test_op(Funct3.REMU, 0xffffffff, 0x80000000, result=0x7fffffff)

    test_remu_15 = test_op(Funct3.REMU, 0x7fffffff, 0x00000000, result=0x7fffffff)
    test_remu_16 = test_op(Funct3.REMU, 0x7fffffff, 0x00000001, result=0x00000000)
    test_remu_17 = test_op(Funct3.REMU, 0x7fffffff, 0xffffffff, result=0x7fffffff)
    test_remu_18 = test_op(Funct3.REMU, 0x7fffffff, 0x7fffffff, result=0x00000000)
    test_remu_19 = test_op(Funct3.REMU, 0x7fffffff, 0x80000000, result=0x7fffffff)

    test_remu_20 = test_op(Funct3.REMU, 0x80000000, 0x00000000, result=0x80000000)
    test_remu_21 = test_op(Funct3.REMU, 0x80000000, 0x00000001, result=0x00000000)
    test_remu_22 = test_op(Funct3.REMU, 0x80000000, 0xffffffff, result=0x80000000)
    test_remu_23 = test_op(Funct3.REMU, 0x80000000, 0x7fffffff, result=0x00000001)
    test_remu_24 = test_op(Funct3.REMU, 0x80000000, 0x80000000, result=0x00000000)
