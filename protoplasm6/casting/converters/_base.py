__all__ = [
    'BaseConverter',
]
import abc
from protoplasm6.structs import *


class BaseConverter(abc.ABC):
    """Interface for converters that cast between protobuf message objects and
    protoplasm6 dataclasses (`DataclassBase`).

    Protoplasm6 uses the "current" converter (see
    `protoplasm6.casting.converters.get_converter()`) whenever it needs to cast
    between the two, e.g. in `DataclassBase.to_proto()`,
    `DataclassBase.from_proto()`, `casting.proto_to_dataclass()`,
    `casting.dataclass_to_proto()` and in the gRPC senders and receivers.
    """
    name: ClassVar[str] = ''

    @abc.abstractmethod
    def dataclass_to_proto(self, dc: DataclassBase) -> GeneratedProtocolMessageType:
        """Creates a new protobuf message object (of the dataclass's
        `__proto_cls__` type) populated with the data from the given dataclass.
        """

    @abc.abstractmethod
    def proto_to_dataclass(self, proto: GeneratedProtocolMessageType,
                           dataclass_type: Optional[Type[T_DCB]] = None) -> T_DCB:
        """Creates a new dataclass object populated with the data from the
        given protobuf message object.

        :param proto: The protobuf message object
        :param dataclass_type: The dataclass type to create, which defaults to
                               the dataclass type generated for the protobuf
                               message's type (via neobuilder6)
        """

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} {self.name!r}>'
