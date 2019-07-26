from enum import Enum
from collections import OrderedDict

from nmigen import *
from nmigen.hdl.rec import *
from nmigen.tools import bits_for


__all__ = ["CSRAccess", "CSR", "AutoCSR", "CSRFile"]


CSRAccess = Enum("CSRAccess", ("WIRI", "WPRI", "WLRL", "WARL"))


class CSR():
    def __init__(self, addr, description, name=None):
        self.addr = addr
        self.access = OrderedDict()
        fields = []
        for name, shape, access in description:
            fields.append((name, shape))
            self.access[name] = access
        self.r = Record(fields)
        self.w = Record(fields)
        self.re = Signal()
        self.we = Signal()


class AutoCSR():
    def iter_csrs(self):
        for v in vars(self).values():
            if isinstance(v, CSR):
                yield v
            elif hasattr(v, "iter_csrs"):
                yield from v.iter_csrs()


class CSRFile(Elaboratable):
    def __init__(self, width=32, depth=2**12):
        self.width = width
        self.depth = depth
        self._csr_map = OrderedDict()
        self._read_ports = []
        self._write_ports = []

    def add_csrs(self, csrs):
        for csr in csrs:
            if not isinstance(csr, CSR):
                raise TypeError("Object {!r} is not a CSR".format(csr))
            if csr.addr in self._csr_map:
                raise ValueError("CSR address 0x{:x} has already been allocated"
                                 .format(csr.addr))
            self._csr_map[csr.addr] = csr

    def read_port(self):
        port = Record([("addr", bits_for(self.depth)), ("en", 1), ("data", self.width)])
        self._read_ports.append(port)
        return port

    def write_port(self):
        port = Record([("addr", bits_for(self.depth)), ("en", 1), ("data", self.width)])
        self._write_ports.append(port)
        return port

    def elaborate(self, platform):
        m = Module()

        def do_read(csr, rp):
            dat_r = Record.like(csr.r)
            m.d.comb += rp.data.eq(dat_r)
            for name, field in csr.r.fields.items():
                access = csr.access[name]
                if access in {CSRAccess.WLRL, CSRAccess.WARL}:
                    m.d.comb += dat_r[name].eq(field)
                else:
                    m.d.comb += dat_r[name].eq(Const(0))
            m.d.comb += csr.re.eq(rp.en)

        def do_write(csr, wp):
            dat_w = Record.like(csr.w)
            m.d.comb += dat_w.eq(wp.data)
            for name, field in csr.w.fields.items():
                access = csr.access[name]
                if access in {CSRAccess.WLRL, CSRAccess.WARL}:
                    m.d.comb += field.eq(dat_w[name])
                else:
                    m.d.comb += field.eq(csr.r[name])
            m.d.comb += csr.we.eq(wp.en)

        for rp in self._read_ports:
            with m.Switch(rp.addr):
                for addr, csr in self._csr_map.items():
                    with m.Case(addr):
                        do_read(csr, rp)

        for wp in self._write_ports:
            with m.Switch(wp.addr):
                for addr, csr in self._csr_map.items():
                    with m.Case(addr):
                        do_write(csr, wp)

        return m
