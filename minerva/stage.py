from amaranth import *
from amaranth.lib import stream, wiring
from amaranth.lib.wiring import In, Out


__all__ = ["Stage"]


class Stage(wiring.Component):
    def __init__(self, sink_layout, source_layout, *, sink_init=None, source_init=None):
        self._kill_any  = 0
        self._stall_any = 0

        members = {
            "valid": Out(1),
            "ready": Out(1),
        }
        if sink_layout is not None:
            members["sink"] = In(stream.Signature(sink_layout, payload_init=sink_init))
        if source_layout is not None:
            members["source"] = Out(stream.Signature(source_layout, payload_init=source_init))

        super().__init__(members)

    def kill_on(self, expr):
        self._kill_any |= expr

    def stall_on(self, expr):
        self._stall_any |= expr

    def elaborate(self, platform):
        m = Module()

        if hasattr(self, "sink"):
            m.d.comb += self.sink.ready.eq(self.ready)
            m.d.comb += self.valid.eq(self.sink.valid & ~self._kill_any)
        else:
            m.d.comb += self.valid.eq(~self._kill_any)

        if hasattr(self, "source"):
            with m.If(self.ready):
                m.d.sync += self.source.valid.eq(self.valid)
            with m.Elif(self.source.ready):
                m.d.sync += self.source.valid.eq(0)

            m.d.comb += self.ready.eq(self.source.ready & ~self._stall_any)
        else:
            m.d.comb += self.ready.eq(~self._stall_any)

        return m
