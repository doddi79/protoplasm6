__all__ = [
    'BaseGrpcClientImplementation',
]
import grpc  # noqa

from protoplasm6.structs import *
from ._remotewrap import *
from ._metadata import *
from .dataclass_bases import *

import logging
log = logging.getLogger(__name__)


class BaseGrpcClientImplementation:
    def __init__(self, service_stub_cls: Type, grpc_host='localhost:50051',
                 credentials: Optional[Union[bool, grpc.ChannelCredentials]] = None,
                 options: Optional[Dict] = None, metadata: MetadataSpec = None, *args, **kwargs):
        """
        credentials:
        - None -> Automatic... will use `grpc.ssl_channel_credentials()` and secure_channel if port is 443
        - True -> Will use `grpc.ssl_channel_credentials()` and secure_channel
        - False -> Will use insecure_channel and no creds
        - grpc.ChannelCredentials -> Will use given creds and secure_channel

        metadata:
        - Metadata (i.e. headers, e.g. for authorization) added to every call
          made by this client, either as a dict, an iterable of (key, value)
          pairs or a callable returning either of those (which gets called for
          every call, e.g. to fetch a fresh access token). It can also be set
          (or changed) later via the `metadata` attribute.
        - See also `call_metadata()` for adding metadata to calls within a
          `with` block.
        """
        self.metadata: MetadataSpec = metadata
        options = options or {}
        if 'grpc.enable_http_proxy' not in options:
            options['grpc.enable_http_proxy'] = 0
        option_tuple = tuple(options.items())

        # Backwards compatibility
        if kwargs:
            if not credentials and 'credential' in kwargs:
                credentials = kwargs.pop('credential')
                log.warning('Deprecated keyword "credential" used when initiating BaseGrpcClient.'
                            ' Please use "credentials" instead!')

        # This keeps happening...!
        if ':' not in grpc_host:
            if credentials:
                log.warning('No port used in host... adding 443 by default (cause this is a secure connection)!')
                grpc_host = f'{grpc_host}:443'
            else:
                log.warning('No port used in host... adding 50051 by default!')
                grpc_host = f'{grpc_host}:50051'

        if credentials is None:
            if grpc_host.endswith(':443'):
                credentials = grpc.ssl_channel_credentials()
        elif credentials is True:
            credentials = grpc.ssl_channel_credentials()

        if credentials:
            self.grpc_channel: grpc.Channel = grpc.secure_channel(grpc_host, credentials, options=option_tuple)
        else:
            self.grpc_channel: grpc.Channel = grpc.insecure_channel(grpc_host, options=option_tuple)

        self.stub = service_stub_cls(self.grpc_channel)

    def call_metadata(self, metadata: MetadataSpec = None, **kwargs: Union[str, bytes]):
        """Context manager that adds the given metadata to every call made by
        this client (only) within its block (in the current thread/context).

        ```python
        with orders.call_metadata({'authorization': f'Bearer {token}'}):
            orders.get_order('o1')
        ```
        """
        return call_metadata(metadata, _client=self, **kwargs)

    def _forward_to_grpc(self, request_cls: Type[T_DCB], stub_method: Callable,
                         *args, **kwargs) -> Optional[Union[Any, Tuple[Any], Iterable[T_DCB]]]:
        return RemoteMethodWrapper(self, request_cls, stub_method, *args, **kwargs).call()
