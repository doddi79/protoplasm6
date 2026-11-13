__all__ = [
    'DictConverter',
]
from protoplasm6.structs import *
from protoplasm6.casting.converters._base import *


class DictConverter(BaseConverter):
    """The original protoplasm (5.x and older) conversion that goes through Python
    dicts via `google.protobuf.json_format`, i.e:

    - protobuf -> `json_format.MessageToDict` -> dict -> dictators -> dataclass
    - dataclass -> dictators -> dict -> `json_format.ParseDict` -> protobuf

    This is slower than the `DirectConverter` (as everything gets converted
    twice and values like timestamps, bytes and 64 bit ints get serialized to
    and parsed from strings in between) but it is the reference implementation
    which the `DirectConverter` aims to be equivalent to.
    """
    name = 'dict'

    def dataclass_to_proto(self, dc: DataclassBase) -> GeneratedProtocolMessageType:
        from protoplasm6.casting.dictator import dataclass_to_dict
        from protoplasm6.casting.objectifier import dict_to_proto
        return dict_to_proto(dc.__proto_cls__, dataclass_to_dict(dc))

    def proto_to_dataclass(self, proto: GeneratedProtocolMessageType,
                           dataclass_type: Optional[Type[T_DCB]] = None) -> T_DCB:
        from protoplasm6.casting.castutils import import_dataclass_by_proto
        from protoplasm6.casting.dictator import proto_to_dict
        from protoplasm6.casting.objectifier import dict_to_dataclass
        if dataclass_type is None:
            dataclass_type = import_dataclass_by_proto(proto.__class__)
        return dict_to_dataclass(dataclass_type, proto_to_dict(proto))
