"""Converters between protobuf message objects and protoplasm6 dataclasses.

Two converters are included:

- `'direct'` (`DirectConverter`, the default) converts directly between
  protobuf messages and dataclasses.
- `'dict'` (`DictConverter`) is the original conversion that goes through Python
  dicts via `google.protobuf.json_format`.

The converter used by protoplasm6 (in `DataclassBase.to_proto()`,
`DataclassBase.from_proto()`, `casting.proto_to_dataclass()`,
`casting.dataclass_to_proto()` and in the gRPC senders and receivers) can be
chosen in a few ways:

- Setting the `PROTOPLASM6_CONVERTER` environment variable (to `direct` or
  `dict`) before protoplasm6 is imported
- Globally, by calling `set_converter('dict')`
- Temporarily (in the current thread/context), e.g:

  ```python
  with use_converter('dict'):
      proto = my_dataclass.to_proto()
  ```

You can also register your own (`BaseConverter` subclass) converters with
`register_converter()` or just pass instances of them to `set_converter()` and
`use_converter()`.
"""
__all__ = [
    'BaseConverter',
    'DictConverter',
    'DirectConverter',
    'DEFAULT_CONVERTER_NAME',
    'ENV_VAR_NAME',
    'get_converter',
    'set_converter',
    'use_converter',
    'register_converter',
    'available_converters',
]
import contextlib
import contextvars
import os

from protoplasm6.structs import *
from protoplasm6.casting.converters._base import *
from protoplasm6.casting.converters._dict import *
from protoplasm6.casting.converters._direct import *

import logging
log = logging.getLogger(__name__)

DEFAULT_CONVERTER_NAME = 'direct'
ENV_VAR_NAME = 'PROTOPLASM6_CONVERTER'

_REGISTRY: Dict[str, BaseConverter] = {
    DirectConverter.name: DirectConverter(),
    DictConverter.name: DictConverter(),
}

_OVERRIDE: contextvars.ContextVar[Optional[BaseConverter]] = contextvars.ContextVar('protoplasm6_converter',
                                                                                    default=None)

ConverterSpec = Union[str, BaseConverter]


def register_converter(converter: BaseConverter, name: Optional[str] = None) -> BaseConverter:
    """Registers a converter instance under the given name (or its `name`
    class attribute) so it can be selected by name (e.g. via the environment
    variable).
    """
    name = name or converter.name
    if not name:
        raise ValueError('Converters need a name to be registered')
    _REGISTRY[name] = converter
    return converter


def available_converters() -> Dict[str, BaseConverter]:
    return dict(_REGISTRY)


def _resolve(converter: ConverterSpec) -> BaseConverter:
    if isinstance(converter, BaseConverter):
        return converter
    try:
        return _REGISTRY[str(converter).strip().lower()]
    except KeyError:
        raise ValueError(f'Unknown protoplasm6 converter {converter!r} '
                         f'(available: {", ".join(sorted(_REGISTRY))})') from None


def _from_env() -> BaseConverter:
    env_value = os.environ.get(ENV_VAR_NAME, '').strip()
    if env_value:
        try:
            return _resolve(env_value)
        except ValueError as ex:
            log.warning('%s - Using the default %r converter instead', ex, DEFAULT_CONVERTER_NAME)
    return _REGISTRY[DEFAULT_CONVERTER_NAME]


_current: BaseConverter = _from_env()


def get_converter() -> BaseConverter:
    """Returns the converter currently in use."""
    return _OVERRIDE.get() or _current


def set_converter(converter: ConverterSpec) -> BaseConverter:
    """Sets the (global) converter by name (`'direct'` or `'dict'`) or
    instance and returns it.
    """
    global _current
    _current = _resolve(converter)
    return _current


@contextlib.contextmanager
def use_converter(converter: ConverterSpec):
    """Context manager that uses the given converter within its block (in the
    current thread/context only)."""
    token = _OVERRIDE.set(_resolve(converter))
    try:
        yield _OVERRIDE.get()
    finally:
        _OVERRIDE.reset(token)
