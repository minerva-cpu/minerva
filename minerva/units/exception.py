from amaranth import *
from amaranth.lib import enum, wiring
from amaranth.lib.data import StructLayout
from amaranth.lib.wiring import In, Out

from .. import csr


__all__ = ["ExceptionUnit"]


class MSTATUS(csr.Register):
    class Mode(enum.Enum, shape=2):
        USER       = 0
        SUPERVISOR = 1
        MACHINE    = 3

    def __init__(self):
        super().__init__({
            "_uie":  csr.Field(csr.action.WPRI, 1),
            "_sie":  csr.Field(csr.action.WPRI, 1),
            "_2":    csr.Field(csr.action.WPRI, 1),
            "mie":   csr.Field(csr.action.WARL, 1),
            "_upie": csr.Field(csr.action.WPRI, 1),
            "_spie": csr.Field(csr.action.WPRI, 1),
            "_6":    csr.Field(csr.action.WPRI, 1),
            "mpie":  csr.Field(csr.action.WARL, 1),
            "_spp":  csr.Field(csr.action.WPRI, 1),
            "_9":    csr.Field(csr.action.WPRI, 2),
            "mpp":   csr.Field(csr.action.WARL, self.Mode, init=self.Mode.MACHINE),
            "_fs":   csr.Field(csr.action.WPRI, 2),
            "_xs":   csr.Field(csr.action.WPRI, 2),
            "_mprv": csr.Field(csr.action.WPRI, 1),
            "_sum":  csr.Field(csr.action.WPRI, 1),
            "_mxr":  csr.Field(csr.action.WPRI, 1),
            "_tvm":  csr.Field(csr.action.WPRI, 1),
            "_tw":   csr.Field(csr.action.WPRI, 1),
            "_tsr":  csr.Field(csr.action.WPRI, 1),
            "_23":   csr.Field(csr.action.WPRI, 8),
            "_sd":   csr.Field(csr.action.WPRI, 1),
        })


class MISA(csr.Register):
    class Extension(enum.Flag, shape=26):
        A = 1 <<  0 # Atomic
        C = 1 <<  2 # Compressed
        D = 1 <<  3 # Double-precision floating-point
        E = 1 <<  4 # RV32E base ISA
        F = 1 <<  5 # Single-precision floating-point
        G = 1 <<  6 # Additional standard extensions
        I = 1 <<  8 # RV32I base ISA
        M = 1 << 12 # Integer Multiply/Divide
        N = 1 << 13 # User-level interrupts
        Q = 1 << 16 # Quad-precision floating-point
        S = 1 << 18 # Supervisor-mode
        U = 1 << 20 # User-mode
        X = 1 << 23 # Non-standard extensions

    class MXL(enum.Enum, shape=2):
        _UNIMP   = 0
        XLEN_32  = 1
        XLEN_64  = 2
        XLEN_128 = 3

    def __init__(self, with_muldiv):
        misa_ext = self.Extension.I
        if with_muldiv:
            misa_ext |= self.Extension.M

        super().__init__({
            "ext": csr.Field(csr.action.WARL, self.Extension, init=misa_ext),
            "_26": csr.Field(csr.action.WPRI, 4), # actually WARL, but always reads 0
            "mxl": csr.Field(csr.action.WARL, self.MXL, init=self.MXL.XLEN_32),
        })


class MIE(csr.Register):
    _usie: csr.Field(csr.action.WPRI,  1)
    _ssie: csr.Field(csr.action.WPRI,  1)
    _2:    csr.Field(csr.action.WPRI,  1)
    msie:  csr.Field(csr.action.WARL,  1)
    _utie: csr.Field(csr.action.WPRI,  1)
    _stie: csr.Field(csr.action.WPRI,  1)
    _6:    csr.Field(csr.action.WPRI,  1)
    mtie:  csr.Field(csr.action.WARL,  1)
    _ueie: csr.Field(csr.action.WPRI,  1)
    _seie: csr.Field(csr.action.WPRI,  1)
    _10:   csr.Field(csr.action.WPRI,  1)
    meie:  csr.Field(csr.action.WARL,  1)
    _12:   csr.Field(csr.action.WPRI,  4)
    mfie:  csr.Field(csr.action.WARL, 16) # Machine Fast Interrupts Enable (custom)


class MIP(csr.Register):
    _usip: csr.Field(csr.action.WPRI,  1)
    _ssip: csr.Field(csr.action.WPRI,  1)
    _2:    csr.Field(csr.action.WPRI,  1)
    msip:  csr.Field(csr.action.WARL,  1)
    _utip: csr.Field(csr.action.WPRI,  1)
    _stip: csr.Field(csr.action.WPRI,  1)
    _6:    csr.Field(csr.action.WPRI,  1)
    mtip:  csr.Field(csr.action.WARL,  1)
    _ueip: csr.Field(csr.action.WPRI,  1)
    _seip: csr.Field(csr.action.WPRI,  1)
    _10:   csr.Field(csr.action.WPRI,  1)
    meip:  csr.Field(csr.action.WARL,  1)
    _12:   csr.Field(csr.action.WPRI,  4)
    mfip:  csr.Field(csr.action.WARL, 16) # Machine Fast Interrupts Pending (custom)


class MTVEC(csr.Register):
    class Mode(enum.Enum, shape=2):
        DIRECT   = 0b00
        VECTORED = 0b01

    def __init__(self):
        super().__init__({
            "mode": csr.Field(csr.action.WARL, self.Mode, init=self.Mode.DIRECT),
            "base": csr.Field(csr.action.WARL, 30),
        })


class MSCRATCH(csr.Register):
    def __init__(self):
        super().__init__(csr.Field(csr.action.WARL, 32))


class MEPC(csr.Register):
    _0:   csr.Field(csr.action.WPRI,  2)
    base: csr.Field(csr.action.WARL, 30)


class MCAUSE(csr.Register):
    class Code(enum.IntEnum, shape=32):
        # interrupts
        S_SOFTWARE_INTERRUPT  = (1 << 31) |  1
        M_SOFTWARE_INTERRUPT  = (1 << 31) |  3
        S_TIMER_INTERRUPT     = (1 << 31) |  5
        M_TIMER_INTERRUPT     = (1 << 31) |  7
        S_EXTERNAL_INTERRUPT  = (1 << 31) |  9
        M_EXTERNAL_INTERRUPT  = (1 << 31) | 11
        # interrupts (custom)
        M_FAST_INTERRUPT_0    = (1 << 31) | 16
        M_FAST_INTERRUPT_1    = (1 << 31) | 17
        M_FAST_INTERRUPT_2    = (1 << 31) | 18
        M_FAST_INTERRUPT_3    = (1 << 31) | 19
        M_FAST_INTERRUPT_4    = (1 << 31) | 20
        M_FAST_INTERRUPT_5    = (1 << 31) | 21
        M_FAST_INTERRUPT_6    = (1 << 31) | 22
        M_FAST_INTERRUPT_7    = (1 << 31) | 23
        M_FAST_INTERRUPT_8    = (1 << 31) | 24
        M_FAST_INTERRUPT_9    = (1 << 31) | 25
        M_FAST_INTERRUPT_10   = (1 << 31) | 26
        M_FAST_INTERRUPT_11   = (1 << 31) | 27
        M_FAST_INTERRUPT_12   = (1 << 31) | 28
        M_FAST_INTERRUPT_13   = (1 << 31) | 29
        M_FAST_INTERRUPT_14   = (1 << 31) | 30
        M_FAST_INTERRUPT_15   = (1 << 31) | 31
        # exceptions
        FETCH_MISALIGNED      =  0
        FETCH_ACCESS_FAULT    =  1
        ILLEGAL_INSTRUCTION   =  2
        BREAKPOINT            =  3
        LOAD_MISALIGNED       =  4
        LOAD_ACCESS_FAULT     =  5
        STORE_MISALIGNED      =  6
        STORE_ACCESS_FAULT    =  7
        ECALL_FROM_USER       =  8
        ECALL_FROM_SUPERVISOR =  9
        ECALL_FROM_MACHINE    = 11
        FETCH_PAGE_FAULT      = 12
        LOAD_PAGE_FAULT       = 13
        STORE_PAGE_FAULT      = 15

    def __init__(self):
        super().__init__(csr.Field(csr.action.WLRL, self.Code))


class MTVAL(csr.Register):
    def __init__(self):
        super().__init__(csr.Field(csr.action.WARL, 32))


class ExceptionUnit(wiring.Component):
    x_mtvec_base:         Out(30)
    x_mepc_base:          Out(30)
    x_ready:              In(1)

    m_fetch_misaligned:   In(1)
    m_fetch_error:        In(1)
    m_fetch_badaddr:      In(30)
    m_load_misaligned:    In(1)
    m_load_error:         In(1)
    m_store_misaligned:   In(1)
    m_store_error:        In(1)
    m_loadstore_badaddr:  In(30)
    m_branch_target:      In(32)
    m_illegal:            In(1)
    m_ebreak:             In(1)
    m_ecall:              In(1)
    m_pc:                 In(32)
    m_instruction:        In(32)
    m_result:             In(32)
    m_mret:               In(1)
    m_trap:               Out(1)
    m_ready:              In(1)

    w_software_interrupt: In(1)
    w_timer_interrupt:    In(1)
    w_external_interrupt: In(1)
    w_fast_interrupt:     In(16)
    w_pc:                 In(32)
    w_valid:              In(1)

    def __init__(self, with_muldiv):
        self._csr_bank = csr.RegisterBank(addr_width=7)

        self._mstatus  = self._csr_bank.add("mstatus",  MSTATUS(),         addr=0x00)
        self._misa     = self._csr_bank.add("misa",     MISA(with_muldiv), addr=0x01)
        self._mie      = self._csr_bank.add("mie",      MIE(),             addr=0x04)
        self._mtvec    = self._csr_bank.add("mtvec",    MTVEC(),           addr=0x05)
        self._mscratch = self._csr_bank.add("mscratch", MSCRATCH(),        addr=0x40)
        self._mepc     = self._csr_bank.add("mepc",     MEPC(),            addr=0x41)
        self._mcause   = self._csr_bank.add("mcause",   MCAUSE(),          addr=0x42)
        self._mtval    = self._csr_bank.add("mtval",    MTVAL(),           addr=0x43)
        self._mip      = self._csr_bank.add("mip",      MIP(),             addr=0x44)

        super().__init__()

    @property
    def csr_bank(self):
        return self._csr_bank

    def elaborate(self, platform):
        m = Module()

        m.submodules.csr_bank = self._csr_bank

        # X stage:

        m.d.comb += [
            self.x_mtvec_base.eq(self._mtvec.f.base.x_data),
            self.x_mepc_base .eq(self._mepc .f.base.x_data),
        ]

        # M stage:

        m_mstatus = Signal(StructLayout({"mie": 1, "mpie": 1}))
        m_mie     = Signal(StructLayout({"msie": 1, "mtie": 1, "meie": 1, "mfie": 16}))
        m_mip     = Signal(StructLayout({"msip": 1, "mtip": 1, "meip": 1, "mfip": 16}))
        m_mcause  = Signal(32)
        m_mtval   = Signal(32)

        with m.If(self.x_ready):
            m.d.sync += [
                m_mstatus.mie .eq(self._mstatus.f.mie .x_data),
                m_mstatus.mpie.eq(self._mstatus.f.mpie.x_data),

                m_mie.msie.eq(self._mie.f.msie.x_data),
                m_mie.mtie.eq(self._mie.f.mtie.x_data),
                m_mie.meie.eq(self._mie.f.meie.x_data),
                m_mie.mfie.eq(self._mie.f.mfie.x_data),

                m_mip.msip.eq(self._mip.f.msip.x_data),
                m_mip.mtip.eq(self._mip.f.mtip.x_data),
                m_mip.meip.eq(self._mip.f.meip.x_data),
                m_mip.mfip.eq(self._mip.f.mfip.x_data),
            ]

        m_trap_req = Signal(StructLayout({
            "i": StructLayout({
                "m_software":       1,
                "m_timer":          1,
                "m_external":       1,
                "m_fast":          16,
            }),
            "e": StructLayout({
                "fetch_misaligned": 1,
                "fetch_error":      1,
                "illegal":          1,
                "ebreak":           1,
                "load_misaligned":  1,
                "load_error":       1,
                "store_misaligned": 1,
                "store_error":      1,
                "ecall":            1,
            }),
        }))
        m_trap_gnt = Signal.like(m_trap_req)

        with m.If(m_mstatus.mie):
            m.d.comb += [
                m_trap_req.i.m_software.eq(m_mie.msie & m_mip.msip),
                m_trap_req.i.m_timer   .eq(m_mie.mtie & m_mip.mtip),
                m_trap_req.i.m_external.eq(m_mie.meie & m_mip.meip),
                m_trap_req.i.m_fast    .eq(m_mie.mfie & m_mip.mfip),
            ]

        m.d.comb += [
            m_trap_req.e.fetch_misaligned.eq(self.m_fetch_misaligned),
            m_trap_req.e.fetch_error     .eq(self.m_fetch_error),
            m_trap_req.e.illegal         .eq(self.m_illegal),
            m_trap_req.e.ebreak          .eq(self.m_ebreak),
            m_trap_req.e.load_misaligned .eq(self.m_load_misaligned),
            m_trap_req.e.load_error      .eq(self.m_load_error),
            m_trap_req.e.store_misaligned.eq(self.m_store_misaligned),
            m_trap_req.e.store_error     .eq(self.m_store_error),
            m_trap_req.e.ecall           .eq(self.m_ecall),
        ]

        m.d.comb += [
            m_trap_gnt.eq(m_trap_req.as_value() & (-m_trap_req.as_value())), # isolate rightmost 1-bit
            self.m_trap.eq(m_trap_gnt.as_value().any()),
        ]

        m_mcause_mux  = 0
        m_mcause_mux |= Mux(m_trap_gnt.i.m_software,       MCAUSE.Code.M_SOFTWARE_INTERRUPT, 0)
        m_mcause_mux |= Mux(m_trap_gnt.i.m_timer,          MCAUSE.Code.M_TIMER_INTERRUPT,    0)
        m_mcause_mux |= Mux(m_trap_gnt.i.m_external,       MCAUSE.Code.M_EXTERNAL_INTERRUPT, 0)
        for j in range(16):
            m_mcause_mux |= Mux(m_trap_gnt.i.m_fast[j],    MCAUSE.Code.M_FAST_INTERRUPT_0+j, 0)
        m_mcause_mux |= Mux(m_trap_gnt.e.fetch_misaligned, MCAUSE.Code.FETCH_MISALIGNED,     0)
        m_mcause_mux |= Mux(m_trap_gnt.e.fetch_error,      MCAUSE.Code.FETCH_ACCESS_FAULT,   0)
        m_mcause_mux |= Mux(m_trap_gnt.e.illegal,          MCAUSE.Code.ILLEGAL_INSTRUCTION,  0)
        m_mcause_mux |= Mux(m_trap_gnt.e.ebreak,           MCAUSE.Code.BREAKPOINT,           0)
        m_mcause_mux |= Mux(m_trap_gnt.e.load_misaligned,  MCAUSE.Code.LOAD_MISALIGNED,      0)
        m_mcause_mux |= Mux(m_trap_gnt.e.load_error,       MCAUSE.Code.LOAD_ACCESS_FAULT,    0)
        m_mcause_mux |= Mux(m_trap_gnt.e.store_misaligned, MCAUSE.Code.STORE_MISALIGNED,     0)
        m_mcause_mux |= Mux(m_trap_gnt.e.store_error,      MCAUSE.Code.STORE_ACCESS_FAULT,   0)
        m_mcause_mux |= Mux(m_trap_gnt.e.ecall,            MCAUSE.Code.ECALL_FROM_MACHINE,   0)

        m.d.comb += m_mcause.eq(m_mcause_mux)

        m_mtval_mux  = 0
        m_mtval_mux |= Mux(m_trap_gnt.e.fetch_misaligned, self.m_branch_target,          0)
        m_mtval_mux |= Mux(m_trap_gnt.e.fetch_error,      self.m_fetch_badaddr << 2,     0)
        m_mtval_mux |= Mux(m_trap_gnt.e.illegal,          self.m_instruction,            0)
        m_mtval_mux |= Mux(m_trap_gnt.e.ebreak,           self.m_pc,                     0)
        m_mtval_mux |= Mux(m_trap_gnt.e.load_misaligned | m_trap_gnt.e.store_misaligned,
                           self.m_result, 0)
        m_mtval_mux |= Mux(m_trap_gnt.e.load_error | m_trap_gnt.e.store_error,
                           self.m_loadstore_badaddr << 2, 0)

        m.d.comb += m_mtval.eq(m_mtval_mux)

        m.d.comb += [
            # read-only fields:
            self._mstatus.f.mpp .m_rdy.eq(0),
            self._misa   .f.ext .m_rdy.eq(0),
            self._misa   .f.mxl .m_rdy.eq(0),
            self._mtvec  .f.mode.m_rdy.eq(0),
            self._mcause .f     .m_rdy.eq(0),
            self._mip    .f.msip.m_rdy.eq(0),
            self._mip    .f.mtip.m_rdy.eq(0),
            self._mip    .f.meip.m_rdy.eq(0),
            self._mip    .f.mfip.m_rdy.eq(0),
        ]

        # W stage:

        w_mret    = Signal()
        w_trap    = Signal()
        w_mstatus = Signal.like(m_mstatus)
        w_mcause  = Signal.like(m_mcause)
        w_mtval   = Signal.like(m_mtval)

        with m.If(self.m_ready):
            m.d.sync += [
                w_mret   .eq(self.m_mret),
                w_trap   .eq(self.m_trap),
                w_mstatus.eq(m_mstatus),
                w_mcause .eq(m_mcause),
                w_mtval  .eq(m_mtval),
            ]

        m.d.comb += [
            self._mstatus.f.mie .w_en  .eq(self.w_valid & (w_mret | w_trap)),
            self._mstatus.f.mie .w_data.eq(Mux(w_mret, w_mstatus.mpie, 0)),
            self._mstatus.f.mpie.w_en  .eq(self.w_valid & w_trap),
            self._mstatus.f.mpie.w_data.eq(w_mstatus.mie),

            self._mepc.f.base.w_en  .eq(self.w_valid & w_trap),
            self._mepc.f.base.w_data.eq(self.w_pc[2:]),

            self._mcause.f.w_en  .eq(self.w_valid & w_trap),
            self._mcause.f.w_data.eq(w_mcause),

            self._mtval.f.w_en  .eq(self.w_valid & w_trap),
            self._mtval.f.w_data.eq(w_mtval),

            self._mip.f.msip.w_en  .eq(self.w_valid),
            self._mip.f.msip.w_data.eq(self.w_software_interrupt),
            self._mip.f.mtip.w_en  .eq(self.w_valid),
            self._mip.f.mtip.w_data.eq(self.w_timer_interrupt),
            self._mip.f.meip.w_en  .eq(self.w_valid),
            self._mip.f.meip.w_data.eq(self.w_external_interrupt),
            self._mip.f.mfip.w_en  .eq(self.w_valid),
            self._mip.f.mfip.w_data.eq(self.w_fast_interrupt),
        ]

        return m
