from nmigen import *


__all__ = ["File"]


class File(Elaboratable):
    def __init__(self, *, width, depth, init=None, name=None, attrs=None):
        self._mem  = Memory(width=width, depth=depth, init=init, name=name, attrs=attrs)
        self.width = self._mem.width
        self.depth = self._mem.depth
        self.attrs = self._mem.attrs
        self.init  = self._mem.init

        self.rp1 = Record([
            ("addr", range(depth)),
            ("data", width),
        ])
        self.rp2 = Record([
            ("addr", range(depth)),
            ("data", width),
        ])
        self.wp  = Record([
            ("addr", range(depth)),
            ("en",   1),
            ("data", width),
        ])

    def elaborate(self, platform):
        m = Module()

        # This register file exposes a 1W2R interface with transparent ("write-first") ports.
        #
        # Some BRAMs (such as those of Xilinx 7 Series FPGAs) are subject to undefined behaviour
        # when a transparent port writes to an address that is being read by another port
        # (cf. Xilinx UG473: "Conflict Avoidance", Table 1-4).
        # To avoid this, we use non-transparent ports internally. On an address collision, the
        # write port data is forwarded to the read port.

        m.submodules.mem_rp1 = mem_rp1 = self._mem.read_port(transparent=False)
        m.submodules.mem_rp2 = mem_rp2 = self._mem.read_port(transparent=False)
        m.submodules.mem_wp  = mem_wp  = self._mem.write_port()

        m.d.comb += [
            mem_rp1.addr.eq(self.rp1.addr),
            mem_rp1.en  .eq(Const(1)),

            mem_rp2.addr.eq(self.rp2.addr),
            mem_rp2.en  .eq(Const(1)),

            mem_wp.addr.eq(self.wp.addr),
            mem_wp.en  .eq(self.wp.en),
            mem_wp.data.eq(self.wp.data),
        ]

        collision = Signal(2)
        data_fwd  = Signal(self.width)
        m.d.sync += [
            collision[0].eq(self.wp.en & (self.wp.addr == self.rp1.addr)),
            collision[1].eq(self.wp.en & (self.wp.addr == self.rp2.addr)),
            data_fwd    .eq(self.wp.data),
        ]

        with m.If(collision[0]):
            m.d.comb += self.rp1.data.eq(data_fwd)
        with m.Else():
            m.d.comb += self.rp1.data.eq(mem_rp1.data)

        with m.If(collision[1]):
            m.d.comb += self.rp2.data.eq(data_fwd)
        with m.Else():
            m.d.comb += self.rp2.data.eq(mem_rp2.data)

        return m
