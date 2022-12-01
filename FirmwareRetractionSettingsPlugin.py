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

class FirmwareRetractionSettingsPlugin(Extension):
    def __init__(self):
        super().__init__()

        self._application = Application.getInstance()

        self._i18n_catalog = None

        self._settings_dict = OrderedDict()
        self._settings_dict["initialize_firmware_retraction"] = {
            "label": "Initialize Firmware Retraction",
            "description": "Add M207 and M208 commands to start Gcode to setup firmware retraction settings.",
            "type": "bool",
            "default_value": False,
            "value": False,
            "settable_per_mesh": False,
            "settable_per_extruder": False,
            "settable_per_meshgroup": False
        }

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

        travel_category = container.findDefinitions(key="travel")
        firmware_retraction_setting = container.findDefinitions(key=list(self._settings_dict.keys())[0])
        if travel_category and not firmware_retraction_setting:
            # this machine doesn't have a firmware retraction setting yet
            travel_category = travel_category[0]
            for setting_key, setting_dict in self._settings_dict.items():

                definition = SettingDefinition(setting_key, container, travel_category, self._i18n_catalog)
                definition.deserialize(setting_dict)

                # add the setting to the already existing travel settingdefinition
                travel_category._children.append(definition)
                container._definition_cache[setting_key] = definition
                container._updateRelations(definition)


    def _filterGcode(self, output_device):
        scene = self._application.getController().getScene()

        global_container_stack = self._application.getGlobalContainerStack()
        used_extruder_stacks = self._application.getExtruderManager().getUsedExtruderStacks()
        if not global_container_stack or not used_extruder_stacks:
            return

        # get setting from Cura
        initialize_firmware_retraction = global_container_stack.getProperty("initialize_firmware_retraction", "value")
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
