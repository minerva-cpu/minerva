from amaranth import *
from amaranth.lib.coding import PriorityEncoder

from ..csr import *
from ..isa import *


__all__ = ["ExceptionUnit"]


class ExceptionUnit(Elaboratable, AutoCSR):
    def __init__(self):
        self.mstatus     = CSR(0x300, mstatus_layout)
        self.misa        = CSR(0x301, misa_layout) # FIXME move elsewhere
        self.mie         = CSR(0x304, mie_layout)
        self.mtvec       = CSR(0x305, mtvec_layout)
        self.mscratch    = CSR(0x340, flat_layout) # FIXME move elsewhere
        self.mepc        = CSR(0x341, mepc_layout)
        self.mcause      = CSR(0x342, mcause_layout)
        self.mtval       = CSR(0x343, flat_layout)
        self.mip         = CSR(0x344, mip_layout)
        self.irq_mask    = CSR(0x330, flat_layout)
        self.irq_pending = CSR(0x360, flat_layout)

        self.external_interrupt = Signal(32)
        self.timer_interrupt = Signal()
        self.software_interrupt = Signal()

        self.m_fetch_misaligned = Signal()
        self.m_fetch_error = Signal()
        self.m_fetch_badaddr = Signal(30)
        self.m_load_misaligned = Signal()
        self.m_load_error = Signal()
        self.m_store_misaligned = Signal()
        self.m_store_error = Signal()
        self.m_loadstore_badaddr = Signal(30)
        self.m_branch_target = Signal(32)
        self.m_illegal = Signal()
        self.m_ebreak = Signal()
        self.m_ecall = Signal()
        self.m_pc = Signal(32)
        self.m_instruction = Signal(32)
        self.m_result = Signal(32)
        self.m_mret = Signal()
        self.m_stall = Signal()
        self.m_valid = Signal()

        self.m_raise = Signal()

    def elaborate(self, platform):
        m = Module()

        for csr in self.iter_csrs():
            with m.If(csr.we):
                m.d.sync += csr.r.eq(csr.w)

        trap_pe = m.submodules.trap_pe = PriorityEncoder(16)
        m.d.comb += [
            trap_pe.i[Cause.FETCH_MISALIGNED   ].eq(self.m_fetch_misaligned),
            trap_pe.i[Cause.FETCH_ACCESS_FAULT ].eq(self.m_fetch_error),
            trap_pe.i[Cause.ILLEGAL_INSTRUCTION].eq(self.m_illegal),
            trap_pe.i[Cause.BREAKPOINT         ].eq(self.m_ebreak),
            trap_pe.i[Cause.LOAD_MISALIGNED    ].eq(self.m_load_misaligned),
            trap_pe.i[Cause.LOAD_ACCESS_FAULT  ].eq(self.m_load_error),
            trap_pe.i[Cause.STORE_MISALIGNED   ].eq(self.m_store_misaligned),
            trap_pe.i[Cause.STORE_ACCESS_FAULT ].eq(self.m_store_error),
            trap_pe.i[Cause.ECALL_FROM_M       ].eq(self.m_ecall)
        ]

        m.d.sync += [
            self.irq_pending.r.eq(self.external_interrupt & self.irq_mask.r),
            self.mip.r.msip.eq(self.software_interrupt),
            self.mip.r.mtip.eq(self.timer_interrupt),
            self.mip.r.meip.eq(self.irq_pending.r.bool())
        ]

        interrupt_pe = m.submodules.interrupt_pe = PriorityEncoder(16)
        m.d.comb += [
            interrupt_pe.i[Cause.M_SOFTWARE_INTERRUPT].eq(self.mip.r.msip & self.mie.r.msie),
            interrupt_pe.i[Cause.M_TIMER_INTERRUPT   ].eq(self.mip.r.mtip & self.mie.r.mtie),
            interrupt_pe.i[Cause.M_EXTERNAL_INTERRUPT].eq(self.mip.r.meip & self.mie.r.meie)
        ]

        m.d.comb += self.m_raise.eq(~trap_pe.n | ~interrupt_pe.n & self.mstatus.r.mie)

        with m.If(self.m_valid & ~self.m_stall):
            with m.If(self.m_raise):
                m.d.sync += [
                    self.mstatus.r.mpie.eq(self.mstatus.r.mie),
                    self.mstatus.r.mie.eq(0),
                    self.mepc.r.base.eq(self.m_pc[2:])
                ]
                with m.If(~trap_pe.n):
                    m.d.sync += [
                        self.mcause.r.ecode.eq(trap_pe.o),
                        self.mcause.r.interrupt.eq(0)
                    ]
                    with m.Switch(trap_pe.o):
                        with m.Case(Cause.FETCH_MISALIGNED):
                            m.d.sync += self.mtval.r.eq(self.m_branch_target)
                        with m.Case(Cause.FETCH_ACCESS_FAULT):
                            m.d.sync += self.mtval.r.eq(self.m_fetch_badaddr << 2)
                        with m.Case(Cause.ILLEGAL_INSTRUCTION):
                            m.d.sync += self.mtval.r.eq(self.m_instruction)
                        with m.Case(Cause.BREAKPOINT):
                            m.d.sync += self.mtval.r.eq(self.m_pc)
                        with m.Case(Cause.LOAD_MISALIGNED, Cause.STORE_MISALIGNED):
                            m.d.sync += self.mtval.r.eq(self.m_result)
                        with m.Case(Cause.LOAD_ACCESS_FAULT, Cause.STORE_ACCESS_FAULT):
                            m.d.sync += self.mtval.r.eq(self.m_loadstore_badaddr << 2)
                        with m.Case():
                            m.d.sync += self.mtval.r.eq(0)
                with m.Else():
                    m.d.sync += [
                        self.mcause.r.ecode.eq(interrupt_pe.o),
                        self.mcause.r.interrupt.eq(1)
                    ]
            with m.Elif(self.m_mret):
                m.d.sync += self.mstatus.r.mie.eq(self.mstatus.r.mpie)

        return m
