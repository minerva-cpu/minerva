from nmigen import *

from ..isa import Funct3


__all__ = ["Multiplier"]


class Multiplier(Elaboratable):
    def __init__(self):
        self.x_op     = Signal(3)
        self.x_src1   = Signal(32)
        self.x_src2   = Signal(32)
        self.x_stall  = Signal()

        self.m_result = Signal(32)

    def elaborate(self, platform):
        m = Module()

        x_low = Signal()
        x_src1_signed = Signal()
        x_src2_signed = Signal()

        with m.Switch(self.x_op):
            with m.Case(Funct3.MUL):
                m.d.comb += x_low.eq(1)
            with m.Case(Funct3.MULH):
                m.d.comb += x_src1_signed.eq(1), x_src2_signed.eq(1)
            with m.Case(Funct3.MULHSU):
                m.d.comb += x_src1_signed.eq(1)

        m_low = Signal()
        m_src1 = Signal((33, True))
        m_src2 = Signal((33, True))
        m_prod = Signal((66, True))

        with m.If(~self.x_stall):
            m.d.sync += [
                m_low.eq(x_low),
                m_src1.eq(Cat(self.x_src1, x_src1_signed & self.x_src1[31])),
                m_src2.eq(Cat(self.x_src2, x_src2_signed & self.x_src2[31]))
            ]

        m.d.comb += [
            m_prod.eq(m_src1 * m_src2),
            self.m_result.eq(Mux(m_low, m_prod[:32], m_prod[32:]))
        ]

        return m
