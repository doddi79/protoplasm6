import json
import sys
import threading
import unittest
from concurrent import futures

import grpc

from tests.testutils import *

from protoplasm6 import plasm

import logging
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

PORT = 50071


class CallMetadataTest(unittest.TestCase):
    """Issue #8 - Custom call metadata (headers) in client calls"""
    server = None

    @classmethod
    def setUpClass(cls) -> None:
        build_new_protos(package_name='unittesting')
        sys.path.append(BUILD_ROOT)
        from unittesting.unary.unaryservice_api import UnaryServiceInterface

        class EchoMetadata(UnaryServiceInterface):
            """Returns the requested metadata keys (comma separated) as JSON"""
            @plasm.takes_context
            def with_both(self, some_input: str = None, context: plasm.GrpcContext = None) -> str:
                return json.dumps({k: context.get_meta(k) for k in some_input.split(',')})

        cls.server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        UnaryServiceInterface.__servicer_cls__(EchoMetadata()).add_to_server(cls.server)
        cls.server.add_insecure_port(f'[::]:{PORT}')
        cls.server.start()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.server:
            cls.server.stop(0)

    @staticmethod
    def _client(**kwargs):
        from unittesting.unary.unaryservice_grpc_sender import UnaryService
        return UnaryService(f'localhost:{PORT}', **kwargs)

    @staticmethod
    def _echo(client, *keys):
        return json.loads(client.with_both(','.join(keys)))

    def test_no_metadata(self):
        self.assertEqual({'authorization': None}, self._echo(self._client(), 'authorization'))

    def test_client_metadata(self):
        client = self._client(metadata={'Authorization': 'Bearer abc', 'x-number': 42})
        self.assertEqual({'authorization': 'Bearer abc', 'x-number': '42'},
                         self._echo(client, 'authorization', 'x-number'))

        client.metadata = [('authorization', 'Bearer xyz')]
        self.assertEqual({'authorization': 'Bearer xyz'}, self._echo(client, 'authorization'))

    def test_callable_metadata_is_called_for_every_call(self):
        counter = iter(range(1, 100))
        client = self._client(metadata=lambda: {'authorization': f'Bearer token-{next(counter)}'})
        self.assertEqual({'authorization': 'Bearer token-1'}, self._echo(client, 'authorization'))
        self.assertEqual({'authorization': 'Bearer token-2'}, self._echo(client, 'authorization'))

    def test_call_metadata_context(self):
        client = self._client(metadata={'x-client': 'yes'})
        other = self._client()
        with plasm.call_metadata({'authorization': 'Bearer ctx'}):
            self.assertEqual({'authorization': 'Bearer ctx', 'x-client': 'yes'},
                             self._echo(client, 'authorization', 'x-client'))
            self.assertEqual({'authorization': 'Bearer ctx'}, self._echo(other, 'authorization'))

            with client.call_metadata(x_only_this_client='1'):  # Keyword underscores become dashes
                self.assertEqual({'x-only-this-client': '1'}, self._echo(client, 'x-only-this-client'))
                self.assertEqual({'x-only-this-client': None}, self._echo(other, 'x-only-this-client'))

            self.assertEqual({'x-only-this-client': None}, self._echo(client, 'x-only-this-client'))
        self.assertEqual({'authorization': None}, self._echo(other, 'authorization'))

    def test_repeated_keys_are_all_sent(self):
        client = self._client(metadata=[('x-multi', 'a'), ('x-multi', 'b')])
        with plasm.call_metadata({'x-multi': 'c'}):
            self.assertEqual({'x-multi': ['a', 'b', 'c']}, self._echo(client, 'x-multi'))

    def test_context_is_per_thread(self):
        client = self._client()
        results = {}
        started = threading.Event()
        release = threading.Event()

        def other_thread():
            started.set()
            release.wait(5)
            results['other'] = self._echo(client, 'authorization')

        t = threading.Thread(target=other_thread)
        t.start()
        started.wait(5)
        with plasm.call_metadata(authorization='Bearer mine'):
            release.set()
            t.join(5)
            results['mine'] = self._echo(client, 'authorization')
        self.assertEqual({'authorization': None}, results['other'])
        self.assertEqual({'authorization': 'Bearer mine'}, results['mine'])

    def test_failing_metadata_callable(self):
        def boom():
            raise RuntimeError('no token for you')
        with self.assertRaises(plasm.PreRequestError):
            self._client(metadata=boom).with_both('authorization')
