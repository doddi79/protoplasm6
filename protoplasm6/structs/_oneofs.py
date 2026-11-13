"""Helpers for protobuf `oneof` groups in protoplasm6 dataclasses."""
__all__ = [
    'OneofMember',
    'real_oneof_name',
    'get_oneof_members',
    'get_oneof_member_map',
    'get_field_default',
    'is_unset_value',
]
import dataclasses
from typing import *

from google.protobuf import descriptor as _descriptor

_CACHE: Dict[type, Dict[str, Tuple['OneofMember', ...]]] = {}
_MEMBER_MAP_CACHE: Dict[type, Dict[str, 'OneofMember']] = {}


class OneofMember(NamedTuple):
    group: str  # The oneof group's name
    dc_name: str  # The dataclass field name
    pb_name: str  # The protobuf field name
    field: dataclasses.Field


def real_oneof_name(fd: _descriptor.FieldDescriptor) -> Optional[str]:
    """The name of the "real" oneof group a protobuf field belongs to (i.e.
    not the synthetic one that proto3 `optional` fields get), if any.
    """
    oneof = fd.containing_oneof
    if oneof is None:
        return None
    if len(oneof.fields) == 1 and oneof.name == f'_{fd.name}':  # Synthetic (proto3 optional)
        return None
    return oneof.name


def get_oneof_members(dataclass_type: type) -> Dict[str, Tuple[OneofMember, ...]]:
    """Returns the oneof groups of a protoplasm6 dataclass type (by group name)
    and their members (in field order).
    """
    groups = _CACHE.get(dataclass_type)
    if groups is None:
        groups = {}
        proto_cls = getattr(dataclass_type, '__proto_cls__', None)
        if proto_cls is not None and dataclasses.is_dataclass(dataclass_type):
            fields_by_name = proto_cls.DESCRIPTOR.fields_by_name
            bfr: Dict[str, List[OneofMember]] = {}
            for field in dataclasses.fields(dataclass_type):
                pb_name = field.metadata.get('pb_name', field.name)
                fd = fields_by_name.get(pb_name)
                if fd is None:
                    continue
                group = real_oneof_name(fd)
                if group:
                    bfr.setdefault(group, []).append(OneofMember(group, field.name, pb_name, field))
            groups = {k: tuple(v) for k, v in bfr.items()}
        _CACHE[dataclass_type] = groups
    return groups


def get_oneof_member_map(dataclass_type: type) -> Dict[str, OneofMember]:
    """Returns all oneof members of a protoplasm6 dataclass type by their
    dataclass field name.
    """
    member_map = _MEMBER_MAP_CACHE.get(dataclass_type)
    if member_map is None:
        member_map = {m.dc_name: m for members in get_oneof_members(dataclass_type).values() for m in members}
        _MEMBER_MAP_CACHE[dataclass_type] = member_map
    return member_map


def get_field_default(field: dataclasses.Field) -> Any:
    if field.default is not dataclasses.MISSING:
        return field.default
    if field.default_factory is not dataclasses.MISSING:  # noqa
        return field.default_factory()  # noqa
    return None


def is_unset_value(field: dataclasses.Field, value: Any) -> bool:
    """Is this the "unset" value of a oneof member field? Since generated
    dataclasses give scalar fields default values (e.g. `''` and `0`), a oneof
    member with its default value counts as unset (just like protobuf, which
    can't tell the difference on the wire either).
    """
    if value is None or value is ...:
        return True
    default = get_field_default(field)
    if default is None or default is ...:
        return False
    try:
        return bool(value == default)
    except Exception:  # noqa
        return False
