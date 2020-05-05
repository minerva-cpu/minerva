from enum import Enum
from collections import OrderedDict

from nmigen import *
from nmigen.utils import bits_for


__all__ = ["CSRAccess", "CSR", "AutoCSR", "CSRFile"]


class CSRAccess(Enum):
    RW = 0
    RO = 1


class CSR(Record):
    def __init__(self, addr, description, name=None, src_loc_at=0):
        fields = []
        mask   = 0
        offset = 0
        for fname, shape, access in description:
            if isinstance(shape, int):
                shape = shape, False
            width, signed = shape
            fields.append((fname, shape))
            if access is CSRAccess.RW:
                mask |= ((1 << width) - 1) << offset
            offset += width

        self.addr = addr
        self.mask = mask

        super().__init__([
            ("r",  fields),
            ("w",  fields),
            ("re", 1),
            ("we", 1),
        ], name=name, src_loc_at=1 + src_loc_at)


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
        port = Record([("addr", bits_for(self.depth)), ("en", 1), ("data", self.width)], name="rp")
        self._read_ports.append(port)
        return port

    def write_port(self):
        port = Record([("addr", bits_for(self.depth)), ("en", 1), ("data", self.width)], name="wp")
        self._write_ports.append(port)
        return port

    def elaborate(self, platform):
        m = Module()

        for rp in self._read_ports:
            with m.Switch(rp.addr):
                for addr, csr in self._csr_map.items():
                    with m.Case(addr):
                        m.d.comb += [
                            csr.re.eq(rp.en),
                            rp.data.eq(csr.r)
                        ]

        for wp in self._write_ports:
            with m.Switch(wp.addr):
                for addr, csr in self._csr_map.items():
                    with m.Case(addr):
                        m.d.comb += csr.we.eq(wp.en)
                        for i in range(self.width):
                            rw = (1 << i) & csr.mask
                            m.d.comb += csr.w[i].eq(wp.data[i] if rw else csr.r[i])

        return m
