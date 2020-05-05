from nmigen import *
from nmigen.hdl.rec import *

from .dmi import *


__all__ = ["DebugRegisterFile"]


class DmiOp:
    NOP   = 0
    READ  = 1
    WRITE = 2


reg_map = {
    DebugReg.DMSTATUS:   dmstatus_layout,
    DebugReg.DMCONTROL:  dmcontrol_layout,
    DebugReg.HARTINFO:   flat_layout,
    DebugReg.ABSTRACTCS: abstractcs_layout,
    DebugReg.COMMAND:    command_layout,
    DebugReg.SBCS:       sbcs_layout,
    DebugReg.SBADDRESS0: flat_layout,
    DebugReg.SBDATA0:    flat_layout,
    DebugReg.DATA0:      flat_layout,
    DebugReg.HALTSUM0:   flat_layout,
    DebugReg.HALTSUM1:   flat_layout,
}


class DebugRegisterFile(Elaboratable):
    def __init__(self, dmi):
        self.dmi = dmi
        self.ports = dict()

    def reg_port(self, addr, name=None, src_loc_at=0):
        if addr not in reg_map:
            raise ValueError("Unknown register {:x}.".format(addr))
        if addr in self.ports:
            raise ValueError("Register {:x} has already been allocated.".format(addr))
        layout = [f[:2] for f in reg_map[addr]]
        port = Record([("r", layout), ("w", layout), ("update", 1), ("capture", 1)],
                      name=name, src_loc_at=1 + src_loc_at)
        for name, shape, mode, reset in reg_map[addr]:
            getattr(port.r, name).reset = reset
            getattr(port.w, name).reset = reset
        self.ports[addr] = port
        return port

    def elaborate(self, platform):
        m = Module()

        def do_read(addr, port):
            rec = Record(port.w.layout)
            m.d.sync += self.dmi.r.data.eq(rec)
            for name, shape, mode, reset in reg_map[addr]:
                dst = getattr(rec, name)
                src = getattr(port.w, name)
                if mode in {RegMode.R, RegMode.RW, RegMode.RW1C}:
                    m.d.comb += dst.eq(src)
                else:
                    m.d.comb += dst.eq(Const(0))
            m.d.sync += port.capture.eq(1)

        def do_write(addr, port):
            rec = Record(port.r.layout)
            m.d.comb += rec.eq(self.dmi.w.data)
            for name, shape, mode, reset in reg_map[addr]:
                dst = getattr(port.r, name)
                src = getattr(rec, name)
                if mode in {RegMode.W, RegMode.RW}:
                    m.d.sync += dst.eq(src)
                elif mode is RegMode.W1:
                    m.d.sync += dst.eq(getattr(port.w, name) | src)
                elif mode is RegMode.RW1C:
                    m.d.sync += dst.eq(getattr(port.w, name) & ~src)

            m.d.sync += port.update.eq(1)

        with m.If(self.dmi.update):
            with m.Switch(self.dmi.w.addr):
                for addr, port in self.ports.items():
                    with m.Case(addr):
                        with m.If(self.dmi.w.op == DmiOp.READ):
                            do_read(addr, port)
                        with m.Elif(self.dmi.w.op == DmiOp.WRITE):
                            do_write(addr, port)

        for port in self.ports.values():
            with m.If(port.update):
                m.d.sync += port.update.eq(0)
            with m.If(port.capture):
                m.d.sync += port.capture.eq(0)

        return m
