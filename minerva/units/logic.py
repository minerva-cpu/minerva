from nmigen import *

from ..isa import Funct3


__all__ = ["LogicUnit"]


class LogicUnit(Elaboratable):
    def __init__(self):
        self.op = Signal(3)
        self.src1 = Signal(32)
        self.src2 = Signal(32)

        self.result = Signal(32)

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
