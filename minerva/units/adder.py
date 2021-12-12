from amaranth import *


__all__ = ["Adder"]


class Adder(Elaboratable):
    def __init__(self):
        self.d_sub      = Signal()
        self.d_stall    = Signal()
        self.x_src1     = Signal(32)
        self.x_src2     = Signal(32)

        self.x_result   = Signal(32)
        self.x_carry    = Signal()
        self.x_overflow = Signal()

    def elaborate(self, platform):
        m = Module()

        x_sub = Signal()

        with m.If(~self.d_stall):
            m.d.sync += x_sub.eq(self.d_sub)

        x_add_result   = Signal(32)
        x_add_carry    = Signal()
        x_add_overflow = Signal()

        m.d.comb += [
            Cat(x_add_result, x_add_carry).eq(self.x_src1 + self.x_src2),
            x_add_overflow.eq(~self.x_src1[-1] & self.x_src2[-1] & x_add_result[-1]),
        ]

        x_sub_result   = Signal(32)
        x_sub_carry    = Signal()
        x_sub_overflow = Signal()

        m.d.comb += [
            Cat(x_sub_result, x_sub_carry).eq(self.x_src1 - self.x_src2),
            x_sub_overflow.eq((self.x_src1[-1] != self.x_src2[-1]) & (x_sub_result[-1] == self.x_src2[-1])),
        ]

        with m.If(x_sub):
            m.d.comb += [
                self.x_result  .eq(x_sub_result),
                self.x_carry   .eq(x_sub_carry),
                self.x_overflow.eq(x_sub_overflow),
            ]
        with m.Else():
            m.d.comb += [
                self.x_result  .eq(x_add_result),
                self.x_carry   .eq(x_add_carry),
                self.x_overflow.eq(x_add_overflow),
            ]

        return m
