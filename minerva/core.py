from functools import reduce
from operator import or_
from itertools import tee

from nmigen import *
from nmigen.lib.coding import PriorityEncoder

from .isa import CSRIndex, Cause, mcause_layout, flat_layout
from .stage import Stage
from .units.adder import AdderUnit
from .units.branch import BranchUnit, BranchPredictor
from .units.decoder import InstructionDecoder
from .units.ifetch import SimpleInstructionUnit, CachedInstructionUnit
from .units.loadstore import SimpleLoadStoreUnit, CachedLoadStoreUnit
from .units.logic import LogicUnit
from .units.regfile import GPRFile, CSRFile
from .units.shifter import Shifter
from .wishbone import wishbone_layout


__all__ = ["Minerva"]


_af_layout = [
    ("pc", (31, True))
]


_fd_layout = [
    ("pc",          30),
    ("instruction", 32),
    ("bus_error",    1)
]


_dx_layout = [
    ("pc",                  30),
    ("rd",                   5),
    ("rs1",                  5),
    ("rd_we",                1),
    ("rs1_re",               1),
    ("src1",                32),
    ("src2",                32),
    ("immediate",           32),
    ("bypass_x",             1),
    ("bypass_m",             1),
    ("funct3",               3),
    ("load",                 1),
    ("store",                1),
    ("adder_sub",            1),
    ("logic",                1),
    ("shift",                1),
    ("direction",            1),
    ("sext",                 1),
    ("jump",                 1),
    ("compare",              1),
    ("branch",               1),
    ("branch_target",       32),
    ("branch_predict_taken", 1),
    ("fence_i",              1),
    ("csr",                  1),
    ("csr_adr",             12),
    ("csr_we",               1),
    ("bus_error",            1),
    ("ecall",                1),
    ("ebreak",               1),
    ("mret",                 1),
    ("illegal",              1)
]


_xm_layout = [
    ("pc",                  30),
    ("rd",                   5),
    ("rd_we",                1),
    ("bypass_m",             1),
    ("result",              32),
    ("shift",                1),
    ("dcache_select",        1),
    ("load",                 1),
    ("load_mask",            3),
    ("store",                1),
    ("dbus_sel",             4),
    ("store_data",          32),
    ("compare",              1),
    ("condition_met",        1),
    ("branch_target",       32),
    ("branch_taken",         1),
    ("branch_predict_taken", 1),
    ("csr_adr",             12),
    ("csr_we",               1),
    ("csr_result",          32),
    ("mret",                 1),
    ("exception",            1),
    ("mcause",   mcause_layout),
    ("mepc",       flat_layout)
]


_mw_layout = [
    ("pc",                30),
    ("rd",                 5),
    ("rd_we",              1),
    ("result",            32),
    ("load",               1),
    ("load_mask",          3),
    ("load_data",         32),
    ("exception",          1),
    ("csr_adr",           12),
    ("csr_we",             1),
    ("csr_result",        32),
    ("mret",               1),
    ("mcause", mcause_layout),
    ("mepc",     flat_layout)
]


class Minerva:
    def __init__(self, reset_address=0x00000000,
                with_icache=True,
                icache_nb_ways=1, icache_nb_lines=512, icache_nb_words=8,
                icache_base=0, icache_limit=2**31,
                with_dcache=True,
                dcache_nb_ways=1, dcache_nb_lines=512, dcache_nb_words=8,
                dcache_base=0, dcache_limit=2**31):
        self.external_interrupt = Signal(32)
        self.timer_interrupt = Signal()
        self.ibus = Record(wishbone_layout)
        self.dbus = Record(wishbone_layout)

        # TODO Figure out a better way to pass parameters.
        self.reset_address = reset_address
        self.with_icache = with_icache
        self.icache_nb_ways = icache_nb_ways
        self.icache_nb_lines = icache_nb_lines
        self.icache_nb_words = icache_nb_words
        self.icache_base = icache_base
        self.icache_limit = icache_limit
        self.with_dcache = with_dcache
        self.dcache_nb_ways = dcache_nb_ways
        self.dcache_nb_lines = dcache_nb_lines
        self.dcache_nb_words = dcache_nb_words
        self.dcache_base = dcache_base
        self.dcache_limit = dcache_limit

    def elaborate(self, platform):
        cpu = Module()

        # pipeline stages

        a = cpu.submodules.a = Stage(None, _af_layout)
        f = cpu.submodules.f = Stage(_af_layout, _fd_layout)
        d = cpu.submodules.d = Stage(_fd_layout, _dx_layout)
        x = cpu.submodules.x = Stage(_dx_layout, _xm_layout)
        m = cpu.submodules.m = Stage(_xm_layout, _mw_layout)
        w = cpu.submodules.w = Stage(_mw_layout, None)
        stages = a, f, d, x, m, w

        sources, sinks = tee(stages)
        next(sinks)
        for s1, s2 in zip(sources, sinks):
            # FIXME
            # cpu.d.comb += s1.source.connect(s2.sink)
            cpu.d.comb += [
                s2.sink.valid.eq(s1.source.valid),
                s1.source.stall.eq(s2.sink.stall),
                s2.sink.kill.eq(s1.source.kill)
            ]
            for name, *rest in s1.source.payload.layout:
                src = getattr(s1.source.payload, name)
                snk = getattr(s2.sink.payload, name)
                cpu.d.comb += snk.eq(src)

        a.source.pc.reset = self.reset_address//4 - 1
        cpu.d.comb += a.valid.eq(1)

        # units

        if self.with_icache:
            ifu = cpu.submodules.ifu = CachedInstructionUnit(
                    self.icache_nb_ways, self.icache_nb_lines, self.icache_nb_words,
                    self.icache_base, self.icache_limit)
            cpu.d.comb += [
                ifu.f_stall.eq(f.stall),
                ifu.f_valid.eq(f.valid),
                ifu.icache.flush.eq(x.sink.fence_i & x.valid)
            ]
            if self.with_dcache:
                dcache_stall_request = Signal()
                cpu.d.comb += ifu.icache.refill_ready.eq(~dcache_stall_request)
            else:
                cpu.d.comb += ifu.icache.refill_ready.eq(1)

            x.stall_on(ifu.icache.stall_request)
            m.stall_on(ifu.icache.stall_request \
                    & (ifu.m_branch_predict_taken != ifu.m_branch_taken))
            m.stall_on(self.ibus.cyc & ifu.m_branch_taken)
        else:
            ifu = cpu.submodules.ifu = SimpleInstructionUnit()
            m.stall_on(self.ibus.cyc)

        d_branch_predict_taken = Signal()
        d_branch_target = Signal(32)

        cpu.d.comb += [
            # FIXME
            # ifu.ibus.connect(self.ibus),
            self.ibus.adr.eq(ifu.ibus.adr),
            self.ibus.dat_w.eq(ifu.ibus.dat_w),
            ifu.ibus.dat_r.eq(self.ibus.dat_r),
            self.ibus.sel.eq(ifu.ibus.sel),
            self.ibus.cyc.eq(ifu.ibus.cyc),
            self.ibus.stb.eq(ifu.ibus.stb),
            ifu.ibus.ack.eq(self.ibus.ack),
            self.ibus.we.eq(ifu.ibus.we),
            self.ibus.cti.eq(ifu.ibus.cti),
            self.ibus.bte.eq(ifu.ibus.bte),
            ifu.ibus.err.eq(self.ibus.err),

            ifu.a_stall.eq(a.stall),
            ifu.f_pc.eq(f.sink.pc[:30]),
            ifu.d_branch_predict_taken.eq(d_branch_predict_taken & d.valid),
            ifu.d_branch_target.eq(d_branch_target[2:]),
            ifu.x_pc.eq(x.sink.pc[:30]),
            ifu.m_branch_taken.eq(m.sink.branch_taken & m.valid),
            ifu.m_branch_target.eq(m.sink.branch_target[2:]),
            ifu.m_branch_predict_taken.eq(m.sink.branch_predict_taken & m.valid),
        ]

        decoder = cpu.submodules.decoder = InstructionDecoder()
        cpu.d.comb += [
            decoder.instruction.eq(d.sink.instruction)
        ]

        d.kill_on(d.source.illegal & d.source.valid)

        gprf = cpu.submodules.gprf = GPRFile()
        cpu.d.comb += [
            gprf.rp1.addr.eq(decoder.rs1),
            gprf.rp2.addr.eq(decoder.rs2)
        ]

        csrf = cpu.submodules.csrf = CSRFile()
        cpu.d.comb += csrf.rp.addr.eq(decoder.immediate[:12])

        # csr set/clear instructions are translated to logic operations
        x_csr_set_clear = x.sink.funct3[1]
        x_csr_clear = x_csr_set_clear & x.sink.funct3[0]
        x_csr_fmt_i = x.sink.funct3[2]
        x_csr_src1 = Mux(x_csr_fmt_i, x.sink.rs1, x.sink.src1)
        x_csr_src1 = Mux(x_csr_clear, ~x_csr_src1, x_csr_src1)
        x_csr_logic_op = x.sink.funct3 | 0b100

        logic = cpu.submodules.logic = LogicUnit()
        cpu.d.comb += [
            logic.op.eq(Mux(x.sink.csr, x_csr_logic_op, x.sink.funct3)),
            logic.src1.eq(Mux(x.sink.csr, x_csr_src1, x.sink.src1)),
            logic.src2.eq(x.sink.src2)
        ]

        adder = cpu.submodules.adder = AdderUnit()
        cpu.d.comb += [
            adder.op.eq(x.sink.adder_sub),
            adder.src1.eq(x.sink.src1),
            adder.src2.eq(Mux(x.sink.store, x.sink.immediate, x.sink.src2))
        ]

        bu = cpu.submodules.bu = BranchUnit()
        cpu.d.comb += [
            # share condition signal between compare and branch instructions
            bu.condition.eq(Mux(x.sink.compare, x.sink.funct3 << 1, x.sink.funct3)),
            bu.cmp_zero.eq(x.sink.src1 == x.sink.src2),
            bu.cmp_negative.eq(adder.result[-1]),
            bu.cmp_overflow.eq(adder.overflow),
            bu.cmp_carry.eq(adder.carry)
        ]

        shifter = cpu.submodules.shifter = Shifter()
        cpu.d.comb += [
            shifter.x_direction.eq(x.sink.direction),
            shifter.x_sext.eq(x.sink.sext),
            shifter.x_shamt.eq(x.sink.src2[:5]),
            shifter.x_src1.eq(x.sink.src1),
            shifter.x_stall.eq(x.stall)
        ]

        if self.with_dcache:
            lsu = cpu.submodules.lsu = CachedLoadStoreUnit(
                    self.dcache_nb_ways, self.dcache_nb_lines, self.dcache_nb_words,
                    self.dcache_base, self.dcache_limit)
            cpu.d.comb += [
                lsu.m_address.eq(m.sink.result),
                lsu.m_dcache_select.eq(m.sink.dcache_select),
                lsu.m_load.eq(m.sink.load & m.valid),
                lsu.m_store.eq(m.sink.store & m.valid),
                lsu.m_dbus_sel.eq(m.sink.dbus_sel),
                lsu.m_store_data.eq(m.sink.store_data),
                lsu.m_stall.eq(m.stall)
            ]

            x.stall_on((lsu.x_load | lsu.x_store) & ~lsu.x_dcache_select \
                    & (self.dbus.cyc | lsu.wrbuf.readable | lsu.dcache.refill_request))
            m.stall_on(lsu.m_load & ~lsu.m_dcache_select & self.dbus.cyc & ~self.dbus.ack)
            m.stall_on(lsu.m_store & lsu.m_dcache_select & ~lsu.wrbuf.writable)
            m.stall_on((lsu.m_store | lsu.m_load) & ~lsu.m_dcache_select & lsu.wrbuf.readable)
            m.stall_on(lsu.dcache.stall_request)

            with cpu.If(~x.stall):
                cpu.d.sync += x.source.dcache_select.eq(lsu.x_dcache_select)

            if self.with_icache:
                cpu.d.comb += dcache_stall_request.eq(lsu.dcache.stall_request)
        else:
            lsu = cpu.submodules.lsu = SimpleLoadStoreUnit()
            m.stall_on(self.dbus.cyc)

        cpu.d.comb += [
            # FIXME
            # lsu.dbus.connect(self.dbus),
            self.dbus.adr.eq(lsu.dbus.adr),
            self.dbus.dat_w.eq(lsu.dbus.dat_w),
            lsu.dbus.dat_r.eq(self.dbus.dat_r),
            self.dbus.sel.eq(lsu.dbus.sel),
            self.dbus.cyc.eq(lsu.dbus.cyc),
            self.dbus.stb.eq(lsu.dbus.stb),
            lsu.dbus.ack.eq(self.dbus.ack),
            self.dbus.we.eq(lsu.dbus.we),
            self.dbus.cti.eq(lsu.dbus.cti),
            self.dbus.bte.eq(lsu.dbus.bte),
            lsu.dbus.err.eq(self.dbus.err),

            lsu.x_address.eq(adder.result),
            lsu.x_load.eq(x.sink.load & x.valid),
            lsu.x_store.eq(x.sink.store & x.valid),
            lsu.x_store_operand.eq(x.sink.src2),
            lsu.x_mask.eq(x.sink.funct3),
            lsu.x_stall.eq(x.stall),
            lsu.w_address.eq(w.sink.result),
            lsu.w_load_mask.eq(w.sink.load_mask),
            lsu.w_load_data.eq(w.sink.load_data)
        ]

        # RAW hazard management

        x_raw_rs1 = Signal()
        m_raw_rs1 = Signal()
        w_raw_rs1 = Signal()
        x_raw_rs2 = Signal()
        m_raw_rs2 = Signal()
        w_raw_rs2 = Signal()
        x_raw_csr = Signal()
        m_raw_csr = Signal()
        w_raw_csr = Signal()
        x_lock = Signal()
        m_lock = Signal()

        cpu.d.comb += [
            x_raw_rs1.eq((x.sink.rd == decoder.rs1) & x.sink.rd_we & x.valid),
            m_raw_rs1.eq((m.sink.rd == decoder.rs1) & m.sink.rd_we & m.valid),
            w_raw_rs1.eq((w.sink.rd == decoder.rs1) & w.sink.rd_we & w.valid),

            x_raw_rs2.eq((x.sink.rd == decoder.rs2) & x.sink.rd_we & x.valid),
            m_raw_rs2.eq((m.sink.rd == decoder.rs2) & m.sink.rd_we & m.valid),
            w_raw_rs2.eq((w.sink.rd == decoder.rs2) & w.sink.rd_we & w.valid),

            x_raw_csr.eq((x.sink.csr_adr == csrf.rp.addr) & x.sink.csr_we & x.valid),
            m_raw_csr.eq((m.sink.csr_adr == csrf.rp.addr) & m.sink.csr_we & m.valid),
            w_raw_csr.eq((w.sink.csr_adr == csrf.rp.addr) & w.sink.csr_we & w.valid),

            x_lock.eq(~x.sink.bypass_x & (decoder.rs1_re & x_raw_rs1 | decoder.rs2_re & x_raw_rs2)),
            m_lock.eq(~m.sink.bypass_m & (decoder.rs1_re & m_raw_rs1 | decoder.rs2_re & m_raw_rs2))
        ]

        d.stall_on((x_lock | m_lock) & d.valid)

        # result selection

        x_result = Signal(32)
        m_result = Signal(32)
        w_result = Signal(32)
        x_csr_result = Signal(32)

        with cpu.If(x.sink.jump):
            cpu.d.comb += x_result.eq(x.sink.pc + 1 << 2)
        with cpu.Elif(x.sink.logic):
            cpu.d.comb += x_result.eq(logic.result)
        with cpu.Elif(x.sink.csr):
            cpu.d.comb += x_result.eq(x.sink.src2)
        with cpu.Else():
            cpu.d.comb += x_result.eq(adder.result)

        with cpu.If(m.sink.compare):
            cpu.d.comb += m_result.eq(m.sink.condition_met)
        with cpu.Elif(m.sink.shift):
            cpu.d.comb += m_result.eq(shifter.m_result)
        with cpu.Else():
            cpu.d.comb += m_result.eq(m.sink.result)

        with cpu.If(w.sink.load):
            cpu.d.comb += w_result.eq(lsu.w_load_result)
        with cpu.Else():
            cpu.d.comb += w_result.eq(w.sink.result)

        with cpu.If(x_csr_set_clear):
            cpu.d.comb += x_csr_result.eq(logic.result)
        with cpu.Else():
            cpu.d.comb += x_csr_result.eq(x.sink.src1)

        # D stage operand selection

        d_src1 = Signal(32)
        d_src2 = Signal(32)

        with cpu.If(decoder.lui):
            cpu.d.comb += d_src1.eq(0)
        with cpu.Elif(decoder.auipc):
            cpu.d.comb += d_src1.eq(d.sink.pc << 2)
        with cpu.Elif(decoder.rs1_re & (decoder.rs1 == 0)):
            cpu.d.comb += d_src1.eq(0)
        with cpu.Elif(x_raw_rs1):
            cpu.d.comb += d_src1.eq(x_result)
        with cpu.Elif(m_raw_rs1):
            cpu.d.comb += d_src1.eq(m_result)
        with cpu.Elif(w_raw_rs1):
            cpu.d.comb += d_src1.eq(w_result)
        with cpu.Else():
            cpu.d.comb += d_src1.eq(gprf.rp1.data)

        with cpu.If(decoder.csr):
            with cpu.If(x_raw_csr):
                cpu.d.comb += d_src2.eq(x_csr_result)
            with cpu.Elif(m_raw_csr):
                cpu.d.comb += d_src2.eq(m.sink.csr_result)
            with cpu.Elif(w_raw_csr):
                cpu.d.comb += d_src2.eq(w.sink.csr_result)
            with cpu.Else():
                cpu.d.comb += d_src2.eq(csrf.rp.data)
        with cpu.Elif(~decoder.rs2_re):
            cpu.d.comb += d_src2.eq(decoder.immediate)
        with cpu.Elif(decoder.rs2 == 0):
            cpu.d.comb += d_src2.eq(0)
        with cpu.Elif(x_raw_rs2):
            cpu.d.comb += d_src2.eq(x_result)
        with cpu.Elif(m_raw_rs2):
            cpu.d.comb += d_src2.eq(m_result)
        with cpu.Elif(w_raw_rs2):
            cpu.d.comb += d_src2.eq(w_result)
        with cpu.Else():
            cpu.d.comb += d_src2.eq(gprf.rp2.data)

        # csr ports

        mstatus = csrf.get_csr_port(CSRIndex.MSTATUS)
        mtvec = csrf.get_csr_port(CSRIndex.MTVEC)
        mcause = csrf.get_csr_port(CSRIndex.MCAUSE)
        mepc = csrf.get_csr_port(CSRIndex.MEPC)
        mip = csrf.get_csr_port(CSRIndex.MIP)
        mie = csrf.get_csr_port(CSRIndex.MIE)
        irq_pending = csrf.get_csr_port(CSRIndex.IRQ_PENDING)
        irq_mask = csrf.get_csr_port(CSRIndex.IRQ_MASK)

        # branch prediction

        bp = cpu.submodules.bp = BranchPredictor()
        cpu.d.comb += [
            bp.d_branch.eq(decoder.branch),
            bp.d_jump.eq(decoder.jump),
            bp.d_offset.eq(decoder.immediate),
            bp.d_pc.eq(d.sink.pc),
            bp.d_rs1_re.eq(decoder.rs1_re),
            bp.d_src1.eq(d_src1)
        ]

        x_branch_taken = Signal()
        cpu.d.comb += [
            d_branch_predict_taken.eq(bp.d_branch_predict_taken),
            d_branch_target.eq(bp.d_branch_target),
            x_branch_taken.eq(x.sink.jump | x.sink.branch & bu.condition_met),
        ]

        f.kill_on(x.sink.branch_predict_taken & x.valid)
        for s in a, f:
            s.kill_on(m.sink.branch_predict_taken & ~m.sink.branch_taken & m.valid)
        for s in a, f, d:
            s.kill_on(~m.sink.branch_predict_taken & m.sink.branch_taken & m.valid)

        # exception & interrupt management

        exception_pe = cpu.submodules.exception_pe = PriorityEncoder(16)
        interrupt_pe = cpu.submodules.interrupt_pe = PriorityEncoder(16)
        cpu.d.comb += [
            exception_pe.i[Cause.FETCH_MISALIGNED].eq(x_branch_taken & (x.sink.branch_target[:2] != 0)),
            exception_pe.i[Cause.FETCH_ACCESS_FAULT].eq(x.sink.bus_error),
            exception_pe.i[Cause.ILLEGAL_INSTRUCTION].eq(x.sink.illegal),
            exception_pe.i[Cause.BREAKPOINT].eq(x.sink.ebreak),
            exception_pe.i[Cause.ECALL_FROM_M].eq(x.sink.ecall),

            interrupt_pe.i[Cause.M_SOFTWARE_INTERRUPT].eq(mip.dat_r.msip & mie.dat_r.msie),
            interrupt_pe.i[Cause.M_TIMER_INTERRUPT].eq(mip.dat_r.mtip & mie.dat_r.mtie),
            interrupt_pe.i[Cause.M_EXTERNAL_INTERRUPT].eq(mip.dat_r.meip & mie.dat_r.meie),

            irq_pending.we.eq(1),
            irq_pending.dat_w.value.eq(self.external_interrupt & irq_mask.dat_r.value),

            mip.we.eq(1),
            mip.dat_w.mtip.eq(self.timer_interrupt),
            mip.dat_w.meip.eq(reduce(or_, irq_pending.dat_w.value)),
        ]

        x_exception = Signal()
        cpu.d.comb += x_exception.eq(~exception_pe.n & x.valid | mstatus.dat_r.mie & ~interrupt_pe.n)

        x_mepc = Record(mepc.dat_r.layout)
        with cpu.If(m.sink.csr_we & (m.sink.csr_adr == CSRIndex.MEPC)):
            cpu.d.comb += x_mepc.eq(m.sink.csr_result)
        with cpu.Elif(w.sink.csr_we & (w.sink.csr_adr == CSRIndex.MEPC)):
            cpu.d.comb += x_mepc.eq(w.sink.csr_result)
        with cpu.Else():
            cpu.d.comb += x_mepc.eq(mepc.dat_r)

        x_mtvec = Record(mtvec.dat_r.layout)
        with cpu.If(m.sink.csr_we & (m.sink.csr_adr == CSRIndex.MTVEC)):
            cpu.d.comb += x_mtvec.eq(m.sink.csr_result)
        with cpu.Elif(w.sink.csr_we & (w.sink.csr_adr == CSRIndex.MTVEC)):
            cpu.d.comb += x_mtvec.eq(w.sink.csr_result)
        with cpu.Else():
            cpu.d.comb += x_mtvec.eq(mtvec.dat_r)

        # pipeline registers

        # A/F
        with cpu.If(~a.stall):
            cpu.d.sync += a.source.pc.eq(ifu.a_pc)

        # F/D
        with cpu.If(~f.stall):
            cpu.d.sync += [
                f.source.pc.eq(f.sink.pc[:30]),
                f.source.instruction.eq(ifu.f_instruction),
                f.source.bus_error.eq(ifu.f_bus_error)
            ]

        # D/X
        with cpu.If(~d.stall):
            cpu.d.sync += [
                d.source.pc.eq(d.sink.pc),
                d.source.bus_error.eq(d.sink.bus_error),
                d.source.rd.eq(decoder.rd),
                d.source.rs1.eq(decoder.rs1),
                d.source.rd_we.eq(decoder.rd_we),
                d.source.rs1_re.eq(decoder.rs1_re),
                d.source.immediate.eq(decoder.immediate),
                d.source.bypass_x.eq(decoder.bypass_x),
                d.source.bypass_m.eq(decoder.bypass_m),
                d.source.funct3.eq(decoder.funct3),
                d.source.load.eq(decoder.load),
                d.source.store.eq(decoder.store),
                d.source.adder_sub.eq(decoder.adder_sub),
                d.source.compare.eq(decoder.compare),
                d.source.logic.eq(decoder.logic),
                d.source.shift.eq(decoder.shift),
                d.source.direction.eq(decoder.direction),
                d.source.sext.eq(decoder.sext),
                d.source.jump.eq(decoder.jump),
                d.source.branch.eq(decoder.branch),
                d.source.fence_i.eq(decoder.fence_i),
                d.source.csr.eq(decoder.csr),
                d.source.csr_adr.eq(decoder.immediate[:12]),
                d.source.csr_we.eq(decoder.csr_we),
                d.source.ecall.eq(decoder.ecall),
                d.source.ebreak.eq(decoder.ebreak),
                d.source.mret.eq(decoder.mret),
                d.source.illegal.eq(decoder.illegal),
                d.source.src1.eq(d_src1),
                d.source.src2.eq(d_src2),
                d.source.branch_predict_taken.eq(bp.d_branch_predict_taken),
                d.source.branch_target.eq(bp.d_branch_target)
            ]

        # X/M
        with cpu.If(~x.stall):
            cpu.d.sync += [
                x.source.pc.eq(x.sink.pc),
                x.source.rd.eq(x.sink.rd),
                x.source.rd_we.eq(x.sink.rd_we),
                x.source.bypass_m.eq(x.sink.bypass_m | x.sink.bypass_x),
                x.source.load.eq(x.sink.load),
                x.source.load_mask.eq(x.sink.funct3),
                x.source.store.eq(x.sink.store),
                x.source.dbus_sel.eq(lsu.x_dbus_sel),
                x.source.store_data.eq(lsu.x_store_data),
                x.source.compare.eq(x.sink.compare),
                x.source.shift.eq(x.sink.shift),
                x.source.csr_adr.eq(x.sink.csr_adr),
                x.source.csr_we.eq(x.sink.csr & x.sink.csr_we),
                x.source.csr_result.eq(x_csr_result),
                x.source.exception.eq(x_exception),
                x.source.mret.eq(x.sink.mret),
                x.source.condition_met.eq(bu.condition_met),
                x.source.branch_taken.eq(x_branch_taken | x_exception | x.sink.mret),
                x.source.branch_predict_taken.eq(x.sink.branch_predict_taken & ~x_exception),
                x.source.mcause.interrupt.eq(mstatus.dat_r.mie & ~interrupt_pe.n),
                x.source.mcause.ecode.eq(Mux(exception_pe.n, interrupt_pe.o, exception_pe.o)),
                x.source.result.eq(x_result)
            ]

            with cpu.If(x_exception):
                cpu.d.sync += x.source.branch_target.eq(x_mtvec.base << 2)
            with cpu.Elif(x.sink.mret):
                cpu.d.sync += x.source.branch_target.eq(x_mepc.value)
            with cpu.Else():
                cpu.d.sync += x.source.branch_target.eq(x.sink.branch_target)

            with cpu.If(x.sink.ecall | x.sink.ebreak | mstatus.dat_r.mie & ~interrupt_pe.n):
                cpu.d.sync += [
                    x.source.mepc.value.eq(x.sink.pc << 2),
                    x.source.rd_we.eq(0)
                ]
            with cpu.Else():
                cpu.d.sync += [
                    x.source.mepc.value.eq(x.sink.pc + 1 << 2),
                    x.source.rd_we.eq(x.sink.rd_we)
                ]

        # M/W
        with cpu.If(~m.stall):
            cpu.d.sync += [
                m.source.pc.eq(m.sink.pc),
                m.source.rd.eq(m.sink.rd),
                m.source.load.eq(m.sink.load),
                m.source.load_mask.eq(m.sink.load_mask),
                m.source.load_data.eq(lsu.m_load_data),
                m.source.csr_adr.eq(m.sink.csr_adr),
                m.source.csr_we.eq(m.sink.csr_we),
                m.source.csr_result.eq(m.sink.csr_result),
                m.source.mret.eq(m.sink.mret),
                m.source.exception.eq(m.sink.exception),
                m.source.mcause.eq(m.sink.mcause),
                m.source.mepc.eq(m.sink.mepc),
                m.source.rd_we.eq(m.sink.rd_we),
                m.source.result.eq(m_result)
            ]

        # W
        cpu.d.comb += [
            gprf.wp.en.eq((w.sink.rd != 0) & w.sink.rd_we & w.valid),
            gprf.wp.addr.eq(w.sink.rd),
            gprf.wp.data.eq(w_result),
            csrf.wp.en.eq(w.sink.csr_we & w.valid),
            csrf.wp.addr.eq(w.sink.csr_adr),
            csrf.wp.data.eq(w.sink.csr_result),
            mstatus.we.eq((w.sink.exception | w.sink.mret) & w.valid)
        ]
        with cpu.If(w.sink.exception):
            cpu.d.comb += [
                mstatus.dat_w.mpie.eq(mstatus.dat_r.mie),
                mstatus.dat_w.mie.eq(0)
            ]
        with cpu.Elif(w.sink.mret):
            cpu.d.comb += mstatus.dat_w.mie.eq(mstatus.dat_r.mpie)
        cpu.d.comb += [
            mcause.we.eq(w.sink.exception & w.valid),
            mcause.dat_w.eq(w.sink.mcause),
            mepc.we.eq(w.sink.exception & w.valid),
            mepc.dat_w.eq(w.sink.mepc),
        ]

        return cpu
