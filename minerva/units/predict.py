from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out


__all__ = ["BranchPredictor"]


class BranchPredictor(wiring.Component):
    d_branch:        In(1)
    d_jump:          In(1)
    d_offset:        In(signed(32))
    d_pc:            In(32)
    d_rs1_re:        In(1)
    d_branch_taken:  Out(1)
    d_branch_target: Out(32)

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
