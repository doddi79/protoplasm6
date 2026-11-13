__all__ = [
    'DirectConverter',
]
import enum
import threading

from google.protobuf import descriptor as _descriptor
from google.protobuf import json_format
from google.protobuf import message_factory

from protoplasm6.structs import *
from protoplasm6.structs import _oneofs
from protoplasm6.casting import dictators
from protoplasm6.casting.converters._base import *

import logging
log = logging.getLogger(__name__)

_FD = _descriptor.FieldDescriptor


class _Container(enum.Enum):
    SINGLE = 'single'
    LIST = 'list'
    MAP = 'map'


class _Kind(enum.Enum):
    SCALAR = 'scalar'
    ENUM = 'enum'
    NULL = 'null'  # google.protobuf.NullValue (an enum)
    MESSAGE = 'message'  # Another protoplasm6 dataclass
    TIMESTAMP = 'timestamp'
    DURATION = 'duration'
    ANY = 'any'
    JSON = 'json'  # google.protobuf.Struct, Value & ListValue


_JSON_TYPES = {'google.protobuf.Struct', 'google.protobuf.Value', 'google.protobuf.ListValue'}

# The dictators each kind of field is expected to have in generated code. Any
# other dictator (e.g. a custom one) makes the field fall back to the
# DictConverter logic so its dictator gets used.
_EXPECTED_DICTATORS = {
    _Kind.SCALAR: (dictators.BaseDictator, dictators.LongDictator, dictators.ByteDictator),
    _Kind.ENUM: (dictators.BaseDictator, dictators.EnumDictator),
    _Kind.NULL: (dictators.BaseDictator, dictators.NullValueDictator),
    _Kind.MESSAGE: (dictators.BaseDictator,),
    _Kind.TIMESTAMP: (dictators.TimestampDictator,),
    _Kind.DURATION: (dictators.DurationDictator,),
    _Kind.ANY: (dictators.AnyDictator,),
    _Kind.JSON: (dictators.BaseDictator, dictators.StructDictator, dictators.ValueDictator,
                 dictators.ListValueDictator),
}

_INT_CPP_TYPES = {_FD.CPPTYPE_INT32, _FD.CPPTYPE_INT64, _FD.CPPTYPE_UINT32, _FD.CPPTYPE_UINT64}
_FLOAT_CPP_TYPES = {_FD.CPPTYPE_FLOAT, _FD.CPPTYPE_DOUBLE}


class _FieldPlan:
    """Everything needed to convert one field, worked out once per dataclass
    type (so the per-object conversion does as little thinking as possible).
    """
    __slots__ = ('dc_name', 'pb_name', 'fd', 'container', 'kind', 'value_fd', 'key_fd',
                 'value_type', 'enum_by_name', 'has_presence', 'default', 'oneof')

    def __init__(self, dc_name: str, pb_name: str, fd: _FD):
        self.dc_name = dc_name
        self.pb_name = pb_name
        self.fd = fd
        self.container = _Container.SINGLE
        self.kind = _Kind.SCALAR
        self.value_fd = fd
        self.key_fd = None
        self.value_type = None  # Dataclass or Enum type (or None for raw values)
        self.enum_by_name = None
        self.has_presence = fd.has_presence
        self.default = fd.default_value if not fd.is_repeated else None
        self.oneof = _oneofs.real_oneof_name(fd)


class _Plan:
    __slots__ = ('dataclass_type', 'proto_cls', 'fields', 'fallback_fields')

    def __init__(self, dataclass_type: Type[DataclassBase]):
        self.dataclass_type = dataclass_type
        self.proto_cls = dataclass_type.__proto_cls__
        self.fields: List[_FieldPlan] = []
        self.fallback_fields: List[dataclasses.Field] = []


class DirectConverter(BaseConverter):
    """Converts directly between protobuf message objects and protoplasm6
    dataclasses by walking the fields of both (using only the public protobuf
    message API), without going through dicts and `json_format` like the
    `DictConverter` does.

    The conversion "plan" for each dataclass type is worked out the first time
    it's converted and cached.

    Fields this converter doesn't know how to handle directly (e.g. fields
    with custom dictators or message types that have no protoplasm6
    dataclass) fall back to the `DictConverter` logic for that field only.

    Behavioural differences from the `DictConverter` (which are all bug fixes
    really):

    - Map keys keep their proper type (e.g. `Dict[int, str]` maps get `int`
      keys, where the `DictConverter` gives `str` keys since JSON object keys
      are always strings) and `bool` keyed maps work
    - Timezone aware `datetime` values are correctly converted to UTC (the
      `DictConverter` ignores their timezone)
    - `Duration` and `Timestamp` values keep their full (microsecond)
      precision
    """
    name = 'direct'

    def __init__(self):
        self._plans: Dict[type, _Plan] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ plans

    def _get_plan(self, dataclass_type: Type[DataclassBase]) -> _Plan:
        plan = self._plans.get(dataclass_type)
        if plan is None:
            with self._lock:
                plan = self._plans.get(dataclass_type)
                if plan is None:
                    plan = self._build_plan(dataclass_type)
                    self._plans[dataclass_type] = plan
        return plan

    def clear_cache(self):
        """Clears the cached conversion plans (e.g. after reloading modules)"""
        with self._lock:
            self._plans.clear()

    def _build_plan(self, dataclass_type: Type[DataclassBase]) -> _Plan:
        plan = _Plan(dataclass_type)
        fields_by_name = plan.proto_cls.DESCRIPTOR.fields_by_name
        for field in dataclasses.fields(dataclass_type):
            pb_name = field.metadata.get('pb_name', field.name)
            fd = fields_by_name.get(pb_name)
            if fd is None:  # Not a protobuf field (shouldn't happen in generated code)
                continue
            try:
                field_plan = self._build_field_plan(field, pb_name, fd, dataclass_type)
            except Exception as ex:  # noqa
                log.debug('DirectConverter falling back to dict conversion for %s.%s: %r',
                          dataclass_type.__name__, field.name, ex)
                field_plan = None
            if field_plan is None:
                plan.fallback_fields.append(field)
            else:
                plan.fields.append(field_plan)
        return plan

    @staticmethod
    def _build_field_plan(field: dataclasses.Field, pb_name: str, fd: _FD,
                          dataclass_type: Type[DataclassBase]) -> Optional[_FieldPlan]:
        from protoplasm6.casting import castutils
        fp = _FieldPlan(field.name, pb_name, fd)

        if fd.type == _FD.TYPE_MESSAGE and fd.message_type.GetOptions().map_entry:
            fp.container = _Container.MAP
            fp.key_fd = fd.message_type.fields_by_name['key']
            fp.value_fd = fd.message_type.fields_by_name['value']
        elif fd.is_repeated:
            fp.container = _Container.LIST

        vfd = fp.value_fd
        if vfd.type == _FD.TYPE_GROUP:
            return None
        elif vfd.type == _FD.TYPE_MESSAGE:
            full_name = vfd.message_type.full_name
            if full_name == 'google.protobuf.Timestamp':
                fp.kind = _Kind.TIMESTAMP
            elif full_name == 'google.protobuf.Duration':
                fp.kind = _Kind.DURATION
            elif full_name == 'google.protobuf.Any':
                fp.kind = _Kind.ANY
            elif full_name in _JSON_TYPES:
                fp.kind = _Kind.JSON
            else:
                if not field.metadata.get('is_obj', False):
                    return None
                fp.kind = _Kind.MESSAGE
                fp.value_type = castutils.get_dc_field_obj_type(field, dataclass_type)
                if not (isinstance(fp.value_type, type) and issubclass(fp.value_type, DataclassBase)):
                    return None
        elif vfd.type == _FD.TYPE_ENUM:
            if vfd.enum_type.full_name == 'google.protobuf.NullValue':
                fp.kind = _Kind.NULL
            else:
                fp.kind = _Kind.ENUM
                fp.enum_by_name = {v.name: v.number for v in vfd.enum_type.values}
                if field.metadata.get('dictator', dictators.BaseDictator) is dictators.EnumDictator:
                    fp.value_type = castutils.get_dc_field_obj_type(field, dataclass_type)
        else:
            fp.kind = _Kind.SCALAR

        dictator = field.metadata.get('dictator', dictators.BaseDictator)
        if dictator not in _EXPECTED_DICTATORS[fp.kind]:
            return None  # Custom dictator... let it do its thing via the dict logic

        return fp

    # ------------------------------------------------------ dataclass -> proto

    def dataclass_to_proto(self, dc: DataclassBase) -> GeneratedProtocolMessageType:
        proto = dc.__proto_cls__()
        self._fill_proto(proto, dc)
        return proto

    def _fill_proto(self, proto, dc: DataclassBase):
        plan = self._get_plan(type(dc))

        if plan.fallback_fields:
            from protoplasm6.casting.dictator import _dataclass_field_to_dict_field  # noqa
            d = {}
            for field in plan.fallback_fields:
                dicted = _dataclass_field_to_dict_field(field, dc)
                if dicted is not ...:
                    d[field.metadata.get('pb_name', field.name)] = dicted
            json_format.ParseDict(d, proto)

        oneofs_set = None
        for fp in plan.fields:
            val = getattr(dc, fp.dc_name)
            if val is ...:  # The "unset" sentinel (e.g. for google.protobuf.Value fields)
                continue

            if fp.oneof is not None:
                # Generated dataclasses give oneof members default values
                # (e.g. '' and 0) so only members with non-default values
                # count as the one that's "set"
                if val is None or (fp.kind is not _Kind.MESSAGE and fp.default is not None and val == fp.default):
                    continue
                if oneofs_set is None:
                    oneofs_set = {}
                if fp.oneof in oneofs_set:
                    raise ValueError(f'{type(dc).__name__} has multiple "{fp.oneof}" oneof fields set '
                                     f'({oneofs_set[fp.oneof]!r} and {fp.dc_name!r})')
                oneofs_set[fp.oneof] = fp.dc_name
            if val is None:
                if fp.kind is _Kind.JSON and fp.container is _Container.SINGLE \
                        and fp.value_fd.message_type.full_name == 'google.protobuf.Value':
                    getattr(proto, fp.pb_name).null_value = 0  # Same as ParseDict does with None
                continue

            if fp.container is _Container.SINGLE:
                if fp.kind is _Kind.SCALAR or fp.kind is _Kind.ENUM or fp.kind is _Kind.NULL:
                    self._set_scalar(proto, fp, self._to_proto_scalar(fp, val))
                else:
                    sub = getattr(proto, fp.pb_name)
                    sub.SetInParent()
                    self._fill_message_value(sub, fp, val)

            elif fp.container is _Container.LIST:
                if not val:
                    continue
                container = getattr(proto, fp.pb_name)
                if fp.kind is _Kind.SCALAR or fp.kind is _Kind.ENUM or fp.kind is _Kind.NULL:
                    vals = [self._to_proto_scalar(fp, v) for v in val]
                    try:
                        container.extend(vals)
                    except (TypeError, ValueError):
                        container.extend([self._coerce(fp.value_fd, v) for v in vals])
                else:
                    for v in val:
                        self._fill_message_value(container.add(), fp, v)

            else:  # MAP
                if not val:
                    continue
                container = getattr(proto, fp.pb_name)
                for k, v in val.items():
                    try:
                        k = self._check_key(fp.key_fd, k)
                    except (TypeError, ValueError):
                        k = self._coerce(fp.key_fd, k)
                    if fp.kind is _Kind.SCALAR or fp.kind is _Kind.ENUM or fp.kind is _Kind.NULL:
                        v = self._to_proto_scalar(fp, v)
                        try:
                            container[k] = v
                        except (TypeError, ValueError):
                            container[k] = self._coerce(fp.value_fd, v)
                    else:
                        self._fill_message_value(container[k], fp, v)

    def _fill_message_value(self, sub, fp: _FieldPlan, val: Any):
        kind = fp.kind
        if kind is _Kind.MESSAGE:
            if not isinstance(val, fp.value_type):
                from protoplasm6.casting.castutils import force_object
                val = force_object(fp.value_type, val)
            self._fill_proto(sub, val)
        elif kind is _Kind.TIMESTAMP:
            sub.FromDatetime(val)
        elif kind is _Kind.DURATION:
            sub.FromTimedelta(val)
        elif kind is _Kind.ANY:
            sub.Pack(self.dataclass_to_proto(val))
        else:  # JSON
            if val is None:  # Only possible in lists/maps of Values
                sub.null_value = 0
            else:
                json_format.ParseDict(val, sub)

    @staticmethod
    def _to_proto_scalar(fp: _FieldPlan, val: Any) -> Any:
        if fp.kind is _Kind.ENUM:
            if isinstance(val, str):
                return fp.enum_by_name[val]
            return int(val)
        if fp.kind is _Kind.NULL:
            return 0
        return val

    def _set_scalar(self, proto, fp: _FieldPlan, val: Any):
        try:
            setattr(proto, fp.pb_name, val)
        except (TypeError, ValueError):
            setattr(proto, fp.pb_name, self._coerce(fp.value_fd, val))

    @staticmethod
    def _check_key(key_fd: _FD, key: Any) -> Any:
        # Map containers happily accept a bool for an int key (and vice versa)
        # in some protobuf implementations, so we make sure here
        if key_fd.cpp_type == _FD.CPPTYPE_BOOL and not isinstance(key, bool):
            raise TypeError('bool key expected')
        if key_fd.cpp_type in _INT_CPP_TYPES and isinstance(key, str):
            raise TypeError('int key expected')
        return key

    @staticmethod
    def _coerce(fd: _FD, val: Any) -> Any:
        """Lenient casting of values protobuf won't take as is, but which the
        `json_format.ParseDict` used by the `DictConverter` accepts (e.g.
        string ints, which is how map keys come out of the `DictConverter`).
        """
        cpp_type = fd.cpp_type
        if cpp_type in _INT_CPP_TYPES:
            if isinstance(val, float) and not val.is_integer():
                raise ValueError(f'Can not convert non-integer {val!r} for field {fd.full_name}')
            return int(val)
        if cpp_type in _FLOAT_CPP_TYPES:
            return float(val)
        if cpp_type == _FD.CPPTYPE_BOOL:
            if isinstance(val, str):
                if val.lower() in ('true', '1'):
                    return True
                if val.lower() in ('false', '0'):
                    return False
                raise ValueError(f'Can not convert {val!r} to bool for field {fd.full_name}')
            return bool(val)
        if cpp_type == _FD.CPPTYPE_ENUM and isinstance(val, str):
            return fd.enum_type.values_by_name[val].number
        raise TypeError(f'Can not convert {type(val)} value {val!r} for field {fd.full_name}')

    # ------------------------------------------------------ proto -> dataclass

    def proto_to_dataclass(self, proto: GeneratedProtocolMessageType,
                           dataclass_type: Optional[Type[T_DCB]] = None) -> T_DCB:
        if dataclass_type is None:
            from protoplasm6.casting.castutils import import_dataclass_by_proto
            dataclass_type = import_dataclass_by_proto(proto.__class__)
        elif proto.DESCRIPTOR is not dataclass_type.__proto_cls__.DESCRIPTOR:
            # Casting a proto into a "foreign" dataclass... the dict logic
            # handles that by field names so let's leave that to it
            from protoplasm6.casting.converters._dict import DictConverter
            return DictConverter().proto_to_dataclass(proto, dataclass_type)
        return self._to_dataclass(proto, dataclass_type)

    def _to_dataclass(self, proto, dataclass_type: Type[T_DCB]) -> T_DCB:
        plan = self._get_plan(dataclass_type)
        kwargs = {}

        if plan.fallback_fields:
            from protoplasm6.casting.dictator import proto_to_dict
            from protoplasm6.casting.objectifier import _dict_value_to_field_value  # noqa
            d = proto_to_dict(proto)
            for field in plan.fallback_fields:
                pb_name = field.metadata.get('pb_name', field.name)
                if pb_name in d:
                    kwargs[field.name] = _dict_value_to_field_value(field, d[pb_name], dataclass_type)

        for fp in plan.fields:
            if fp.container is _Container.SINGLE:
                if fp.has_presence:
                    if not proto.HasField(fp.pb_name):
                        continue
                    val = getattr(proto, fp.pb_name)
                else:
                    val = getattr(proto, fp.pb_name)
                    if val == fp.default:
                        continue  # Unset (as far as proto3 is concerned) so we leave the dataclass default

                kind = fp.kind
                if kind is _Kind.SCALAR:
                    kwargs[fp.dc_name] = val
                elif kind is _Kind.ENUM:
                    kwargs[fp.dc_name] = fp.value_type(val) if fp.value_type else val
                elif kind is _Kind.NULL:
                    kwargs[fp.dc_name] = None
                else:
                    kwargs[fp.dc_name] = self._from_message_value(fp, val)

            elif fp.container is _Container.LIST:
                container = getattr(proto, fp.pb_name)
                if not container:
                    continue
                kind = fp.kind
                if kind is _Kind.SCALAR:
                    kwargs[fp.dc_name] = list(container)
                elif kind is _Kind.ENUM:
                    kwargs[fp.dc_name] = [fp.value_type(v) for v in container] if fp.value_type else list(container)
                elif kind is _Kind.NULL:
                    kwargs[fp.dc_name] = [None] * len(container)
                else:
                    kwargs[fp.dc_name] = [self._from_message_value(fp, v) for v in container]

            else:  # MAP
                container = getattr(proto, fp.pb_name)
                if not container:
                    continue
                kind = fp.kind
                if kind is _Kind.SCALAR:
                    kwargs[fp.dc_name] = dict(container)
                elif kind is _Kind.ENUM:
                    kwargs[fp.dc_name] = ({k: fp.value_type(v) for k, v in container.items()} if fp.value_type
                                          else dict(container))
                elif kind is _Kind.NULL:
                    kwargs[fp.dc_name] = {k: None for k in container}
                else:
                    kwargs[fp.dc_name] = {k: self._from_message_value(fp, v) for k, v in container.items()}

        return dataclass_type(**kwargs)

    def _from_message_value(self, fp: _FieldPlan, sub) -> Any:
        kind = fp.kind
        if kind is _Kind.MESSAGE:
            return self._to_dataclass(sub, fp.value_type)
        elif kind is _Kind.TIMESTAMP:
            return sub.ToDatetime()
        elif kind is _Kind.DURATION:
            return sub.ToTimedelta()
        elif kind is _Kind.ANY:
            return self._unpack_any(sub)
        else:  # JSON
            return json_format.MessageToDict(sub, preserving_proto_field_name=True)

    def _unpack_any(self, any_proto) -> Optional[DataclassBase]:
        if not any_proto.type_url:
            return None
        from protoplasm6.casting import castutils
        desc = castutils.get_proto_descriptor_by_type_url(any_proto.type_url)
        inner = message_factory.GetMessageClass(desc)()
        any_proto.Unpack(inner)
        return self._to_dataclass(inner, castutils.import_dataclass_by_proto(inner.__class__))
