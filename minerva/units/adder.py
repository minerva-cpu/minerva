from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out


__all__ = ["Adder"]


class Adder(wiring.Component):
    d_sub:      In(1)
    d_ready:    In(1)

    x_src1:     In(32)
    x_src2:     In(32)
    x_result:   Out(32)
    x_carry:    Out(1)
    x_overflow: Out(1)

    def elaborate(self, platform):
        m = Module()

        x_sub = Signal()

        with m.If(self.d_ready):
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
