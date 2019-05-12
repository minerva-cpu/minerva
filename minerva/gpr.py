from nmigen import *

from .reg import *


__all__ = ["GPRFile"]


_gpr_names = [
    "zero",
    "ra",
    "sp",
    "gp",
    "tp",
    *(f"t{i}" for i in range(3)),
    "fp",
    "s1",
    *(f"a{i}" for i in range(8)),
    *(f"s{i}" for i in range(2, 12)),
    *(f"t{i}" for i in range(3, 7))
]


class GPRFile(RegisterFileBase, Elaboratable):
    def __init__(self):
        super().__init__(None, 32, 32)

    def elaborate(self, platform):
        m = Module()
        regs = Array(Signal(self.width, name=_gpr_names[i]) for i in range(self.depth))

        for rp in self._read_ports:
            with m.If(rp.en):
                m.d.comb += rp.data.eq(regs[rp.addr])

        for wp in self._write_ports:
            with m.If(wp.en):
                m.d.sync += regs[wp.addr].eq(wp.data)

        return m
