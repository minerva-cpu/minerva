from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ..isa import Funct3


__all__ = ["LogicUnit"]


class LogicUnit(wiring.Component):
    op:     In(3)
    src1:   In(32)
    src2:   In(32)
    result: Out(32)

    def elaborate(self, platform):
        m = Module()

        with m.Switch(self.op):
            with m.Case(Funct3.XOR):
                m.d.comb += self.result.eq(self.src1 ^ self.src2)
            with m.Case(Funct3.OR):
                m.d.comb += self.result.eq(self.src1 | self.src2)
            with m.Case(Funct3.AND):
                m.d.comb += self.result.eq(self.src1 & self.src2)

        return m
