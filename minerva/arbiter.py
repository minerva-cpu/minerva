from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from amaranth_soc import wishbone


__all__ = ["WishboneArbiter"]


class WishboneArbiter(wiring.Component):
    bus: Out(wishbone.Signature(addr_width=30, data_width=32, granularity=8,
                                features=("err", "cti", "bte")))

    def __init__(self):
        self._port_map = dict()
        super().__init__()

    def port(self, priority):
        if not isinstance(priority, int) or priority < 0:
            raise TypeError("Priority must be a non-negative integer, not '{!r}'"
                            .format(priority))
        if priority in self._port_map:
            raise ValueError("Conflicting priority: '{!r}'".format(priority))
        port = wishbone.Interface(addr_width=30, data_width=32, granularity=8,
                                  features=("err", "cti", "bte"))
        self._port_map[priority] = port
        return port

    def elaborate(self, platform):
        m = Module()

        ports = [port for priority, port in sorted(self._port_map.items())]

        req = Signal(len(ports))
        gnt = Signal.like(req)

        with m.If(~self.bus.cyc):
            for i, port in enumerate(ports):
                m.d.sync += req[i].eq(port.cyc)

        m.d.comb += gnt.eq(req & (-req)) # isolate rightmost 1-bit

        bus_adr_mux   = 0
        bus_dat_w_mux = 0
        bus_sel_mux   = 0
        bus_cyc_mux   = 0
        bus_stb_mux   = 0
        bus_we_mux    = 0
        bus_cti_mux   = 0
        bus_bte_mux   = 0

        for i, port in enumerate(ports):
            bus_adr_mux   |= Mux(gnt[i], port.adr,   0)
            bus_dat_w_mux |= Mux(gnt[i], port.dat_w, 0)
            bus_sel_mux   |= Mux(gnt[i], port.sel,   0)
            bus_cyc_mux   |= Mux(gnt[i], port.cyc,   0)
            bus_stb_mux   |= Mux(gnt[i], port.stb,   0)
            bus_we_mux    |= Mux(gnt[i], port.we,    0)
            bus_cti_mux   |= Mux(gnt[i], port.cti,   0)
            bus_bte_mux   |= Mux(gnt[i], port.bte,   0)

            m.d.comb += [
                port.dat_r.eq(self.bus.dat_r),
                port.ack  .eq(self.bus.ack & gnt[i]),
                port.err  .eq(self.bus.err & gnt[i]),
            ]

        m.d.comb += [
            self.bus.adr  .eq(bus_adr_mux),
            self.bus.dat_w.eq(bus_dat_w_mux),
            self.bus.sel  .eq(bus_sel_mux),
            self.bus.cyc  .eq(bus_cyc_mux),
            self.bus.stb  .eq(bus_stb_mux),
            self.bus.we   .eq(bus_we_mux),
            self.bus.cti  .eq(bus_cti_mux),
            self.bus.bte  .eq(bus_bte_mux),
        ]

        return m
