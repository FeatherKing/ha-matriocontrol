"""Constants for the Matrio Control integration."""

DOMAIN = "matriocontrol"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_ZONES = "zones"

# Default values
DEFAULT_PORT = 8899
DEFAULT_ZONES = 8

# Packet constants
PACKET_START = 0x82
PACKET_END = 0xCC
PACKET_FF = 0xFF

# Commands
CMD_POWER = 0x08
CMD_VOLUME = 0x01
CMD_MUTE = 0x0E
CMD_BALANCE = 0x0F
CMD_BASS = 0x10
CMD_TREBLE = 0x11
CMD_INPUT = 0x0D
CMD_ZONE_NAME = 0x13
CMD_INPUT_NAME = 0x14

# Zone selection patterns
ZONE_INDIVIDUAL = [0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02]
ZONE_GROUP_ALL = [0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01]

# Device information
DEVICE_MANUFACTURER = "Dayton Audio"
DEVICE_MODEL = "Matrio Control Compatible"

# Zone mappings
ZONES = {
    1: "Zone 1",
    2: "Zone 2", 
    3: "Zone 3",
    4: "Zone 4",
    5: "Zone 5",
    6: "Zone 6",
    7: "Zone 7",
    8: "Zone 8"
}

# Input mappings (fallback names, actual names come from device via ALLNAMES)
INPUTS = {
    1: "Input1",
    2: "Input2", 
    3: "Input3",
    4: "Input4",
    5: "Input5",
    6: "Input6",
    7: "Input7",
    8: "Input8"
}

# Volume range (0-38 as per MatrioController)
VOLUME_MIN = 0
VOLUME_MAX = 38

# Balance range (-100 to +100 as per MatrioController)
BALANCE_MIN = -100
BALANCE_MAX = 100

# Bass/Treble range (-12 to +12 as per MatrioController)
BASS_TREBLE_MIN = -12
BASS_TREBLE_MAX = 12

# Legacy input mappings (for backward compatibility)
INPUT_MAPPINGS = INPUTS