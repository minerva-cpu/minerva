from operator import and_

from nmigen import *
from nmigen.lib.coding import Encoder
from nmigen.tools import log2_int


__all__ = ["L1Cache"]


def split(v, *counts):
    r = []
    offset = 0
    for n in counts:
        if n != 0:
            r.append(v[offset:offset+n])
        else:
            r.append(None)
        offset += n
    return tuple(r)


def displacer(signal, shift, output, n=None, reverse=False):
    if shift is None:
        return output.eq(signal)
    if n is None:
        n = 2**len(shift)
    w = len(signal)
    if reverse:
        r = reversed(range(n))
    else:
        r = range(n)
    l = [Repl(shift == i, w) & signal for i in r]
    return output.eq(Cat(*l))


class L1Cache(Module):
    def __init__(self, nb_ways, nb_lines, nb_words, base, limit):
        if nb_ways not in {1, 2}:
            raise ValueError
        if not nb_lines or nb_lines & nb_lines-1:
            raise ValueError("nb_lines must be a power of two")
        if nb_words not in {4, 8, 16}:
            raise ValueError

        self.nb_ways = nb_ways
        self.nb_lines = nb_lines
        self.nb_words = nb_words
        self.base = base
        self.limit = limit

        self.s1_address = Signal(30)
        self.s1_stall = Signal()
        self.s2_address = Signal(30)
        self.s2_stall = Signal()
        self.s2_re = Signal()
        self.s2_we = Signal()
        self.s2_sel = Signal(4)
        self.s2_dat_w = Signal(32)
        self.refill_address = Signal(30)
        self.refill_ready = Signal()
        self.refill_valid = Signal()
        self.refill_data = Signal(32)
        self.last_refill = Signal()
        self.flush = Signal()

        self.stall_request = Signal()
        self.refill_request = Signal()
        self.s2_dat_r = Signal(32)

    @property
    def offsetbits(self):
        return log2_int(self.nb_words)

    @property
    def linebits(self):
        return log2_int(self.nb_lines) - self.offsetbits

    @property
    def tagbits(self):
        wordbits = log2_int(32//8)
        addressbits = log2_int(self.limit - self.base)
        return addressbits - (wordbits + self.offsetbits + self.linebits)

    def elaborate(self, platform):
        m = Module()

        def split_adr(adr):
            return split(adr, self.offsetbits, self.linebits, self.tagbits)

        s1_offset, s1_line, s1_tag = split_adr(self.s1_address)
        s2_offset, s2_line, s2_tag = split_adr(self.s2_address)
        refill_offset, refill_line, refill_tag = split_adr(self.refill_address)

        tag_layout = [("value", self.tagbits), ("valid", 1)]
        way_layout = [("data", 32), ("tag", tag_layout), ("enable", 1)]
        ways = Array(Record(way_layout) for _ in range(self.nb_ways))

        refilling = Signal()
        refill_status = Array(Signal() for _ in range(self.nb_words))

        refill_lru = Signal()
        if self.nb_ways == 1:
            m.d.comb += refill_lru.eq(0)
        else:
            # TODO: Implement a scalable pseudo-LRU refill policy.
            assert self.nb_ways == 2
            with m.If(self.refill_request):
                m.d.sync += refill_lru.eq(~refill_lru)
        m.d.comb += ways[refill_lru].enable.eq(1)

        flushing = Signal()
        flush_line = Signal(self.linebits, reset=2**self.linebits-1)

        flush_stall = Signal()
        refill_stall = Signal()
        m.d.comb += self.stall_request.eq(flush_stall | refill_stall)

        latch_s1_line = Signal.like(s1_line)
        latch_s1_line_no_stall = Signal.like(s1_line)
        m.d.sync += latch_s1_line.eq(s1_line)
        with m.If(~self.s1_stall):
            m.d.sync += latch_s1_line_no_stall.eq(s1_line)

        # select the way containing the requested data
        way_sel = m.submodules.way_sel = Encoder(self.nb_ways)
        for j, way in enumerate(ways):
            m.d.comb += way_sel.i[j].eq((latch_s1_line_no_stall == s2_line) & (way.tag.value == s2_tag) & way.tag.valid)

        miss = Signal()
        m.d.comb += miss.eq(self.s2_re & way_sel.n)

        # cache control FSM

        s2_dat_r = Signal.like(self.s2_dat_r)
        with m.FSM() as fsm:
            m.d.comb += flushing.eq(fsm.ongoing("FLUSH"))
            with m.State("FLUSH"):
                m.d.comb += flush_stall.eq(1)
                m.d.sync += flush_line.eq(flush_line - 1)
                with m.If(flush_line == 0):
                    m.next = "CHECK"

            with m.State("CHECK"):
                m.d.comb += s2_dat_r.eq(ways[way_sel.o].data)
                with m.If(self.flush):
                    m.next = "FLUSH"
                with m.Elif(miss):
                    m.d.comb += refill_stall.eq(1)
                    with m.If(self.refill_ready):
                        m.d.comb += self.refill_request.eq(1)
                        m.next = "REFILL"

            m.d.comb += refilling.eq(fsm.ongoing("REFILL"))
            with m.State("REFILL"):
                with m.If((refill_tag == s2_tag) & (refill_line == s2_line) & ~self.s2_we):
                    # Resume execution as soon as the requested word is available.
                    with m.If(refill_offset == s2_offset):
                        m.d.comb += [
                            refill_stall.eq(~self.refill_valid),
                            s2_dat_r.eq(self.refill_data)
                        ]
                    with m.Else():
                        # We use refill_status to track valid words during a refill.
                        m.d.comb += [
                            refill_stall.eq(~refill_status[s2_offset]),
                            s2_dat_r.eq(ways[way_sel.o].data)
                        ]
                with m.Else():
                    m.d.comb += [
                        refill_stall.eq(miss | self.s2_we | (refill_tag != s2_tag)),
                        s2_dat_r.eq(ways[way_sel.o].data)
                    ]
                with m.If(self.refill_valid):
                    m.d.sync += refill_status[refill_offset].eq(1)
                    with m.If(self.last_refill):
                        m.d.sync += (s.eq(0) for s in refill_status)
                        m.next = "CHECK"

        # XXX: This is a dirty workaround to temporarily avoid using a RE
        # on the tag and data memory ports.
        # https://github.com/m-labs/nmigen/issues/16
        # https://github.com/YosysHQ/yosys/issues/760
        latch_s2_dat_r = Signal.like(self.s2_dat_r)
        latch_s2_stall = Signal()
        latch_stall_request = Signal()
        restore_s2 = Signal()
        m.d.sync += [
            latch_s2_stall.eq(self.s2_stall),
            latch_stall_request.eq(self.stall_request)
        ]
        with m.If(~latch_s2_stall & self.s2_stall \
                | latch_stall_request & self.refill_request \
                | latch_stall_request & ~self.stall_request & self.s2_stall):
            m.d.sync += [
                restore_s2.eq(~self.stall_request | refilling),
                latch_s2_dat_r.eq(s2_dat_r)
            ]
        with m.If(latch_s2_stall & restore_s2 & ~(refilling & (self.refill_address == self.s2_address))):
            m.d.comb += self.s2_dat_r.eq(latch_s2_dat_r)
        with m.Else():
            m.d.comb += self.s2_dat_r.eq(s2_dat_r)

        # tag memory

        tag_din = Record(tag_layout)
        with m.If(refilling):
            m.d.comb += [
                tag_din.value.eq(refill_tag),
                tag_din.valid.eq(self.last_refill & self.refill_valid)
            ]
        with m.Elif(self.s2_we):
            m.d.comb += [
                tag_din.value.eq(ways[refill_lru].tag.value),
                tag_din.valid.eq(way_sel.i.part(refill_lru, 1))
            ]
        with m.Else():
            m.d.comb += [
                tag_din.value.eq(0),
                tag_din.valid.eq(0)
            ]

        for way in ways:
            tag_mem = Memory(len(tag_din), 2**self.linebits)
            tag_wp = m.submodules.tag_wp = tag_mem.write_port()
            tag_rp = m.submodules.tag_rp = tag_mem.read_port()

            with m.If(refilling):
                m.d.comb += [
                    tag_wp.addr.eq(refill_line),
                    tag_wp.en.eq(way.enable)
                ]
            with m.Elif(flushing):
                m.d.comb += [
                    tag_wp.addr.eq(flush_line),
                    tag_wp.en.eq(1)
                ]
            with m.Else():
                m.d.comb += [
                    tag_wp.addr.eq(s2_line),
                    tag_wp.en.eq(way.enable & self.s2_we)
                ]
            m.d.comb += tag_wp.data.eq(tag_din)

            m.d.comb += tag_rp.addr.eq(s1_line)
            latch_tag_rp_data = Signal.like(tag_rp.data)
            with m.If(latch_s1_line == s2_line):
                m.d.sync += latch_tag_rp_data.eq(tag_rp.data)
                m.d.comb += way.tag.eq(tag_rp.data)
            with m.Else():
                m.d.comb += way.tag.eq(latch_tag_rp_data)

        # data memory

        data_din = Signal(32)
        for i in range(len(self.s2_sel)):
            byte = slice(i*8, (i+1)*8)
            with m.If(self.s2_sel[i]):
                m.d.comb += data_din[byte].eq(self.s2_dat_w[byte])
            with m.Else():
                m.d.comb += data_din[byte].eq(ways[refill_lru].data[byte])

        for way in ways:
            data_mem = Memory(self.nb_words*32, 2**self.linebits)
            data_wp = m.submodules.data_wp = data_mem.write_port(granularity=32)
            data_rp = m.submodules.data_rp = data_mem.read_port()

            with m.If(refilling):
                m.d.comb += [
                    data_wp.addr.eq(refill_line),
                    displacer(way.enable, refill_offset, data_wp.en),
                    displacer(self.refill_data, refill_offset, data_wp.data)
                ]
            with m.Elif(flushing):
                m.d.comb += data_wp.addr.eq(flush_line)
            with m.Else():
                m.d.comb += [
                    data_wp.addr.eq(s2_line),
                    displacer(way.enable & self.s2_we, s2_offset, data_wp.en),
                    displacer(data_din, s2_offset, data_wp.data)
                ]

            m.d.comb += data_rp.addr.eq(s1_line)
            latch_data_rp_data = Signal.like(data_rp.data)
            with m.If(latch_s1_line == s2_line):
                m.d.sync += latch_data_rp_data.eq(data_rp.data)
                m.d.comb += way.data.eq(data_rp.data.part(s2_offset*32, 32))
            with m.Else():
                m.d.comb += way.data.eq(latch_data_rp_data.part(s2_offset*32, 32))

        return m
