from functools import reduce
from operator import or_

from nmigen import *
from nmigen.hdl.rec import *

from ..isa import *
from ..wishbone import *


__all__ = ["rvfi_layout", "RVFIController"]

# RISC-V Formal Interface
# https://github.com/SymbioticEDA/riscv-formal/blob/master/docs/rvfi.md

rvfi_layout = [
    ("valid",      1, DIR_FANOUT),
    ("order",     64, DIR_FANOUT),
    ("insn",      32, DIR_FANOUT),
    ("trap",       1, DIR_FANOUT),
    ("halt",       1, DIR_FANOUT),
    ("intr",       1, DIR_FANOUT),
    ("mode",       2, DIR_FANOUT),
    ("ixl",        2, DIR_FANOUT),

    ("rs1_addr",   5, DIR_FANOUT),
    ("rs2_addr",   5, DIR_FANOUT),
    ("rs1_rdata", 32, DIR_FANOUT),
    ("rs2_rdata", 32, DIR_FANOUT),
    ("rd_addr",    5, DIR_FANOUT),
    ("rd_wdata",  32, DIR_FANOUT),

    ("pc_rdata",  32, DIR_FANOUT),
    ("pc_wdata",  32, DIR_FANOUT),

    ("mem_addr",  32, DIR_FANOUT),
    ("mem_rmask",  4, DIR_FANOUT),
    ("mem_wmask",  4, DIR_FANOUT),
    ("mem_rdata", 32, DIR_FANOUT),
    ("mem_wdata", 32, DIR_FANOUT)
]


class RVFIController(Elaboratable):
    def __init__(self):
        self.rvfi               = Record(rvfi_layout)

        self.d_insn             = Signal.like(self.rvfi.insn)
        self.d_rs1_addr         = Signal.like(self.rvfi.rs1_addr)
        self.d_rs2_addr         = Signal.like(self.rvfi.rs2_addr)
        self.d_rs1_rdata        = Signal.like(self.rvfi.rs1_rdata)
        self.d_rs2_rdata        = Signal.like(self.rvfi.rs2_rdata)
        self.d_stall            = Signal()
        self.x_mem_addr         = Signal.like(self.rvfi.mem_addr)
        self.x_mem_wmask        = Signal.like(self.rvfi.mem_wmask)
        self.x_mem_rmask        = Signal.like(self.rvfi.mem_rmask)
        self.x_mem_wdata        = Signal.like(self.rvfi.mem_wdata)
        self.x_stall            = Signal()
        self.m_mem_rdata        = Signal.like(self.rvfi.mem_rdata)
        self.m_fetch_misaligned = Signal()
        self.m_illegal_insn     = Signal()
        self.m_load_misaligned  = Signal()
        self.m_store_misaligned = Signal()
        self.m_exception        = Signal()
        self.m_mret             = Signal()
        self.m_branch_taken     = Signal()
        self.m_branch_target    = Signal(32)
        self.m_pc_rdata         = Signal.like(self.rvfi.pc_rdata)
        self.m_stall            = Signal()
        self.m_valid            = Signal()
        self.w_rd_addr          = Signal.like(self.rvfi.rd_addr)
        self.w_rd_wdata         = Signal.like(self.rvfi.rd_wdata)

        self.mtvec_r_base       = Signal(30)
        self.mepc_r_value       = Signal(32)

    def elaborate(self, platform):
        m = Module()

        # Instruction Metadata

        with m.If(~self.m_stall):
            m.d.sync += self.rvfi.valid.eq(self.m_valid)
        with m.Elif(self.rvfi.valid):
            m.d.sync += self.rvfi.valid.eq(0)

        with m.If(self.rvfi.valid):
            m.d.sync += self.rvfi.order.eq(self.rvfi.order + 1)

        x_insn = Signal.like(self.rvfi.insn)
        m_insn = Signal.like(self.rvfi.insn)

        with m.If(~self.d_stall):
            m.d.sync += x_insn.eq(self.d_insn)
        with m.If(~self.x_stall):
            m.d.sync += m_insn.eq(x_insn)
        with m.If(~self.m_stall):
            m.d.sync += self.rvfi.insn.eq(m_insn)

        with m.If(~self.m_stall):
            m.d.sync += [
                self.rvfi.trap.eq(reduce(or_, (
                    self.m_fetch_misaligned,
                    self.m_illegal_insn,
                    self.m_load_misaligned,
                    self.m_store_misaligned
                ))),
                self.rvfi.intr.eq(self.m_pc_rdata == self.mtvec_r_base << 2)
            ]

        m.d.comb += [
            self.rvfi.mode.eq(Const(3)), # M-mode
            self.rvfi.ixl.eq(Const(1)) # XLEN=32
        ]

        # Integer Register Read/Write

        x_rs1_addr  = Signal.like(self.rvfi.rs1_addr)
        x_rs2_addr  = Signal.like(self.rvfi.rs2_addr)
        x_rs1_rdata = Signal.like(self.rvfi.rs1_rdata)
        x_rs2_rdata = Signal.like(self.rvfi.rs2_rdata)

        m_rs1_addr  = Signal.like(self.rvfi.rs1_addr)
        m_rs2_addr  = Signal.like(self.rvfi.rs2_addr)
        m_rs1_rdata = Signal.like(self.rvfi.rs1_rdata)
        m_rs2_rdata = Signal.like(self.rvfi.rs2_rdata)

        with m.If(~self.d_stall):
            m.d.sync += [
                x_rs1_addr.eq(self.d_rs1_addr),
                x_rs2_addr.eq(self.d_rs2_addr),
                x_rs1_rdata.eq(self.d_rs1_rdata),
                x_rs2_rdata.eq(self.d_rs2_rdata)
            ]
        with m.If(~self.x_stall):
            m.d.sync += [
                m_rs1_addr.eq(x_rs1_addr),
                m_rs2_addr.eq(x_rs2_addr),
                m_rs1_rdata.eq(x_rs1_rdata),
                m_rs2_rdata.eq(x_rs2_rdata)
            ]
        with m.If(~self.m_stall):
            m.d.sync += [
                self.rvfi.rs1_addr.eq(m_rs1_addr),
                self.rvfi.rs2_addr.eq(m_rs2_addr),
                self.rvfi.rs1_rdata.eq(m_rs1_rdata),
                self.rvfi.rs2_rdata.eq(m_rs2_rdata)
            ]

        m.d.comb += [
            self.rvfi.rd_addr.eq(self.w_rd_addr),
            self.rvfi.rd_wdata.eq(self.w_rd_wdata)
        ]

        # Program Counter

        m_pc_wdata = Signal.like(self.rvfi.pc_wdata)

        with m.If(self.m_exception):
            m.d.comb += m_pc_wdata.eq(self.mtvec_r_base << 2)
        with m.Elif(self.m_mret):
            m.d.comb += m_pc_wdata.eq(self.mepc_r_value)
        with m.Elif(self.m_branch_taken):
            m.d.comb += m_pc_wdata.eq(self.m_branch_target)
        with m.Else():
            m.d.comb += m_pc_wdata.eq(self.m_pc_rdata + 4)

        with m.If(~self.m_stall):
            m.d.sync += [
                self.rvfi.pc_rdata.eq(self.m_pc_rdata),
                self.rvfi.pc_wdata.eq(m_pc_wdata)
            ]

        # Memory Access

        m_mem_addr  = Signal.like(self.rvfi.mem_addr)
        m_mem_wmask = Signal.like(self.rvfi.mem_wmask)
        m_mem_rmask = Signal.like(self.rvfi.mem_rmask)
        m_mem_wdata = Signal.like(self.rvfi.mem_wdata)

        with m.If(~self.x_stall):
            m.d.sync += [
                m_mem_addr.eq(self.x_mem_addr),
                m_mem_wmask.eq(self.x_mem_wmask),
                m_mem_rmask.eq(self.x_mem_rmask),
                m_mem_wdata.eq(self.x_mem_wdata)
            ]
        with m.If(~self.m_stall):
            m.d.sync += [
                self.rvfi.mem_addr.eq(m_mem_addr),
                self.rvfi.mem_wmask.eq(m_mem_wmask),
                self.rvfi.mem_rmask.eq(m_mem_rmask),
                self.rvfi.mem_wdata.eq(m_mem_wdata),
                self.rvfi.mem_rdata.eq(self.m_mem_rdata)
            ]

        return m
