from functools import reduce
from operator import or_

from amaranth import *
from amaranth.hdl.rec import *

from ..csr import *
from ..isa import *


__all__ = ["TriggerUnit"]


class Type:
    NOP        = 0
    LEGACY     = 1
    MATCH      = 2
    INSN_COUNT = 3
    INTERRUPT  = 4
    EXCEPTION  = 5


mcontrol_layout = [
    ("load",    1),
    ("store",   1),
    ("execute", 1),
    ("u",       1),
    ("s",       1),
    ("zero0",   1),
    ("m",       1),
    ("match",   4),
    ("chain",   1),
    ("action",  4),
    ("size",    2),
    ("timing",  1),
    ("select",  1),
    ("hit",     1),
    ("maskmax", 6)
]


class TriggerUnit(Elaboratable, AutoCSR):
    def __init__(self, nb_triggers):
        if not isinstance(nb_triggers, int):
            raise TypeError("Number of triggers must be an int, not {!r}"
                            .format(nb_triggers))
        if nb_triggers == 0 or nb_triggers & nb_triggers - 1:
            raise ValueError("Number of triggers must be a power of 2, not {!r}"
                             .format(nb_triggers))
        self.nb_triggers = nb_triggers

        self.tselect = CSR(0x7a0, flat_layout)
        self.tdata1  = CSR(0x7a1, tdata1_layout)
        self.tdata2  = CSR(0x7a2, flat_layout)

        self.x_pc = Signal(32)
        self.x_valid = Signal()

        self.haltreq = Signal()
        self.x_trap = Signal()

    def elaborate(self, platform):
        m = Module()

        triggers = [Record.like(self.tdata1.r) for _ in range(self.nb_triggers)]
        for t in triggers:
            # We only support address/data match triggers.
            m.d.comb += t.type.eq(Type.MATCH)

        def do_trigger_update(trigger):
            m.d.sync += trigger.dmode.eq(self.tdata1.w.dmode)
            mcontrol = Record([("i", mcontrol_layout), ("o", mcontrol_layout)])
            m.d.comb += [
                mcontrol.i.eq(self.tdata1.w.data),
                mcontrol.o.execute.eq(mcontrol.i.execute),
                mcontrol.o.m.eq(mcontrol.i.m),
                mcontrol.o.action.eq(mcontrol.i.action),
            ]
            m.d.sync += trigger.data.eq(mcontrol.o)

        with m.Switch(self.tselect.r.value):
            for i, t in enumerate(triggers):
                with m.Case(i):
                    m.d.comb += self.tdata1.r.eq(t)
                    with m.If(self.tdata1.we):
                        do_trigger_update(t)

        with m.If(self.tselect.we):
            with m.If(self.tselect.w.value & (self.nb_triggers - 1)):
                m.d.sync += self.tselect.r.value.eq(self.tselect.w.value)

        with m.If(self.tdata2.we):
            m.d.sync += self.tdata2.r.eq(self.tdata2.w)

        hit = Signal()
        halt = Signal()

        with m.Switch(self.tdata1.r.type):
            with m.Case(Type.MATCH):
                mcontrol = Record(mcontrol_layout)
                m.d.comb += mcontrol.eq(self.tdata1.r.data)

                match = Signal()
                with m.If(mcontrol.execute):
                    m.d.comb += match.eq(self.tdata2.r == self.x_pc & self.x_valid)
                m.d.comb += [
                    hit.eq(match & mcontrol.m),
                    halt.eq(mcontrol.action)
                ]

        with m.If(hit):
            with m.If(halt):
                m.d.comb += self.haltreq.eq(self.tdata1.r.dmode)
            with m.Else():
                m.d.comb += self.x_trap.eq(1)

        return m
