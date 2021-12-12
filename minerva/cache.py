from amaranth import *
from amaranth.asserts import *
from amaranth.lib.coding import Encoder
from amaranth.utils import log2_int, bits_for

from .mem import ForwardingMemory


__all__ = ["L1Cache"]


class L1Cache(Elaboratable):
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

        self.nways = nways
        self.nlines = nlines
        self.nwords = nwords
        self.base = base
        self.limit = limit

        offsetbits = log2_int(nwords)
        linebits = log2_int(nlines)
        tagbits = bits_for(limit) - linebits - offsetbits - 2

        self.s1_addr = Record([("offset", offsetbits), ("line", linebits), ("tag", tagbits)])
        self.s1_stall = Signal()
        self.s1_valid = Signal()
        self.s2_addr = Record.like(self.s1_addr)
        self.s2_re = Signal()
        self.s2_flush = Signal()
        self.s2_evict = Signal()
        self.s2_valid = Signal()
        self.bus_valid = Signal()
        self.bus_error = Signal()
        self.bus_rdata = Signal(32)

        self.s2_miss = Signal()
        self.s2_flush_ack = Signal()
        self.s2_rdata = Signal(32)
        self.bus_re = Signal()
        self.bus_addr = Record.like(self.s1_addr)
        self.bus_last = Signal()

    def elaborate(self, platform):
        m = Module()

        ways = Array(Record([("data",   self.nwords * 32),
                             ("tag",    self.s2_addr.tag.shape()),
                             ("valid",  1),
                             ("bus_re", 1)])
                     for _ in range(self.nways))

        if self.nways == 1:
            way_lru = Const(0)
        elif self.nways == 2:
            way_lru = Signal()
            with m.If(self.bus_re & self.bus_valid & self.bus_last & ~self.bus_error):
                m.d.sync += way_lru.eq(~way_lru)

        m.d.comb += ways[way_lru].bus_re.eq(self.bus_re)

        way_hit = m.submodules.way_hit = Encoder(self.nways)
        for j, way in enumerate(ways):
            m.d.comb += way_hit.i[j].eq((way.tag == self.s2_addr.tag) & way.valid)

        m.d.comb += [
            self.s2_miss.eq(way_hit.n),
            self.s2_rdata.eq(ways[way_hit.o].data.word_select(self.s2_addr.offset, 32))
        ]

        flush_line = Signal(range(self.nlines), reset=self.nlines - 1)
        with m.If(self.s1_valid & ~self.s1_stall):
            m.d.sync += self.s2_flush_ack.eq(0)

        with m.FSM() as fsm:
            last_offset = Signal.like(self.s2_addr.offset)

            with m.State("CHECK"):
                with m.If(self.s2_valid):
                    with m.If(self.s2_flush & ~self.s2_flush_ack):
                        m.d.sync += flush_line.eq(flush_line.reset)
                        m.next = "FLUSH"
                    with m.Elif(self.s2_re & self.s2_miss):
                        m.d.sync += [
                            self.bus_addr.eq(self.s2_addr),
                            self.bus_re.eq(1),
                            last_offset.eq(self.s2_addr.offset - 1)
                        ]
                        m.next = "REFILL"

            with m.State("REFILL"):
                m.d.comb += self.bus_last.eq(self.bus_addr.offset == last_offset)
                with m.If(~self.s1_stall):
                    m.d.sync += self.bus_re.eq(0)
                    m.next = "CHECK"
                with m.Else():
                    with m.If(self.bus_valid):
                        m.d.sync += self.bus_addr.offset.eq(self.bus_addr.offset + 1)
                    with m.If(self.bus_valid & self.bus_last | self.bus_error):
                        m.d.sync += self.bus_re.eq(0)

            with m.State("FLUSH"):
                with m.If(flush_line == 0):
                    m.d.sync += self.s2_flush_ack.eq(1)
                    m.next = "CHECK"
                with m.Else():
                    m.d.sync += flush_line.eq(flush_line - 1)

        if platform == "formal":
            with m.If(Initial()):
                m.d.comb += Assume(fsm.ongoing("CHECK"))

        for i, way in enumerate(ways):
            tag_mem    = ForwardingMemory(width=1 + len(way.tag), depth=self.nlines)
            tag_mem_rp = tag_mem.read_port()
            tag_mem_wp = tag_mem.write_port()
            m.submodules[f"tag_mem_{i}"] = tag_mem

            dat_mem    = ForwardingMemory(width=len(way.data), depth=self.nlines)
            dat_mem_rp = dat_mem.read_port()
            dat_mem_wp = dat_mem.write_port(granularity=32)
            m.submodules[f"dat_mem_{i}"] = dat_mem

            mem_rp_addr = Signal.like(self.s1_addr.line)
            with m.If(self.s1_stall):
                m.d.comb += mem_rp_addr.eq(self.s2_addr.line)
            with m.Else():
                m.d.comb += mem_rp_addr.eq(self.s1_addr.line)

            m.d.comb += [
                tag_mem_rp.addr.eq(mem_rp_addr),
                dat_mem_rp.addr.eq(mem_rp_addr),
                Cat(way.tag, way.valid).eq(tag_mem_rp.data),
                way.data.eq(dat_mem_rp.data),
            ]

            with m.If(fsm.ongoing("FLUSH")):
                m.d.comb += [
                    tag_mem_wp.addr.eq(flush_line),
                    tag_mem_wp.en.eq(1),
                    tag_mem_wp.data.eq(0),
                ]
            with m.Elif(way.bus_re):
                m.d.comb += [
                    tag_mem_wp.addr.eq(self.bus_addr.line),
                    tag_mem_wp.en.eq(way.bus_re & self.bus_valid),
                    tag_mem_wp.data.eq(Cat(self.bus_addr.tag, self.bus_last & ~self.bus_error)),
                ]
            with m.Else():
                m.d.comb += [
                    tag_mem_wp.addr.eq(self.s2_addr.line),
                    tag_mem_wp.en.eq(self.s2_evict & self.s2_valid & (way.tag == self.s2_addr.tag)),
                    tag_mem_wp.data.eq(0),
                ]

            m.d.comb += [
                dat_mem_wp.addr.eq(self.bus_addr.line),
                dat_mem_wp.en.bit_select(self.bus_addr.offset, 1).eq(way.bus_re & self.bus_valid),
                dat_mem_wp.data.eq(Repl(self.bus_rdata, self.nwords)),
            ]

        return m
