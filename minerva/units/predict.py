from nmigen import *


__all__ = ["BranchPredictor"]


class BranchPredictor(Elaboratable):
    def __init__(self):
        self.d_branch = Signal()
        self.d_jump = Signal()
        self.d_offset = Signal((32, True))
        self.d_pc = Signal(30)
        self.d_rs1_re = Signal()
        self.d_src1 = Signal(32)

        self.d_branch_taken = Signal()
        self.d_branch_target = Signal(32)

    def elaborate(self, platform):
        m = Module()

        with m.If(self.d_branch):
            # Backward conditional branches are predicted as taken.
            # Forward conditional branches are predicted as not taken.
            m.d.comb += self.d_branch_taken.eq(self.d_offset[-1])
        with m.Else():
            # Jumps are predicted as taken.
            # Other branch types (ie. exceptions) are not predicted.
            m.d.comb += self.d_branch_taken.eq(self.d_jump)

        with m.If(self.d_jump & self.d_rs1_re): # jalr
            m.d.comb += self.d_branch_target.eq((self.d_src1 + self.d_offset)[1:] << 1)
        with m.Else():
            m.d.comb += self.d_branch_target.eq((self.d_pc << 2) + self.d_offset)

        return m


