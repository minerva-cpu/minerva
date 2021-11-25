from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ..isa import Funct3


__all__ = ["CompareUnit"]


class CompareUnit(wiring.Component):
    op:            In(3)
    zero:          In(1)
    negative:      In(1)
    overflow:      In(1)
    carry:         In(1)
    condition_met: Out(1)

    def elaborate(self, platform):
        m = Module()

        with m.Switch(self.op):
            with m.Case(Funct3.BEQ):
                m.d.comb += self.condition_met.eq(self.zero)
            with m.Case(Funct3.BNE):
                m.d.comb += self.condition_met.eq(~self.zero)
            with m.Case(Funct3.BLT):
                m.d.comb += self.condition_met.eq(~self.zero & (self.negative != self.overflow))
            with m.Case(Funct3.BGE):
                m.d.comb += self.condition_met.eq(self.negative == self.overflow)
            with m.Case(Funct3.BLTU):
                m.d.comb += self.condition_met.eq(~self.zero & self.carry)
            with m.Case(Funct3.BGEU):
                m.d.comb += self.condition_met.eq(~self.carry)

        return m
