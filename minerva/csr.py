from enum import Enum

from nmigen import *
from nmigen.hdl.rec import *

from .reg import *


__all__ = ["CSRAccess", "CSR", "AutoCSR", "CSRFile"]


CSRAccess = Enum("CSRAccess", ("WIRI", "WPRI", "WLRL", "WARL"))


class _CSRLayout(Layout):
    def __init__(self, fields):
        super().__init__([(name, shape) for name, shape, *_ in fields])
        self.params = dict()
        for name, shape, access in fields:
            self.params[name] = access


class CSR(RegisterBase):
    def __init__(self, addr, fields, name=None):
        self.layout = _CSRLayout(fields)
        width = sum(f[1] for f in fields)
        super().__init__(addr, width, name)
        self.re = Signal(name=f"{self.name}_re")
        self.r  = Record(self.layout, name=f"{self.name}_r")
        self.we = Signal(name=f"{self.name}_we")
        self.w  = Record(self.layout, name=f"{self.name}_w")


class AutoCSR:
    def get_csrs(self):
        csrs = []
        for v in vars(self).values():
            if not isinstance(v, Value):
                if isinstance(v, CSR):
                    csrs.append(v)
                elif hasattr(v, "get_csrs"):
                    csrs += getattr(v, "get_csrs")()
        return csrs


class CSRFile(Elaboratable, RegisterFileBase):
    def __init__(self, source, width=32, depth=2**12):
        super().__init__(source, width, depth)

    def elaborate(self, platform):
        m = Module()

        self.scan("get_csrs")

        def do_read(csr, rp):
            dat_r = Record(csr.layout)
            m.d.comb += rp.data.eq(dat_r)
            for name, field in csr.r.fields.items():
                access = csr.layout.params[name]
                if access in {CSRAccess.WLRL, CSRAccess.WARL}:
                    m.d.comb += dat_r[name].eq(field)
                else:
                    m.d.comb += dat_r[name].eq(Const(0))
            m.d.comb += csr.re.eq(rp.en)

        def do_write(csr, wp):
            dat_w = Record(csr.layout)
            m.d.comb += dat_w.eq(wp.data)
            for name, field in csr.w.fields.items():
                access = csr.layout.params[name]
                if access in {CSRAccess.WLRL, CSRAccess.WARL}:
                    m.d.comb += field.eq(dat_w[name])
                else:
                    m.d.comb += field.eq(csr.r[name])
            m.d.comb += csr.we.eq(wp.en)

        for rp in self._read_ports:
            with m.Switch(rp.addr):
                for addr, csr in self._register_map.items():
                    with m.Case(addr):
                        do_read(csr, rp)

        for wp in self._write_ports:
            with m.Switch(wp.addr):
                for addr, csr in self._register_map.items():
                    with m.Case(addr):
                        do_write(csr, wp)

        return m
