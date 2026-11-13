# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [6.1.0] - 2026-11-14

### Added

- Custom call metadata (i.e. headers, e.g. for JWT authorization) for gRPC
  clients ([protoplasm#8](https://github.com/ccpgames/protoplasm/issues/8)):
  - A `metadata` argument (and attribute) on clients
    (`BaseGrpcClientImplementation`) taking a dict, `(key, value)` pairs or a
    callable returning either (called for every call, e.g. to refresh tokens)
  - `plasm.call_metadata(...)` context manager adding metadata to all calls
    within its block (in the current thread/context) and
    `client.call_metadata(...)` for a single client
  - `plasm.MetadataSpec` type
- Oneof support in dataclasses
  ([protoplasm#4](https://github.com/ccpgames/protoplasm/issues/4)):
  - `which_oneof(group)`, `get_oneof(group, default=None)`,
    `clear_oneof(group)` and the `oneof_groups()` class method on
    `DataclassBase`
  - Setting a oneof member on a dataclass resets the other members of its
    group (just like protobuf messages do)
- `plasm.ResponseIterationTimeoutError` (the correctly spelled name of
  `ResponseIterationTimoutError`, which is kept as a deprecated alias)
- A task-oriented [Public API index](docs/api-index.md) (for humans and LLMs
  alike)

### Changed

- The `DictConverter` now leaves out unset oneof members when converting
  dataclasses to protobuf (it used to send them all, which protobuf rejects)
- `GrpcContext.get_meta()` is now case-insensitive (gRPC metadata keys are
  always lower case)

### Fixed

- Unset (`None`) messages turning into empty messages (and empty lists of
  messages crashing) when going through dicts, e.g. via `to_dict()` /
  `from_dict()`, `to_json()` / `from_json()` and `from_clone()`
  ([protoplasm#10](https://github.com/ccpgames/protoplasm/issues/10))
- `from_clone()` breaking `oneof` fields
  ([protoplasm#9](https://github.com/ccpgames/protoplasm/issues/9))


## [6.0.0] - 2026-11-14

Forked and renamed!!

### Added

- This project by forking [`protoplasm`](https://github.com/ccpgames/protoplasm)
  (v5.3.1) in order to continue its development and maintenance
- Pluggable protobuf <-> dataclass converters in the new
  `protoplasm6.casting.converters` module:
  - `DirectConverter` (`'direct'`, the default) that converts directly
    between protobuf messages and dataclasses using the protobuf message API,
    which is roughly 4-7 times faster than the original conversion (both ways)
  - `DictConverter` (`'dict'`) which is the original protoplasm conversion via
    `json_format` dicts
  - `get_converter()`, `set_converter()`, the `use_converter()` context
    manager, `register_converter()` and the `PROTOPLASM6_CONVERTER`
    environment variable for choosing which one is used
  - `BaseConverter` for rolling your own
- Optional `dataclass_type` argument to `casting.proto_to_dataclass()`
- Support for modern type annotations in `castutils.check_type` (and thus in
  `require_params(typecheck=True)`), i.e. builtin generics like `list[int]`
  and `dict[str, Foo]` (PEP 585) and `X | Y` unions (PEP 604)
- Official support (as in: unit tests) for Python 3.10, 3.11, 3.12, 3.13 and
  3.14
- `googleapis` optional extra (`pip install protoplasm6[googleapis]`) for
  those who still want `googleapis-common-protos` installed alongside
- Unit tests checking that both converters give the same results (and for the
  cases where they don't, see below)
- A proper README, including the "monolith first, split into services later"
  idea behind the service interfaces

### Changed

- Renamed the package (and the module) from `protoplasm` to `protoplasm6`
  - So `from protoplasm import plasm` is now `from protoplasm6 import plasm`
    etc.
- Replaced the dependency on `ccptools` with its continuation fork
  [`batutils`](https://github.com/doddi79/batutils)
- Bumped dependencies to their latest major versions:
  - `protobuf` from `==5.27.2` to `>=7.34, <8`
  - `grpcio` from `>=1.66.1` to `>=1.80, <2`
- `DataclassBase.to_proto()`, `DataclassBase.from_proto()`,
  `casting.proto_to_dataclass()`, `casting.dataclass_to_proto()` and thus all
  gRPC senders and receivers now use the current converter (i.e. the
  `DirectConverter` by default)
- `DataclassBase.__post_init__` now caches which fields need casting per
  dataclass type, making creating dataclasses faster
- `castutils.check_type` now checks members of `Union`/`Optional` annotations
  recursively (e.g. `Optional[List[int]]` used to raise a `TypeError`)
  and checks `TypeVar` bounds
- Unit tests now run Neobuilder6 using the current Python interpreter
  (`sys.executable`) instead of whatever `python` is on the `PATH`
- Modernized packaging metadata (SPDX license, `requires-python`)

### Removed

- Official support for Python 3.8 and 3.9 (as in: removed from unit tests
  and `requires-python` is now `>=3.10`, as required by `protobuf` 7 anyway)
- `grpcio-tools` as a dependency since protoplasm6 itself never used it (it's
  now a dependency of `neobuilder6`, which actually uses it)
- `googleapis-common-protos` as a hard dependency (it was never used by
  protoplasm itself, see the new `googleapis` extra above)
- All of the old CCP GitHub workflows (unit tests, PyPI publishing and the
  Docker image building which pushed to CCP's Docker Hub registry) and the
  Dockerfiles, for now at least
- Python <3.9 compatibility code paths

### Fixed

When using the (default) `DirectConverter`, compared to the original
protoplasm conversion (i.e. the `DictConverter`):

- Maps with integer keys (e.g. `Dict[int, str]`) keep their `int` keys
  (the `DictConverter` gives them `str` keys since JSON object keys are
  always strings)
- Maps with `bool` keys work (the `DictConverter` fails to convert them to
  protobuf)
- Timezone aware `datetime` values are correctly converted to UTC (the
  `DictConverter` ignores their timezone)
- Messages with scalar `oneof` members work (the `DictConverter` fails to
  convert them to protobuf since all oneof members have default values in the
  dataclass, so it sends them all) and setting more than one member of the
  same oneof raises a `ValueError`
- Empty `repeated google.protobuf.Value` fields work (the `DictConverter`
  sends them as `None` which `json_format.ParseDict` fails on)
- `Duration` and `Timestamp` values keep their full microsecond precision

Also:

- The `ValueError` raised by `dict_to_dataclass()` on unknown fields was
  itself raising an `AttributeError` (because it referenced the missing field)

### Known issues

- Neobuilder6 gives proto3 `optional` scalar fields and scalar `oneof` members
  non-`None` default values in the generated dataclasses (e.g. `''` and `0`)
  so `optional` fields are always "present" in protobuf messages made from
  dataclasses and setting a scalar oneof member to its default value (e.g.
  `0`) is the same as not setting it


---

_Everything below is the history of the original
[`protoplasm`](https://github.com/ccpgames/protoplasm) package by CCP Games._

## [5.3.1] - 2024-09-24

### Fixed

- Dependency on the correct protobuf version now!


## [5.3.0] - 2024-09-24

### Added

- Support for the `google.protobuf.Value` message


## [5.2.0] - 2024-09-23

### Added

- Support for the `google.protobuf.Struct` message



## [5.0.0] - 2024-04-15

### Changed

- Moved this entire project over to Github 
- Bumped the version in order to not confuse older stuff that doesn't expect 
  protoplasm to exist in Pypi.org (if we end up migriting this there and 
  just open-sourcing the whole thing)
  - Also in case something changes in the API while migrating, cause I tend 
    to fiddle with the code and tidy up and refactor when moving stuff


## [4.6.0] - 2024-03-19

### Added

- Docker image building of the latest stable version of Protoplasm and all 
  its dependencies to this project for both Alpine and Debian and Python 
  versions 3.8-3.12
  - Thus, checking in and publishing a new stable version of Protoplasm 
    should trigger new Docker base images with Protoplasm and all the gRPC 
    binaries up-to-date and ready to be used by other projects (speeding up 
    their testing and building considerably)
  - ...at least in the old CI/CD environment... We'll see what's what once 
    this is all in Github and Github Actions

### Changed

- A ton of CI/CD stuff that's irrelevant now that we've moved to Github



## [4.3.0] - 2022-08-03

Fixed ANOTHER bug in type hint importing

### Fixed

- Now importing `List` and `Dict` with nested dots work (e.g. `List[foo.Bar]`)


## [4.2.0] - 2022-08-03

Fixed bug in type hint importing

### Fixed

- Now importing `List` and `Dict` works (was only `typing.List` and `typing.Dict` before)



## [4.1.0] - 2022-04-24

### Added

- Added the `ResponseIterator` which remote method calls with stream output now return as a wrapper around the previously returned iterable results.
- Added `TimeoutResponseIterator` which wraps the new `ResponseIterator` with timeout functionality while waiting for response stream iterations.
- `ResponseIterator` has a `with_timeout()` method which automatically wraps it in a `TimeoutResponseIterator`
- Both `ResponseIterator` and `TimeoutResponseIterator` have a `one_and_done()` method which waits for one next response stream iteration and then closes the stream.
- `RequestIterator` can now take in a `list` or `tuple` as `initial_request` to load up multiple initial requests.
- Added `close()` method to `RequestIterator` to close the request stream (force a cancel event)
- Added `unpack()` to `DataclassBase`


## [4.0.0] - 2022-06-18

Major update that unifies the API and functionality of versions 2 and 3.

Skipping a bunch of versions and checkins between 3.0 and 4.0 cause they're 
not really important at the moment (it's 2024 and I'm migrating this from 
our internal Gitlab repo to Github).

### Added

- Unify the unary functionality of Protoplasm 2 with the streaming 
  functionality of Protoplasm 3
  - The two turn out to be completely incompatible and API shattering 
    Protoplasm 4 must incorporate BOTH functionalities wile being backwards 
    compatible enough for both Protoplasm 2 and 3 projects to be able to 
    migrate to 4
  -The key here is detecting the `stream` keyword in protos that denote 
    streaming input and/or output
- Add piled up functionality/utility/QoL improvements/bugs that's been on The 
  List™ for a while
  - Cast to/from base64 encoded strings
  - Utilize the `__all__` directive to isolate `import *` side effects 
  - Integrate the Neobuf Builder CLI (from various other projects) into 
    Protoplasm and generalize it
  - Address the "`None` is default value" issue
  - Explore the pros/cons of making non-existing Message/Object attributes 
    return `Empty` or `EmptyDict` to simplify nested attribute fetching...?

### Changed

- Refactor and restructure the package properly
  - Separate the 4 main roles of the package logically
    1. Cross-piling `*.proto` to `*_pb2.py` and `*_pb2_grpc.py`
    2. Cross-piling `*_pb2.py` to `*_dc.py` Neobuf Dataclasses
    3. Generating `*_api.py` interfaces
    4. Generating gRPC implementation of Services


## [3.0.0] - 2021-05-11

Major update including support for gRPC streams.

Skipping a bunch of versions and checkins between 2.0 and 3.0 cause they're 
not really important at the moment (it's 2024 and I'm migrating this from 
our internal Gitlab repo to Github).

## Added

- Support for gRPC streams

## Changed

- This broke backwards compatibility with version 1 and 2's non-streaming 
  gRPC calls


## [2.0.0] - 2021-02-18

Major update including support for secure channels.

Skipping a bunch of versions and checkins between 1.0 and 2.0 cause they're 
not really important at the moment (it's 2024 and I'm migrating this from 
our internal Gitlab repo to Github).

### Added

- Support for Secure gRPC channels


## [1.0.0] - 2019-07-11

Initial stable release. 

Skipping a bunch of versions and checkins between 0.1 and 1.0 cause they're 
not really important at the moment (it's 2024 and I'm migrating this from 
our internal Gitlab repo to Github).

### Added

- A bunch of features


## [0.1.0] - 2019-01-17

### Added

- The initial checkin of this project