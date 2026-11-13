"""Custom call metadata (i.e. HTTP/2 headers, e.g. for authorization) for gRPC
calls made by protoplasm6 clients.
"""
__all__ = [
    'MetadataSpec',
    'call_metadata',
    'normalize_metadata',
    'resolve_metadata',
]
import contextlib
import contextvars

from protoplasm6.structs import *

MetadataValue = Union[str, bytes]
MetadataPairs = Union[Mapping[str, MetadataValue], Iterable[Tuple[str, MetadataValue]]]
MetadataSpec = Union[MetadataPairs, Callable[[], Optional[MetadataPairs]], None]
"""Metadata can be given as a dict, an iterable of (key, value) pairs or a
callable (taking no arguments) returning either of those, which gets called
for every single call (e.g. to fetch a fresh access token)."""

# Stack of (client or None for "all clients", metadata spec)
_CONTEXT: contextvars.ContextVar[Tuple[Tuple[Any, MetadataSpec], ...]] = contextvars.ContextVar(
    'protoplasm6_call_metadata', default=())


def normalize_metadata(metadata: MetadataSpec) -> List[Tuple[str, MetadataValue]]:
    """Turns a metadata spec into a list of (key, value) tuples with lower case
    keys (as gRPC requires).
    """
    if metadata is None:
        return []
    if callable(metadata):
        metadata = metadata()
        if metadata is None:
            return []
    if isinstance(metadata, Mapping):
        metadata = metadata.items()
    pairs = []
    for key, value in metadata:
        key = str(key).lower()
        if not key.endswith('-bin') and not isinstance(value, str):
            value = str(value)
        pairs.append((key, value))
    return pairs


@contextlib.contextmanager
def call_metadata(metadata: MetadataSpec = None, *, _client: Any = None, **kwargs: MetadataValue):
    """Context manager that adds the given metadata (e.g. authorization
    headers) to every gRPC call made by protoplasm6 clients within its block
    (in the current thread/context only).

    ```python
    from protoplasm6 import plasm

    with plasm.call_metadata({'authorization': f'Bearer {token}'}):
        orders.get_order('o1')

    with plasm.call_metadata(x_request_id='abc123'):  # Underscores become dashes in keywords
        orders.get_order('o1')
    ```

    These can be nested and combined with the client's own metadata (see
    `BaseGrpcClientImplementation`). Use `client.call_metadata(...)` to only
    add metadata to the calls of a single client.
    """
    entries = []
    if metadata is not None:
        entries.append((_client, metadata))
    if kwargs:
        entries.append((_client, {k.replace('_', '-'): v for k, v in kwargs.items()}))
    token = _CONTEXT.set(_CONTEXT.get() + tuple(entries))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def resolve_metadata(client: Any) -> Optional[List[Tuple[str, MetadataValue]]]:
    """Returns all the metadata for a call made by the given client: The
    client's own metadata followed by any metadata added via `call_metadata()`
    (for all clients or for this one) in the order it was added.
    """
    pairs = normalize_metadata(getattr(client, 'metadata', None))
    for target, spec in _CONTEXT.get():
        if target is None or target is client:
            pairs.extend(normalize_metadata(spec))
    return pairs or None
