# Matrio Control

Home Assistant integration for Dayton Audio multi-zone amplifiers using the Matrio Control protocol.

## 🎵 Features

### **Complete Zone Control**
- **8 Independent Zones**: Full control over each zone
- **Power Management**: Turn zones on/off individually
- **Volume Control**: 0-38 range with precise control
- **Audio Controls**: Balance (-100 to +100), Bass (-12 to +12), Treble (-12 to +12)
- **Mute Control**: Individual zone muting
- **Input Selection**: Choose from 8 available inputs per zone

### **Smart Device Integration**
- **Auto-Discovery**: Automatically detects device information
- **Dynamic Naming**: Uses actual device zone and input names
- **Real-time Updates**: Live status monitoring and control
- **Connection Monitoring**: Automatic reconnection on device issues

### **Rich Home Assistant Entities**
- **Media Players**: 8 media player entities (one per zone)
- **Switches**: 16 switch entities (power + mute per zone)
- **Number Controls**: 32 number entities (volume, balance, bass, treble per zone)
- **Select Dropdowns**: 8 select entities (input selection per zone)
- **Sensors**: Device status and zone information sensors
- **Text Inputs**: Zone and input name customization
- **Binary Sensors**: Connection status monitoring

## 🚀 Installation

### HACS (Recommended)

1. Add this repository to HACS
2. Install "Matrio Control"
3. Restart Home Assistant
4. Add integration via Configuration > Integrations

### Manual Installation

1. Copy the `matriocontrol` folder to your `custom_components` directory
2. Restart Home Assistant
3. Add integration via Configuration > Integrations

## ⚙️ Configuration

1. Go to **Configuration** > **Integrations**
2. Click **"Add Integration"**
3. Search for **"Matrio Control"**
4. Enter your device IP address and port (default: 8899)
5. Give your device a name

### Supported Devices
- **Dayton Audio DAX88** (tested)
- **Other Dayton Audio multi-zone amplifiers** using Matrio Control protocol

## 🎮 Usage

After installation, you'll have access to comprehensive control over your multi-zone amplifier:

### **Media Player Entities** (8 zones)
- **Power Control**: Turn zones on/off
- **Volume Control**: 0-100% slider (converted to 0-38 device range)
- **Mute Control**: Toggle mute for each zone
- **Input Selection**: Choose from available inputs
- **Source List**: Dynamic list of actual device input names

### **Switch Entities** (16 total)
- **Zone Power Switches**: Individual power control for each zone
- **Mute Switches**: Individual mute control for each zone

### **Number Entities** (32 total)
- **Volume Controls**: Precise volume control (0-38 range)
- **Balance Controls**: Left/right balance (-100 to +100)
- **Bass Controls**: Bass adjustment (-12 to +12)
- **Treble Controls**: Treble adjustment (-12 to +12)

### **Select Entities** (8 total)
- **Input Selection**: Dropdown menus for input selection
- **Dynamic Options**: Uses actual device input names

### **Sensor Entities** (9 total)
- **Device Status**: Connection status and device information
- **Zone Names**: Current zone names from device
- **Rich Attributes**: Device name, MAC address, firmware info

### **Text Entities** (16 total)
- **Zone Name Editing**: Rename zones directly in Home Assistant
- **Input Name Editing**: Rename inputs directly in Home Assistant

### **Binary Sensor** (1 total)
- **Connection Status**: Monitor device connectivity

## 🔧 Technical Details

### **Protocol Implementation**
This integration uses the reverse-engineered protocol from the Matrio mobile app:
- **TCP Connection**: Port 8899 for device communication
- **Binary Protocol**: Custom packet format with zone selection patterns
- **UPnP Integration**: Event subscriptions for device status
- **SOAP Commands**: Device initialization and control
- **Zone Selection**: Individual and group operation support

### **MatrioController Library**
- **Complete Implementation**: Full Python library for Matrio Control protocol
- **Device Agnostic**: Works with any Matrio Control compatible device
- **Error Handling**: Robust connection management and reconnection
- **Real-time Updates**: Live device status monitoring

### **Home Assistant Integration**
- **Coordinator Pattern**: Efficient data management and updates
- **Entity Platform**: Comprehensive entity coverage
- **Dynamic Configuration**: Auto-discovery of device capabilities
- **Error Recovery**: Automatic reconnection and error handling

## 🧪 Testing

The integration has been thoroughly tested with:
- **Zone 2 Comprehensive Testing**: All functions verified
- **Volume Control**: 0-38 range testing
- **Audio Controls**: Balance, bass, treble verification
- **Input Selection**: All 8 inputs tested
- **Power Management**: On/off functionality confirmed
- **Mute Control**: Individual zone muting verified

## 🛠️ Development

This integration was created by reverse engineering the Matrio mobile app's communication protocol with Dayton Audio multi-zone amplifiers. The implementation includes:

- **Protocol Analysis**: Network packet capture and analysis
- **Binary Protocol**: Custom packet format implementation
- **UPnP Integration**: Event subscription handling
- **Home Assistant Integration**: Complete entity implementation

## 📄 License

MIT License

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## 📞 Support

For support, please open an issue on the GitHub repository with:
- Device model and firmware version
- Home Assistant version
- Integration logs
- Description of the issue