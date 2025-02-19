from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.data import StructLayout
from amaranth.lib.memory import Memory
from amaranth.lib.wiring import In, Out


__all__ = ["RegisterBypass", "RegisterFile"]


class RegisterBypass(wiring.Component):
    d_rp_addr:  In(5)
    d_rp_raw:   Out(1)
    d_rp_rdy:   Out(1)
    d_rp_data:  Out(32)

    x_wp_addr:  In(5)
    x_wp_en:    In(1)
    x_wp_rdy:   In(1)
    x_wp_data:  In(32)

    m_wp_addr:  In(5)
    m_wp_en:    In(1)
    m_wp_rdy:   In(1)
    m_wp_data:  In(32)

    w_wp_addr:  In(5)
    w_wp_en:    In(1)
    w_wp_data:  In(32)

    def elaborate(self, platform):
        m = Module()

        d_rp_raw = Signal(StructLayout({"d": 1, "x": 1, "m": 1, "w": 1}))
        d_rp_sel = Signal.like(d_rp_raw)
        d_rp_rdy = Signal.like(d_rp_raw)

        m.d.comb += [
            d_rp_raw.d.eq(self.d_rp_addr == 0),
            d_rp_raw.x.eq(self.x_wp_en & (self.d_rp_addr == self.x_wp_addr)),
            d_rp_raw.m.eq(self.m_wp_en & (self.d_rp_addr == self.m_wp_addr)),
            d_rp_raw.w.eq(self.w_wp_en & (self.d_rp_addr == self.w_wp_addr)),

            d_rp_sel.eq(d_rp_raw.as_value() & (-d_rp_raw.as_value())), # isolate rightmost 1-bit

            d_rp_rdy.d.eq(d_rp_sel.d),
            d_rp_rdy.x.eq(d_rp_sel.x & self.x_wp_rdy),
            d_rp_rdy.m.eq(d_rp_sel.m & self.m_wp_rdy),
            d_rp_rdy.w.eq(d_rp_sel.w),
        ]

        d_rp_data_mux  = 0
        d_rp_data_mux |= Mux(d_rp_sel.x, self.x_wp_data, 0)
        d_rp_data_mux |= Mux(d_rp_sel.m, self.m_wp_data, 0)
        d_rp_data_mux |= Mux(d_rp_sel.w, self.w_wp_data, 0)

        m.d.comb += [
            self.d_rp_raw .eq(d_rp_raw.as_value().any()),
            self.d_rp_rdy .eq(d_rp_rdy.as_value().any()),
            self.d_rp_data.eq(d_rp_data_mux),
        ]

        return m


class RegisterFile(wiring.Component):
    d_rp1_addr: In(5)
    d_rp1_rdy:  Out(1)
    d_rp2_addr: In(5)
    d_rp2_rdy:  Out(1)
    d_ready:    In(1)

    x_rp1_data: Out(32)
    x_rp2_data: Out(32)
    x_wp_addr:  In(5)
    x_wp_en:    In(1)
    x_wp_rdy:   In(1)
    x_wp_data:  In(32)

    m_wp_addr:  In(5)
    m_wp_en:    In(1)
    m_wp_rdy:   In(1)
    m_wp_data:  In(32)

    w_wp_addr:  In(5)
    w_wp_en:    In(1)
    w_wp_data:  In(32)

    def elaborate(self, platform):
        m = Module()

        m.submodules.bypass1 = bypass1 = RegisterBypass()
        m.submodules.bypass2 = bypass2 = RegisterBypass()

        m.d.comb += [
            bypass1.d_rp_addr.eq(self.d_rp1_addr),
            bypass2.d_rp_addr.eq(self.d_rp2_addr),
        ]

        for bypass in (bypass1, bypass2):
            m.d.comb += [
                bypass.x_wp_addr.eq(self.x_wp_addr),
                bypass.x_wp_en  .eq(self.x_wp_en),
                bypass.x_wp_rdy .eq(self.x_wp_rdy),
                bypass.x_wp_data.eq(self.x_wp_data),

                bypass.m_wp_addr.eq(self.m_wp_addr),
                bypass.m_wp_en  .eq(self.m_wp_en),
                bypass.m_wp_rdy .eq(self.m_wp_rdy),
                bypass.m_wp_data.eq(self.m_wp_data),

                bypass.w_wp_addr.eq(self.w_wp_addr),
                bypass.w_wp_en  .eq(self.w_wp_en),
                bypass.w_wp_data.eq(self.w_wp_data),
            ]

        m.d.comb += [
            self.d_rp1_rdy.eq(~bypass1.d_rp_raw | bypass1.d_rp_rdy),
            self.d_rp2_rdy.eq(~bypass2.d_rp_raw | bypass2.d_rp_rdy),
        ]

        m.submodules.mem = mem = Memory(shape=unsigned(32), depth=32, init=[0] * 32)

        mem_wp  = mem.write_port()
        mem_rp1 = mem.read_port()
        mem_rp2 = mem.read_port()

        m.d.comb += [
            mem_wp.addr.eq(self.w_wp_addr),
            mem_wp.en  .eq(self.w_wp_en),
            mem_wp.data.eq(self.w_wp_data),

            mem_rp1.addr.eq(self.d_rp1_addr),
            mem_rp1.en  .eq(self.d_ready),
            mem_rp2.addr.eq(self.d_rp2_addr),
            mem_rp2.en  .eq(self.d_ready),
        ]

        x_bypass1_raw  = Signal()
        x_bypass1_data = Signal(32)
        x_bypass2_raw  = Signal()
        x_bypass2_data = Signal(32)

        with m.If(self.d_ready):
            m.d.sync += [
                x_bypass1_raw .eq(bypass1.d_rp_raw),
                x_bypass1_data.eq(bypass1.d_rp_data),
                x_bypass2_raw .eq(bypass2.d_rp_raw),
                x_bypass2_data.eq(bypass2.d_rp_data),
            ]

        m.d.comb += [
            self.x_rp1_data.eq(Mux(x_bypass1_raw, x_bypass1_data, mem_rp1.data)),
            self.x_rp2_data.eq(Mux(x_bypass2_raw, x_bypass2_data, mem_rp2.data)),
        ]

        return m
