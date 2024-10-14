from collections.abc import Mapping
import enum

from amaranth import *
from amaranth.hdl import ShapeLike
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from amaranth_soc.memory import MemoryMap


__all__ = ["FieldPort", "FieldAction", "Field", "Register", "RegisterBank", "RegisterFile"]


class FieldPort(wiring.PureInterface):
    class Access(enum.Enum):
        WPRI = "wpri"
        WARL = "warl"
        WLRL = "wlrl"

    class Signature(wiring.Signature):
        def __init__(self, shape, access):
            if not isinstance(shape, ShapeLike):
                raise TypeError("Field shape must be a shape-like object, not {shape!r}")

            self._shape  = shape
            self._access = FieldPort.Access(access)

            super().__init__({
                "x_rp_data": In(shape),

                "m_wp_data": Out(shape),
                "m_wp_rdy":  In(1),

                "w_wp_data": Out(shape),
                "w_wp_en":   Out(1),
            })

        def create(self, *, path=None, src_loc_at=0):
            return FieldPort(self, path=path, src_loc_at=1 + src_loc_at)

        def __eq__(self, other):
            return (isinstance(other, FieldPort.Signature) and
                    Shape.cast(self._shape) == Shape.cast(other._shape) and
                    self._access == other._access)

    def __init__(self, signature, *, path=None, src_loc_at=0):
        if not isinstance(signature, FieldPort.Signature):
            raise TypeError(f"Signature must be a FieldPort.Signature, not {signature!r}")
        super().__init__(signature, path=path, src_loc_at=1 + src_loc_at)

    @property
    def shape(self):
        return self.signature._shape

    @property
    def access(self):
        return self.signature._access


class FieldAction(wiring.Component):
    def __init__(self, shape, access, members=()):
        members = dict(members)
        if "port" in members:
            raise ValueError(f"'port' is a reserved name, which cannot be assigned to member "
                             f"{members['port']!r}")

        super().__init__({
            "port": In(FieldPort.Signature(shape, access)),
            **members,
        })

    @property
    def w_rvfi_wmask(self):
        return self.port.w_wp_en.replicate(Value.cast(self.port.w_wp_data).width)

    @property
    def w_rvfi_wdata(self):
        return self.port.w_wp_data


class Field:
    def __init__(self, action_cls, *args, **kwargs):
        if not issubclass(action_cls, FieldAction):
            raise TypeError(f"{action_cls.__qualname__} must be a subclass of FieldAction")

        self._action_cls = action_cls
        self._args       = args
        self._kwargs     = kwargs

    def create(self):
        return self._action_cls(*self._args, **self._kwargs)


class _FieldActionMap(Mapping):
    def __init__(self, fields):
        if not isinstance(fields, dict):
            raise TypeError(f"Fields must be a dict, not {fields!r}")

        self._actions = {}
        for name, field in fields.items():
            if not (isinstance(name, str) and name):
                raise TypeError(f"Field name must be a non-empty string, not {name!r}")
            if not isinstance(field, Field):
                raise TypeError(f"Field {name} must be an instance of Field, not {field!r}")
            self._actions[name] = field.create()

        super().__init__()

    def __getitem__(self, key):
        return self._actions[key]

    def __getattr__(self, name):
        try:
            item = self[name]
        except KeyError as e:
            raise AttributeError(f"Field name {name} was not found; did you mean one of: "
                                 f"{', '.join(self.keys())}?") from e
        return item

    def __iter__(self):
        yield from self._actions

    def __len__(self):
        return len(self._actions)


class Register(wiring.Component):
    x_rp_data: Out(32)

    m_wp_data: In(32)
    m_wp_rdy:  Out(1)
    m_wp_err:  Out(1)

    w_wp_data: In(32)
    w_wp_en:   In(1)

    def __init__(self, fields=None):
        if hasattr(self, "__annotations__"):
            annot_fields = dict()
            for key, value in self.__annotations__.items():
                if isinstance(value, Field):
                    annot_fields[key] = value
            if annot_fields:
                if fields is not None:
                    raise ValueError(f"Field arguments are mutually exclusive with field "
                                     f"annotations: {' '.join(annot_fields)}")
                fields = annot_fields

        if isinstance(fields, dict):
            self._field = _FieldActionMap(fields)
        elif isinstance(fields, Field):
            self._field = fields.create()
        else:
            raise TypeError("Field collection must be a dict or a Field object, not {fields!r}")

        if width := sum(Shape.cast(field.port.shape).width for _, field in self) != 32:
            raise ValueError("Register width must be 32 bits, not {width}")

        super().__init__()

    @property
    def field(self):
        return self._field

    @property
    def f(self):
        return self._field

    @property
    def x_rvfi_rdata(self):
        return self.x_rp_data

    @property
    def w_rvfi_wmask(self):
        return Cat(field.w_rvfi_wmask for field_name, field in self)

    @property
    def w_rvfi_wdata(self):
        return Cat(field.w_rvfi_wdata for field_name, field in self)

    def __iter__(self):
        if isinstance(self._field, FieldAction):
            yield None, self._field
        else:
            yield from self._field.items()

    def elaborate(self, platform):
        m = Module()

        field_start  = 0
        m_wp_rdy_any = 0
        m_wp_err_any = 0

        for field_name, field in self:
            field_width = Shape.cast(field.port.shape).width
            field_slice = slice(field_start, field_start + field_width)

            m.submodules[field_name or "$field"] = field

            if field.port.access != FieldPort.Access.WPRI:
                m.d.comb += [
                    self.x_rp_data[field_slice].eq(field.port.x_rp_data),
                    field.port.m_wp_data.eq(self.m_wp_data[field_slice]),
                    field.port.w_wp_data.eq(self.w_wp_data[field_slice]),
                    field.port.w_wp_en.eq(self.w_wp_en),
                ]
                m_wp_rdy_any |= field.port.m_wp_rdy

            if field.port.access == FieldPort.Access.WLRL:
                m_wp_err_any |= ~field.port.m_wp_rdy

            field_start = field_slice.stop

        m.d.comb += [
            self.m_wp_rdy.eq(m_wp_rdy_any),
            self.m_wp_err.eq(m_wp_err_any),
        ]

        return m


class RegisterBank(wiring.Component):
    def __init__(self, *, addr_width):
        self._memory_map = MemoryMap(addr_width=addr_width, data_width=32)
        self._addr_width = addr_width

        super().__init__({
            "d_addr":    In(addr_width),
            "d_ready":   In(1),

            "x_rp_data": Out(32),
            "x_ready":   In(1),

            "m_wp_data": In(32),
            "m_wp_rdy":  Out(1),
            "m_wp_err":  Out(1),
            "m_ready":   In(1),

            "w_wp_data": In(32),
            "w_wp_en":   In(1),
        })

    @property
    def memory_map(self):
        self._memory_map.freeze()
        return self._memory_map

    @property
    def addr_width(self):
        return self._addr_width

    def add(self, name, reg, *, addr):
        if not isinstance(reg, Register):
            raise TypeError(f"Register must be an instance of Register, not {reg!r}")

        self._memory_map.add_resource(reg, addr=addr, name=name, size=1)
        return reg

    def elaborate(self, platform):
        m = Module()

        x_rp_data_mux = 0
        m_wp_rdy_mux  = 0
        m_wp_err_mux  = 0

        for reg, reg_name, (reg_addr, _) in self.memory_map.resources():
            assert isinstance(reg, Register)

            m.submodules["_".join(reg_name)] = reg

            reg_d_select = Signal(name=f"{'_'.join(reg_name)}_d_select")
            reg_x_select = Signal(name=f"{'_'.join(reg_name)}_x_select")
            reg_m_select = Signal(name=f"{'_'.join(reg_name)}_m_select")
            reg_w_select = Signal(name=f"{'_'.join(reg_name)}_w_select")

            m.d.comb += reg_d_select.eq(self.d_addr == reg_addr)

            with m.If(self.d_ready):
                m.d.sync += reg_x_select.eq(reg_d_select)
            with m.If(self.x_ready):
                m.d.sync += reg_m_select.eq(reg_x_select)
            with m.If(self.m_ready):
                m.d.sync += reg_w_select.eq(reg_m_select)

            x_rp_data_mux |= Mux(reg_x_select, reg.x_rp_data, 0)
            m_wp_rdy_mux  |= Mux(reg_m_select, reg.m_wp_rdy,  0)
            m_wp_err_mux  |= Mux(reg_m_select, reg.m_wp_err,  0)

            m.d.comb += [
                reg.m_wp_data.eq(self.m_wp_data),
                reg.w_wp_data.eq(self.w_wp_data),
                reg.w_wp_en  .eq(self.w_wp_en & reg_w_select),
            ]

        m.d.comb += [
            self.x_rp_data.eq(x_rp_data_mux),
            self.m_wp_rdy .eq(m_wp_rdy_mux),
            self.m_wp_err .eq(m_wp_err_mux),
        ]

        return m


class RegisterFile(wiring.Component):
    d_addr:    In(12)
    d_ready:   In(1)

    x_rp_data: Out(32)
    x_ready:   In(1)

    m_wp_data: In(32)
    m_wp_rdy:  Out(1)
    m_wp_err:  Out(1)
    m_ready:   In(1)

    w_wp_data: In(32)
    w_wp_en:   In(1)

    def __init__(self):
        self._memory_map = MemoryMap(addr_width=12, data_width=32)
        self._banks      = dict()

        super().__init__()

    @property
    def memory_map(self):
        self._memory_map.freeze()
        return self._memory_map

    def add(self, bank, *, addr):
        if not isinstance(bank, RegisterBank):
            raise TypeError(f"Bank must be an instance of RegisterBank, not {bank!r}")

        self._memory_map.add_window(bank._memory_map, addr=addr, name=("bank", f"{addr:03x}"))
        self._banks[bank.memory_map] = bank

    def elaborate(self, platform):
        m = Module()

        x_rp_data_mux = 0
        m_wp_rdy_mux  = 0
        m_wp_err_mux  = 0

        for window, bank_name, (bank_pattern, ratio) in self.memory_map.window_patterns():
            bank = self._banks[window]

            assert isinstance(bank, RegisterBank)
            assert bank._memory_map is window
            assert ratio == 1

            bank_d_select = Signal(name=f"{'_'.join(bank_name)}_d_select")
            bank_x_select = Signal(name=f"{'_'.join(bank_name)}_x_select")
            bank_m_select = Signal(name=f"{'_'.join(bank_name)}_m_select")
            bank_w_select = Signal(name=f"{'_'.join(bank_name)}_w_select")

            m.d.comb += bank_d_select.eq(self.d_addr.matches(bank_pattern))

            with m.If(self.d_ready):
                m.d.sync += bank_x_select.eq(bank_d_select)
            with m.If(self.x_ready):
                m.d.sync += bank_m_select.eq(bank_x_select)
            with m.If(self.m_ready):
                m.d.sync += bank_w_select.eq(bank_m_select)

            m.d.comb += [
                bank.d_addr .eq(self.d_addr[:bank.addr_width]),
                bank.d_ready.eq(self.d_ready),
                bank.x_ready.eq(self.x_ready),
                bank.m_ready.eq(self.m_ready),
            ]

            x_rp_data_mux |= Mux(bank_x_select, bank.x_rp_data, 0)
            m_wp_rdy_mux  |= Mux(bank_m_select, bank.m_wp_rdy,  0)
            m_wp_err_mux  |= Mux(bank_m_select, bank.m_wp_err,  0)

            m.d.comb += [
                bank.m_wp_data.eq(self.m_wp_data),
                bank.w_wp_data.eq(self.w_wp_data),
                bank.w_wp_en  .eq(self.w_wp_en & bank_w_select),
            ]

        m.d.comb += [
            self.x_rp_data.eq(x_rp_data_mux),
            self.m_wp_rdy .eq(m_wp_rdy_mux),
            self.m_wp_err .eq(m_wp_err_mux),
        ]

        return m
