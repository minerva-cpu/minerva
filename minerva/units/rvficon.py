from functools import reduce
from operator import or_

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from amaranth_soc.memory import MemoryMap

from .. import isa
from .. import csr


__all__ = ["RVFISignature", "RVFIController"]


# RISC-V Formal Interface

class RVFISignature(wiring.Signature):
    def __init__(self, csr_map):
        assert isinstance(csr_map, MemoryMap)
        members = {
            "valid":     Out(1),
            "order":     Out(64),
            "insn":      Out(32),
            "trap":      Out(1),
            "halt":      Out(1),
            "intr":      Out(1),
            "mode":      Out(2),
            "ixl":       Out(2),

            "rs1_addr":  Out(5),
            "rs2_addr":  Out(5),
            "rs1_rdata": Out(32),
            "rs2_rdata": Out(32),
            "rd_addr":   Out(5),
            "rd_wdata":  Out(32),

            "pc_rdata":  Out(32),
            "pc_wdata":  Out(32),

            "mem_addr":  Out(32),
            "mem_rmask": Out(4),
            "mem_wmask": Out(4),
            "mem_rdata": Out(32),
            "mem_wdata": Out(32),
        }
        for res_info in csr_map.all_resources():
            csr_name = res_info.path[-1][0]
            members.update({
                f"csr_{csr_name}_rmask": Out(32),
                f"csr_{csr_name}_wmask": Out(32),
                f"csr_{csr_name}_rdata": Out(32),
                f"csr_{csr_name}_wdata": Out(32),
            })
        super().__init__(members)


class RVFIController(wiring.Component):
    def __init__(self, csr_map):
        assert isinstance(csr_map, MemoryMap)
        self._csr_map = csr_map
        super().__init__({
            "rvfi":               Out(RVFISignature(csr_map)),

            "d_insn":             In(32),
            "d_rs1_addr":         In(5),
            "d_rs2_addr":         In(5),
            "d_ready":            In(1),

            "x_rs1_rdata":        In(32),
            "x_rs2_rdata":        In(32),
            "x_mem_addr":         In(32),
            "x_mem_wmask":        In(4),
            "x_mem_rmask":        In(4),
            "x_mem_wdata":        In(32),
            "x_mtvec_base":       In(30),
            "x_mepc_base":        In(30),
            "x_ready":            In(1),

            "m_mem_rdata":        In(32),
            "m_fetch_misaligned": In(1),
            "m_illegal_insn":     In(1),
            "m_load_misaligned":  In(1),
            "m_store_misaligned": In(1),
            "m_exception":        In(1),
            "m_mret":             In(1),
            "m_branch_taken":     In(1),
            "m_branch_target":    In(32),
            "m_pc_rdata":         In(32),
            "m_ready":            In(1),
            "m_valid":            In(1),
            "w_rd_addr":          In(5),
            "w_rd_wdata":         In(32),
        })

    def elaborate(self, platform):
        m = Module()

        m_mtvec_base = Signal(30)
        m_mepc_base  = Signal(30)

        with m.If(self.x_ready):
            m.d.sync += [
                m_mtvec_base.eq(self.x_mtvec_base),
                m_mepc_base .eq(self.x_mepc_base),
            ]

        # Instruction Metadata

        with m.If(self.m_ready):
            m.d.sync += self.rvfi.valid.eq(self.m_valid)
        with m.Elif(self.rvfi.valid):
            m.d.sync += self.rvfi.valid.eq(0)

        with m.If(self.rvfi.valid):
            m.d.sync += self.rvfi.order.eq(self.rvfi.order + 1)

        x_insn = Signal.like(self.rvfi.insn)
        m_insn = Signal.like(self.rvfi.insn)

        with m.If(self.d_ready):
            m.d.sync += x_insn.eq(self.d_insn)
        with m.If(self.x_ready):
            m.d.sync += m_insn.eq(x_insn)
        with m.If(self.m_ready):
            m.d.sync += self.rvfi.insn.eq(m_insn)

        with m.If(self.m_ready):
            m.d.sync += [
                self.rvfi.trap.eq(reduce(or_, (
                    self.m_fetch_misaligned,
                    self.m_illegal_insn,
                    self.m_load_misaligned,
                    self.m_store_misaligned
                ))),
                self.rvfi.intr.eq(self.m_pc_rdata == (m_mtvec_base << 2))
            ]

        m.d.comb += [
            self.rvfi.mode.eq(Const(3)), # M-mode
            self.rvfi.ixl.eq(Const(1)) # XLEN=32
        ]

        # Integer Register Read/Write

        x_rs1_addr  = Signal.like(self.rvfi.rs1_addr)
        x_rs2_addr  = Signal.like(self.rvfi.rs2_addr)

        m_rs1_addr  = Signal.like(self.rvfi.rs1_addr)
        m_rs2_addr  = Signal.like(self.rvfi.rs2_addr)
        m_rs1_rdata = Signal.like(self.rvfi.rs1_rdata)
        m_rs2_rdata = Signal.like(self.rvfi.rs2_rdata)

        with m.If(self.d_ready):
            m.d.sync += [
                x_rs1_addr.eq(self.d_rs1_addr),
                x_rs2_addr.eq(self.d_rs2_addr),
            ]
        with m.If(self.x_ready):
            m.d.sync += [
                m_rs1_addr.eq(x_rs1_addr),
                m_rs2_addr.eq(x_rs2_addr),
                m_rs1_rdata.eq(self.x_rs1_rdata),
                m_rs2_rdata.eq(self.x_rs2_rdata)
            ]
        with m.If(self.m_ready):
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
            m.d.comb += m_pc_wdata.eq(m_mtvec_base << 2)
        with m.Elif(self.m_mret):
            m.d.comb += m_pc_wdata.eq(m_mepc_base << 2)
        with m.Elif(self.m_branch_taken):
            m.d.comb += m_pc_wdata.eq(self.m_branch_target)
        with m.Else():
            m.d.comb += m_pc_wdata.eq(self.m_pc_rdata + 4)

        with m.If(self.m_ready):
            m.d.sync += [
                self.rvfi.pc_rdata.eq(self.m_pc_rdata),
                self.rvfi.pc_wdata.eq(m_pc_wdata)
            ]

        # Memory Access

        m_mem_addr  = Signal.like(self.rvfi.mem_addr)
        m_mem_wmask = Signal.like(self.rvfi.mem_wmask)
        m_mem_rmask = Signal.like(self.rvfi.mem_rmask)
        m_mem_wdata = Signal.like(self.rvfi.mem_wdata)

        with m.If(self.x_ready):
            m.d.sync += [
                m_mem_addr.eq(self.x_mem_addr),
                m_mem_wmask.eq(self.x_mem_wmask),
                m_mem_rmask.eq(self.x_mem_rmask),
                m_mem_wdata.eq(self.x_mem_wdata)
            ]
        with m.If(self.m_ready):
            m.d.sync += [
                self.rvfi.mem_addr.eq(m_mem_addr),
                self.rvfi.mem_wmask.eq(m_mem_wmask),
                self.rvfi.mem_rmask.eq(m_mem_rmask),
                self.rvfi.mem_wdata.eq(m_mem_wdata),
                self.rvfi.mem_rdata.eq(self.m_mem_rdata)
            ]

        # CSRs

        for res_info in self._csr_map.all_resources():
            csr_reg, csr_name = res_info.resource, res_info.path[-1][0]
            assert isinstance(csr_reg, csr.Register)

            m_csr_rdata = Signal(32, name=f"m_csr_{csr_name}_rdata")
            w_csr_rdata = Signal(32, name=f"w_csr_{csr_name}_rdata")

            with m.If(self.x_ready):
                m.d.sync += m_csr_rdata.eq(csr_reg.x_rvfi_rdata)
            with m.If(self.m_ready):
                m.d.sync += w_csr_rdata.eq(m_csr_rdata)

            m.d.comb += [
                getattr(self.rvfi, f"csr_{csr_name}_rmask").eq(Const(1).replicate(32)),
                getattr(self.rvfi, f"csr_{csr_name}_rdata").eq(w_csr_rdata),
                getattr(self.rvfi, f"csr_{csr_name}_wmask").eq(csr_reg.w_rvfi_wmask),
                getattr(self.rvfi, f"csr_{csr_name}_wdata").eq(csr_reg.w_rvfi_wdata),
            ]

        return m
