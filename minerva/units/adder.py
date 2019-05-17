from nmigen import *


__all__ = ["Adder"]


class Adder(Elaboratable):
    def __init__(self):
        self.sub = Signal()
        self.src1 = Signal(32)
        self.src2 = Signal(32)

        self.result = Signal(32)
        self.carry = Signal()
        self.overflow = Signal()

    def elaborate(self, platform):
        m = Module()

        with m.If(self.sub):
            m.d.comb += [
                Cat(self.result, self.carry).eq(self.src1 - self.src2),
                self.overflow.eq((self.src1[-1] != self.src2[-1]) & (self.result[-1] == self.src2[-1]))
            ]
        with m.Else():
            m.d.comb += [
                Cat(self.result, self.carry).eq(self.src1 + self.src2),
                self.overflow.eq(~self.src1[-1] & self.src2[-1] & self.result[-1])
            ]

        return m
