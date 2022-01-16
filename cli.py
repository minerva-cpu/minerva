import argparse
import warnings
from amaranth import cli

from minerva.core import Minerva


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("--reset-addr",
            type=lambda s: int(s, 16), default="0x00000000",
            help="reset vector address")

    parser.add_argument("--with-icache",
            default=False, action="store_true",
            help="enable the instruction cache")
    parser.add_argument("--with-dcache",
            default=False, action="store_true",
            help="enable the data cache")
    parser.add_argument("--with-muldiv",
            default=False, action="store_true",
            help="enable RV32M support")
    parser.add_argument("--with-debug",
            default=False, action="store_true",
            help="enable the Debug Module")
    parser.add_argument("--with-trigger",
            default=False, action="store_true",
            help="enable the Trigger Module")
    parser.add_argument("--with-rvfi",
            default=False, action="store_true",
            help="enable the riscv-formal interface")

    icache_group = parser.add_argument_group("icache options")
    icache_group.add_argument("--icache-nways",
            type=int, choices=[1, 2], default=1,
            help="number of ways")
    icache_group.add_argument("--icache-nlines",
            type=int, default=32,
            help="number of lines")
    icache_group.add_argument("--icache-nwords",
            type=int, choices=[4, 8, 16], default=4,
            help="number of words in a line")
    icache_group.add_argument("--icache-base",
            type=lambda s: int(s, 16), default="0x00000000",
            help="base address")
    icache_group.add_argument("--icache-limit",
            type=lambda s: int(s, 16), default="0x80000000",
            help="limit address")

    dcache_group = parser.add_argument_group("dcache options")
    dcache_group.add_argument("--dcache-nways",
            type=int, choices=[1, 2], default=1,
            help="number of ways")
    dcache_group.add_argument("--dcache-nlines",
            type=int, default=32,
            help="number of lines")
    dcache_group.add_argument("--dcache-nwords",
            type=int, choices=[4, 8, 16], default=4,
            help="number of words in a line")
    dcache_group.add_argument("--dcache-base",
            type=lambda s: int(s, 16), default="0x00000000",
            help="base address")
    dcache_group.add_argument("--dcache-limit",
            type=lambda s: int(s, 16), default="0x80000000",
            help="limit address")
    dcache_group.add_argument("--wrbuf-depth",
            type=int, default=8,
            help="write buffer depth")

    trigger_group = parser.add_argument_group("trigger options")
    trigger_group.add_argument("--nb-triggers",
            type=int, default=8,
            help="number of triggers")

    cli.main_parser(parser)

    args = parser.parse_args()

    if args.with_debug and not args.with_trigger:
        warnings.warn("Support for hardware breakpoints requires --with-trigger")

    cpu = Minerva(args.reset_addr,
            args.with_icache, args.icache_nways, args.icache_nlines, args.icache_nwords,
            args.icache_base, args.icache_limit,
            args.with_dcache, args.dcache_nways, args.dcache_nlines, args.dcache_nwords,
            args.dcache_base, args.dcache_limit,
            args.wrbuf_depth,
            args.with_muldiv,
            args.with_debug,
            args.with_trigger, args.nb_triggers,
            args.with_rvfi)

    ports = [
        cpu.external_interrupt, cpu.timer_interrupt, cpu.software_interrupt,
        cpu.ibus.ack, cpu.ibus.adr, cpu.ibus.bte, cpu.ibus.cti, cpu.ibus.cyc, cpu.ibus.dat_r,
        cpu.ibus.dat_w, cpu.ibus.sel, cpu.ibus.stb, cpu.ibus.we, cpu.ibus.err,
        cpu.dbus.ack, cpu.dbus.adr, cpu.dbus.bte, cpu.dbus.cti, cpu.dbus.cyc, cpu.dbus.dat_r,
        cpu.dbus.dat_w, cpu.dbus.sel, cpu.dbus.stb, cpu.dbus.we, cpu.dbus.err
    ]

    if args.with_debug:
        ports += [cpu.jtag.tck, cpu.jtag.tdi, cpu.jtag.tdo, cpu.jtag.tms]

    if args.with_rvfi:
        ports += [
            cpu.rvfi.valid, cpu.rvfi.order, cpu.rvfi.insn, cpu.rvfi.trap, cpu.rvfi.halt,
            cpu.rvfi.intr, cpu.rvfi.mode, cpu.rvfi.ixl, cpu.rvfi.rs1_addr, cpu.rvfi.rs2_addr,
            cpu.rvfi.rs1_rdata, cpu.rvfi.rs2_rdata, cpu.rvfi.rd_addr, cpu.rvfi.rd_wdata,
            cpu.rvfi.pc_rdata, cpu.rvfi.pc_wdata, cpu.rvfi.mem_addr, cpu.rvfi.mem_rmask,
            cpu.rvfi.mem_wmask, cpu.rvfi.mem_rdata, cpu.rvfi.mem_wdata
        ]

    cli.main_runner(parser, args, cpu, name="minerva_cpu", ports=ports)


if __name__ == "__main__":
    main()
