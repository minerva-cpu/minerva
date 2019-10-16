from nmigen import *
from nmigen.utils import log2_int
from nmigen.lib.fifo import SyncFIFO

from ..cache import *
from ..isa import Funct3
from ..wishbone import *


__all__ = ["DataSelector", "LoadStoreUnitInterface", "BareLoadStoreUnit", "CachedLoadStoreUnit"]


class DataSelector(Elaboratable):
    def __init__(self):
        self.x_offset = Signal(2)
        self.x_funct3 = Signal(3)
        self.x_store_operand = Signal(32)
        self.w_offset = Signal(2)
        self.w_funct3 = Signal(3)
        self.w_load_data = Signal(32)

        self.x_misaligned = Signal()
        self.x_mask = Signal(4)
        self.x_store_data = Signal(32)
        self.w_load_result = Signal((32, True))

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

        w_byte = Signal((8, True))
        w_half = Signal((16, True))

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


class LoadStoreUnitInterface:
    def __init__(self):
        self.dbus = Record(wishbone_layout)

        self.x_addr = Signal(32)
        self.x_mask = Signal(4)
        self.x_load = Signal()
        self.x_store = Signal()
        self.x_store_data = Signal(32)
        self.x_stall = Signal()
        self.x_valid = Signal()
        self.m_stall = Signal()
        self.m_valid = Signal()

        self.x_busy = Signal()
        self.m_busy = Signal()
        self.m_load_data = Signal(32)
        self.m_load_error = Signal()
        self.m_store_error = Signal()
        self.m_badaddr = Signal(30)


class BareLoadStoreUnit(LoadStoreUnitInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        with m.If(self.dbus.cyc):
            with m.If(self.dbus.ack | self.dbus.err | ~self.m_valid):
                m.d.sync += [
                    self.dbus.cyc.eq(0),
                    self.dbus.stb.eq(0),
                    self.m_load_data.eq(self.dbus.dat_r)
                ]
        with m.Elif((self.x_load | self.x_store) & self.x_valid & ~self.x_stall):
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
        with m.Elif(~self.m_stall):
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


class CachedLoadStoreUnit(LoadStoreUnitInterface, Elaboratable):
    def __init__(self, *dcache_args):
        super().__init__()

        self.dcache_args = dcache_args

        self.x_fence_i = Signal()
        self.x_flush = Signal()
        self.m_addr = Signal(32)
        self.m_load = Signal()
        self.m_store = Signal()

    def elaborate(self, platform):
        m = Module()

        dcache = m.submodules.dcache = L1Cache(*self.dcache_args)

        x_dcache_select = Signal()
        m_dcache_select = Signal()

        m.d.comb += x_dcache_select.eq((self.x_addr >= dcache.base) & (self.x_addr < dcache.limit))
        with m.If(~self.x_stall):
            m.d.sync += m_dcache_select.eq(x_dcache_select)

        m.d.comb += [
            dcache.s1_addr.eq(self.x_addr[2:]),
            dcache.s1_flush.eq(self.x_flush),
            dcache.s1_stall.eq(self.x_stall),
            dcache.s1_valid.eq(self.x_valid & x_dcache_select),
            dcache.s2_addr.eq(self.m_addr[2:]),
            dcache.s2_re.eq(self.m_load),
            dcache.s2_evict.eq(self.m_store),
            dcache.s2_valid.eq(self.m_valid & m_dcache_select)
        ]

        wrbuf_din  = Record([("addr", 30), ("mask", 4), ("data", 32)])
        wrbuf_dout = Record.like(wrbuf_din)
        wrbuf = m.submodules.wrbuf = SyncFIFO(width=len(wrbuf_din), depth=dcache.nwords)
        m.d.comb += [
            wrbuf.din.eq(wrbuf_din),
            wrbuf_din.addr.eq(self.x_addr[2:]),
            wrbuf_din.mask.eq(self.x_mask),
            wrbuf_din.data.eq(self.x_store_data),
            wrbuf.we.eq(self.x_store & self.x_valid & x_dcache_select & ~self.x_stall),
            wrbuf_dout.eq(wrbuf.dout),
        ]

        dbus_arbiter = m.submodules.dbus_arbiter = WishboneArbiter()
        m.d.comb += dbus_arbiter.bus.connect(self.dbus)

        wrbuf_port = dbus_arbiter.port(priority=0)
        with m.If(wrbuf_port.cyc):
            with m.If(wrbuf_port.ack | wrbuf_port.err):
                m.d.sync += [
                    wrbuf_port.cyc.eq(0),
                    wrbuf_port.stb.eq(0)
                ]
                m.d.comb += wrbuf.re.eq(1)
        with m.Elif(wrbuf.readable):
            m.d.sync += [
                wrbuf_port.cyc.eq(1),
                wrbuf_port.stb.eq(1),
                wrbuf_port.adr.eq(wrbuf_dout.addr),
                wrbuf_port.sel.eq(wrbuf_dout.mask),
                wrbuf_port.dat_w.eq(wrbuf_dout.data)
            ]
        m.d.comb += wrbuf_port.we.eq(Const(1))

        dcache_port = dbus_arbiter.port(priority=1)
        m.d.comb += [
            dcache_port.cyc.eq(dcache.bus_re),
            dcache_port.stb.eq(dcache.bus_re),
            dcache_port.adr.eq(dcache.bus_addr),
            dcache_port.cti.eq(Mux(dcache.bus_last, Cycle.END, Cycle.INCREMENT)),
            dcache_port.bte.eq(Const(log2_int(dcache.nwords) - 1)),
            dcache.bus_valid.eq(dcache_port.ack),
            dcache.bus_error.eq(dcache_port.err),
            dcache.bus_rdata.eq(dcache_port.dat_r)
        ]

        bare_port = dbus_arbiter.port(priority=2)
        bare_rdata = Signal.like(bare_port.dat_r)
        with m.If(bare_port.cyc):
            with m.If(bare_port.ack | bare_port.err | ~self.m_valid):
                m.d.sync += [
                    bare_port.cyc.eq(0),
                    bare_port.stb.eq(0),
                    bare_rdata.eq(bare_port.dat_r)
                ]
        with m.Elif((self.x_load | self.x_store) & ~x_dcache_select & self.x_valid & ~self.x_stall):
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
        with m.Elif(~self.m_stall):
            m.d.sync += [
                self.m_load_error.eq(0),
                self.m_store_error.eq(0)
            ]

        with m.If(self.x_fence_i):
            m.d.comb += self.x_busy.eq(wrbuf.readable)
        with m.Elif(x_dcache_select):
            m.d.comb += self.x_busy.eq(self.x_store & ~wrbuf.writable)
        with m.Else():
            m.d.comb += self.x_busy.eq(bare_port.cyc)

        with m.If(self.m_load_error | self.m_store_error):
            m.d.comb += [
                self.m_busy.eq(0),
                self.m_load_data.eq(0)
            ]
        with m.Elif(m_dcache_select):
            m.d.comb += [
                self.m_busy.eq(dcache.s2_re & dcache.s2_miss),
                self.m_load_data.eq(dcache.s2_rdata)
            ]
        with m.Else():
            m.d.comb += [
                self.m_busy.eq(bare_port.cyc),
                self.m_load_data.eq(bare_rdata)
            ]

        return m
