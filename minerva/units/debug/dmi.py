from enum import Enum


class Version:
    NONE  = 0
    V011  = 1
    V013  = 2
    OTHER = 15


class Command:
    ACCESS_REG   = 0
    QUICK_ACCESS = 1
    ACCESS_MEM   = 2


class Error:
    NONE        = 0
    BUSY        = 1
    UNSUPPORTED = 2
    EXCEPTION   = 3
    HALT_RESUME = 4


RegMode = Enum("RegMode", ("R", "W", "W1", "RW", "RW1C", "WARL"))


class DmiOp:
    NOP   = 0
    READ  = 1
    WRITE = 2


# Debug registers

class DebugReg:
    DATA0      = 0x04
    DMCONTROL  = 0x10
    DMSTATUS   = 0x11
    HARTINFO   = 0x12
    HALTSUM1   = 0x13
    ABSTRACTCS = 0x16
    COMMAND    = 0x17
    PROGBUF0   = 0x20
    HALTSUM2   = 0x34
    HALTSUM3   = 0x35
    SBCS       = 0x38
    SBADDRESS0 = 0x39
    SBDATA0    = 0x3c
    HALTSUM0   = 0x40


dmstatus_layout = [
    ("version",           4, RegMode.R,    Version.V013),
    ("confstrptrvalid",   1, RegMode.R,    False),
    ("hasresethaltreq",   1, RegMode.R,    False),
    ("authbusy",          1, RegMode.R,    False),
    ("authenticated",     1, RegMode.R,    True),
    ("anyhalted",         1, RegMode.R,    False),
    ("allhalted",         1, RegMode.R,    False),
    ("anyrunning",        1, RegMode.R,    False),
    ("allrunning",        1, RegMode.R,    False),
    ("anyunavail",        1, RegMode.R,    False),
    ("allunavail",        1, RegMode.R,    False),
    ("anynonexistent",    1, RegMode.R,    False),
    ("allnonexistent",    1, RegMode.R,    False),
    ("anyresumeack",      1, RegMode.R,    False),
    ("allresumeack",      1, RegMode.R,    False),
    ("anyhavereset",      1, RegMode.R,    False),
    ("allhavereset",      1, RegMode.R,    False),
    ("zero0",             2, RegMode.R,    0),
    ("impebreak",         1, RegMode.R,    False),
    ("zero1",             9, RegMode.R,    0)
]


dmcontrol_layout = [
    ("dmactive",          1, RegMode.RW,   False),
    ("ndmreset",          1, RegMode.RW,   False),
    ("clrresethaltreq",   1, RegMode.W1,   False),
    ("setresethaltreq",   1, RegMode.W1,   False),
    ("zero0",             2, RegMode.R,    0),
    ("hartselhi",        10, RegMode.R,    0),
    ("hartsello",        10, RegMode.R,    0),
    ("hasel",             1, RegMode.RW,   False),
    ("zero1",             1, RegMode.R,    0),
    ("ackhavereset",      1, RegMode.W1,   False),
    ("hartreset",         1, RegMode.RW,   False),
    ("resumereq",         1, RegMode.W1,   False),
    ("haltreq",           1, RegMode.W,    False)
]


abstractcs_layout = [
    ("datacount",         4, RegMode.R,    1),
    ("zero0",             4, RegMode.R,    0),
    ("cmderr",            3, RegMode.RW1C, 0),
    ("zero1",             1, RegMode.R,    0),
    ("busy",              1, RegMode.R,    False),
    ("zero2",            11, RegMode.R,    0),
    ("progbufsize",       5, RegMode.R,    0),
    ("zero3",             3, RegMode.R,    0)
]


cmd_access_reg_layout = [
    ("regno",            16),
    ("write",             1),
    ("transfer",          1),
    ("postexec",          1),
    ("aarpostincrement",  1),
    ("aarsize",           3),
    ("zero0",             1),
]


command_layout = [
    ("control",          24, RegMode.W,    0),
    ("cmdtype",           8, RegMode.W,    Command.ACCESS_REG)
]


sbcs_layout = [
    ("sbaccess8",         1, RegMode.R,    True),
    ("sbaccess16",        1, RegMode.R,    True),
    ("sbaccess32",        1, RegMode.R,    True),
    ("sbaccess64",        1, RegMode.R,    False),
    ("sbaccess128",       1, RegMode.R,    False),
    ("sbasize",           7, RegMode.R,    32),
    ("sberror",           3, RegMode.RW1C, 0),
    ("sbreadondata",      1, RegMode.RW,   False),
    ("sbautoincrement",   1, RegMode.RW,   False),
    ("sbaccess",          3, RegMode.RW,   2),
    ("sbreadonaddr",      1, RegMode.RW,   False),
    ("sbbusy",            1, RegMode.R,    False),
    ("sbbusyerror",       1, RegMode.RW1C, False),
    ("zero0",             6, RegMode.R,    0),
    ("sbversion",         3, RegMode.R,    1)
]


flat_layout = [
    ("value",            32, RegMode.RW,   0)
]
