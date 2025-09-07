#!/usr/bin/env python3
"""
Standalone Live Broadcast Packet Decoder Test Script - Version 3

Fixed zone detection - zones are 0-based in the pattern but displayed as 1-based.
"""

import sys
import socket
import time
import threading
from typing import Dict, Any, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
_LOGGER = logging.getLogger(__name__)

class UniversalHNGSyncDecoder:
    """Universal HNG sync packet decoder that handles both 68-byte and 96-byte packets"""
    
    def __init__(self):
        self.zones = {}
        
    def decode_hng_sync_packet(self, packet_hex: str, input_mappings: Dict[int, str]) -> Dict[str, Any]:
        """Decode a complete HNG sync packet - automatically detects packet size"""
        packet = bytes.fromhex(packet_hex)
        
        result = {
            'packet_length': len(packet),
            'packet_type': '68-byte' if len(packet) == 68 else '96-byte' if len(packet) == 96 else f'{len(packet)}-byte',
            'zones': {}
        }
        
        # Determine HNG section start based on packet size
        if packet.startswith(b'\x82\x0c'):
            hng_start = 0  # Extracted HNG packet: HNG section starts at byte 0
        elif len(packet) == 96:
            hng_start = 28  # Full 96-byte packet: HNG section starts at byte 28
        elif len(packet) == 68:
            hng_start = 0   # 68-byte packet: HNG section starts at byte 0
        else:
            _LOGGER.warning("Unknown packet size %d bytes", len(packet))
            hng_start = 0
        
        # Decode each zone
        for zone in range(8):
            zone_num = zone + 1
            zone_data = self.decode_zone(zone, packet, hng_start, len(packet), input_mappings)
            result['zones'][zone_num] = zone_data
        
        return result
    
    def decode_zone(self, zone: int, packet: bytes, hng_start: int, packet_size: int, input_mappings: Dict[int, str]) -> Dict[str, Any]:
        """Decode individual zone data based on packet size"""
        
        # Input state
        if packet_size == 96:
            input_start = hng_start + 2  # bytes 2-9 in HNG section
        else:  # 68-byte packet
            input_start = hng_start + 2  # bytes 2-9
        input_val = packet[input_start + zone]
        input_name = self.decode_input_selection(input_val, input_mappings)
        
        # Volume state
        if packet_size == 96:
            volume_start = hng_start + 10  # bytes 10-17 in HNG section
        else:  # 68-byte packet
            volume_start = hng_start + 10  # bytes 10-17
        volume_val = packet[volume_start + zone]
        volume = self.decode_volume_level(volume_val)
        
        # Power state
        if packet_size == 96:
            power_start = hng_start + 44  # bytes 44-51 in HNG section
        else:  # 68-byte packet
            power_start = hng_start + 50  # bytes 50-57
        power_val = packet[power_start + zone]
        power = self.decode_power_state(power_val, packet_size)
        
        # Balance state
        balance_start = hng_start + 34
        balance_val = packet[balance_start + zone]
        balance = self.decode_balance_state(balance_val, packet_size)
        
        # Mute state
        if packet_size == 96:
            mute_start = hng_start + 52  # bytes 52-59 in HNG section
        else:  # 68-byte packet
            mute_start = hng_start + 28  # bytes 28-35
        mute_val = packet[mute_start + zone]
        mute = self.decode_mute_state(mute_val, packet_size)
        
        # Bass and treble state
        bass, treble = self.decode_bass_treble(zone, packet, hng_start, packet_size)
        
        # Get raw bass and treble values for raw_data
        bass_start = self.get_bass_start(hng_start, packet_size)
        treble_start = self.get_treble_start(hng_start, packet_size)
        bass_val = packet[bass_start + zone]
        treble_val = packet[treble_start + zone]
        
        return {
            'zone_id': zone + 1,
            'power': power,
            'input': input_name,
            'volume': volume,
            'balance': balance,
            'mute': mute,
            'bass': bass,
            'treble': treble,
            'raw_data': {
                'power': f"0x{power_val:02x}",
                'input': f"0x{input_val:02x}",
                'volume': f"0x{volume_val:02x}",
                'balance': f"0x{balance_val:02x}",
                'mute': f"0x{mute_val:02x}",
                'bass': f"0x{bass_val:02x}",
                'treble': f"0x{treble_val:02x}"
            }
        }
    
    def decode_power_state(self, power: int, packet_size: int) -> str:
        """Decode zone power state based on packet size"""
        if packet_size == 96:
            if power == 0x02:
                return "ON"
            elif power == 0x01:
                return "OFF"
            else:
                return f"UNKNOWN(0x{power:02x})"
        else:
            if power == 0x01:
                return "ON"
            elif power == 0x02:
                return "OFF"
            else:
                return f"UNKNOWN(0x{power:02x})"
    
    def decode_input_selection(self, input_val: int, input_mappings: Dict[int, str]) -> str:
        """Decode zone input selection using device-provided input mappings"""
        result = input_mappings.get(input_val, f"UNKNOWN(0x{input_val:02x})")
        return result
    
    def decode_volume_level(self, volume: int) -> int:
        """Decode zone volume level (with +1 offset)"""
        ui_volume = volume - 1
        return max(0, ui_volume)
    
    def decode_balance_state(self, balance: int, packet_size: int) -> str:
        """Decode zone balance state based on differential analysis"""
        if balance == 0x3d:
            return "MAX Right"
        elif balance == 0x1f:
            return "Default"
        elif balance == 0x01:
            return "MAX Left"
        else:
            if 0x01 <= balance <= 0x3d:
                ui_value = int((balance - 0x01) / (0x3d - 0x01) * 200) - 100
                return str(ui_value)
            else:
                return f"UNKNOWN(0x{balance:02x})"
    
    def decode_mute_state(self, mute: int, packet_size: int) -> str:
        """Decode zone mute state based on packet size"""
        if packet_size == 96:
            if mute == 0x01:
                return "DEFAULT"
            elif mute == 0x02:
                return "MUTED"
            else:
                return f"UNKNOWN(0x{mute:02x})"
        else:
            if mute == 0x0d:
                return "DEFAULT"
            elif mute == 0x02:
                return "MUTED"
            else:
                return f"UNKNOWN(0x{mute:02x})"
    
    def get_bass_start(self, hng_start: int, packet_size: int) -> int:
        """Get the starting byte position for bass data"""
        return hng_start + 26
    
    def get_treble_start(self, hng_start: int, packet_size: int) -> int:
        """Get the starting byte position for treble data"""
        return hng_start + 18
    
    def decode_bass_treble(self, zone: int, packet: bytes, hng_start: int, packet_size: int) -> tuple[int, int]:
        """Decode bass and treble values from HNG sync packet"""
        bass_start = self.get_bass_start(hng_start, packet_size)
        treble_start = self.get_treble_start(hng_start, packet_size)
        
        bass_val = packet[bass_start + zone]
        treble_val = packet[treble_start + zone]
        
        bass = bass_val - 0x0d if 0x01 <= bass_val <= 0x19 else 0
        treble = treble_val - 0x0d if 0x01 <= treble_val <= 0x19 else 0
        
        return bass, treble

class BroadcastDecoder:
    """Decodes broadcast packets from Matrio device"""
    
    def __init__(self, input_mappings: Dict[int, str]):
        self.input_mappings = input_mappings
        
    def decode_packet(self, packet_hex: str) -> Optional[Dict[str, Any]]:
        """Decode any packet - either broadcast or command echo"""
        try:
            packet = bytes.fromhex(packet_hex)
            
            # Check if this is a command echo packet (starts with 18961820)
            if len(packet) >= 4 and packet[:4] == b'\x18\x96\x18\x20':
                return self._decode_command_echo_packet(packet)
            
            # Check if this is a direct broadcast packet (starts with 82)
            elif len(packet) >= 3 and packet[0] == 0x82:
                return self._decode_direct_broadcast_packet(packet)
            
            return None
                
        except Exception as e:
            _LOGGER.error(f"Failed to decode packet: {e}")
            return None
    
    def _decode_command_echo_packet(self, packet: bytes) -> Optional[Dict[str, Any]]:
        """Decode command echo packet to extract the actual command"""
        try:
            # Extract payload (skip header + length + data = 20 bytes)
            if len(packet) < 20:
                return None
                
            payload = packet[20:]
            
            # Look for MCU+PAS+ (4d43552b5041532b) + command
            if len(payload) < 10 or payload[:8] != b'MCU+PAS+':
                return None
                
            # Extract command part (skip MCU+PAS+)
            command_part = payload[8:]
            
            if len(command_part) < 2:
                return None
                
            command = command_part[1]  # Skip 0x82, get command
            
            # Extract the actual broadcast data (skip 0x82 + command)
            if len(command_part) < 10:
                return None
                
            broadcast_data = command_part[2:10]  # 8 bytes: value + zone pattern
            
            # Decode based on command type
            return self._decode_command_data(command, broadcast_data)
            
        except Exception as e:
            _LOGGER.error(f"Failed to decode command echo packet: {e}")
            return None
    
    def _decode_direct_broadcast_packet(self, packet: bytes) -> Optional[Dict[str, Any]]:
        """Decode direct broadcast packet"""
        if len(packet) < 11:
            return None
            
        command = packet[1]
        broadcast_data = packet[2:10]  # 8 bytes: value + zone pattern
        
        return self._decode_command_data(command, broadcast_data)
    
    def _decode_command_data(self, command: int, data: bytes) -> Optional[Dict[str, Any]]:
        """Decode command data based on command type"""
        if len(data) < 8:
            return None
            
        # Extract value (first byte) and zone pattern (remaining 7 bytes)
        value = data[0]
        zone_pattern = data[1:8]  # 7 bytes for zones 1-7 (0-based indexing)
        
        # Find which zones are affected (0-based indexing)
        affected_zones = []
        for i, zone_val in enumerate(zone_pattern):
            if zone_val == 0x01:
                affected_zones.append(i + 1)  # Convert to 1-based for display
        
        # Decode based on command type
        if command == 0x08:  # Power command
            power_on = value == 0x02  # 0x02 = ON, 0x01 = OFF (inverted from what I initially thought)
            return {
                "type": "power",
                "zones": affected_zones,
                "power_on": power_on,
                "raw_command": f"0x{command:02x}",
                "raw_data": data.hex()
            }
            
        elif command == 0x01:  # Volume command
            volume = max(0, value - 1)  # Convert from device value to UI value
            return {
                "type": "volume",
                "zones": affected_zones,
                "volume": volume,
                "raw_command": f"0x{command:02x}",
                "raw_data": data.hex()
            }
            
        elif command == 0x0e:  # Mute command
            is_muted = value == 0x02
            return {
                "type": "mute",
                "zones": affected_zones,
                "muted": is_muted,
                "raw_command": f"0x{command:02x}",
                "raw_data": data.hex()
            }
            
        elif command == 0x0d:  # Input selection command
            input_id = value
            input_name = self.input_mappings.get(input_id, f"Input {input_id}")
            return {
                "type": "input",
                "zones": affected_zones,
                "input_id": input_id,
                "input_name": input_name,
                "raw_command": f"0x{command:02x}",
                "raw_data": data.hex()
            }
            
        elif command == 0x05:  # Balance command
            balance = self._decode_balance_value(value)
            return {
                "type": "balance",
                "zones": affected_zones,
                "balance": balance,
                "raw_command": f"0x{command:02x}",
                "raw_data": data.hex()
            }
            
        elif command == 0x03:  # Bass command
            bass = value - 0x0d if 0x01 <= value <= 0x19 else 0
            return {
                "type": "bass",
                "zones": affected_zones,
                "bass": bass,
                "raw_command": f"0x{command:02x}",
                "raw_data": data.hex()
            }
            
        elif command == 0x02:  # Treble command
            treble = value - 0x0d if 0x01 <= value <= 0x19 else 0
            return {
                "type": "treble",
                "zones": affected_zones,
                "treble": treble,
                "raw_command": f"0x{command:02x}",
                "raw_data": data.hex()
            }
            
        elif command == 0x10:  # Total volume command
            volume = max(0, value - 1)
            return {
                "type": "total_volume",
                "zones": affected_zones,
                "volume": volume,
                "raw_command": f"0x{command:02x}",
                "raw_data": data.hex()
            }
        
        return None
    
    def _decode_balance_value(self, value: int) -> int:
        """Decode balance value from device format to UI format"""
        if value == 0x3d:
            return 100  # Max right
        elif value == 0x1f:
            return 0    # Center
        elif value == 0x01:
            return -100 # Max left
        else:
            # Linear interpolation
            if 0x01 <= value <= 0x3d:
                return int((value - 0x01) / (0x3d - 0x01) * 200) - 100
            else:
                return 0

class MatrioController:
    """Simplified Matrio controller for testing"""
    
    def __init__(self, ip: str, port: int = 8899):
        self.ip = ip
        self.port = port
        self.socket = None
        self.hng_decoder = UniversalHNGSyncDecoder()
        
        # Default input mapping
        self.inputs = {
            1: "TV", 2: "Google Music", 3: "Input3", 4: "Input4",
            5: "Input5", 6: "Input6", 7: "Input7", 8: "Wi-Fi"
        }
    
    def connect(self) -> bool:
        """Connect to Matrio-compatible device"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.ip, self.port))
            print(f"Connected to Matrio device at {self.ip}:{self.port}")
            
            # Initialize the device with the required protocol sequence
            if self._initialize_device():
                print("Device initialized successfully")
                return True
            else:
                print("Device initialization failed")
                self.disconnect()
                return False
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    def _initialize_device(self) -> bool:
        """Initialize the device with the required UPnP and binary protocol sequence"""
        try:
            # Step 1: UPnP Event Subscriptions
            if not self._setup_upnp_subscriptions():
                return False
            
            # Step 2: SOAP Commands
            if not self._send_soap_commands():
                return False
            
            # Step 3: Binary Protocol Initialization
            if not self._send_binary_initialization():
                return False
            
            return True
            
        except Exception as e:
            print(f"Device initialization failed: {e}")
            return False
    
    def _get_local_ip(self) -> str:
        """Get the local IP address of this machine"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((self.ip, 80))
                local_ip = s.getsockname()[0]
                return local_ip
        except Exception:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    return local_ip
            except Exception:
                return "127.0.0.1"
    
    def _setup_upnp_subscriptions(self) -> bool:
        """Setup UPnP event subscriptions on port 59152"""
        try:
            upnp_port = 59152
            local_ip = self._get_local_ip()
            
            # Subscribe to rendertransport1 events
            subscribe_request1 = (
                "SUBSCRIBE /upnp/event/rendertransport1 HTTP/1.1\r\n"
                f"Host: {self.ip}:{upnp_port}\r\n"
                "Content-Length: 0\r\n"
                "Connection: keep-alive\r\n"
                "TIMEOUT: Second-1800\r\n"
                "NT: upnp:event\r\n"
                "User-Agent: iOS/7.0 UPnP/1.1 UPNPX/1.2.4\r\n"
                f"CALLBACK: <http://{local_ip}:22809/Event>\r\n"
                "Accept-Encoding: gzip, deflate\r\n"
                "\r\n"
            )
            
            sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock1.settimeout(10)
            sock1.connect((self.ip, upnp_port))
            sock1.send(subscribe_request1.encode())
            response1 = sock1.recv(1024)
            sock1.close()
            
            time.sleep(0.5)
            
            # Subscribe to rendercontrol1 events
            subscribe_request2 = (
                "SUBSCRIBE /upnp/event/rendercontrol1 HTTP/1.1\r\n"
                f"Host: {self.ip}:{upnp_port}\r\n"
                "Content-Length: 0\r\n"
                "Connection: keep-alive\r\n"
                "TIMEOUT: Second-1800\r\n"
                "NT: upnp:event\r\n"
                "User-Agent: iOS/7.0 UPnP/1.1 UPNPX/1.2.4\r\n"
                f"CALLBACK: <http://{local_ip}:22809/Event>\r\n"
                "Accept-Encoding: gzip, deflate\r\n"
                "\r\n"
            )
            
            sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock2.settimeout(10)
            sock2.connect((self.ip, upnp_port))
            sock2.send(subscribe_request2.encode())
            response2 = sock2.recv(1024)
            sock2.close()
            
            time.sleep(0.5)
            
            # Subscribe to PlayQueue1 events
            subscribe_request3 = (
                "SUBSCRIBE /upnp/event/PlayQueue1 HTTP/1.1\r\n"
                f"Host: {self.ip}:{upnp_port}\r\n"
                "Content-Length: 0\r\n"
                "Connection: keep-alive\r\n"
                "TIMEOUT: Second-1800\r\n"
                "User-Agent: iOS/7.0 UPnP/1.1 UPNPX/1.2.4\r\n"
                "Accept-Encoding: gzip, deflate\r\n"
                f"CALLBACK: <http://{local_ip}:22809/Event>\r\n"
                "\r\n"
            )
            
            sock3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock3.settimeout(10)
            sock3.connect((self.ip, upnp_port))
            sock3.send(subscribe_request3.encode())
            response3 = sock3.recv(1024)
            sock3.close()
            
            return True
            
        except Exception as e:
            print(f"UPnP subscription failed: {e}")
            return False
    
    def _send_soap_commands(self) -> bool:
        """Send required SOAP commands on port 59152"""
        try:
            upnp_port = 59152
            
            # GetControlDeviceInfo
            soap_request1 = (
                "POST /upnp/control/rendercontrol1 HTTP/1.1\r\n"
                f"Host: {self.ip}\r\n"
                "SOAPACTION: \"urn:schemas-upnp-org:service:RenderingControl:1#GetControlDeviceInfo\"\r\n"
                "Content-Type: text/xml; charset=\"utf-8\"\r\n"
                "Content-Length: 325\r\n"
                "\r\n"
                "<?xml version=\"1.0\" encoding=\"utf-8\"?><s:Envelope s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\" xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\"><s:Body><u:GetControlDeviceInfo xmlns:u=\"urn:schemas-upnp-org:service:RenderingControl:1\"><InstanceID>0</InstanceID></u:GetControlDeviceInfo></s:Body></s:Envelope>"
            )
            
            sock4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock4.settimeout(10)
            sock4.connect((self.ip, upnp_port))
            sock4.send(soap_request1.encode())
            response4 = sock4.recv(1024)
            sock4.close()
            
            time.sleep(0.5)
            
            # GetInfoEx
            soap_request2 = (
                "POST /upnp/control/rendertransport1 HTTP/1.1\r\n"
                f"Host: {self.ip}\r\n"
                "SOAPACTION: \"urn:schemas-upnp-org:service:AVTransport:1#GetInfoEx\"\r\n"
                "Content-Type: text/xml; charset=\"utf-8\"\r\n"
                "Content-Length: 298\r\n"
                "\r\n"
                "<?xml version=\"1.0\" encoding=\"utf-8\"?><s:Envelope s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\" xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\"><s:Body><u:GetInfoEx xmlns:u=\"urn:schemas-upnp-org:service:AVTransport:1\"><InstanceID>0</InstanceID></u:GetInfoEx></s:Body></s:Envelope>"
            )
            
            sock5 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock5.settimeout(10)
            sock5.connect((self.ip, upnp_port))
            sock5.send(soap_request2.encode())
            response5 = sock5.recv(1024)
            sock5.close()
            
            time.sleep(0.5)
            
            # GetChannel
            soap_request3 = (
                "POST /upnp/control/rendercontrol1 HTTP/1.1\r\n"
                f"Host: {self.ip}\r\n"
                "SOAPACTION: \"urn:schemas-upnp-org:service:RenderingControl:1#GetChannel\"\r\n"
                "Content-Type: text/xml; charset=\"utf-8\"\r\n"
                "Content-Length: 330\r\n"
                "\r\n"
                "<?xml version=\"1.0\" encoding=\"utf-8\"?><s:Envelope s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\" xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\"><s:Body><u:GetChannel xmlns:u=\"urn:schemas-upnp-org:service:RenderingControl:1\"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetChannel></s:Body></s:Envelope>"
            )
            
            sock6 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock6.settimeout(10)
            sock6.connect((self.ip, upnp_port))
            sock6.send(soap_request3.encode())
            response6 = sock6.recv(1024)
            sock6.close()
            
            return True
            
        except Exception as e:
            print(f"SOAP commands failed: {e}")
            return False
    
    def _send_binary_initialization(self) -> bool:
        """Send binary protocol initialization sequence"""
        try:
            # Send initialization command (0x0a)
            init_packet = bytes.fromhex("189618200f0000005706000000000000000000004d43552b5041532b820affffff8926")
            self.socket.send(init_packet)
            
            # Wait for HNG_SYNC_COMMAND response
            self.socket.settimeout(5.0)
            sync_response = self.socket.recv(1024)
            if len(sync_response) == 0:
                return False
            
            # Wait for ALLNAMES response
            allnames_response = self.socket.recv(1024)
            if len(allnames_response) == 0:
                return False
            
            return True
            
        except Exception as e:
            print(f"Binary initialization failed: {e}")
            return False
    
    def trigger_hng_sync(self) -> Dict[str, Any] | None:
        """Trigger HNG sync packet and decode all zone states"""
        if not self.socket:
            _LOGGER.error("Not connected to device")
            return None
        
        try:
            _LOGGER.debug("Triggering HNG sync...")
            
            # Use the existing protocol command that we know works
            init_packet = bytes.fromhex("189618200f0000005706000000000000000000004d43552b5041532b820affffff8926")
            self.socket.send(init_packet)
            
            # Wait for HNG_SYNC_COMMAND response
            self.socket.settimeout(5.0)
            sync_response = self.socket.recv(1024)
            if len(sync_response) == 0:
                _LOGGER.debug("No sync response received")
                return None
            
            _LOGGER.debug("Received sync response: %d bytes", len(sync_response))
            
            # Wait for ALLNAMES response
            allnames_response = self.socket.recv(1024)
            if len(allnames_response) == 0:
                _LOGGER.debug("No ALLNAMES response received")
                return None
            
            _LOGGER.debug("Received ALLNAMES response: %d bytes", len(allnames_response))
            
            # Look for HNG sync packet in the responses
            combined_data = sync_response + allnames_response
            _LOGGER.debug("Combined data: %d bytes", len(combined_data))
            
            # Check if this is a concatenated packet (multiple HNG sync packets)
            if len(combined_data) > 100:  # Likely concatenated packets
                _LOGGER.debug("Detected concatenated packets, extracting HNG sync...")
                hng_hex = self._extract_hng_sync_packet(combined_data)
                if not hng_hex:
                    _LOGGER.warning("Could not extract HNG sync packet from concatenated data")
                    return None
            else:
                hng_hex = combined_data.hex()
            
            # Decode the packet
            result = self.hng_decoder.decode_hng_sync_packet(hng_hex, self.inputs)
            
            _LOGGER.debug("HNG sync decoded: %s packet with %d zones", 
                         result['packet_type'], len(result['zones']))
            
            return result
                
        except Exception as e:
            _LOGGER.error("HNG sync failed: %s", e)
            return None
    
    def _extract_hng_sync_packet(self, data: bytes) -> str | None:
        """Extract HNG sync packet from concatenated packet data"""
        try:
            # Look for HNG sync packet signature (820c)
            hng_signature = b'\x82\x0c'
            
            # Find the first occurrence of HNG sync signature
            hng_pos = data.find(hng_signature)
            if hng_pos == -1:
                _LOGGER.warning("HNG sync signature not found in packet data")
                return None
            
            # Extract the HNG sync packet - try both 68-byte and 96-byte sizes
            hng_start = hng_pos
            
            # Try 96-byte packet first (more common in newer devices)
            hng_end_96 = hng_start + 96
            if hng_end_96 <= len(data):
                hng_packet = data[hng_start:hng_end_96]
                _LOGGER.debug("Extracted 96-byte HNG sync packet: %d bytes", len(hng_packet))
                return hng_packet.hex()
            
            # Fall back to 68-byte packet
            hng_end_68 = hng_start + 68
            if hng_end_68 <= len(data):
                hng_packet = data[hng_start:hng_end_68]
                _LOGGER.debug("Extracted 68-byte HNG sync packet: %d bytes", len(hng_packet))
                return hng_packet.hex()
            
            _LOGGER.warning("HNG sync packet extends beyond received data")
            return None
            
        except Exception as e:
            _LOGGER.error("Failed to extract HNG sync packet: %s", e)
            return None
    
    def disconnect(self):
        """Disconnect from device"""
        if self.socket:
            self.socket.close()
            self.socket = None
            print("Disconnected from Matrio device")

class LiveBroadcastListener:
    """Listens for live broadcast packets from Matrio device"""
    
    def __init__(self, device_ip: str):
        self.device_ip = device_ip
        self.controller = MatrioController(device_ip)
        self.broadcast_decoder = None
        self.socket = None
        self.running = False
        self.initial_state = None
        
    def connect_and_initialize(self) -> bool:
        """Connect to device and initialize with HNG sync"""
        print(f"Connecting to Matrio device at {self.device_ip}...")
        
        if not self.controller.connect():
            print("Failed to connect to device")
            return False
        
        print("Connected successfully!")
        
        # Initialize broadcast decoder with default input mappings
        self.broadcast_decoder = BroadcastDecoder(self.controller.inputs)
        
        # Get initial state via HNG sync
        print("Getting initial state via HNG sync...")
        try:
            self.initial_state = self.controller.trigger_hng_sync()
            if self.initial_state and 'zones' in self.initial_state:
                print("Initial state received:")
                for zone_id, zone_data in self.initial_state['zones'].items():
                    print(f"  Zone {zone_id}: {zone_data}")
            else:
                print("Warning: Could not get initial state")
        except Exception as e:
            print(f"Warning: Could not get initial state: {e}")
        
        # Get the socket for listening to broadcasts
        self.socket = self.controller.socket
        return True
    
    def start_listening(self):
        """Start listening for broadcast packets"""
        if not self.socket:
            print("Not connected to device")
            return
        
        print("\n" + "="*60)
        print("LISTENING FOR BROADCAST PACKETS")
        print("Make changes in the mobile app to see live updates!")
        print("Press Enter to stop listening...")
        print("="*60)
        
        self.running = True
        
        # Start listening thread
        listen_thread = threading.Thread(target=self._listen_loop)
        listen_thread.daemon = True
        listen_thread.start()
        
        # Wait for user input to stop
        try:
            input()
        except KeyboardInterrupt:
            pass
        
        self.running = False
        print("\nStopping broadcast listener...")
    
    def _listen_loop(self):
        """Main listening loop for broadcast packets"""
        while self.running:
            try:
                # Set a short timeout so we can check if we should stop
                self.socket.settimeout(1.0)
                
                # Try to receive data
                data = self.socket.recv(1024)
                
                if len(data) == 0:
                    print("Connection lost!")
                    break
                
                # Decode the packet
                packet_hex = data.hex()
                print(f"\nReceived packet: {packet_hex}")
                
                # Try to decode as broadcast packet
                broadcast_info = self.broadcast_decoder.decode_packet(packet_hex)
                
                if broadcast_info:
                    self._print_broadcast_info(broadcast_info)
                else:
                    print("  (Not a recognized packet)")
                
            except socket.timeout:
                # Timeout is expected, continue listening
                continue
            except Exception as e:
                if self.running:  # Only print error if we're still supposed to be running
                    print(f"Error receiving data: {e}")
                break
    
    def _print_broadcast_info(self, info: Dict[str, Any]):
        """Print formatted broadcast information"""
        if 'error' in info:
            print(f"  ERROR: {info['error']}")
            return
        
        change_type = info['type']
        zones = info.get('zones', [])
        
        if not zones:
            print(f"  {change_type.upper()}: No zones affected")
            return
        
        zone_str = ", ".join(map(str, zones))
        
        if change_type == "power":
            power_state = "ON" if info['power_on'] else "OFF"
            print(f"  POWER: Zones {zone_str} turned {power_state}")
            
        elif change_type == "volume":
            volume = info['volume']
            print(f"  VOLUME: Zones {zone_str} volume set to {volume}")
            
        elif change_type == "mute":
            mute_state = "MUTED" if info['muted'] else "UNMUTED"
            print(f"  MUTE: Zones {zone_str} {mute_state}")
            
        elif change_type == "input":
            input_name = info['input_name']
            print(f"  INPUT: Zones {zone_str} switched to {input_name}")
            
        elif change_type == "balance":
            balance = info['balance']
            print(f"  BALANCE: Zones {zone_str} balance set to {balance}")
            
        elif change_type == "bass":
            bass = info['bass']
            print(f"  BASS: Zones {zone_str} bass set to {bass}")
            
        elif change_type == "treble":
            treble = info['treble']
            print(f"  TREBLE: Zones {zone_str} treble set to {treble}")
            
        elif change_type == "total_volume":
            volume = info['volume']
            print(f"  TOTAL VOLUME: Zones {zone_str} total volume set to {volume}")
        
        # Show raw data for debugging
        print(f"  Command: {info.get('raw_command', 'N/A')}")
        print(f"  Data: {info.get('raw_data', 'N/A')}")
    
    def disconnect(self):
        """Disconnect from device"""
        self.running = False
        if self.controller:
            self.controller.disconnect()

def main():
    if len(sys.argv) != 2:
        print("Usage: python test_broadcast_standalone_v3.py <device_ip>")
        print("Example: python test_broadcast_standalone_v3.py 192.168.1.100")
        sys.exit(1)
    
    device_ip = sys.argv[1]
    
    listener = LiveBroadcastListener(device_ip)
    
    try:
        # Connect and initialize
        if not listener.connect_and_initialize():
            sys.exit(1)
        
        # Start listening for broadcasts
        listener.start_listening()
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        listener.disconnect()
        print("Disconnected from device")

if __name__ == "__main__":
    main()
