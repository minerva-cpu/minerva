from nmigen import *
from nmigen.hdl.rec import *

from ..isa import *


__all__ = ["GPRFile", "CSRFile"]


class GPRFile:
    def __init__(self):
        self.rp1 = Record([("addr", 5), ("data", 32)])
        self.rp2 = Record(self.rp1.layout)
        self.wp  = Record([("addr", 5), ("en", 1), ("data", 32)])

    def elaborate(self, platform):
        m = Module()
        regs = Array(Signal(32) for _ in range(32))
        for rp in (self.rp1, self.rp2):
            m.d.comb += rp.data.eq(regs[rp.addr])
        with m.If(self.wp.en):
            m.d.sync += regs[self.wp.addr].eq(self.wp.data)
        return m


_csr_map = {
    CSRIndex.MVENDORID:   flat_layout,
    CSRIndex.MARCHID:     flat_layout,
    CSRIndex.MIMPID:      flat_layout,
    CSRIndex.MHARTID:     flat_layout,
    CSRIndex.MSTATUS:     mstatus_layout,
    CSRIndex.MISA:        misa_layout,
    CSRIndex.MIE:         mie_layout,
    CSRIndex.MTVEC:       mtvec_layout,
    CSRIndex.MSCRATCH:    flat_layout,
    CSRIndex.MEPC:        flat_layout,
    CSRIndex.MCAUSE:      mcause_layout,
    CSRIndex.MTVAL:       flat_layout,
    CSRIndex.MIP:         mip_layout,
    CSRIndex.IRQ_MASK:    flat_layout,
    CSRIndex.IRQ_PENDING: flat_layout
}


class CSRFile:
    def __init__(self):
        self.rp = Record([("addr", 12), ("data", 32)])
        self.wp = Record([("addr", 12), ("en", 1), ("data", 32)])
        self._ports = []

    def get_csr_port(self, addr):
        if addr not in _csr_map:
            raise ValueError("Unknown CSR address.")
        csr_port_layout = [
            ("dat_r", _csr_map[addr]),
            ("we",    1),
            ("dat_w", _csr_map[addr])
        ]
        port = Record(csr_port_layout)
        self._ports.append((addr, port))
        return port

    def elaborate(self, platform):
        m = Module()
        regs = {addr: Signal(32) for addr in _csr_map}

        with m.Switch(self.rp.addr):
            for addr in _csr_map:
                with m.Case(addr):
                    m.d.comb += self.rp.data.eq(regs[addr])

        with m.If(self.wp.en):
            with m.Switch(self.wp.addr):
                for addr in _csr_map:
                    with m.Case(addr):
                        m.d.sync += regs[addr].eq(self.wp.data)

        for addr, rec in self._ports:
            m.d.comb += rec.dat_r.eq(regs[addr])
            with m.If(rec.we):
                m.d.sync += regs[addr].eq(rec.dat_w)

        return m
