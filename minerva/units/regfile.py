from nmigen import *
from nmigen.hdl.rec import *

from ..isa import *


__all__ = ["GPRFile", "CSRFile"]


class GPRFile:
    def __init__(self):
        self._read_ports = []
        self._write_ports = []

    def read_port(self):
        port = Record([("addr", 5), ("data", 32)])
        self._read_ports.append(port)
        return port

    def write_port(self):
        port = Record([("addr", 5), ("en", 1), ("data", 32)])
        self._write_ports.append(port)
        return port

    def elaborate(self, platform):
        m = Module()
        regs = Array(Signal(32) for _ in range(32))
        for rp in self._read_ports:
            m.d.comb += rp.data.eq(regs[rp.addr])
        for wp in self._write_ports:
            with m.If(wp.en):
                m.d.sync += regs[wp.addr].eq(wp.data)
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
    CSRIndex.IRQ_PENDING: flat_layout,
    CSRIndex.DCSR:        dcsr_layout,
    CSRIndex.DPC:         flat_layout,
}


class CSRFile:
    def __init__(self):
        self._read_ports = []
        self._write_ports = []
        self._csr_ports = []

    def read_port(self):
        port = Record([("addr", 12), ("data", 32)])
        self._read_ports.append(port)
        return port

    def write_port(self):
        port = Record([("addr", 12), ("en", 1), ("data", 32)])
        self._write_ports.append(port)
        return port

    def csr_port(self, addr):
        if addr not in _csr_map:
            raise ValueError("Unknown CSR address.")
        csr_port_layout = [
            ("dat_r", _csr_map[addr]),
            ("we",    1),
            ("dat_w", _csr_map[addr])
        ]
        port = Record(csr_port_layout)
        self._csr_ports.append((addr, port))
        return port

    def elaborate(self, platform):
        m = Module()
        regs = {addr: Signal(32) for addr in _csr_map}

        for rp in self._read_ports:
            with m.Switch(rp.addr):
                for addr in _csr_map:
                    with m.Case(addr):
                        m.d.comb += rp.data.eq(regs[addr])

        for wp in self._write_ports:
            with m.If(wp.en):
                with m.Switch(wp.addr):
                    for addr in _csr_map:
                        with m.Case(addr):
                            m.d.sync += regs[addr].eq(wp.data)

        for addr, port in self._csr_ports:
            m.d.comb += port.dat_r.eq(regs[addr])
            with m.If(port.we):
                m.d.sync += regs[addr].eq(port.dat_w)

        return m
