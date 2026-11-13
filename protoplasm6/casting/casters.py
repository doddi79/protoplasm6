__all__ = [
    'mkproto',
    'mkdataclass',
    'proto_to_dataclass',
    'dataclass_to_proto',
    'unpack_dataclass_return',
    'pack_dataclass_response',
]
# Alias imports
from protoplasm6.structs import *
from protoplasm6.casting.castutils import *
from protoplasm6.casting.dictator import *
from protoplasm6.casting.objectifier import *
from protoplasm6.casting import converters

import logging
log = logging.getLogger(__name__)


def mkproto(proto_class: Type[GeneratedProtocolMessageType], **kwargs) -> GeneratedProtocolMessageType:
    """Creates a new Protobuf object of the given proto_class type and populates
    it using the given kwargs, first converting the kwargs to a dict via the
    kwdict function that turns keywords using double-underscores into sub-dicts
    for use as data for nested proto messages.

    :param proto_class: The Protobuf message class (type)
    :return: A fully initialized and populated Profobuf object
    """
    return dict_to_proto(proto_class, kwdict(**kwargs))


def mkdataclass(dataclass_type: Type[T_DCB], **kwargs) -> T_DCB:
    """Creates a new Dataclass object of the given dataclass_type and populates
    it using the given kwargs, first converting the kwargs to a dict via the
    kwdict function that turns keywords using double-underscores into sub-dicts
    for use as data for nested proto messages.

    :param dataclass_type: Dataclass type to create
    :return: A fully initialized and populated Profobuf object
    """
    return dict_to_dataclass(dataclass_type, kwdict(**kwargs))


def proto_to_dataclass(proto: GeneratedProtocolMessageType,
                       dataclass_type: Optional[Type[T_DCB]] = None) -> DataclassBase:
    """Casts a protobuf message into its corresponding dataclass (or the
    given `dataclass_type`) using the current converter (see
    `protoplasm6.casting.converters`).
    """
    return converters.get_converter().proto_to_dataclass(proto, dataclass_type)


def dataclass_to_proto(dc: DataclassBase) -> GeneratedProtocolMessageType:
    """Casts a dataclass into its corresponding protobuf message using the
    current converter (see `protoplasm6.casting.converters`).
    """
    return converters.get_converter().dataclass_to_proto(dc)


def unpack_dataclass_return(dc: DataclassBase) -> Optional[Tuple[Any]]:
    l = []
    for field in dataclasses.fields(dc):
        l.append(getattr(dc, field.name))
    ln = len(l)
    if ln == 0:
        return
    elif ln == 1:
        return l[0]
    return tuple(l)


def pack_dataclass_response(dc_response_type: Type[T_DCB], return_value) -> T_DCB:
    if isinstance(return_value, dc_response_type):
        return return_value

    if return_value is None:
        return dc_response_type()

    if isinstance(return_value, dict):
        return dc_response_type(**return_value)  # TODO(thordurm@ccpgames.com>): Temporary solution
        # TODO(thordurm@ccpgames.com>): If keys match dc_response_type fields, it's a simple kwargs mapping
        # TODO(thordurm@ccpgames.com>): ...else If the first field it a dict, treat this as the first field
        # TODO(thordurm@ccpgames.com>): ...else we're fucked!

    elif isinstance(return_value, tuple):
        return dc_response_type(*return_value)  # TODO(thordurm@ccpgames.com>): Temporary solution
        # TODO(thordurm@ccpgames.com>): If value types match field types and len is <= fields, it's a simple args mapping
    else:
        return dc_response_type(return_value)
