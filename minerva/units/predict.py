from nmigen import *


__all__ = ["BranchPredictor"]


class BranchPredictor(Elaboratable):
    def __init__(self):
        self.d_branch = Signal()
        self.d_jump = Signal()
        self.d_offset = Signal((32, True))
        self.d_pc = Signal(32)
        self.d_rs1_re = Signal()

        self.d_branch_taken = Signal()
        self.d_branch_target = Signal(32)

    def elaborate(self, platform):
        m = Module()

        d_fetch_misaligned = Signal()
        m.d.comb += [
            d_fetch_misaligned.eq(self.d_pc[:2].bool() | self.d_offset[:2].bool()),
            self.d_branch_target.eq(self.d_pc + self.d_offset),
        ]

        with m.If(d_fetch_misaligned):
            m.d.comb += self.d_branch_taken.eq(0)
        with m.Elif(self.d_branch):
            # Backward conditional branches are predicted as taken.
            # Forward conditional branches are predicted as not taken.
            m.d.comb += self.d_branch_taken.eq(self.d_offset[-1])
        with m.Else():
            # Direct jumps are predicted as taken.
            # Other branch types (ie. indirect jumps, exceptions) are not predicted.
            m.d.comb += self.d_branch_taken.eq(self.d_jump & ~self.d_rs1_re)

        return m
