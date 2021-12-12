from amaranth import *

from ..isa import Funct3


__all__ = ["CompareUnit"]


class CompareUnit(Elaboratable):
    def __init__(self):
        self.op = Signal(3)
        self.zero = Signal()
        self.negative = Signal()
        self.overflow = Signal()
        self.carry = Signal()

        self.condition_met = Signal()

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
