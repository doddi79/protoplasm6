import datetime
import sys
import unittest

from tests.testutils import *

from protoplasm6.casting import converters

import logging
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

NOW = datetime.datetime(2026, 11, 14, 1, 2, 3)


class OneofTest(unittest.TestCase):
    """Issue #4 - Oneof support in dataclasses"""
    @classmethod
    def setUpClass(cls) -> None:
        build_new_protos()
        sys.path.append(BUILD_ROOT)

    def test_oneof_groups(self):
        from sandbox.test import converters_dc, rainbow_dc
        self.assertEqual({'choice': ('choice_string', 'choice_int', 'choice_message', 'choice_timestamp')},
                         converters_dc.PresenceMessage.oneof_groups())
        self.assertEqual({}, rainbow_dc.SubMessage.oneof_groups())

    def test_which_and_get_oneof(self):
        from sandbox.test import converters_dc, rainbow_dc
        p = converters_dc.PresenceMessage()
        self.assertIsNone(p.which_oneof('choice'))
        self.assertIsNone(p.get_oneof('choice'))
        self.assertEqual('nope', p.get_oneof('choice', 'nope'))

        p = converters_dc.PresenceMessage(choice_int=42)
        self.assertEqual('choice_int', p.which_oneof('choice'))
        self.assertEqual(42, p.get_oneof('choice'))

        sub = rainbow_dc.SubMessage()
        p = converters_dc.PresenceMessage(choice_message=sub)
        self.assertEqual('choice_message', p.which_oneof('choice'))
        self.assertIs(sub, p.get_oneof('choice'))

        with self.assertRaises(ValueError):
            p.which_oneof('not_a_group')

    def test_setting_a_member_resets_the_others(self):
        from sandbox.test import converters_dc, rainbow_dc
        p = converters_dc.PresenceMessage(choice_string='first')
        p.choice_timestamp = NOW
        self.assertEqual('', p.choice_string)
        self.assertEqual('choice_timestamp', p.which_oneof('choice'))

        p.choice_message = rainbow_dc.SubMessage(foo='x')
        self.assertIsNone(p.choice_timestamp)
        self.assertEqual('choice_message', p.which_oneof('choice'))

        # Setting the default (unset) value doesn't reset anything
        p.choice_int = 0
        self.assertEqual('choice_message', p.which_oneof('choice'))

        # Non-oneof fields aren't affected
        p.plain_string = 'plain'
        p.maybe_message = rainbow_dc.SubMessage()
        self.assertEqual('choice_message', p.which_oneof('choice'))

    def test_constructor_last_member_wins(self):
        from sandbox.test import converters_dc
        # Like protobuf messages, the last oneof member (in field order) wins
        p = converters_dc.PresenceMessage(choice_string='a', choice_int=7)
        self.assertEqual('choice_int', p.which_oneof('choice'))
        self.assertEqual('', p.choice_string)

    def test_clear_oneof(self):
        from sandbox.test import converters_dc
        p = converters_dc.PresenceMessage(choice_timestamp=NOW, plain_string='keep')
        p.clear_oneof('choice')
        self.assertIsNone(p.which_oneof('choice'))
        self.assertEqual(converters_dc.PresenceMessage(plain_string='keep'), p)

    def test_classes_without_oneofs_keep_the_plain_setattr(self):
        from sandbox.test import converters_dc, rainbow_dc
        self.assertIs(object.__setattr__, rainbow_dc.SubMessage.__setattr__)
        self.assertIsNot(object.__setattr__, converters_dc.PresenceMessage.__setattr__)

    def test_oneofs_with_both_converters(self):
        from sandbox.test import converters_dc, rainbow_dc
        for c in ('direct', 'dict'):
            for dc in (converters_dc.PresenceMessage(),
                       converters_dc.PresenceMessage(choice_int=3),
                       converters_dc.PresenceMessage(choice_message=rainbow_dc.SubMessage()),
                       converters_dc.PresenceMessage(choice_timestamp=NOW)):
                with self.subTest(converter=c, dc=dc), converters.use_converter(c):
                    proto = dc.to_proto()
                    self.assertEqual(dc.which_oneof('choice'), proto.WhichOneof('choice'))
                    self.assertEqual(dc, converters_dc.PresenceMessage.from_proto(proto))


class NoneMessagesThroughDictsTest(unittest.TestCase):
    """Issues #9 & #10 - None messages turning into empty ones via dicts"""
    @classmethod
    def setUpClass(cls) -> None:
        build_new_protos()
        sys.path.append(BUILD_ROOT)

    def test_none_messages_stay_none(self):
        from sandbox.test import converters_dc, rainbow_dc
        e = converters_dc.Everything(big=5)
        self.assertIsNone(e.sub)
        back = converters_dc.Everything.from_dict(e.to_dict())
        self.assertIsNone(back.sub)
        self.assertIsNone(back.presence)
        self.assertEqual([], back.subs)
        self.assertEqual({}, back.sub_map)
        self.assertEqual(e, back)
        self.assertEqual(e, converters_dc.Everything.from_json(e.to_json()))

        # ...while empty (but set) messages stay empty messages
        e = converters_dc.Everything(sub=rainbow_dc.SubMessage())
        self.assertEqual(rainbow_dc.SubMessage(), converters_dc.Everything.from_dict(e.to_dict()).sub)

    def test_from_clone_with_oneofs(self):
        from sandbox.test import converters_dc, rainbow_dc, clones_dc
        p = converters_dc.PresenceMessage(choice_message=rainbow_dc.SubMessage(foo='x'))
        clone = converters_dc.PresenceMessage.from_clone(p)
        self.assertEqual(p, clone)
        for c in ('direct', 'dict'):
            with self.subTest(converter=c), converters.use_converter(c):
                self.assertEqual('choice_message', clone.to_proto().WhichOneof('choice'))

        one = clones_dc.ThingOne(my_string='a', my_timestamp=NOW)
        two = clones_dc.ThingTwo.from_clone(one)
        self.assertIsNone(two.my_subthing)
        self.assertEqual(NOW, two.my_timestamp)
