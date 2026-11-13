# Protoplasm6 Public API Index

Task-oriented reference for code that *uses* `protoplasm6` (distribution
`protoplasm6`, import `protoplasm6`). Covers the working tree for version
**6.1.0** (see [`protoplasm6/__init__.py`](../protoplasm6/__init__.py)).

Protoplasm6 is the runtime half of a pair: [`neobuilder6`](https://github.com/doddi79/neobuilder6)
generates code from `.proto` files (`*_dc.py` dataclasses, `*_api.py`
interfaces, `*_grpc_receiver.py` servicers, `*_grpc_sender.py` clients) and that
code is built on the classes below. Examples use the generated `myshop.orders`
package from the [README](../README.md).

**Preferred imports**

```python
from protoplasm6 import plasm      # Everything for services, dataclasses, errors, decorators, metadata
from protoplasm6 import casting    # Casting between protobuf, dataclasses, dicts and JSON
from protoplasm6.casting import converters  # Choosing the protobuf <-> dataclass converter
```

`plasm` also re-exports every `typing` name (a side effect of internal star
imports); don't rely on those, import `typing` yourself.

## Find it by task

| I want to...                                                       | Use                                                                 |
|--------------------------------------------------------------------|---------------------------------------------------------------------|
| Turn a message dataclass into protobuf / bytes / base64 / dict / JSON | [`DataclassBase.to_*`](#dataclasses)                              |
| Build a message dataclass from protobuf / bytes / base64 / dict / JSON | [`DataclassBase.from_*`](#dataclasses)                            |
| Build nested messages from keyword args (`a__b=1`)                  | [`from_kwdict`, `casting.mkdataclass`, `casting.mkproto`](#casting-helpers) |
| Copy data between two similar message types                         | [`DataclassBase.from_clone`](#dataclasses)                         |
| See / clear which `oneof` member is set                             | [`which_oneof`, `get_oneof`, `clear_oneof`](#oneof-fields)         |
| Make protobuf conversion faster or use the old behaviour            | [`converters`](#converters-protobuf---dataclass)                    |
| Implement a gRPC service                                            | [Generated `*Interface` + `plasm` errors](#implementing-a-service) |
| Run a gRPC server                                                   | [`plasm.GrpcServer` / `__servicer_cls__`](#serving)                |
| Call a remote service                                               | [Generated client + `BaseGrpcClientImplementation`](#calling-a-service) |
| Send auth tokens / headers (JWT, API keys) with calls               | [`metadata=`, `plasm.call_metadata`](#call-metadata-headers)        |
| Read request headers / client IP in a service                       | [`plasm.takes_context`, `GrpcContext.get_meta`](#request-context-headers-ip) |
| Validate required / typed arguments                                 | [`plasm.require_params`](#argument-validation)                      |
| Return a gRPC status code (NOT_FOUND etc.) / catch one on the client | [`plasm` errors](#errors-status-codes)                             |
| Stream requests or responses                                        | [`RequestIterator`, `ResponseIterator`](#streaming)                 |
| Look up a dataclass by proto message name / type URL                | [`loader`, `castutils`](#lookups-and-utilities)                     |
| Check a value against a type annotation                             | [`casting.check_type`](#lookups-and-utilities)                     |

## Dataclasses

Every generated message class extends `plasm.DataclassBase`
([source](../protoplasm6/structs/dataclassbase.py)) and has a
`__proto_cls__` class attribute pointing to its `*_pb2` message class.

| Method                                                   | Returns / notes |
|----------------------------------------------------------|-----------------|
| `to_proto() -> Message`                                  | Protobuf message, via the [current converter](#converters-protobuf---dataclass) |
| `to_protostr() -> bytes`                                 | Serialized protobuf |
| `to_base64() -> bytes`                                   | Serialized protobuf as base64 (no newlines) |
| `to_dict() -> dict`                                      | Nested, JSON-safe dict (timestamps as ISO strings ending in `Z`, bytes as base64, int64 as strings, enums as ints, unset messages and empty lists/maps as `None`) |
| `to_json(indent=None) -> str`                            | `json.dumps(to_dict())` |
| `unpack() -> dict`                                       | Field name -> value, **not** recursive (sub-messages stay dataclasses) |
| `explode() -> value \| tuple \| None`                    | Field values only; a single field is returned bare, no fields returns `None` |
| `@classmethod from_proto(proto)`                         | Via the current converter |
| `@classmethod from_protostr(data: bytes)`                |  |
| `@classmethod from_base64(data: bytes \| str)`           | Tolerates missing padding and whitespace |
| `@classmethod from_dict(d, ignore_extras=False)`         | Unknown keys raise `ValueError` unless `ignore_extras` |
| `@classmethod from_json(s)`                              |  |
| `@classmethod from_kwdict(**kwargs)`                     | `Order.from_kwdict(order_id='o1', customer__name='Jane')` |
| `@classmethod from_clone(other)`                         | Copies matching fields from another dataclass (extras ignored) |

Field conventions in generated dataclasses:

- Scalars default to their protobuf defaults (`''`, `0`, `False`, `b''`),
  sub-messages to `None`, repeated fields to `[]`, maps to `{}`.
- `Timestamp` -> naive UTC `datetime.datetime` (aware datetimes are converted
  to UTC), `Duration` -> `datetime.timedelta`, `Any` -> any `DataclassBase`,
  `Struct` -> `dict`, `ListValue` -> `list`, `Value` -> any JSON value with
  `...` (Ellipsis) meaning "unset" and `None` meaning JSON `null`.
- Enums are `enum.IntEnum` classes in the `*_dc.py` modules (nested enums are
  nested classes, e.g. `WithInternalEnum.InternalEnum`).
- Fields named after Python keywords get a trailing underscore (`class_`,
  `None_`); the protobuf name is kept in the field's `pb_name` metadata.
- Sub-messages, lists and maps of messages can be given as dicts, tuples or
  dataclasses when constructing; they're cast to the right dataclass in
  `__post_init__`.
- Proto3 `optional` fields aren't nullable in the dataclass (they get scalar
  defaults), so they're always "present" in protobuf made from a dataclass.

### Oneof fields

Dataclasses for messages with `oneof` groups behave like protobuf messages:
setting one member resets the others. A member holding its default value
(e.g. `0`, `''`, `None`) counts as **not set** (protobuf can't tell the
difference on the wire either).

```python
p = PaymentMessage(card_number='4111...')
p.which_oneof('method')           # 'card_number' (dataclass field name), or None
p.get_oneof('method', default=None)
p.bank_account = 'IS12...'        # Resets card_number
p.clear_oneof('method')
PaymentMessage.oneof_groups()     # {'method': ('card_number', 'bank_account')}
```

Unknown group names raise `ValueError`. When constructing with several
members of the same group, the last one (in field order) wins.
Tests: [tests/test_oneofs_and_dicts.py](../tests/test_oneofs_and_dicts.py).

## Converters (protobuf <-> dataclass)

[Source](../protoplasm6/casting/converters/__init__.py) ·
[tests](../tests/test_converters.py)

All protobuf <-> dataclass casting (`to_proto`, `from_proto`,
`casting.proto_to_dataclass`, `casting.dataclass_to_proto` and every gRPC call)
goes through the current converter.

| Name               | Class                        | Notes |
|--------------------|------------------------------|-------|
| `'direct'` (default) | `converters.DirectConverter` | ~4-7x faster; walks message fields directly; falls back to dict logic per field for custom dictators |
| `'dict'`           | `converters.DictConverter`   | Original protoplasm 5 behaviour via `json_format` dicts |

```python
converters.get_converter() -> BaseConverter
converters.set_converter('dict' | 'direct' | BaseConverter) -> BaseConverter   # Global
with converters.use_converter('dict'): ...                                      # Current thread/context only
converters.register_converter(converter: BaseConverter, name: str | None = None)
converters.available_converters() -> dict[str, BaseConverter]
```

Environment variable: `PROTOPLASM6_CONVERTER=dict|direct` (read at import;
unknown values log a warning and use `direct`).

Behaviour differences (the `dict` converter's are bugs kept for
compatibility): with `direct`, `Dict[int, ...]` map keys stay `int` (`dict`
gives `str`), `bool` map keys work, timezone-aware datetimes are converted to
UTC, and empty `repeated Value` lists work.

Custom converters subclass `converters.BaseConverter` and implement
`dataclass_to_proto(dc) -> Message` and
`proto_to_dataclass(proto, dataclass_type=None) -> DataclassBase`.

## Casting helpers

[Source](../protoplasm6/casting/casters.py) · [tests](../tests/test_casting.py)

```python
casting.proto_to_dataclass(proto, dataclass_type=None) -> DataclassBase  # Type defaults to the generated one
casting.dataclass_to_proto(dc) -> Message
casting.proto_to_dict(proto) -> dict              # MessageToDict(preserving_proto_field_name, int enums)
casting.dataclass_to_dict(dc) -> dict             # Same as dc.to_dict()
casting.dict_to_proto(proto_class, d=None) -> Message
casting.dict_to_dataclass(dataclass_type, d=None, ignore_extras=False) -> DataclassBase
casting.mkproto(proto_class, **kwargs) -> Message           # Double underscores nest: customer__name='Jane'
casting.mkdataclass(dataclass_type, **kwargs) -> DataclassBase
casting.kwdict(**kwargs) -> dict                  # {'customer__name': 'J'} -> {'customer': {'name': 'J'}}
casting.unpack_dataclass_return(dc)               # Like DataclassBase.explode()
casting.pack_dataclass_response(dc_type, value)   # Value / tuple / dict / None -> response dataclass
```

## Implementing a service

Neobuilder6 generates `<Service>Interface` in `*_api.py` with one method per
RPC. Request fields become keyword arguments (all defaulting to `None`) and
response fields become the return value:

| Response message fields | Return                         |
|-------------------------|--------------------------------|
| none                    | `None`                         |
| one                     | that field's value             |
| several                 | a tuple, in field order        |
| streaming (`stream`)    | an iterable of response dataclasses |

Return values are packed into the response dataclass for you (a value, a
tuple, a dict of fields or the response dataclass itself all work).
Unimplemented methods raise `plasm.Unimplemented`. Method names are
`snake_case` versions of the RPC names.

```python
class MyOrderService(OrderServiceInterface):
    @plasm.require_params
    def get_order(self, order_id: str) -> Order:
        order = db.get(order_id)
        if not order:
            raise plasm.NotFound(f'No order {order_id}')
        return order
```

The same interface is implemented by the generated client, so code calling a
service doesn't know whether it's local or remote (the "monolith first, split
into services later" idea).

### Serving

```python
server = plasm.GrpcServer(port='[::]:50051', max_workers=10)
server.add_servicer(OrderServiceInterface.__servicer_cls__(MyOrderService()))
server.serve()   # Blocks until KeyboardInterrupt
```

Or with your own `grpc.server(...)`: `OrderServiceGrpcServicer(impl).add_to_server(grpc_server)`
(`plasm.BaseGrpcServicer`, [source](../protoplasm6/bases/_servicer.py)). The
servicer is plain `grpcio` with a thread pool.

### Calling a service

The generated client class in `*_grpc_sender.py` is named after the service
and extends `plasm.BaseGrpcClientImplementation`
([source](../protoplasm6/bases/_client.py)):

```python
OrderService(grpc_host='localhost:50051', credentials=None, options=None, metadata=None)
```

- `credentials`: `None` = TLS only if the port is 443, `True` = TLS with
  default roots, `False` = insecure, or a `grpc.ChannelCredentials`.
- `grpc_host` without a port gets `:443` (with credentials) or `:50051`.
- `options`: dict of gRPC channel options (`grpc.enable_http_proxy` defaults
  to `0`).
- Errors from the server are raised as the matching `plasm` error (see
  below); failures before/after the request raise `plasm.PreRequestError` /
  `plasm.PostRequestError` (both `plasm.ClientApiError`).
- Arguments can be passed positionally or by keyword, in request field order.

### Call metadata (headers)

[Source](../protoplasm6/bases/_metadata.py) · [tests](../tests/test_call_metadata.py)

```python
orders = OrderService('localhost:50051', metadata={'authorization': f'Bearer {token}'})
orders = OrderService(..., metadata=lambda: {'authorization': f'Bearer {get_fresh_token()}'})  # Called per call
orders.metadata = [('x-api-key', 'abc')]            # Can be changed later

with plasm.call_metadata({'x-request-id': 'r1'}):   # All clients, current thread/context only
    orders.get_order('o1')
with plasm.call_metadata(x_request_id='r1'): ...    # Keyword underscores become dashes
with orders.call_metadata(authorization='Bearer x'): ...  # This client only
```

`plasm.MetadataSpec` = dict, iterable of `(key, value)` pairs or a no-argument
callable returning either. Keys are lower-cased (gRPC requires it); values
must be `str` (or `bytes` for keys ending in `-bin`), other values are
`str()`-ed. Metadata is combined in this order: client `metadata`, then
`call_metadata` blocks (outermost first); repeated keys are all sent. If a
metadata callable raises, the call raises `plasm.PreRequestError`.

### Request context (headers, IP)

```python
class MyOrderService(OrderServiceInterface):
    @plasm.takes_context                       # Or @plasm.takes_context('ctx')
    def get_order(self, order_id: str, context: plasm.GrpcContext = None) -> Order:
        token = context.get_meta('authorization')   # Case-insensitive; repeated keys give a list
        ip = context.get_origin_ip()                # x-forwarded-for, else the peer address
        raw = context.wrapped_context               # The grpc.ServicerContext
```

### Argument validation

```python
@plasm.require_params                          # All parameters must be non-None
@plasm.require_params('order_id', 'customer')  # Only these
@plasm.require_params(typecheck=True)          # Also check values against annotations
```

Missing (`None`) or mistyped parameters raise `plasm.InvalidArgument`
(gRPC `INVALID_ARGUMENT`). Type checking understands `typing` generics,
builtin generics (`list[int]`) and `X | Y` unions
([source](../protoplasm6/decorators/apihelpers.py)).

### Errors (status codes)

Raise these in implementations; clients raise the same classes. All extend
`plasm.ServiceApiException(status_code=2, details='unknown', ref_code=None,
should_log=False)` -> `plasm.ProtoplasmError`
([source](../protoplasm6/errors/_api.py)):

`NotFound`, `InvalidArgument`, `Unimplemented`, `PermissionDenied`,
`Unauthenticated`, `Unavailable`, `DeadlineExceeded`, `AlreadyExists`,
`FailedPrecondition`, `DataLoss`, `ResourceExhausted`, `OutOfRange`,
`Internal`, `Cancelled`, `Aborted`, `Unknown`.

Any other exception in an implementation becomes `UNKNOWN` (and is logged
with a `ref_code`, also sent as trailing metadata, for matching client and
server logs). `plasm` errors are only logged, and given a `ref_code`, when
raised with `should_log=True`. Failures casting the request become
`FAILED_PRECONDITION` and failures packing the response `CANCELLED`
([source](../protoplasm6/bases/_methwrap.py)). `protoplasm6.errors` has the same names (`errors.api.*` is a backwards
compatible alias).

### Streaming

RPCs with `stream` inputs take a single `request_iterator` argument; ones with
`stream` outputs return a `plasm.ResponseIterator`
([source](../protoplasm6/structs/_responseiter.py)):

```python
for line in story_service.tell_me_a_story('Three Little Pigs'):   # Server streaming
    print(line.line)

requests = plasm.RequestIterator(MarcoPoloRequest(question='Marco!'))  # Client streaming
for response in game.marco_polo(requests):
    requests.send(MarcoPoloRequest(question='Marco?'))   # Feed more while reading
requests.close()                                         # Ends the request stream

responses = story_service.tell_me_a_story('x').with_timeout(5.0)   # Per-item timeout
responses.next()                     # Raises plasm.ResponseIterationTimeoutError on timeout
story_service.tell_me_a_story('x').one_and_done(timeout_seconds=5) # First item, then cancel
```

`ResponseIterator.close()` cancels the RPC. `with_timeout(timeout_seconds=60,
raise_timeout=True)`; with `raise_timeout=False` iteration just stops.
`ResponseIterationTimoutError` (sic) is a deprecated alias of
`ResponseIterationTimeoutError`. Tests: [tests/test_services.py](../tests/test_services.py)
and [tests/_sandbox](../tests/_sandbox).

## Lookups and utilities

```python
from protoplasm6 import loader
loader.get_dataclass_by_message_name('myshop.orders.Order') -> type[DataclassBase]

casting.import_dataclass_by_proto(proto_class) -> type[DataclassBase]   # foo_pb2.X -> foo_dc.X
casting.get_type_url(proto_class, prefix='type.googleapis.com/') -> str
casting.get_proto_descriptor_by_type_url(type_url) -> Descriptor        # TypeError if not imported yet
casting.check_type(value, annotation) -> bool
casting.humps_to_under('GetOrderID') -> 'get_order_id'
casting.fuzzy_base64_to_bytes(data) -> bytes                            # Tolerates missing padding
casting.force_object(cls, value)    # None/instance as is, dict -> cls(**v), list/tuple -> cls(*v), else cls(v)
```

Type URL lookups (and `Any` unpacking) need the message's `*_pb2` module
imported; call `your_package.load_symbols()` (generated by Neobuilder6) to
import everything.

## Coverage gaps

- Modules prefixed with `_` and `protoplasm6.casting.dictators` (per-field
  value casters referenced from generated metadata) are internal; custom
  dictators work but aren't a documented extension point.
- `castutils` exports more helpers than listed here (`get_type_from_module_import_as`,
  `get_dc_field_obj_type`, `base64_stripper`, `base64_filler`,
  `get_type_name_from_url`, `get_proto_file_by_type_url`); they're mostly
  used by generated code and the converters.
