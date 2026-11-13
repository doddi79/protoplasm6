from __future__ import annotations

__all__ = [
    'DataclassBase',
    'T_DCB',  # Required...?!?
]

import json
import base64

from protoplasm6.structs._base import *
from protoplasm6.structs import _oneofs
import dataclasses

import logging
log = logging.getLogger(__name__)

T_DCB = TypeVar('T_DCB', bound='DataclassBase')

# Per dataclass type: The fields that hold other dataclasses (and whether
# they're maps or lists) so __post_init__ doesn't need to work that out for
# every single object
_OBJ_FIELDS_CACHE: Dict[type, Tuple[Tuple[dataclasses.Field, bool, bool], ...]] = {}


def _has_real_oneofs(proto_cls: Any) -> bool:
    desc = getattr(proto_cls, 'DESCRIPTOR', None)
    if desc is None:
        return False
    return any(_oneofs.real_oneof_name(fd) for fd in desc.fields)


def _oneof_setattr(self, name: str, value: Any):
    """`__setattr__` for dataclasses with oneof groups that, just like
    protobuf messages, resets the other members of a oneof group when one of
    them gets set.
    """
    object.__setattr__(self, name, value)
    member = _oneofs.get_oneof_member_map(type(self)).get(name)
    if member is not None and not _oneofs.is_unset_value(member.field, value):
        for other in _oneofs.get_oneof_members(type(self))[member.group]:
            if other.dc_name != name:
                object.__setattr__(self, other.dc_name, _oneofs.get_field_default(other.field))


@dataclasses.dataclass
class DataclassBase(Generic[T_DCB]):
    __proto_cls__: ClassVar[GeneratedProtocolMessageType]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Only dataclasses with oneof groups get the (slower) oneof aware
        # __setattr__
        if '__setattr__' not in cls.__dict__ and _has_real_oneofs(cls.__dict__.get('__proto_cls__')):
            cls.__setattr__ = _oneof_setattr

    def __post_init__(self):
        obj_fields = _OBJ_FIELDS_CACHE.get(type(self))
        if obj_fields is None:
            obj_fields = tuple((f, f.metadata.get('is_map', False), f.metadata.get('is_list', False))
                               for f in dataclasses.fields(self) if f.metadata.get('is_obj', False))
            _OBJ_FIELDS_CACHE[type(self)] = obj_fields
        if not obj_fields:
            return

        from protoplasm6.casting import castutils
        for f, is_map, is_list in obj_fields:
            f_val = getattr(self, f.name, None)
            if f_val:
                f_type = castutils.get_dc_field_obj_type(f, self)
                if is_map:
                    for k in f_val.keys():
                        f_val[k] = castutils.force_object(f_type, f_val[k])
                elif is_list:
                    for i in range(len(f_val)):
                        f_val[i] = castutils.force_object(f_type, f_val[i])
                else:
                    setattr(self, f.name, castutils.force_object(f_type, f_val))

    @classmethod
    def oneof_groups(cls) -> Dict[str, Tuple[str, ...]]:
        """Returns the oneof groups of this dataclass (by name) and the
        (dataclass) names of the fields in each of them.
        """
        return {k: tuple(m.dc_name for m in v) for k, v in _oneofs.get_oneof_members(cls).items()}

    def _get_oneof_group(self, group: str) -> Tuple[_oneofs.OneofMember, ...]:
        members = _oneofs.get_oneof_members(type(self)).get(group)
        if members is None:
            raise ValueError(f'{type(self).__name__} has no oneof group called "{group}"')
        return members

    def which_oneof(self, group: str) -> Optional[str]:
        """Returns the (dataclass) name of the field that's set in the given
        oneof group or None if none of them is (like protobuf's
        `WhichOneof()`).

        Note that since dataclasses give oneof scalar fields default values
        (e.g. `''` and `0`), a field with its default value counts as not set
        (protobuf can't tell the difference on the wire either).

        :raises ValueError: If there's no oneof group with the given name
        """
        for m in self._get_oneof_group(group):
            if not _oneofs.is_unset_value(m.field, getattr(self, m.dc_name)):
                return m.dc_name
        return None

    def get_oneof(self, group: str, default: Any = None) -> Any:
        """Returns the value of the field that's set in the given oneof group
        (or the given default if none of them is).

        :raises ValueError: If there's no oneof group with the given name
        """
        name = self.which_oneof(group)
        if name is None:
            return default
        return getattr(self, name)

    def clear_oneof(self, group: str):
        """Resets all the fields in the given oneof group to their defaults
        (like protobuf's `ClearField()` with a oneof name).

        :raises ValueError: If there's no oneof group with the given name
        """
        for m in self._get_oneof_group(group):
            object.__setattr__(self, m.dc_name, _oneofs.get_field_default(m.field))

    def to_dict(self) -> Dict:
        """Turns this `DataclassBase` into a dict of its fields and values
        recursively and returns, so for any field value that is itself a
        `DataclassBase`, `to_dict` is also called, resulting in a nested dict of
        only "primitive" (and JSON serializable) values.
        """
        from protoplasm6 import casting
        return casting.dataclass_to_dict(self)

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_proto(self) -> GeneratedProtocolMessageType:
        from protoplasm6 import casting
        return casting.dataclass_to_proto(self)

    def to_protostr(self) -> bytes:
        from protoplasm6 import casting
        return casting.dataclass_to_proto(self).SerializeToString()

    def to_base64(self) -> bytes:
        return base64.encodebytes(self.to_protostr()).strip().replace(b'\r',
                                                                      b'').replace(b'\n', b'').replace(b'\t', b'')

    def unpack(self) -> Dict[str, Any]:
        """Returns a dict with the fields of this `DataclassBase` as keys and
        their values as they are.

        The main difference between this and the `to_dict` method is that
        `to_dict` is recursive so on any field value that is itself a
        `DataclassBase`, `to_dict` is also called, resulting in a nested dict of
        only "primitive" (and JSON serializable) values.

        This `unpack` method on the other hand will leave any `DataclassBase`
        values be.

        The main use-case for this method is to "unpack"/"explode"/"break up" a
        gRPC Proto Service Request/Response message up into individual method
        arguments.
        """
        d = {}
        for field in dataclasses.fields(self):
            d[field.name] = getattr(self, field.name)
        return d

    def explode(self) -> Optional[Union[Tuple[Any], Any]]:
        """Returns a tuple with the field values of this `DataclassBase` or if
        this `DataclassBase` only contains one field, returns that field's value
        alone.

        This is similar to the `unpack()` method except this only returns values
        and if there's only a single field (as many RPC Response messages do),
        it's not wrapped in a tuple.

        The main use-case for this method is to "unpack" a gRPC Proto Service
        RPC Unary Response message up into individual return values (often just
        one).
        """
        tu = []
        for field in dataclasses.fields(self):
            tu.append(getattr(self, field.name))
        if not tu:
            return  # We can theoretically have "empty" Response message classes
        if len(tu) == 1:
            return tu[0]
        return tuple(tu)

    @classmethod
    def from_kwdict(cls, **kwargs) -> T_DCB:
        from protoplasm6.casting import castutils
        return cls.from_dict(castutils.kwdict(**kwargs))

    @classmethod
    def from_dict(cls, dict_data: dict, ignore_extras: bool = False) -> T_DCB:
        from protoplasm6 import casting
        return casting.dict_to_dataclass(cls, dict_data, ignore_extras)

    @classmethod
    def from_json(cls, json_string: str) -> T_DCB:
        return cls.from_dict(json.loads(json_string))

    @classmethod
    def from_proto(cls, proto: GeneratedProtocolMessageType) -> T_DCB:
        from protoplasm6 import casting
        return casting.proto_to_dataclass(proto, cls)

    @classmethod
    def from_protostr(cls, protostr: bytes) -> T_DCB:
        proto = cls.__proto_cls__()
        proto.ParseFromString(protostr)
        return cls.from_proto(proto)

    @classmethod
    def from_base64(cls, base64str: Union[bytes, str]) -> T_DCB:
        from protoplasm6.casting import castutils
        return cls.from_protostr(castutils.fuzzy_base64_to_bytes(base64str))

    @classmethod
    def from_clone(cls, clone: DataclassBase) -> T_DCB:
        return cls.from_dict(clone.to_dict(), ignore_extras=True)
