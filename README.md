# FirmwareRetractionSettingsPlugin

This plugin adds a setting named "Initialize Firmware Retraction" to the Travel category in the Custom print setup of Cura. The plugin inserts M207 and M208 commands after the start Gcode to set the firmware retraction parameters based on the current extruder 0 retraction settings in Cura. This plugin also removes redundant z hop commands from the Gcode added by Cura since firmware retraction handles z hop. Note that the retraction parameters used for the M207 and M208 commands are for extruder 0, as this plugin was only designed to be used for single extrusion printers. To enable linear advance for your printer in Cura to send G10 and G11 commands, you must add the "Printer Settings" plugin by fieldOfView found here: https://marketplace.ultimaker.com/app/cura/plugins/fieldofview/PrinterSettingsPlugin

For more information about Firmware Retraction, see the Marlin documentation: https://marlinfw.org/docs/features/fwretract.html#:~:text=When%20Automatic%20Firmware%20Retraction%20is%20enabled%20%28e.g.%2C%20with,firmware%20instead%20of%20those%20specified%20by%20the%20G-code.



