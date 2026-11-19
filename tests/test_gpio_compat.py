"""Tests for the gpiod v1/v2 compatibility layer in misc.py.

Injects fake gpiod modules shaped like each API version into sys.modules
and imports misc against them, so the tests run on any machine.
Run: python -m unittest discover -s tests
"""
import enum
import importlib
import os
import sys
import types
import unittest

PKG_DIR = os.path.join(os.path.dirname(__file__), '..', 'rockpi-quad',
                       'usr', 'bin', 'rockpi-quad')


class FakeV2:
    """Module shaped like gpiod 2.x."""

    def __init__(self):
        self.opened_chips = []
        self.requests = []

        # Plain Enum like the real gpiod.line.Value: no int() support,
        # but __bool__ is defined.
        class Value(enum.Enum):
            INACTIVE = 0
            ACTIVE = 1

            def __bool__(self):
                return self == Value.ACTIVE

        line = types.SimpleNamespace(
            Direction=enum.Enum('Direction', 'INPUT OUTPUT'),
            Value=Value,
        )

        class LineSettings:
            def __init__(self, direction=None, output_value=None):
                self.direction = direction
                self.output_value = output_value

        class Request:
            def __init__(self, consumer, config):
                self.consumer = consumer
                self.config = config
                self.values = {
                    off: settings.output_value
                    for off, settings in config.items()
                }

            def set_value(self, offset, value):
                self.values[offset] = value

            def get_value(self, offset):
                return self.values[offset]

        class Chip:
            def __init__(self, path):
                FakeV2.instance.opened_chips.append(path)
                self.path = path

            def request_lines(self, config, consumer=None):
                req = Request(consumer, config)
                FakeV2.instance.requests.append(req)
                return req

        self.line = line
        self.LineSettings = LineSettings
        self.Chip = Chip
        FakeV2.instance = self


class FakeV1:
    """Module shaped like gpiod 1.x."""

    def __init__(self):
        self.opened_chips = []
        self.lines = []
        self.LINE_REQ_DIR_OUT = 2

        class Line:
            def __init__(self, offset):
                self.offset = offset
                self.requested = None
                self.value = None

            def request(self, consumer, type):
                self.requested = (consumer, type)

            def set_value(self, value):
                self.value = value

            def get_value(self):
                return self.value

        class Chip:
            def __init__(self, path):
                FakeV1.instance.opened_chips.append(path)
                self.path = path

            def get_line(self, offset):
                line = Line(offset)
                FakeV1.instance.lines.append(line)
                return line

        self.Chip = Chip
        FakeV1.instance = self


def import_misc(fake):
    sys.modules.pop('misc', None)
    sys.modules['gpiod'] = fake
    sys.path.insert(0, PKG_DIR)
    try:
        return importlib.import_module('misc')
    finally:
        sys.path.remove(PKG_DIR)


class ChipPathTest(unittest.TestCase):
    def test_forms(self):
        misc = import_misc(FakeV1())
        self.assertEqual(misc.chip_path('0'), '/dev/gpiochip0')
        self.assertEqual(misc.chip_path('gpiochip0'), '/dev/gpiochip0')
        self.assertEqual(misc.chip_path('/dev/gpiochip4'), '/dev/gpiochip4')


class OutputLineV2Test(unittest.TestCase):
    def test_request_and_values(self):
        fake = FakeV2()
        misc = import_misc(fake)
        self.assertTrue(misc.GPIOD_V2)

        line = misc.OutputLine('0', 17, consumer='hat_button', value=1)
        self.assertEqual(fake.opened_chips, ['/dev/gpiochip0'])
        (req,) = fake.requests
        self.assertEqual(req.consumer, 'hat_button')
        (settings,) = req.config.values()
        self.assertEqual(settings.direction, fake.line.Direction.OUTPUT)
        self.assertEqual(settings.output_value, fake.line.Value.ACTIVE)
        self.assertEqual(line.get_value(), 1)

        line.set_value(0)
        self.assertEqual(line.get_value(), 0)
        self.assertIs(req.values[17], fake.line.Value.INACTIVE)


class OutputLineV1Test(unittest.TestCase):
    def test_request_and_values(self):
        fake = FakeV1()
        misc = import_misc(fake)
        self.assertFalse(misc.GPIOD_V2)

        line = misc.OutputLine('/dev/gpiochip4', 25, consumer='SATA_LINE_1',
                               value=1)
        self.assertEqual(fake.opened_chips, ['/dev/gpiochip4'])
        (raw,) = fake.lines
        self.assertEqual(raw.offset, 25)
        self.assertEqual(raw.requested,
                         ('SATA_LINE_1', fake.LINE_REQ_DIR_OUT))
        self.assertEqual(line.get_value(), 1)

        line.set_value(0)
        self.assertEqual(line.get_value(), 0)


if __name__ == '__main__':
    unittest.main()
