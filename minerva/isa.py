from .csr import *

__all__ = [
    "Opcode", "Funct3", "Funct7", "Funct12", "CSRIndex", "Cause",
    "flat_layout", "misa_layout", "mstatus_layout", "mtvec_layout", "mepc_layout",
    "mip_layout", "mie_layout", "mcause_layout", "dcsr_layout", "tdata1_layout"
]

class Opcode:
    LUI       = 0b01101
    AUIPC     = 0b00101
    JAL       = 0b11011
    JALR      = 0b11001
    BRANCH    = 0b11000
    LOAD      = 0b00000
    STORE     = 0b01000
    OP_IMM_32 = 0b00100
    OP_32     = 0b01100
    MISC_MEM  = 0b00011
    SYSTEM    = 0b11100


class Funct3:
    BEQ  = B  = ADD  = FENCE  = PRIV   = MUL    = 0b000
    BNE  = H  = SLL  = FENCEI = CSRRW  = MULH   = 0b001
    _    = W  = SLT  = _      = CSRRS  = MULHSU = 0b010
    _    = _  = SLTU = _      = CSRRC  = MULHU  = 0b011
    BLT  = BU = XOR  = _      = _      = DIV    = 0b100
    BGE  = HU = SR   = _      = CSRRWI = DIVU   = 0b101
    BLTU = _  = OR   = _      = CSRRSI = REM    = 0b110
    BGEU = _  = AND  = _      = CSRRCI = REMU   = 0b111


class Funct7:
    SRL = ADD = 0b0000000
    MULDIV    = 0b0000001
    SRA = SUB = 0b0100000


class Funct12:
    ECALL  = 0b000000000000
    EBREAK = 0b000000000001
    MRET   = 0b001100000010
    WFI    = 0b000100000101


class CSRIndex:
    MVENDORID   = 0xF11
    MARCHID     = 0xF12
    MIMPID      = 0xF13
    MHARTID     = 0xF14
    MSTATUS     = 0x300
    MISA        = 0x301
    MEDELEG     = 0x302
    MIDELEG     = 0x303
    MIE         = 0x304
    MTVEC       = 0x305
    MCOUTEREN   = 0x306
    MSCRATCH    = 0x340
    MEPC        = 0x341
    MCAUSE      = 0x342
    MTVAL       = 0x343
    MIP         = 0x344
    # µarch specific
    IRQ_MASK    = 0x330
    IRQ_PENDING = 0x360
    # trigger module
    TSELECT     = 0x7a0
    TDATA1      = 0x7a1
    TDATA2      = 0x7a2
    TDATA3      = 0x7a3
    TINFO       = 0x7a4
    MCONTEXT    = 0x7a8
    # debug module
    DCSR        = 0x7b0
    DPC         = 0x7b1


class Cause:
    FETCH_MISALIGNED     = 0
    FETCH_ACCESS_FAULT   = 1
    ILLEGAL_INSTRUCTION  = 2
    BREAKPOINT           = 3
    LOAD_MISALIGNED      = 4
    LOAD_ACCESS_FAULT    = 5
    STORE_MISALIGNED     = 6
    STORE_ACCESS_FAULT   = 7
    ECALL_FROM_U         = 8
    ECALL_FROM_S         = 9
    ECALL_FROM_M         = 11
    FETCH_PAGE_FAULT     = 12
    LOAD_PAGE_FAULT      = 13
    STORE_PAGE_FAULT     = 15
    # interrupts
    U_SOFTWARE_INTERRUPT = 0
    S_SOFTWARE_INTERRUPT = 1
    M_SOFTWARE_INTERRUPT = 3
    U_TIMER_INTERRUPT    = 4
    S_TIMER_INTERRUPT    = 5
    M_TIMER_INTERRUPT    = 7
    U_EXTERNAL_INTERRUPT = 8
    S_EXTERNAL_INTERRUPT = 9
    M_EXTERNAL_INTERRUPT = 11


# CSR layouts

flat_layout = [
    ("value", 32, CSRAccess.WARL)
]


misa_layout = [
    ("extensions", 26, CSRAccess.WARL),
    ("wiri0",       4, CSRAccess.WIRI),
    ("mxl",         2, CSRAccess.WARL)
]


mstatus_layout = [
    ("uie",   1, CSRAccess.WARL), # User Interrupt Enable
    ("sie",   1, CSRAccess.WARL), # Supervisor Interrupt Enable
    ("wpri0", 1, CSRAccess.WPRI),
    ("mie",   1, CSRAccess.WARL), # Machine Interrupt Enable
    ("upie",  1, CSRAccess.WARL), # User Previous Interrupt Enable
    ("spie",  1, CSRAccess.WARL), # Supervisor Previous Interrupt Enable
    ("wpri1", 1, CSRAccess.WPRI),
    ("mpie",  1, CSRAccess.WARL), # Machine Previous Interrupt Enable
    ("spp",   1, CSRAccess.WARL), # Supervisor Previous Privilege
    ("wpri2", 2, CSRAccess.WPRI),
    ("mpp",   2, CSRAccess.WARL), # Machine Previous Privilege
    ("fs",    2, CSRAccess.WARL), # FPU Status
    ("xs",    2, CSRAccess.WARL), # user-mode eXtensions Status
    ("mprv",  1, CSRAccess.WARL), # Modify PRiVilege
    ("sum",   1, CSRAccess.WARL), # Supervisor User Memory access
    ("mxr",   1, CSRAccess.WARL), # Make eXecutable Readable
    ("tvm",   1, CSRAccess.WARL), # Trap Virtual Memory
    ("tw",    1, CSRAccess.WARL), # Timeout Wait
    ("tsr",   1, CSRAccess.WARL), # Trap SRET
    ("wpri3", 8, CSRAccess.WPRI),
    ("sd",    1, CSRAccess.WARL)  # State Dirty (set if XS or FS are set to dirty)
]


mtvec_layout = [
    ("mode",  2, CSRAccess.WARL),
    ("base", 30, CSRAccess.WARL)
]


mepc_layout = [
    ("zero",  2, CSRAccess.WIRI),  # 16-bit instructions are not supported
    ("base", 30, CSRAccess.WARL)
]


mip_layout = [
    ("usip",   1, CSRAccess.WARL),
    ("ssip",   1, CSRAccess.WARL),
    ("wiri0",  1, CSRAccess.WIRI),
    ("msip",   1, CSRAccess.WARL),
    ("utip",   1, CSRAccess.WARL),
    ("stip",   1, CSRAccess.WARL),
    ("wiri1",  1, CSRAccess.WIRI),
    ("mtip",   1, CSRAccess.WARL),
    ("ueip",   1, CSRAccess.WARL),
    ("seip",   1, CSRAccess.WARL),
    ("wiri2",  1, CSRAccess.WIRI),
    ("meip",   1, CSRAccess.WARL),
    ("wiri3", 20, CSRAccess.WIRI)
]


mie_layout = [
    ("usie",   1, CSRAccess.WARL),
    ("ssie",   1, CSRAccess.WARL),
    ("wpri0",  1, CSRAccess.WPRI),
    ("msie",   1, CSRAccess.WARL),
    ("utie",   1, CSRAccess.WARL),
    ("stie",   1, CSRAccess.WARL),
    ("wpri1",  1, CSRAccess.WPRI),
    ("mtie",   1, CSRAccess.WARL),
    ("ueie",   1, CSRAccess.WARL),
    ("seie",   1, CSRAccess.WARL),
    ("wpri2",  1, CSRAccess.WPRI),
    ("meie",   1, CSRAccess.WARL),
    ("wpri3", 20, CSRAccess.WPRI)
]


mcause_layout = [
    ("ecode",    31, CSRAccess.WARL),
    ("interrupt", 1, CSRAccess.WARL)
]


dcsr_layout = [
    ("prv",        2, CSRAccess.WARL), # Privilege level before Debug Mode was entered
    ("step",       1, CSRAccess.WARL), # Execute a single instruction and re-enter Debug Mode
    ("nmip",       1, CSRAccess.WLRL), # A non-maskable interrupt is pending
    ("mprven",     1, CSRAccess.WARL), # Use mstatus.mprv in Debug Mode
    ("zero0",      1, CSRAccess.WPRI),
    ("cause",      3, CSRAccess.WLRL), # Explains why Debug Mode was entered
    ("stoptime",   1, CSRAccess.WARL), # Stop timer increment during Debug Mode
    ("stopcount",  1, CSRAccess.WARL), # Stop counter increment during Debug Mode
    ("stepie",     1, CSRAccess.WARL), # Enable interrupts during single stepping
    ("ebreaku",    1, CSRAccess.WARL), # EBREAKs in U-mode enter Debug Mode
    ("ebreaks",    1, CSRAccess.WARL), # EBREAKs in S-mode enter Debug Mode
    ("zero1",      1, CSRAccess.WPRI),
    ("ebreakm",    1, CSRAccess.WARL), # EBREAKs in M-mode enter Debug Mode
    ("zero2",     12, CSRAccess.WPRI),
    ("xdebugver",  4, CSRAccess.WLRL)  # External Debug specification version
]


tdata1_layout = [
    ("data",  27, CSRAccess.WARL),
    ("dmode",  1, CSRAccess.WARL),
    ("type",   4, CSRAccess.WARL)
]
