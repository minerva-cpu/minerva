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
        cpu.ibus.err,
        cpu.dbus.ack,
        cpu.dbus.adr,
        cpu.dbus.bte,
        cpu.dbus.cti,
        cpu.dbus.cyc,
        cpu.dbus.dat_r,
        cpu.dbus.dat_w,
        cpu.dbus.sel,
        cpu.dbus.stb,
        cpu.dbus.we,
        cpu.dbus.err
    ]
    if cpu.with_debug:
        ports += [
            cpu.jtag.tck,
            cpu.jtag.tdi,
            cpu.jtag.tdo,
            cpu.jtag.tms
        ]

    if cpu.with_rvfi:
        ports += [
            cpu.rvfi.valid,
            cpu.rvfi.order,
            cpu.rvfi.insn,
            cpu.rvfi.trap,
            cpu.rvfi.halt,
            cpu.rvfi.intr,
            cpu.rvfi.mode,
            cpu.rvfi.ixl,
            cpu.rvfi.rs1_addr,
            cpu.rvfi.rs2_addr,
            cpu.rvfi.rs1_rdata,
            cpu.rvfi.rs2_rdata,
            cpu.rvfi.rd_addr,
            cpu.rvfi.rd_wdata,
            cpu.rvfi.pc_rdata,
            cpu.rvfi.pc_wdata,
            cpu.rvfi.mem_addr,
            cpu.rvfi.mem_rmask,
            cpu.rvfi.mem_wmask,
            cpu.rvfi.mem_rdata,
            cpu.rvfi.mem_wdata,
        ]

    frag = cpu.elaborate(platform=None)
    print(verilog.convert(frag, name="minerva_cpu", ports=ports))


if __name__ == "__main__":
    main()
