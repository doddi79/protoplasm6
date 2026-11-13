import datetime
import os
import subprocess
import sys
import unittest

from tests.testutils import *

from protoplasm6 import casting
from protoplasm6.casting import converters
from protoplasm6.casting import dictators

import logging
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


DIRECT = converters.DirectConverter()
DICT = converters.DictConverter()

NOW = datetime.datetime(2026, 11, 13, 12, 34, 56, 789012)


def _samples():
    """Dataclass instances that both converters should handle identically."""
    from sandbox.test import rainbow_dc, test_dc, enums_dc, anytest_dc, googlestruct_dc, timeduration_dc
    from sandbox.test import nested_dc, illnamedfields_dc, delta_dc, beta_dc, alpha_dc, converters_dc
    sub = rainbow_dc.SubMessage(foo='foo', bar='bar')
    simple = test_dc.Simple(my_string='s', my_float=1.5, my_double=2.25, my_int32=-32, my_int64=-2 ** 40,
                            my_uint32=32, my_uint64=2 ** 63, my_sint32=-7, my_sint64=-2 ** 50, my_fixed32=99,
                            my_fixed64=2 ** 60, my_sfixed32=-99, my_sfixed64=-2 ** 60, my_bool=True,
                            my_bytes=b'\x00\x01binary\xff')
    return [
        rainbow_dc.SubMessage(),
        sub,
        rainbow_dc.RainbowMessage(simple_field='x', message_field=sub, simple_list=['a', 'b'],
                                  message_list=[sub, rainbow_dc.SubMessage(foo='2')],
                                  simple_map={'k': 'v', 'k2': ''}, message_map={'m': sub, 'empty': rainbow_dc.SubMessage()}),
        rainbow_dc.RainbowMessage(message_field=rainbow_dc.SubMessage()),  # Empty but set sub message
        rainbow_dc.TimestampMessage(my_timestamp=NOW, my_timestamp_list=[NOW, NOW.replace(microsecond=0)],
                                    my_timestamp_map={'a': NOW}),
        rainbow_dc.BytesMessage(my_bytes=b'bytes', my_bytes_list=[b'a', b'', b'\xfe'], my_bytes_map={'x': b'y'}),
        simple,
        test_dc.SimpleList(my_string_list=['a', ''], my_int64_list=[1, 2 ** 62], my_uint64_list=[2 ** 64 - 1],
                           my_float_list=[0.5], my_double_list=[0.25, -1.0]),
        test_dc.SimpleMap(my_string_map={'a': 'b'}),
        test_dc.NestedDude(my_simple=simple),
        test_dc.NestedList(my_simple_list=[simple, test_dc.Simple()]),
        test_dc.NestedMap(my_string_simple_map={'s': simple}),
        test_dc.VeryNestedDude(my_nested_dude=test_dc.NestedDude(my_simple=simple), my_non_nested_simple=simple,
                               my_list_of_lists=[test_dc.NestedList(my_simple_list=[simple])]),
        enums_dc.WithExternalEnum(my_enum=enums_dc.ExternalEnum.TWO, my_alias_enum=enums_dc.ExternalAliasEnum.FIVE,
                                  my_enum_list=[enums_dc.ExternalEnum.ONE, enums_dc.ExternalEnum.ZERO_AND_DEFAULT],
                                  my_alias_enum_list=[enums_dc.ExternalAliasEnum.SIX],
                                  my_enum_map={'a': enums_dc.ExternalEnum.THREE},
                                  my_alias_enum_map={'b': enums_dc.ExternalAliasEnum.FOUR}),
        enums_dc.WithInternalEnum(my_internal_enum=enums_dc.WithInternalEnum.InternalEnum.FIVE,
                                  my_internal_alias_enum=enums_dc.WithInternalEnum.InternalAliasEnum.NINE,
                                  my_internal_enum_list=[enums_dc.WithInternalEnum.InternalEnum.SIX],
                                  my_internal_alias_enum_map={'x': enums_dc.WithInternalEnum.InternalAliasEnum.SEVEN}),
        anytest_dc.AnyMessage(my_any=sub, my_any_list=[simple, sub], my_any_map={'a': alpha_dc.AlphaMessage(my_string='a')}),
        googlestruct_dc.StructMessage(my_struct={'a': 1.0, 'b': 'two', 'c': [1.0, 'x', None, True], 'd': {'e': {}}}),
        googlestruct_dc.StructMessage(my_struct={'x': 'y'}, my_value='just a string'),
        googlestruct_dc.StructMessage(my_value={'nested': [1.0, 2.0]}),
        googlestruct_dc.StructMessage(my_value=None),
        timeduration_dc.DurationMessage(my_duration=datetime.timedelta(days=1, seconds=5, microseconds=250000),
                                        my_duration_list=[datetime.timedelta(seconds=1)],
                                        my_duration_map={'a': datetime.timedelta(minutes=5)}),
        nested_dc.OuterMessage(my_int=5, my_string='outer', my_message=nested_dc.OuterMessage.InnerMessage()),
        illnamedfields_dc.BadNames(False_='f', None_='n', class_='c', def_='d'),
        delta_dc.DeltaMessage(my_string='d', my_level_three_message=beta_dc.BetaMessage(
            my_foreign_message=alpha_dc.AlphaMessage(my_string='deep', my_number=3))),
        converters_dc.JsonValues(my_struct={'a': 'b'}, my_value=1.0, my_list_value=[1.0, 'two'],
                                 my_struct_map={'s': {'x': 1.0}}, my_value_list=[1.0, 'two', None, {'three': [3.0]}]),
        converters_dc.Everything(sub=sub, subs=[sub], sub_map={'s': sub}, when=NOW,
                                 how_long=datetime.timedelta(hours=1), whens=[NOW], blob=b'blob', blobs=[b'1', b'2'],
                                 big=2 ** 62, bigs=[1, 2], ratio=0.125, my_enum=enums_dc.ExternalEnum.TWO,
                                 my_alias_enums=[enums_dc.ExternalAliasEnum.FOUR, enums_dc.ExternalAliasEnum.SIX]),
        converters_dc.PresenceMessage(maybe_string='maybe', maybe_long=12, plain_string='plain',
                                      maybe_message=sub, choice_int=42),
        converters_dc.PresenceMessage(),
        converters_dc.PresenceMessage(choice_timestamp=NOW),
        converters_dc.PresenceMessage(choice_message=rainbow_dc.SubMessage()),
        converters_dc.PresenceMessage(choice_string='c', maybe_enum=enums_dc.ExternalEnum.ONE),
        converters_dc.Everything(presence=converters_dc.PresenceMessage(choice_string='c')),
    ]


def _direct_only_samples():
    """Dataclass instances the DictConverter can't handle (or handles wrong)
    but the DirectConverter should round trip."""
    from sandbox.test import rainbow_dc, converters_dc, enums_dc
    sub = rainbow_dc.SubMessage(foo='foo', bar='bar')
    return [
        # The DictConverter sends None for empty lists of google.protobuf.Value
        # which protobuf's ParseDict chokes on
        converters_dc.JsonValues(),
        converters_dc.JsonValues(my_value=None, my_struct={'a': None}),
        # The DictConverter gives str keys for int (and can't do bool) keys
        converters_dc.KeyedMaps(int_keys={1: 'one'}, long_keys={-(2 ** 40): sub}, bool_keys={False: 'no'},
                                timestamps={7: NOW}, enums={-1: enums_dc.ExternalEnum.THREE}),
    ]


class ConverterParityTest(unittest.TestCase):
    """The DirectConverter must produce the same results as the DictConverter
    (the reference implementation) wherever the DictConverter works right."""

    @classmethod
    def setUpClass(cls) -> None:
        build_new_protos()
        sys.path.append(BUILD_ROOT)
        from sandbox import load_symbols
        load_symbols()

    def setUp(self):
        self.maxDiff = None

    def test_dataclass_to_proto_parity(self):
        for dc in _samples():
            with self.subTest(dc=dc):
                direct = DIRECT.dataclass_to_proto(dc)
                reference = DICT.dataclass_to_proto(dc)
                self.assertEqual(reference, direct)
                self.assertEqual(reference.SerializeToString(deterministic=True),
                                 direct.SerializeToString(deterministic=True))

    def test_proto_to_dataclass_parity(self):
        for dc in _samples():
            with self.subTest(dc=dc):
                proto = DICT.dataclass_to_proto(dc)
                self.assertEqual(DICT.proto_to_dataclass(proto), DIRECT.proto_to_dataclass(proto))

    def test_round_trip(self):
        for dc in _samples() + _direct_only_samples():
            with self.subTest(dc=dc):
                self.assertEqual(dc, DIRECT.proto_to_dataclass(DIRECT.dataclass_to_proto(dc)))

    def test_proto_to_dataclass_of_given_type(self):
        from sandbox.test import rainbow_dc
        proto = rainbow_dc.SubMessage(foo='a').to_proto()
        self.assertEqual(rainbow_dc.SubMessage(foo='a'), DIRECT.proto_to_dataclass(proto, rainbow_dc.SubMessage))
        self.assertEqual(rainbow_dc.SubMessage(foo='a'), rainbow_dc.SubMessage.from_proto(proto))

    def test_presence_is_kept(self):
        from sandbox.test import converters_dc, converters_pb2
        dc = converters_dc.PresenceMessage(maybe_string='x', choice_int=7)
        p = DIRECT.dataclass_to_proto(dc)
        self.assertTrue(p.HasField('maybe_string'))
        self.assertFalse(p.HasField('maybe_message'))
        self.assertEqual('choice_int', p.WhichOneof('choice'))
        # NOTE: Since neobuilder6 gives `optional` scalars non-None defaults
        # (e.g. 0 for maybe_long) they're always marked as present (the
        # DictConverter does the same)
        self.assertTrue(p.HasField('maybe_long'))

        p = converters_pb2.PresenceMessage()
        p.maybe_message.SetInParent()
        dc = DIRECT.proto_to_dataclass(p)
        self.assertIsNotNone(dc.maybe_message)
        self.assertIsNone(DIRECT.proto_to_dataclass(converters_pb2.PresenceMessage()).maybe_message)

    def test_value_sentinels(self):
        from sandbox.test import googlestruct_dc
        unset = googlestruct_dc.StructMessage()
        self.assertIs(unset.my_value, ...)
        self.assertFalse(DIRECT.dataclass_to_proto(unset).HasField('my_value'))
        self.assertIs(DIRECT.proto_to_dataclass(DIRECT.dataclass_to_proto(unset)).my_value, ...)

        null = googlestruct_dc.StructMessage(my_value=None)
        self.assertTrue(DIRECT.dataclass_to_proto(null).HasField('my_value'))
        self.assertIsNone(DIRECT.proto_to_dataclass(DIRECT.dataclass_to_proto(null)).my_value)


class DirectConverterFixesTest(unittest.TestCase):
    """Cases where the DictConverter gets it wrong (or crashes) and the
    DirectConverter gets it right."""

    @classmethod
    def setUpClass(cls) -> None:
        build_new_protos()
        sys.path.append(BUILD_ROOT)

    def test_map_keys_keep_their_type(self):
        from sandbox.test import converters_dc, rainbow_dc, enums_dc
        dc = converters_dc.KeyedMaps(int_keys={1: 'one', -2: 'minus two'},
                                     long_keys={2 ** 40: rainbow_dc.SubMessage(foo='big')},
                                     bool_keys={True: 'yes', False: 'no'},
                                     enums={-5: enums_dc.ExternalEnum.TWO})
        back = DIRECT.proto_to_dataclass(DIRECT.dataclass_to_proto(dc))
        self.assertEqual(dc, back)
        self.assertEqual('one', back.int_keys[1])
        self.assertIsInstance(back.enums[-5], enums_dc.ExternalEnum)

        # The DictConverter turns int keys into strings...
        self.assertEqual({'1': 'one', '-2': 'minus two'},
                         DICT.proto_to_dataclass(DICT.dataclass_to_proto(converters_dc.KeyedMaps(
                             int_keys={1: 'one', -2: 'minus two'}))).int_keys)
        # ...and can't handle bool keys at all
        with self.assertRaises(Exception):
            DICT.dataclass_to_proto(converters_dc.KeyedMaps(bool_keys={True: 'yes'}))

    def test_string_map_keys_from_dict_converter_are_accepted(self):
        from sandbox.test import converters_dc
        dc = converters_dc.KeyedMaps(int_keys={'1': 'one'}, bool_keys={'true': 'yes'})
        p = DIRECT.dataclass_to_proto(dc)
        self.assertEqual('one', p.int_keys[1])
        self.assertEqual('yes', p.bool_keys[True])

    def test_oneofs(self):
        from sandbox.test import converters_dc, rainbow_dc
        self.assertIsNone(DIRECT.dataclass_to_proto(converters_dc.PresenceMessage()).WhichOneof('choice'))
        self.assertEqual('choice_timestamp',
                         DIRECT.dataclass_to_proto(converters_dc.PresenceMessage(choice_timestamp=NOW)).WhichOneof('choice'))
        self.assertEqual('choice_message', DIRECT.dataclass_to_proto(converters_dc.PresenceMessage(
            choice_message=rainbow_dc.SubMessage())).WhichOneof('choice'))
        # Setting a oneof member resets the others (like protobuf) so to get
        # two of them set we need to sneak past __setattr__
        both = converters_dc.PresenceMessage(choice_string='a')
        object.__setattr__(both, 'choice_int', 1)
        with self.assertRaises(ValueError):
            DIRECT.dataclass_to_proto(both)

    def test_timezone_aware_timestamps(self):
        from sandbox.test import rainbow_dc
        plus_five = datetime.timezone(datetime.timedelta(hours=5))
        dc = rainbow_dc.TimestampMessage(my_timestamp=datetime.datetime(2020, 1, 1, 12, 0, tzinfo=plus_five))
        self.assertEqual(datetime.datetime(2020, 1, 1, 7, 0), DIRECT.dataclass_to_proto(dc).my_timestamp.ToDatetime())


class LenientValuesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build_new_protos()
        sys.path.append(BUILD_ROOT)

    def test_values_parse_dict_accepts_are_accepted(self):
        from sandbox.test import converters_dc, enums_dc
        dc = converters_dc.Everything(big='123', bigs=['4', 5], ratio=1, my_enum='TWO')
        for converter in (DICT, DIRECT):
            with self.subTest(converter=converter):
                p = converter.dataclass_to_proto(dc)
                self.assertEqual(123, p.big)
                self.assertEqual([4, 5], list(p.bigs))
                self.assertEqual(1.0, p.ratio)
                self.assertEqual(enums_dc.ExternalEnum.TWO, p.my_enum)


class _ShoutingDictator(dictators.BaseDictator):
    @classmethod
    def to_dict_value(cls, dc_value, field, parent):
        return dc_value.upper() if dc_value else dc_value

    @classmethod
    def from_dict_value(cls, proto_value, field, parent_type):
        return proto_value.lower() if proto_value else proto_value


class FallbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build_new_protos()
        sys.path.append(BUILD_ROOT)

    def test_custom_dictators_use_the_dict_logic(self):
        import dataclasses
        from protoplasm6 import plasm
        from sandbox.test import rainbow_pb2

        @dataclasses.dataclass
        class Custom(plasm.DataclassBase):
            __proto_cls__ = rainbow_pb2.SubMessage
            foo: str = dataclasses.field(default='', metadata={'dictator': _ShoutingDictator})
            bar: str = dataclasses.field(default='', metadata={'dictator': dictators.BaseDictator})

        p = DIRECT.dataclass_to_proto(Custom(foo='quiet', bar='as is'))
        self.assertEqual('QUIET', p.foo)
        self.assertEqual('as is', p.bar)
        self.assertEqual(Custom(foo='quiet', bar='as is'), DIRECT.proto_to_dataclass(p, Custom))


class ConverterSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build_new_protos()
        sys.path.append(BUILD_ROOT)

    def tearDown(self):
        converters.set_converter(converters.DEFAULT_CONVERTER_NAME)

    def test_default_is_direct(self):
        if os.environ.get(converters.ENV_VAR_NAME):
            self.skipTest(f'{converters.ENV_VAR_NAME} is set')
        self.assertIsInstance(converters.get_converter(), converters.DirectConverter)

    def test_set_and_use_converter(self):
        converters.set_converter('dict')
        self.assertIsInstance(converters.get_converter(), converters.DictConverter)
        with converters.use_converter('direct'):
            self.assertIsInstance(converters.get_converter(), converters.DirectConverter)
            with converters.use_converter(DICT) as c:
                self.assertIs(DICT, c)
                self.assertIs(DICT, converters.get_converter())
            self.assertIsInstance(converters.get_converter(), converters.DirectConverter)
        self.assertIsInstance(converters.get_converter(), converters.DictConverter)

        with self.assertRaises(ValueError):
            converters.set_converter('nope')

    def test_conversions_use_the_current_converter(self):
        from sandbox.test import rainbow_dc
        calls = []

        class Spy(converters.DirectConverter):
            name = 'spy'

            def dataclass_to_proto(self, dc):
                calls.append('to')
                return super().dataclass_to_proto(dc)

            def proto_to_dataclass(self, proto, dataclass_type=None):
                calls.append('from')
                return super().proto_to_dataclass(proto, dataclass_type)

        converters.register_converter(Spy())
        with converters.use_converter('spy'):
            p = rainbow_dc.SubMessage(foo='x').to_proto()
            rainbow_dc.SubMessage.from_proto(p)
            casting.proto_to_dataclass(p)
            casting.dataclass_to_proto(rainbow_dc.SubMessage())
            rainbow_dc.SubMessage.from_protostr(p.SerializeToString())
        self.assertEqual(['to', 'from', 'from', 'to', 'from'], calls)

    def test_env_var(self):
        code = 'from protoplasm6.casting import converters; print(converters.get_converter().name)'
        for value, expected in (('dict', 'dict'), ('DIRECT', 'direct'), ('bogus', 'direct')):
            with self.subTest(value=value):
                env = dict(os.environ, **{converters.ENV_VAR_NAME: value})
                out = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True,
                                     cwd=PROJECT_ROOT)
                self.assertEqual(expected, out.stdout.strip(), out.stderr)
