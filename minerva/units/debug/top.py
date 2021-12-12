from amaranth import *
from amaranth.hdl.rec import *


from ...csr import *
from ...isa import *
from ...wishbone import wishbone_layout
from .controller import *
from .jtag import *
from .regfile import *
from .wbmaster import *


__all__ = ["DebugUnit"]


jtag_regs = {
    JTAGReg.IDCODE: [("value", 32)],
    JTAGReg.DTMCS:  dtmcs_layout,
    JTAGReg.DMI:    dmi_layout
}


class DebugUnit(Elaboratable, AutoCSR):
    def __init__(self):
        self.jtag = Record(jtag_layout)
        self.dbus = Record(wishbone_layout)

        self.trigger_haltreq = Signal()

        self.x_ebreak = Signal()
        self.x_pc = Signal(32)
        self.x_stall = Signal()

        self.m_branch_taken = Signal()
        self.m_branch_target = Signal(32)
        self.m_mret = Signal()
        self.m_exception = Signal()
        self.m_pc = Signal(32)
        self.m_valid = Signal()
        self.mepc_r_base = Signal(30)
        self.mtvec_r_base = Signal(30)

        self.dcsr_step = Signal()
        self.dcsr_ebreakm = Signal()
        self.dpc_value = Signal(32)

        self.halt = Signal()
        self.halted = Signal()
        self.killall = Signal()
        self.resumereq = Signal()
        self.resumeack = Signal()

        self.dbus_busy = Signal()

        self.csrf_addr = Signal(12)
        self.csrf_re = Signal()
        self.csrf_dat_r = Signal(32)
        self.csrf_we = Signal()
        self.csrf_dat_w = Signal(32)

        self.gprf_addr = Signal(5)
        self.gprf_re = Signal()
        self.gprf_dat_r = Signal(32)
        self.gprf_we = Signal()
        self.gprf_dat_w = Signal(32)

        self.dcsr = CSR(0x7b0, dcsr_layout)
        self.dpc  = CSR(0x7b1, flat_layout)

    def elaborate(self, platform):
        m = Module()

        from jtagtap import JTAGTap
        tap        = m.submodules.tap        = JTAGTap(jtag_regs)
        regfile    = m.submodules.regfile    = DebugRegisterFile(tap.regs[JTAGReg.DMI])
        controller = m.submodules.controller = DebugController(regfile)
        wbmaster   = m.submodules.wbmaster   = DebugWishboneMaster(regfile)

        m.d.comb += [
            tap.port.connect(self.jtag),
            tap.regs[JTAGReg.IDCODE].r.eq(0x10e31913), # Usurpate a Spike core for now.
            tap.regs[JTAGReg.DTMCS].r.eq(0x71) # (abits=7, version=1) TODO
        ]

        self.dcsr.r.xdebugver.reset = 4 # Use debug spec v0.13
        with m.If(self.dcsr.we):
            m.d.sync += self.dcsr.r.eq(self.dcsr.w)
        with m.If(controller.dcsr_we):
            m.d.sync += self.dcsr.r.eq(controller.dcsr_w)

        with m.If(controller.dpc_we):
            m.d.sync += self.dpc.r.eq(controller.dpc_w)

        m.d.comb += [
            controller.dcsr_r.eq(self.dcsr.r),
            controller.trigger_haltreq.eq(self.trigger_haltreq),

            controller.x_ebreak.eq(self.x_ebreak),
            controller.x_pc.eq(self.x_pc),
            controller.x_stall.eq(self.x_stall),

            controller.m_branch_taken.eq(self.m_branch_taken),
            controller.m_branch_target.eq(self.m_branch_target),
            controller.m_pc.eq(self.m_pc),
            controller.m_valid.eq(self.m_valid),

            self.halt.eq(controller.halt),
            controller.halted.eq(self.halted),
            self.killall.eq(controller.killall),
            self.resumereq.eq(controller.resumereq),
            controller.resumeack.eq(self.resumeack),

            self.dcsr_step.eq(self.dcsr.r.step),
            self.dcsr_ebreakm.eq(self.dcsr.r.ebreakm),
            self.dpc_value.eq(self.dpc.r.value),

            self.csrf_addr.eq(controller.csrf_addr),
            self.csrf_re.eq(controller.csrf_re),
            controller.csrf_dat_r.eq(self.csrf_dat_r),
            self.csrf_we.eq(controller.csrf_we),
            self.csrf_dat_w.eq(controller.csrf_dat_w),

            self.gprf_addr.eq(controller.gprf_addr),
            self.gprf_re.eq(controller.gprf_re),
            controller.gprf_dat_r.eq(self.gprf_dat_r),
            self.gprf_we.eq(controller.gprf_we),
            self.gprf_dat_w.eq(controller.gprf_dat_w),
        ]

        m.d.comb += [
            wbmaster.bus.connect(self.dbus),
            self.dbus_busy.eq(wbmaster.dbus_busy)
        ]

        return m
