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
