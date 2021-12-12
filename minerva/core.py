from functools import reduce
from operator import or_
from itertools import tee

from amaranth import *
from amaranth.lib.coding import PriorityEncoder

from .isa import *
from .stage import *
from .csr import *
from . import gpr

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
    def __init__(self,
            reset_address = 0x00000000,
            with_icache   = False,
            icache_nways  = 1,
            icache_nlines = 32,
            icache_nwords = 4,
            icache_base   = 0,
            icache_limit  = 2**31,
            with_dcache   = False,
            dcache_nways  = 1,
            dcache_nlines = 32,
            dcache_nwords = 4,
            dcache_base   = 0,
            dcache_limit  = 2**31,
            wrbuf_depth   = 8,
            with_muldiv   = False,
            with_debug    = False,
            with_trigger  = False,
            nb_triggers   = 8,
            with_rvfi     = False):

        # Ports

        self.external_interrupt = Signal(32)
        self.timer_interrupt    = Signal()
        self.software_interrupt = Signal()

        self.ibus = Record(wishbone_layout)
        self.dbus = Record(wishbone_layout)

        if with_debug:
            self.jtag = Record(jtag_layout)
        else:
            self.jtag = None

        if with_rvfi:
            self.rvfi = Record(rvfi_layout)
        else:
            self.rvfi = None

        self.reset_address = reset_address
        self.with_icache   = with_icache
        self.with_dcache   = with_dcache
        self.with_muldiv   = with_muldiv
        self.with_debug    = with_debug
        self.with_trigger  = with_trigger
        self.with_rvfi     = with_rvfi

        # Pipeline stages

        self._a = Stage(None, _af_layout)
        self._f = Stage(_af_layout, _fd_layout)
        self._d = Stage(_fd_layout, _dx_layout)
        self._x = Stage(_dx_layout, _xm_layout)
        self._m = Stage(_xm_layout, _mw_layout)
        self._w = Stage(_mw_layout, None)

        # Units

        self._pc_sel    = PCSelector()
        self._data_sel  = DataSelector()
        self._adder     = Adder()
        self._compare   = CompareUnit()
        self._decoder   = InstructionDecoder(with_muldiv)
        self._exception = ExceptionUnit()
        self._logic     = LogicUnit()
        self._predict   = BranchPredictor()
        self._shifter   = Shifter()

        if with_icache:
            self._fetch = CachedFetchUnit(
                icache_nways  = icache_nways,
                icache_nlines = icache_nlines,
                icache_nwords = icache_nwords,
                icache_base   = icache_base,
                icache_limit  = icache_limit,
            )
        else:
            self._fetch = BareFetchUnit()

        if with_dcache:
            self._loadstore = CachedLoadStoreUnit(
                dcache_nways  = dcache_nways,
                dcache_nlines = dcache_nlines,
                dcache_nwords = dcache_nwords,
                dcache_base   = dcache_base,
                dcache_limit  = dcache_limit,
                wrbuf_depth   = wrbuf_depth,
            )
        else:
            self._loadstore = BareLoadStoreUnit()

        if with_muldiv:
            if with_rvfi:
                self._multiplier = DummyMultiplier()
                self._divider    = DummyDivider()
            else:
                self._multiplier = Multiplier()
                self._divider    = Divider()
        else:
            self._multiplier = None
            self._divider    = None

        if with_debug:
            self._debug        = DebugUnit()
            self._dbus_arbiter = WishboneArbiter()
        else:
            self._debug        = None
            self._dbus_arbiter = None

        if self.with_trigger:
            self._trigger = TriggerUnit(nb_triggers)
        else:
            self._trigger = None

        if self.with_rvfi:
            self._rvficon = RVFIController()
        else:
            self._rvficon = None

        # Register files

        self._gprf = gpr.File(width=32, depth=32)
        self._csrf = CSRFile()

        self._csrf.add_csrs(self._exception.iter_csrs())
        if with_debug:
            self._csrf.add_csrs(self._debug.iter_csrs())
        if with_trigger:
            self._csrf.add_csrs(self._trigger.iter_csrs())

    def elaborate(self, platform):
        cpu = Module()

        cpu.submodules.a = self._a
        cpu.submodules.f = self._f
        cpu.submodules.d = self._d
        cpu.submodules.x = self._x
        cpu.submodules.m = self._m
        cpu.submodules.w = self._w

        stages = self._a, self._f, self._d, self._x, self._m, self._w
        sources, sinks = tee(stages)
        next(sinks)
        for s1, s2 in zip(sources, sinks):
            cpu.d.comb += s1.source.connect(s2.sink)

        self._a.source.pc.reset = self.reset_address - 4
        cpu.d.comb += self._a.valid.eq(Const(1))

        cpu.submodules.pc_sel    = self._pc_sel
        cpu.submodules.data_sel  = self._data_sel
        cpu.submodules.adder     = self._adder
        cpu.submodules.compare   = self._compare
        cpu.submodules.decoder   = self._decoder
        cpu.submodules.exception = self._exception
        cpu.submodules.logic     = self._logic
        cpu.submodules.predict   = self._predict
        cpu.submodules.shifter   = self._shifter
        cpu.submodules.fetch     = self._fetch
        cpu.submodules.loadstore = self._loadstore

        if self.with_muldiv:
            cpu.submodules.multiplier = self._multiplier
            cpu.submodules.divider    = self._divider

        if self.with_debug:
            cpu.submodules.debug        = self._debug
            cpu.submodules.dbus_arbiter = self._dbus_arbiter

        if self.with_trigger:
            cpu.submodules.trigger = self._trigger

        if self.with_rvfi:
            cpu.submodules.rvficon = self._rvficon

        cpu.submodules.gprf = self._gprf
        cpu.submodules.csrf = self._csrf

        csrf_rp = self._csrf.read_port()
        csrf_wp = self._csrf.write_port()

        # Pipeline logic

        cpu.d.comb += [
            self._pc_sel.f_pc                  .eq(self._f.sink.pc),
            self._pc_sel.d_pc                  .eq(self._d.sink.pc),
            self._pc_sel.d_branch_predict_taken.eq(self._predict.d_branch_taken),
            self._pc_sel.d_branch_target       .eq(self._predict.d_branch_target),
            self._pc_sel.d_valid               .eq(self._d.valid),
            self._pc_sel.x_pc                  .eq(self._x.sink.pc),
            self._pc_sel.x_fence_i             .eq(self._x.sink.fence_i),
            self._pc_sel.x_valid               .eq(self._x.valid),
            self._pc_sel.m_branch_predict_taken.eq(self._m.sink.branch_predict_taken),
            self._pc_sel.m_branch_taken        .eq(self._m.sink.branch_taken),
            self._pc_sel.m_branch_target       .eq(self._m.sink.branch_target),
            self._pc_sel.m_exception           .eq(self._exception.m_raise),
            self._pc_sel.m_mret                .eq(self._m.sink.mret),
            self._pc_sel.m_valid               .eq(self._m.valid),
            self._pc_sel.mtvec_r_base          .eq(self._exception.mtvec.r.base),
            self._pc_sel.mepc_r_base           .eq(self._exception.mepc.r.base)
        ]

        cpu.d.comb += [
            self._fetch.a_pc   .eq(self._pc_sel.a_pc),
            self._fetch.a_stall.eq(self._a.stall),
            self._fetch.a_valid.eq(self._a.valid),
            self._fetch.f_stall.eq(self._f.stall),
            self._fetch.f_valid.eq(self._f.valid),

            self._fetch.ibus.connect(self.ibus),
        ]

        self._m.stall_on(self._fetch.a_busy & self._a.valid)
        self._m.stall_on(self._fetch.f_busy & self._f.valid)

        if self.with_icache:
            flush_icache = self._x.sink.fence_i & self._x.valid
            if self.with_debug:
                flush_icache |= self._debug.resumereq

            cpu.d.comb += [
                self._fetch.f_pc   .eq(self._f.sink.pc),
                self._fetch.a_flush.eq(flush_icache)
            ]

        cpu.d.comb += [
            self._decoder.instruction.eq(self._d.sink.instruction)
        ]

        if self.with_debug:
            with cpu.If(self._debug.halt & self._debug.halted):
                cpu.d.comb += self._gprf.rp1.addr.eq(self._debug.gprf_addr)
            with cpu.Elif(~self._d.stall):
                cpu.d.comb += self._gprf.rp1.addr.eq(self._fetch.f_instruction[15:20])
            with cpu.Else():
                cpu.d.comb += self._gprf.rp1.addr.eq(self._decoder.rs1)

            cpu.d.comb += self._debug.gprf_dat_r.eq(self._gprf.rp1.data)
        else:
            with cpu.If(~self._d.stall):
                cpu.d.comb += self._gprf.rp1.addr.eq(self._fetch.f_instruction[15:20])
            with cpu.Else():
                cpu.d.comb += self._gprf.rp1.addr.eq(self._decoder.rs1)

        with cpu.If(~self._d.stall):
            cpu.d.comb += self._gprf.rp2.addr.eq(self._fetch.f_instruction[20:25])
        with cpu.Else():
            cpu.d.comb += self._gprf.rp2.addr.eq(self._decoder.rs2)

        with cpu.If(~self._f.stall):
            cpu.d.sync += csrf_rp.addr.eq(self._fetch.f_instruction[20:32])
        cpu.d.comb += csrf_rp.en.eq(self._decoder.csr & self._d.valid)

        # CSR set/clear instructions are translated to logic operations.
        x_csr_set_clear = self._x.sink.funct3[1]
        x_csr_clear     = x_csr_set_clear & self._x.sink.funct3[0]
        x_csr_fmt_i     = self._x.sink.funct3[2]
        x_csr_src1      = Mux(x_csr_fmt_i, self._x.sink.rs1, self._x.sink.src1)
        x_csr_src1      = Mux(x_csr_clear, ~x_csr_src1, x_csr_src1)
        x_csr_logic_op  = self._x.sink.funct3 | 0b100

        cpu.d.comb += [
            self._logic.op  .eq(Mux(self._x.sink.csr, x_csr_logic_op, self._x.sink.funct3)),
            self._logic.src1.eq(Mux(self._x.sink.csr, x_csr_src1, self._x.sink.src1)),
            self._logic.src2.eq(self._x.sink.src2)
        ]

        cpu.d.comb += [
            self._adder.d_sub  .eq(self._decoder.adder & self._decoder.adder_sub
                                 | self._decoder.compare | self._decoder.branch),
            self._adder.d_stall.eq(self._d.stall),
            self._adder.x_src1 .eq(self._x.sink.src1),
            self._adder.x_src2 .eq(self._x.sink.src2),
        ]

        if self.with_muldiv:
            cpu.d.comb += [
                self._multiplier.d_op   .eq(self._decoder.funct3),
                self._multiplier.d_stall.eq(self._d.stall),
                self._multiplier.x_src1 .eq(self._x.sink.src1),
                self._multiplier.x_src2 .eq(self._x.sink.src2),
                self._multiplier.x_stall.eq(self._x.stall),
                self._multiplier.m_stall.eq(self._m.stall),
            ]

            cpu.d.comb += [
                self._divider.x_op   .eq(self._x.sink.funct3),
                self._divider.x_src1 .eq(self._x.sink.src1),
                self._divider.x_src2 .eq(self._x.sink.src2),
                self._divider.x_valid.eq(self._x.sink.valid),
                self._divider.x_stall.eq(self._x.stall),
            ]

            self._m.stall_on(self._divider.m_busy)

        cpu.d.comb += [
            self._shifter.x_direction.eq(self._x.sink.direction),
            self._shifter.x_sext     .eq(self._x.sink.sext),
            self._shifter.x_shamt    .eq(self._x.sink.src2),
            self._shifter.x_src1     .eq(self._x.sink.src1),
            self._shifter.x_stall    .eq(self._x.stall),
        ]

        # compare.op is shared by compare and branch instructions.
        with cpu.If(self._x.sink.compare):
            cpu.d.comb += self._compare.op.eq(self._x.sink.funct3[:2] << 1)
        with cpu.Else():
            cpu.d.comb += self._compare.op.eq(self._x.sink.funct3)

        cpu.d.comb += [
            self._compare.zero    .eq(self._x.sink.src1 == self._x.sink.src2),
            self._compare.negative.eq(self._adder.x_result[-1]),
            self._compare.overflow.eq(self._adder.x_overflow),
            self._compare.carry   .eq(self._adder.x_carry)
        ]

        cpu.d.comb += [
            self._exception.external_interrupt .eq(self.external_interrupt),
            self._exception.timer_interrupt    .eq(self.timer_interrupt),
            self._exception.software_interrupt .eq(self.software_interrupt),
            self._exception.m_fetch_misaligned .eq(self._m.sink.branch_taken
                                                 & self._m.sink.branch_target[:2].bool()),
            self._exception.m_fetch_error      .eq(self._m.sink.fetch_error),
            self._exception.m_fetch_badaddr    .eq(self._m.sink.fetch_badaddr),
            self._exception.m_load_misaligned  .eq(self._m.sink.load
                                                 & self._m.sink.loadstore_misaligned),
            self._exception.m_load_error       .eq(self._loadstore.m_load_error),
            self._exception.m_store_misaligned .eq(self._m.sink.store
                                                 & self._m.sink.loadstore_misaligned),
            self._exception.m_store_error      .eq(self._loadstore.m_store_error),
            self._exception.m_loadstore_badaddr.eq(self._loadstore.m_badaddr),
            self._exception.m_branch_target    .eq(self._m.sink.branch_target),
            self._exception.m_illegal          .eq(self._m.sink.illegal),
            self._exception.m_ecall            .eq(self._m.sink.ecall),
            self._exception.m_pc               .eq(self._m.sink.pc),
            self._exception.m_instruction      .eq(self._m.sink.instruction),
            self._exception.m_result           .eq(self._m.sink.result),
            self._exception.m_mret             .eq(self._m.sink.mret),
            self._exception.m_stall            .eq(self._m.sink.stall),
            self._exception.m_valid            .eq(self._m.valid)
        ]

        m_ebreak = self._m.sink.ebreak
        if self.with_debug:
            # If dcsr.ebreakm is set, EBREAK instructions enter Debug Mode.
            # We do not want to raise an exception in this case because Debug Mode
            # should be invisible to software execution.
            m_ebreak &= ~self._debug.dcsr_ebreakm
        if self.with_trigger:
            m_trigger_trap = Signal()
            with cpu.If(~self._x.stall):
                cpu.d.sync += m_trigger_trap.eq(self._trigger.x_trap)
            m_ebreak |= m_trigger_trap
        cpu.d.comb += self._exception.m_ebreak.eq(m_ebreak)

        self._m.kill_on(self._m.source.exception & self._m.source.valid)

        cpu.d.comb += [
            self._data_sel.x_offset       .eq(self._adder.x_result[:2]),
            self._data_sel.x_funct3       .eq(self._x.sink.funct3),
            self._data_sel.x_store_operand.eq(self._x.sink.store_operand),
            self._data_sel.w_offset       .eq(self._w.sink.result[:2]),
            self._data_sel.w_funct3       .eq(self._w.sink.funct3),
            self._data_sel.w_load_data    .eq(self._w.sink.load_data)
        ]

        cpu.d.comb += [
            self._loadstore.x_addr      .eq(self._adder.x_result),
            self._loadstore.x_mask      .eq(self._data_sel.x_mask),
            self._loadstore.x_load      .eq(self._x.sink.load),
            self._loadstore.x_store     .eq(self._x.sink.store),
            self._loadstore.x_store_data.eq(self._data_sel.x_store_data),
            self._loadstore.x_stall     .eq(self._x.stall),
            self._loadstore.x_valid     .eq(self._x.valid),
            self._loadstore.m_stall     .eq(self._m.stall),
            self._loadstore.m_valid     .eq(self._m.valid)
        ]

        self._m.stall_on(self._loadstore.x_busy & self._x.valid)
        self._m.stall_on(self._loadstore.m_busy & self._m.valid)

        if self.with_dcache:
            if self.with_debug:
                cpu.d.comb += self._loadstore.m_flush.eq(self._debug.resumereq)

            cpu.d.comb += [
                self._loadstore.x_fence_i.eq(self._x.sink.fence_i),
                self._loadstore.m_load   .eq(self._m.sink.load),
                self._loadstore.m_store  .eq(self._m.sink.store),
            ]

        for s in self._a, self._f:
            s.kill_on(self._x.sink.fence_i & self._x.valid)

        if self.with_debug:
            debug_dbus_port     = self._dbus_arbiter.port(priority=0)
            loadstore_dbus_port = self._dbus_arbiter.port(priority=1)
            cpu.d.comb += [
                self._loadstore.dbus  .connect(loadstore_dbus_port),
                self._debug.dbus      .connect(debug_dbus_port),
                self._dbus_arbiter.bus.connect(self.dbus),
            ]
        else:
            cpu.d.comb += self._loadstore.dbus.connect(self.dbus)

        # RAW hazard management

        d_raw_rs1_x = Signal()
        d_raw_rs1_m = Signal()
        d_raw_rs1_w = Signal()
        d_raw_rs2_x = Signal()
        d_raw_rs2_m = Signal()
        d_raw_rs2_w = Signal()

        with cpu.If((self._x.sink.rd != 0) & self._x.sink.rd_we):
            cpu.d.comb += [
                d_raw_rs1_x.eq(self._x.sink.rd == self._decoder.rs1),
                d_raw_rs2_x.eq(self._x.sink.rd == self._decoder.rs2),
            ]

        with cpu.If((self._m.sink.rd != 0) & self._m.sink.rd_we):
            cpu.d.comb += [
                d_raw_rs1_m.eq(self._m.sink.rd == self._decoder.rs1),
                d_raw_rs2_m.eq(self._m.sink.rd == self._decoder.rs2),
            ]

        with cpu.If((self._w.sink.rd != 0) & self._w.sink.rd_we):
            cpu.d.comb += [
                d_raw_rs1_w.eq(self._w.sink.rd == self._decoder.rs1),
                d_raw_rs2_w.eq(self._w.sink.rd == self._decoder.rs2),
            ]

        d_raw_csr_x = Signal()
        d_raw_csr_m = Signal()

        with cpu.If(self._x.sink.csr_we):
            cpu.d.comb += d_raw_csr_x.eq(self._x.sink.csr_adr == self._decoder.immediate)

        with cpu.If(self._m.sink.csr_we):
            cpu.d.comb += d_raw_csr_m.eq(self._m.sink.csr_adr == self._decoder.immediate)

        d_lock_x = Signal()
        d_lock_m = Signal()
        d_lock   = Signal()

        with cpu.If(~self._x.sink.bypass_x):
            cpu.d.comb += d_lock_x.eq(self._decoder.rs1_re & d_raw_rs1_x
                                    | self._decoder.rs2_re & d_raw_rs2_x
                                    | self._decoder.csr    & d_raw_csr_x)

        with cpu.If(~self._m.sink.bypass_m):
            cpu.d.comb += d_lock_m.eq(self._decoder.rs1_re & d_raw_rs1_m
                                    | self._decoder.rs2_re & d_raw_rs2_m
                                    | self._decoder.csr    & d_raw_csr_m)

        cpu.d.comb += d_lock.eq(d_lock_x & self._x.valid | d_lock_m & self._m.valid)

        if self.with_debug:
            self._d.stall_on(d_lock & self._d.valid & ~self._debug.dcsr_step)
        else:
            self._d.stall_on(d_lock & self._d.valid)

        # Result selection

        x_result     = Signal(32)
        m_result     = Signal(32)
        w_result     = Signal(32)
        x_csr_result = Signal(32)

        with cpu.If(self._x.sink.jump):
            cpu.d.comb += x_result.eq(self._x.sink.pc + 4)
        with cpu.Elif(self._x.sink.logic):
            cpu.d.comb += x_result.eq(self._logic.result)
        with cpu.Elif(self._x.sink.csr):
            cpu.d.comb += x_result.eq(self._x.sink.src2)
        with cpu.Else():
            cpu.d.comb += x_result.eq(self._adder.x_result)

        with cpu.If(self._m.sink.compare):
            cpu.d.comb += m_result.eq(self._m.sink.condition_met)
        if self.with_muldiv:
            with cpu.Elif(self._m.sink.divide):
                cpu.d.comb += m_result.eq(self._divider.m_result)
        with cpu.Elif(self._m.sink.shift):
            cpu.d.comb += m_result.eq(self._shifter.m_result)
        with cpu.Else():
            cpu.d.comb += m_result.eq(self._m.sink.result)

        with cpu.If(self._w.sink.load):
            cpu.d.comb += w_result.eq(self._data_sel.w_load_result)
        if self.with_muldiv:
            with cpu.Elif(self._w.sink.multiply):
                cpu.d.comb += w_result.eq(self._multiplier.w_result)
        with cpu.Else():
            cpu.d.comb += w_result.eq(self._w.sink.result)

        with cpu.If(x_csr_set_clear):
            cpu.d.comb += x_csr_result.eq(self._logic.result)
        with cpu.Else():
            cpu.d.comb += x_csr_result.eq(x_csr_src1)

        # Register writeback

        with cpu.If(~self._exception.m_raise & ~self._m.stall):
            cpu.d.comb += csrf_wp.en.eq(self._m.sink.csr & self._m.sink.csr_we & self._m.valid)
        cpu.d.comb += [
            csrf_wp.addr.eq(self._m.sink.csr_adr),
            csrf_wp.data.eq(self._m.sink.csr_result)
        ]

        if self.with_debug:
            with cpu.If(self._debug.halt & self._debug.halted):
                cpu.d.comb += [
                    self._gprf.wp.addr.eq(self._debug.gprf_addr),
                    self._gprf.wp.en  .eq(self._debug.gprf_we),
                    self._gprf.wp.data.eq(self._debug.gprf_dat_w)
                ]
            with cpu.Else():
                with cpu.If((self._w.sink.rd != 0) & ~self._w.sink.exception):
                    cpu.d.comb += self._gprf.wp.en.eq(self._w.sink.rd_we & self._w.valid)
                cpu.d.comb += [
                    self._gprf.wp.addr.eq(self._w.sink.rd),
                    self._gprf.wp.data.eq(w_result)
                ]
        else:
            with cpu.If((self._w.sink.rd != 0) & ~self._w.sink.exception):
                cpu.d.comb += self._gprf.wp.en.eq(self._w.sink.rd_we & self._w.valid)
            cpu.d.comb += [
                self._gprf.wp.addr.eq(self._w.sink.rd),
                self._gprf.wp.data.eq(w_result)
            ]

        # D stage operand selection

        d_src1 = Signal(32)
        d_src2 = Signal(32)

        with cpu.If(self._decoder.lui):
            cpu.d.comb += d_src1.eq(0)
        with cpu.Elif(self._decoder.auipc):
            cpu.d.comb += d_src1.eq(self._d.sink.pc)
        with cpu.Elif(self._decoder.rs1_re & (self._decoder.rs1 == 0)):
            cpu.d.comb += d_src1.eq(0)
        with cpu.Elif(d_raw_rs1_x & self._x.sink.valid):
            cpu.d.comb += d_src1.eq(x_result)
        with cpu.Elif(d_raw_rs1_m & self._m.sink.valid):
            cpu.d.comb += d_src1.eq(m_result)
        with cpu.Elif(d_raw_rs1_w & self._w.sink.valid):
            cpu.d.comb += d_src1.eq(w_result)
        with cpu.Else():
            cpu.d.comb += d_src1.eq(self._gprf.rp1.data)

        with cpu.If(self._decoder.csr):
            cpu.d.comb += d_src2.eq(csrf_rp.data)
        with cpu.Elif(~self._decoder.rs2_re):
            cpu.d.comb += d_src2.eq(self._decoder.immediate)
        with cpu.Elif(self._decoder.rs2 == 0):
            cpu.d.comb += d_src2.eq(0)
        with cpu.Elif(d_raw_rs2_x & self._x.sink.valid):
            cpu.d.comb += d_src2.eq(x_result)
        with cpu.Elif(d_raw_rs2_m & self._m.sink.valid):
            cpu.d.comb += d_src2.eq(m_result)
        with cpu.Elif(d_raw_rs2_w & self._w.sink.valid):
            cpu.d.comb += d_src2.eq(w_result)
        with cpu.Else():
            cpu.d.comb += d_src2.eq(self._gprf.rp2.data)

        # Branch prediction

        cpu.d.comb += [
            self._predict.d_branch.eq(self._decoder.branch),
            self._predict.d_jump  .eq(self._decoder.jump),
            self._predict.d_offset.eq(self._decoder.immediate),
            self._predict.d_pc    .eq(self._d.sink.pc),
            self._predict.d_rs1_re.eq(self._decoder.rs1_re)
        ]

        self._a.kill_on(self._predict.d_branch_taken & self._d.valid)
        for s in self._a, self._f:
            s.kill_on(self._m.sink.branch_predict_taken & ~self._m.sink.branch_taken
                    & self._m.valid)
        for s in self._a, self._f, self._d:
            s.kill_on(~self._m.sink.branch_predict_taken & self._m.sink.branch_taken
                    & self._m.valid)
            s.kill_on((self._exception.m_raise | self._m.sink.mret) & self._m.valid)

        # Debug unit

        if self.with_debug:
            cpu.d.comb += [
                self._debug.jtag.connect(self.jtag),

                self._debug.x_pc           .eq(self._x.sink.pc),
                self._debug.x_ebreak       .eq(self._x.sink.ebreak),
                self._debug.x_stall        .eq(self._x.stall),
                self._debug.m_branch_taken .eq(self._m.sink.branch_taken),
                self._debug.m_branch_target.eq(self._m.sink.branch_target),
                self._debug.m_mret         .eq(self._m.sink.mret),
                self._debug.m_exception    .eq(self._exception.m_raise),
                self._debug.m_pc           .eq(self._m.sink.pc),
                self._debug.m_valid        .eq(self._m.valid),
                self._debug.mepc_r_base    .eq(self._exception.mepc.r.base),
                self._debug.mtvec_r_base   .eq(self._exception.mtvec.r.base)
            ]

            if self.with_trigger:
                cpu.d.comb += self._debug.trigger_haltreq.eq(self._trigger.haltreq)
            else:
                cpu.d.comb += self._debug.trigger_haltreq.eq(Const(0))

            csrf_debug_rp = self._csrf.read_port()
            csrf_debug_wp = self._csrf.write_port()
            cpu.d.comb += [
                csrf_debug_rp.addr.eq(self._debug.csrf_addr),
                csrf_debug_rp.en  .eq(self._debug.csrf_re),
                self._debug.csrf_dat_r.eq(csrf_debug_rp.data),

                csrf_debug_wp.addr.eq(self._debug.csrf_addr),
                csrf_debug_wp.en  .eq(self._debug.csrf_we),
                csrf_debug_wp.data.eq(self._debug.csrf_dat_w)
            ]

            self._x.stall_on(self._debug.halt)
            self._m.stall_on(self._debug.dcsr_step & self._m.valid & ~self._debug.halt)
            for s in self._a, self._f, self._d, self._x:
                s.kill_on(self._debug.killall)

            halted = self._x.stall & ~reduce(or_, (s.valid for s in (self._m, self._w)))
            cpu.d.sync += self._debug.halted.eq(halted)

            with cpu.If(self._debug.resumereq):
                with cpu.If(~self._debug.dbus_busy):
                    cpu.d.comb += self._debug.resumeack.eq(1)
                    cpu.d.sync += self._a.source.pc.eq(self._debug.dpc_value - 4)

        if self.with_trigger:
            cpu.d.comb += [
                self._trigger.x_pc   .eq(self._x.sink.pc),
                self._trigger.x_valid.eq(self._x.valid),
            ]

        # riscv-formal

        if self.with_rvfi:
            rvficon_d_rs1_addr  = Signal.like(self._rvficon.d_rs1_addr)
            rvficon_d_rs2_addr  = Signal.like(self._rvficon.d_rs2_addr)
            rvficon_d_rs1_rdata = Signal.like(self._rvficon.d_rs1_rdata)
            rvficon_d_rs2_rdata = Signal.like(self._rvficon.d_rs2_rdata)
            rvficon_x_mem_wmask = Signal.like(self._rvficon.x_mem_wmask)
            rvficon_x_mem_rmask = Signal.like(self._rvficon.x_mem_rmask)
            rvficon_w_rd_addr   = Signal.like(self._rvficon.w_rd_addr)
            rvficon_w_rd_wdata  = Signal.like(self._rvficon.w_rd_wdata)

            with cpu.If(self._decoder.rs1_re):
                cpu.d.comb += [
                    rvficon_d_rs1_addr .eq(self._decoder.rs1),
                    rvficon_d_rs1_rdata.eq(d_src1),
                ]
            with cpu.If(self._decoder.rs2_re):
                cpu.d.comb += [
                    rvficon_d_rs2_addr .eq(self._decoder.rs2),
                    rvficon_d_rs2_rdata.eq(d_src2),
                ]

            with cpu.If(self._loadstore.x_store):
                cpu.d.comb += rvficon_x_mem_wmask.eq(self._loadstore.x_mask)
            with cpu.If(self._loadstore.x_load):
                cpu.d.comb += rvficon_x_mem_rmask.eq(self._loadstore.x_mask)

            with cpu.If(self._gprf.wp.en):
                cpu.d.comb += [
                    rvficon_w_rd_addr .eq(self._gprf.wp.addr),
                    rvficon_w_rd_wdata.eq(self._gprf.wp.data),
                ]

            cpu.d.comb += [
                self._rvficon.d_insn            .eq(self._decoder.instruction),
                self._rvficon.d_rs1_addr        .eq(rvficon_d_rs1_addr),
                self._rvficon.d_rs2_addr        .eq(rvficon_d_rs2_addr),
                self._rvficon.d_rs1_rdata       .eq(rvficon_d_rs1_rdata),
                self._rvficon.d_rs2_rdata       .eq(rvficon_d_rs2_rdata),
                self._rvficon.d_stall           .eq(self._d.stall),
                self._rvficon.x_mem_addr        .eq(self._loadstore.x_addr[2:] << 2),
                self._rvficon.x_mem_wmask       .eq(rvficon_x_mem_wmask),
                self._rvficon.x_mem_rmask       .eq(rvficon_x_mem_rmask),
                self._rvficon.x_mem_wdata       .eq(self._loadstore.x_store_data),
                self._rvficon.x_stall           .eq(self._x.stall),
                self._rvficon.m_mem_rdata       .eq(self._loadstore.m_load_data),
                self._rvficon.m_fetch_misaligned.eq(self._exception.m_fetch_misaligned),
                self._rvficon.m_illegal_insn    .eq(self._m.sink.illegal),
                self._rvficon.m_load_misaligned .eq(self._exception.m_load_misaligned),
                self._rvficon.m_store_misaligned.eq(self._exception.m_store_misaligned),
                self._rvficon.m_exception       .eq(self._exception.m_raise),
                self._rvficon.m_mret            .eq(self._m.sink.mret),
                self._rvficon.m_branch_taken    .eq(self._m.sink.branch_taken),
                self._rvficon.m_branch_target   .eq(self._m.sink.branch_target),
                self._rvficon.m_pc_rdata        .eq(self._m.sink.pc),
                self._rvficon.m_stall           .eq(self._m.stall),
                self._rvficon.m_valid           .eq(self._m.valid),
                self._rvficon.w_rd_addr         .eq(rvficon_w_rd_addr),
                self._rvficon.w_rd_wdata        .eq(rvficon_w_rd_wdata),
                self._rvficon.mtvec_r_base      .eq(self._exception.mtvec.r.base),
                self._rvficon.mepc_r_value      .eq(self._exception.mepc.r),

                self._rvficon.rvfi.connect(self.rvfi),
            ]

        # Pipeline registers

        # A/F

        with cpu.If(~self._a.stall):
            cpu.d.sync += self._a.source.pc.eq(self._fetch.a_pc)

        # F/D

        with cpu.If(~self._f.stall):
            cpu.d.sync += [
                self._f.source.pc           .eq(self._f.sink.pc),
                self._f.source.instruction  .eq(self._fetch.f_instruction),
                self._f.source.fetch_error  .eq(self._fetch.f_fetch_error),
                self._f.source.fetch_badaddr.eq(self._fetch.f_badaddr)
            ]

        # D/X

        d_adder_sub = Signal()

        cpu.d.comb += d_adder_sub.eq(self._decoder.adder & self._decoder.adder_sub
                                   | self._decoder.compare
                                   | self._decoder.branch)

        with cpu.If(~self._d.stall):
            cpu.d.sync += [
                self._d.source.pc                  .eq(self._d.sink.pc),
                self._d.source.instruction         .eq(self._d.sink.instruction),
                self._d.source.fetch_error         .eq(self._d.sink.fetch_error),
                self._d.source.fetch_badaddr       .eq(self._d.sink.fetch_badaddr),
                self._d.source.illegal             .eq(self._decoder.illegal),
                self._d.source.rd                  .eq(self._decoder.rd),
                self._d.source.rs1                 .eq(self._decoder.rs1),
                self._d.source.rd_we               .eq(self._decoder.rd_we),
                self._d.source.rs1_re              .eq(self._decoder.rs1_re),
                self._d.source.bypass_x            .eq(self._decoder.bypass_x),
                self._d.source.bypass_m            .eq(self._decoder.bypass_m),
                self._d.source.funct3              .eq(self._decoder.funct3),
                self._d.source.load                .eq(self._decoder.load),
                self._d.source.store               .eq(self._decoder.store),
                self._d.source.adder_sub           .eq(d_adder_sub),
                self._d.source.compare             .eq(self._decoder.compare),
                self._d.source.logic               .eq(self._decoder.logic),
                self._d.source.shift               .eq(self._decoder.shift),
                self._d.source.direction           .eq(self._decoder.direction),
                self._d.source.sext                .eq(self._decoder.sext),
                self._d.source.jump                .eq(self._decoder.jump),
                self._d.source.branch              .eq(self._decoder.branch),
                self._d.source.fence_i             .eq(self._decoder.fence_i),
                self._d.source.csr                 .eq(self._decoder.csr),
                self._d.source.csr_adr             .eq(self._decoder.immediate),
                self._d.source.csr_we              .eq(self._decoder.csr_we),
                self._d.source.ecall               .eq(self._decoder.ecall),
                self._d.source.ebreak              .eq(self._decoder.ebreak),
                self._d.source.mret                .eq(self._decoder.mret),
                self._d.source.src1                .eq(d_src1),
                self._d.source.store_operand       .eq(d_src2),
                self._d.source.branch_predict_taken.eq(self._predict.d_branch_taken),
                self._d.source.branch_target       .eq(self._predict.d_branch_target)
            ]

            with cpu.If(self._decoder.store):
                cpu.d.sync += self._d.source.src2.eq(self._decoder.immediate)
            with cpu.Else():
                cpu.d.sync += self._d.source.src2.eq(d_src2)

            if self.with_muldiv:
                cpu.d.sync += [
                    self._d.source.multiply.eq(self._decoder.multiply),
                    self._d.source.divide  .eq(self._decoder.divide)
                ]

        # X/M

        x_bypass_m = Signal()

        cpu.d.comb += x_bypass_m.eq(self._x.sink.bypass_m | self._x.sink.bypass_x)

        x_branch_taken  = Signal()
        x_branch_target = Signal(32)

        cpu.d.comb += x_branch_taken.eq(self._x.sink.jump
                                      | self._x.sink.branch & self._compare.condition_met)

        with cpu.If(self._x.sink.jump & self._x.sink.rs1_re): # JALR
            cpu.d.comb += x_branch_target.eq(self._adder.x_result[1:] << 1)
        with cpu.Else():
            cpu.d.comb += x_branch_target.eq(self._x.sink.branch_target)

        with cpu.If(~self._x.stall):
            cpu.d.sync += [
                self._x.source.pc                  .eq(self._x.sink.pc),
                self._x.source.instruction         .eq(self._x.sink.instruction),
                self._x.source.fetch_error         .eq(self._x.sink.fetch_error),
                self._x.source.fetch_badaddr       .eq(self._x.sink.fetch_badaddr),
                self._x.source.illegal             .eq(self._x.sink.illegal),
                self._x.source.loadstore_misaligned.eq(self._data_sel.x_misaligned),
                self._x.source.ecall               .eq(self._x.sink.ecall),
                self._x.source.ebreak              .eq(self._x.sink.ebreak),
                self._x.source.rd                  .eq(self._x.sink.rd),
                self._x.source.rd_we               .eq(self._x.sink.rd_we),
                self._x.source.bypass_m            .eq(x_bypass_m),
                self._x.source.funct3              .eq(self._x.sink.funct3),
                self._x.source.load                .eq(self._x.sink.load),
                self._x.source.store               .eq(self._x.sink.store),
                self._x.source.store_data          .eq(self._loadstore.x_store_data),
                self._x.source.compare             .eq(self._x.sink.compare),
                self._x.source.shift               .eq(self._x.sink.shift),
                self._x.source.mret                .eq(self._x.sink.mret),
                self._x.source.condition_met       .eq(self._compare.condition_met),
                self._x.source.branch_taken        .eq(x_branch_taken),
                self._x.source.branch_target       .eq(x_branch_target),
                self._x.source.branch_predict_taken.eq(self._x.sink.branch_predict_taken),
                self._x.source.csr                 .eq(self._x.sink.csr),
                self._x.source.csr_adr             .eq(self._x.sink.csr_adr),
                self._x.source.csr_we              .eq(self._x.sink.csr_we),
                self._x.source.csr_result          .eq(x_csr_result),
                self._x.source.result              .eq(x_result)
            ]

            if self.with_muldiv:
                cpu.d.sync += [
                    self._x.source.multiply.eq(self._x.sink.multiply),
                    self._x.source.divide  .eq(self._x.sink.divide)
                ]

        # M/W

        with cpu.If(~self._m.stall):
            cpu.d.sync += [
                self._m.source.pc       .eq(self._m.sink.pc),
                self._m.source.rd       .eq(self._m.sink.rd),
                self._m.source.load     .eq(self._m.sink.load),
                self._m.source.funct3   .eq(self._m.sink.funct3),
                self._m.source.load_data.eq(self._loadstore.m_load_data),
                self._m.source.rd_we    .eq(self._m.sink.rd_we),
                self._m.source.result   .eq(m_result),
                self._m.source.exception.eq(self._exception.m_raise)
            ]
            if self.with_muldiv:
                cpu.d.sync += [
                    self._m.source.multiply.eq(self._m.sink.multiply)
                ]

        return cpu
