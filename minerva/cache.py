from nmigen import *
from nmigen.asserts import *
from nmigen.lib.coding import Encoder
from nmigen.utils import log2_int


__all__ = ["L1Cache"]


class L1Cache(Elaboratable):
    def __init__(self, nways, nlines, nwords, base, limit):
        if not nlines or nlines & nlines-1:
            raise ValueError("nlines must be a power of 2, not {!r}".format(nlines))
        if nwords not in {4, 8, 16}:
            raise ValueError("nwords must be 4, 8 or 16, not {!r}".format(nwords))
        if nways not in {1, 2}:
            raise ValueError("nways must be 1 or 2, not {!r}".format(nways))

        self.nways = nways
        self.nlines = nlines
        self.nwords = nwords
        self.base = base
        self.limit = limit

        offsetbits = log2_int(nwords)
        linebits = log2_int(nlines)
        tagbits = log2_int(limit-base) - log2_int(nlines) - log2_int(nwords) - 2

        self.s1_addr = Record([("offset", offsetbits), ("line", linebits), ("tag", tagbits)])
        self.s1_flush = Signal()
        self.s1_stall = Signal()
        self.s1_valid = Signal()
        self.s2_addr = Record.like(self.s1_addr)
        self.s2_re = Signal()
        self.s2_evict = Signal()
        self.s2_valid = Signal()
        self.bus_valid = Signal()
        self.bus_error = Signal()
        self.bus_rdata = Signal(32)

        self.s2_miss = Signal()
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

        with m.FSM() as fsm:
            last_offset = Signal.like(self.s2_addr.offset)

            with m.State("CHECK"):
                with m.If(self.s2_re & self.s2_miss & self.s2_valid):
                    m.d.sync += [
                        self.bus_addr.eq(self.s2_addr),
                        self.bus_re.eq(1),
                        last_offset.eq(self.s2_addr.offset - 1)
                    ]
                    m.next = "REFILL"

            with m.State("REFILL"):
                m.d.comb += self.bus_last.eq(self.bus_addr.offset == last_offset)
                with m.If(self.bus_valid):
                    m.d.sync += self.bus_addr.offset.eq(self.bus_addr.offset + 1)
                with m.If(self.bus_valid & self.bus_last | self.bus_error):
                    m.d.sync += self.bus_re.eq(0)
                with m.If(~self.bus_re & ~self.s1_stall):
                    m.next = "CHECK"

        if platform == "formal":
            with m.If(Initial()):
                m.d.comb += Assume(fsm.ongoing("CHECK"))

        for way in ways:
            valid_lines = Signal(self.nlines)

            with m.If(self.s1_flush & self.s1_valid):
                m.d.sync += valid_lines.eq(0)
            with m.Elif(way.bus_re & self.bus_error):
                m.d.sync += valid_lines.bit_select(self.bus_addr.line, 1).eq(0)
            with m.Elif(way.bus_re & self.bus_valid & self.bus_last):
                m.d.sync += valid_lines.bit_select(self.bus_addr.line, 1).eq(1)
            with m.Elif(self.s2_evict & self.s2_valid & (way.tag == self.s2_addr.tag)):
                m.d.sync += valid_lines.bit_select(self.s2_addr.line, 1).eq(0)

            tag_mem = Memory(width=len(way.tag), depth=self.nlines)
            tag_rp = tag_mem.read_port()
            tag_wp = tag_mem.write_port()
            m.submodules += tag_rp, tag_wp

            data_mem = Memory(width=len(way.data), depth=self.nlines)
            data_rp = data_mem.read_port()
            data_wp = data_mem.write_port(granularity=32)
            m.submodules += data_rp, data_wp

            m.d.comb += [
                tag_rp.addr.eq(Mux(self.s1_stall, self.s2_addr.line, self.s1_addr.line)),
                data_rp.addr.eq(Mux(self.s1_stall, self.s2_addr.line, self.s1_addr.line)),

                tag_wp.addr.eq(self.bus_addr.line),
                tag_wp.en.eq(way.bus_re & self.bus_valid & self.bus_last),
                tag_wp.data.eq(self.bus_addr.tag),

                data_wp.addr.eq(self.bus_addr.line),
                data_wp.en.bit_select(self.bus_addr.offset, 1).eq(way.bus_re & self.bus_valid),
                data_wp.data.eq(self.bus_rdata << self.bus_addr.offset*32),

                way.valid.eq(valid_lines.bit_select(self.s2_addr.line, 1)),
                way.tag.eq(tag_rp.data),
                way.data.eq(data_rp.data)
            ]

            if platform == "formal":
                with m.If(Initial()):
                    m.d.comb += Assume(~valid_lines.bool())

        return m
