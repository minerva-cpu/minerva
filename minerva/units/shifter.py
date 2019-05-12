from nmigen import *


__all__ = ["Shifter"]


class Shifter(Elaboratable):
    def __init__(self):
        self.x_direction = Signal()
        self.x_sext = Signal()
        self.x_shamt = Signal(5)
        self.x_src1 = Signal(32)
        self.x_stall = Signal()

        self.m_result = Signal(32)

    def elaborate(self, platform):
        m = Module()

        x_operand = Signal(32)
        x_filler = Signal()
        m_direction = Signal()
        m_result = Signal(32)

        m.d.comb += [
            # left shifts are equivalent to right shifts with reversed bits
            x_operand.eq(Mux(self.x_direction, self.x_src1, self.x_src1[::-1])),
            x_filler.eq(Mux(self.x_direction & self.x_sext, self.x_src1[-1], 0))
        ]

        with m.If(~self.x_stall):
            m.d.sync += [
                m_direction.eq(self.x_direction),
                m_result.eq(Cat(x_operand, Repl(x_filler, 32)) >> self.x_shamt)
            ]

        m.d.comb += self.m_result.eq(Mux(m_direction, m_result, m_result[::-1]))

        return m
