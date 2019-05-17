from nmigen import *

from ..isa import Funct3


__all__ = ["Multiplier"]


class Multiplier(Elaboratable):
    def __init__(self):
        self.x_op     = Signal(3)
        self.x_src1   = Signal(32)
        self.x_src2   = Signal(32)
        self.x_stall  = Signal()
        self.m_stall  = Signal()

        self.w_result = Signal(32)

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

        x_src1 = Signal((33, True))
        x_src2 = Signal((33, True))

        m.d.comb += [
            x_src1.eq(Cat(self.x_src1, x_src1_signed & self.x_src1[31])),
            x_src2.eq(Cat(self.x_src2, x_src2_signed & self.x_src2[31]))
        ]

        m_low = Signal()
        m_prod = Signal((66, True))

        with m.If(~self.x_stall):
            m.d.sync += [
                m_low.eq(x_low),
                m_prod.eq(x_src1 * x_src2)
            ]

        with m.If(~self.m_stall):
            m.d.sync += self.w_result.eq(Mux(m_low, m_prod[:32], m_prod[32:]))

        return m
