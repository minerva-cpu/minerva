from amaranth import *

from .mem import ForwardingMemory


__all__ = ["File"]


class File(Elaboratable):
    def __init__(self, *, width, depth, init=None, name=None, attrs=None):
        self._mem  = ForwardingMemory(width=width, depth=depth, init=init, name=name, attrs=attrs)
        self.rp1   = self._mem.read_port()
        self.rp2   = self._mem.read_port()
        self.wp    = self._mem.write_port()

        self.width = self._mem.width
        self.depth = self._mem.depth
        self.attrs = self._mem.attrs
        self.init  = self._mem.init

    def elaborate(self, platform):
        m = Module()
        m.submodules.mem = self._mem
        return m
