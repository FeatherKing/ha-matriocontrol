# Matrio Control

Home Assistant integration for Dayton Audio multi-zone amplifiers using the Matrio Control protocol. This project is not officially supported by Dayton Audio and could break with future firmware updates.

## 🎵 Features

### **Control your device over TCP/IP instead of Serial**
- **No Extra Device Required for Control**: Many integrations for Xantech/Dayton Audio require usb-to-serial connections. This integration controls devices over the network instead.

### **Real-time control**
- This integration makes a connection and then listens to the device for broadcasts. Broadcasts on 8899 are decoded and Home Assistant entities are updated immediately.

### **Complete Device Control**
- **Configurable Number of Zones**: Full control over each zone
- **Power Management**: Turn zones on/off
- **Volume Control**: 0-38 range with precise control
- **Audio Controls**: Balance (-100 to +100), Bass (-12 to +12), Treble (-12 to +12)
- **Mute Control**: Individual zone muting
- **Input Selection**: Set inputs for each zone

### **Complete device control**
- **Dynamic Naming**: Uses actual device zone and input names
- **Real-time Updates**: Live status monitoring and control
- **Connection Monitoring**: Automatic reconnection on device issues

### **Rich Home Assistant Entities**
- **Media Players**: Media player entities for each zone (with Power, Volume, Mute, Source select)
- **Number Controls**: Balance, Bass, Treble per zone
- **Binary Sensors**: Connection status monitoring

## 🚀 Installation

### HACS (Recommended)

1. Add this repository to HACS
2. Install "Matrio Control"
3. Restart Home Assistant
4. Add integration via Configuration > Integrations

### HACS (Manual Repository Add, allows easy updates)

1. Install HACS
2. Add https://github.com/featherking/ha-matriocontrol as a custom repository
    1. use the Integation type
3. In Home Assitant, go to Device & Settings > Integrations > + Integration > Select Matrio Control

### Manual Installation

1. Copy the `matriocontrol` folder to your `custom_components` directory
2. Restart Home Assistant
3. Add integration via Configuration > Integrations

## ⚙️ Configuration

1. Go to **Configuration** > **Integrations**
2. Click **"Add Integration"**
3. Search for **"Matrio Control"**
4. Enter your device IP address and port (default: 8899)
5. Give your device a name (this name is only used in Home Assistant)
    1. Zone and Input names will be gathered from the device

### Supported Devices
- **Dayton Audio DAX88**

## Untested but Should Work
- **Other Dayton Audio multi-zone amplifiers** using Matrio Control protocol

## 📄 License

MIT License

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## 📞 Support

For support, please open an issue on the GitHub repository with:
- Device model and firmware version
- Home Assistant version
- Debug logs
- Description of the issue
