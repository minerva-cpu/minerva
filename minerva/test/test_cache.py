from nmigen import *
from nmigen.utils import log2_int
from nmigen.test.utils import *
from nmigen.asserts import *

from ..cache import L1Cache


class L1CacheSpec(Elaboratable):
    """
    A cache read at a given address must either:
    - miss and start a cache refill;
    - hit and return the last refilled value for that address.
    """
    def __init__(self, cache):
        self.cache = cache

    def elaborate(self, platform):
        m = Module()
        m.submodules.dut = cache = self.cache

        addr  = AnyConst(cache.s1_addr.shape())
        s1_re = AnySeq(1)

        with m.If(~cache.s1_stall):
            m.d.sync += [
                cache.s2_addr.eq(cache.s1_addr),
                cache.s2_re.eq(s1_re),
                cache.s2_valid.eq(cache.s1_valid)
            ]

        m.d.comb += Assume(cache.s1_valid.implies(cache.s1_addr == addr))
        with m.If(cache.s2_re & cache.s2_miss & cache.s2_valid):
            m.d.comb += Assume(cache.s1_stall)

        spec_s2_rdata = Signal(32)
        spec_bus_re   = Signal()
        spec_bus_addr = Record.like(cache.bus_addr)
        spec_bus_last = Signal()
        last_offset   = Signal.like(cache.s2_addr.offset)

        with m.If(~Past(cache.s1_stall)):
            with m.If(cache.s2_re & cache.s2_miss & cache.s2_valid):
                m.d.sync += [
                    spec_bus_re.eq(1),
                    spec_bus_addr.eq(cache.s2_addr),
                    last_offset.eq(cache.s2_addr.offset - 1)
                ]

        with m.If(cache.bus_re):
            with m.If(cache.bus_valid):
                # Lines are refilled with an incremental burst that starts at the missed address
                # and wraps around the offset bits.
                m.d.sync += spec_bus_addr.offset.eq(spec_bus_addr.offset + 1)
                with m.If((cache.bus_addr == cache.s2_addr) & ~cache.bus_error):
                    m.d.sync += spec_s2_rdata.eq(cache.bus_rdata)
            # A burst ends when all words in the line have been refilled, or an error occured.
            m.d.comb += spec_bus_last.eq(cache.bus_addr.offset == last_offset)
            with m.If(cache.bus_valid & cache.bus_last | cache.bus_error):
                m.d.sync += spec_bus_re.eq(0)

        with m.If(cache.s2_re & cache.s2_valid & ~cache.s2_miss):
            m.d.comb += Assert(cache.s2_rdata == spec_s2_rdata)

        m.d.comb += Assert(cache.bus_re == spec_bus_re)
        with m.If(cache.bus_re):
            m.d.comb += [
                Assert(cache.bus_addr == spec_bus_addr),
                Assert(cache.bus_last == spec_bus_last)
            ]

        with m.If(Initial()):
            m.d.comb += [
                Assume(cache.s1_stall),
                Assume(~cache.s2_valid),
                Assume(~cache.bus_re),
                Assume(~spec_bus_re)
            ]

        return m


class L1CacheTestCase(FHDLTestCase):
    def check(self, cache):
        self.assertFormal(L1CacheSpec(cache), mode="bmc", depth=10)

    def test_direct_mapped(self):
        self.check(L1Cache(nways=1, nlines=2, nwords=4, base=0, limit=1024))

    def test_2_ways(self):
        self.check(L1Cache(nways=2, nlines=2, nwords=4, base=0, limit=1024))
