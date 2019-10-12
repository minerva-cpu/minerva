from nmigen import *

from ..isa import Funct3


__all__ = ["MultiplierInterface", "Multiplier", "DummyMultiplier"]


class MultiplierInterface:
    def __init__(self):
        self.x_op     = Signal(3)
        self.x_src1   = Signal(32)
        self.x_src2   = Signal(32)
        self.x_stall  = Signal()
        self.m_stall  = Signal()

        self.w_result = Signal(32)


class Multiplier(MultiplierInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        x_low = Signal()
        x_src1_signed = Signal()
        x_src2_signed = Signal()

        m.d.comb += [
            x_low.eq(self.x_op == Funct3.MUL),
            x_src1_signed.eq((self.x_op == Funct3.MULH) | (self.x_op == Funct3.MULHSU)),
            x_src2_signed.eq(self.x_op == Funct3.MULH)
        ]

        x_src1 = Signal(signed(33))
        x_src2 = Signal(signed(33))

        m.d.comb += [
            x_src1.eq(Cat(self.x_src1, x_src1_signed & self.x_src1[31])),
            x_src2.eq(Cat(self.x_src2, x_src2_signed & self.x_src2[31]))
        ]

        m_low = Signal()
        m_prod = Signal(signed(66))

        with m.If(~self.x_stall):
            m.d.sync += [
                m_low.eq(x_low),
                m_prod.eq(x_src1 * x_src2)
            ]

        with m.If(~self.m_stall):
            m.d.sync += self.w_result.eq(Mux(m_low, m_prod[:32], m_prod[32:]))

        return m


class DummyMultiplier(MultiplierInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        x_result = Signal.like(self.w_result)
        m_result = Signal.like(self.w_result)

        with m.Switch(self.x_op):
            # As per the RVFI specification (§ "Alternative Arithmetic Operations").
            # https://github.com/SymbioticEDA/riscv-formal/blob/master/docs/rvfi.md
            with m.Case(Funct3.MUL):
                m.d.comb += x_result.eq((self.x_src1 + self.x_src2) ^ C(0x5876063e))
            with m.Case(Funct3.MULH):
                m.d.comb += x_result.eq((self.x_src1 + self.x_src2) ^ C(0xf6583fb7))
            with m.Case(Funct3.MULHSU):
                m.d.comb += x_result.eq((self.x_src1 - self.x_src2) ^ C(0xecfbe137))
            with m.Case(Funct3.MULHU):
                m.d.comb += x_result.eq((self.x_src1 + self.x_src2) ^ C(0x949ce5e8))

        with m.If(~self.x_stall):
            m.d.sync += m_result.eq(x_result)
        with m.If(~self.m_stall):
            m.d.sync += self.w_result.eq(m_result)

        return m
