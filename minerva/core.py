from functools import reduce
from operator import or_
from itertools import tee

from nmigen import *
from nmigen.lib.coding import PriorityEncoder

from .isa import *
from .stage import *
from .csr import *

from .units.adder import *
from .units.compare import *
from .units.debug import *
from .units.decoder import *
from .units.divider import *
from .units.exception import *
from .units.fetch import *
from .units.rvficon import *
from .units.loadstore import *
from .units.logic import *
from .units.multiplier import *
from .units.predict import *
from .units.shifter import *
from .units.trigger import *

from .units.debug.jtag import jtag_layout
from .wishbone import wishbone_layout, WishboneArbiter


__all__ = ["Minerva"]


_af_layout = [
    ("pc",      (33, True)),
]


_fd_layout = [
    ("pc",               32),
    ("instruction",      32),
    ("fetch_error",       1),
    ("fetch_badaddr",    30)
]


_dx_layout = [
    ("pc",                  32),
    ("instruction",         32),
    ("fetch_error",          1),
    ("fetch_badaddr",       30),
    ("illegal",              1),
    ("rd",                   5),
    ("rs1",                  5),
    ("rd_we",                1),
    ("rs1_re",               1),
    ("src1",                32),
    ("src2",                32),
    ("store_operand",       32),
    ("bypass_x",             1),
    ("bypass_m",             1),
    ("funct3",               3),
    ("load",                 1),
    ("store",                1),
    ("adder_sub",            1),
    ("logic",                1),
    ("multiply",             1),
    ("divide",               1),
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
    ("ecall",                1),
    ("ebreak",               1),
    ("mret",                 1),
]


_xm_layout = [
    ("pc",                  32),
    ("instruction",         32),
    ("fetch_error",          1),
    ("fetch_badaddr",       30),
    ("illegal",              1),
    ("loadstore_misaligned", 1),
    ("ecall",                1),
    ("ebreak",               1),
    ("rd",                   5),
    ("rd_we",                1),
    ("bypass_m",             1),
    ("funct3",               3),
    ("result",              32),
    ("shift",                1),
    ("load",                 1),
    ("store",                1),
    ("store_data",          32),
    ("compare",              1),
    ("multiply",             1),
    ("divide",               1),
    ("condition_met",        1),
    ("branch_target",       32),
    ("branch_taken",         1),
    ("branch_predict_taken", 1),
    ("csr",                  1),
    ("csr_adr",             12),
    ("csr_we",               1),
    ("csr_result",          32),
    ("mret",                 1),
    ("exception",            1)
]


_mw_layout = [
    ("pc",                32),
    ("rd",                 5),
    ("rd_we",              1),
    ("funct3",             3),
    ("result",            32),
    ("load",               1),
    ("load_data",         32),
    ("multiply",           1),
    ("exception",          1)
]


class Minerva(Elaboratable):
    def __init__(self, reset_address=0x00000000,
                with_icache=False,
                icache_nways=1, icache_nlines=32, icache_nwords=4, icache_base=0, icache_limit=2**31,
                with_dcache=False,
                dcache_nways=1, dcache_nlines=32, dcache_nwords=4, dcache_base=0, dcache_limit=2**31,
                with_muldiv=False,
                with_debug=False,
                with_trigger=False, nb_triggers=8,
                with_rvfi=False):
        self.external_interrupt = Signal(32)
        self.timer_interrupt = Signal()
        self.software_interrupt = Signal()
        self.ibus = Record(wishbone_layout)
        self.dbus = Record(wishbone_layout)

        if with_debug:
            self.jtag = Record(jtag_layout)

        if with_rvfi:
            self.rvfi = Record(rvfi_layout)

        self.reset_address = reset_address
        self.with_icache   = with_icache
        self.icache_args   = icache_nways, icache_nlines, icache_nwords, icache_base, icache_limit
        self.with_dcache   = with_dcache
        self.dcache_args   = dcache_nways, dcache_nlines, dcache_nwords, dcache_base, dcache_limit
        self.with_muldiv   = with_muldiv
        self.with_debug    = with_debug
        self.with_trigger  = with_trigger
        self.nb_triggers   = nb_triggers
        self.with_rvfi     = with_rvfi

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
            cpu.d.comb += s1.source.connect(s2.sink)

        a.source.pc.reset = self.reset_address - 4
        cpu.d.comb += a.valid.eq(Const(1))

        # units

        pc_sel    = cpu.submodules.pc_sel    = PCSelector()
        data_sel  = cpu.submodules.data_sel  = DataSelector()
        adder     = cpu.submodules.adder     = Adder()
        compare   = cpu.submodules.compare   = CompareUnit()
        decoder   = cpu.submodules.decoder   = InstructionDecoder(self.with_muldiv)
        exception = cpu.submodules.exception = ExceptionUnit()
        logic     = cpu.submodules.logic     = LogicUnit()
        predict   = cpu.submodules.predict   = BranchPredictor()
        shifter   = cpu.submodules.shifter   = Shifter()

        if self.with_icache:
            fetch = cpu.submodules.fetch = CachedFetchUnit(*self.icache_args)
        else:
            fetch = cpu.submodules.fetch = BareFetchUnit()

        if self.with_dcache:
            loadstore = cpu.submodules.loadstore = CachedLoadStoreUnit(*self.dcache_args)
        else:
            loadstore = cpu.submodules.loadstore = BareLoadStoreUnit()

        if self.with_muldiv:
            multiplier = Multiplier() if not self.with_rvfi else DummyMultiplier()
            divider    = Divider()    if not self.with_rvfi else DummyDivider()
            cpu.submodules.multiplier = multiplier
            cpu.submodules.divider    = divider

        if self.with_debug:
            debug = cpu.submodules.debug = DebugUnit()

        if self.with_trigger:
            trigger = cpu.submodules.trigger = TriggerUnit(self.nb_triggers)

        if self.with_rvfi:
            rvficon = cpu.submodules.rvficon = RVFIController()

        # register files

        gprf = Memory(width=32, depth=32)
        gprf_rp1 = gprf.read_port()
        gprf_rp2 = gprf.read_port()
        gprf_wp  = gprf.write_port()
        cpu.submodules += gprf_rp1, gprf_rp2, gprf_wp

        csrf = cpu.submodules.csrf = CSRFile()
        csrf_rp = csrf.read_port()
        csrf_wp = csrf.write_port()

        csrf.add_csrs(exception.iter_csrs())
        if self.with_debug:
            csrf.add_csrs(debug.iter_csrs())
        if self.with_trigger:
            csrf.add_csrs(trigger.iter_csrs())

        # pipeline logic

        cpu.d.comb += [
            pc_sel.f_pc.eq(f.sink.pc),
            pc_sel.d_pc.eq(d.sink.pc),
            pc_sel.d_branch_predict_taken.eq(predict.d_branch_taken),
            pc_sel.d_branch_target.eq(predict.d_branch_target),
            pc_sel.d_valid.eq(d.valid),
            pc_sel.x_pc.eq(x.sink.pc),
            pc_sel.x_fence_i.eq(x.sink.fence_i),
            pc_sel.x_valid.eq(x.valid),
            pc_sel.m_branch_predict_taken.eq(m.sink.branch_predict_taken),
            pc_sel.m_branch_taken.eq(m.sink.branch_taken),
            pc_sel.m_branch_target.eq(m.sink.branch_target),
            pc_sel.m_exception.eq(exception.m_raise),
            pc_sel.m_mret.eq(m.sink.mret),
            pc_sel.m_valid.eq(m.valid),
            pc_sel.mtvec_r_base.eq(exception.mtvec.r.base),
            pc_sel.mepc_r_base.eq(exception.mepc.r.base)
        ]

        cpu.d.comb += [
            fetch.a_pc.eq(pc_sel.a_pc),
            fetch.a_stall.eq(a.stall),
            fetch.a_valid.eq(a.valid),
            fetch.f_stall.eq(f.stall),
            fetch.f_valid.eq(f.valid),
            fetch.ibus.connect(self.ibus)
        ]

        m.stall_on(fetch.a_busy & a.valid)
        m.stall_on(fetch.f_busy & f.valid)

        if self.with_icache:
            flush_icache = x.sink.fence_i & x.valid
            if self.with_debug:
                flush_icache |= debug.resumereq

            cpu.d.comb += [
                fetch.f_pc.eq(f.sink.pc),
                fetch.a_flush.eq(flush_icache)
            ]

        cpu.d.comb += [
            decoder.instruction.eq(d.sink.instruction)
        ]

        if self.with_debug:
            with cpu.If(debug.halt & debug.halted):
                cpu.d.comb += gprf_rp1.addr.eq(debug.gprf_addr)
            with cpu.Elif(~d.stall):
                cpu.d.comb += gprf_rp1.addr.eq(fetch.f_instruction[15:20])
            with cpu.Else():
                cpu.d.comb += gprf_rp1.addr.eq(decoder.rs1)

            cpu.d.comb += debug.gprf_dat_r.eq(gprf_rp1.data)
        else:
            with cpu.If(~d.stall):
                cpu.d.comb += gprf_rp1.addr.eq(fetch.f_instruction[15:20])
            with cpu.Else():
                cpu.d.comb += gprf_rp1.addr.eq(decoder.rs1)

        with cpu.If(~d.stall):
            cpu.d.comb += gprf_rp2.addr.eq(fetch.f_instruction[20:25])
        with cpu.Else():
            cpu.d.comb += gprf_rp2.addr.eq(decoder.rs2)

        with cpu.If(~f.stall):
            cpu.d.sync += csrf_rp.addr.eq(fetch.f_instruction[20:32])
        cpu.d.comb += csrf_rp.en.eq(decoder.csr & d.valid)

        # CSR set/clear instructions are translated to logic operations.
        x_csr_set_clear = x.sink.funct3[1]
        x_csr_clear = x_csr_set_clear & x.sink.funct3[0]
        x_csr_fmt_i = x.sink.funct3[2]
        x_csr_src1 = Mux(x_csr_fmt_i, x.sink.rs1, x.sink.src1)
        x_csr_src1 = Mux(x_csr_clear, ~x_csr_src1, x_csr_src1)
        x_csr_logic_op = x.sink.funct3 | 0b100

        cpu.d.comb += [
            logic.op.eq(Mux(x.sink.csr, x_csr_logic_op, x.sink.funct3)),
            logic.src1.eq(Mux(x.sink.csr, x_csr_src1, x.sink.src1)),
            logic.src2.eq(x.sink.src2)
        ]

        cpu.d.comb += [
            adder.sub.eq(x.sink.adder_sub),
            adder.src1.eq(x.sink.src1),
            adder.src2.eq(x.sink.src2),
        ]

        if self.with_muldiv:
            cpu.d.comb += [
                multiplier.x_op.eq(x.sink.funct3),
                multiplier.x_src1.eq(x.sink.src1),
                multiplier.x_src2.eq(x.sink.src2),
                multiplier.x_stall.eq(x.stall),
                multiplier.m_stall.eq(m.stall)
            ]

            cpu.d.comb += [
                divider.x_op.eq(x.sink.funct3),
                divider.x_src1.eq(x.sink.src1),
                divider.x_src2.eq(x.sink.src2),
                divider.x_valid.eq(x.sink.valid),
                divider.x_stall.eq(x.stall)
            ]

            m.stall_on(divider.m_busy)

        cpu.d.comb += [
            shifter.x_direction.eq(x.sink.direction),
            shifter.x_sext.eq(x.sink.sext),
            shifter.x_shamt.eq(x.sink.src2),
            shifter.x_src1.eq(x.sink.src1),
            shifter.x_stall.eq(x.stall)
        ]

        cpu.d.comb += [
            # compare.op is shared by compare and branch instructions.
            compare.op.eq(Mux(x.sink.compare, x.sink.funct3 << 1, x.sink.funct3)),
            compare.zero.eq(x.sink.src1 == x.sink.src2),
            compare.negative.eq(adder.result[-1]),
            compare.overflow.eq(adder.overflow),
            compare.carry.eq(adder.carry)
        ]

        cpu.d.comb += [
            exception.external_interrupt.eq(self.external_interrupt),
            exception.timer_interrupt.eq(self.timer_interrupt),
            exception.software_interrupt.eq(self.software_interrupt),
            exception.m_fetch_misaligned.eq(m.sink.branch_taken & m.sink.branch_target[:2].bool()),
            exception.m_fetch_error.eq(m.sink.fetch_error),
            exception.m_fetch_badaddr.eq(m.sink.fetch_badaddr),
            exception.m_load_misaligned.eq(m.sink.load & m.sink.loadstore_misaligned),
            exception.m_load_error.eq(loadstore.m_load_error),
            exception.m_store_misaligned.eq(m.sink.store & m.sink.loadstore_misaligned),
            exception.m_store_error.eq(loadstore.m_store_error),
            exception.m_loadstore_badaddr.eq(loadstore.m_badaddr),
            exception.m_branch_target.eq(m.sink.branch_target),
            exception.m_illegal.eq(m.sink.illegal),
            exception.m_ecall.eq(m.sink.ecall),
            exception.m_pc.eq(m.sink.pc),
            exception.m_instruction.eq(m.sink.instruction),
            exception.m_result.eq(m.sink.result),
            exception.m_mret.eq(m.sink.mret),
            exception.m_stall.eq(m.sink.stall),
            exception.m_valid.eq(m.valid)
        ]

        m_ebreak = m.sink.ebreak
        if self.with_debug:
            # If dcsr.ebreakm is set, EBREAK instructions enter Debug Mode.
            # We do not want to raise an exception in this case because Debug Mode
            # should be invisible to software execution.
            m_ebreak &= ~debug.dcsr_ebreakm
        if self.with_trigger:
            m_trigger_trap = Signal()
            with cpu.If(~x.stall):
                cpu.d.sync += m_trigger_trap.eq(trigger.x_trap)
            m_ebreak |= m_trigger_trap
        cpu.d.comb += exception.m_ebreak.eq(m_ebreak)

        m.kill_on(m.source.exception & m.source.valid)

        cpu.d.comb += [
            data_sel.x_offset.eq(adder.result[:2]),
            data_sel.x_funct3.eq(x.sink.funct3),
            data_sel.x_store_operand.eq(x.sink.store_operand),
            data_sel.w_offset.eq(w.sink.result[:2]),
            data_sel.w_funct3.eq(w.sink.funct3),
            data_sel.w_load_data.eq(w.sink.load_data)
        ]

        cpu.d.comb += [
            loadstore.x_addr.eq(adder.result),
            loadstore.x_mask.eq(data_sel.x_mask),
            loadstore.x_load.eq(x.sink.load),
            loadstore.x_store.eq(x.sink.store),
            loadstore.x_store_data.eq(data_sel.x_store_data),
            loadstore.x_stall.eq(x.stall),
            loadstore.x_valid.eq(x.valid),
            loadstore.m_stall.eq(m.stall),
            loadstore.m_valid.eq(m.valid)
        ]

        m.stall_on(loadstore.x_busy & x.valid)
        m.stall_on(loadstore.m_busy & m.valid)

        if self.with_dcache:
            if self.with_debug:
                cpu.d.comb += loadstore.m_flush.eq(debug.resumereq)

            cpu.d.comb += [
                loadstore.x_fence_i.eq(x.sink.fence_i),
                loadstore.m_load.eq(m.sink.load),
                loadstore.m_store.eq(m.sink.store),
            ]

        for s in a, f:
            s.kill_on(x.sink.fence_i & x.valid)

        if self.with_debug:
            cpu.submodules.dbus_arbiter = dbus_arbiter = WishboneArbiter()
            debug_dbus_port = dbus_arbiter.port(priority=0)
            loadstore_dbus_port = dbus_arbiter.port(priority=1)
            cpu.d.comb += [
                loadstore.dbus.connect(loadstore_dbus_port),
                debug.dbus.connect(debug_dbus_port),
                dbus_arbiter.bus.connect(self.dbus),
            ]
        else:
            cpu.d.comb += loadstore.dbus.connect(self.dbus)

        # RAW hazard management

        x_raw_rs1 = Signal()
        m_raw_rs1 = Signal()
        w_raw_rs1 = Signal()
        x_raw_rs2 = Signal()
        m_raw_rs2 = Signal()
        w_raw_rs2 = Signal()

        x_raw_csr = Signal()
        m_raw_csr = Signal()

        x_lock = Signal()
        m_lock = Signal()

        cpu.d.comb += [
            x_raw_rs1.eq(x.sink.rd.any() & (x.sink.rd == decoder.rs1) & x.sink.rd_we),
            m_raw_rs1.eq(m.sink.rd.any() & (m.sink.rd == decoder.rs1) & m.sink.rd_we),
            w_raw_rs1.eq(w.sink.rd.any() & (w.sink.rd == decoder.rs1) & w.sink.rd_we),

            x_raw_rs2.eq(x.sink.rd.any() & (x.sink.rd == decoder.rs2) & x.sink.rd_we),
            m_raw_rs2.eq(m.sink.rd.any() & (m.sink.rd == decoder.rs2) & m.sink.rd_we),
            w_raw_rs2.eq(w.sink.rd.any() & (w.sink.rd == decoder.rs2) & w.sink.rd_we),

            x_raw_csr.eq((x.sink.csr_adr == decoder.immediate) & x.sink.csr_we),
            m_raw_csr.eq((m.sink.csr_adr == decoder.immediate) & m.sink.csr_we),

            x_lock.eq(~x.sink.bypass_x & (decoder.rs1_re & x_raw_rs1 | decoder.rs2_re & x_raw_rs2)
                     | decoder.csr & x_raw_csr),
            m_lock.eq(~m.sink.bypass_m & (decoder.rs1_re & m_raw_rs1 | decoder.rs2_re & m_raw_rs2)
                     | decoder.csr & m_raw_csr),
        ]

        if self.with_debug:
            d.stall_on((x_lock & x.valid | m_lock & m.valid) & d.valid & ~debug.dcsr_step)
        else:
            d.stall_on((x_lock & x.valid | m_lock & m.valid) & d.valid)

        # result selection

        x_result = Signal(32)
        m_result = Signal(32)
        w_result = Signal(32)
        x_csr_result = Signal(32)

        with cpu.If(x.sink.jump):
            cpu.d.comb += x_result.eq(x.sink.pc + 4)
        with cpu.Elif(x.sink.logic):
            cpu.d.comb += x_result.eq(logic.result)
        with cpu.Elif(x.sink.csr):
            cpu.d.comb += x_result.eq(x.sink.src2)
        with cpu.Else():
            cpu.d.comb += x_result.eq(adder.result)

        with cpu.If(m.sink.compare):
            cpu.d.comb += m_result.eq(m.sink.condition_met)
        if self.with_muldiv:
            with cpu.Elif(m.sink.divide):
                cpu.d.comb += m_result.eq(divider.m_result)
        with cpu.Elif(m.sink.shift):
            cpu.d.comb += m_result.eq(shifter.m_result)
        with cpu.Else():
            cpu.d.comb += m_result.eq(m.sink.result)

        with cpu.If(w.sink.load):
            cpu.d.comb += w_result.eq(data_sel.w_load_result)
        if self.with_muldiv:
            with cpu.Elif(w.sink.multiply):
                cpu.d.comb += w_result.eq(multiplier.w_result)
        with cpu.Else():
            cpu.d.comb += w_result.eq(w.sink.result)

        with cpu.If(x_csr_set_clear):
            cpu.d.comb += x_csr_result.eq(logic.result)
        with cpu.Else():
            cpu.d.comb += x_csr_result.eq(x_csr_src1)

        cpu.d.comb += [
            csrf_wp.en.eq(m.sink.csr & m.sink.csr_we & m.valid & ~exception.m_raise & ~m.stall),
            csrf_wp.addr.eq(m.sink.csr_adr),
            csrf_wp.data.eq(m.sink.csr_result)
        ]

        if self.with_debug:
            with cpu.If(debug.halt & debug.halted):
                cpu.d.comb += [
                    gprf_wp.addr.eq(debug.gprf_addr),
                    gprf_wp.en.eq(debug.gprf_we),
                    gprf_wp.data.eq(debug.gprf_dat_w)
                ]
            with cpu.Else():
                cpu.d.comb += [
                    gprf_wp.en.eq((w.sink.rd != 0) & w.sink.rd_we & w.valid & ~w.sink.exception),
                    gprf_wp.addr.eq(w.sink.rd),
                    gprf_wp.data.eq(w_result)
                ]
        else:
            cpu.d.comb += [
                gprf_wp.en.eq((w.sink.rd != 0) & w.sink.rd_we & w.valid),
                gprf_wp.addr.eq(w.sink.rd),
                gprf_wp.data.eq(w_result)
            ]

        # D stage operand selection

        d_src1 = Signal(32)
        d_src2 = Signal(32)

        with cpu.If(decoder.lui):
            cpu.d.comb += d_src1.eq(0)
        with cpu.Elif(decoder.auipc):
            cpu.d.comb += d_src1.eq(d.sink.pc)
        with cpu.Elif(decoder.rs1_re & (decoder.rs1 == 0)):
            cpu.d.comb += d_src1.eq(0)
        with cpu.Elif(x_raw_rs1 & x.sink.valid):
            cpu.d.comb += d_src1.eq(x_result)
        with cpu.Elif(m_raw_rs1 & m.sink.valid):
            cpu.d.comb += d_src1.eq(m_result)
        with cpu.Elif(w_raw_rs1 & w.sink.valid):
            cpu.d.comb += d_src1.eq(w_result)
        with cpu.Else():
            cpu.d.comb += d_src1.eq(gprf_rp1.data)

        with cpu.If(decoder.csr):
            cpu.d.comb += d_src2.eq(csrf_rp.data)
        with cpu.Elif(~decoder.rs2_re):
            cpu.d.comb += d_src2.eq(decoder.immediate)
        with cpu.Elif(decoder.rs2 == 0):
            cpu.d.comb += d_src2.eq(0)
        with cpu.Elif(x_raw_rs2 & x.sink.valid):
            cpu.d.comb += d_src2.eq(x_result)
        with cpu.Elif(m_raw_rs2 & m.sink.valid):
            cpu.d.comb += d_src2.eq(m_result)
        with cpu.Elif(w_raw_rs2 & w.sink.valid):
            cpu.d.comb += d_src2.eq(w_result)
        with cpu.Else():
            cpu.d.comb += d_src2.eq(gprf_rp2.data)

        # branch prediction

        cpu.d.comb += [
            predict.d_branch.eq(decoder.branch),
            predict.d_jump.eq(decoder.jump),
            predict.d_offset.eq(decoder.immediate),
            predict.d_pc.eq(d.sink.pc),
            predict.d_rs1_re.eq(decoder.rs1_re)
        ]

        a.kill_on(predict.d_branch_taken & d.valid)
        for s in a, f:
            s.kill_on(m.sink.branch_predict_taken & ~m.sink.branch_taken & m.valid)
        for s in a, f, d:
            s.kill_on(~m.sink.branch_predict_taken & m.sink.branch_taken & m.valid)
            s.kill_on((exception.m_raise | m.sink.mret) & m.valid)

        # debug unit

        if self.with_debug:
            cpu.d.comb += [
                debug.jtag.connect(self.jtag),
                debug.x_pc.eq(x.sink.pc),
                debug.x_ebreak.eq(x.sink.ebreak),
                debug.x_stall.eq(x.stall),
                debug.m_branch_taken.eq(m.sink.branch_taken),
                debug.m_branch_target.eq(m.sink.branch_target),
                debug.m_mret.eq(m.sink.mret),
                debug.m_exception.eq(exception.m_raise),
                debug.m_pc.eq(m.sink.pc),
                debug.m_valid.eq(m.valid),
                debug.mepc_r_base.eq(exception.mepc.r.base),
                debug.mtvec_r_base.eq(exception.mtvec.r.base)
            ]

            if self.with_trigger:
                cpu.d.comb += debug.trigger_haltreq.eq(trigger.haltreq)
            else:
                cpu.d.comb += debug.trigger_haltreq.eq(Const(0))

            csrf_debug_rp = csrf.read_port()
            csrf_debug_wp = csrf.write_port()
            cpu.d.comb += [
                csrf_debug_rp.addr.eq(debug.csrf_addr),
                csrf_debug_rp.en.eq(debug.csrf_re),
                debug.csrf_dat_r.eq(csrf_debug_rp.data),
                csrf_debug_wp.addr.eq(debug.csrf_addr),
                csrf_debug_wp.en.eq(debug.csrf_we),
                csrf_debug_wp.data.eq(debug.csrf_dat_w)
            ]

            x.stall_on(debug.halt)
            m.stall_on(debug.dcsr_step & m.valid & ~debug.halt)
            for s in a, f, d, x:
                s.kill_on(debug.killall)

            halted = x.stall & ~reduce(or_, (s.valid for s in (m, w)))
            cpu.d.sync += debug.halted.eq(halted)

            with cpu.If(debug.resumereq):
                with cpu.If(~debug.dbus_busy):
                    cpu.d.comb += debug.resumeack.eq(1)
                    cpu.d.sync += a.source.pc.eq(debug.dpc_value - 4)

        if self.with_trigger:
            cpu.d.comb += [
                trigger.x_pc.eq(x.sink.pc),
                trigger.x_valid.eq(x.valid),
            ]

        if self.with_rvfi:
            cpu.d.comb += [
                rvficon.d_insn.eq(decoder.instruction),
                rvficon.d_rs1_addr.eq(Mux(decoder.rs1_re, decoder.rs1, 0)),
                rvficon.d_rs2_addr.eq(Mux(decoder.rs2_re, decoder.rs2, 0)),
                rvficon.d_rs1_rdata.eq(Mux(decoder.rs1_re, d_src1, 0)),
                rvficon.d_rs2_rdata.eq(Mux(decoder.rs2_re, d_src2, 0)),
                rvficon.d_stall.eq(d.stall),
                rvficon.x_mem_addr.eq(loadstore.x_addr[2:] << 2),
                rvficon.x_mem_wmask.eq(Mux(loadstore.x_store, loadstore.x_mask, 0)),
                rvficon.x_mem_rmask.eq(Mux(loadstore.x_load, loadstore.x_mask, 0)),
                rvficon.x_mem_wdata.eq(loadstore.x_store_data),
                rvficon.x_stall.eq(x.stall),
                rvficon.m_mem_rdata.eq(loadstore.m_load_data),
                rvficon.m_fetch_misaligned.eq(exception.m_fetch_misaligned),
                rvficon.m_illegal_insn.eq(m.sink.illegal),
                rvficon.m_load_misaligned.eq(exception.m_load_misaligned),
                rvficon.m_store_misaligned.eq(exception.m_store_misaligned),
                rvficon.m_exception.eq(exception.m_raise),
                rvficon.m_mret.eq(m.sink.mret),
                rvficon.m_branch_taken.eq(m.sink.branch_taken),
                rvficon.m_branch_target.eq(m.sink.branch_target),
                rvficon.m_pc_rdata.eq(m.sink.pc),
                rvficon.m_stall.eq(m.stall),
                rvficon.m_valid.eq(m.valid),
                rvficon.w_rd_addr.eq(Mux(gprf_wp.en, gprf_wp.addr, 0)),
                rvficon.w_rd_wdata.eq(Mux(gprf_wp.en, gprf_wp.data, 0)),
                rvficon.mtvec_r_base.eq(exception.mtvec.r.base),
                rvficon.mepc_r_value.eq(exception.mepc.r),
                rvficon.rvfi.connect(self.rvfi)
            ]

        # pipeline registers

        # A/F
        with cpu.If(~a.stall):
            cpu.d.sync += a.source.pc.eq(fetch.a_pc)

        # F/D
        with cpu.If(~f.stall):
            cpu.d.sync += [
                f.source.pc.eq(f.sink.pc),
                f.source.instruction.eq(fetch.f_instruction),
                f.source.fetch_error.eq(fetch.f_fetch_error),
                f.source.fetch_badaddr.eq(fetch.f_badaddr)
            ]

        # D/X
        with cpu.If(~d.stall):
            cpu.d.sync += [
                d.source.pc.eq(d.sink.pc),
                d.source.instruction.eq(d.sink.instruction),
                d.source.fetch_error.eq(d.sink.fetch_error),
                d.source.fetch_badaddr.eq(d.sink.fetch_badaddr),
                d.source.illegal.eq(decoder.illegal),
                d.source.rd.eq(decoder.rd),
                d.source.rs1.eq(decoder.rs1),
                d.source.rd_we.eq(decoder.rd_we),
                d.source.rs1_re.eq(decoder.rs1_re),
                d.source.bypass_x.eq(decoder.bypass_x),
                d.source.bypass_m.eq(decoder.bypass_m),
                d.source.funct3.eq(decoder.funct3),
                d.source.load.eq(decoder.load),
                d.source.store.eq(decoder.store),
                d.source.adder_sub.eq(decoder.adder & decoder.adder_sub
                                    | decoder.compare | decoder.branch),
                d.source.compare.eq(decoder.compare),
                d.source.logic.eq(decoder.logic),
                d.source.shift.eq(decoder.shift),
                d.source.direction.eq(decoder.direction),
                d.source.sext.eq(decoder.sext),
                d.source.jump.eq(decoder.jump),
                d.source.branch.eq(decoder.branch),
                d.source.fence_i.eq(decoder.fence_i),
                d.source.csr.eq(decoder.csr),
                d.source.csr_adr.eq(decoder.immediate),
                d.source.csr_we.eq(decoder.csr_we),
                d.source.ecall.eq(decoder.ecall),
                d.source.ebreak.eq(decoder.ebreak),
                d.source.mret.eq(decoder.mret),
                d.source.src1.eq(d_src1),
                d.source.src2.eq(Mux(decoder.store, decoder.immediate, d_src2)),
                d.source.store_operand.eq(d_src2),
                d.source.branch_predict_taken.eq(predict.d_branch_taken),
                d.source.branch_target.eq(predict.d_branch_target)
            ]

            if self.with_muldiv:
                cpu.d.sync += [
                    d.source.multiply.eq(decoder.multiply),
                    d.source.divide.eq(decoder.divide)
                ]

        # X/M
        with cpu.If(~x.stall):
            cpu.d.sync += [
                x.source.pc.eq(x.sink.pc),
                x.source.instruction.eq(x.sink.instruction),
                x.source.fetch_error.eq(x.sink.fetch_error),
                x.source.fetch_badaddr.eq(x.sink.fetch_badaddr),
                x.source.illegal.eq(x.sink.illegal),
                x.source.loadstore_misaligned.eq(data_sel.x_misaligned),
                x.source.ecall.eq(x.sink.ecall),
                x.source.ebreak.eq(x.sink.ebreak),
                x.source.rd.eq(x.sink.rd),
                x.source.rd_we.eq(x.sink.rd_we),
                x.source.bypass_m.eq(x.sink.bypass_m | x.sink.bypass_x),
                x.source.funct3.eq(x.sink.funct3),
                x.source.load.eq(x.sink.load),
                x.source.store.eq(x.sink.store),
                x.source.store_data.eq(loadstore.x_store_data),
                x.source.compare.eq(x.sink.compare),
                x.source.shift.eq(x.sink.shift),
                x.source.mret.eq(x.sink.mret),
                x.source.condition_met.eq(compare.condition_met),
                x.source.branch_taken.eq(x.sink.jump | x.sink.branch & compare.condition_met),
                x.source.branch_target.eq(Mux(x.sink.jump & x.sink.rs1_re, adder.result[1:] << 1, x.sink.branch_target)),
                x.source.branch_predict_taken.eq(x.sink.branch_predict_taken),
                x.source.csr.eq(x.sink.csr),
                x.source.csr_adr.eq(x.sink.csr_adr),
                x.source.csr_we.eq(x.sink.csr_we),
                x.source.csr_result.eq(x_csr_result),
                x.source.result.eq(x_result)
            ]
            if self.with_muldiv:
                cpu.d.sync += [
                    x.source.multiply.eq(x.sink.multiply),
                    x.source.divide.eq(x.sink.divide)
                ]

        # M/W
        with cpu.If(~m.stall):
            cpu.d.sync += [
                m.source.pc.eq(m.sink.pc),
                m.source.rd.eq(m.sink.rd),
                m.source.load.eq(m.sink.load),
                m.source.funct3.eq(m.sink.funct3),
                m.source.load_data.eq(loadstore.m_load_data),
                m.source.rd_we.eq(m.sink.rd_we),
                m.source.result.eq(m_result),
                m.source.exception.eq(exception.m_raise)
            ]
            if self.with_muldiv:
                cpu.d.sync += [
                    m.source.multiply.eq(m.sink.multiply)
                ]

        return cpu
