from nmigen import *
from nmigen.lib.coding import PriorityEncoder

from ..csr import *
from ..isa import *


__all__ = ["ExceptionUnit"]


class ExceptionUnit(Elaboratable, AutoCSR):
    def __init__(self):
        self.mstatus     = CSR(0x300, mstatus_layout, name="mstatus")
        self.misa        = CSR(0x301, misa_layout, name="misa") # FIXME move elsewhere
        self.mie         = CSR(0x304, mie_layout, name="mie")
        self.mtvec       = CSR(0x305, mtvec_layout, name="mtvec")
        self.mscratch    = CSR(0x340, flat_layout, name="mscratch") # FIXME move elsewhere
        self.mepc        = CSR(0x341, flat_layout, name="mepc")
        self.mcause      = CSR(0x342, mcause_layout, name="mcause")
        self.mip         = CSR(0x344, mip_layout, name="mip")
        self.irq_mask    = CSR(0x330, flat_layout, name="irq_mask")
        self.irq_pending = CSR(0x360, flat_layout, name="irq_pending")

        self.external_interrupt = Signal(32)
        self.timer_interrupt = Signal()
        self.x_pc = Signal(32)
        self.x_ebreak = Signal()
        self.x_ecall = Signal()
        self.x_misaligned_fetch = Signal()
        self.x_bus_error = Signal()
        self.x_illegal = Signal()
        self.x_mret = Signal()
        self.x_stall = Signal()
        self.x_valid = Signal()

        self.x_raise = Signal()

    def elaborate(self, platform):
        m = Module()

        for csr in self.get_csrs():
            with m.If(csr.we):
                m.d.sync += csr.r.eq(csr.w)

        trap_pe = m.submodules.trap_pe = PriorityEncoder(16)
        m.d.comb += [
            trap_pe.i[Cause.FETCH_MISALIGNED   ].eq(self.x_misaligned_fetch),
            trap_pe.i[Cause.FETCH_ACCESS_FAULT ].eq(self.x_bus_error),
            trap_pe.i[Cause.ILLEGAL_INSTRUCTION].eq(self.x_illegal),
            trap_pe.i[Cause.BREAKPOINT         ].eq(self.x_ebreak),
            trap_pe.i[Cause.ECALL_FROM_M       ].eq(self.x_ecall)
        ]

        m.d.sync += [
            self.irq_pending.r.eq(self.external_interrupt & self.irq_mask.r),
            self.mip.r.mtip.eq(self.timer_interrupt),
            self.mip.r.meip.eq(self.irq_pending.r.bool())
        ]

        interrupt_pe = m.submodules.interrupt_pe = PriorityEncoder(16)
        m.d.comb += [
            interrupt_pe.i[Cause.M_SOFTWARE_INTERRUPT].eq(self.mip.r.msip & self.mie.r.msie),
            interrupt_pe.i[Cause.M_TIMER_INTERRUPT   ].eq(self.mip.r.mtip & self.mie.r.mtie),
            interrupt_pe.i[Cause.M_EXTERNAL_INTERRUPT].eq(self.mip.r.meip & self.mie.r.meie)
        ]

        m.d.comb += self.x_raise.eq(~trap_pe.n | ~interrupt_pe.n & self.mstatus.r.mie)

        with m.If(self.x_valid & ~self.x_stall):
            with m.If(self.x_raise):
                m.d.sync += [
                    self.mstatus.r.mpie.eq(self.mstatus.r.mie),
                    self.mstatus.r.mie.eq(0),
                    self.mepc.r.eq(self.x_pc[2:] << 2)
                ]
                with m.If(~trap_pe.n):
                    m.d.sync += [
                        self.mcause.r.ecode.eq(trap_pe.o),
                        self.mcause.r.interrupt.eq(0)
                    ]
                with m.Else():
                    m.d.sync += [
                        self.mcause.r.ecode.eq(interrupt_pe.o),
                        self.mcause.r.interrupt.eq(1)
                    ]
            with m.Elif(self.x_mret):
                m.d.sync += self.mstatus.r.mie.eq(self.mstatus.r.mpie)

        return m
