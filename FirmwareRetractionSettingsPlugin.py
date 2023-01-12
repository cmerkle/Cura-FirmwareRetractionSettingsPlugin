# Copyright (c) 2022 cmerkle
# The FirmwareRetractionSettingsPlugin is released under the terms of the AGPLv3 or higher.

import re
from collections import OrderedDict

from UM.Extension import Extension
from UM.Application import Application
from UM.Settings.SettingDefinition import SettingDefinition
from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.ContainerRegistry import ContainerRegistry
from UM.Logger import Logger
from UM.Version import Version

import collections
import json
import os.path

from typing import List, Optional, Any, Dict, TYPE_CHECKING

class FirmwareRetractionSettingsPlugin(Extension):
    def __init__(self):
        super().__init__()

        self._application = Application.getInstance()

        self._i18n_catalog = None

        self._settings_dict = {}  # type: Dict[str, Any]
        self._expanded_categories = []  # type: List[str]  # temporary list used while creating nested settings

        try:
            api_version = self._application.getAPIVersion()
        except AttributeError:
            # UM.Application.getAPIVersion was added for API > 6 (Cura 4)
            # Since this plugin version is only compatible with Cura 3.5 and newer, and no version-granularity
            # is required before Cura 4.7, it is safe to assume API 5
            api_version = Version(5)

        if api_version < Version("7.3.0"):
            settings_definition_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firmware_retraction35.def.json")
        else:
            settings_definition_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firmware_retraction47.def.json")
        try:
            with open(settings_definition_path, "r", encoding = "utf-8") as f:
                self._settings_dict = json.load(f, object_pairs_hook = collections.OrderedDict)
        except:
            Logger.logException("e", "Could not load firmware retraction settings definition")
            return

        ContainerRegistry.getInstance().containerLoadComplete.connect(self._onContainerLoadComplete)

        self._application.getOutputDeviceManager().writeStarted.connect(self._filterGcode)


    def _onContainerLoadComplete(self, container_id):
        if not ContainerRegistry.getInstance().isLoaded(container_id):
            # skip containers that could not be loaded, or subsequent findContainers() will cause an infinite loop
            return

        try:
            container = ContainerRegistry.getInstance().findContainers(id = container_id)[0]
        except IndexError:
            # the container no longer exists
            return

        if not isinstance(container, DefinitionContainer):
            # skip containers that are not definitions
            return
        if container.getMetaDataEntry("type") == "extruder":
            # skip extruder definitions
            return

        try:
            travel_category = container.findDefinitions(key="travel")[0]
        except IndexError:
            Logger.log("e", "Could not find parent category setting to add settings to")
            return

        for setting_key in self._settings_dict.keys():
            setting_definition = SettingDefinition(setting_key, container, travel_category, self._i18n_catalog)
            setting_definition.deserialize(self._settings_dict[setting_key])

            # add the setting to the already existing travel settingdefinition
            travel_category._children.append(setting_definition)
            container._definition_cache[setting_key] = setting_definition

            self._expanded_categories = self._application.expandedCategories.copy()
            self._updateAddedChildren(container, setting_definition)
            self._application.setExpandedCategories(self._expanded_categories)
            self._expanded_categories = []  # type: List[str]
            container._updateRelations(setting_definition)

    def _updateAddedChildren(self, container: DefinitionContainer, setting_definition: SettingDefinition) -> None:
        children = setting_definition.children
        if not children or not setting_definition.parent:
            return

        # make sure this setting is expanded so its children show up  in setting views
        if setting_definition.parent.key in self._expanded_categories:
            self._expanded_categories.append(setting_definition.key)

        for child in children:
            container._definition_cache[child.key] = child
            self._updateAddedChildren(container, child)

    def _filterGcode(self, output_device):
        scene = self._application.getController().getScene()

        global_container_stack = self._application.getGlobalContainerStack()
        used_extruder_stacks = self._application.getExtruderManager().getUsedExtruderStacks()
        if not global_container_stack or not used_extruder_stacks:
            return

        # get setting from Cura
        initialize_firmware_retraction = global_container_stack.getProperty("initialize_firmware_retraction", "value")
        remove_zhops = global_container_stack.getProperty("remove_slicer_z_hops", "value")
        if not initialize_firmware_retraction:
            return

        retraction_amount = float(used_extruder_stacks[0].getProperty("retraction_amount", "value"))
        retraction_retract_speed = float(used_extruder_stacks[0].getProperty("retraction_retract_speed", "value"))
        retraction_prime_speed = float(used_extruder_stacks[0].getProperty("retraction_prime_speed", "value"))
        retraction_extra_prime_amount = float(used_extruder_stacks[0].getProperty("retraction_extra_prime_amount", "value"))
        retraction_hop_enabled = used_extruder_stacks[0].getProperty("retraction_hop_enabled", "value")
        retraction_hop = float(used_extruder_stacks[0].getProperty("retraction_hop", "value"))

        if not retraction_hop_enabled:
            retraction_hop = 0

        gcode_dict = getattr(scene, "gcode_dict", {})
        if not gcode_dict: # this also checks for an empty dict
            Logger.log("w", "Scene has no gcode to process")
            return

        dict_changed = False

        for plate_id in gcode_dict:
            gcode_list = gcode_dict[plate_id]
            if len(gcode_list) < 2:
                Logger.log("w", "Plate %s does not contain any layers", plate_id)
                continue

            if ";FIRMWARERETRACTIONPROCESSED\n" not in gcode_list[0]:

                firmwareRetraction = "M207 S%f F%d Z%f ; Added by FirmwareRetratcionSettingsPlugin\n" % (retraction_amount, int(retraction_retract_speed * 60), retraction_hop)
                firmwareRecover = "M208 S%f F%d ; Added by FirmwareRetratcionSettingsPlugin\n" % (retraction_extra_prime_amount, int(retraction_prime_speed * 60))

                z_hop_regex = re.compile(r"G[01]\sF\d*\sZ\d*\.?\d*.*")
 
                gcode_list[0] += ";FIRMWARERETRACTIONPROCESSED\n"
                gcode_list[1] += firmwareRetraction + firmwareRecover

                if remove_zhops:
                    for layer_nr, layer in enumerate(gcode_list):
                        lines = layer.split("\n")
                        lines_changed = False
                        for line_nr, line in enumerate(lines):
                            if "G10" in line and z_hop_regex.fullmatch(lines[line_nr + 1]):
                                lines[line_nr + 1] = '; Z HOP REMOVED BY FIRMWARE RETRACTION SETTINGS PLUGIN'
                            if "G11" in line and z_hop_regex.fullmatch(lines[line_nr - 1]):
                                lines[line_nr - 1] = '; Z HOP REMOVED BY FIRMWARE RETRACTION SETTINGS PLUGIN'
                            
                        gcode_list[layer_nr] = "\n".join(lines)


                gcode_dict[plate_id] = gcode_list
                dict_changed = True
            else:
                Logger.log("d", "Plate %s has already been processed", plate_id)
                continue

        if dict_changed:
            setattr(scene, "gcode_dict", gcode_dict)
