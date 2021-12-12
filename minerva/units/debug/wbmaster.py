from functools import reduce
from operator import or_

from amaranth import *
from amaranth.hdl.rec import *

from ...wishbone import wishbone_layout
from .dmi import *


__all__ = ["BusError", "AccessSize", "DebugWishboneMaster"]


class BusError:
    NONE        = 0
    TIMEOUT     = 1
    BAD_ADDRESS = 2
    MISALIGNED  = 3
    BAD_SIZE    = 4
    OTHER       = 7


class AccessSize:
    BYTE = 0
    HALF = 1
    WORD = 2


class DebugWishboneMaster(Elaboratable):
    def __init__(self, debugrf):
        self.bus = Record(wishbone_layout)

        self.dbus_busy = Signal()

        self.sbcs       = debugrf.reg_port(DebugReg.SBCS)
        self.sbaddress0 = debugrf.reg_port(DebugReg.SBADDRESS0)
        self.sbdata0    = debugrf.reg_port(DebugReg.SBDATA0)

    def elaborate(self, platform):
        m = Module()

        addr = self.sbaddress0.w.value
        size = self.sbcs.r.sbaccess

        width = Signal(6)
        m.d.comb += width.eq((1<<size)*8)

        sbbusyerror = self.sbcs.w.sbbusyerror
        sberror = self.sbcs.w.sberror
        m.d.comb += self.dbus_busy.eq(self.sbcs.w.sbbusy)

        m.d.comb += [
            self.sbcs.w.sbaccess8.eq(1),
            self.sbcs.w.sbaccess16.eq(1),
            self.sbcs.w.sbaccess32.eq(1),
            self.sbcs.w.sbasize.eq(32),
            self.sbcs.w.sbversion.eq(1)
        ]

        with m.If(self.sbcs.update):
            m.d.sync += [
                self.sbcs.w.sbbusyerror.eq(self.sbcs.r.sbbusyerror),
                self.sbcs.w.sberror.eq(self.sbcs.r.sberror)
            ]

        we = Signal()
        re = Signal()

        with m.If(self.sbdata0.update):
            with m.If(self.sbcs.w.sbbusy):
                m.d.sync += self.sbcs.w.sbbusyerror.eq(1)
            with m.Else():
                m.d.sync += we.eq(~sberror.bool())

        with m.If(self.sbdata0.capture):
            with m.If(self.sbcs.w.sbbusy):
                m.d.sync += self.sbcs.w.sbbusyerror.eq(1)
            with m.Else():
                m.d.sync += re.eq(self.sbcs.r.sbreadondata & ~sberror.bool())

        with m.If(self.sbaddress0.update):
            with m.If(self.sbcs.w.sbbusy):
                m.d.sync += self.sbcs.w.sbbusyerror.eq(1)
            with m.Else():
                m.d.sync += [
                    re.eq(self.sbcs.r.sbreadonaddr & ~sberror.bool()),
                    self.sbaddress0.w.value.eq(self.sbaddress0.r.value)
                ]

        with m.FSM():
            with m.State("IDLE"):
                with m.If(we | re):
                    m.d.sync += we.eq(0), re.eq(0)
                    with m.If(size > AccessSize.WORD):
                        m.d.sync += sberror.eq(BusError.BAD_SIZE)
                    with m.Elif((addr & (1<<size)-1) != 0):
                        m.d.sync += sberror.eq(BusError.MISALIGNED)
                    with m.Else():
                        m.d.sync += [
                            self.bus.cyc.eq(1),
                            self.bus.stb.eq(1),
                            self.bus.adr.eq(addr[2:]),
                            self.bus.we.eq(we),
                            self.bus.sel.eq((1<<(1<<size))-1 << addr[:2]),
                            self.bus.dat_w.eq((self.sbdata0.r & (1<<width)-1) << addr[:2]*8)
                        ]
                        m.next = "BUSY"

            with m.State("BUSY"):
                m.d.comb += self.sbcs.w.sbbusy.eq(1)
                with m.If(self.bus.ack | self.bus.err):
                    m.d.sync += [
                        self.bus.cyc.eq(0),
                        self.bus.stb.eq(0),
                        self.bus.we.eq(0),
                    ]
                    with m.If(self.bus.err):
                        m.d.sync += sberror.eq(BusError.OTHER)
                    with m.Else():
                        with m.If(~self.bus.we):
                            m.d.sync += self.sbdata0.w.eq((self.bus.dat_r >> addr[:2]*8) & (1<<width)-1)
                        with m.If(self.sbcs.r.sbautoincrement):
                            m.d.sync += addr.eq(addr + (1<<size))
                    m.next = "IDLE"

        return m
