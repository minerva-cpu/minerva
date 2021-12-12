from amaranth import *

from ..isa import Funct3


__all__ = ["MultiplierInterface", "Multiplier", "DummyMultiplier"]


class MultiplierInterface:
    def __init__(self):
        self.d_op     = Signal(3)
        self.d_stall  = Signal()
        self.x_src1   = Signal(32)
        self.x_src2   = Signal(32)
        self.x_stall  = Signal()
        self.m_stall  = Signal()

        self.w_result = Signal(32)


class Multiplier(MultiplierInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        d_low = Signal()
        d_src1_signed = Signal()
        d_src2_signed = Signal()

        m.d.comb += [
            d_low.eq(self.d_op == Funct3.MUL),
            d_src1_signed.eq((self.d_op == Funct3.MULH) | (self.d_op == Funct3.MULHSU)),
            d_src2_signed.eq(self.d_op == Funct3.MULH)
        ]

        x_low = Signal()
        x_src1_signed = Signal()
        x_src2_signed = Signal()

        with m.If(~self.d_stall):
            m.d.sync += [
                x_low.eq(d_low),
                x_src1_signed.eq(d_src1_signed),
                x_src2_signed.eq(d_src2_signed),
            ]

        x_src1 = Signal(signed(33))
        x_src2 = Signal(signed(33))
        x_prod = Signal(signed(66))

        m.d.comb += [
            x_src1.eq(Cat(self.x_src1, x_src1_signed & self.x_src1[31])),
            x_src2.eq(Cat(self.x_src2, x_src2_signed & self.x_src2[31])),
            x_prod.eq(x_src1 * x_src2),
        ]

        m_low = Signal()
        m_prod = Signal(signed(66))

        with m.If(~self.x_stall):
            m.d.sync += [
                m_low.eq(x_low),
                m_prod.eq(x_prod),
            ]

        m_result = Signal(32)

        with m.If(m_low):
            m.d.comb += m_result.eq(m_prod[:32])
        with m.Else():
            m.d.comb += m_result.eq(m_prod[32:])

        with m.If(~self.m_stall):
            m.d.sync += self.w_result.eq(m_result)

        return m


class DummyMultiplier(MultiplierInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        x_op = Signal.like(self.d_op)

        with m.If(~self.x_stall):
            m.d.sync += x_op.eq(self.d_op)

        x_result = Signal.like(self.w_result)
        m_result = Signal.like(self.w_result)

        with m.Switch(x_op):
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
