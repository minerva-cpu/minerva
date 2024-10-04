from amaranth import *
from amaranth.asserts import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib.data import StructLayout, ArrayLayout
from amaranth.lib.memory import *
from amaranth.utils import exact_log2


__all__ = ["L1Cache"]


class _L1CacheWay(Elaboratable):
    def __init__(self, cache):
        self._tag_mem = Memory(shape=StructLayout({"tag": cache.s1_addr.tag.shape(), "valid": 1}),
                               depth=cache.nlines,
                               init=[{"tag": 0, "valid": 0}] * cache.nlines)
        self._dat_mem = Memory(shape=unsigned(32),
                               depth=cache.nlines * cache.nwords,
                               init=[0] * cache.nlines * cache.nwords)

        self.tag_rp = self._tag_mem.read_port()
        self.tag_wp = self._tag_mem.write_port()
        self.dat_rp = self._dat_mem.read_port()
        self.dat_wp = self._dat_mem.write_port()

    def elaborate(self, platform):
        m = Module()
        m.submodules.tag_mem = self._tag_mem
        m.submodules.dat_mem = self._dat_mem
        return m


class L1Cache(wiring.Component):
    def __init__(self, nways, nlines, nwords, base, limit):
        if not isinstance(nlines, int):
            raise TypeError("nlines must be an integer, not {!r}".format(nlines))
        if nlines == 0 or nlines & nlines - 1:
            raise ValueError("nlines must be a power of 2, not {}".format(nlines))
        if nwords not in {4, 8, 16}:
            raise ValueError("nwords must be 4, 8 or 16, not {!r}".format(nwords))
        if nways not in {1, 2}:
            raise ValueError("nways must be 1 or 2, not {!r}".format(nways))

        if not isinstance(base, int) or base not in range(0, 2**32):
            raise ValueError("base must be an integer between {:#x} and {:#x} inclusive, not {!r}"
                             .format(0, 2**32-1, base))
        if limit not in range(0, 2**32):
            raise ValueError("limit must be an integer between {:#x} and {:#x} inclusive, not {!r}"
                             .format(0, 2**32-1, limit))

        if base >= limit:
            raise ValueError("limit {:#x} must be greater than base {:#x}"
                             .format(limit, base))
        if (limit - base) & (limit - base) - 1:
            raise ValueError("limit - base must be a power of 2, not {:#x}"
                             .format(limit - base))
        if base % (limit - base):
            raise ValueError("base must be a multiple of limit - base, but {:#x} is not a multiple "
                             "of {:#x}"
                             .format(base, limit - base))

        self.nways  = nways
        self.nlines = nlines
        self.nwords = nwords
        self.base   = base  >> 2
        self.limit  = limit >> 2

        wordbits = exact_log2(nwords)
        linebits = exact_log2(nlines)
        tagbits  = exact_log2(self.limit - self.base) - linebits - wordbits

        addr_layout = StructLayout({
            "word": wordbits,
            "line": linebits,
            "tag":  tagbits,
        })

        super().__init__({
            "s1_addr":  In(addr_layout),
            "s1_ready": In(1),

            "s2_addr":  In(addr_layout),
            "s2_op":    In(StructLayout({"read": 1, "flush": 1, "evict": 1})),
            "s2_valid": In(1),
            "s2_busy":  Out(1, init=1),
            "s2_data":  Out(32),

            "bus_addr": Out(addr_layout),
            "bus_req":  Out(1),
            "bus_last": Out(1),
            "bus_ack":  In(1),
            "bus_data": In(32),
        })

        self._ways = tuple(_L1CacheWay(self) for _ in range(nways))

    def elaborate(self, platform):
        m = Module()

        mem_rp_addr = Signal(StructLayout({"word": self.s1_addr.word.shape(),
                                           "line": self.s1_addr.line.shape()}))
        mem_rp_addr_saved = Signal.like(mem_rp_addr)

        with m.If(self.s1_ready):
            m.d.comb += mem_rp_addr.eq(Cat(self.s1_addr.word, self.s1_addr.line))
            m.d.sync += mem_rp_addr_saved.eq(mem_rp_addr)
        with m.Else():
            m.d.comb += mem_rp_addr.eq(mem_rp_addr_saved)

        way_hit = Signal(len(self._ways))
        way_lru = Signal(range(len(self._ways)))

        for i, way in enumerate(self._ways):
            m.submodules[f"way_{i}"] = way
            m.d.comb += [
                way.tag_rp.addr.eq(mem_rp_addr.line),
                way.dat_rp.addr.eq(mem_rp_addr),
                way_hit[i].eq(way.tag_rp.data.valid & (way.tag_rp.data.tag == self.s2_addr.tag)),
            ]

        if len(self._ways) == 1:
            m.d.comb += self.s2_data.eq(self._ways[0].dat_rp.data)
        if len(self._ways) == 2:
            s2_data_mux  = Mux(way_hit[0], self._ways[0].dat_rp.data, 0)
            s2_data_mux |= Mux(way_hit[1], self._ways[1].dat_rp.data, 0)
            m.d.comb += self.s2_data.eq(s2_data_mux)

        flush_line = Signal(range(self.nlines), init=self.nlines - 1)
        flush_done = Signal()

        with m.If(self.s1_ready):
            m.d.sync += flush_line.eq(flush_line.init)

        m.d.comb += flush_done.eq(flush_line == 0)

        with m.FSM() as fsm:
            with m.State("CHECK"):
                with m.If(self.s2_op.flush & self.s2_valid & ~flush_done):
                    m.next = "FLUSH"
                with m.Elif(self.s2_op.evict & self.s2_valid & way_hit.any()):
                    m.next = "EVICT"
                with m.Elif(self.s2_op.read & self.s2_valid & ~way_hit.any()):
                    m.d.sync += [
                        self.bus_addr.word.eq(0),
                        self.bus_addr.line.eq(self.s2_addr.line),
                        self.bus_addr.tag .eq(self.s2_addr.tag),
                    ]
                    m.next = "REFILL"
                with m.Else():
                    m.d.comb += self.s2_busy.eq(0)

            with m.State("FLUSH"):
                for way in self._ways:
                    m.d.comb += [
                        way.tag_wp.addr.eq(flush_line),
                        way.tag_wp.en  .eq(1),
                        way.tag_wp.data.eq(0),
                    ]
                with m.If(flush_done):
                    m.next = "DONE"
                with m.Else():
                    m.d.sync += flush_line.eq(flush_line - 1)

            with m.State("EVICT"):
                for i, way in enumerate(self._ways):
                    m.d.comb += [
                        way.tag_wp.addr.eq(mem_rp_addr.line),
                        way.tag_wp.en  .eq(way_hit[i]),
                        way.tag_wp.data.eq(0),
                    ]
                m.next = "DONE"

            with m.State("REFILL"):
                m.d.comb += [
                    self.bus_req .eq(1),
                    self.bus_last.eq(self.bus_addr.word == Const(self.nwords - 1)),
                ]
                for i, way in enumerate(self._ways):
                    m.d.comb += [
                        way.tag_wp.addr.eq(self.bus_addr.line),
                        way.tag_wp.en  .eq(self.bus_ack & (way_lru == i)),
                        way.tag_wp.data.eq(Cat(self.bus_addr.tag, self.bus_last)),
                        way.dat_wp.addr.eq(Cat(self.bus_addr.word, self.bus_addr.line)),
                        way.dat_wp.en  .eq(self.bus_ack & (way_lru == i)),
                        way.dat_wp.data.eq(self.bus_data),
                    ]
                    with m.If(self.bus_ack):
                        with m.If(self.bus_last):
                            m.d.sync += way_lru.eq(~way_lru)
                            m.next = "DONE"
                        with m.Else():
                            m.d.sync += self.bus_addr.word.eq(self.bus_addr.word + 1)

            with m.State("DONE"):
                m.next = "CHECK"

        if platform == "formal":
            with m.If(Initial()):
                m.d.comb += Assume(fsm.ongoing("CHECK"))

        return m
