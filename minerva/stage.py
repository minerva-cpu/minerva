from functools import reduce
from operator import or_

from amaranth import *
from amaranth.hdl.rec import *


__all__ = ["Stage"]


def _force_fanout(layout):
    fields = []
    for name, shape, dir in Layout.cast(layout):
        if isinstance(shape, int):
            shape = Shape(shape)
        if isinstance(shape, Shape):
            fields.append((name, shape, DIR_FANOUT))
        else:
            fields.append((name, _force_fanout(shape)))
    return Layout(fields)


class _EndpointDescription:
    def __init__(self, payload_layout):
        self.payload_layout = Layout.cast(payload_layout)

    def get_full_layout(self):
        reserved = {"valid", "stall", "kill"}
        attributed = set()
        for name, shape, dir in self.payload_layout:
            if name in attributed:
                raise ValueError(name + " already attributed in payload layout")
            if name in reserved:
                raise ValueError(name + " cannot be used in endpoint layout")
            attributed.add(name)

        full_layout = [
            ("valid",   1, DIR_FANOUT),
            ("stall",   1, DIR_FANIN),
            ("kill",    1, DIR_FANOUT),
            ("payload", _force_fanout(self.payload_layout))
        ]
        return Layout(full_layout)


class _Endpoint(Record):
    def __init__(self, layout):
        self.description = _EndpointDescription(layout)
        super().__init__(self.description.get_full_layout())

    def __getattr__(self, name):
        try:
            return super().__getattr__(name)
        except AttributeError:
            return self.fields["payload"][name]


class Stage(Elaboratable):
    def __init__(self, sink_layout, source_layout):
        self.kill = Signal()
        self.stall = Signal()
        self.valid = Signal()

        if sink_layout is None and source_layout is None:
            raise ValueError
        if sink_layout is not None:
            self.sink = _Endpoint(sink_layout)
        if source_layout is not None:
            self.source = _Endpoint(source_layout)

        self._kill_sources = []
        self._stall_sources = []

    def kill_on(self, cond):
        self._kill_sources.append(cond)

    def stall_on(self, cond):
        self._stall_sources.append(cond)

    def elaborate(self, platform):
        m = Module()

        if hasattr(self, "sink"):
            m.d.comb += [
                self.valid.eq(self.sink.valid & ~self.sink.kill),
                self.sink.stall.eq(self.stall)
            ]

        if hasattr(self, "source"):
            with m.If(~self.stall):
                m.d.sync += self.source.valid.eq(self.valid)
            with m.Elif(~self.source.stall | self.kill):
                m.d.sync += self.source.valid.eq(0)
            self.stall_on(self.source.stall)
            m.d.comb += [
                self.source.kill.eq(self.kill),
                self.kill.eq(reduce(or_, self._kill_sources, 0))
            ]

        m.d.comb += self.stall.eq(reduce(or_, self._stall_sources, 0))

        return m
