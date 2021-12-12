from amaranth import *


__all__ = ["ForwardingMemory"]


class ForwardingMemory(Elaboratable):
    """
    A memory with conflict resolution circuitry and transparent ("write-first") ports.

    Some BRAMs (such as those of Xilinx 7 Series FPGAs) are subject to undefined behaviour
    when a transparent port writes to an address that is being read by another port
    (cf. Xilinx UG473: "Conflict Avoidance", Table 1-4).
    To avoid this, this memory uses non-transparent ports internally. On an address collision,
    the write port data is forwarded to the read port.
    """
    def __init__(self, width, depth, init=None, name=None, attrs=None):
        self._mem  = Memory(width=width, depth=depth, init=init, name=name, attrs=attrs)
        self._rp   = []
        self._wp   = None

        self.width = self._mem.width
        self.depth = self._mem.depth
        self.attrs = self._mem.attrs
        self.init  = self._mem.init

    def read_port(self, *, src_loc_at=0):
        if len(self._rp) >= 2:
            raise AttributeError("ForwardingMemory {!r} cannot have more than two read ports, "
                                 "and both {!r} and {!r} have already been requested."
                                 .format(self, self._rp[0][1], self._rp[1][1]))

        mem_rp = self._mem.read_port(transparent=False)
        pub_rp = Record([
            ("addr", range(self.depth)),
            ("data", self.width),
        ], src_loc_at=1 + src_loc_at)

        self._rp.append((mem_rp, pub_rp))
        return pub_rp

    def write_port(self, *, granularity=None, src_loc_at=0):
        if self._wp is not None:
            raise AttributeError("ForwardingMemory {!r} cannot have more than one write port, "
                                 "and {!r} has already been requested."
                                 .format(self, self._wp[1]))

        mem_wp = self._mem.write_port(granularity=granularity)
        pub_wp = Record([
            ("addr", range(self.depth)),
            ("en",   int(self.width // mem_wp.granularity)),
            ("data", self.width),
        ], src_loc_at=1 + src_loc_at)

        self._wp = mem_wp, pub_wp
        return pub_wp

    def elaborate(self, platform):
        m = Module()

        for i, (mem_rp, pub_rp) in enumerate(self._rp, start=1):
            m.submodules[f"mem_rp{i}"] = mem_rp
            m.d.comb += [
                mem_rp.addr.eq(pub_rp.addr),
                mem_rp.en  .eq(Const(1)),
            ]

        if self._wp is not None:
            mem_wp, pub_wp = self._wp

            m.submodules.mem_wp = mem_wp
            m.d.comb += [
                mem_wp.addr.eq(pub_wp.addr),
                mem_wp.en  .eq(pub_wp.en),
                mem_wp.data.eq(pub_wp.data),
            ]

            collision   = Signal(len(self._rp))
            fwd_wp_en   = Signal.like(pub_wp.en)
            fwd_wp_data = Signal.like(pub_wp.data)

            m.d.sync += [
                fwd_wp_en  .eq(pub_wp.en),
                fwd_wp_data.eq(pub_wp.data),
            ]

            for i, (mem_rp, pub_rp) in enumerate(self._rp):
                m.d.sync += collision[i].eq(pub_wp.addr == pub_rp.addr)

                for j, forward in enumerate(fwd_wp_en):
                    pub_rp_word = pub_rp.data.word_select(j, mem_wp.granularity)
                    fwd_wp_word = fwd_wp_data.word_select(j, mem_wp.granularity)
                    mem_rp_word = mem_rp.data.word_select(j, mem_wp.granularity)

                    with m.If(collision[i] & forward):
                        m.d.comb += pub_rp_word.eq(fwd_wp_word)
                    with m.Else():
                        m.d.comb += pub_rp_word.eq(mem_rp_word)

        return m
