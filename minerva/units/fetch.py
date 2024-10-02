from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, flipped, connect
from amaranth.utils import ceil_log2, exact_log2

from amaranth_soc import wishbone
from amaranth_soc.wishbone.bus import CycleType

from ..cache import *
from ..arbiter import WishboneArbiter


__all__ = ["PCSelector", "BareFetchUnit", "CachedFetchUnit"]


class PCSelector(wiring.Component):
    a_pc:                   Out(32)

    f_pc:                   In(32)

    d_pc:                   In(32)
    d_branch_predict_taken: In(1)
    d_branch_target:        In(32)
    d_valid:                In(1)

    x_pc:                   In(32)
    x_fence_i:              In(1)
    x_mtvec_base:           In(30)
    x_mepc_base:            In(30)
    x_valid:                In(1)

    m_branch_predict_taken: In(1)
    m_branch_taken:         In(1)
    m_branch_target:        In(32)
    m_exception:            In(1)
    m_mret:                 In(1)
    m_valid:                In(1)

    def elaborate(self, platform):
        m = Module()

        m_sel   = Signal(reset=1)
        m_pc4_a = Signal(30)
        a_pc4   = Signal(30)

        with m.If(self.m_exception):
            # The pipeline will stall new instructions at D stage while a CSR write instruction
            # is in-flight. Therefore, we assume that no write to mtvec is ongoing here.
            m.d.comb += m_pc4_a.eq(self.x_mtvec_base)
        with m.Elif(self.m_mret):
            # Same for mepc.
            m.d.comb += m_pc4_a.eq(self.x_mepc_base)
        with m.Elif(self.m_branch_predict_taken & ~self.m_branch_taken):
            m.d.comb += m_pc4_a.eq(self.x_pc[2:])
        with m.Elif(~self.m_branch_predict_taken & self.m_branch_taken):
            m.d.comb += m_pc4_a.eq(self.m_branch_target[2:]),
        with m.Else():
            m.d.comb += m_sel.eq(0)

        with m.If(m_sel & self.m_valid):
            m.d.comb += a_pc4.eq(m_pc4_a)
        with m.Elif(self.x_fence_i & self.x_valid):
            m.d.comb += a_pc4.eq(self.d_pc[2:])
        with m.Elif(self.d_branch_predict_taken & self.d_valid):
            m.d.comb += a_pc4.eq(self.d_branch_target[2:]),
        with m.Else():
            m.d.comb += a_pc4.eq(self.f_pc[2:] + 1)

        m.d.comb += self.a_pc[2:].eq(a_pc4)

        return m


class BareFetchUnit(wiring.Component):
    ibus:          Out(wishbone.Signature(addr_width=30, data_width=32, granularity=8,
                                          features=("err", "cti", "bte")))

    a_pc:          In(32)
    a_busy:        Out(1)
    a_ready:       In(1)
    a_valid:       In(1)

    f_busy:        Out(1)
    f_instruction: Out(32)
    f_fetch_error: Out(1)
    f_badaddr:     Out(30)
    f_ready:       In(1)
    f_valid:       In(1)

    def elaborate(self, platform):
        m = Module()

        ibus_rdata = Signal.like(self.ibus.dat_r)
        with m.If(self.ibus.cyc):
            with m.If(self.ibus.ack | self.ibus.err):
                m.d.sync += [
                    self.ibus.cyc.eq(0),
                    self.ibus.stb.eq(0),
                    ibus_rdata.eq(self.ibus.dat_r)
                ]
        with m.Elif(self.a_valid & self.a_ready):
            m.d.sync += [
                self.ibus.adr.eq(self.a_pc[2:]),
                self.ibus.cyc.eq(1),
                self.ibus.stb.eq(1)
            ]
        m.d.comb += self.ibus.sel.eq(0b1111)

        with m.If(self.ibus.cyc & self.ibus.err):
            m.d.sync += [
                self.f_fetch_error.eq(1),
                self.f_badaddr.eq(self.ibus.adr)
            ]
        with m.Elif(self.f_ready):
            m.d.sync += self.f_fetch_error.eq(0)

        m.d.comb += self.a_busy.eq(self.ibus.cyc)

        with m.If(self.f_fetch_error):
            m.d.comb += [
                self.f_busy.eq(0),
                self.f_instruction.eq(0x00000013), # nop (addi x0, x0, 0)
            ]
        with m.Else():
            m.d.comb += [
                self.f_busy.eq(self.ibus.cyc),
                self.f_instruction.eq(ibus_rdata)
            ]

        return m


class CachedFetchUnit(wiring.Component):
    ibus:          Out(wishbone.Signature(addr_width=30, data_width=32, granularity=8,
                                          features=("err", "cti", "bte")))

    a_pc:          In(32)
    a_flush:       In(1)
    a_busy:        Out(1)
    a_ready:       In(1)
    a_valid:       In(1)

    f_pc:          In(32)
    f_busy:        Out(1)
    f_instruction: Out(32)
    f_fetch_error: Out(1)
    f_badaddr:     Out(30)
    f_ready:       In(1)
    f_valid:       In(1)

    def __init__(self, *, icache_nways, icache_nlines, icache_nwords, icache_base, icache_limit):
        self._icache = L1Cache(
            nways  = icache_nways,
            nlines = icache_nlines,
            nwords = icache_nwords,
            base   = icache_base,
            limit  = icache_limit
        )
        super().__init__()

    def elaborate(self, platform):
        m = Module()

        m.submodules.icache = self._icache

        a_icache_select = Signal()

        # Test whether the target address is inside the L1 cache region. We use a bit mask in order
        # to avoid carry chains from arithmetic comparisons. To this end, the base and limit
        # addresses of the cached region must satisfy the following constraints:
        # 1) the region size (i.e. ``limit - base``) must be a power of 2
        # 2) ``base`` must be a multiple of the region size

        def addr_between(base, limit):
            assert base  in range(0, 2**30 + 1)
            assert limit in range(0, 2**30 + 1)
            assert limit >= base
            assert base % (limit - base) == 0
            addr_width = exact_log2(limit - base)
            const_bits = 30 - addr_width
            if const_bits > 0:
                const_pat = "{:0{}b}".format(base >> addr_width, const_bits)
            else:
                const_pat = ""
            return "{}{}".format(const_pat, "-" * addr_width)

        icache_pattern = addr_between(self._icache.base >> 2, self._icache.limit >> 2)
        with m.If(self.a_pc[2:].matches(icache_pattern)):
            m.d.comb += a_icache_select.eq(1)

        f_icache_select = Signal()
        f_flush = Signal()

        with m.If(self.a_ready):
            m.d.sync += [
                f_icache_select.eq(a_icache_select),
                f_flush.eq(self.a_flush),
            ]

        m.d.comb += [
            self._icache.s1_addr    .eq(self.a_pc[2:]),
            self._icache.s1_ready   .eq(self.a_ready),
            self._icache.s2_addr    .eq(self.f_pc[2:]),
            self._icache.s2_op.read .eq(f_icache_select),
            self._icache.s2_op.evict.eq(Const(0)),
            self._icache.s2_op.flush.eq(f_flush),
            self._icache.s2_valid   .eq(self.f_valid),
        ]

        ibus_arbiter = m.submodules.ibus_arbiter = WishboneArbiter()
        connect(m, ibus_arbiter.bus, flipped(self.ibus))

        icache_port = ibus_arbiter.port(priority=0)
        m.d.comb += [
            icache_port.cyc.eq(self._icache.bus_req),
            icache_port.stb.eq(self._icache.bus_req),
            icache_port.adr.eq(self._icache.bus_addr),
            icache_port.sel.eq(0b1111),
            icache_port.cti.eq(Mux(self._icache.bus_last, CycleType.END_OF_BURST, CycleType.INCR_BURST)),
            icache_port.bte.eq(Const(ceil_log2(self._icache.nwords) - 1)),
            self._icache.bus_ack .eq(icache_port.ack | icache_port.err),
            self._icache.bus_data.eq(icache_port.dat_r)
        ]

        bare_port = ibus_arbiter.port(priority=1)
        bare_rdata = Signal.like(bare_port.dat_r)
        with m.If(bare_port.cyc):
            with m.If(bare_port.ack | bare_port.err):
                m.d.sync += [
                    bare_port.cyc.eq(0),
                    bare_port.stb.eq(0),
                    bare_rdata.eq(bare_port.dat_r)
                ]
        with m.Elif(~a_icache_select & self.a_valid & self.a_ready):
            m.d.sync += [
                bare_port.cyc.eq(1),
                bare_port.stb.eq(1),
                bare_port.adr.eq(self.a_pc[2:])
            ]
        m.d.comb += bare_port.sel.eq(0b1111)

        m.d.comb += self.a_busy.eq(bare_port.cyc)

        with m.If(self.ibus.cyc & self.ibus.err):
            m.d.sync += [
                self.f_fetch_error.eq(1),
                self.f_badaddr.eq(self.ibus.adr)
            ]
        with m.Elif(self.f_ready):
            m.d.sync += self.f_fetch_error.eq(0)

        with m.If(f_icache_select):
            m.d.comb += self.f_busy.eq(self._icache.s2_busy)
        with m.Else():
            m.d.comb += self.f_busy.eq(bare_port.cyc)

        with m.If(self.f_fetch_error):
            m.d.comb += self.f_instruction.eq(0x00000013) # nop (addi x0, x0, 0)
        with m.Elif(f_icache_select):
            m.d.comb += self.f_instruction.eq(self._icache.s2_data)
        with m.Else():
            m.d.comb += self.f_instruction.eq(bare_rdata)

        return m
