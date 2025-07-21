from amaranth import *
from amaranth.lib import stream, wiring
from amaranth.lib.wiring import In, Out


__all__ = ["Stage"]


class Stage(wiring.Component):
    """Pipeline stage component.

    Arguments
    ---------
    sink_layout : :class:`Layout`
        Data received from the previous pipeline stage, if any.
    source_layout : :class:`Layout`
        Data sent to the next pipeline stage, if any.
    sink_init
        Initial value of the payload data received from the previous pipeline
        stage.
    source_init
        Initial value of the payload data sent to the next pipeline stage.

    Members
    -------
    valid : ``Out(1)``
        High when the previous pipeline stage, if any, was not 'killed' last
        cycle and this stage is not 'killed' this cycle.
    ready : ``Out(1)``
        High when the next pipeline stage, if any, is not stalled this cycle and
        this stage is not 'stalled' this cycle.
    sink : ``In(stream.Signature(sink_layout, payload_init=sink_init))``
        Stream connection to the previous pipeline stage.
    source : ``Out(stream.Signature(source_layout, payload_init=source_init))``
        Stream connection to the next pipeline stage.
    """
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
