from itertools import tee

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.data import StructLayout
from amaranth.lib.wiring import In, Out, flipped, connect

from amaranth_soc import wishbone

from . import gpr, csr
from .isa import *
from .stage import *

from .units.adder import *
from .units.compare import *
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


__all__ = ["Minerva"]


_af_layout = StructLayout({
    "pc": signed(33),
})

_fd_layout = StructLayout({
    "pc":            32,
    "instruction":   32,
    "fetch_error":    1,
    "fetch_badaddr": 30
})


_dx_layout = StructLayout({
    "pc":                   32,
    "instruction":          32,
    "fetch_error":           1,
    "fetch_badaddr":        30,
    "illegal":               1,
    "rd":                    5,
    "rs1":                   5,
    "rd_we":                 1,
    "rs1_re":                1,
    "rs2_re":                1,
    "immediate":            32,
    "bypass_x":              1,
    "bypass_m":              1,
    "funct3":                3,
    "lui":                   1,
    "auipc":                 1,
    "load":                  1,
    "store":                 1,
    "adder_sub":             1,
    "logic":                 1,
    "multiply":              1,
    "divide":                1,
    "shift":                 1,
    "direction":             1,
    "sext":                  1,
    "jump":                  1,
    "compare":               1,
    "branch":                1,
    "branch_target":        32,
    "branch_predict_taken":  1,
    "fence_i":               1,
    "csr_re":                1,
    "csr_we":                1,
    "csr_fmt_i":             1,
    "csr_set":               1,
    "csr_clear":             1,
    "ecall":                 1,
    "ebreak":                1,
    "mret":                  1,
})


_xm_layout = StructLayout({
    "pc":                   32,
    "instruction":          32,
    "fetch_error":           1,
    "fetch_badaddr":        30,
    "illegal":               1,
    "loadstore_misaligned":  1,
    "ecall":                 1,
    "ebreak":                1,
    "rd":                    5,
    "rd_we":                 1,
    "bypass_m":              1,
    "funct3":                3,
    "result":               32,
    "shift":                 1,
    "load":                  1,
    "store":                 1,
    "store_data":           32,
    "compare":               1,
    "multiply":              1,
    "divide":                1,
    "condition_met":         1,
    "branch_target":        32,
    "branch_taken":          1,
    "branch_predict_taken":  1,
    "csr_we":                1,
    "csr_result":           32,
    "mret":                  1,
})


_mw_layout = StructLayout({
    "pc":         32,
    "rd":          5,
    "rd_we":       1,
    "funct3":      3,
    "result":     32,
    "load":        1,
    "load_data":  32,
    "csr_we":      1,
    "csr_rdy":     1,
    "csr_result": 32,
    "multiply":    1,
    "trap":        1
})


class Minerva(wiring.Component):
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
            with_rvfi     = False):

        self._reset_address = reset_address
        self._with_icache   = with_icache
        self._with_dcache   = with_dcache
        self._with_muldiv   = with_muldiv
        self._with_rvfi     = with_rvfi

        # Ports

        members = {
            "fast_interrupt":     In(16),
            "external_interrupt": In(1),
            "timer_interrupt":    In(1),
            "software_interrupt": In(1),

            "ibus": Out(wishbone.Signature(addr_width=30, data_width=32, granularity=8,
                                           features=("err", "cti", "bte"))),
            "dbus": Out(wishbone.Signature(addr_width=30, data_width=32, granularity=8,
                                           features=("err", "cti", "bte"))),
        }

        # Pipeline stages

        self._a = Stage(      None, _af_layout, source_init={"pc": reset_address - 4})
        self._f = Stage(_af_layout, _fd_layout,   sink_init={"pc": reset_address - 4})
        self._d = Stage(_fd_layout, _dx_layout)
        self._x = Stage(_dx_layout, _xm_layout)
        self._m = Stage(_xm_layout, _mw_layout)
        self._w = Stage(_mw_layout,       None)

        # Units

        self._pc_sel    = PCSelector()
        self._data_sel  = DataSelector()
        self._adder     = Adder()
        self._compare   = CompareUnit()
        self._decoder   = InstructionDecoder(with_muldiv)
        self._exception = ExceptionUnit(with_muldiv)
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

        # Storage

        self._gprf = gpr.RegisterFile()
        self._csrf = csr.RegisterFile()

        self._csrf.add(self._exception.csr_bank, addr=0x300)

        # Verification

        if with_rvfi:
            self._rvficon = RVFIController(self._csrf.memory_map)
            members.update({
                "rvfi": Out(RVFISignature(self._csrf.memory_map))
            })

        super().__init__(members)

    def elaborate(self, platform):
        m = Module()

        m.submodules.a = self._a
        m.submodules.f = self._f
        m.submodules.d = self._d
        m.submodules.x = self._x
        m.submodules.m = self._m
        m.submodules.w = self._w

        stages = self._a, self._f, self._d, self._x, self._m, self._w
        sources, sinks = tee(stages)
        next(sinks)
        for s1, s2 in zip(sources, sinks):
            connect(m, s1.source, s2.sink)

        m.submodules.pc_sel    = self._pc_sel
        m.submodules.data_sel  = self._data_sel
        m.submodules.adder     = self._adder
        m.submodules.compare   = self._compare
        m.submodules.decoder   = self._decoder
        m.submodules.exception = self._exception
        m.submodules.logic     = self._logic
        m.submodules.predict   = self._predict
        m.submodules.shifter   = self._shifter
        m.submodules.fetch     = self._fetch
        m.submodules.loadstore = self._loadstore

        if self._with_muldiv:
            m.submodules.multiplier = self._multiplier
            m.submodules.divider    = self._divider

        if self._with_rvfi:
            m.submodules.rvficon = self._rvficon

        m.submodules.gprf = self._gprf
        m.submodules.csrf = self._csrf

        # Pipeline logic

        m.d.comb += [
            self._pc_sel.f_pc                  .eq(self._f.sink.p.pc),
            self._pc_sel.d_pc                  .eq(self._d.sink.p.pc),
            self._pc_sel.d_branch_predict_taken.eq(self._predict.d_branch_taken),
            self._pc_sel.d_branch_target       .eq(self._predict.d_branch_target),
            self._pc_sel.d_valid               .eq(self._d.valid),
            self._pc_sel.x_pc                  .eq(self._x.sink.p.pc),
            self._pc_sel.x_fence_i             .eq(self._x.sink.p.fence_i),
            self._pc_sel.x_mtvec_base          .eq(self._exception.x_mtvec_base),
            self._pc_sel.x_mepc_base           .eq(self._exception.x_mepc_base),
            self._pc_sel.x_valid               .eq(self._x.valid),
            self._pc_sel.m_branch_predict_taken.eq(self._m.sink.p.branch_predict_taken),
            self._pc_sel.m_branch_taken        .eq(self._m.sink.p.branch_taken),
            self._pc_sel.m_branch_target       .eq(self._m.sink.p.branch_target),
            self._pc_sel.m_exception           .eq(self._exception.m_trap),
            self._pc_sel.m_mret                .eq(self._m.sink.p.mret),
            self._pc_sel.m_valid               .eq(self._m.valid),
        ]

        m.d.comb += [
            self._fetch.a_pc   .eq(self._pc_sel.a_pc),
            self._fetch.a_ready.eq(self._a.ready),
            self._fetch.a_valid.eq(self._a.valid),
            self._fetch.f_ready.eq(self._f.ready),
            self._fetch.f_valid.eq(self._f.valid),
        ]

        connect(m, self._fetch.ibus, flipped(self.ibus))

        self._m.stall_on(self._fetch.a_busy)
        self._m.stall_on(self._fetch.f_busy)

        if self._with_icache:
            flush_icache = self._x.sink.p.fence_i & self._x.valid

            m.d.comb += [
                self._fetch.f_pc   .eq(self._f.sink.p.pc),
                self._fetch.a_flush.eq(flush_icache)
            ]

        m.d.comb += [
            self._decoder.instruction.eq(self._d.sink.p.instruction)
        ]

        m.d.comb += [
            self._gprf.d_rp1_addr.eq(self._decoder.rs1),
            self._gprf.d_rp2_addr.eq(self._decoder.rs2),
            self._gprf.d_ready   .eq(self._d.ready),
        ]

        self._d.stall_on(((self._decoder.rs1_re & ~self._gprf.d_rp1_rdy) |
                          (self._decoder.rs2_re & ~self._gprf.d_rp2_rdy)) & self._d.valid)

        x_src1 = Signal(32)
        x_src2 = Signal(32)

        with m.If(self._x.sink.p.lui):
            m.d.comb += x_src1.eq(0)
        with m.Elif(self._x.sink.p.auipc):
            m.d.comb += x_src1.eq(self._x.sink.p.pc)
        with m.Elif(self._x.sink.p.csr_re & self._x.sink.p.csr_fmt_i):
            m.d.comb += x_src1.eq(self._x.sink.p.rs1)
        with m.Else():
            m.d.comb += x_src1.eq(self._gprf.x_rp1_data)

        with m.If(self._x.sink.p.store | ~self._x.sink.p.rs2_re):
            m.d.comb += x_src2.eq(self._x.sink.p.immediate)
        with m.Else():
            m.d.comb += x_src2.eq(self._gprf.x_rp2_data)

        m.d.comb += [
            self._csrf.d_addr   .eq(self._decoder.immediate[:12]),
            self._csrf.d_ready  .eq(self._d.ready),
            self._csrf.x_ready  .eq(self._x.ready),
            self._csrf.m_wp_data.eq(self._m.sink.p.csr_result),
            self._csrf.m_ready  .eq(self._m.ready),
            self._csrf.w_wp_data.eq(self._w.sink.p.csr_result),
            self._csrf.w_wp_en  .eq(self._w.sink.p.csr_we & self._w.sink.p.csr_rdy &
                                    self._w.valid & ~self._w.sink.p.trap),
        ]

        self._d.stall_on(self._decoder.csr & self._d.valid & (self._x.valid |
                                                              self._m.valid |
                                                              self._w.valid))

        self._d.stall_on(self._x.sink.p.csr_we & self._x.valid |
                         self._m.sink.p.csr_we & self._m.valid & ~self._exception.m_trap |
                         self._w.sink.p.csr_we & self._w.valid & ~self._w.sink.p.trap)

        x_csr_sc_logic_op   = Signal(3)
        x_csr_sc_logic_src1 = Signal(32)

        m.d.comb += x_csr_sc_logic_op.eq(self._x.sink.p.funct3 | 0b100)

        with m.If(self._x.sink.p.csr_clear):
            m.d.comb += x_csr_sc_logic_src1.eq(~x_src1)
        with m.Else():
            m.d.comb += x_csr_sc_logic_src1.eq(x_src1)

        with m.If(self._x.sink.p.csr_re):
            m.d.comb += [
                self._logic.op  .eq(x_csr_sc_logic_op),
                self._logic.src1.eq(x_csr_sc_logic_src1),
                self._logic.src2.eq(self._csrf.x_rp_data),
            ]
        with m.Else():
            m.d.comb += [
                self._logic.op  .eq(self._x.sink.p.funct3),
                self._logic.src1.eq(x_src1),
                self._logic.src2.eq(x_src2),
            ]

        m.d.comb += [
            self._adder.d_sub  .eq(self._decoder.adder & self._decoder.adder_sub
                                 | self._decoder.compare | self._decoder.branch),
            self._adder.d_ready.eq(self._d.ready),
            self._adder.x_src1 .eq(x_src1),
            self._adder.x_src2 .eq(x_src2),
        ]

        if self._with_muldiv:
            m.d.comb += [
                self._multiplier.d_op   .eq(self._decoder.funct3),
                self._multiplier.d_ready.eq(self._d.ready),
                self._multiplier.x_src1 .eq(x_src1),
                self._multiplier.x_src2 .eq(x_src2),
                self._multiplier.x_ready.eq(self._x.ready),
                self._multiplier.m_ready.eq(self._m.ready),
            ]

            m.d.comb += [
                self._divider.x_op   .eq(self._x.sink.p.funct3),
                self._divider.x_src1 .eq(x_src1),
                self._divider.x_src2 .eq(x_src2),
                self._divider.x_valid.eq(self._x.valid),
                self._divider.x_ready.eq(self._x.ready),
            ]

            self._m.stall_on(self._divider.m_busy)

        m.d.comb += [
            self._shifter.x_direction.eq(self._x.sink.p.direction),
            self._shifter.x_sext     .eq(self._x.sink.p.sext),
            self._shifter.x_shamt    .eq(x_src2),
            self._shifter.x_src1     .eq(x_src1),
            self._shifter.x_ready    .eq(self._x.ready),
        ]

        # compare.op is shared by compare and branch instructions.
        with m.If(self._x.sink.p.compare):
            m.d.comb += self._compare.op.eq(self._x.sink.p.funct3[:2] << 1)
        with m.Else():
            m.d.comb += self._compare.op.eq(self._x.sink.p.funct3)

        m.d.comb += [
            self._compare.zero    .eq(x_src1 == x_src2),
            self._compare.negative.eq(self._adder.x_result[-1]),
            self._compare.overflow.eq(self._adder.x_overflow),
            self._compare.carry   .eq(self._adder.x_carry)
        ]

        m.d.comb += [
            self._exception.x_ready             .eq(self._x.ready),

            self._exception.m_fetch_misaligned  .eq(self._m.sink.p.branch_taken
                                                  & self._m.sink.p.branch_target[:2].bool()),
            self._exception.m_fetch_error       .eq(self._m.sink.p.fetch_error),
            self._exception.m_fetch_badaddr     .eq(self._m.sink.p.fetch_badaddr),
            self._exception.m_load_misaligned   .eq(self._m.sink.p.load
                                                  & self._m.sink.p.loadstore_misaligned),
            self._exception.m_load_error        .eq(self._loadstore.m_load_error),
            self._exception.m_store_misaligned  .eq(self._m.sink.p.store
                                                  & self._m.sink.p.loadstore_misaligned),
            self._exception.m_store_error       .eq(self._loadstore.m_store_error),
            self._exception.m_loadstore_badaddr .eq(self._loadstore.m_badaddr),
            self._exception.m_branch_target     .eq(self._m.sink.p.branch_target),
            self._exception.m_illegal           .eq(self._m.sink.p.illegal),
            self._exception.m_ebreak            .eq(self._m.sink.p.ebreak),
            self._exception.m_ecall             .eq(self._m.sink.p.ecall),
            self._exception.m_pc                .eq(self._m.sink.p.pc),
            self._exception.m_instruction       .eq(self._m.sink.p.instruction),
            self._exception.m_result            .eq(self._m.sink.p.result),
            self._exception.m_mret              .eq(self._m.sink.p.mret),
            self._exception.m_ready             .eq(self._m.ready),

            self._exception.w_software_interrupt.eq(self.software_interrupt),
            self._exception.w_timer_interrupt   .eq(self.timer_interrupt),
            self._exception.w_external_interrupt.eq(self.external_interrupt),
            self._exception.w_fast_interrupt    .eq(self.fast_interrupt),
            self._exception.w_pc                .eq(self._w.sink.p.pc),
            self._exception.w_valid             .eq(self._w.valid),
        ]

        m.d.comb += [
            self._data_sel.x_offset       .eq(self._adder.x_result[:2]),
            self._data_sel.x_funct3       .eq(self._x.sink.p.funct3),
            self._data_sel.x_store_operand.eq(self._gprf.x_rp2_data),
            self._data_sel.w_offset       .eq(self._w.sink.p.result[:2]),
            self._data_sel.w_funct3       .eq(self._w.sink.p.funct3),
            self._data_sel.w_load_data    .eq(self._w.sink.p.load_data)
        ]

        m.d.comb += [
            self._loadstore.x_addr      .eq(self._adder.x_result),
            self._loadstore.x_mask      .eq(self._data_sel.x_mask),
            self._loadstore.x_load      .eq(self._x.sink.p.load),
            self._loadstore.x_store     .eq(self._x.sink.p.store),
            self._loadstore.x_store_data.eq(self._data_sel.x_store_data),
            self._loadstore.x_ready     .eq(self._x.ready),
            self._loadstore.x_valid     .eq(self._x.valid),
            self._loadstore.m_ready     .eq(self._m.ready),
            self._loadstore.m_valid     .eq(self._m.valid)
        ]

        self._m.stall_on(self._loadstore.x_busy)
        self._m.stall_on(self._loadstore.m_busy)

        if self._with_dcache:
            m.d.comb += [
                self._loadstore.x_fence_i.eq(self._x.sink.p.fence_i),
                self._loadstore.m_load   .eq(self._m.sink.p.load),
                self._loadstore.m_store  .eq(self._m.sink.p.store),
            ]

        for s in self._f, self._d:
            s.kill_on(self._x.sink.p.fence_i & self._x.valid)

        connect(m, self._loadstore.dbus, flipped(self.dbus))

        # Result selection

        x_result     = Signal(32)
        m_result     = Signal(32)
        w_result     = Signal(32)
        x_csr_result = Signal(32)

        with m.If(self._x.sink.p.jump):
            m.d.comb += x_result.eq(self._x.sink.p.pc + 4)
        with m.Elif(self._x.sink.p.logic):
            m.d.comb += x_result.eq(self._logic.result)
        with m.Elif(self._x.sink.p.csr_re):
            m.d.comb += x_result.eq(self._csrf.x_rp_data)
        with m.Else():
            m.d.comb += x_result.eq(self._adder.x_result)

        with m.If(self._m.sink.p.compare):
            m.d.comb += m_result.eq(self._m.sink.p.condition_met)
        if self._with_muldiv:
            with m.Elif(self._m.sink.p.divide):
                m.d.comb += m_result.eq(self._divider.m_result)
        with m.Elif(self._m.sink.p.shift):
            m.d.comb += m_result.eq(self._shifter.m_result)
        with m.Else():
            m.d.comb += m_result.eq(self._m.sink.p.result)

        with m.If(self._w.sink.p.load):
            m.d.comb += w_result.eq(self._data_sel.w_load_result)
        if self._with_muldiv:
            with m.Elif(self._w.sink.p.multiply):
                m.d.comb += w_result.eq(self._multiplier.w_result)
        with m.Else():
            m.d.comb += w_result.eq(self._w.sink.p.result)

        with m.If(self._x.sink.p.csr_set | self._x.sink.p.csr_clear):
            m.d.comb += x_csr_result.eq(self._logic.result)
        with m.Else():
            m.d.comb += x_csr_result.eq(x_src1)

        # Register writeback

        m.d.comb += [
            self._gprf.x_wp_addr.eq(self._x.sink.p.rd),
            self._gprf.x_wp_en  .eq(self._x.sink.p.rd_we & self._x.valid),
            self._gprf.x_wp_rdy .eq(self._x.sink.p.bypass_x),
            self._gprf.x_wp_data.eq(x_result),

            self._gprf.m_wp_addr.eq(self._m.sink.p.rd),
            self._gprf.m_wp_en  .eq(self._m.sink.p.rd_we & self._m.valid),
            self._gprf.m_wp_rdy .eq(self._m.sink.p.bypass_m),
            self._gprf.m_wp_data.eq(m_result),

            self._gprf.w_wp_addr.eq(self._w.sink.p.rd),
            self._gprf.w_wp_en  .eq(self._w.sink.p.rd_we & self._w.valid & ~self._w.sink.p.trap),
            self._gprf.w_wp_data.eq(w_result),
        ]

        # Branch prediction

        m.d.comb += [
            self._predict.d_branch.eq(self._decoder.branch),
            self._predict.d_jump  .eq(self._decoder.jump),
            self._predict.d_offset.eq(self._decoder.immediate),
            self._predict.d_pc    .eq(self._d.sink.p.pc),
            self._predict.d_rs1_re.eq(self._decoder.rs1_re)
        ]

        self._f.kill_on(self._predict.d_branch_taken & self._d.valid)
        for s in self._f, self._d:
            s.kill_on(self._m.sink.p.branch_predict_taken & ~self._m.sink.p.branch_taken &
                      self._m.valid)
        for s in self._f, self._d, self._x:
            s.kill_on(~self._m.sink.p.branch_predict_taken & self._m.sink.p.branch_taken &
                      self._m.valid)
            s.kill_on((self._exception.m_trap | self._m.sink.p.mret) & self._m.valid)


        # riscv-formal

        if self._with_rvfi:
            rvficon_d_rs1_addr  = Signal.like(self._rvficon.d_rs1_addr)
            rvficon_d_rs2_addr  = Signal.like(self._rvficon.d_rs2_addr)
            rvficon_x_rs1_rdata = Signal.like(self._rvficon.x_rs1_rdata)
            rvficon_x_rs2_rdata = Signal.like(self._rvficon.x_rs2_rdata)
            rvficon_x_mem_wmask = Signal.like(self._rvficon.x_mem_wmask)
            rvficon_x_mem_rmask = Signal.like(self._rvficon.x_mem_rmask)
            rvficon_w_rd_addr   = Signal.like(self._rvficon.w_rd_addr)
            rvficon_w_rd_wdata  = Signal.like(self._rvficon.w_rd_wdata)

            with m.If(self._decoder.rs1_re):
                m.d.comb += rvficon_d_rs1_addr.eq(self._decoder.rs1),
            with m.If(self._decoder.rs2_re):
                m.d.comb += rvficon_d_rs2_addr.eq(self._decoder.rs2)

            with m.If(self._x.sink.p.rs1_re):
                m.d.comb += rvficon_x_rs1_rdata.eq(self._gprf.x_rp1_data)
            with m.If(self._x.sink.p.rs2_re):
                m.d.comb += rvficon_x_rs2_rdata.eq(self._gprf.x_rp2_data)

            with m.If(self._loadstore.x_store):
                m.d.comb += rvficon_x_mem_wmask.eq(self._loadstore.x_mask)
            with m.If(self._loadstore.x_load):
                m.d.comb += rvficon_x_mem_rmask.eq(self._loadstore.x_mask)

            with m.If(self._gprf.w_wp_en & (self._gprf.w_wp_addr != 0)):
                m.d.comb += [
                    rvficon_w_rd_addr .eq(self._gprf.w_wp_addr),
                    rvficon_w_rd_wdata.eq(self._gprf.w_wp_data),
                ]

            m.d.comb += [
                self._rvficon.d_insn            .eq(self._decoder.instruction),
                self._rvficon.d_rs1_addr        .eq(rvficon_d_rs1_addr),
                self._rvficon.d_rs2_addr        .eq(rvficon_d_rs2_addr),
                self._rvficon.d_ready           .eq(self._d.ready),
                self._rvficon.x_rs1_rdata       .eq(rvficon_x_rs1_rdata),
                self._rvficon.x_rs2_rdata       .eq(rvficon_x_rs2_rdata),
                self._rvficon.x_mem_addr        .eq(self._loadstore.x_addr[2:] << 2),
                self._rvficon.x_mem_wmask       .eq(rvficon_x_mem_wmask),
                self._rvficon.x_mem_rmask       .eq(rvficon_x_mem_rmask),
                self._rvficon.x_mem_wdata       .eq(self._loadstore.x_store_data),
                self._rvficon.x_mtvec_base      .eq(self._exception.x_mtvec_base),
                self._rvficon.x_mepc_base       .eq(self._exception.x_mepc_base),
                self._rvficon.x_ready           .eq(self._x.ready),
                self._rvficon.m_mem_rdata       .eq(self._loadstore.m_load_data),
                self._rvficon.m_fetch_misaligned.eq(self._exception.m_fetch_misaligned),
                self._rvficon.m_illegal_insn    .eq(self._m.sink.p.illegal),
                self._rvficon.m_load_misaligned .eq(self._exception.m_load_misaligned),
                self._rvficon.m_store_misaligned.eq(self._exception.m_store_misaligned),
                self._rvficon.m_exception       .eq(self._exception.m_trap),
                self._rvficon.m_mret            .eq(self._m.sink.p.mret),
                self._rvficon.m_branch_taken    .eq(self._m.sink.p.branch_taken),
                self._rvficon.m_branch_target   .eq(self._m.sink.p.branch_target),
                self._rvficon.m_pc_rdata        .eq(self._m.sink.p.pc),
                self._rvficon.m_ready           .eq(self._m.ready),
                self._rvficon.m_valid           .eq(self._m.valid),
                self._rvficon.w_rd_addr         .eq(rvficon_w_rd_addr),
                self._rvficon.w_rd_wdata        .eq(rvficon_w_rd_wdata),
            ]

            connect(m, self._rvficon.rvfi, flipped(self.rvfi))

        # Pipeline registers

        # A/F

        with m.If(self._a.ready):
            m.d.sync += self._a.source.p.pc.eq(self._fetch.a_pc)

        # F/D

        with m.If(self._f.ready):
            m.d.sync += [
                self._f.source.p.pc           .eq(self._f.sink.p.pc),
                self._f.source.p.instruction  .eq(self._fetch.f_instruction),
                self._f.source.p.fetch_error  .eq(self._fetch.f_fetch_error),
                self._f.source.p.fetch_badaddr.eq(self._fetch.f_badaddr)
            ]

        # D/X

        d_adder_sub = Signal()

        m.d.comb += d_adder_sub.eq( self._decoder.adder & self._decoder.adder_sub
                                    | self._decoder.compare
                                    | self._decoder.branch)

        with m.If(self._d.ready):
            m.d.sync += [
                self._d.source.p.pc                  .eq(self._d.sink.p.pc),
                self._d.source.p.instruction         .eq(self._d.sink.p.instruction),
                self._d.source.p.fetch_error         .eq(self._d.sink.p.fetch_error),
                self._d.source.p.fetch_badaddr       .eq(self._d.sink.p.fetch_badaddr),
                self._d.source.p.illegal             .eq(self._decoder.illegal),
                self._d.source.p.rd                  .eq(self._decoder.rd),
                self._d.source.p.rs1                 .eq(self._decoder.rs1),
                self._d.source.p.rd_we               .eq(self._decoder.rd_we),
                self._d.source.p.rs1_re              .eq(self._decoder.rs1_re),
                self._d.source.p.rs2_re              .eq(self._decoder.rs2_re),
                self._d.source.p.bypass_x            .eq(self._decoder.bypass_x),
                self._d.source.p.bypass_m            .eq(self._decoder.bypass_m),
                self._d.source.p.funct3              .eq(self._decoder.funct3),
                self._d.source.p.lui                 .eq(self._decoder.lui),
                self._d.source.p.auipc               .eq(self._decoder.auipc),
                self._d.source.p.load                .eq(self._decoder.load),
                self._d.source.p.store               .eq(self._decoder.store),
                self._d.source.p.adder_sub           .eq(d_adder_sub),
                self._d.source.p.compare             .eq(self._decoder.compare),
                self._d.source.p.logic               .eq(self._decoder.logic),
                self._d.source.p.shift               .eq(self._decoder.shift),
                self._d.source.p.direction           .eq(self._decoder.direction),
                self._d.source.p.sext                .eq(self._decoder.sext),
                self._d.source.p.jump                .eq(self._decoder.jump),
                self._d.source.p.branch              .eq(self._decoder.branch),
                self._d.source.p.fence_i             .eq(self._decoder.fence_i),
                self._d.source.p.csr_re              .eq(self._decoder.csr),
                self._d.source.p.csr_we              .eq(self._decoder.csr & self._decoder.csr_we),
                self._d.source.p.csr_fmt_i           .eq(self._decoder.csr_fmt_i),
                self._d.source.p.csr_set             .eq(self._decoder.csr_set),
                self._d.source.p.csr_clear           .eq(self._decoder.csr_clear),
                self._d.source.p.ecall               .eq(self._decoder.ecall),
                self._d.source.p.ebreak              .eq(self._decoder.ebreak),
                self._d.source.p.mret                .eq(self._decoder.mret),
                self._d.source.p.immediate           .eq(self._decoder.immediate),
                self._d.source.p.branch_predict_taken.eq(self._predict.d_branch_taken),
                self._d.source.p.branch_target       .eq(self._predict.d_branch_target)
            ]

            if self._with_muldiv:
                m.d.sync += [
                    self._d.source.p.multiply.eq(self._decoder.multiply),
                    self._d.source.p.divide  .eq(self._decoder.divide)
                ]

        # X/M

        x_bypass_m      = Signal()
        x_branch_taken  = Signal()
        x_branch_target = Signal(32)

        m.d.comb += [
            x_bypass_m.eq(self._x.sink.p.bypass_m | self._x.sink.p.bypass_x),

            x_branch_taken.eq(self._x.sink.p.jump |
                              self._x.sink.p.branch & self._compare.condition_met),
        ]

        with m.If(self._x.sink.p.jump & self._x.sink.p.rs1_re): # JALR
            m.d.comb += x_branch_target.eq(self._adder.x_result[1:] << 1)
        with m.Else():
            m.d.comb += x_branch_target.eq(self._x.sink.p.branch_target)

        with m.If(self._x.ready):
            m.d.sync += [
                self._x.source.p.pc                  .eq(self._x.sink.p.pc),
                self._x.source.p.instruction         .eq(self._x.sink.p.instruction),
                self._x.source.p.fetch_error         .eq(self._x.sink.p.fetch_error),
                self._x.source.p.fetch_badaddr       .eq(self._x.sink.p.fetch_badaddr),
                self._x.source.p.illegal             .eq(self._x.sink.p.illegal),
                self._x.source.p.loadstore_misaligned.eq(self._data_sel.x_misaligned),
                self._x.source.p.ecall               .eq(self._x.sink.p.ecall),
                self._x.source.p.ebreak              .eq(self._x.sink.p.ebreak),
                self._x.source.p.rd                  .eq(self._x.sink.p.rd),
                self._x.source.p.rd_we               .eq(self._x.sink.p.rd_we),
                self._x.source.p.bypass_m            .eq(x_bypass_m),
                self._x.source.p.funct3              .eq(self._x.sink.p.funct3),
                self._x.source.p.load                .eq(self._x.sink.p.load),
                self._x.source.p.store               .eq(self._x.sink.p.store),
                self._x.source.p.store_data          .eq(self._loadstore.x_store_data),
                self._x.source.p.compare             .eq(self._x.sink.p.compare),
                self._x.source.p.shift               .eq(self._x.sink.p.shift),
                self._x.source.p.mret                .eq(self._x.sink.p.mret),
                self._x.source.p.condition_met       .eq(self._compare.condition_met),
                self._x.source.p.branch_taken        .eq(x_branch_taken),
                self._x.source.p.branch_target       .eq(x_branch_target),
                self._x.source.p.branch_predict_taken.eq(self._x.sink.p.branch_predict_taken),
                self._x.source.p.csr_we              .eq(self._x.sink.p.csr_we),
                self._x.source.p.csr_result          .eq(x_csr_result),
                self._x.source.p.result              .eq(x_result)
            ]

            if self._with_muldiv:
                m.d.sync += [
                    self._x.source.p.multiply.eq(self._x.sink.p.multiply),
                    self._x.source.p.divide  .eq(self._x.sink.p.divide)
                ]

        # M/W

        with m.If(self._m.ready):
            m.d.sync += [
                self._m.source.p.pc        .eq(self._m.sink.p.pc),
                self._m.source.p.rd        .eq(self._m.sink.p.rd),
                self._m.source.p.load      .eq(self._m.sink.p.load),
                self._m.source.p.funct3    .eq(self._m.sink.p.funct3),
                self._m.source.p.load_data .eq(self._loadstore.m_load_data),
                self._m.source.p.rd_we     .eq(self._m.sink.p.rd_we),
                self._m.source.p.result    .eq(m_result),
                self._m.source.p.csr_we    .eq(self._m.sink.p.csr_we),
                self._m.source.p.csr_rdy   .eq(self._csrf.m_wp_rdy),
                self._m.source.p.csr_result.eq(self._m.sink.p.csr_result),
                self._m.source.p.trap      .eq(self._exception.m_trap)
            ]

            if self._with_muldiv:
                m.d.sync += [
                    self._m.source.p.multiply.eq(self._m.sink.p.multiply)
                ]

        return m
