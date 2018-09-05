from nmigen import *
from nmigen.hdl.rec import *


class Cycle:
    CLASSIC   = 0
    CONSTANT  = 1
    INCREMENT = 2
    END       = 7


wishbone_layout = [
    ("adr",   30, DIR_FANOUT),
    ("dat_w", 32, DIR_FANOUT),
    ("dat_r", 32, DIR_FANIN),
    ("sel",    4, DIR_FANOUT),
    ("cyc",    1, DIR_FANOUT),
    ("stb",    1, DIR_FANOUT),
    ("ack",    1, DIR_FANIN),
    ("we",     1, DIR_FANOUT),
    ("cti",    3, DIR_FANOUT),
    ("bte",    2, DIR_FANOUT),
    ("err",    1, DIR_FANIN)
]
