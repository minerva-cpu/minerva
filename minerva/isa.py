from .csr import *


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
    ("value", 32, CSRAccess.RW),
]


misa_layout = [
    ("extensions", 26, CSRAccess.RW),
    ("zero",        4, CSRAccess.RO),
    ("mxl",         2, CSRAccess.RW),
]


mstatus_layout = [
    ("uie",   1, CSRAccess.RO), # User Interrupt Enable
    ("sie",   1, CSRAccess.RO), # Supervisor Interrupt Enable
    ("zero0", 1, CSRAccess.RO),
    ("mie",   1, CSRAccess.RW), # Machine Interrupt Enable
    ("upie",  1, CSRAccess.RO), # User Previous Interrupt Enable
    ("spie",  1, CSRAccess.RO), # Supervisor Previous Interrupt Enable
    ("zero1", 1, CSRAccess.RO),
    ("mpie",  1, CSRAccess.RW), # Machine Previous Interrupt Enable
    ("spp",   1, CSRAccess.RO), # Supervisor Previous Privilege
    ("zero2", 2, CSRAccess.RO),
    ("mpp",   2, CSRAccess.RW), # Machine Previous Privilege
    ("fs",    2, CSRAccess.RO), # FPU Status
    ("xs",    2, CSRAccess.RO), # user-mode eXtensions Status
    ("mprv",  1, CSRAccess.RO), # Modify PRiVilege
    ("sum",   1, CSRAccess.RO), # Supervisor User Memory access
    ("mxr",   1, CSRAccess.RO), # Make eXecutable Readable
    ("tvm",   1, CSRAccess.RO), # Trap Virtual Memory
    ("tw",    1, CSRAccess.RO), # Timeout Wait
    ("tsr",   1, CSRAccess.RO), # Trap SRET
    ("zero3", 8, CSRAccess.RO),
    ("sd",    1, CSRAccess.RO), # State Dirty (set if XS or FS are set to dirty)
]


mtvec_layout = [
    ("mode",  2, CSRAccess.RW),
    ("base", 30, CSRAccess.RW),
]


mepc_layout = [
    ("zero",  2, CSRAccess.RO), # 16-bit instructions are not supported
    ("base", 30, CSRAccess.RW),
]


mip_layout = [
    ("usip",   1, CSRAccess.RO),
    ("ssip",   1, CSRAccess.RO),
    ("zero0",  1, CSRAccess.RO),
    ("msip",   1, CSRAccess.RW),
    ("utip",   1, CSRAccess.RO),
    ("stip",   1, CSRAccess.RO),
    ("zero1",  1, CSRAccess.RO),
    ("mtip",   1, CSRAccess.RW),
    ("ueip",   1, CSRAccess.RO),
    ("seip",   1, CSRAccess.RO),
    ("zero2",  1, CSRAccess.RO),
    ("meip",   1, CSRAccess.RW),
    ("zero3", 20, CSRAccess.RO),
]


mie_layout = [
    ("usie",   1, CSRAccess.RO),
    ("ssie",   1, CSRAccess.RO),
    ("zero0",  1, CSRAccess.RO),
    ("msie",   1, CSRAccess.RW),
    ("utie",   1, CSRAccess.RO),
    ("stie",   1, CSRAccess.RO),
    ("zero1",  1, CSRAccess.RO),
    ("mtie",   1, CSRAccess.RW),
    ("ueie",   1, CSRAccess.RO),
    ("seie",   1, CSRAccess.RO),
    ("zero2",  1, CSRAccess.RO),
    ("meie",   1, CSRAccess.RW),
    ("zero3", 20, CSRAccess.RO),
]


mcause_layout = [
    ("ecode",    31, CSRAccess.RW),
    ("interrupt", 1, CSRAccess.RW),
]


dcsr_layout = [
    ("prv",        2, CSRAccess.RW), # Privilege level before Debug Mode was entered
    ("step",       1, CSRAccess.RW), # Execute a single instruction and re-enter Debug Mode
    ("nmip",       1, CSRAccess.RO), # A non-maskable interrupt is pending
    ("mprven",     1, CSRAccess.RW), # Use mstatus.mprv in Debug Mode
    ("zero0",      1, CSRAccess.RO),
    ("cause",      3, CSRAccess.RO), # Explains why Debug Mode was entered
    ("stoptime",   1, CSRAccess.RW), # Stop timer increment during Debug Mode
    ("stopcount",  1, CSRAccess.RW), # Stop counter increment during Debug Mode
    ("stepie",     1, CSRAccess.RW), # Enable interrupts during single stepping
    ("ebreaku",    1, CSRAccess.RW), # EBREAKs in U-mode enter Debug Mode
    ("ebreaks",    1, CSRAccess.RW), # EBREAKs in S-mode enter Debug Mode
    ("zero1",      1, CSRAccess.RO),
    ("ebreakm",    1, CSRAccess.RW), # EBREAKs in M-mode enter Debug Mode
    ("zero2",     12, CSRAccess.RO),
    ("xdebugver",  4, CSRAccess.RO), # External Debug specification version
]


tdata1_layout = [
    ("data",  27, CSRAccess.RW),
    ("dmode",  1, CSRAccess.RW),
    ("type",   4, CSRAccess.RW),
]
