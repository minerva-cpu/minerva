from amaranth import *

from ..isa import Funct3


__all__ = ["DividerInterface", "Divider", "DummyDivider"]


class DividerInterface:
    def __init__(self):
        self.x_op     = Signal(3)
        self.x_src1   = Signal(32)
        self.x_src2   = Signal(32)
        self.x_valid  = Signal()
        self.x_stall  = Signal()

        self.m_result = Signal(32)
        self.m_busy   = Signal()


class Divider(DividerInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        x_enable  = Signal()
        x_modulus = Signal()
        x_signed  = Signal()

        with m.Switch(self.x_op):
            with m.Case(Funct3.DIV):
                m.d.comb += x_enable.eq(1), x_signed.eq(1)
            with m.Case(Funct3.DIVU):
                m.d.comb += x_enable.eq(1)
            with m.Case(Funct3.REM):
                m.d.comb += x_enable.eq(1), x_modulus.eq(1), x_signed.eq(1)
            with m.Case(Funct3.REMU):
                m.d.comb += x_enable.eq(1), x_modulus.eq(1)

        x_negative = Signal()
        with m.If(x_modulus):
            m.d.comb += x_negative.eq(x_signed & self.x_src1[31])
        with m.Else():
            m.d.comb += x_negative.eq(x_signed & (self.x_src1[31] ^ self.x_src2[31]))

        x_dividend = Signal(32)
        x_divisor  = Signal(32)
        m.d.comb += [
            x_dividend.eq(Mux(x_signed & self.x_src1[31], -self.x_src1, self.x_src1)),
            x_divisor.eq(Mux(x_signed & self.x_src2[31], -self.x_src2, self.x_src2))
        ]

        m_modulus  = Signal()
        m_negative = Signal()

        timer      = Signal(range(33), reset=32)
        quotient   = Signal(32)
        divisor    = Signal(32)
        remainder  = Signal(32)
        difference = Signal(33)

        with m.FSM() as fsm:
            with m.State("IDLE"):
                with m.If(x_enable & self.x_valid & ~self.x_stall):
                    m.d.sync += [
                        m_modulus.eq(x_modulus),
                        m_negative.eq(x_negative)
                    ]
                    with m.If(x_divisor == 0):
                        # Division by zero
                        m.d.sync += [
                            quotient.eq(-1),
                            remainder.eq(self.x_src1)
                        ]
                    with m.Elif(x_signed & (self.x_src1 == -2**31) & (self.x_src2 == -1)):
                        # Signed overflow
                        m.d.sync += [
                            quotient.eq(self.x_src1),
                            remainder.eq(0)
                        ]
                    with m.Elif(x_dividend == 0):
                        m.d.sync += [
                            quotient.eq(0),
                            remainder.eq(0)
                        ]
                    with m.Else():
                        m.d.sync += [
                            quotient.eq(x_dividend),
                            remainder.eq(0),
                            divisor.eq(x_divisor),
                            timer.eq(timer.reset)
                        ]
                        m.next = "DIVIDE"

            with m.State("DIVIDE"):
                m.d.comb += self.m_busy.eq(1)
                with m.If(timer != 0):
                    m.d.sync += timer.eq(timer - 1)
                    m.d.comb += difference.eq(Cat(quotient[31], remainder) - divisor)
                    with m.If(difference[32]):
                        m.d.sync += [
                            remainder.eq(Cat(quotient[31], remainder)),
                            quotient.eq(Cat(0, quotient))
                        ]
                    with m.Else():
                        m.d.sync += [
                            remainder.eq(difference),
                            quotient.eq(Cat(1, quotient))
                        ]
                with m.Else():
                    m.d.sync += [
                        quotient.eq(Mux(m_negative, -quotient, quotient)),
                        remainder.eq(Mux(m_negative, -remainder, remainder))
                    ]
                    m.next = "IDLE"

        m.d.comb += self.m_result.eq(Mux(m_modulus, remainder, quotient))

        return m


class DummyDivider(DividerInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        x_result = Signal.like(self.m_result)

        with m.Switch(self.x_op):
            # As per the RVFI specification (§ "Alternative Arithmetic Operations").
            # https://github.com/SymbioticEDA/riscv-formal/blob/master/docs/rvfi.md
            with m.Case(Funct3.DIV):
                m.d.comb += x_result.eq((self.x_src1 - self.x_src2) ^ C(0x7f8529ec))
            with m.Case(Funct3.DIVU):
                m.d.comb += x_result.eq((self.x_src1 - self.x_src2) ^ C(0x10e8fd70))
            with m.Case(Funct3.REM):
                m.d.comb += x_result.eq((self.x_src1 - self.x_src2) ^ C(0x8da68fa5))
            with m.Case(Funct3.REMU):
                m.d.comb += x_result.eq((self.x_src1 - self.x_src2) ^ C(0x3138d0e1))

        with m.If(~self.x_stall):
            m.d.sync += self.m_result.eq(x_result)

        m.d.comb += self.m_busy.eq(C(0))

        return m
