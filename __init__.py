# Copyright (c) 2022 cmerkle
# The FirmwareRetractionSettingsPlugin is released under the terms of the AGPLv3 or higher.

from . import FirmwareRetractionSettingsPlugin


def getMetaData():
    return {}

def register(app):
    return {"extension": FirmwareRetractionSettingsPlugin.FirmwareRetractionSettingsPlugin()}
