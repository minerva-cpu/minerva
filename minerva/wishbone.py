from amaranth import *
from amaranth.hdl.rec import *
from amaranth.lib.coding import *


__all__ = ["Cycle", "wishbone_layout", "WishboneArbiter"]


class Cycle:
    CLASSIC   = 0
    CONSTANT  = 1
    INCREMENT = 2
    END       = 7


wishbone_layout = [
    ("adr",   30, DIR_FANOUT),
    ("dat_w", 32, DIR_FANOUT),
    ("dat_r", 32, DIR_FANIN),
    ("sel",    4, DIR_FANOUT),
    ("cyc",    1, DIR_FANOUT),
    ("stb",    1, DIR_FANOUT),
    ("ack",    1, DIR_FANIN),
    ("we",     1, DIR_FANOUT),
    ("cti",    3, DIR_FANOUT),
    ("bte",    2, DIR_FANOUT),
    ("err",    1, DIR_FANIN)
]


class WishboneArbiter(Elaboratable):
    def __init__(self):
        self.bus = Record(wishbone_layout)
        self._port_map = dict()

    def port(self, priority):
        if not isinstance(priority, int) or priority < 0:
            raise TypeError("Priority must be a non-negative integer, not '{!r}'"
                            .format(priority))
        if priority in self._port_map:
            raise ValueError("Conflicting priority: '{!r}'".format(priority))
        port = self._port_map[priority] = Record.like(self.bus)
        return port

    def elaborate(self, platform):
        m = Module()

        ports = [port for priority, port in sorted(self._port_map.items())]

        for port in ports:
            m.d.comb += port.dat_r.eq(self.bus.dat_r)

        bus_pe = m.submodules.bus_pe = PriorityEncoder(len(ports))
        with m.If(~self.bus.cyc):
            for j, port in enumerate(ports):
                m.d.sync += bus_pe.i[j].eq(port.cyc)

        source = Array(ports)[bus_pe.o]
        m.d.comb += [
            self.bus.adr.eq(source.adr),
            self.bus.dat_w.eq(source.dat_w),
            self.bus.sel.eq(source.sel),
            self.bus.cyc.eq(source.cyc),
            self.bus.stb.eq(source.stb),
            self.bus.we.eq(source.we),
            self.bus.cti.eq(source.cti),
            self.bus.bte.eq(source.bte),
            source.ack.eq(self.bus.ack),
            source.err.eq(self.bus.err)
        ]

        return m
