from nmigen import *
from nmigen.hdl.rec import *
from nmigen.lib.coding import *

from nmigen_soc import wishbone


__all__ = ["WishbonePriorityArbiter"]


class WishbonePriorityArbiter(Elaboratable):
    def __init__(self, bus):
        if not isinstance(bus, wishbone.Interface):
            raise ValueError("Bus must be an instance of wishbone.Interface, not {!r}"
                             .format(bus))
        self.bus = bus
        self._port_map = dict()

    def port(self, priority):
        if not isinstance(priority, int) or priority < 0:
            raise TypeError("Priority must be a non-negative integer, not '{!r}'"
                            .format(priority))
        if priority in self._port_map:
            raise ValueError("Conflicting priority: '{!r}'".format(priority))
        port = wishbone.Interface.like(self.bus)
        self._port_map[priority] = port
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
        ]
        if hasattr(self.bus, "cti"):
            m.d.comb += self.bus.cti.eq(source.cti)
        if hasattr(self.bus, "bte"):
            m.d.comb += self.bus.bte.eq(source.bte)

        m.d.comb += source.ack.eq(self.bus.ack)
        if hasattr(self.bus, "err"):
            m.d.comb += source.err.eq(self.bus.err)

        return m
