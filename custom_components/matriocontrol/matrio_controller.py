#!/usr/bin/env python3
"""
Matrio Controller - Complete Python implementation for Dayton Audio multi-zone amplifiers
Reverse engineered from Matrio mobile app communication protocol.

Protocol Details:
- TCP connection on port 8899
- Binary packet format: 82 [COMMAND] [VALUE] [PATTERN] ff cc
- Zone selection pattern: 01=selected, 02=not selected
- Individual mode: all 02s, Group mode: mix of 01s and 02s

Compatible with:
- Dayton Audio DAX88 (tested)
- Other Dayton Audio multi-zone amplifiers using Matrio Control protocol

Author: Reverse engineered from network analysis
Date: 2025-01-02
"""

import socket
import time
import struct
import logging
from typing import Dict, List, Any

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
        # If this is an extracted HNG packet (starts with 820c), hng_start is always 0
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
        # Confirmed by differential analysis: balance is at position 34 + zone_index
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
        
        # Bass and treble state - decode from specific byte positions
        bass, treble = self.decode_bass_treble(zone, packet, hng_start, packet_size)
        
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
                'mute': f"0x{mute_val:02x}"
            }
        }
    
    def decode_power_state(self, power: int, packet_size: int) -> str:
        """Decode zone power state based on packet size"""
        if packet_size == 96:
            # 96-byte packet: 0x02=ON, 0x01=OFF
            if power == 0x02:
                return "ON"
            elif power == 0x01:
                return "OFF"
            else:
                return f"UNKNOWN(0x{power:02x})"
        else:
            # 68-byte packet: 0x01=ON, 0x02=OFF (with reversed zone mapping)
            if power == 0x01:
                return "ON"
            elif power == 0x02:
                return "OFF"
            else:
                return f"UNKNOWN(0x{power:02x})"
    
    def decode_input_selection(self, input_val: int, input_mappings: Dict[int, str]) -> str:
        """Decode zone input selection using device-provided input mappings"""
        # HNG input values directly correspond to device input IDs (1-8)
        # No mapping needed - input_val is already the correct input ID
        result = input_mappings.get(input_val, f"UNKNOWN(0x{input_val:02x})")
        _LOGGER.debug("Decoding input %d with mappings %s -> %s", input_val, input_mappings, result)
        return result
    
    def decode_volume_level(self, volume: int) -> int:
        """Decode zone volume level (with +1 offset)"""
        # Volume is stored as (UI_volume + 1)
        ui_volume = volume - 1
        return max(0, ui_volume)  # Ensure non-negative
    
    def decode_balance_state(self, balance: int, packet_size: int) -> str:
        """Decode zone balance state based on differential analysis"""
        # Based on differential analysis, balance values are:
        # 0x01 = MAX Left (-100), 0x1f = Center (0), 0x3d = MAX Right (+100)
        if balance == 0x3d:
            return "MAX Right"
        elif balance == 0x1f:
            return "Default"
        elif balance == 0x01:
            return "MAX Left"
        else:
            # For intermediate values, we need to map them to UI values
            # The range appears to be 0x01 to 0x3d (1 to 61)
            if 0x01 <= balance <= 0x3d:
                # Map 0x01-0x3d to -100 to +100
                ui_value = int((balance - 0x01) / (0x3d - 0x01) * 200) - 100
                return str(ui_value)
            else:
                return f"UNKNOWN(0x{balance:02x})"
    
    def decode_mute_state(self, mute: int, packet_size: int) -> str:
        """Decode zone mute state based on packet size"""
        if packet_size == 96:
            # 96-byte packet: 0x01=Default, 0x02=Muted
            if mute == 0x01:
                return "DEFAULT"
            elif mute == 0x02:
                return "MUTED"
            else:
                return f"UNKNOWN(0x{mute:02x})"
        else:
            # 68-byte packet: 0x0d=Default, 0x02=Muted
            if mute == 0x0d:
                return "DEFAULT"
            elif mute == 0x02:
                return "MUTED"
            else:
                return f"UNKNOWN(0x{mute:02x})"

    
    def get_bass_start(self, hng_start: int, packet_size: int) -> int:
        """Get the starting byte position for bass data"""
        # Confirmed by differential analysis: bass is at position 26 + zone_index
        return hng_start + 26
    
    def get_treble_start(self, hng_start: int, packet_size: int) -> int:
        """Get the starting byte position for treble data"""
        # Confirmed by differential analysis: treble is at position 18 + zone_index
        return hng_start + 18
    
    def decode_bass_treble(self, zone: int, packet: bytes, hng_start: int, packet_size: int) -> tuple[int, int]:
        """Decode bass and treble values from HNG sync packet"""
        
        bass_start = self.get_bass_start(hng_start, packet_size)
        treble_start = self.get_treble_start(hng_start, packet_size)
        
        bass_val = packet[bass_start + zone]
        treble_val = packet[treble_start + zone]
        
        # Based on differential analysis:
        # Bass: 0x0d is center (0), range appears to be 0x01 to 0x19 (1 to 25)
        # Treble: 0x0d is center (0), range appears to be 0x01 to 0x19 (1 to 25)
        bass = bass_val - 0x0d if 0x01 <= bass_val <= 0x19 else 0
        treble = treble_val - 0x0d if 0x01 <= treble_val <= 0x19 else 0
        
        return bass, treble

class MatrioController:
    """Complete controller for Dayton Audio multi-zone amplifiers using Matrio Control protocol"""
    
    def __init__(self, ip: str, port: int = 8899):
        """
        Initialize Matrio controller
        
        Args:
            ip: IP address of the Matrio-compatible device
            port: TCP port (default 8899 - the actual communication port)
        """
        self.ip = ip
        self.port = port
        self.socket = None
        self.zones = {}
        self.hng_decoder = UniversalHNGSyncDecoder()
        
        # Default input mapping based on capture analysis
        self.inputs = {
            1: "TV",
            2: "Google Music", 
            3: "Input3",
            4: "Input4",
            5: "Input5",
            6: "Input6",
            7: "Input7",
            8: "Wi-Fi"
        }
    
    def _get_local_ip(self) -> str:
        """
        Get the local IP address of this machine
        """
        try:
            # Create a socket to determine the local IP
            # Connect to a remote address to determine the local interface
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # Connect to the Matrio device to use the same network interface
                s.connect((self.ip, 80))
                local_ip = s.getsockname()[0]
                return local_ip
        except Exception:
            # Fallback: try to connect to a public DNS server
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    return local_ip
            except Exception:
                # Last resort: return localhost
                return "127.0.0.1"
        
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
        """
        Initialize the device with the required UPnP and binary protocol sequence
        This is required before the device will accept control commands
        """
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
    
    def _setup_upnp_subscriptions(self) -> bool:
        """Setup UPnP event subscriptions on port 59152"""
        try:
            upnp_port = 59152
            
            # Subscribe to rendertransport1 events
            local_ip = self._get_local_ip()
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
            
            # Small delay between subscriptions
            import time
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
                "NT: upnp:event\r\n"
                "User-Agent: iOS/7.0 UPnP/1.1 UPNPX/1.2.4\r\n"
                f"CALLBACK: <http://{local_ip}:22809/Event>\r\n"
                "Accept-Encoding: gzip, deflate\r\n"
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
    
    def disconnect(self):
        """Disconnect from device"""
        if self.socket:
            self.socket.close()
            self.socket = None
            print("Disconnected from Matrio device")
    
    
    def _send_input_command(self, zone_id: int, input_id: int) -> bool:
        """
        Send input command using the correct protocol discovered from capture analysis
        
        Args:
            zone_id: Zone ID (1-8)
            input_id: Input ID (1-8)
        """
        _LOGGER.debug("_send_input_command called: zone_id=%s, input_id=%s", zone_id, input_id)
        
        if not self.socket:
            _LOGGER.debug("No socket connection available")
            return False
        
        if zone_id < 1 or zone_id > 8:
            _LOGGER.debug("Invalid zone ID: %s. Must be 1-8", zone_id)
            return False
        
        if input_id < 1 or input_id > 8:
            _LOGGER.debug("Invalid input ID: %s. Must be 1-8", input_id)
            return False
        
        # Create zone pattern: 01 at target zone position, 02 elsewhere
        # Pattern is 8 bytes: 0202010202020202 for zone 3, 0202020102020202 for zone 4, etc.
        zone_pattern = [0x02] * 8
        zone_pattern[zone_id - 1] = 0x01  # zone_id is 1-based, array is 0-based
        
        _LOGGER.debug("Zone pattern: %s", [hex(b) for b in zone_pattern])
        
        # Protocol format based on capture analysis:
        # Header (4 bytes) + Length (4 bytes) + Data (12 bytes) + Payload
        header = bytes.fromhex("18961820")
        length = 22  # 22 bytes total
        data = bytes.fromhex("b60400000000000000000000")  # Fixed data
        payload = bytes.fromhex("4d43552b5041532b") + bytes([0x82, 0x0d, input_id]) + bytes(zone_pattern) + bytes.fromhex("ffcc26")
        
        packet = header + length.to_bytes(4, 'little') + data + payload
        
        _LOGGER.debug("Sending packet: %s", packet.hex())
        _LOGGER.debug("Packet length: %s bytes", len(packet))
        
        try:
            bytes_sent = self.socket.send(packet)
            _LOGGER.debug("Sent %s bytes to device", bytes_sent)
            
            # Wait for response
            self.socket.settimeout(2.0)
            response = self.socket.recv(1024)
            
            if len(response) > 0:
                _LOGGER.debug("Received response: %s...", response.hex()[:50])
                return True
            else:
                _LOGGER.debug("No response received from device")
                return False
        except Exception as e:
            _LOGGER.debug("Input command failed with exception: %s", e)
            return False
    
    def _send_power_command(self, zone_id: int, power_on: bool) -> bool:
        """
        Send power command using the correct protocol discovered from mobile app analysis
        
        Args:
            zone_id: Zone ID (1-8)
            power_on: True for power ON, False for power OFF
        """
        if not self.socket:
            return False
        
        if zone_id < 1 or zone_id > 8:
            print(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        
        try:
            if power_on:
                # Power ON: Use ab04 command with shifted pattern (02 + zone pattern + 02)
                command_code = "ab04"
                # Create shifted pattern: 02 + [zone pattern] + 02 (11 bytes total)
                zone_pattern = [0x02] * 11  # Start with all 02s
                zone_pattern[zone_id] = 0x01  # Set target zone to 01
                pattern_hex = ''.join(f'{b:02x}' for b in zone_pattern)
                length = 0x18  # 24 bytes total
            else:
                # Power OFF: Use aa04 command with dual pattern (01 at position 0 + 01 at target zone)
                command_code = "aa04"
                # Create dual pattern: 01 at position 0 + 01 at target zone (9 bytes total)
                zone_pattern = [0x02] * 9  # Start with all 02s
                zone_pattern[0] = 0x01  # Always 01 at position 0
                zone_pattern[zone_id] = 0x01  # 01 at target zone position (zone_id is 1-based, array is 0-based)
                pattern_hex = ''.join(f'{b:02x}' for b in zone_pattern)
                length = 0x16  # 22 bytes total
            
            # Create packet
            packet_hex = f"18961820{length:02x}000000{command_code}000000000000000000004d43552b5041532b8208{pattern_hex}ffcc26"
            packet = bytes.fromhex(packet_hex)
            
            self.socket.send(packet)
            
            # Wait for response
            self.socket.settimeout(2.0)
            response = self.socket.recv(1024)
            
            if len(response) > 0:
                print(f"Zone {zone_id} power {'ON' if power_on else 'OFF'} command sent successfully")
                return True
            else:
                print(f"Zone {zone_id} power {'ON' if power_on else 'OFF'} command failed - no response")
                return False
                
        except Exception as e:
            print(f"Power command failed: {e}")
            return False
    
    def _send_volume_command(self, zone_id: int, volume: int) -> bool:
        """
        Send volume command using the correct zone-specific protocol from packet capture analysis
        
        Args:
            zone_id: Zone ID (1-8)
            volume: Volume level (0-38)
        """
        if not self.socket:
            return False
        
        if zone_id < 1 or zone_id > 8:
            print(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        
        if volume < 0 or volume > 38:
            print(f"Invalid volume: {volume}. Must be 0-38")
            return False
        
        try:
            # Create zone-specific pattern: [volume] + zone pattern
            # Zone pattern has 01 at position (zone_id - 1), 02 elsewhere
            zone_pattern = [0x02] * 8
            zone_pattern[zone_id - 1] = 0x01  # zone_id is 1-based, array is 0-based
            zone_pattern_hex = ''.join(f'{b:02x}' for b in zone_pattern)
            
            # Volume value needs to be adjusted by +1 (UI shows volume-1)
            # Volume 0 might not work, so we'll use 1 as minimum
            adjusted_volume = max(1, volume + 1)
            
            # Pattern format: [adjusted_volume] + zone_pattern (8 bytes)
            pattern = f"{adjusted_volume:02x}{zone_pattern_hex}"
            
            # Use the working command code from packet capture (b604 works for all volume levels)
            command_code = "b604"
            
            # Create packet using exact format from packet capture
            packet_hex = f"1896182016000000{command_code}000000000000000000004d43552b5041532b8201{pattern}ffcc26"
            packet = bytes.fromhex(packet_hex)
            
            self.socket.send(packet)
            
            # Wait for response
            self.socket.settimeout(2.0)
            response = self.socket.recv(1024)
            
            if len(response) > 0:
                print(f"Zone {zone_id} volume: {volume}")
                return True
            else:
                print(f"Zone {zone_id} volume command failed - no response")
                return False
                
        except Exception as e:
            print(f"Volume command failed: {e}")
            return False
    
    def _send_mute_command(self, zone_id: int, mute: bool) -> bool:
        """
        Send mute command using the correct zone-specific protocol from packet capture analysis
        
        Args:
            zone_id: Zone ID (1-8)
            mute: True for mute ON, False for mute OFF
        """
        if not self.socket:
            return False
        
        if zone_id < 1 or zone_id > 8:
            print(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        
        try:
            # Create zone-specific pattern: [state] + zone pattern
            # Zone pattern has 01 at position (zone_id - 1), 02 elsewhere
            # But mute commands use different indexing - they seem to be off by one
            zone_pattern = [0x02] * 8
            zone_pattern[zone_id - 1] = 0x01  # zone_id is 1-based, array is 0-based
            zone_pattern_hex = ''.join(f'{b:02x}' for b in zone_pattern)
            
            if mute:
                # Mute ON: b104 with pattern [02] + zone_pattern
                command_code = "b104"
                pattern = f"02{zone_pattern_hex}"
            else:
                # Mute OFF: b004 with pattern [01] + zone_pattern
                command_code = "b004"
                pattern = f"01{zone_pattern_hex}"
            
            # Create packet using exact format from packet capture
            packet_hex = f"1896182016000000{command_code}000000000000000000004d43552b5041532b820e{pattern}ffcc26"
            packet = bytes.fromhex(packet_hex)
            
            self.socket.send(packet)
            
            # Wait for response
            self.socket.settimeout(2.0)
            response = self.socket.recv(1024)
            
            if len(response) > 0:
                print(f"Zone {zone_id} mute: {'ON' if mute else 'OFF'}")
                return True
            else:
                print(f"Zone {zone_id} mute command failed - no response")
                return False
                
        except Exception as e:
            print(f"Mute command failed: {e}")
            return False
    
    def _send_name_command(self, command_type: int, item_id: int, name: str) -> bool:
        """
        Send zone or input name command
        
        Args:
            command_type: 0x01 for zone names, 0x02 for input names
            item_id: Zone or input ID (1-8)
            name: New name to set
        """
        if not self.socket:
            return False
        
        # Convert name to bytes
        name_bytes = name.encode('utf-8')
        name_length = len(name_bytes)
        
        # Packet format: 82 13 [TYPE] [ID] [LENGTH] [NAME] cc
        packet = bytes([0x82, 0x13, command_type, item_id, name_length] + list(name_bytes) + [0xcc])
        
        try:
            self.socket.send(packet)
            # Wait for response
            response = self.socket.recv(1024)
            return len(response) > 0
        except Exception as e:
            print(f"Name command failed: {e}")
            return False
    
    
    # Zone and Input Naming
    def set_zone_name(self, zone_id: int, name: str) -> bool:
        """Set zone name (zones 1-8)"""
        if zone_id < 1 or zone_id > 8:
            print(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        result = self._send_name_command(0x01, zone_id, name)
        if result:
            print(f"Zone {zone_id} renamed to: {name}")
        return result
    
    def set_input_name(self, input_id: int, name: str) -> bool:
        """Set input name (inputs 1-8)"""
        if input_id < 1 or input_id > 8:
            print(f"Invalid input ID: {input_id}. Must be 1-8")
            return False
        result = self._send_name_command(0x02, input_id, name)
        if result:
            print(f"Input {input_id} renamed to: {name}")
        return result
    
    # Individual Zone Controls
    def set_zone_power(self, zone_id: int, power: bool) -> bool:
        """Turn individual zone on/off using the correct protocol"""
        return self._send_power_command(zone_id, power)
    
    def set_volume(self, zone_id: int, volume: int) -> bool:
        """Set volume for individual zone (0-38) using correct protocol"""
        if zone_id < 1 or zone_id > 8:
            print(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        
        # Volume range matches mobile app: 0-38
        if volume < 0 or volume > 38:
            print(f"Invalid volume: {volume}. Must be 0-38")
            return False
        
        return self._send_volume_command(zone_id, volume)
    
    def set_mute(self, zone_id: int, mute: bool) -> bool:
        """Mute/unmute individual zone using correct protocol"""
        if zone_id < 1 or zone_id > 8:
            print(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        
        return self._send_mute_command(zone_id, mute)
    
    def set_balance(self, zone_id: int, balance: int) -> bool:
        """Set balance for individual zone (-50 to +50, where 0 is center)"""
        center = 44
        device_balance = center + balance
        device_balance = max(0, min(127, device_balance))
        result = self._send_command(0x05, device_balance, selected_zones={zone_id})
        if result:
            print(f"Zone {zone_id} balance: {balance}")
        return result
    
    def set_bass(self, zone_id: int, bass: int) -> bool:
        """Set bass for individual zone (-10 to +10)"""
        center = 13
        device_bass = center + bass
        device_bass = max(0, min(127, device_bass))
        result = self._send_command(0x03, device_bass, selected_zones={zone_id})
        if result:
            print(f"Zone {zone_id} bass: {bass}")
        return result
    
    def set_treble(self, zone_id: int, treble: int) -> bool:
        """Set treble for individual zone (-10 to +10)"""
        center = 13
        device_treble = center + treble
        device_treble = max(0, min(127, device_treble))
        result = self._send_command(0x02, device_treble, selected_zones={zone_id})
        if result:
            print(f"Zone {zone_id} treble: {treble}")
        return result
    
    def set_input(self, zone_id: int, input_id: int) -> bool:
        """Set input for individual zone (1-8)"""
        _LOGGER.debug("set_input called: zone_id=%s, input_id=%s", zone_id, input_id)
        
        if input_id < 1 or input_id > 8:
            _LOGGER.debug("Invalid input ID: %s. Must be 1-8", input_id)
            return False
        
        input_name = self.inputs.get(input_id, f"Input {input_id}")
        _LOGGER.debug("Attempting to set Zone %s to %s (ID: %s)", zone_id, input_name, input_id)
        
        result = self._send_input_command(zone_id, input_id)
        
        if result:
            _LOGGER.debug("SUCCESS: Zone %s input set to %s", zone_id, input_name)
        else:
            _LOGGER.debug("FAILED: Zone %s input change failed", zone_id)
        
        return result
    
    
    def get_available_inputs(self) -> Dict[int, str]:
        """Get available inputs"""
        return self.inputs.copy()
    
    def get_device_name(self) -> str:
        """Get the device name from the device (should be called after connection)"""
        # Query the device for its actual name
        device_info = self.query_device_info()
        if device_info and "device_name" in device_info:
            return device_info["device_name"]
        
        # If we can't get device info, raise an exception
        raise RuntimeError("Could not retrieve device name from device")
    
    def _send_protocol_command(self, command: int) -> bytes | None:
        """
        Send a protocol command using the Matrio Control protocol format
        Based on packet capture analysis of Matrio Control app
        Format: header (4 bytes) + length (4 bytes) + data (12 bytes) + payload
        """
        if not self.socket:
            return None
        
        try:
            # Protocol format discovered from packet capture:
            # Header: 18961820 (4 bytes)
            # Length: varies (4 bytes, little endian)
            # Data: varies (12 bytes)
            # Payload: MCU+PAS+ + command + data
            
            if command == 0x0a:  # First command (10 bytes)
                length = 0x0f  # 15 bytes total
                data = bytes.fromhex("570600000000000000000000")
                payload = bytes.fromhex("4d43552b5041532b820affffff8926")
            elif command == 0x0c:  # Second command (12 bytes) 
                length = 0x4c  # 76 bytes total
                data = bytes.fromhex("a90800000000000000000000")
                payload = bytes.fromhex("4d43552b5041532b820c0108080808080808070f22171d0805050d0d0d0d0d0d0d0d0d0d0d0d0d0d0d1f1f1f1f1f1f1f1f02010201010101010101010102010101010140180c14ffffcc26")
            else:
                print(f"Unknown command: 0x{command:02x}")
                return None
            
            # Construct packet
            header = bytes.fromhex("18961820")
            packet = header + length.to_bytes(4, 'little') + data + payload
            
            self.socket.send(packet)
            
            # For the sequence, we need to handle the protocol flow:
            # 1. Send 0x0a command
            # 2. Receive ACK
            # 3. Receive 0x0c response
            # 4. Send ACK
            # 5. Receive ALLNAMES (0x15) packet
            
            if command == 0x0a:
                # Send first command and wait for responses
                self.socket.settimeout(5.0)
                
                # Wait for ACK
                ack = self.socket.recv(1024)
                if len(ack) == 0:
                    print("Received ACK")
                
                # Wait for 0x0c response (this is actually the ALLNAMES packet)
                response = self.socket.recv(1024)
                if len(response) > 0:
                    print(f"Received response: {len(response)} bytes")
                    # This is the ALLNAMES packet, return it directly
                    return response
                
                return None
            else:
                # For other commands, just send and receive
                self.socket.settimeout(2.0)
                response = self.socket.recv(1024)
                return response if len(response) > 0 else None
                
        except Exception as e:
            print(f"Protocol command failed: {e}")
            return None
    
    def check_heartbeat(self) -> bool:
        """
        Check if the device is responding (heartbeat check)
        Returns True if device responds, False otherwise
        """
        if not self.socket:
            return False
        
        try:
            # Try the first command to check if device is alive
            response = self._send_protocol_command(0x0a)
            return response is not None and len(response) > 0
        except Exception:
            return False
    
    def query_device_info(self) -> Dict[str, str]:
        """
        Query device information from the Matrio-compatible device using the correct protocol
        Based on the logs, the device reports deviceInfo with MAC, firmware, etc.
        """
        if not self.socket:
            raise ConnectionError("Not connected to device")
        
        # Send the first command (0x0a) to trigger the protocol sequence that returns ALLNAMES
        response = self._send_protocol_command(0x0a)
        if not response:
            raise RuntimeError("Device did not respond to ALLNAMES command")
        
        # Parse the ALLNAMES response to extract device info
        try:
            # The ALLNAMES packet structure from packet capture:
            # Header: 18961820a3000000823400000000000000000000
            # Payload: 4d43552b5041532b82150b4441582038385f363136450b4c6976696e6720526f6f6d0e4d617374657220426564726f6f6d0d4465636b2055707374616972730f4465636b20446f776e7374616972730a446f776e737461697273065a4f4e453636055a4f4e4537055a4f4e45380254560c476f6f676c65204d7573696306496e7075743306496e7075743406496e7075743507496e707574363606496e70757437cc26
            
            # Skip the protocol header and get to the actual data
            # The payload starts after the protocol header (20 bytes)
            payload_start = 20
            if len(response) < payload_start:
                raise RuntimeError("Response too short to contain ALLNAMES data")
            
            # Extract the payload (skip protocol header)
            payload = response[payload_start:]
            
            # The payload structure:
            # MCU+PAS+ (8 bytes) + 8215 (2 bytes) + length (1 byte) + device_name + zone_names + input_names
            
            # Skip MCU+PAS+ and command (10 bytes)
            data_start = 10
            if len(payload) < data_start:
                raise RuntimeError("Payload too short")
            
            data = payload[data_start:]
            
            # Parse the device name (first length-prefixed string)
            if len(data) < 1:
                raise RuntimeError("No device name length found")
            
            device_name_len = data[0]
            if len(data) < 1 + device_name_len:
                raise RuntimeError("Device name extends beyond data")
            
            device_name = data[1:1 + device_name_len].decode('ascii', errors='ignore')
            
            # The ALLNAMES packet only contains the device name and zone/input names
            # It does not contain MAC address, firmware, or hardware information
            # These would need to be obtained from other protocol commands or device queries
            
            return {
                "device_name": device_name,
                "mac_address": None,  # Not available in ALLNAMES packet
                "firmware": None,     # Not available in ALLNAMES packet  
                "hardware": None      # Not available in ALLNAMES packet
            }
                
        except Exception as e:
            raise RuntimeError(f"Failed to parse device info from response: {e}")
    
    def query_all_names(self) -> Dict[str, str]:
        """
        Query all zone and input names from the device
        Based on the logs, the device sends ALLNAMES packets with zone and input names
        """
        if not self.socket:
            raise ConnectionError("Not connected to device")
        
        # Send the first command (0x0a) to trigger the protocol sequence that returns ALLNAMES
        response = self._send_protocol_command(0x0a)
        if not response:
            raise RuntimeError("Device did not respond to ALLNAMES command")
        
        # Parse the ALLNAMES response to extract zone and input names
        try:
            # The ALLNAMES packet structure from packet capture:
            # Header: 18961820a3000000823400000000000000000000
            # Payload: 4d43552b5041532b82150b4441582038385f363136450b4c6976696e6720526f6f6d0e4d617374657220426564726f6f6d0d4465636b2055707374616972730f4465636b20446f776e7374616972730a446f776e737461697273065a4f4e453636055a4f4e4537055a4f4e45380254560c476f6f676c65204d7573696306496e7075743306496e7075743406496e7075743507496e707574363606496e70757437cc26
            
            # Skip the protocol header and get to the actual data
            # The payload starts after the protocol header (20 bytes)
            payload_start = 20
            if len(response) < payload_start:
                raise RuntimeError("Response too short to contain ALLNAMES data")
            
            # Extract the payload (skip protocol header)
            payload = response[payload_start:]
            
            # The payload structure:
            # MCU+PAS+ (8 bytes) + 8215 (2 bytes) + length (1 byte) + device_name + zone_names + input_names
            
            # Skip MCU+PAS+ and command (10 bytes)
            data_start = 10
            if len(payload) < data_start:
                raise RuntimeError("Payload too short")
            
            data = payload[data_start:]
            
            # Parse length-prefixed strings
            names = {}
            pos = 0
            
            # First string is device name (length 0x0b = 11 bytes)
            if pos + 1 > len(data):
                raise RuntimeError("No device name length found")
            
            device_name_len = data[pos]
            pos += 1
            
            if pos + device_name_len > len(data):
                raise RuntimeError("Device name extends beyond data")
            
            device_name = data[pos:pos + device_name_len].decode('ascii', errors='ignore')
            pos += device_name_len
            
            # Parse zone names (8 zones)
            zone_names = []
            for zone_id in range(8):
                if pos >= len(data):
                    break
                
                name_len = data[pos]
                pos += 1
                
                if pos + name_len > len(data):
                    break
                
                zone_name = data[pos:pos + name_len].decode('ascii', errors='ignore')
                zone_names.append(zone_name)
                pos += name_len
            
            # Parse input names (8 inputs)
            input_names = []
            for input_id in range(8):
                if pos >= len(data):
                    # If we've reached the end of data, Input 8 is typically "Wi-Fi"
                    if input_id == 7:  # Input 8 (index 7)
                        input_names.append("Wi-Fi")
                    break
                
                name_len = data[pos]
                pos += 1
                
                if pos + name_len > len(data):
                    # If we can't read the full name, Input 8 is typically "Wi-Fi"
                    if input_id == 7:  # Input 8 (index 7)
                        input_names.append("Wi-Fi")
                    break
                
                input_name = data[pos:pos + name_len].decode('ascii', errors='ignore')
                input_names.append(input_name)
                pos += name_len
            
            # Ensure we have exactly 8 input names (pad with "Wi-Fi" for Input 8 if missing)
            while len(input_names) < 8:
                if len(input_names) == 7:  # Input 8 (index 7)
                    input_names.append("Wi-Fi")
                else:
                    input_names.append(f"Input{len(input_names) + 1}")
            
            # Build the names dictionary
            for i, zone_name in enumerate(zone_names):
                names[f"zone_{i}"] = zone_name
            
            for i, input_name in enumerate(input_names):
                names[f"input_{i+1}"] = input_name
            
            return names
            
        except Exception as e:
            raise RuntimeError(f"Failed to parse zone/input names from response: {e}")
    
    def _send_audio_control_command(self, zone_id: int, control_type: str, value: int) -> bool:
        """
        Send audio control command (balance, bass, treble) using the correct protocol
        
        Args:
            zone_id: Zone ID (1-8)
            control_type: 'balance', 'bass', or 'treble'
            value: Control value
                - Balance: -100 to +100 (left to right)
                - Bass/Treble: -12 to +12 (minimum to maximum)
        
        Returns:
            bool: True if command sent successfully
        """
        if not self.socket:
            print("Not connected to device")
            return False
        
        if zone_id < 1 or zone_id > 8:
            print(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        
        # Map control types to command codes
        command_codes = {
            'balance': 0x05,  # 8205 from capture analysis
            'bass': 0x03,     # 8203 - swapped with treble
            'treble': 0x02    # 8202 - swapped with bass
        }
        
        if control_type not in command_codes:
            print(f"Invalid control type: {control_type}. Must be 'balance', 'bass', or 'treble'")
            return False
        
        command_code = command_codes[control_type]
        
        # Convert value to hex based on control type
        if control_type == 'balance':
            # Balance: -100 to +100 -> 0x01 to 0x3d (1 to 61)
            # Based on MatrioLog13.txt: 0x01=min left, 0x1f=middle, 0x3d=max right
            if value < -100 or value > 100:
                print(f"Invalid balance value: {value}. Must be -100 to +100")
                return False
            
            # Use exact values from logs
            if value == -100:
                hex_value = 0x01  # Maximum left
            elif value == 0:
                hex_value = 0x1f  # Center (from logs)
            elif value == 100:
                hex_value = 0x3d  # Maximum right
            else:
                # Linear interpolation between known points
                if value < 0:
                    # Map -100 to 0 onto 0x01 to 0x1f
                    hex_value = 0x01 + int((value + 100) / 100.0 * (0x1f - 0x01))
                else:
                    # Map 0 to 100 onto 0x1f to 0x3d
                    hex_value = 0x1f + int(value / 100.0 * (0x3d - 0x1f))
            hex_value = max(0x01, min(0x3d, hex_value))
            
        else:  # bass or treble
            # Bass/Treble: -12 to +12 -> 0x01 to 0x19 (1 to 25)
            # Based on actual UI mapping: 0x01=-12, 0x0d=0, 0x19=+12
            if value < -12 or value > 12:
                print(f"Invalid {control_type} value: {value}. Must be -12 to +12")
                return False
            
            # Use the correct UI to hex conversion (limited range)
            hex_value = self._ui_value_to_hex_limited(value)
        
        # Create zone pattern (zone selection)
        zone_pattern = [0x02] * 8  # All zones unselected by default
        zone_pattern[zone_id - 1] = 0x01  # Select the target zone
        
        # Create packet using exact format from working balance commands
        packet_hex = f"1896182016000000e304000000000000000000004d43552b5041532b82{command_code:02x}{hex_value:02x}{''.join(f'{b:02x}' for b in zone_pattern)}ffcc26"
        packet = bytes.fromhex(packet_hex)
        
        try:
            self.socket.send(packet)
            
            # Wait for response like other working commands
            self.socket.settimeout(2.0)
            response = self.socket.recv(1024)
            
            if len(response) > 0:
                print(f"Sent {control_type} command for zone {zone_id}: value={value} (0x{hex_value:02x}) - Response: {response.hex()[:20]}...")
                return True
            else:
                print(f"{control_type} command for zone {zone_id} failed - no response")
                return False
                
        except Exception as e:
            print(f"Failed to send {control_type} command: {e}")
            return False


    def _ui_value_to_hex_limited(self, ui_value: int) -> int:
        """
        Convert UI value (-12 to +12) to hex value for bass/treble controls (limited range)
        
        Args:
            ui_value: UI value from -12 to +12
            
        Returns:
            int: Hex value (0x01 to 0x19)
        """
        # Clamp value to valid range
        ui_value = max(-12, min(12, ui_value))
        
        # Simple linear conversion: -12 to +12 maps to 0x01 to 0x19
        # Range is 25 values: -12, -11, ..., 0, ..., +11, +12
        # Hex range is 25 values: 0x01, 0x02, ..., 0x19
        # Formula: hex = (ui_value + 12) + 1 = ui_value + 13
        hex_value = ui_value + 13
        
        # Ensure it's within bounds (should always be 0x01 to 0x19)
        return max(0x01, min(0x19, hex_value))
    
    def set_balance(self, zone_id: int, balance: int) -> bool:
        """
        Set balance for individual zone
        
        Args:
            zone_id: Zone ID (1-8)
            balance: Balance value (-100 to +100, where -100 is full left, +100 is full right, 0 is center)
        
        Returns:
            bool: True if command sent successfully
        """
        return self._send_audio_control_command(zone_id, 'balance', balance)
    
    def set_bass(self, zone_id: int, bass: int) -> bool:
        """
        Set bass level for individual zone
        
        Args:
            zone_id: Zone ID (1-8)
            bass: Bass level (-12 to +12, where -12 is minimum, +12 is maximum, 0 is neutral)
        
        Returns:
            bool: True if command sent successfully
        """
        return self._send_audio_control_command(zone_id, 'bass', bass)
    
    def set_treble(self, zone_id: int, treble: int) -> bool:
        """
        Set treble level for individual zone
        
        Args:
            zone_id: Zone ID (1-8)
            treble: Treble level (-12 to +12, where -12 is minimum, +12 is maximum, 0 is neutral)
        
        Returns:
            bool: True if command sent successfully
        """
        return self._send_audio_control_command(zone_id, 'treble', treble)
    
    def trigger_hng_sync(self) -> Dict[str, Any] | None:
        """
        Trigger HNG sync packet and decode all zone states
        
        Returns:
            Dict containing decoded zone states or None if failed
        """
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
            
            # Get input mappings from coordinator if available
            input_mappings = getattr(self, 'input_mappings', None)
            _LOGGER.debug("Using input mappings in trigger_hng_sync: %s", input_mappings)
            
            # Decode the packet
            result = self.hng_decoder.decode_hng_sync_packet(hng_hex, input_mappings)
            
            _LOGGER.debug("HNG sync decoded: %s packet with %d zones", 
                         result['packet_type'], len(result['zones']))
            
            return result
                
        except Exception as e:
            _LOGGER.error("HNG sync failed: %s", e)
            return None
    
    def _extract_hng_sync_packet(self, data: bytes) -> str | None:
        """
        Extract HNG sync packet from concatenated packet data
        
        Args:
            data: Raw packet data that may contain multiple packets
            
        Returns:
            Hex string of the HNG sync packet or None if not found
        """
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
    
    def get_zone_states(self, input_mappings: Dict[int, str]) -> Dict[str, Any]:
        """
        Get current state of all zones using HNG sync
        
        Args:
            input_mappings: Input mappings from device for proper input name decoding
            
        Returns:
            Dict containing zone states or empty dict if failed
        """
        # Store input mappings for use in trigger_hng_sync
        if input_mappings:
            self.input_mappings = input_mappings
            _LOGGER.debug("Stored input mappings: %s", input_mappings)
        else:
            _LOGGER.warning("No input mappings provided to get_zone_states")
        
        hng_result = self.trigger_hng_sync()
        if hng_result and 'zones' in hng_result:
            return hng_result['zones']
        return {}
    
    def get_zone_state(self, zone_id: int, input_mappings: Dict[int, str]) -> Dict[str, Any] | None:
        """
        Get current state of a specific zone using HNG sync
        
        Args:
            zone_id: Zone ID (1-8)
            input_mappings: Input mappings from device for proper input name decoding
            
        Returns:
            Dict containing zone state or None if failed
        """
        zone_states = self.get_zone_states(input_mappings)
        if zone_states and zone_id in zone_states:
            return zone_states[zone_id]
        return None