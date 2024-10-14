import argparse
from amaranth import cli
from amaranth.back import rtlil, cxxrtl, verilog

from minerva.core import Minerva


__all__ = ["main"]


def main_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser()

    p_action = parser.add_subparsers(dest="action")

    p_generate = p_action.add_parser("generate",
            help="generate RTLIL, Verilog or CXXRTL from the design")
    p_generate.add_argument("-t", "--type",
            dest="generate_type", metavar="LANGUAGE", choices=["il", "cc", "v"],
            help="generate LANGUAGE (il for RTLIL, v for Verilog, cc for CXXRTL; "
                 "default: file extension of FILE, if given)")
    p_generate.add_argument("--no-src",
            dest="emit_src", default=True, action="store_false",
            help="suppress generation of source location attributes")
    p_generate.add_argument("generate_file",
            metavar="FILE", type=argparse.FileType("w"), nargs="?",
            help="write generated code to FILE")

    return parser


def main_runner(parser, args, design, name="top"):
    if args.action == "generate":
        generate_type = args.generate_type
        if generate_type is None and args.generate_file:
            if args.generate_file.name.endswith(".il"):
                generate_type = "il"
            if args.generate_file.name.endswith(".cc"):
                generate_type = "cc"
            if args.generate_file.name.endswith(".v"):
                generate_type = "v"
        if generate_type is None:
            parser.error("Unable to auto-detect language, specify explicitly with -t/--type")
        if generate_type == "il":
            output = rtlil.convert(design, name=name, emit_src=args.emit_src)
        if generate_type == "cc":
            output = cxxrtl.convert(design, name=name, emit_src=args.emit_src)
        if generate_type == "v":
            output = verilog.convert(design, name=name, emit_src=args.emit_src)
        if args.generate_file:
            args.generate_file.write(output)
        else:
            print(output)

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

    main_parser(parser)

    args = parser.parse_args()

    cpu = Minerva(args.reset_addr,
            args.with_icache, args.icache_nways, args.icache_nlines, args.icache_nwords,
            args.icache_base, args.icache_limit,
            args.with_dcache, args.dcache_nways, args.dcache_nlines, args.dcache_nwords,
            args.dcache_base, args.dcache_limit,
            args.wrbuf_depth,
            args.with_muldiv,
            args.with_rvfi)

    main_runner(parser, args, cpu, name="minerva_cpu")


if __name__ == "__main__":
    main()
