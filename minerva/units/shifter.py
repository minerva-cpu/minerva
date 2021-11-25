from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out


__all__ = ["Shifter"]


class Shifter(wiring.Component):
    x_direction: In(1)
    x_sext:      In(1)
    x_shamt:     In(5)
    x_src1:      In(32)
    x_ready:     In(1)

    m_result:    Out(32)

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

        with m.If(self.x_ready):
            m.d.sync += [
                m_direction.eq(self.x_direction),
                m_result.eq(Cat(x_operand, x_filler.replicate(32)) >> self.x_shamt)
            ]

        m.d.comb += self.m_result.eq(Mux(m_direction, m_result, m_result[::-1]))

        return m
