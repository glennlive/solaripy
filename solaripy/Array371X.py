#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Support for Array 371X Electronic Loads

    http://www.array.sh/download/371X%20User%27s%20Manual.pdf
    http://www.array.sh/download/Communication%20protocol%20for%20electronic%20load.pdf

                    Valid Ranges        Scale
    Current         0 - 30 A            x1000
    Voltage         0 - 360 V           x1000
    Power           0 - 200 W           x10
    Resistance      0 - 500 Ohm         x100
    Duration        0 - 65535 sec       x1

"""
import logging
from construct import *

"""
Define the Array Protocol with construct library.
Improvements for later:
 - Add support for programming sequences
 - Perhaps someday this should be refactored to use an EmbeddedSwitch and combine the commands?
 - Maybe also improve usage of construct to not need a named "fields" to get RawCopy?
"""

ARRAYCMD_SET = Struct(
    "fields" / RawCopy(Struct(
        "start" / Const(0xAA, Byte),
        "address" / Byte,
        "command" / Const(0x90, Byte),
        "max_current" / Default(Int16ul, 0),
        "max_power" / Default(Int16ul, 0),
        "new_address" / Byte,
        "type" / Enum(Byte, current=1, power=2, resistance=3),
        "value" / Default(Int16ul, 0),
        Padded(14, Pass)
    )),
    "checksum" / Checksum(Byte,
        lambda data: 0xff & sum([x for x in data]), this.fields.data))

ARRAYCMD_GET = Struct(
    "fields" / RawCopy(Struct(
        "start" / Const(0xAA, Byte),
        "address" / Byte,
        "command" / Const(0x91, Byte),
        "current" / Default(Int16ul, 0),
        "voltage" / Default(Int32ul, 0),
        "power" / Default(Int16ul, 0),
        "max_current" / Default(Int16ul, 0),
        "max_power" / Default(Int16ul, 0),
        "resistance" / Default(Int16ul, 0),
        "state" / BitStruct(
            Padding(2),
            "excessive_current" / Default(Flag, False),
            "excessive_voltage" / Default(Flag, False),
            "excessive_temperature" / Default(Flag, False),
            "incorrect_polarity" / Default(Flag, False),
            "enabled" / Default(Flag, False),
            "remote" / Default(Flag, False),
        ),
        Padded(7, Pass)
)),
"checksum" / Checksum(Byte,
        lambda data: 0xff & sum([x for x in data]), this.fields.data))

ARRAYCMD_STATE = Struct(
    "fields" / RawCopy(Struct(
        "start" / Const(0xAA, Byte),
        "address" / Byte,
        "command" / Const(0x92, Byte),
        "state" / BitStruct(
            Padding(6),
            "remote" / Default(Flag, True),
            "enabled" / Default(Flag, False),
        ),
        Padded(21, Pass),
    )),
    "checksum" / Checksum(Byte,
        lambda data: 0xff & sum([x for x in data]), this.fields.data))


class DeviceProperty:
        def __init__(self, name):
            self.name = name

        def __get__(self, obj, owner):
            if self.name in ["enabled", "remote"]:
                ret = obj.device_state
                return obj.device_state.get("state").get(self.name, None)
            return obj.device_state.get(self.name, None)

        def __set__(self, obj, value):
            obj.device_state = {self.name: value}


class ScalingLimitor:
    """
    A simple descriptor that scales a value, and scales it.
    """
    def __init__(self, name, min_v, max_v, scale, units=None):
        self.name = name
        self.min = float(min_v)
        self.max = float(max_v)
        self.scale = float(scale)
        self.__doc__ = "Get/set %s, valid input %d and %d %s" % (
            name, min_v, max_v, units)

    def __get__(self, obj, objtype):
        return obj.device_state[self.name] / self.scale

    def __set__(self, obj, value):
        val = max(self.min, min(self.max, value)) * self.scale
        obj.device_state = {self.name: int(val)}

class Array371X:
    """
    Electronic Loads From Array.
    """

    def __new__(cls, stream, address, **kwargs):
        """
        Note: valid streams require read() and write() interface
        """
        try:
            if callable(stream.write) and callable(stream.read):
                return object.__new__(cls)
        except Exception as err:
            logging.error(err)
            raise TypeError("Inavlid 'stream', must support read() and write().")
        return None

    def __init__(self, stream, address, **kwargs):
        """
        Create Array3710a object.

        Currently this supports configuration and readback, but does not
        implement control of the built-in sequences.

        One should set max_power and max_current before enabling the load.

        Params:
            stream      an object supporting read() and write(). Ex: a pySerial Serial object
            address     the address of the Array370a (0x00-0xFE)
        """

        try:
            self._addr = int(address)
        except ValueError:
            logging.error("Invalid address: {}".format(address))
            self._addr = 0

        # stream was verified in __new__
        self._stream = stream
        if hasattr(stream, 'timeout'):
            stream.timeout = 1  # don't wait forever...

        # need to keep track of max_current / max_power
        self.max_power = 0
        self.max_current = 0


    @property
    def device_state(self):
        """ communicate with device and get state """
        cmd = ARRAYCMD_GET.build({"fields": {"value": dict(address=self._addr)}})
        self._stream.write(cmd)
        response = self._stream.read(26)
        logging.debug("Read: {}".format(["%02x" % x for x in response]))
        try:
            response = ARRAYCMD_GET.parse(response)
        except Exception as err:
            logging.error(err)
            return None
        return dict(response["fields"]["value"])

    @device_state.setter
    def device_state(self, kwdict):
        for key, value in kwdict.items():
            set_types = {"current": 1,
                         "power": 2,
                         "resistance": 3}

            if key in ["enabled", "remote"]:
                cmd = ARRAYCMD_STATE.build({"fields": {"value": {
                    "address":self._addr,
                    "state":{key:value}}}})
                self._stream.write(cmd)
            elif key in set_types:
                cmd = ARRAYCMD_SET.build({"fields": {"value": dict(
                    address=self._addr,
                    new_address=self._addr,
                    max_power=self.max_power,
                    max_current=self.max_current,
                    value=value,
                    type=set_types[key]
                )}})
                self._stream.write(cmd)
            else:
                # should be for new address settings...
                pass

    # properties via descriptors
    current = ScalingLimitor("current", 0, 30, 1000, "Amps")
    voltage = ScalingLimitor("voltage", 0, 360, 1000, "Volts")
    resistance = ScalingLimitor("resistance", 0, 500, 100, "Ohms")
    power = ScalingLimitor("power", 0, 200, 10, "Watts")
    duration = ScalingLimitor("duration", 0, 65535, 1, "Seconds")

    enabled = DeviceProperty("enabled")
    remote = DeviceProperty("remote")
