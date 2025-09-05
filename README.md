# Matrio Control

Home Assistant integration for Dayton Audio DAX88 multi-zone amplifier.

## Features

- **Multi-zone control**: Control up to 8 zones independently
- **Group operations**: Control multiple zones simultaneously
- **Input switching**: Switch between 8 different inputs
- **Audio controls**: Volume, mute, bass, treble, and balance
- **Zone naming**: Customize zone and input names
- **Media player entities**: Each zone appears as a media player

## Installation

### HACS (Recommended)

1. Add this repository to HACS
2. Install "Matrio Control"
3. Restart Home Assistant
4. Add integration via Configuration > Integrations

### Manual Installation

1. Copy the `matriocontrol` folder to your `custom_components` directory
2. Restart Home Assistant
3. Add integration via Configuration > Integrations

## Configuration

1. Go to Configuration > Integrations
2. Click "Add Integration"
3. Search for "Matrio Control"
4. Enter your DAX88 IP address and port (default: 8899)
5. Give your device a name

## Usage

After installation, you'll have:

- **Media Player entities** for each zone (power, volume, mute, input selection)
- **Number entities** for bass, treble, and balance controls
- **Group controls** for operating multiple zones simultaneously

## Protocol

This integration uses the reverse-engineered protocol from the Matrio mobile app:
- TCP connection on port 8899
- Binary packet format with zone selection patterns
- Support for individual and group operations

## Development

This integration was created by reverse engineering the Matrio mobile app's communication protocol with the DAX88 device.

## License

MIT License