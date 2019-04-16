from nmigen import *
from nmigen.tools import bits_for


__all__ = ["RegisterBase", "RegisterFileBase"]


class RegisterBase:
    def __init__(self, addr, width, name):
        self.addr = addr
        self.width = width
        self.name = name or tracer.get_var_name()


class RegisterFileBase:
    def __init__(self, source, width, depth):
        self.source = source
        self.width = width
        self.depth = depth
        self._register_map = dict()
        self._read_ports = []
        self._write_ports = []

    def scan(self, method):
        for submodule, name in self.source._submodules:
            if hasattr(submodule, method):
                for reg in getattr(submodule, method)():
                    if reg.addr in self._register_map:
                        raise ValueError(f"Address {reg.addr} cannot be used by multiple registers.")
                    self._register_map[reg.addr] = reg

    def read_port(self):
        port = Record([("addr", bits_for(self.depth)), ("en", 1), ("data", self.width)])
        self._read_ports.append(port)
        return port

    def write_port(self):
        port = Record([("addr", bits_for(self.depth)), ("en", 1), ("data", self.width)])
        self._write_ports.append(port)
        return port
