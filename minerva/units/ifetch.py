from operator import and_

from nmigen import *

from ..cache import L1Cache
from ..wishbone import Cycle, wishbone_layout


__all__ = ["SimpleInstructionUnit", "CachedInstructionUnit"]


class _InstructionUnit:
    def __init__(self):
        self.ibus = Record(wishbone_layout)

        self.a_stall = Signal()
        self.f_pc = Signal(30)
        self.d_branch_predict_taken = Signal()
        self.d_branch_target = Signal(30)
        self.x_pc = Signal(30)
        self.m_branch_taken = Signal()
        self.m_branch_target = Signal(30)
        self.m_branch_predict_taken = Signal()

        self.a_pc = Signal(30)
        self.f_instruction = Signal(32)
        self.f_bus_error = Signal()

    def get_fragment(self, platform):
        m = Module()

        with m.If(self.d_branch_predict_taken):
            m.d.comb += self.a_pc.eq(self.d_branch_target)
        with m.Elif(self.m_branch_predict_taken & ~self.m_branch_taken):
            m.d.comb += self.a_pc.eq(self.x_pc)
        with m.Elif(~self.m_branch_predict_taken & self.m_branch_taken):
            m.d.comb += self.a_pc.eq(self.m_branch_target)
        with m.Else():
            m.d.comb += self.a_pc.eq(self.f_pc + 1)

        return m.lower(platform)


class SimpleInstructionUnit(_InstructionUnit):
    def get_fragment(self, platform):
        m = Module()
        m.submodules += super().get_fragment(platform)

        with m.If(self.ibus.cyc):
            with m.If(self.ibus.ack | self.ibus.err):
                m.d.sync += [
                    self.ibus.cyc.eq(0),
                    self.ibus.stb.eq(0)
                ]
            m.d.sync += [
                self.f_instruction.eq(self.ibus.dat_r),
                self.f_bus_error.eq(self.ibus.err)
            ]
        with m.Elif(~self.a_stall):
            m.d.sync += [
                self.ibus.adr.eq(self.a_pc),
                self.ibus.cyc.eq(1),
                self.ibus.stb.eq(1),
                self.f_bus_error.eq(0)
            ]

        return m.lower(platform)


class CachedInstructionUnit(_InstructionUnit):
    def __init__(self, *icache_args):
        super().__init__()

        self.f_stall = Signal()
        self.f_valid = Signal()

        self.icache = L1Cache(*icache_args)

    def get_fragment(self, platform):
        m = Module()
        m.submodules += super().get_fragment(platform)

        icache = m.submodules.icache = self.icache
        m.d.comb += [
            icache.s1_address.eq(self.a_pc),
            icache.s1_stall.eq(self.a_stall),
            icache.s2_address.eq(self.f_pc),
            icache.s2_stall.eq(self.f_stall),
            icache.s2_re.eq(self.f_valid),
            icache.refill_address.eq(self.ibus.adr),
            icache.refill_data.eq(self.ibus.dat_r),
            icache.refill_valid.eq(self.ibus.cyc & self.ibus.ack),
            self.f_instruction.eq(icache.s2_dat_r),
        ]

        next_offset = Signal(icache.offsetbits)
        last_offset = Signal(icache.offsetbits)
        next_cti = Signal(3)
        m.d.comb += [
            next_offset.eq(self.ibus.adr[:icache.offsetbits]+1),
            next_cti.eq(Mux(next_offset == last_offset, Cycle.END, Cycle.INCREMENT)),
            icache.last_refill.eq(self.ibus.adr[:icache.offsetbits] == last_offset),
            self.ibus.bte.eq(icache.offsetbits-1)
        ]

        with m.If(self.ibus.cyc):
            with m.If(self.ibus.ack | self.ibus.err):
                with m.If(self.ibus.cti == Cycle.END):
                    m.d.sync += [
                        self.ibus.cyc.eq(0),
                        self.ibus.stb.eq(0)
                    ]
                m.d.sync += [
                    self.ibus.adr[:icache.offsetbits].eq(next_offset),
                    self.ibus.cti.eq(next_cti)
                ]
            m.d.sync += self.f_bus_error.eq(self.ibus.err)
        with m.Elif(icache.refill_request):
            m.d.sync += [
                last_offset.eq(icache.s2_address[:icache.offsetbits]-1),
                self.ibus.adr.eq(icache.s2_address),
                self.ibus.cti.eq(Cycle.INCREMENT),
                self.ibus.cyc.eq(1),
                self.ibus.stb.eq(1)
            ]

        return m.lower(platform)
