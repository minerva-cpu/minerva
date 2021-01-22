from nmigen import *
from nmigen.utils import log2_int

from ..cache import *
from ..wishbone import *


__all__ = ["PCSelector", "FetchUnitInterface", "BareFetchUnit", "CachedFetchUnit"]


class PCSelector(Elaboratable):
    def __init__(self):
        self.f_pc = Signal(32)
        self.d_pc = Signal(32)
        self.d_branch_predict_taken = Signal()
        self.d_branch_target = Signal(32)
        self.d_valid = Signal()
        self.x_pc = Signal(32)
        self.x_fence_i = Signal()
        self.x_valid = Signal()
        self.m_branch_predict_taken = Signal()
        self.m_branch_taken = Signal()
        self.m_branch_target = Signal(32)
        self.m_exception = Signal()
        self.m_mret = Signal()
        self.m_valid = Signal()
        self.mtvec_r_base = Signal(30)
        self.mepc_r_base = Signal(30)

        self.a_pc = Signal(32)

    def elaborate(self, platform):
        m = Module()

        m_sel   = Signal(reset=1)
        m_pc4_a = Signal(30)
        a_pc4   = Signal(30)

        with m.If(self.m_exception):
            m.d.comb += m_pc4_a.eq(self.mtvec_r_base)
        with m.Elif(self.m_mret):
            m.d.comb += m_pc4_a.eq(self.mepc_r_base)
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


class FetchUnitInterface:
    def __init__(self):
        self.ibus = Record(wishbone_layout)

        self.a_pc = Signal(32)
        self.a_stall = Signal()
        self.a_valid = Signal()
        self.f_stall = Signal()
        self.f_valid = Signal()

        self.a_busy = Signal()
        self.f_busy = Signal()
        self.f_instruction = Signal(32, reset=0x00000013) # nop (addi x0, x0, 0)
        self.f_fetch_error = Signal()
        self.f_badaddr = Signal(30)


class BareFetchUnit(FetchUnitInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        ibus_rdata = Signal.like(self.ibus.dat_r)
        with m.If(self.ibus.cyc):
            with m.If(self.ibus.ack | self.ibus.err | ~self.f_valid):
                m.d.sync += [
                    self.ibus.cyc.eq(0),
                    self.ibus.stb.eq(0),
                    ibus_rdata.eq(self.ibus.dat_r)
                ]
        with m.Elif(self.a_valid & ~self.a_stall):
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
        with m.Elif(~self.f_stall):
            m.d.sync += self.f_fetch_error.eq(0)

        m.d.comb += self.a_busy.eq(self.ibus.cyc)

        with m.If(self.f_fetch_error):
            m.d.comb += self.f_busy.eq(0)
        with m.Else():
            m.d.comb += [
                self.f_busy.eq(self.ibus.cyc),
                self.f_instruction.eq(ibus_rdata)
            ]

        return m


class CachedFetchUnit(FetchUnitInterface, Elaboratable):
    def __init__(self, *icache_args):
        super().__init__()

        self.icache_args = icache_args

        self.f_pc = Signal(32)
        self.a_flush = Signal()

    def elaborate(self, platform):
        m = Module()

        icache = m.submodules.icache = L1Cache(*self.icache_args)

        a_icache_select = Signal()

        # Test whether the target address is inside the L1 cache region. We use bit masks in order
        # to avoid carry chains from arithmetic comparisons. This restricts the region boundaries
        # to powers of 2.
        with m.Switch(self.a_pc[2:]):
            def addr_below(limit):
                assert limit in range(1, 2**30 + 1)
                range_bits = log2_int(limit)
                const_bits = 30 - range_bits
                return "{}{}".format("0" * const_bits, "-" * range_bits)

            if icache.base >= 4:
                with m.Case(addr_below(icache.base >> 2)):
                    m.d.comb += a_icache_select.eq(0)
            with m.Case(addr_below(icache.limit >> 2)):
                m.d.comb += a_icache_select.eq(1)
            with m.Default():
                m.d.comb += a_icache_select.eq(0)

        f_icache_select = Signal()
        f_flush = Signal()

        with m.If(~self.a_stall):
            m.d.sync += [
                f_icache_select.eq(a_icache_select),
                f_flush.eq(self.a_flush),
            ]

        m.d.comb += [
            icache.s1_addr.eq(self.a_pc[2:]),
            icache.s1_stall.eq(self.a_stall),
            icache.s1_valid.eq(self.a_valid),
            icache.s2_addr.eq(self.f_pc[2:]),
            icache.s2_re.eq(f_icache_select),
            icache.s2_evict.eq(Const(0)),
            icache.s2_flush.eq(f_flush),
            icache.s2_valid.eq(self.f_valid),
        ]

        ibus_arbiter = m.submodules.ibus_arbiter = WishboneArbiter()
        m.d.comb += ibus_arbiter.bus.connect(self.ibus)

        icache_port = ibus_arbiter.port(priority=0)
        m.d.comb += [
            icache_port.cyc.eq(icache.bus_re),
            icache_port.stb.eq(icache.bus_re),
            icache_port.adr.eq(icache.bus_addr),
            icache_port.sel.eq(0b1111),
            icache_port.cti.eq(Mux(icache.bus_last, Cycle.END, Cycle.INCREMENT)),
            icache_port.bte.eq(Const(log2_int(icache.nwords) - 1)),
            icache.bus_valid.eq(icache_port.ack),
            icache.bus_error.eq(icache_port.err),
            icache.bus_rdata.eq(icache_port.dat_r)
        ]

        bare_port = ibus_arbiter.port(priority=1)
        bare_rdata = Signal.like(bare_port.dat_r)
        with m.If(bare_port.cyc):
            with m.If(bare_port.ack | bare_port.err | ~self.f_valid):
                m.d.sync += [
                    bare_port.cyc.eq(0),
                    bare_port.stb.eq(0),
                    bare_rdata.eq(bare_port.dat_r)
                ]
        with m.Elif(~a_icache_select & self.a_valid & ~self.a_stall):
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
        with m.Elif(~self.f_stall):
            m.d.sync += self.f_fetch_error.eq(0)

        with m.If(f_flush):
            m.d.comb += self.f_busy.eq(~icache.s2_flush_ack)
        with m.Elif(self.f_fetch_error):
            m.d.comb += self.f_busy.eq(0)
        with m.Elif(f_icache_select):
            m.d.comb += [
                self.f_busy.eq(icache.s2_miss),
                self.f_instruction.eq(icache.s2_rdata)
            ]
        with m.Else():
            m.d.comb += [
                self.f_busy.eq(bare_port.cyc),
                self.f_instruction.eq(bare_rdata)
            ]

        return m
