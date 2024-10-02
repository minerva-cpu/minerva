from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, flipped, connect
from amaranth.lib.data import StructLayout
from amaranth.utils import ceil_log2, exact_log2
from amaranth.lib.fifo import SyncFIFOBuffered

from amaranth_soc import wishbone
from amaranth_soc.wishbone import CycleType

from ..cache import *
from ..isa import Funct3
from ..arbiter import WishboneArbiter


__all__ = ["DataSelector", "BareLoadStoreUnit", "CachedLoadStoreUnit"]


class DataSelector(wiring.Component):
    x_offset:        In(2)
    x_funct3:        In(3)
    x_store_operand: In(32)
    x_misaligned:    Out(1)
    x_mask:          Out(4)
    x_store_data:    Out(32)

    w_offset:        In(2)
    w_funct3:        In(3)
    w_load_data:     In(32)
    w_load_result:   Out(signed(32))

    def elaborate(self, platform):
        m = Module()

        with m.Switch(self.x_funct3):
            with m.Case(Funct3.H, Funct3.HU):
                m.d.comb += self.x_misaligned.eq(self.x_offset[0])
            with m.Case(Funct3.W):
                m.d.comb += self.x_misaligned.eq(self.x_offset.bool())

        with m.Switch(self.x_funct3):
            with m.Case(Funct3.B, Funct3.BU):
                m.d.comb += self.x_mask.eq(0b1 << self.x_offset)
            with m.Case(Funct3.H, Funct3.HU):
                m.d.comb += self.x_mask.eq(0b11 << self.x_offset)
            with m.Case(Funct3.W):
                m.d.comb += self.x_mask.eq(0b1111)

        with m.Switch(self.x_funct3):
            with m.Case(Funct3.B):
                m.d.comb += self.x_store_data.eq(self.x_store_operand[:8] << self.x_offset*8)
            with m.Case(Funct3.H):
                m.d.comb += self.x_store_data.eq(self.x_store_operand[:16] << self.x_offset[1]*16)
            with m.Case(Funct3.W):
                m.d.comb += self.x_store_data.eq(self.x_store_operand)

        w_byte = Signal(signed(8))
        w_half = Signal(signed(16))

        m.d.comb += [
            w_byte.eq(self.w_load_data.word_select(self.w_offset, 8)),
            w_half.eq(self.w_load_data.word_select(self.w_offset[1], 16))
        ]

        with m.Switch(self.w_funct3):
            with m.Case(Funct3.B):
                m.d.comb += self.w_load_result.eq(w_byte)
            with m.Case(Funct3.BU):
                m.d.comb += self.w_load_result.eq(Cat(w_byte, 0))
            with m.Case(Funct3.H):
                m.d.comb += self.w_load_result.eq(w_half)
            with m.Case(Funct3.HU):
                m.d.comb += self.w_load_result.eq(Cat(w_half, 0))
            with m.Case(Funct3.W):
                m.d.comb += self.w_load_result.eq(self.w_load_data)

        return m


class BareLoadStoreUnit(wiring.Component):
    dbus:          Out(wishbone.Signature(addr_width=30, data_width=32, granularity=8,
                                          features=("err", "cti", "bte")))

    x_addr:        In(32)
    x_mask:        In(4)
    x_load:        In(1)
    x_store:       In(1)
    x_store_data:  In(32)
    x_busy:        Out(1)
    x_ready:       In(1)
    x_valid:       In(1)

    m_busy:        Out(1)
    m_load_data:   Out(32)
    m_load_error:  Out(1)
    m_store_error: Out(1)
    m_badaddr:     Out(30)
    m_ready:       In(1)
    m_valid:       In(1)

    def elaborate(self, platform):
        m = Module()

        with m.If(self.dbus.cyc):
            with m.If(self.dbus.ack | self.dbus.err):
                m.d.sync += [
                    self.dbus.cyc.eq(0),
                    self.dbus.stb.eq(0),
                    self.m_load_data.eq(self.dbus.dat_r)
                ]
        with m.Elif((self.x_load | self.x_store) & self.x_valid & self.x_ready):
            m.d.sync += [
                self.dbus.cyc.eq(1),
                self.dbus.stb.eq(1),
                self.dbus.adr.eq(self.x_addr[2:]),
                self.dbus.sel.eq(self.x_mask),
                self.dbus.we.eq(self.x_store),
                self.dbus.dat_w.eq(self.x_store_data)
            ]

        with m.If(self.dbus.cyc & self.dbus.err):
            m.d.sync += [
                self.m_load_error.eq(~self.dbus.we),
                self.m_store_error.eq(self.dbus.we),
                self.m_badaddr.eq(self.dbus.adr)
            ]
        with m.Elif(self.m_ready):
            m.d.sync += [
                self.m_load_error.eq(0),
                self.m_store_error.eq(0)
            ]

        m.d.comb += self.x_busy.eq(self.dbus.cyc)

        with m.If(self.m_load_error | self.m_store_error):
            m.d.comb += self.m_busy.eq(0)
        with m.Else():
            m.d.comb += self.m_busy.eq(self.dbus.cyc)

        return m


class WriteBuffer(wiring.Component):
    def __init__(self, *, depth, addr_width, data_width, granularity):
        op_layout = StructLayout({
            "addr": addr_width,
            "mask": data_width // granularity,
            "data": data_width,
        })
        super().__init__({
            "w_en":  In(1),
            "w_rdy": Out(1),
            "w_op":  In(op_layout),
            "r_en":  In(1),
            "r_rdy": Out(1),
            "r_op":  Out(op_layout),
        })
        self._fifo = SyncFIFOBuffered(width=len(self.w_op.as_value()), depth=depth)


    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = self._fifo
        m.d.comb += [
            self.w_rdy.eq(self._fifo.w_rdy),
            self._fifo.w_en  .eq(self.w_en),
            self._fifo.w_data.eq(self.w_op),

            self._fifo.r_en.eq(self.r_en),
            self.r_rdy.eq(self._fifo.r_rdy),
            self.r_op .eq(self._fifo.r_data),
        ]

        return m


class CachedLoadStoreUnit(wiring.Component):
    dbus:          Out(wishbone.Signature(addr_width=30, data_width=32, granularity=8,
                                          features=("err", "cti", "bte")))

    x_addr:        In(32)
    x_mask:        In(4)
    x_load:        In(1)
    x_fence_i:     In(1)
    x_store:       In(1)
    x_store_data:  In(32)
    x_busy:        Out(1)
    x_ready:       In(1)
    x_valid:       In(1)

    m_load:        In(1)
    m_store:       In(1)
    m_flush:       In(1)
    m_busy:        Out(1)
    m_load_data:   Out(32)
    m_load_error:  Out(1)
    m_store_error: Out(1)
    m_badaddr:     Out(30)
    m_ready:       In(1)
    m_valid:       In(1)

    def __init__(self, *, dcache_nways, dcache_nlines, dcache_nwords, dcache_base, dcache_limit,
                 wrbuf_depth):
        self._dcache = L1Cache(
            nways  = dcache_nways,
            nlines = dcache_nlines,
            nwords = dcache_nwords,
            base   = dcache_base,
            limit  = dcache_limit
        )
        self._wrbuf  = WriteBuffer(
            depth       = wrbuf_depth,
            addr_width  = 30,
            data_width  = 32,
            granularity = 8,
        )
        super().__init__()

    def elaborate(self, platform):
        m = Module()

        m.submodules.dcache = self._dcache

        x_dcache_select = Signal()

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

        dcache_pattern = addr_between(self._dcache.base >> 2, self._dcache.limit >> 2)
        with m.If(self.x_addr[2:].matches(dcache_pattern)):
            m.d.comb += x_dcache_select.eq(1)

        m_dcache_select = Signal()
        m_addr = Signal.like(self.x_addr)

        with m.If(self.x_ready):
            m.d.sync += [
                m_dcache_select.eq(x_dcache_select),
                m_addr.eq(self.x_addr),
            ]

        m.d.comb += [
            self._dcache.s1_addr    .eq(self.x_addr[2:]),
            self._dcache.s1_ready   .eq(self.x_ready),
            self._dcache.s2_addr    .eq(m_addr[2:]),
            self._dcache.s2_op.read .eq(self.m_load  & m_dcache_select),
            self._dcache.s2_op.evict.eq(self.m_store & m_dcache_select),
            self._dcache.s2_op.flush.eq(self.m_flush),
            self._dcache.s2_valid   .eq(self.m_valid),
        ]

        m.submodules.wrbuf = self._wrbuf
        m.d.comb += [
            self._wrbuf.w_en     .eq(self.x_store & self.x_valid & x_dcache_select & self.x_ready),
            self._wrbuf.w_op.addr.eq(self.x_addr[2:]),
            self._wrbuf.w_op.mask.eq(self.x_mask),
            self._wrbuf.w_op.data.eq(self.x_store_data),
        ]

        dbus_arbiter = m.submodules.dbus_arbiter = WishboneArbiter()
        connect(m, dbus_arbiter.bus, flipped(self.dbus))

        wrbuf_port = dbus_arbiter.port(priority=0)
        m.d.comb += [
            wrbuf_port.cyc.eq(self._wrbuf.r_rdy),
            wrbuf_port.we.eq(Const(1)),
        ]
        with m.If(wrbuf_port.stb):
            with m.If(wrbuf_port.ack | wrbuf_port.err):
                m.d.sync += wrbuf_port.stb.eq(0)
                m.d.comb += self._wrbuf.r_en.eq(1)
        with m.Elif(self._wrbuf.r_rdy):
            m.d.sync += [
                wrbuf_port.stb  .eq(1),
                wrbuf_port.adr  .eq(self._wrbuf.r_op.addr),
                wrbuf_port.sel  .eq(self._wrbuf.r_op.mask),
                wrbuf_port.dat_w.eq(self._wrbuf.r_op.data),
            ]

        dcache_port = dbus_arbiter.port(priority=1)
        m.d.comb += [
            dcache_port.cyc.eq(self._dcache.bus_req),
            dcache_port.stb.eq(self._dcache.bus_req),
            dcache_port.adr.eq(self._dcache.bus_addr),
            dcache_port.sel.eq(0b1111),
            dcache_port.cti.eq(Mux(self._dcache.bus_last, CycleType.END_OF_BURST, CycleType.INCR_BURST)),
            dcache_port.bte.eq(Const(ceil_log2(self._dcache.nwords) - 1)),
            self._dcache.bus_ack .eq(dcache_port.ack | dcache_port.err),
            self._dcache.bus_data.eq(dcache_port.dat_r)
        ]

        bare_port = dbus_arbiter.port(priority=2)
        bare_rdata = Signal.like(bare_port.dat_r)
        with m.If(bare_port.cyc):
            with m.If(bare_port.ack | bare_port.err):
                m.d.sync += [
                    bare_port.cyc.eq(0),
                    bare_port.stb.eq(0),
                    bare_rdata.eq(bare_port.dat_r)
                ]
        with m.Elif((self.x_load | self.x_store) & ~x_dcache_select & self.x_valid & self.x_ready):
            m.d.sync += [
                bare_port.cyc.eq(1),
                bare_port.stb.eq(1),
                bare_port.adr.eq(self.x_addr[2:]),
                bare_port.sel.eq(self.x_mask),
                bare_port.we.eq(self.x_store),
                bare_port.dat_w.eq(self.x_store_data)
            ]

        with m.If(self.dbus.cyc & self.dbus.err):
            m.d.sync += [
                self.m_load_error.eq(~self.dbus.we),
                self.m_store_error.eq(self.dbus.we),
                self.m_badaddr.eq(self.dbus.adr)
            ]
        with m.Elif(self.m_ready):
            m.d.sync += [
                self.m_load_error.eq(0),
                self.m_store_error.eq(0)
            ]

        with m.If(self.x_fence_i):
            m.d.comb += self.x_busy.eq(self._wrbuf.r_rdy)
        with m.Elif(x_dcache_select):
            m.d.comb += self.x_busy.eq(self.x_store & ~self._wrbuf.w_rdy)
        with m.Else():
            m.d.comb += self.x_busy.eq(bare_port.cyc)

        with m.If(m_dcache_select):
            m.d.comb += self.m_busy.eq(self._dcache.s2_busy)
        with m.Else():
            m.d.comb += self.m_busy.eq(bare_port.cyc)

        with m.If(self.m_load_error):
            m.d.comb += self.m_load_data.eq(0)
        with m.Elif(m_dcache_select):
            m.d.comb += self.m_load_data.eq(self._dcache.s2_data)
        with m.Else():
            m.d.comb += self.m_load_data.eq(bare_rdata)

        return m
