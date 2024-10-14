from amaranth import *
from amaranth.lib.wiring import In, Out

from .reg import FieldAction


__all__ = ["WPRI", "WARL", "WLRL"]


class WPRI(FieldAction):
    def __init__(self, shape):
        super().__init__(shape, access="wpri")

    def elaborate(self, platform):
        return Module()


class _WxRL(FieldAction):
    def __init__(self, shape, *, access, init=0):
        self._storage = Signal(shape, init=init)
        self._init    = init

        super().__init__(shape, access=access, members={
            "x_data": Out(shape),

            "m_data": Out(shape),
            "m_rdy":  In(1, init=1),

            "w_data": In(shape),
            "w_en":   In(1)
        })

    @property
    def init(self):
        return self._init

    @property
    def w_rvfi_wmask(self):
        return (self.port.w_wp_en | self.w_en).replicate(Value.cast(self.port.w_wp_data).width)

    @property
    def w_rvfi_wdata(self):
        return Mux(self.w_en, self.w_data, self.port.w_wp_data)

    def elaborate(self, platform):
        m = Module()

        m.d.comb += [
            self.x_data.eq(self._storage),
            self.port.x_rp_data.eq(self._storage),
        ]
        m.d.comb += [
            self.m_data.eq(self.port.m_wp_data),
            self.port.m_wp_rdy.eq(self.m_rdy),
        ]

        with m.If(self.w_en):
            m.d.sync += self._storage.eq(self.w_data)
        with m.If(self.port.w_wp_en):
            m.d.sync += self._storage.eq(self.port.w_wp_data)

        # m.d.comb += Assert(~(self.w_en & self.port.w_wp_en))

        return m


class WARL(_WxRL):
    def __init__(self, shape, *, init=0):
        super().__init__(shape, access="warl", init=init)


class WLRL(_WxRL):
    def __init__(self, shape, *, init=0):
        super().__init__(shape, access="wlrl", init=init)
