from nmigen.hdl.rec import *


__all__ = ["jtag_layout", "JTAGReg", "dtmcs_layout", "dmi_layout"]


jtag_layout = [
    ("tck",  1, DIR_FANIN),
    ("tdi",  1, DIR_FANIN),
    ("tdo",  1, DIR_FANOUT),
    ("tms",  1, DIR_FANIN),
    ("trst", 1, DIR_FANIN) # TODO
]


class JTAGReg:
    BYPASS = 0x00
    IDCODE = 0x01
    DTMCS  = 0x10
    DMI    = 0x11


# JTAG register layouts

dtmcs_layout = [
    ("version",       4),
    ("abits",         6),
    ("dmistat",       2),
    ("idle",          3),
    ("zero0",         1),
    ("dmireset",      1),
    ("dmihardreset",  1),
    ("zero1",        14)
]


dmi_layout = [
    ("op",    2),
    ("data", 32),
    ("addr",  7),
]
