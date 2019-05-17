from nmigen.back import verilog

from minerva.core import Minerva


def main():
    cpu = Minerva(as_instance=True, with_icache=False, with_dcache=False, with_muldiv=False)
    ports = [
        cpu.clk,
        cpu.rst,
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
    ]
    if cpu.with_debug:
        ports += [
            cpu.jtag.tck,
            cpu.jtag.tdi,
            cpu.jtag.tdo,
            cpu.jtag.tms
        ]

    frag = cpu.elaborate(platform=None)
    print(verilog.convert(frag, name="minerva_cpu", ports=ports))


if __name__ == "__main__":
    main()
