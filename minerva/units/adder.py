from nmigen import *


__all__ = ["Adder"]


class _AddSub:
    def __init__(self):
        self.add = Signal()
        self.a = Signal(32)
        self.b = Signal(32)

        self.result = Signal(32)
        self.cout = Signal()

    def elaborate(self, platform):
        m = Module()

        add_ab = Signal(33)
        sub_ab = Signal(33)
        m.d.comb += [
            add_ab.eq(self.a + self.b),
            sub_ab.eq(self.a - self.b),
            self.result.eq(Mux(self.add, add_ab[:32], sub_ab[:32])),
            self.cout.eq(Mux(self.add, add_ab[32], sub_ab[32]))
        ]

        return m


class AdderUnit:
    def __init__(self):
        self.op = Signal()
        self.src1 = Signal(32)
        self.src2 = Signal(32)

        self.result = Signal(32)
        self.carry = Signal()
        self.overflow = Signal()

    def elaborate(self, platform):
        m = Module()

        overflow_add = Signal()
        overflow_sub = Signal()
        m.d.comb += [
            overflow_add.eq(~self.src1[-1] &  self.src2[-1] &  self.result[-1]),
            overflow_sub.eq( self.src1[-1] & ~self.src2[-1] & ~self.result[-1]),
            self.overflow.eq(overflow_add | overflow_sub)
        ]

        addsub = m.submodules.addsub = _AddSub()
        m.d.comb += [
            addsub.add.eq(~self.op),
            addsub.a.eq(self.src1),
            addsub.b.eq(self.src2),
            self.result.eq(addsub.result),
            self.carry.eq(addsub.cout)
        ]

        return m
