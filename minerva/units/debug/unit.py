from nmigen import *
from nmigen.hdl.rec import *

from jtagtap import JTAGTap

from ...isa import CSRIndex
from ...wishbone import wishbone_layout
from .controller import *
from .dmi import *
from .jtag import *
from .regfile import *
from .wbm import *


__all__ = ["DebugUnit"]


class DebugUnit:
    def __init__(self, gprf, csrf):
        self.jtag = Record(jtag_layout)
        self.dbus = Record(wishbone_layout)

        self.x_pc = Signal(30)
        self.x_valid = Signal()

        self.m_branch_taken = Signal()
        self.m_branch_target = Signal(32)
        self.m_breakpoint = Signal()
        self.m_pc = Signal(30)
        self.m_valid = Signal()

        self.halt = Signal()
        self.halted = Signal()
        self.killall = Signal()
        self.resumereq = Signal()
        self.resumeack = Signal()

        self.sbbusy = Signal()

        self.csrf_rp = csrf.read_port()
        self.csrf_wp = csrf.write_port()
        self.gprf_rp = gprf.read_port()
        self.gprf_wp = gprf.write_port()

        self.dcsr = csrf.csr_port(CSRIndex.DCSR)
        self.dpc  = csrf.csr_port(CSRIndex.DPC)

    def elaborate(self, platform):
        m = Module()

        dtm_regs = {
            JTAGReg.IDCODE: [("value", 32)],
            JTAGReg.DTMCS:  dtmcs_layout,
            JTAGReg.DMI:    dmi_layout
        }
        tap = m.submodules.tap = JTAGTap(dtm_regs)
        m.d.comb += [
            tap.port.connect(self.jtag),
            tap.regs[JTAGReg.IDCODE].r.eq(0x10e31913), # Usurpate a Spike core for now.
            tap.regs[JTAGReg.DTMCS].r.eq(0x61) # (abits=6, version=1) TODO
        ]

        dmi = tap.regs[JTAGReg.DMI]
        dmrf = m.submodules.dmrf = DebugRegisterFile(dmi)

        ctl = m.submodules.ctl = DebugController(dmrf)
        m.d.comb += [
            self.gprf_wp.addr.eq(ctl.gprf_addr),
            self.gprf_wp.en.eq(ctl.gprf_we),
            self.gprf_wp.data.eq(ctl.gprf_dat_w),
            self.gprf_rp.addr.eq(ctl.gprf_addr),
            ctl.gprf_dat_r.eq(self.gprf_rp.data),

            self.csrf_wp.addr.eq(ctl.csrf_addr),
            self.csrf_wp.en.eq(ctl.csrf_we),
            self.csrf_wp.data.eq(ctl.csrf_dat_w),
            self.csrf_rp.addr.eq(ctl.csrf_addr),
            ctl.csrf_dat_r.eq(self.csrf_rp.data),

            self.dcsr.we.eq(ctl.dcsr_we),
            self.dcsr.dat_w.eq(ctl.dcsr_dat_w),
            ctl.dcsr_dat_r.eq(self.dcsr.dat_r),

            self.dpc.we.eq(ctl.dpc_we),
            self.dpc.dat_w.eq(ctl.dpc_dat_w),
            ctl.dpc_dat_r.eq(self.dpc.dat_r),

            ctl.x_pc.eq(self.x_pc),
            ctl.x_valid.eq(self.x_valid),

            ctl.m_branch_taken.eq(self.m_branch_taken),
            ctl.m_branch_target.eq(self.m_branch_target),
            ctl.m_breakpoint.eq(self.m_breakpoint),
            ctl.m_pc.eq(self.m_pc),
            ctl.m_valid.eq(self.m_valid),

            self.halt.eq(ctl.halt),
            ctl.halted.eq(self.halted),
            self.killall.eq(ctl.killall),
            self.resumereq.eq(ctl.resumereq),
            ctl.resumeack.eq(self.resumeack),
        ]

        wbm = m.submodules.wbm = DebugWishboneMaster(dmrf)
        m.d.comb += [
            wbm.bus.connect(self.dbus),
            self.sbbusy.eq(wbm.sbbusy)
        ]

        return m
