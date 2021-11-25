from amaranth import *
from amaranth.asserts import *

from minerva.test.utils import FormalTestCase
from minerva.cache import L1Cache


class L1CacheSpec(Elaboratable):
    def __init__(self, cache):
        self.cache = cache

    def elaborate(self, platform):
        m = Module()
        m.submodules.dut = cache = self.cache

        mem_addr = Signal.like(cache.bus_addr)
        mem_data = Signal.like(cache.bus_data)

        m.d.comb += [
            mem_addr.eq(AnyConst(cache.bus_addr.shape())),
            mem_data.eq(AnyConst(cache.bus_data.shape())),
        ]

        with m.If(cache.bus_req & (cache.bus_addr == mem_addr)):
            m.d.comb += Assume(cache.bus_data == mem_data)

        s1_op    = Signal.like(cache.s2_op)
        s1_valid = Signal()

        m.d.comb  += [
            s1_op.read .eq(AnySeq(1)),
            s1_op.flush.eq(AnySeq(1)),
            s1_op.evict.eq(AnySeq(1)),
            s1_valid   .eq(AnySeq(1)),
        ]

        with m.If(cache.s1_ready):
            m.d.sync += [
                cache.s2_addr .eq(cache.s1_addr),
                cache.s2_op   .eq(s1_op),
                cache.s2_valid.eq(s1_valid)
            ]

        with m.If(cache.s2_valid & cache.s2_busy):
            m.d.comb += Assume(~cache.s1_ready)

        with m.If(Initial()):
            m.d.comb += Assume(~cache.s2_valid)
            m.d.comb += Assume(~cache.bus_req)

        # Any hit at `mem_addr` must return `mem_data`.
        with m.If(cache.s2_op.read & (cache.s2_addr == mem_addr) &
                  cache.s2_valid & ~cache.s2_busy):
            m.d.comb += Assert(cache.s2_data == mem_data)

        # The next read at any address after a flush must miss.
        cache_empty = Signal()
        with m.If(cache.s2_op.flush & cache.s2_valid & ~cache.s2_busy):
            m.d.sync += cache_empty.eq(1)
        with m.If(cache.bus_req & cache.bus_ack & cache.bus_last):
            m.d.sync += cache_empty.eq(0)
        with m.If(cache.s2_op.read & cache.s2_valid & cache_empty):
            m.d.comb += Assert(cache.s2_busy)

        # The next read at a refilled address must hit.
        line_valid  = Signal()
        refill_addr = Signal.like(cache.s2_addr)
        with m.If(cache.bus_req & cache.bus_ack & cache.bus_last):
            m.d.sync += line_valid.eq(1)
            m.d.sync += refill_addr.eq(cache.bus_addr)
        with m.If((cache.s2_op.flush | cache.s2_op.evict) & cache.s2_valid):
            m.d.sync += line_valid.eq(0)
        with m.If(cache.s2_op.read & cache.s2_valid & line_valid &
                  (cache.s2_addr.line == refill_addr.line) &
                  (cache.s2_addr.tag  == refill_addr.tag)):
            m.d.comb += Assert(~cache.s2_busy)

        # The next read at an evicted address must miss.
        line_empty = Signal()
        evict_addr = Signal.like(cache.s2_addr)
        with m.If(cache.s2_op.evict & cache.s2_valid):
            m.d.sync += line_empty.eq(1)
            m.d.sync += evict_addr.eq(cache.s2_addr)
        with m.If(cache.bus_req & cache.bus_ack & cache.bus_last &
                  (cache.bus_addr.line == evict_addr.line)):
            m.d.sync += line_empty.eq(0)
        with m.If(cache.s2_op.read & cache.s2_valid & line_empty &
                  (cache.s2_addr.line == evict_addr.line) &
                  (cache.s2_addr.tag  == evict_addr.tag)):
            m.d.comb += Assert(cache.s2_busy)

        return m


class L1CacheTestCase(FormalTestCase):
    def check(self, cache):
        self.assertFormal(L1CacheSpec(cache), mode="bmc", depth=12)

    def test_direct_mapped(self):
        self.check(L1Cache(nways=1, nlines=2, nwords=4, base=0, limit=64))

    def test_2_ways(self):
        self.check(L1Cache(nways=2, nlines=2, nwords=4, base=0, limit=64))
