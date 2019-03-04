from nmigen import *

from ..isa import Funct3


__all__ = ["BranchPredictor", "BranchUnit"]


class BranchPredictor:
    def __init__(self):
        self.d_branch = Signal()
        self.d_jump = Signal()
        self.d_offset = Signal((32, True))
        self.d_pc = Signal(30)
        self.d_rs1_re = Signal()
        self.d_src1 = Signal(32)

        self.d_branch_predict_taken = Signal()
        self.d_branch_target = Signal(32)

    def elaborate(self, platform):
        m = Module()

        with m.If(self.d_branch):
            # Backward conditional branches are predicted as taken.
            # Forward conditional branches are predicted as not taken.
            m.d.comb += self.d_branch_predict_taken.eq(self.d_offset[-1])
        with m.Else():
            # Jumps are predicted as taken.
            # Other branch types (ie. exceptions) are not predicted.
            m.d.comb += self.d_branch_predict_taken.eq(self.d_jump)

        with m.If(self.d_jump & self.d_rs1_re): # jalr
            m.d.comb += self.d_branch_target.eq((self.d_src1 + self.d_offset)[1:] << 1)
        with m.Else():
            m.d.comb += self.d_branch_target.eq((self.d_pc << 2) + self.d_offset)

        return m


class BranchUnit:
    def __init__(self):
        self.condition = Signal(3)
        self.cmp_zero = Signal()
        self.cmp_negative = Signal()
        self.cmp_overflow = Signal()
        self.cmp_carry = Signal()

        self.condition_met = Signal()

    def elaborate(self, platform):
        m = Module()

        with m.Switch(self.condition):
            with m.Case(Funct3.BEQ):
                m.d.comb += self.condition_met.eq(self.cmp_zero)
            with m.Case(Funct3.BNE):
                m.d.comb += self.condition_met.eq(~self.cmp_zero)
            with m.Case(Funct3.BLT):
                m.d.comb += self.condition_met.eq(~self.cmp_zero & (self.cmp_negative != self.cmp_overflow))
            with m.Case(Funct3.BGE):
                m.d.comb += self.condition_met.eq(self.cmp_negative == self.cmp_overflow)
            with m.Case(Funct3.BLTU):
                m.d.comb += self.condition_met.eq(~self.cmp_zero & self.cmp_carry)
            with m.Case(Funct3.BGEU):
                m.d.comb += self.condition_met.eq(~self.cmp_carry)

        return m
