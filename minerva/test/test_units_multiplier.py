import unittest

from amaranth import *
from amaranth.sim import *

from ..units.multiplier import *
from ..isa import Funct3


def test_op(funct3, src1, src2, result):
    def test(self):
        sim = Simulator(self.dut)
        def process():
            yield self.dut.d_op.eq(funct3)
            yield self.dut.d_stall.eq(0)
            yield Tick()
            yield self.dut.x_src1.eq(src1)
            yield self.dut.x_src2.eq(src2)
            yield self.dut.x_stall.eq(0)
            yield Tick()
            yield self.dut.m_stall.eq(0)
            yield Tick()
            yield Tick()
            self.assertEqual((yield self.dut.w_result), result)
        sim.add_clock(1e-6)
        sim.add_sync_process(process)
        with sim.write_vcd("dump.vcd"):
            sim.run()
    return test


class MultiplierTestCase(unittest.TestCase):
    def setUp(self):
        self.dut = Multiplier()

    # Test cases are taken from the riscv-compliance testbench:
    # https://github.com/riscv/riscv-compliance/tree/master/riscv-test-suite/rv32im

    # MUL ----------------------------------------------------------------------------

    test_mul_0     = test_op(Funct3.MUL,    0x00000000, 0x00000000, result=0x00000000)
    test_mul_1     = test_op(Funct3.MUL,    0x00000000, 0x00000001, result=0x00000000)
    test_mul_2     = test_op(Funct3.MUL,    0x00000000, 0xffffffff, result=0x00000000)
    test_mul_3     = test_op(Funct3.MUL,    0x00000000, 0x7fffffff, result=0x00000000)
    test_mul_4     = test_op(Funct3.MUL,    0x00000000, 0x80000000, result=0x00000000)

    test_mul_5     = test_op(Funct3.MUL,    0x00000001, 0x00000000, result=0x00000000)
    test_mul_6     = test_op(Funct3.MUL,    0x00000001, 0x00000001, result=0x00000001)
    test_mul_7     = test_op(Funct3.MUL,    0x00000001, 0xffffffff, result=0xffffffff)
    test_mul_8     = test_op(Funct3.MUL,    0x00000001, 0x7fffffff, result=0x7fffffff)
    test_mul_9     = test_op(Funct3.MUL,    0x00000001, 0x80000000, result=0x80000000)

    test_mul_10    = test_op(Funct3.MUL,    0xffffffff, 0x00000000, result=0x00000000)
    test_mul_11    = test_op(Funct3.MUL,    0xffffffff, 0x00000001, result=0xffffffff)
    test_mul_12    = test_op(Funct3.MUL,    0xffffffff, 0xffffffff, result=0x00000001)
    test_mul_13    = test_op(Funct3.MUL,    0xffffffff, 0x7fffffff, result=0x80000001)
    test_mul_14    = test_op(Funct3.MUL,    0xffffffff, 0x80000000, result=0x80000000)

    test_mul_15    = test_op(Funct3.MUL,    0x7fffffff, 0x00000000, result=0x00000000)
    test_mul_16    = test_op(Funct3.MUL,    0x7fffffff, 0x00000001, result=0x7fffffff)
    test_mul_17    = test_op(Funct3.MUL,    0x7fffffff, 0xffffffff, result=0x80000001)
    test_mul_18    = test_op(Funct3.MUL,    0x7fffffff, 0x7fffffff, result=0x00000001)
    test_mul_19    = test_op(Funct3.MUL,    0x7fffffff, 0x80000000, result=0x80000000)

    test_mul_20    = test_op(Funct3.MUL,    0x80000000, 0x00000000, result=0x00000000)
    test_mul_21    = test_op(Funct3.MUL,    0x80000000, 0x00000001, result=0x80000000)
    test_mul_22    = test_op(Funct3.MUL,    0x80000000, 0xffffffff, result=0x80000000)
    test_mul_23    = test_op(Funct3.MUL,    0x80000000, 0x7fffffff, result=0x80000000)
    test_mul_24    = test_op(Funct3.MUL,    0x80000000, 0x80000000, result=0x00000000)

    # MULH ---------------------------------------------------------------------------

    test_mulh_0    = test_op(Funct3.MULH,   0x00000000, 0x00000000, result=0x00000000)
    test_mulh_1    = test_op(Funct3.MULH,   0x00000000, 0x00000001, result=0x00000000)
    test_mulh_2    = test_op(Funct3.MULH,   0x00000000, 0xffffffff, result=0x00000000)
    test_mulh_3    = test_op(Funct3.MULH,   0x00000000, 0x7fffffff, result=0x00000000)
    test_mulh_4    = test_op(Funct3.MULH,   0x00000000, 0x80000000, result=0x00000000)

    test_mulh_5    = test_op(Funct3.MULH,   0x00000001, 0x00000000, result=0x00000000)
    test_mulh_6    = test_op(Funct3.MULH,   0x00000001, 0x00000001, result=0x00000000)
    test_mulh_7    = test_op(Funct3.MULH,   0x00000001, 0xffffffff, result=0xffffffff)
    test_mulh_8    = test_op(Funct3.MULH,   0x00000001, 0x7fffffff, result=0x00000000)
    test_mulh_9    = test_op(Funct3.MULH,   0x00000001, 0x80000000, result=0xffffffff)

    test_mulh_10   = test_op(Funct3.MULH,   0xffffffff, 0x00000000, result=0x00000000)
    test_mulh_11   = test_op(Funct3.MULH,   0xffffffff, 0x00000001, result=0xffffffff)
    test_mulh_12   = test_op(Funct3.MULH,   0xffffffff, 0xffffffff, result=0x00000000)
    test_mulh_13   = test_op(Funct3.MULH,   0xffffffff, 0x7fffffff, result=0xffffffff)
    test_mulh_14   = test_op(Funct3.MULH,   0xffffffff, 0x80000000, result=0x00000000)

    test_mulh_15   = test_op(Funct3.MULH,   0x7fffffff, 0x00000000, result=0x00000000)
    test_mulh_16   = test_op(Funct3.MULH,   0x7fffffff, 0x00000001, result=0x00000000)
    test_mulh_17   = test_op(Funct3.MULH,   0x7fffffff, 0xffffffff, result=0xffffffff)
    test_mulh_18   = test_op(Funct3.MULH,   0x7fffffff, 0x7fffffff, result=0x3fffffff)
    test_mulh_19   = test_op(Funct3.MULH,   0x7fffffff, 0x80000000, result=0xc0000000)

    test_mulh_20   = test_op(Funct3.MULH,   0x80000000, 0x00000000, result=0x00000000)
    test_mulh_21   = test_op(Funct3.MULH,   0x80000000, 0x00000001, result=0xffffffff)
    test_mulh_22   = test_op(Funct3.MULH,   0x80000000, 0xffffffff, result=0x00000000)
    test_mulh_23   = test_op(Funct3.MULH,   0x80000000, 0x7fffffff, result=0xc0000000)
    test_mulh_24   = test_op(Funct3.MULH,   0x80000000, 0x80000000, result=0x40000000)

    # MULHSU -------------------------------------------------------------------------

    test_mulhsu_0  = test_op(Funct3.MULHSU, 0x00000000, 0x00000000, result=0x00000000)
    test_mulhsu_1  = test_op(Funct3.MULHSU, 0x00000000, 0x00000001, result=0x00000000)
    test_mulhsu_2  = test_op(Funct3.MULHSU, 0x00000000, 0xffffffff, result=0x00000000)
    test_mulhsu_3  = test_op(Funct3.MULHSU, 0x00000000, 0x7fffffff, result=0x00000000)
    test_mulhsu_4  = test_op(Funct3.MULHSU, 0x00000000, 0x80000000, result=0x00000000)

    test_mulhsu_5  = test_op(Funct3.MULHSU, 0x00000001, 0x00000000, result=0x00000000)
    test_mulhsu_6  = test_op(Funct3.MULHSU, 0x00000001, 0x00000001, result=0x00000000)
    test_mulhsu_7  = test_op(Funct3.MULHSU, 0x00000001, 0xffffffff, result=0x00000000)
    test_mulhsu_8  = test_op(Funct3.MULHSU, 0x00000001, 0x7fffffff, result=0x00000000)
    test_mulhsu_9  = test_op(Funct3.MULHSU, 0x00000001, 0x80000000, result=0x00000000)

    test_mulhsu_10 = test_op(Funct3.MULHSU, 0xffffffff, 0x00000000, result=0x00000000)
    test_mulhsu_11 = test_op(Funct3.MULHSU, 0xffffffff, 0x00000001, result=0xffffffff)
    test_mulhsu_12 = test_op(Funct3.MULHSU, 0xffffffff, 0xffffffff, result=0xffffffff)
    test_mulhsu_13 = test_op(Funct3.MULHSU, 0xffffffff, 0x7fffffff, result=0xffffffff)
    test_mulhsu_14 = test_op(Funct3.MULHSU, 0xffffffff, 0x80000000, result=0xffffffff)

    test_mulhsu_15 = test_op(Funct3.MULHSU, 0x7fffffff, 0x00000000, result=0x00000000)
    test_mulhsu_16 = test_op(Funct3.MULHSU, 0x7fffffff, 0x00000001, result=0x00000000)
    test_mulhsu_17 = test_op(Funct3.MULHSU, 0x7fffffff, 0xffffffff, result=0x7ffffffe)
    test_mulhsu_18 = test_op(Funct3.MULHSU, 0x7fffffff, 0x7fffffff, result=0x3fffffff)
    test_mulhsu_19 = test_op(Funct3.MULHSU, 0x7fffffff, 0x80000000, result=0x3fffffff)

    test_mulhsu_20 = test_op(Funct3.MULHSU, 0x80000000, 0x00000000, result=0x00000000)
    test_mulhsu_21 = test_op(Funct3.MULHSU, 0x80000000, 0x00000001, result=0xffffffff)
    test_mulhsu_22 = test_op(Funct3.MULHSU, 0x80000000, 0xffffffff, result=0x80000000)
    test_mulhsu_23 = test_op(Funct3.MULHSU, 0x80000000, 0x7fffffff, result=0xc0000000)
    test_mulhsu_24 = test_op(Funct3.MULHSU, 0x80000000, 0x80000000, result=0xc0000000)

    # MULHU --------------------------------------------------------------------------

    test_mulhu_0   = test_op(Funct3.MULHU,  0x00000000, 0x00000000, result=0x00000000)
    test_mulhu_1   = test_op(Funct3.MULHU,  0x00000000, 0x00000001, result=0x00000000)
    test_mulhu_2   = test_op(Funct3.MULHU,  0x00000000, 0xffffffff, result=0x00000000)
    test_mulhu_3   = test_op(Funct3.MULHU,  0x00000000, 0x7fffffff, result=0x00000000)
    test_mulhu_4   = test_op(Funct3.MULHU,  0x00000000, 0x80000000, result=0x00000000)

    test_mulhu_5   = test_op(Funct3.MULHU,  0x00000001, 0x00000000, result=0x00000000)
    test_mulhu_6   = test_op(Funct3.MULHU,  0x00000001, 0x00000001, result=0x00000000)
    test_mulhu_7   = test_op(Funct3.MULHU,  0x00000001, 0xffffffff, result=0x00000000)
    test_mulhu_8   = test_op(Funct3.MULHU,  0x00000001, 0x7fffffff, result=0x00000000)
    test_mulhu_9   = test_op(Funct3.MULHU,  0x00000001, 0x80000000, result=0x00000000)

    test_mulhu_10  = test_op(Funct3.MULHU,  0xffffffff, 0x00000000, result=0x00000000)
    test_mulhu_11  = test_op(Funct3.MULHU,  0xffffffff, 0x00000001, result=0x00000000)
    test_mulhu_12  = test_op(Funct3.MULHU,  0xffffffff, 0xffffffff, result=0xfffffffe)
    test_mulhu_13  = test_op(Funct3.MULHU,  0xffffffff, 0x7fffffff, result=0x7ffffffe)
    test_mulhu_14  = test_op(Funct3.MULHU,  0xffffffff, 0x80000000, result=0x7fffffff)

    test_mulhu_15  = test_op(Funct3.MULHU,  0x7fffffff, 0x00000000, result=0x00000000)
    test_mulhu_16  = test_op(Funct3.MULHU,  0x7fffffff, 0x00000001, result=0x00000000)
    test_mulhu_17  = test_op(Funct3.MULHU,  0x7fffffff, 0xffffffff, result=0x7ffffffe)
    test_mulhu_18  = test_op(Funct3.MULHU,  0x7fffffff, 0x7fffffff, result=0x3fffffff)
    test_mulhu_19  = test_op(Funct3.MULHU,  0x7fffffff, 0x80000000, result=0x3fffffff)

    test_mulhu_20  = test_op(Funct3.MULHU,  0x80000000, 0x00000000, result=0x00000000)
    test_mulhu_21  = test_op(Funct3.MULHU,  0x80000000, 0x00000001, result=0x00000000)
    test_mulhu_22  = test_op(Funct3.MULHU,  0x80000000, 0xffffffff, result=0x7fffffff)
    test_mulhu_23  = test_op(Funct3.MULHU,  0x80000000, 0x7fffffff, result=0x3fffffff)
    test_mulhu_24  = test_op(Funct3.MULHU,  0x80000000, 0x80000000, result=0x40000000)
