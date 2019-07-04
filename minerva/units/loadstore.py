from operator import or_

from nmigen import *
from nmigen.hdl.rec import *
from nmigen.lib.fifo import SyncFIFO

from ..cache import L1Cache
from ..isa import Funct3
from ..wishbone import Cycle, wishbone_layout


__all__ = ["SimpleLoadStoreUnit", "CachedLoadStoreUnit"]


class _LoadStoreUnitBase(Elaboratable):
    def __init__(self):
        self.dbus = Record(wishbone_layout)

        self.x_address = Signal(32)
        self.x_load = Signal()
        self.x_store = Signal()
        self.x_store_operand = Signal(32)
        self.x_mask = Signal(3)
        self.x_stall = Signal()
        self.x_valid = Signal()
        self.w_address = Signal(32)
        self.w_load_mask = Signal(3)
        self.w_load_data = Signal(32)

        self.x_dbus_sel = Signal(4)
        self.x_store_data = Signal(32)
        self.m_bus_error = Signal()
        self.m_load_data = Signal(32)
        self.w_load_result = Signal((32, True))

    def elaborate(self, platform):
        m = Module()

        x_offset = Signal(2)
        m.d.comb += x_offset.eq(self.x_address[:2])

        with m.Switch(self.x_mask[:2]):
            with m.Case(Funct3.B):
                m.d.comb += [
                    self.x_dbus_sel.eq(1 << x_offset),
                    self.x_store_data.eq(self.x_store_operand[:8] << x_offset*8)
                ]
            with m.Case(Funct3.H):
                m.d.comb += [
                    self.x_dbus_sel.eq(3 << x_offset),
                    self.x_store_data.eq(self.x_store_operand[:16] << x_offset*8)
                ]
            with m.Case(Funct3.W):
                m.d.comb += [
                    self.x_dbus_sel.eq(15),
                    self.x_store_data.eq(self.x_store_operand)
                ]

        w_offset = Signal(2)
        w_byte   = Signal((8, True))
        w_half   = Signal((16, True))
        m.d.comb += [
            w_offset.eq(self.w_address[:2]),
            w_byte.eq(self.w_load_data.part(w_offset*8, 8)),
            w_half.eq(self.w_load_data.part(w_offset*8, 16))
        ]

        with m.Switch(self.w_load_mask):
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


class SimpleLoadStoreUnit(_LoadStoreUnitBase):
    def elaborate(self, platform):
        m = Module()
        m.submodules += super().elaborate(platform)

        with m.If(self.dbus.cyc):
            with m.If(self.dbus.ack | self.dbus.err):
                m.d.sync += [
                    self.dbus.cyc.eq(0),
                    self.dbus.stb.eq(0),
                    self.m_load_data.eq(self.dbus.dat_r)
                ]
            m.d.sync += self.m_bus_error.eq(self.dbus.err)
        with m.Elif(self.x_valid & ~self.x_stall):
            with m.If(self.x_store):
                m.d.sync += [
                    self.dbus.cyc.eq(1),
                    self.dbus.stb.eq(1),
                    self.dbus.we.eq(1),
                    self.dbus.adr.eq(self.x_address[2:]),
                    self.dbus.dat_w.eq(self.x_store_data),
                    self.dbus.sel.eq(self.x_dbus_sel)
                ]
            with m.Elif(self.x_load):
                m.d.sync += [
                    self.dbus.cyc.eq(1),
                    self.dbus.stb.eq(1),
                    self.dbus.we.eq(0),
                    self.dbus.adr.eq(self.x_address[2:]),
                    self.dbus.sel.eq(self.x_dbus_sel)
                ]

        return m


class CachedLoadStoreUnit(_LoadStoreUnitBase):
    def __init__(self, *dcache_args):
        super().__init__()

        self.m_address = Signal(32)
        self.m_load = Signal()
        self.m_store = Signal()
        self.m_dbus_sel = Signal(4)
        self.m_store_data = Signal(32)
        self.m_stall = Signal()
        self.m_valid = Signal()

        self.x_dcache_select = Signal()
        self.m_dcache_select = Signal()

        self.dcache = L1Cache(*dcache_args)
        self.wrbuf_din = Record([("adr", 30), ("sel", 4), ("dat_w", 32)])
        self.wrbuf = SyncFIFO(len(self.wrbuf_din), self.dcache.nb_words)

    def elaborate(self, platform):
        m = Module()
        m.submodules += super().elaborate(platform)

        dcache = m.submodules.dcache = self.dcache
        m.d.comb += [
            dcache.s1_address.eq(self.x_address[2:]),
            dcache.s1_stall.eq(self.x_stall),
            dcache.s2_address.eq(self.m_address[2:]),
            dcache.s2_stall.eq(self.m_stall),
            dcache.s2_re.eq(self.m_load & self.m_valid & self.m_dcache_select),
            dcache.s2_we.eq(self.m_store & self.m_valid & self.m_dcache_select),
            dcache.s2_sel.eq(Mux(self.m_dbus_sel == 0, 0b1111, self.m_dbus_sel)),
            dcache.s2_dat_w.eq(self.m_store_data),
            dcache.refill_address.eq(self.dbus.adr),
            dcache.refill_valid.eq(self.dbus.cyc & ~self.dbus.we & self.dbus.ack),
            dcache.refill_data.eq(self.dbus.dat_r),
            self.x_dcache_select.eq((self.x_address >= dcache.base) & (self.x_address < dcache.limit))
        ]

        with m.If(~self.x_stall):
            m.d.sync += self.m_dcache_select.eq(self.x_dcache_select)

        dbus_load_data = Signal.like(self.dbus.dat_r)
        m.d.comb += self.m_load_data.eq(Mux(self.m_dcache_select, dcache.s2_dat_r, dbus_load_data))

        wrbuf_din = self.wrbuf_din
        wrbuf_dout = Record(wrbuf_din.layout)
        wrbuf = m.submodules.wrbuf = self.wrbuf
        m.d.comb += [
            wrbuf_din.adr.eq(self.m_address[2:]),
            wrbuf_din.sel.eq(self.m_dbus_sel),
            wrbuf_din.dat_w.eq(self.m_store_data),
            wrbuf.din.eq(wrbuf_din),
            wrbuf_dout.eq(wrbuf.dout),
            wrbuf.we.eq(self.m_store & self.m_dcache_select & self.m_valid & ~self.m_stall),
            dcache.refill_ready.eq(~wrbuf.readable & ~(self.dbus.cyc & self.dbus.we))
        ]

        next_offset = Signal(dcache.offsetbits)
        last_offset = Signal(dcache.offsetbits)
        next_cti = Signal(3)
        m.d.comb += [
            next_offset.eq(self.dbus.adr[:dcache.offsetbits]+1),
            next_cti.eq(Mux(next_offset == last_offset, Cycle.END, Cycle.INCREMENT)),
            dcache.last_refill.eq(self.dbus.adr[:dcache.offsetbits] == last_offset),
            self.dbus.bte.eq(dcache.offsetbits-1)
        ]

        with m.If(self.dbus.cyc):
            with m.If(self.dbus.ack | self.dbus.err):
                with m.If(self.dbus.cti == Cycle.END):
                    m.d.sync += [
                        self.dbus.cyc.eq(0),
                        self.dbus.stb.eq(0),
                        self.dbus.sel.eq(0),
                        self.dbus.we.eq(0),
                        dbus_load_data.eq(self.dbus.dat_r)
                    ]
                with m.Else():
                    m.d.sync += [
                        self.dbus.adr[:dcache.offsetbits].eq(next_offset),
                        self.dbus.cti.eq(next_cti),
                    ]
                m.d.sync += self.m_bus_error.eq(self.dbus.err)
        with m.Elif(wrbuf.readable):
            m.d.comb += wrbuf.re.eq(1)
            m.d.sync += [
                self.dbus.adr.eq(wrbuf_dout.adr),
                self.dbus.sel.eq(wrbuf_dout.sel),
                self.dbus.dat_w.eq(wrbuf_dout.dat_w),
                self.dbus.cti.eq(Cycle.END),
                self.dbus.cyc.eq(1),
                self.dbus.stb.eq(1),
                self.dbus.we.eq(1)
            ]
        with m.Elif(dcache.refill_request):
            m.d.sync += [
                last_offset.eq(dcache.s2_address[:dcache.offsetbits]-1),
                self.dbus.adr.eq(dcache.s2_address),
                self.dbus.cti.eq(Cycle.INCREMENT),
                self.dbus.cyc.eq(1),
                self.dbus.stb.eq(1)
            ]
        with m.Elif(~self.x_dcache_select & self.x_valid & ~self.x_stall):
            with m.If(self.x_store):
                m.d.sync += [
                    self.dbus.adr.eq(self.x_address[2:]),
                    self.dbus.sel.eq(self.x_dbus_sel),
                    self.dbus.dat_w.eq(self.x_store_data),
                    self.dbus.cti.eq(Cycle.END),
                    self.dbus.cyc.eq(1),
                    self.dbus.stb.eq(1),
                    self.dbus.we.eq(1)
                ]
            with m.Elif(self.x_load):
                m.d.sync += [
                    self.dbus.adr.eq(self.x_address[2:]),
                    self.dbus.sel.eq(self.x_dbus_sel),
                    self.dbus.cti.eq(Cycle.END),
                    self.dbus.cyc.eq(1),
                    self.dbus.stb.eq(1)
                ]

        return m
