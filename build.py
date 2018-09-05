from nmigen.back import verilog

from minerva.core import Minerva


def main():
    cpu = Minerva()
    frag = cpu.get_fragment(platform=None)
    print(verilog.convert(frag, name="minerva_cpu", ports=(
        cpu.external_interrupt,
        cpu.ibus.ack,
        cpu.ibus.adr,
        cpu.ibus.bte,
        cpu.ibus.cti,
        cpu.ibus.cyc,
        cpu.ibus.dat_r,
        cpu.ibus.dat_w,
        cpu.ibus.sel,
        cpu.ibus.stb,
        cpu.ibus.we,
        cpu.dbus.ack,
        cpu.dbus.adr,
        cpu.dbus.bte,
        cpu.dbus.cti,
        cpu.dbus.cyc,
        cpu.dbus.dat_r,
        cpu.dbus.dat_w,
        cpu.dbus.sel,
        cpu.dbus.stb,
        cpu.dbus.we
    )))


if __name__ == "__main__":
    main()
