from nmigen import *
from nmigen.test.utils import *
from nmigen.asserts import *

from ..cache import L1Cache


class L1CacheSpec(Elaboratable):
    def __init__(self, cache):
        self.cache = cache

    def elaborate(self, platform):
        m = Module()
        m.submodules.dut = cache = self.cache

        mem_addr = AnyConst(cache.bus_addr.shape())
        mem_data = AnyConst(cache.bus_rdata.shape())

        with m.If(cache.bus_re & (cache.bus_addr == mem_addr)):
            m.d.comb += Assume(cache.bus_rdata == mem_data)

        s1_re     = AnySeq(1)
        s1_flush  = AnySeq(1)
        s1_evict  = AnySeq(1)
        s1_select = AnySeq(1)

        with m.If(~cache.s1_stall):
            m.d.sync += [
                cache.s2_addr.eq(cache.s1_addr),
                cache.s2_re.eq(s1_re),
                cache.s2_flush.eq(s1_flush),
                cache.s2_evict.eq(s1_evict),
                cache.s2_valid.eq(cache.s1_valid)
            ]

        with m.If((cache.s2_flush & ~cache.s2_flush_ack | cache.s2_re & cache.s2_miss)
                & cache.s2_valid):
            m.d.comb += Assume(cache.s1_stall)

        with m.If(Initial()):
            m.d.comb += Assume(~cache.s2_valid)
            m.d.comb += Assume(~cache.bus_re)

        # Any hit at `mem_addr` must return `mem_data`.
        with m.If(cache.s2_re & (cache.s2_addr == mem_addr) & ~cache.s2_miss
                & cache.s2_valid):
            m.d.comb += Assert(cache.s2_rdata == mem_data)

        # The next read at any address after a flush must miss.
        cache_empty = Signal()
        with m.If(cache.s2_flush & Rose(cache.s2_flush_ack) & cache.s2_valid):
            m.d.sync += cache_empty.eq(1)
        with m.If(cache.bus_re & cache.bus_valid & cache.bus_last & ~cache.bus_error):
            m.d.sync += cache_empty.eq(0)
        with m.If(cache.s2_re & cache.s2_valid & cache_empty):
            m.d.comb += Assert(cache.s2_miss)

        # The next read at a refilled address must hit.
        line_valid  = Signal()
        refill_addr = Record.like(cache.s2_addr)
        with m.If(cache.bus_re & cache.bus_valid & cache.bus_last & ~cache.bus_error):
            m.d.sync += line_valid.eq(1)
            m.d.sync += refill_addr.eq(cache.bus_addr)
        with m.If((cache.s2_flush | cache.s2_evict) & cache.s2_valid):
            m.d.sync += line_valid.eq(0)
        with m.If(cache.s2_re & cache.s2_valid & line_valid
                & (cache.s2_addr.line == refill_addr.line)
                & (cache.s2_addr.tag  == refill_addr.tag)):
            m.d.comb += Assert(~cache.s2_miss)

        # The next read at an evicted address must miss.
        line_empty = Signal()
        evict_addr = Record.like(cache.s2_addr)
        with m.If(cache.s2_evict & cache.s2_valid):
            m.d.sync += line_empty.eq(1)
            m.d.sync += evict_addr.eq(cache.s2_addr)
        with m.If(cache.bus_re & cache.bus_valid & cache.bus_last
                & (cache.bus_addr.line == evict_addr.line)):
            m.d.sync += line_empty.eq(0)
        with m.If(cache.s2_re & cache.s2_valid & line_empty
                & (cache.s2_addr.line == evict_addr.line)
                & (cache.s2_addr.tag  == evict_addr.tag)):
            m.d.comb += Assert(cache.s2_miss)

        return m


# FIXME: FHDLTestCase is internal to nMigen, we shouldn't use it.
class L1CacheTestCase(FHDLTestCase):
    def check(self, cache):
        self.assertFormal(L1CacheSpec(cache), mode="bmc", depth=12)

    def test_direct_mapped(self):
        self.check(L1Cache(nways=1, nlines=2, nwords=4, base=0, limit=64))

    def test_2_ways(self):
        self.check(L1Cache(nways=2, nlines=2, nwords=4, base=0, limit=64))
