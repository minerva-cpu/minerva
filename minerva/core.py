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
from .units.loadstore import *
from .units.logic import *
from .units.multiplier import *
from .units.predict import *
from .units.shifter import *
from .units.trigger import *

from .units.debug.jtag import jtag_layout
from .wishbone import wishbone_layout


__all__ = ["Minerva"]


_af_layout = [
    ("pc",      (33, True)),
    ("misaligned_fetch", 1)
]


_fd_layout = [
    ("pc",               32),
    ("misaligned_fetch",  1),
    ("instruction",      32),
    ("ibus_error",        1)
]


_dx_layout = [
    ("pc",                  32),
    ("misaligned_fetch",     1),
    ("instruction",         32),
    ("ibus_error",           1),
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
    ("illegal",              1)
]


_xm_layout = [
    ("pc",                  32),
    ("rd",                   5),
    ("rd_we",                1),
    ("bypass_m",             1),
    ("result",              32),
    ("shift",                1),
    ("load",                 1),
    ("load_mask",            3),
    ("store",                1),
    ("dbus_sel",             4),
    ("store_data",          32),
    ("compare",              1),
    ("multiply",             1),
    ("divide",               1),
    ("condition_met",        1),
    ("branch_target",       32),
    ("branch_taken",         1),
    ("branch_predict_taken", 1),
    ("mret",                 1),
    ("exception",            1)
]


_mw_layout = [
    ("pc",                32),
    ("rd",                 5),
    ("rd_we",              1),
    ("result",            32),
    ("load",               1),
    ("load_mask",          3),
    ("load_data",         32),
    ("multiply",           1),
    ("exception",          1)
]


class Minerva(Elaboratable):
    def __init__(self, reset_address=0x00000000,
                as_instance=False,
                with_icache=True,
                icache_nb_ways=1, icache_nb_lines=256, icache_nb_words=8,
                icache_base=0, icache_limit=2**31,
                with_dcache=True,
                dcache_nb_ways=1, dcache_nb_lines=256, dcache_nb_words=8,
                dcache_base=0, dcache_limit=2**31,
                with_muldiv=True,
                with_debug=False,
                with_trigger=False, nb_triggers=8):

        self.external_interrupt = Signal(32)
        self.timer_interrupt = Signal()
        self.ibus = Record(wishbone_layout)
        self.dbus = Record(wishbone_layout)

        if as_instance:
            self.clk = Signal()
            self.rst = Signal()

        if with_debug:
            self.jtag = Record(jtag_layout)

        ###

        self.reset_address = reset_address
        self.as_instance   = as_instance
        self.with_icache   = with_icache
        self.with_dcache   = with_dcache
        self.with_muldiv   = with_muldiv
        self.with_debug    = with_debug
        self.with_trigger  = with_trigger

        icache_args = icache_nb_ways, icache_nb_lines, icache_nb_words, icache_base, icache_limit
        if with_icache:
            self.fetch = CachedFetchUnit(*icache_args)
        else:
            self.fetch = SimpleFetchUnit()

        dcache_args = dcache_nb_ways, dcache_nb_lines, dcache_nb_words, dcache_base, dcache_limit
        if with_dcache:
            self.loadstore = CachedLoadStoreUnit(*dcache_args)
        else:
            self.loadstore = SimpleLoadStoreUnit()

        if with_debug:
            self.debug = DebugUnit()

        if with_trigger:
            self.trigger = TriggerUnit(nb_triggers)

        self.adder      = Adder()
        self.compare    = CompareUnit()
        self.decoder    = InstructionDecoder(self.with_muldiv)
        if self.with_muldiv:
            self.multiplier = Multiplier()
            self.divider    = Divider()
        self.exception  = ExceptionUnit()
        self.logic      = LogicUnit()
        self.predict    = BranchPredictor()
        self.shifter    = Shifter()

    def elaborate(self, platform):
        cpu = Module()

        if self.as_instance:
            cd_sync = cpu.domains.cd_sync = ClockDomain()
            cpu.d.comb += [
                cd_sync.clk.eq(self.clk),
                cd_sync.rst.eq(self.rst)
            ]

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

        # register files

        gprf = Memory(width=32, depth=32)
        gprf_rp1 = gprf.read_port()
        gprf_rp2 = gprf.read_port()
        gprf_wp  = gprf.write_port()
        cpu.submodules += gprf_rp1, gprf_rp2, gprf_wp

        csrf = cpu.submodules.csrf = CSRFile(cpu)
        csrf_rp = csrf.read_port()
        csrf_wp = csrf.write_port()

        # units

        adder      = cpu.submodules.adder      = self.adder
        compare    = cpu.submodules.compare    = self.compare
        decoder    = cpu.submodules.decoder    = self.decoder
        if self.with_muldiv:
            multiplier = cpu.submodules.multiplier = self.multiplier
            divider    = cpu.submodules.divider    = self.divider
        exception  = cpu.submodules.exception  = self.exception
        fetch      = cpu.submodules.fetch      = self.fetch
        loadstore  = cpu.submodules.loadstore  = self.loadstore
        logic      = cpu.submodules.logic      = self.logic
        predict    = cpu.submodules.predict    = self.predict
        shifter    = cpu.submodules.shifter    = self.shifter

        cpu.d.comb += [
            fetch.ibus.connect(self.ibus),
            fetch.a_stall.eq(a.stall),
            fetch.f_pc.eq(f.sink.pc),
            fetch.f_stall.eq(f.stall),
            fetch.d_branch_predict_taken.eq(predict.d_branch_taken),
            fetch.d_branch_target.eq(predict.d_branch_target),
            fetch.d_valid.eq(d.valid),
            fetch.x_pc.eq(x.sink.pc),
            fetch.m_branch_predict_taken.eq(m.sink.branch_predict_taken),
            fetch.m_branch_taken.eq(m.sink.branch_taken | m.sink.exception | m.sink.mret),
            fetch.m_valid.eq(m.valid)
        ]

        with cpu.If(m.sink.exception):
            cpu.d.comb += fetch.m_branch_target.eq(exception.mtvec.r.base << 2)
        with cpu.Elif(m.sink.mret):
            cpu.d.comb += fetch.m_branch_target.eq(exception.mepc.r.value)
        with cpu.Else():
            cpu.d.comb += fetch.m_branch_target.eq(m.sink.branch_target)

        if self.with_icache:
            cpu.d.comb += [
                fetch.f_valid.eq(f.valid),
                fetch.icache.refill_ready.eq(~loadstore.dcache.stall_request if self.with_dcache else Const(1))
            ]

            fetch.icache.flush_on(x.sink.fence_i & x.valid)

            x.stall_on(fetch.icache.stall_request)
            m.stall_on(fetch.icache.stall_request & (fetch.m_branch_predict_taken != fetch.m_branch_taken) & m.valid)
            m.stall_on(self.ibus.cyc & fetch.m_branch_taken & m.valid)
        else:
            m.stall_on(self.ibus.cyc)

        cpu.d.comb += [
            decoder.instruction.eq(d.sink.instruction)
        ]

        if self.with_debug:
            with cpu.If(self.debug.halt & self.debug.halted):
                cpu.d.comb += gprf_rp1.addr.eq(self.debug.gprf_addr)
            with cpu.Else():
                cpu.d.comb += gprf_rp1.addr.eq(fetch.f_instruction[15:20])
            cpu.d.comb += self.debug.gprf_dat_r.eq(gprf_rp1.data)
        else:
            cpu.d.comb += gprf_rp1.addr.eq(fetch.f_instruction[15:20])
        cpu.d.comb += gprf_rp2.addr.eq(fetch.f_instruction[20:25])

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
            adder.src2.eq(Mux(x.sink.store, x.sink.immediate, x.sink.src2))
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
                divider.x_valid.eq(x.sink.valid & ~exception.x_raise),
                divider.x_stall.eq(x.stall)
            ]
            m.stall_on(divider.m_divide_ongoing)

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
            exception.x_pc.eq(x.sink.pc),
            exception.x_instruction.eq(x.sink.instruction),
            exception.x_address.eq(loadstore.x_address),
            exception.x_ecall.eq(x.sink.ecall),
            exception.x_misaligned_fetch.eq(x.sink.misaligned_fetch),
            exception.x_ibus_error.eq(x.sink.ibus_error),
            exception.x_illegal.eq(x.sink.illegal),
            exception.x_misaligned_load.eq(loadstore.x_load & loadstore.x_misaligned),
            exception.x_misaligned_store.eq(loadstore.x_store & loadstore.x_misaligned),
            exception.x_mret.eq(x.sink.mret),
            exception.x_stall.eq(x.sink.stall),
            exception.x_valid.eq(x.valid)
        ]

        x_ebreak = x.sink.ebreak
        if self.with_debug:
            # If dcsr.ebreakm is set, EBREAK instructions enter Debug Mode.
            # We do not want to raise an exception in this case because Debug Mode
            # should be invisible to software execution.
            x_ebreak &= ~self.debug.dcsr_ebreakm
        if self.with_trigger:
            x_ebreak |= self.trigger.trap
        cpu.d.comb += exception.x_ebreak.eq(x_ebreak)

        cpu.d.comb += [
            loadstore.x_address.eq(adder.result),
            loadstore.x_load.eq(x.sink.load),
            loadstore.x_store.eq(x.sink.store),
            loadstore.x_store_operand.eq(x.sink.src2),
            loadstore.x_mask.eq(x.sink.funct3),
            loadstore.x_stall.eq(x.stall),
            loadstore.x_valid.eq(x.valid & ~exception.x_raise),
            loadstore.w_address.eq(w.sink.result),
            loadstore.w_load_mask.eq(w.sink.load_mask),
            loadstore.w_load_data.eq(w.sink.load_data)
        ]

        if self.with_dcache:
            cpu.d.comb += [
                loadstore.m_address.eq(m.sink.result),
                loadstore.m_load.eq(m.sink.load),
                loadstore.m_store.eq(m.sink.store),
                loadstore.m_dbus_sel.eq(m.sink.dbus_sel),
                loadstore.m_store_data.eq(m.sink.store_data),
                loadstore.m_stall.eq(m.stall),
                loadstore.m_valid.eq(m.valid & ~m.sink.exception)
            ]

            x.stall_on((loadstore.x_load | loadstore.x_store) & ~loadstore.x_dcache_select & loadstore.x_valid \
                    & (self.dbus.cyc | loadstore.wrbuf.readable | loadstore.dcache.refill_request))
            m.stall_on(loadstore.m_load & ~loadstore.m_dcache_select & loadstore.m_valid & self.dbus.cyc)
            m.stall_on((loadstore.m_store | loadstore.m_load) & ~loadstore.m_dcache_select & loadstore.m_valid \
                    & loadstore.wrbuf.readable)
            m.stall_on(loadstore.m_store & loadstore.m_dcache_select & loadstore.m_valid & ~loadstore.wrbuf.writable)
            m.stall_on(loadstore.dcache.stall_request)
        else:
            m.stall_on(self.dbus.cyc)

        if self.with_debug:
            with cpu.If(self.debug.halt & self.debug.halted):
                cpu.d.comb += self.debug.dbus.connect(self.dbus)
            with cpu.Else():
                cpu.d.comb += loadstore.dbus.connect(self.dbus)
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
        x_lock = Signal()
        m_lock = Signal()

        cpu.d.comb += [
            x_raw_rs1.eq((x.sink.rd == decoder.rs1) & x.sink.rd_we),
            m_raw_rs1.eq((m.sink.rd == decoder.rs1) & m.sink.rd_we),
            w_raw_rs1.eq((w.sink.rd == decoder.rs1) & w.sink.rd_we),

            x_raw_rs2.eq((x.sink.rd == decoder.rs2) & x.sink.rd_we),
            m_raw_rs2.eq((m.sink.rd == decoder.rs2) & m.sink.rd_we),
            w_raw_rs2.eq((w.sink.rd == decoder.rs2) & w.sink.rd_we),

            x_raw_csr.eq((x.sink.csr_adr == decoder.immediate) & x.sink.csr_we),

            x_lock.eq(~x.sink.bypass_x & (decoder.rs1_re & x_raw_rs1 | decoder.rs2_re & x_raw_rs2)),
            m_lock.eq(~m.sink.bypass_m & (decoder.rs1_re & m_raw_rs1 | decoder.rs2_re & m_raw_rs2))
        ]

        if self.with_debug:
            d.stall_on((x_lock & x.valid | m_lock & m.valid) & d.valid & ~self.debug.dcsr_step)
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
            cpu.d.comb += w_result.eq(loadstore.w_load_result)
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
            csrf_wp.en.eq(x.sink.csr & x.sink.csr_we & x.valid & ~exception.x_raise & ~x.stall),
            csrf_wp.addr.eq(x.sink.csr_adr),
            csrf_wp.data.eq(x_csr_result)
        ]

        if self.with_debug:
            with cpu.If(self.debug.halt & self.debug.halted):
                cpu.d.comb += [
                    gprf_wp.addr.eq(self.debug.gprf_addr),
                    gprf_wp.en.eq(self.debug.gprf_we),
                    gprf_wp.data.eq(self.debug.gprf_dat_w)
                ]
            with cpu.Else():
                cpu.d.comb += [
                    gprf_wp.en.eq((w.sink.rd != 0) & w.sink.rd_we & w.valid),
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

        w_valid_r = Signal()
        with cpu.If(~m.stall):
            cpu.d.sync += w_valid_r.eq(m.valid)

        with cpu.If(decoder.lui):
            cpu.d.comb += d_src1.eq(0)
        with cpu.Elif(decoder.auipc):
            cpu.d.comb += d_src1.eq(d.sink.pc)
        with cpu.Elif(decoder.rs1_re & (decoder.rs1 == 0)):
            cpu.d.comb += d_src1.eq(0)
        with cpu.Elif(x_raw_rs1 & x.valid):
            cpu.d.comb += d_src1.eq(x_result)
        with cpu.Elif(m_raw_rs1 & m.valid):
            cpu.d.comb += d_src1.eq(m_result)
        with cpu.Elif(w_raw_rs1 & w_valid_r):
            cpu.d.comb += d_src1.eq(w_result)
        with cpu.Else():
            cpu.d.comb += d_src1.eq(gprf_rp1.data)

        with cpu.If(decoder.csr):
            with cpu.If(x_raw_csr & x.valid):
                cpu.d.comb += d_src2.eq(x_csr_result)
            with cpu.Else():
                cpu.d.comb += d_src2.eq(csrf_rp.data)
        with cpu.Elif(~decoder.rs2_re):
            cpu.d.comb += d_src2.eq(decoder.immediate)
        with cpu.Elif(decoder.rs2 == 0):
            cpu.d.comb += d_src2.eq(0)
        with cpu.Elif(x_raw_rs2 & x.valid):
            cpu.d.comb += d_src2.eq(x_result)
        with cpu.Elif(m_raw_rs2 & m.valid):
            cpu.d.comb += d_src2.eq(m_result)
        with cpu.Elif(w_raw_rs2 & w_valid_r):
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

        f.kill_on(x.sink.branch_predict_taken & x.valid & ~exception.x_raise)
        for s in a, f:
            s.kill_on(m.sink.branch_predict_taken & ~fetch.m_branch_taken & m.valid)
        for s in a, f, d:
            s.kill_on(~m.sink.branch_predict_taken & fetch.m_branch_taken & m.valid)

        # debug unit

        if self.with_debug:
            debug = cpu.submodules.debug = self.debug
            cpu.d.comb += [
                debug.jtag.connect(self.jtag),
                debug.x_pc.eq(x.sink.pc),
                debug.x_ebreak.eq(x.sink.ebreak),
                debug.x_stall.eq(x.stall),
                debug.m_branch_taken.eq(fetch.m_branch_taken),
                debug.m_branch_target.eq(fetch.m_branch_target),
                debug.m_pc.eq(m.sink.pc),
                debug.m_valid.eq(m.valid)
            ]

            if self.with_trigger:
                cpu.d.comb += debug.trigger_haltreq.eq(self.trigger.haltreq)
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
            if self.with_dcache:
                halted &= ~loadstore.wrbuf.readable
            cpu.d.sync += debug.halted.eq(halted)

            with cpu.If(debug.resumereq):
                with cpu.If(~debug.dbus_busy):
                    cpu.d.comb += debug.resumeack.eq(1)
                    cpu.d.sync += a.source.pc.eq(debug.dpc_value - 4)

            if self.with_icache:
                fetch.icache.flush_on(debug.resumereq)
            if self.with_dcache:
                loadstore.dcache.flush_on(debug.resumereq)

        if self.with_trigger:
            trigger = cpu.submodules.trigger = self.trigger
            cpu.d.comb += [
                trigger.x_pc.eq(x.sink.pc),
                trigger.x_valid.eq(x.valid),
            ]

        # pipeline registers

        # A/F
        with cpu.If(~a.stall):
            cpu.d.sync += [
                a.source.pc.eq(fetch.a_pc),
                a.source.misaligned_fetch.eq(fetch.a_misaligned)
            ]

        # F/D
        with cpu.If(~f.stall):
            cpu.d.sync += [
                f.source.pc.eq(f.sink.pc),
                f.source.misaligned_fetch.eq(f.sink.misaligned_fetch),
                f.source.instruction.eq(fetch.f_instruction),
                f.source.ibus_error.eq(fetch.f_ibus_error)
            ]

        # D/X
        with cpu.If(~d.stall):
            cpu.d.sync += [
                d.source.pc.eq(d.sink.pc),
                d.source.misaligned_fetch.eq(d.sink.misaligned_fetch),
                d.source.instruction.eq(d.sink.instruction),
                d.source.ibus_error.eq(d.sink.ibus_error),
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
                d.source.csr_adr.eq(decoder.immediate),
                d.source.csr_we.eq(decoder.csr_we),
                d.source.ecall.eq(decoder.ecall),
                d.source.ebreak.eq(decoder.ebreak),
                d.source.mret.eq(decoder.mret),
                d.source.illegal.eq(decoder.illegal),
                d.source.src1.eq(d_src1),
                d.source.src2.eq(d_src2),
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
                x.source.rd.eq(x.sink.rd),
                x.source.rd_we.eq(x.sink.rd_we & ~exception.x_raise),
                x.source.bypass_m.eq(x.sink.bypass_m | x.sink.bypass_x),
                x.source.load.eq(x.sink.load),
                x.source.load_mask.eq(x.sink.funct3),
                x.source.store.eq(x.sink.store),
                x.source.dbus_sel.eq(loadstore.x_dbus_sel),
                x.source.store_data.eq(loadstore.x_store_data),
                x.source.compare.eq(x.sink.compare),
                x.source.shift.eq(x.sink.shift),
                x.source.exception.eq(exception.x_raise),
                x.source.mret.eq(x.sink.mret),
                x.source.condition_met.eq(compare.condition_met),
                x.source.branch_taken.eq(x.sink.jump | x.sink.branch & compare.condition_met),
                x.source.branch_target.eq(Mux(x.sink.jump & x.sink.rs1_re, adder.result[1:] << 1, x.sink.branch_target)),
                x.source.branch_predict_taken.eq(x.sink.branch_predict_taken & ~exception.x_raise),
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
                m.source.load_mask.eq(m.sink.load_mask),
                m.source.load_data.eq(loadstore.m_load_data),
                m.source.rd_we.eq(m.sink.rd_we),
                m.source.result.eq(m_result),
                m.source.multiply.eq(m.sink.multiply),
                m.source.exception.eq(m.sink.exception)
            ]

        return cpu
