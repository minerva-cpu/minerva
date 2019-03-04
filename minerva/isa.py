__all__ = [
    "Opcode", "Funct3", "Funct7", "Funct12", "CSRIndex", "CSRMode", "Cause",
    "flat_layout", "misa_layout", "mstatus_layout", "mtvec_layout", "mip_layout",
    "mie_layout", "mcause_layout", "dcsr_layout"
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
    BEQ  = B  = ADD  = FENCE  = PRIV   = 0b000
    BNE  = H  = SLL  = FENCEI = CSRRW  = 0b001
    _    = W  = SLT  = _      = CSRRS  = 0b010
    _    = _  = SLTU = _      = CSRRC  = 0b011
    BLT  = BU = XOR  = _      = _      = 0b100
    BGE  = HU = SR   = _      = CSRRWI = 0b101
    BLTU = _  = OR   = _      = CSRRSI = 0b110
    BGEU = _  = AND  = _      = CSRRCI = 0b111


class Funct7:
    SRL = ADD = 0b0000000
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
    # debug mode
    DCSR        = 0x7b0
    DPC         = 0x7b1


class CSRMode:
    RW0 = 0b00
    RW1 = 0b01
    RW2 = 0b10
    RO  = 0b11


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
    ("value", 32)
]


misa_layout = [
    ("extensions", 26),
    ("wiri0",       4),
    ("mxl",         2)
]


mstatus_layout = [
    ("uie",   1), # User Interrupt Enable
    ("sie",   1), # Supervisor Interrupt Enable
    ("wpri0", 1), # reserved
    ("mie",   1), # Machine Interrupt Enable
    ("upie",  1), # User Previous Interrupt Enable
    ("spie",  1), # Supervisor Previous Interrupt Enable
    ("wpri1", 1), # reserved
    ("mpie",  1), # Machine Previous Interrupt Enable
    ("spp",   1), # Supervisor Previous Privilege
    ("wpri2", 2), # reserved
    ("mpp",   2), # Machine Previous Privilege
    ("fs",    2), # FPU Status
    ("xs",    2), # user-mode eXtensions Status
    ("mprv",  1), # Modify PRiVilege
    ("sum",   1), # Supervisor User Memory access
    ("mxr",   1), # Make eXecutable Readable
    ("tvm",   1), # Trap Virtual Memory
    ("tw",    1), # Timeout Wait
    ("tsr",   1), # Trap SRET
    ("wpri3", 8), # reserved
    ("sd",    1)  # State Dirty (set if XS or FS are set to dirty)
]


mtvec_layout = [
    ("mode",  2),
    ("base", 30)
]


mip_layout = [
    ("usip",   1),
    ("ssip",   1),
    ("wiri0",  1),
    ("msip",   1),
    ("utip",   1),
    ("stip",   1),
    ("wiri1",  1),
    ("mtip",   1),
    ("ueip",   1),
    ("seip",   1),
    ("wiri2",  1),
    ("meip",   1),
    ("wiri3", 20)
]


mie_layout = [
    ("usie",   1),
    ("ssie",   1),
    ("wpri0",  1),
    ("msie",   1),
    ("utie",   1),
    ("stie",   1),
    ("wpri1",  1),
    ("mtie",   1),
    ("ueie",   1),
    ("seie",   1),
    ("wpri2",  1),
    ("meie",   1),
    ("wpri3", 20)
]


mcause_layout = [
    ("ecode",    31),
    ("interrupt", 1)
]


dcsr_layout = [
    ("prv",        2), # Privilege level before Debug Mode was entered
    ("step",       1), # Execute a single instruction and re-enter Debug Mode
    ("nmip",       1), # A non-maskable interrupt is pending
    ("mprven",     1), # Use mstatus.mprv in Debug Mode
    ("zero0",      1),
    ("cause",      3), # Explains why Debug Mode was entered
    ("stoptime",   1), # Stop timer increment during Debug Mode
    ("stopcount",  1), # Stop counter increment during Debug Mode
    ("stepie",     1), # Enable interrupts during single stepping
    ("ebreaku",    1), # EBREAKs in U-mode enter Debug Mode
    ("ebreaks",    1), # EBREAKs in S-mode enter Debug Mode
    ("zero1",      1),
    ("ebreakm",    1), # EBREAKs in M-mode enter Debug Mode
    ("zero2",     12),
    ("xdebugver",  4)  # External Debug specification version
]
