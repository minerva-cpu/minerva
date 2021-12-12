from amaranth import *
from amaranth.lib.coding import PriorityEncoder

from ...csr import *
from ...isa import *
from ...wishbone import wishbone_layout
from .dmi import DebugReg, Command, Error, Version, cmd_access_reg_layout


__all__ = ["DebugController"]


class HaltCause:
    EBREAK        = 1
    TRIGGER       = 0
    HALTREQ       = 3
    STEP          = 4
    RESET_HALTREQ = 2


cause_map = [2, 1, 5, 3, 4]


class DebugController(Elaboratable):
    def __init__(self, debugrf):
        self.dcsr_we    = Signal()
        self.dcsr_w     = Record((fname, shape) for (fname, shape, mode) in dcsr_layout)
        self.dcsr_r     = Record.like(self.dcsr_w)
        self.dpc_we     = Signal()
        self.dpc_w      = Signal(32)

        self.dmstatus   = debugrf.reg_port(DebugReg.DMSTATUS)
        self.dmcontrol  = debugrf.reg_port(DebugReg.DMCONTROL)
        self.hartinfo   = debugrf.reg_port(DebugReg.HARTINFO)
        self.abstractcs = debugrf.reg_port(DebugReg.ABSTRACTCS)
        self.command    = debugrf.reg_port(DebugReg.COMMAND)
        self.data0      = debugrf.reg_port(DebugReg.DATA0)
        self.haltsum0   = debugrf.reg_port(DebugReg.HALTSUM0)

        self.trigger_haltreq = Signal()

        self.x_pc = Signal(32)
        self.x_ebreak = Signal()
        self.x_stall = Signal()

        self.m_branch_taken = Signal()
        self.m_branch_target = Signal(32)
        self.m_mret = Signal()
        self.m_exception = Signal()
        self.m_pc = Signal(32)
        self.m_valid = Signal()
        self.mepc_r_base = Signal(30)
        self.mtvec_r_base = Signal(30)

        self.halt = Signal()
        self.halted = Signal()
        self.killall = Signal()
        self.resumereq = Signal()
        self.resumeack = Signal()

        self.gprf_addr = Signal(5)
        self.gprf_re = Signal()
        self.gprf_dat_r = Signal(32)
        self.gprf_we = Signal()
        self.gprf_dat_w = Signal(32)

        self.csrf_addr = Signal(12)
        self.csrf_re = Signal()
        self.csrf_dat_r = Signal(32)
        self.csrf_we = Signal()
        self.csrf_dat_w = Signal(32)

    def elaborate(self, platform):
        m = Module()

        with m.If(self.dmcontrol.update):
            m.d.sync += [
                self.dmcontrol.w.dmactive.eq(self.dmcontrol.r.dmactive),
                self.dmcontrol.w.ndmreset.eq(self.dmcontrol.r.ndmreset),
                self.dmcontrol.w.hartselhi.eq(self.dmcontrol.r.hartselhi),
                self.dmcontrol.w.hartsello.eq(self.dmcontrol.r.hartsello),
                self.dmcontrol.w.hasel.eq(self.dmcontrol.r.hasel),
                self.dmcontrol.w.hartreset.eq(self.dmcontrol.r.hartreset),
                self.dmcontrol.w.resumereq.eq(self.dmcontrol.r.resumereq),
            ]

        with m.If(self.abstractcs.update):
            m.d.sync += self.abstractcs.w.cmderr.eq(self.abstractcs.r.cmderr)

        with m.If(self.data0.update):
            m.d.sync += self.data0.w.eq(self.data0.r)

        m.d.comb += [
            self.dmstatus.w.version.eq(Version.V013),
            self.dmstatus.w.authenticated.eq(1),
            self.resumereq.eq(self.dmcontrol.w.resumereq),
            self.haltsum0.w[0].eq(self.dmstatus.w.allhalted),
        ]

        m_breakpoint = Signal()
        with m.If(~self.x_stall):
            m.d.comb += m_breakpoint.eq(self.x_ebreak & self.dcsr_r.ebreakm)

        halt_pe = m.submodules.halt_pe = PriorityEncoder(5)
        m.d.comb += [
            halt_pe.i[HaltCause.EBREAK].eq(m_breakpoint & self.m_valid),
            halt_pe.i[HaltCause.TRIGGER].eq(self.trigger_haltreq),
            halt_pe.i[HaltCause.HALTREQ].eq(self.dmcontrol.r.haltreq),
            halt_pe.i[HaltCause.STEP].eq(self.dcsr_r.step & self.m_valid),
        ]

        with m.FSM():
            with m.State("RUN"):
                m.d.comb += self.dmstatus.w.allrunning.eq(1)
                m.d.comb += self.dmstatus.w.anyrunning.eq(1)
                with m.If(~halt_pe.n):
                    m.d.sync += self.halt.eq(1)
                    m.d.comb += [
                        self.dcsr_we.eq(1),
                        self.dcsr_w.eq(self.dcsr_r),
                        self.dcsr_w.cause.eq(Array(cause_map)[halt_pe.o]),
                        self.dcsr_w.stepie.eq(1)
                    ]
                    m.d.comb += self.dpc_we.eq(1)
                    with m.If(halt_pe.o == HaltCause.EBREAK):
                        m.d.comb += self.dpc_w.eq(self.m_pc)
                    with m.Elif(self.m_exception & self.m_valid):
                        m.d.comb += self.dpc_w.eq(self.mtvec_r_base << 2)
                    with m.Elif(self.m_mret & self.m_valid):
                        m.d.comb += self.dpc_w.eq(self.mepc_r_base << 2)
                    with m.Elif(self.m_branch_taken & self.m_valid):
                        m.d.comb += self.dpc_w.eq(self.m_branch_target)
                    with m.Else():
                        m.d.comb += self.dpc_w.eq(self.x_pc)
                    m.next = "HALTING"

            with m.State("HALTING"):
                with m.If(self.halted):
                    m.d.comb += self.killall.eq(1)
                    m.d.sync += self.dmstatus.w.allhalted.eq(1)
                    m.d.sync += self.dmstatus.w.anyhalted.eq(1)
                    m.next = "WAIT"

            with m.State("WAIT"):
                with m.If(self.dmcontrol.w.resumereq):
                    m.next = "RESUME"
                with m.Elif(self.command.update):
                    m.d.sync += self.abstractcs.w.busy.eq(1)
                    m.next = "COMMAND:START"

            with m.State("RESUME"):
                with m.If(self.resumeack):
                    m.d.sync += [
                        self.dmcontrol.w.resumereq.eq(0),
                        self.dmstatus.w.allresumeack.eq(1),
                        self.dmstatus.w.anyresumeack.eq(1),
                        self.halt.eq(0),
                        self.dmstatus.w.allhalted.eq(0),
                        self.dmstatus.w.anyhalted.eq(0),
                    ]
                    m.next = "RUN"

            with m.State("COMMAND:START"):
                with m.Switch(self.command.r.cmdtype):
                    with m.Case(Command.ACCESS_REG):
                        control = Record(cmd_access_reg_layout)
                        m.d.comb += control.eq(self.command.r.control)
                        m.d.comb += self.gprf_addr.eq(control.regno)
                        m.next = "COMMAND:ACCESS-REG"
                    with m.Case():
                        m.d.sync += self.abstractcs.w.cmderr.eq(Error.UNSUPPORTED)
                        m.next = "COMMAND:DONE"

            with m.State("COMMAND:ACCESS-REG"):
                control = Record(cmd_access_reg_layout)
                m.d.comb += control.eq(self.command.r.control)
                with m.If(control.postexec | (control.aarsize != 2) | control.aarpostincrement):
                    # Unsupported parameters.
                    m.d.sync += self.abstractcs.w.cmderr.eq(Error.EXCEPTION)
                with m.Elif(control.regno.matches("0000------------")):
                    with m.If(control.transfer):
                        m.d.comb += self.csrf_addr.eq(control.regno)
                        with m.If(control.write):
                            m.d.comb += [
                                self.csrf_we.eq(1),
                                self.csrf_dat_w.eq(self.data0.r)
                            ]
                        with m.Else():
                            m.d.comb += self.csrf_re.eq(1)
                            m.d.sync += self.data0.w.eq(self.csrf_dat_r)
                    m.d.sync += self.abstractcs.w.cmderr.eq(Error.NONE)
                with m.Elif(control.regno.matches("00010000000-----")):
                    with m.If(control.transfer):
                        m.d.comb += self.gprf_addr.eq(control.regno)
                        with m.If(control.write):
                            m.d.comb += [
                                self.gprf_we.eq(1),
                                self.gprf_dat_w.eq(self.data0.r)
                            ]
                        with m.Else():
                            m.d.sync += self.data0.w.eq(self.gprf_dat_r)
                    m.d.sync += self.abstractcs.w.cmderr.eq(Error.NONE)
                with m.Else():
                    # Unknown register number.
                    m.d.sync += self.abstractcs.w.cmderr.eq(Error.EXCEPTION)
                m.next = "COMMAND:DONE"

            with m.State("COMMAND:DONE"):
                m.d.sync += self.abstractcs.w.busy.eq(0)
                m.next = "WAIT"

        return m
