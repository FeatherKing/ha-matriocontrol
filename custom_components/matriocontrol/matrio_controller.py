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
import asyncio
from typing import Dict, List, Any, Optional, Callable

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
            zone_data = self.decode_zone(zone, packet, hng_start, input_mappings)
            result['zones'][zone_num] = zone_data
        
        return result
    
    def decode_zone(self, zone: int, packet: bytes, hng_start: int, input_mappings: Dict[int, str]) -> Dict[str, Any]:
        """Decode individual zone data"""

        # Input, volume, power, and mute all use the same byte offsets and
        # value conventions regardless of packet size (68-byte packets were
        # confirmed against a live capture with a single known zone toggled
        # - see decode_power_state/decode_mute_state).
        # Input state
        input_start = hng_start + 2  # bytes 2-9
        input_val = packet[input_start + zone]
        input_name = self.decode_input_selection(input_val, input_mappings)

        # Volume state
        volume_start = hng_start + 10  # bytes 10-17
        volume_val = packet[volume_start + zone]
        volume = self.decode_volume_level(volume_val)

        # Power state
        power_start = hng_start + 44  # bytes 44-51
        power_val = packet[power_start + zone]
        power = self.decode_power_state(power_val)

        # Balance state
        # Confirmed by differential analysis: balance is at position 34 + zone_index
        balance_start = hng_start + 34
        balance_val = packet[balance_start + zone]
        balance = self.decode_balance_state(balance_val)

        # Mute state - immediately follows power
        mute_start = hng_start + 52  # bytes 52-59
        mute_val = packet[mute_start + zone]
        mute = self.decode_mute_state(mute_val)

        # Bass and treble state - decode from specific byte positions
        bass, treble = self.decode_bass_treble(zone, packet, hng_start)

        # Get raw bass and treble values for raw_data
        bass_start = self.get_bass_start(hng_start)
        treble_start = self.get_treble_start(hng_start)
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
    
    def decode_power_state(self, power: int) -> str:
        """Decode zone power state - same convention for both packet sizes
        (0x02=ON, 0x01=OFF), matching BroadcastDecoder's live power
        broadcasts."""
        if power == 0x02:
            return "ON"
        elif power == 0x01:
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
    
    def decode_balance_state(self, balance: int) -> str:
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
    
    def decode_mute_state(self, mute: int) -> str:
        """Decode zone mute state - same convention for both packet sizes
        (0x01=Default, 0x02=Muted)."""
        if mute == 0x01:
            return "DEFAULT"
        elif mute == 0x02:
            return "MUTED"
        else:
            return f"UNKNOWN(0x{mute:02x})"

    
    def get_bass_start(self, hng_start: int) -> int:
        """Get the starting byte position for bass data"""
        # Confirmed by differential analysis: bass is at position 26 + zone_index
        return hng_start + 26

    def get_treble_start(self, hng_start: int) -> int:
        """Get the starting byte position for treble data"""
        # Confirmed by differential analysis: treble is at position 18 + zone_index
        return hng_start + 18

    def decode_bass_treble(self, zone: int, packet: bytes, hng_start: int) -> tuple[int, int]:
        """Decode bass and treble values from HNG sync packet"""

        bass_start = self.get_bass_start(hng_start)
        treble_start = self.get_treble_start(hng_start)
        
        bass_val = packet[bass_start + zone]
        treble_val = packet[treble_start + zone]
        
        # Based on differential analysis:
        # Bass: 0x0d is center (0), range appears to be 0x01 to 0x19 (1 to 25)
        # Treble: 0x0d is center (0), range appears to be 0x01 to 0x19 (1 to 25)
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
            _LOGGER.debug(f"BroadcastDecoder: Attempting to decode packet ({len(packet)} bytes): {packet_hex[:50]}...")
            
            # Check if this is a command echo packet (starts with 18961820)
            if len(packet) >= 4 and packet[:4] == b'\x18\x96\x18\x20':
                _LOGGER.debug("BroadcastDecoder: Detected command echo packet")
                return self._decode_command_echo_packet(packet)
            
            # Check if this is a direct broadcast packet (starts with 82)
            elif len(packet) >= 3 and packet[0] == 0x82:
                _LOGGER.debug("BroadcastDecoder: Detected direct broadcast packet")
                return self._decode_direct_broadcast_packet(packet)
            
            _LOGGER.debug("BroadcastDecoder: Packet not recognized as broadcast or command echo")
            return None
                
        except Exception as e:
            _LOGGER.error(f"BroadcastDecoder: Failed to decode packet: {e}")
            return None
    
    def _decode_command_echo_packet(self, packet: bytes) -> Optional[Dict[str, Any]]:
        """Decode command echo packet to extract the actual command"""
        try:
            _LOGGER.debug(f"BroadcastDecoder: Decoding command echo packet ({len(packet)} bytes)")
            
            # Extract payload (skip header + length + data = 20 bytes)
            if len(packet) < 20:
                _LOGGER.debug("BroadcastDecoder: Command echo packet too short")
                return None
                
            payload = packet[20:]
            _LOGGER.debug(f"BroadcastDecoder: Extracted payload ({len(payload)} bytes): {payload.hex()[:50]}...")
            
            # Look for MCU+PAS+ (4d43552b5041532b) + command
            if len(payload) < 10 or payload[:8] != b'MCU+PAS+':
                _LOGGER.debug("BroadcastDecoder: Payload does not contain MCU+PAS+ signature")
                return None
                
            # Extract command part (skip MCU+PAS+)
            command_part = payload[8:]
            _LOGGER.debug(f"BroadcastDecoder: Command part ({len(command_part)} bytes): {command_part.hex()}")
            
            if len(command_part) < 2:
                _LOGGER.debug("BroadcastDecoder: Command part too short")
                return None
                
            command = command_part[1]  # Skip 0x82, get command
            _LOGGER.debug(f"BroadcastDecoder: Extracted command: 0x{command:02x}")

            if command == 0x15:  # ALLNAMES: device sends this whenever zone/
                # input names change, not just at connect time. Its payload
                # is a run of length-prefixed name strings, not the 8-byte
                # value+zone-pattern shape every other command uses, so it
                # can't go through the 8-byte slice/_decode_command_data path
                # below - decode it directly from the unsliced remainder.
                return self._decode_names_command(command_part[2:])

            # Extract the actual broadcast data (skip 0x82 + command)
            if len(command_part) < 10:
                _LOGGER.debug("BroadcastDecoder: Command part too short for broadcast data")
                return None
                
            broadcast_data = command_part[2:10]  # 8 bytes: value + zone pattern
            _LOGGER.debug(f"BroadcastDecoder: Broadcast data: {broadcast_data.hex()}")
            
            # Decode based on command type
            result = self._decode_command_data(command, broadcast_data)
            _LOGGER.debug(f"BroadcastDecoder: Command data decode result: {result}")
            return result
            
        except Exception as e:
            _LOGGER.error(f"BroadcastDecoder: Failed to decode command echo packet: {e}")
            return None

    def _decode_names_command(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Decode an ALLNAMES (0x15) payload: device name + 8 zone names +
        8 input names, each a 1-byte-length-prefixed ASCII string. `data`
        must start at the device name's length byte."""
        try:
            pos = 0
            if pos >= len(data):
                return None
            device_name_len = data[pos]
            pos += 1 + device_name_len

            zone_names: Dict[int, str] = {}
            for zone_id in range(1, 9):
                if pos >= len(data):
                    break
                name_len = data[pos]
                pos += 1
                if pos + name_len > len(data):
                    break
                zone_names[zone_id] = data[pos:pos + name_len].decode('ascii', errors='ignore')[:16]
                pos += name_len

            input_names: Dict[int, str] = {}
            for input_id in range(1, 9):
                if pos >= len(data):
                    break
                name_len = data[pos]
                pos += 1
                if pos + name_len > len(data):
                    break
                input_names[input_id] = data[pos:pos + name_len].decode('ascii', errors='ignore')[:16]
                pos += name_len

            if not zone_names and not input_names:
                _LOGGER.debug("BroadcastDecoder: ALLNAMES payload yielded no names")
                return None

            _LOGGER.debug(
                "BroadcastDecoder: Decoded ALLNAMES - zones=%s inputs=%s", zone_names, input_names
            )
            return {
                "type": "names",
                "zone_names": zone_names,
                "input_names": input_names,
                "raw_command": "0x15",
            }
        except Exception as e:
            _LOGGER.debug("BroadcastDecoder: Failed to decode ALLNAMES command: %s", e)
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
            _LOGGER.debug("BroadcastDecoder: Command data too short")
            return None
            
        # Extract value (first byte) and zone pattern (remaining bytes)
        value = data[0]
        zone_pattern = data[1:]  # All bytes except the first (value byte) for zones 1-8
        
        _LOGGER.debug(f"BroadcastDecoder: Command 0x{command:02x}, value 0x{value:02x}, zone_pattern {zone_pattern.hex()}")
        
        # Find which zones are affected (0-based indexing)
        affected_zones = []
        
        # Handle 8-byte zone pattern (zones 1-8)
        if len(zone_pattern) == 8:
            for i, zone_val in enumerate(zone_pattern):
                if zone_val == 0x01:
                    affected_zones.append(i + 1)  # Convert to 1-based for display
        # Handle 7-byte zone pattern (zones 1-7) with special zone 8 handling
        elif len(zone_pattern) == 7:
            for i, zone_val in enumerate(zone_pattern):
                if zone_val == 0x01:
                    affected_zones.append(i + 1)  # Convert to 1-based for display
            # Check if this is a zone 8 pattern (all 0x02 values in 7-byte pattern)
            if all(zone_val == 0x02 for zone_val in zone_pattern):
                affected_zones.append(8)
        else:
            # Fallback: treat as zones 1-N where N is the length
            for i, zone_val in enumerate(zone_pattern):
                if zone_val == 0x01:
                    affected_zones.append(i + 1)  # Convert to 1-based for display
        
        _LOGGER.debug(f"BroadcastDecoder: Affected zones: {affected_zones}")
        
        # Decode based on command type
        if command == 0x08:  # Power command
            power_on = value == 0x02  # 0x02 = ON, 0x01 = OFF
            _LOGGER.debug(f"BroadcastDecoder: Power command - zones {affected_zones} -> {'ON' if power_on else 'OFF'}")
            return {
                "type": "power",
                "zones": affected_zones,
                "power_on": power_on,
                "raw_command": f"0x{command:02x}",
                "raw_data": data.hex()
            }
            
        elif command == 0x01:  # Volume command
            volume = max(0, value - 1)  # Convert from device value to UI value
            _LOGGER.debug(f"BroadcastDecoder: Volume command - zones {affected_zones} -> {volume}")
            return {
                "type": "volume",
                "zones": affected_zones,
                "volume": volume,
                "raw_command": f"0x{command:02x}",
                "raw_data": data.hex()
            }
            
        elif command == 0x0e:  # Mute command
            is_muted = value == 0x02
            _LOGGER.debug(f"BroadcastDecoder: Mute command - zones {affected_zones} -> {'MUTED' if is_muted else 'UNMUTED'}")
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
            _LOGGER.debug(f"BroadcastDecoder: Input command - zones {affected_zones} -> {input_name} (ID: {input_id})")
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
    """Complete controller for Dayton Audio multi-zone amplifiers using Matrio Control protocol"""

    # Shared request packet used both to bootstrap initial state on connect
    # (_send_binary_initialization) and to actively request a fresh full
    # zone-status resync (request_zone_sync) as a periodic fallback to
    # broadcast-driven updates.
    HNG_SYNC_REQUEST_PACKET = bytes.fromhex(
        "189618200f0000005706000000000000000000004d43552b5041532b820affffff8926"
    )

    # Give up on an in-flight sync request after this many seconds (or this
    # many buffered bytes) so a lost/garbled response can't wedge the reader
    # loop into treating all future broadcasts as sync-buffer data. Kept short
    # because the amp answers immediately and this also bounds how long
    # request_zone_sync holds _command_lock (blocking user commands) when the
    # device is unresponsive; unreachable-detection stays slow regardless,
    # since the coordinator throttles sync attempts to one per ~60s.
    SYNC_ABANDON_TIMEOUT = 2.0
    SYNC_BUFFER_MAX_BYTES = 4096

    # Idle timeout for each reader-loop read(). Bounds how quickly an abandoned
    # sync is detected (only re-checked when a read returns or times out), so
    # keep it under SYNC_ABANDON_TIMEOUT. Broadcasts are unaffected - a read
    # returns the instant data arrives.
    READ_TIMEOUT = 1.0

    # Require this many consecutive abandoned sync round-trips before
    # declaring the device unreachable, so a single transient blip (e.g. a
    # brief Wi-Fi hiccup) doesn't force a reconnect on its own - only a
    # sustained failure to respond does. Worst-case detection latency this
    # adds: (SYNC_FAILURE_THRESHOLD - 1) extra ~60s poll cycles.
    SYNC_FAILURE_THRESHOLD = 2

    # Bounds how long writer.write()/drain() itself is allowed to block
    # before giving up - this is local socket buffering, not waiting on the
    # device, so it should always be fast. Without this, a wedged TCP send
    # buffer would hold _command_lock indefinitely and stall every other
    # queued command/sync request behind it.
    COMMAND_WRITE_TIMEOUT = 2.0

    # A Matrio device can accept the TCP connection before its protocol
    # services are ready (notably just after a reboot).  Keep startup
    # recovery bounded so Home Assistant is not held up indefinitely.
    CONNECT_RETRY_DELAYS = (1.0, 2.0, 4.0)

    # Supported HNG sync packet sizes. A short packet is complete before the
    # 96-byte threshold only when its protocol terminator is present; that
    # distinguishes it from the first 68 bytes of a fragmented long packet.
    SYNC_PACKET_SHORT_BYTES = 68
    SYNC_PACKET_COMPLETE_BYTES = 96
    SYNC_PACKET_TERMINATOR = b'\xff\xff\xcc\x26'

    def __init__(self, ip: str, port: int = 8899):
        """
        Initialize Matrio controller
        
        Args:
            ip: IP address of the Matrio-compatible device
            port: TCP port (default 8899 - the actual communication port)
        """
        self.ip = ip
        self.port = port
        self.reader = None
        self.writer = None
        self.zones = {}
        self.zone_names = {}
        self.hng_decoder = UniversalHNGSyncDecoder()
        self.broadcast_decoder = None
        self.state_callback = None
        self.connected = False
        self._reader_task = None
        self._writer_task = None

        # State for an in-flight active zone-status resync request (see
        # request_zone_sync / _reader_loop). Reset on connect()/disconnect()
        # since this MatrioController instance survives reconnects.
        self._awaiting_sync: bool = False
        self._sync_buffer: bytes = b""
        self._sync_chunk_count: int = 0
        self._sync_started_monotonic: float = 0.0
        # Set by _process_sync_chunk when it abandons an in-flight sync
        # request with no valid response - _reader_loop treats this as a
        # liveness failure and ends the connection so the coordinator
        # reconnects, instead of silently keeping a stale "connected" state.
        self._sync_unreachable: bool = False
        # Counts consecutive abandoned sync round-trips; reset to 0 on any
        # successful round-trip (_finish_sync) or fresh connect()/disconnect().
        self._consecutive_sync_failures: int = 0
        # Resolved by _finish_sync() (True) or the abandon path in
        # _process_sync_chunk (False) so request_zone_sync() can await the
        # actual round-trip outcome instead of returning as soon as the
        # request is written.
        self._sync_result_future: Optional[asyncio.Future] = None

        # Serializes all outbound zone commands (power/input/volume/mute/
        # audio control) *and* active sync requests, so only one
        # write-then-await-response cycle - of either kind - is ever in
        # flight at a time, and all of them route their responses through
        # the single persistent _reader_loop instead of racing their own
        # reader.read() against it or against each other.
        # _pending_command_response is reset on connect()/disconnect(); the
        # lock itself never needs resetting - every holder releases it via
        # `async with`, even when the awaited response times out.
        self._command_lock: asyncio.Lock = asyncio.Lock()
        self._pending_command_response: Optional[asyncio.Future] = None

        # Default input mapping based on capture analysis
        self.inputs = {
            1: "Input1",
            2: "Input2", 
            3: "Input3",
            4: "Input4",
            5: "Input5",
            6: "Input6",
            7: "Input7",
            8: "Input8"
        }

    @property
    def has_pending_sync_failure(self) -> bool:
        """True if the most recent zone-sync round-trip failed but hasn't
        yet reached SYNC_FAILURE_THRESHOLD. The coordinator uses this to
        retry sooner than its normal poll interval, so an unreachable device
        is confirmed in a couple of short retries instead of waiting a full
        poll interval between each of the required consecutive failures."""
        return self._consecutive_sync_failures > 0

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
        
    async def connect(self, state_callback: Optional[Callable] = None) -> bool:
        """Connect to Matrio-compatible device and start reader/writer tasks"""
        for attempt in range(1, len(self.CONNECT_RETRY_DELAYS) + 2):
            if await self._connect_once(state_callback):
                return True

            if attempt <= len(self.CONNECT_RETRY_DELAYS):
                delay = self.CONNECT_RETRY_DELAYS[attempt - 1]
                _LOGGER.warning(
                    "Matrio startup attempt %d failed; retrying in %.0f seconds",
                    attempt,
                    delay,
                )
                await asyncio.sleep(delay)

        _LOGGER.error(
            "Unable to initialize Matrio controller after %d startup attempts",
            len(self.CONNECT_RETRY_DELAYS) + 1,
        )
        return False

    async def _connect_once(self, state_callback: Optional[Callable] = None) -> bool:
        """Attempt one complete TCP and protocol initialization sequence."""
        try:
            _LOGGER.debug(f"Attempting to connect to Matrio device at {self.ip}:{self.port}")

            # This instance survives reconnects. If the reader loop broke out
            # on a liveness failure it just flipped `connected` to False without
            # closing the socket, so tear down any leftover connection here
            # before opening a new one to avoid orphaning the old writer/FD.
            if self.writer is not None or self._reader_task is not None:
                _LOGGER.debug("Tearing down stale connection before reconnecting")
                await self.disconnect()

            # Create connection
            self.reader, self.writer = await asyncio.open_connection(self.ip, self.port)
            _LOGGER.info(f"TCP connection established to {self.ip}:{self.port}")
            _LOGGER.debug(f"Reader: {self.reader}, Writer: {self.writer}")

            # This MatrioController instance survives reconnects, so clear
            # any in-flight sync-request state left over from a prior
            # connection before it can wedge the new reader loop.
            self._reset_sync_state()
            self._pending_command_response = None
            self._consecutive_sync_failures = 0

            # Store state callback
            self.state_callback = state_callback
            _LOGGER.debug(f"State callback set: {state_callback is not None}")
            
            # Initialize the device with the required protocol sequence
            _LOGGER.debug("Starting device initialization sequence...")
            if await self._initialize_device():
                _LOGGER.info("Device initialization completed successfully")
                
                # Initialize broadcast decoder
                self.broadcast_decoder = BroadcastDecoder(self.inputs)
                _LOGGER.debug("Broadcast decoder initialized with input mappings: %s", self.inputs)
                
                # Start reader and writer tasks
                _LOGGER.debug("Starting reader and writer tasks...")
                self._reader_task = asyncio.create_task(self._reader_loop())
                self._writer_task = asyncio.create_task(self._writer_loop())
                _LOGGER.debug("Reader task: %s, Writer task: %s", self._reader_task, self._writer_task)
                
                self.connected = True
                _LOGGER.info("Matrio controller fully connected and ready")
                return True
            else:
                _LOGGER.debug("Device initialization did not complete")
                await self.disconnect()
                return False
        except Exception as e:
            _LOGGER.debug("Connection attempt failed: %s", e)
            await self.disconnect()
            return False
    
    async def _initialize_device(self) -> bool:
        """
        Initialize the device with the required UPnP and binary protocol sequence
        This is required before the device will accept control commands
        """
        try:
            _LOGGER.debug("Step 1: Setting up UPnP event subscriptions...")
            # Step 1: UPnP Event Subscriptions
            if not await self._setup_upnp_subscriptions():
                _LOGGER.debug("UPnP event subscriptions failed")
                return False
            _LOGGER.debug("UPnP event subscriptions completed successfully")
            
            _LOGGER.debug("Step 2: Sending SOAP commands...")
            # Step 2: SOAP Commands
            if not await self._send_soap_commands():
                _LOGGER.debug("SOAP commands failed")
                return False
            _LOGGER.debug("SOAP commands completed successfully")
            
            _LOGGER.debug("Step 3: Binary protocol initialization...")
            # Step 3: Binary Protocol Initialization
            if not await self._send_binary_initialization():
                _LOGGER.debug("Binary protocol initialization failed")
                return False
            _LOGGER.debug("Binary protocol initialization completed successfully")
            
            _LOGGER.info("All device initialization steps completed successfully")
            return True
            
        except Exception as e:
            _LOGGER.debug("Device initialization failed: %s", e)
            return False
    
    async def _reader_loop(self):
        """Reader loop that handles incoming packets and broadcasts"""
        try:
            _LOGGER.debug("Reader loop started")
            
            # First, get initial state via HNG sync
            _LOGGER.debug("Getting initial device state via HNG sync...")
            await self._get_initial_state()
            _LOGGER.debug("Initial state retrieval completed")
            
            # Then listen for broadcast packets
            _LOGGER.info("Starting broadcast packet listener...")
            packet_count = 0
            while self.connected:
                try:
                    # Read data with timeout
                    data = await asyncio.wait_for(self.reader.read(1024), timeout=self.READ_TIMEOUT)
                    
                    if len(data) == 0:
                        _LOGGER.warning("Connection lost - received empty data")
                        break

                    packet_count += 1

                    if self._pending_command_response is not None and not self._pending_command_response.done():
                        # This chunk is the ack for an in-flight command sent
                        # via _send_and_await_response() - deliver it there.
                        # It still falls through to normal broadcast decoding
                        # below instead of `continue`-ing past it: a command
                        # echo is itself a decodable broadcast (it carries the
                        # zone/value the device actually applied), and the
                        # device can coalesce it with a genuine unrelated
                        # broadcast in the same read. Skipping decode here
                        # used to silently drop that state update until the
                        # next periodic resync caught up.
                        self._pending_command_response.set_result(data)

                    if self._awaiting_sync:
                        # This chunk is (part of) the response to an active
                        # request_zone_sync() call - route it through the
                        # sync buffer instead of normal broadcast decoding.
                        # Any bytes that arrived after the sync packet are
                        # returned so they still get decoded normally below.
                        data = self._process_sync_chunk(data)
                        if self._sync_unreachable:
                            # Device didn't respond to the sync request in
                            # time - treat as a liveness failure and end the
                            # loop (the finally block below flips `connected`
                            # to False so the coordinator reconnects) rather
                            # than silently keep serving a stale cache.
                            _LOGGER.warning("Ending reader loop - device did not respond to zone sync request")
                            break
                        if data is None:
                            continue

                    _LOGGER.debug(f"Received packet #{packet_count} ({len(data)} bytes): {data.hex()}")
                    await self._decode_and_handle_broadcast(data)

                except asyncio.TimeoutError:
                    # Timeout is expected, continue listening. If we're still
                    # waiting on a sync response and it's been long enough,
                    # give _process_sync_chunk a chance to decode whatever is
                    # already buffered (e.g. both response writes arrived in
                    # a single earlier read, satisfying the response in one
                    # chunk) before falling back to abandoning it outright.
                    if self._awaiting_sync and self._sync_timed_out():
                        leftover = self._process_sync_chunk(b"")
                        if self._sync_unreachable:
                            _LOGGER.warning("Ending reader loop - device did not respond to zone sync request")
                            break
                        if leftover:
                            await self._decode_and_handle_broadcast(leftover)
                    continue
                except Exception as e:
                    if self.connected:
                        _LOGGER.error(f"Error in reader loop: {e}")
                    break
                    
        except Exception as e:
            _LOGGER.error(f"Reader loop failed: {e}")
        finally:
            _LOGGER.debug("Reader loop ending, setting connected=False")
            self.connected = False
    
    async def _writer_loop(self):
        """Writer loop that handles outgoing commands"""
        try:
            while self.connected:
                # This loop can be used for queued commands if needed
                await asyncio.sleep(0.1)
        except Exception as e:
            _LOGGER.error(f"Writer loop failed: {e}")
        finally:
            self.connected = False
    
    async def _get_initial_state(self):
        """Get initial device state - now handled in binary initialization"""
        try:
            _LOGGER.debug("Initial state already retrieved during binary initialization")
            
            # Notify callback of initial state if we have zone data
            if self.zones and self.state_callback:
                _LOGGER.debug("Calling state callback with initial state...")
                self.state_callback(self.zones)
                _LOGGER.debug("State callback completed")
            else:
                _LOGGER.debug("No zone data or state callback available")
                
        except Exception as e:
            # Initial state has already been decoded during binary startup.
            # A callback can fail while Home Assistant is still bringing up
            # its event loop; the coordinator's normal refresh path will
            # publish the cached state instead of treating this as a failed
            # device connection.
            _LOGGER.warning("Initial-state callback failed; it will be retried by the next refresh: %s", e)
    
    def _parse_allnames_response(self, response: bytes) -> Dict[str, str]:
        """Parse ALLNAMES response to extract zone and input names"""
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
            
            # The data starts immediately after the protocol header
            data = payload
            _LOGGER.debug("ALLNAMES data length: %d bytes", len(data))
            _LOGGER.debug("ALLNAMES data hex: %s", data.hex()[:200])
            
            # Parse length-prefixed strings
            names = {}
            pos = 0
            
            # Skip MCU+PAS+ (8 bytes) and 8215 command (2 bytes)
            if len(data) < 10:
                raise RuntimeError("Data too short for MCU+PAS+ and command")
            
            # Verify MCU+PAS+ header
            if data[0:8] != b'MCU+PAS+':
                raise RuntimeError("Invalid MCU+PAS+ header")
            
            # Verify 8215 command
            if data[8:10] != b'\x82\x15':
                raise RuntimeError("Invalid 8215 command")
            
            pos = 10  # Skip MCU+PAS+ and 8215 command
            
            # First string is device name (length 0x0b = 11 bytes)
            if pos + 1 > len(data):
                raise RuntimeError("No device name length found")
            
            device_name_len = data[pos]
            pos += 1
            _LOGGER.debug("Device name length: %d (0x%02x)", device_name_len, device_name_len)
            
            if pos + device_name_len > len(data):
                raise RuntimeError("Device name extends beyond data")
            
            device_name = data[pos:pos + device_name_len].decode('ascii', errors='ignore')
            pos += device_name_len
            _LOGGER.debug("Device name: '%s'", device_name)
            
            # Parse zone names (8 zones)
            zone_names = []
            for zone_id in range(8):
                if pos >= len(data):
                    _LOGGER.debug("Reached end of data at zone %d, pos=%d, len=%d", zone_id, pos, len(data))
                    zone_names.append(f"Zone {zone_id + 1}")  # Add fallback name
                    continue
                
                if pos + 1 > len(data):
                    _LOGGER.debug("No length byte for zone %d, pos=%d, len=%d", zone_id, pos, len(data))
                    zone_names.append(f"Zone {zone_id + 1}")  # Add fallback name
                    continue
                
                name_len = data[pos]
                pos += 1
                _LOGGER.debug("Zone %d name length: %d (0x%02x), pos=%d", zone_id, name_len, name_len, pos)
                
                if pos + name_len > len(data):
                    _LOGGER.debug("Zone %d name extends beyond data, pos=%d, name_len=%d, data_len=%d", zone_id, pos, name_len, len(data))
                    zone_names.append(f"Zone {zone_id + 1}")  # Add fallback name
                    continue
                
                zone_name = data[pos:pos + name_len].decode('ascii', errors='ignore')
                # Truncate to 16 characters if longer
                if len(zone_name) > 16:
                    zone_name = zone_name[:16]
                zone_names.append(zone_name)
                _LOGGER.debug("Zone %d name: '%s', pos after: %d", zone_id, zone_name, pos + name_len)
                pos += name_len
            
            # Parse input names (8 inputs)
            input_names = []
            for input_id in range(8):
                if pos >= len(data):
                    _LOGGER.debug("Reached end of data at input %d, pos=%d, len=%d", input_id, pos, len(data))
                    # If we've reached the end of data, Input 8 is typically "Wi-Fi"
                    if input_id == 7:  # Input 8 (index 7)
                        input_names.append("Wi-Fi")
                    break
                
                if pos + 1 > len(data):
                    _LOGGER.debug("No length byte for input %d, pos=%d, len=%d", input_id, pos, len(data))
                    # If we can't read the full name, Input 8 is typically "Wi-Fi"
                    if input_id == 7:  # Input 8 (index 7)
                        input_names.append("Wi-Fi")
                    break
                
                name_len = data[pos]
                pos += 1
                _LOGGER.debug("Input %d name length: %d (0x%02x), pos=%d", input_id, name_len, name_len, pos)
                
                if pos + name_len > len(data):
                    _LOGGER.debug("Input %d name extends beyond data, pos=%d, name_len=%d, data_len=%d", input_id, pos, name_len, len(data))
                    # If we can't read the full name, Input 8 is typically "Wi-Fi"
                    if input_id == 7:  # Input 8 (index 7)
                        input_names.append("Wi-Fi")
                    break
                
                input_name = data[pos:pos + name_len].decode('ascii', errors='ignore')
                # Truncate to 16 characters if longer
                if len(input_name) > 16:
                    input_name = input_name[:16]
                input_names.append(input_name)
                _LOGGER.debug("Input %d name: '%s', pos after: %d", input_id, input_name, pos + name_len)
                pos += name_len
            
            # Ensure we have exactly 8 input names (pad with "Wi-Fi" for Input 8 if missing)
            while len(input_names) < 8:
                if len(input_names) == 7:  # Input 8 (index 7)
                    input_names.append("Wi-Fi")
                else:
                    input_names.append(f"Input{len(input_names) + 1}")
            
            _LOGGER.debug("Parsed zone names: %s", zone_names)
            _LOGGER.debug("Parsed input names: %s", input_names)
            
            # Build the names dictionary
            for i, zone_name in enumerate(zone_names):
                names[f"zone_{i}"] = zone_name
            
            for i, input_name in enumerate(input_names):
                names[f"input_{i+1}"] = input_name
            
            return names
            
        except Exception as e:
            _LOGGER.error("ALLNAMES parsing failed: %s", e)
            _LOGGER.debug("Response that failed to parse: %s", response.hex())
            raise RuntimeError(f"Failed to parse zone/input names from response: {e}")
    
    async def _decode_and_handle_broadcast(self, data: bytes) -> None:
        """Decode a chunk as a broadcast/command-echo packet and apply it."""
        if not data:
            return

        if not self.broadcast_decoder:
            _LOGGER.warning("Broadcast decoder not initialized")
            return

        packet_hex = data.hex()
        _LOGGER.debug("Attempting to decode packet as broadcast...")
        broadcast_info = self.broadcast_decoder.decode_packet(packet_hex)

        if broadcast_info:
            _LOGGER.debug(f"Successfully decoded broadcast: {broadcast_info}")
            await self._handle_broadcast(broadcast_info)
        else:
            _LOGGER.debug("Packet is not a recognized broadcast packet")

    async def _handle_broadcast(self, broadcast_info: Dict[str, Any]):
        """Handle broadcast packet and update state"""
        try:
            change_type = broadcast_info['type']

            if change_type == "names":
                # Not zone-scoped like the broadcasts below - the device
                # sends this whenever zone/input names are edited (e.g. from
                # the mobile app), not just during initial connect, so it's
                # the only reliable way to pick up a rename after startup.
                zone_names = broadcast_info.get('zone_names', {})
                input_names = broadcast_info.get('input_names', {})
                if zone_names:
                    self.zone_names.update(zone_names)
                    _LOGGER.info("Zone names updated from device: %s", zone_names)
                if input_names:
                    self.inputs.update(input_names)
                    _LOGGER.info("Input names updated from device: %s", input_names)
                if (zone_names or input_names) and self.state_callback:
                    self.state_callback(self.zones)
                return

            zones = broadcast_info.get('zones', [])
            raw_command = broadcast_info.get('raw_command', 'unknown')
            raw_data = broadcast_info.get('raw_data', 'unknown')

            _LOGGER.debug(f"Handling broadcast: type={change_type}, zones={zones}, command={raw_command}, data={raw_data}")

            if not zones:
                _LOGGER.debug(f"{change_type.upper()}: No zones affected")
                return
            
            _LOGGER.info(f"Broadcast received: {change_type.upper()} for zones {zones}")
            
            # Update zone states based on broadcast
            for zone_id in zones:
                if zone_id not in self.zones:
                    _LOGGER.debug(f"Creating new zone entry for zone {zone_id}")
                    self.zones[zone_id] = {}
                
                old_value = None
                if change_type == "power":
                    old_value = self.zones[zone_id].get('power')
                    self.zones[zone_id]['power'] = "ON" if broadcast_info['power_on'] else "OFF"
                    _LOGGER.debug(f"Zone {zone_id} power: {old_value} -> {self.zones[zone_id]['power']}")
                elif change_type == "volume":
                    old_value = self.zones[zone_id].get('volume')
                    self.zones[zone_id]['volume'] = broadcast_info['volume']
                    _LOGGER.debug(f"Zone {zone_id} volume: {old_value} -> {self.zones[zone_id]['volume']}")
                elif change_type == "mute":
                    old_value = self.zones[zone_id].get('mute')
                    self.zones[zone_id]['mute'] = "MUTED" if broadcast_info['muted'] else "DEFAULT"
                    _LOGGER.debug(f"Zone {zone_id} mute: {old_value} -> {self.zones[zone_id]['mute']}")
                elif change_type == "input":
                    old_value = self.zones[zone_id].get('input')
                    self.zones[zone_id]['input'] = broadcast_info['input_name']
                    _LOGGER.debug(f"Zone {zone_id} input: {old_value} -> {self.zones[zone_id]['input']}")
                elif change_type == "balance":
                    old_value = self.zones[zone_id].get('balance')
                    self.zones[zone_id]['balance'] = str(broadcast_info['balance'])
                    _LOGGER.debug(f"Zone {zone_id} balance: {old_value} -> {self.zones[zone_id]['balance']}")
                elif change_type == "bass":
                    old_value = self.zones[zone_id].get('bass')
                    self.zones[zone_id]['bass'] = broadcast_info['bass']
                    _LOGGER.debug(f"Zone {zone_id} bass: {old_value} -> {self.zones[zone_id]['bass']}")
                elif change_type == "treble":
                    old_value = self.zones[zone_id].get('treble')
                    self.zones[zone_id]['treble'] = broadcast_info['treble']
                    _LOGGER.debug(f"Zone {zone_id} treble: {old_value} -> {self.zones[zone_id]['treble']}")
                elif change_type == "total_volume":
                    old_value = self.zones[zone_id].get('volume')
                    self.zones[zone_id]['volume'] = broadcast_info['volume']
                    _LOGGER.debug(f"Zone {zone_id} total volume: {old_value} -> {self.zones[zone_id]['volume']}")
            
            _LOGGER.debug(f"State updated for zones {zones} - {change_type}")
            
            # Notify callback of state change
            if self.state_callback:
                _LOGGER.debug("Calling state callback with updated state...")
                self.state_callback(self.zones)
                _LOGGER.debug("State callback completed")
            else:
                _LOGGER.debug("No state callback set, skipping notification")
                
        except Exception as e:
            _LOGGER.error(f"Failed to handle broadcast: {e}")

    def _sync_buffer_has_complete_packet(self) -> bool:
        """True once the sync buffer holds a complete supported HNG packet."""
        sig_pos = self._sync_buffer.find(b'\x82\x0c')
        if sig_pos == -1:
            return False

        available = len(self._sync_buffer) - sig_pos
        if available >= self.SYNC_PACKET_COMPLETE_BYTES:
            return True

        short_end = sig_pos + self.SYNC_PACKET_SHORT_BYTES
        return (
            available >= self.SYNC_PACKET_SHORT_BYTES
            and self._sync_buffer[short_end - len(self.SYNC_PACKET_TERMINATOR):short_end]
            == self.SYNC_PACKET_TERMINATOR
        )

    def _sync_timed_out(self) -> bool:
        """Check whether the in-flight request_zone_sync() has taken too long."""
        return time.monotonic() - self._sync_started_monotonic > self.SYNC_ABANDON_TIMEOUT

    def _process_sync_chunk(self, data: bytes) -> Optional[bytes]:
        """
        Feed a chunk of data into the in-flight active sync buffer.

        Returns any leftover bytes that should still be run through normal
        broadcast decoding (e.g. a broadcast packet that happened to arrive
        appended right after the sync response), or None if the whole chunk
        was consumed or the sync response is still incomplete.
        """
        self._sync_buffer += data
        self._sync_chunk_count += 1

        # Attempt extraction once either the framed 68-byte response or the
        # full 96-byte response has arrived. The short-packet terminator check
        # prevents a fragmented long packet from being decoded prematurely.
        if self._sync_buffer_has_complete_packet():
            hng_hex = self._extract_hng_sync_packet(self._sync_buffer)
            if hng_hex:
                return self._finish_sync(hng_hex)

        if self._sync_timed_out() or len(self._sync_buffer) > self.SYNC_BUFFER_MAX_BYTES:
            # An abandoned buffer never reached a complete packet (the gate
            # above would have decoded it otherwise), so don't risk decoding a
            # truncated response - release whatever's buffered for normal
            # broadcast decoding instead.
            _LOGGER.warning(
                "Abandoning zone sync request - no valid response after %d bytes / %.1fs / %d chunk(s)",
                len(self._sync_buffer), time.monotonic() - self._sync_started_monotonic, self._sync_chunk_count,
            )
            leftover = self._sync_buffer
            result_future = self._sync_result_future
            self._reset_sync_state()

            # Require SYNC_FAILURE_THRESHOLD consecutive abandoned round-trips
            # before treating this as a liveness failure, so a single
            # transient blip doesn't force a reconnect on its own.
            self._consecutive_sync_failures += 1
            if self._consecutive_sync_failures >= self.SYNC_FAILURE_THRESHOLD:
                _LOGGER.warning(
                    "Zone sync abandoned %d times in a row - treating device as unreachable",
                    self._consecutive_sync_failures,
                )
                self._sync_unreachable = True

            if result_future is not None and not result_future.done():
                result_future.set_result(False)

            return leftover if leftover else None

        # Still waiting on more data to complete the sync response.
        return None

    def _finish_sync(self, hng_hex: str) -> Optional[bytes]:
        """Decode an extracted HNG sync packet, merge it in, and reset sync state."""
        _LOGGER.debug("DIAG hng_hex: %s", hng_hex)
        sig_pos = self._sync_buffer.find(b'\x82\x0c')
        consumed_end = sig_pos + len(hng_hex) // 2 if sig_pos != -1 else len(self._sync_buffer)
        leftover = self._sync_buffer[consumed_end:]

        result_future = self._sync_result_future
        self._reset_sync_state()
        # A complete packet was received - the round-trip itself succeeded
        # at the transport level (independent of whether the payload below
        # decodes cleanly), so the device has proven it's reachable.
        self._consecutive_sync_failures = 0
        if result_future is not None and not result_future.done():
            result_future.set_result(True)

        try:
            result = self.hng_decoder.decode_hng_sync_packet(hng_hex, self.inputs)
            if result and 'zones' in result:
                self._handle_full_sync(result)
            else:
                _LOGGER.warning("Zone sync response could not be decoded")
        except Exception as e:
            _LOGGER.error(f"Failed to decode zone sync response: {e}")

        return leftover if leftover else None

    def _reset_sync_state(self) -> None:
        self._awaiting_sync = False
        self._sync_buffer = b""
        self._sync_chunk_count = 0
        self._sync_unreachable = False
        self._sync_result_future = None

    def _handle_full_sync(self, hng_result: Dict[str, Any]) -> None:
        """Merge a decoded full zone-status sync into self.zones and notify."""
        zones = hng_result.get('zones', {})
        if not zones:
            _LOGGER.debug("Zone sync response contained no zones")
            return

        _LOGGER.info("Zone sync response received: %d zones", len(zones))

        for zone_id, zone_data in zones.items():
            self.zones.setdefault(zone_id, {})
            for key in ('power', 'input', 'volume', 'mute', 'balance', 'bass', 'treble', 'raw_data'):
                if key in zone_data:
                    self.zones[zone_id][key] = zone_data[key]
            _LOGGER.debug(f"Zone {zone_id} synced: {self.zones[zone_id]}")

        if self.state_callback:
            _LOGGER.debug("Calling state callback with synced state...")
            self.state_callback(self.zones)
            _LOGGER.debug("State callback completed")
        else:
            _LOGGER.debug("No state callback set, skipping notification")

    async def _setup_upnp_subscriptions(self) -> bool:
        """Setup UPnP event subscriptions on port 59152"""
        try:
            upnp_port = 59152
            
            # Subscribe to rendertransport1 events. _get_local_ip does a
            # blocking synchronous socket.connect(), so run it in an executor
            # rather than stalling the HA event loop.
            local_ip = await asyncio.get_running_loop().run_in_executor(
                None, self._get_local_ip
            )
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
            
            reader1, writer1 = await asyncio.open_connection(self.ip, upnp_port)
            writer1.write(subscribe_request1.encode())
            await writer1.drain()
            response1 = await reader1.read(1024)
            writer1.close()
            await writer1.wait_closed()
            
            # Small delay between subscriptions
            import time
            await asyncio.sleep(0.5)
            
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
            
            reader2, writer2 = await asyncio.open_connection(self.ip, upnp_port)
            writer2.write(subscribe_request2.encode())
            await writer2.drain()
            response2 = await reader2.read(1024)
            writer2.close()
            await writer2.wait_closed()
            
            await asyncio.sleep(0.5)
            
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
            
            reader3, writer3 = await asyncio.open_connection(self.ip, upnp_port)
            writer3.write(subscribe_request3.encode())
            await writer3.drain()
            response3 = await reader3.read(1024)
            writer3.close()
            await writer3.wait_closed()
            
            return True
            
        except Exception as e:
            _LOGGER.debug("UPnP subscription failed: %s", e)
            return False
    
    async def _send_soap_commands(self) -> bool:
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
            
            reader4, writer4 = await asyncio.open_connection(self.ip, upnp_port)
            writer4.write(soap_request1.encode())
            await writer4.drain()
            response4 = await reader4.read(1024)
            writer4.close()
            await writer4.wait_closed()
            
            await asyncio.sleep(0.5)
            
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
            
            reader5, writer5 = await asyncio.open_connection(self.ip, upnp_port)
            writer5.write(soap_request2.encode())
            await writer5.drain()
            response5 = await reader5.read(1024)
            writer5.close()
            await writer5.wait_closed()
            
            await asyncio.sleep(0.5)
            
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
            
            reader6, writer6 = await asyncio.open_connection(self.ip, upnp_port)
            writer6.write(soap_request3.encode())
            await writer6.drain()
            response6 = await reader6.read(1024)
            writer6.close()
            await writer6.wait_closed()
            
            return True
            
        except Exception as e:
            _LOGGER.debug("SOAP commands failed: %s", e)
            return False
    
    async def _send_binary_initialization(self) -> bool:
        """Send binary protocol initialization sequence"""
        try:
            if self.reader is None or self.writer is None:
                _LOGGER.debug("Binary initialization skipped without an active connection")
                return False

            # Send initialization command (0x0a)
            self.writer.write(self.HNG_SYNC_REQUEST_PACKET)
            await self.writer.drain()
            
            # Wait for HNG_SYNC_COMMAND response
            sync_response = await asyncio.wait_for(self.reader.read(1024), timeout=5.0)
            if len(sync_response) == 0:
                return False
            
            # Wait for the second response. Historically assumed to always be
            # ALLNAMES (with the first always being the HNG sync reply), but
            # a reconnect racing an in-flight sync request can make the
            # device answer with two sync-shaped packets instead - so every
            # response read here is checked by content below rather than by
            # its position.
            allnames_response = await asyncio.wait_for(self.reader.read(1024), timeout=5.0)
            if len(allnames_response) == 0:
                return False

            # Parse ALLNAMES response to get device names immediately. Try
            # both reads rather than assuming allnames_response holds it -
            # order between the two isn't guaranteed (see comment above).
            allnames_data = None
            for candidate in (allnames_response, sync_response):
                try:
                    _LOGGER.debug("Trying to parse as ALLNAMES: %d bytes", len(candidate))
                    allnames_data = self._parse_allnames_response(candidate)
                    _LOGGER.info("Parsed ALLNAMES data: %s", allnames_data)
                    break
                except Exception as e:
                    _LOGGER.debug("Not a parseable ALLNAMES response: %s", e)

            if allnames_data is not None:
                # Update input mappings with actual device names
                for i in range(1, 9):
                    input_key = f"input_{i}"
                    if input_key in allnames_data:
                        self.inputs[i] = allnames_data[input_key]
                        _LOGGER.debug("Updated input %d: %s", i, allnames_data[input_key])

                # Store zone names
                self.zone_names = {}
                for i in range(8):
                    zone_key = f"zone_{i}"
                    if zone_key in allnames_data:
                        self.zone_names[i+1] = allnames_data[zone_key]
                        _LOGGER.debug("Updated zone %d: %s", i+1, allnames_data[zone_key])
            else:
                _LOGGER.warning(
                    "Neither initialization response contained parseable ALLNAMES data"
                )
                # Set default names if ALLNAMES parsing failed
                self.zone_names = {i: f"Zone {i}" for i in range(1, 9)}

            # Extract HNG sync data from the combined responses (like broadcast decoder)
            _LOGGER.debug("Extracting HNG sync data from combined responses...")
            combined_data = sync_response + allnames_response
            _LOGGER.debug("Combined data: %d bytes", len(combined_data))
            
            # Extract HNG sync packet from the combined data
            hng_hex = self._extract_hng_sync_packet(combined_data)
            if hng_hex:
                _LOGGER.debug("Extracted HNG sync packet: %d bytes", len(hng_hex) // 2)
                
                # Decode the HNG sync packet to get initial zone states
                result = self.hng_decoder.decode_hng_sync_packet(hng_hex, self.inputs)
                
                if result and 'zones' in result:
                    self.zones = result['zones']
                    _LOGGER.info("Initial zone states received: %d zones", len(self.zones))
                    _LOGGER.debug("Zone details: %s", {k: v for k, v in self.zones.items()})
                else:
                    _LOGGER.warning("Could not decode HNG sync packet")
                    # Set default zone states if HNG sync fails
                    self.zones = {i: {'power': 'OFF', 'input': 'Input1', 'volume': 0, 'mute': 'DEFAULT', 'balance': 'Default', 'bass': 0, 'treble': 0} for i in range(1, 9)}
                    _LOGGER.info("Using default zone states due to HNG sync decode failure")
            else:
                _LOGGER.warning("Could not extract HNG sync packet from combined data")
                # Set default zone states if HNG sync extraction fails
                self.zones = {i: {'power': 'OFF', 'input': 'Input1', 'volume': 0, 'mute': 'DEFAULT', 'balance': 'Default', 'bass': 0, 'treble': 0} for i in range(1, 9)}
                _LOGGER.info("Using default zone states due to HNG sync extraction failure")
            
            return True
            
        except Exception as e:
            _LOGGER.debug("Binary initialization failed: %s", e)
            return False
    
    async def disconnect(self):
        """Disconnect from device"""
        _LOGGER.debug("Starting disconnect process...")
        self.connected = False
        
        # Cancel reader and writer tasks
        if self._reader_task:
            _LOGGER.debug("Cancelling reader task...")
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                _LOGGER.debug("Reader task cancelled successfully")
                pass
        
        if self._writer_task:
            _LOGGER.debug("Cancelling writer task...")
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                _LOGGER.debug("Writer task cancelled successfully")
                pass
        
        # Close connection
        writer = self.writer
        self.reader = None
        self.writer = None
        if writer:
            _LOGGER.debug("Closing writer connection...")
            try:
                writer.close()
                await writer.wait_closed()
                _LOGGER.debug("Writer connection closed")
            except (AttributeError, OSError, RuntimeError) as err:
                # The peer (or a prior teardown) may already have dropped the
                # socket, making close()/wait_closed() raise. self.writer is
                # already detached above, so swallowing this can't leak a
                # stale reference - it just lets the caller's startup retry
                # loop continue instead of aborting on a teardown error.
                _LOGGER.debug("Writer cleanup after failed connection: %s", err)
        self._reset_sync_state()
        self._pending_command_response = None
        self._consecutive_sync_failures = 0
        _LOGGER.info("Disconnected from Matrio device")

    async def _send_and_await_response(self, packet: bytes, timeout: float = 2.0) -> bool:
        """
        Write a command packet and wait for its ack, without racing the
        persistent _reader_loop for reads.

        Serialized by _command_lock so only one command's write-then-await
        cycle is ever in flight at a time - a rapid burst of commands (e.g.
        turn_on immediately followed by select_source/volume_set) is
        processed one full round-trip at a time instead of each racing its
        own reader.read() against _reader_loop's, which could otherwise
        steal or drop another command's ack. The response itself is
        delivered by _reader_loop into _pending_command_response.

        writer.drain() is separately bounded by COMMAND_WRITE_TIMEOUT (it's
        local socket buffering, not waiting on the device, so it should
        always be fast) so a wedged TCP send buffer can't hold
        _command_lock - and every other queued command/sync request behind
        it - indefinitely.

        Uses a locally-captured reference to the pending future (rather
        than re-reading self._pending_command_response after the await
        points below) so a concurrent connect()/disconnect() clearing that
        attribute can't turn this into an `await None` crash - worst case,
        a torn-down connection just means nothing ever resolves this
        command's own future, and it times out normally instead.
        """
        if not self.writer:
            return False

        async with self._command_lock:
            pending = asyncio.get_running_loop().create_future()
            self._pending_command_response = pending
            try:
                self.writer.write(packet)
                await asyncio.wait_for(self.writer.drain(), timeout=self.COMMAND_WRITE_TIMEOUT)
                response = await asyncio.wait_for(pending, timeout=timeout)
                return len(response) > 0
            except Exception as e:
                _LOGGER.debug("Command failed with exception: %s", e)
                return False
            finally:
                if self._pending_command_response is pending:
                    self._pending_command_response = None

    async def _send_input_command(self, zone_id: int, input_id: int) -> bool:
        """
        Send input command using the correct protocol discovered from capture analysis
        
        Args:
            zone_id: Zone ID (1-8)
            input_id: Input ID (1-8)
        """
        _LOGGER.debug("_send_input_command called: zone_id=%s, input_id=%s", zone_id, input_id)
        
        if not self.writer:
            _LOGGER.debug("No writer connection available")
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
        
        _LOGGER.debug("Sending packet to device")
        return await self._send_and_await_response(packet)

    async def _send_power_command(self, zone_id: int, power_on: bool) -> bool:
        """
        Send power command using the correct protocol discovered from mobile app analysis
        
        Args:
            zone_id: Zone ID (1-8)
            power_on: True for power ON, False for power OFF
        """
        if not self.writer:
            return False
        
        if zone_id < 1 or zone_id > 8:
            _LOGGER.warning(f"Invalid zone ID: {zone_id}. Must be 1-8")
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

            # Powering on from deep standby can take the amp 5-10s to wake,
            # vs. the ~2s a normal command ack takes - use a longer timeout
            # here so _command_lock isn't released (letting a queued
            # follow-on command's packet go out) until the amp has actually
            # finished waking or genuinely failed to respond.
            timeout = 10.0 if power_on else 2.0
            result = await self._send_and_await_response(packet, timeout=timeout)
            if result:
                _LOGGER.debug(f"Zone {zone_id} power {'ON' if power_on else 'OFF'} command sent successfully")
            else:
                _LOGGER.debug(f"Zone {zone_id} power {'ON' if power_on else 'OFF'} command failed - no response")
            return result

        except Exception as e:
            _LOGGER.error(f"Power command failed: {e}")
            return False
    
    async def _send_volume_command(self, zone_id: int, volume: int) -> bool:
        """
        Send volume command using the correct zone-specific protocol from packet capture analysis
        
        Args:
            zone_id: Zone ID (1-8)
            volume: Volume level (0-38)
        """
        if not self.writer:
            return False
        
        if zone_id < 1 or zone_id > 8:
            _LOGGER.warning(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        
        if volume < 0 or volume > 38:
            _LOGGER.warning(f"Invalid volume: {volume}. Must be 0-38")
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

            result = await self._send_and_await_response(packet)
            if result:
                _LOGGER.debug(f"Zone {zone_id} volume: {volume}")
            else:
                _LOGGER.debug(f"Zone {zone_id} volume command failed - no response")
            return result

        except Exception as e:
            _LOGGER.error(f"Volume command failed: {e}")
            return False
    
    async def _send_mute_command(self, zone_id: int, mute: bool) -> bool:
        """
        Send mute command using the correct zone-specific protocol from packet capture analysis
        
        Args:
            zone_id: Zone ID (1-8)
            mute: True for mute ON, False for mute OFF
        """
        if not self.writer:
            return False
        
        if zone_id < 1 or zone_id > 8:
            _LOGGER.warning(f"Invalid zone ID: {zone_id}. Must be 1-8")
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

            result = await self._send_and_await_response(packet)
            if result:
                _LOGGER.debug(f"Zone {zone_id} mute: {'ON' if mute else 'OFF'}")
            else:
                _LOGGER.debug(f"Zone {zone_id} mute command failed - no response")
            return result

        except Exception as e:
            _LOGGER.error(f"Mute command failed: {e}")
            return False
    
    async def _send_name_command(self, command_type: int, item_id: int, name: str) -> bool:
        """
        Send zone or input name command
        
        Args:
            command_type: 0x01 for zone names, 0x02 for input names
            item_id: Zone or input ID (1-8)
            name: New name to set
        """
        if not self.writer:
            return False
        
        # Convert name to bytes
        name_bytes = name.encode('utf-8')
        name_length = len(name_bytes)
        
        # Packet format: 82 13 [TYPE] [ID] [LENGTH] [NAME] cc
        packet = bytes([0x82, 0x13, command_type, item_id, name_length] + list(name_bytes) + [0xcc])
        
        try:
            self.writer.write(packet)
            await self.writer.drain()
            # Wait for response
            response = await asyncio.wait_for(self.reader.read(1024), timeout=2.0)
            return len(response) > 0
        except Exception as e:
            _LOGGER.error(f"Name command failed: {e}")
            return False
    
    
    # Zone and Input Naming
    async def set_zone_name(self, zone_id: int, name: str) -> bool:
        """Set zone name (zones 1-8)"""
        if zone_id < 1 or zone_id > 8:
            _LOGGER.warning(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        result = await self._send_name_command(0x01, zone_id, name)
        if result:
            _LOGGER.debug(f"Zone {zone_id} renamed to: {name}")
        return result
    
    async def set_input_name(self, input_id: int, name: str) -> bool:
        """Set input name (inputs 1-8)"""
        if input_id < 1 or input_id > 8:
            _LOGGER.warning(f"Invalid input ID: {input_id}. Must be 1-8")
            return False
        result = await self._send_name_command(0x02, input_id, name)
        if result:
            _LOGGER.debug(f"Input {input_id} renamed to: {name}")
        return result
    
    # Individual Zone Controls
    async def set_zone_power(self, zone_id: int, power: bool) -> bool:
        """Turn individual zone on/off using the correct protocol"""
        return await self._send_power_command(zone_id, power)
    
    async def set_volume(self, zone_id: int, volume: int) -> bool:
        """Set volume for individual zone (0-38) using correct protocol"""
        if zone_id < 1 or zone_id > 8:
            _LOGGER.warning(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        
        # Volume range matches mobile app: 0-38
        if volume < 0 or volume > 38:
            _LOGGER.warning(f"Invalid volume: {volume}. Must be 0-38")
            return False
        
        return await self._send_volume_command(zone_id, volume)
    
    async def set_mute(self, zone_id: int, mute: bool) -> bool:
        """Mute/unmute individual zone using correct protocol"""
        if zone_id < 1 or zone_id > 8:
            _LOGGER.warning(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        
        return await self._send_mute_command(zone_id, mute)
    
    
    async def set_input(self, zone_id: int, input_id: int) -> bool:
        """Set input for individual zone (1-8)"""
        _LOGGER.debug("set_input called: zone_id=%s, input_id=%s", zone_id, input_id)
        
        if input_id < 1 or input_id > 8:
            _LOGGER.debug("Invalid input ID: %s. Must be 1-8", input_id)
            return False
        
        input_name = self.inputs.get(input_id, f"Input {input_id}")
        _LOGGER.debug("Attempting to set Zone %s to %s (ID: %s)", zone_id, input_name, input_id)
        
        result = await self._send_input_command(zone_id, input_id)
        
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
    
    async def _send_protocol_command(self, command: int) -> bytes | None:
        """
        Send a protocol command using the Matrio Control protocol format
        Based on packet capture analysis of Matrio Control app
        Format: header (4 bytes) + length (4 bytes) + data (12 bytes) + payload
        """
        if not self.writer:
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
                _LOGGER.warning(f"Unknown command: 0x{command:02x}")
                return None
            
            # Construct packet
            header = bytes.fromhex("18961820")
            packet = header + length.to_bytes(4, 'little') + data + payload
            
            self.writer.write(packet)
            await self.writer.drain()
            
            # For the sequence, we need to handle the protocol flow:
            # 1. Send 0x0a command
            # 2. Receive ACK
            # 3. Receive 0x0c response
            # 4. Send ACK
            # 5. Receive ALLNAMES (0x15) packet
            
            if command == 0x0a:
                # Send first command and wait for responses
                
                # Wait for ACK
                ack = await asyncio.wait_for(self.reader.read(1024), timeout=5.0)
                if len(ack) == 0:
                    _LOGGER.debug("Received ACK")
                
                # Wait for 0x0c response (this is actually the ALLNAMES packet)
                response = await asyncio.wait_for(self.reader.read(1024), timeout=5.0)
                if len(response) > 0:
                    _LOGGER.debug(f"Received response: {len(response)} bytes")
                    # This is the ALLNAMES packet, return it directly
                    return response
                
                return None
            else:
                # For other commands, just send and receive
                response = await asyncio.wait_for(self.reader.read(1024), timeout=2.0)
                return response if len(response) > 0 else None
                
        except Exception as e:
            _LOGGER.error(f"Protocol command failed: {e}")
            return None
    
    async def check_heartbeat(self) -> bool:
        """
        Check if the device is responding (heartbeat check)
        Returns True if device responds, False otherwise
        """
        if not self.writer:
            return False
        
        try:
            # Try the first command to check if device is alive
            response = await self._send_protocol_command(0x0a)
            return response is not None and len(response) > 0
        except Exception:
            return False
    
    async def query_device_info(self) -> Dict[str, str]:
        """
        Query device information from the Matrio-compatible device using the correct protocol
        Based on the logs, the device reports deviceInfo with MAC, firmware, etc.
        """
        if not self.writer:
            raise ConnectionError("Not connected to device")
        
        # Send the first command (0x0a) to trigger the protocol sequence that returns ALLNAMES
        response = await self._send_protocol_command(0x0a)
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
    
    async def query_all_names(self) -> Dict[str, str]:
        """
        Query all zone and input names from the device
        Based on the logs, the device sends ALLNAMES packets with zone and input names
        """
        if not self.writer:
            raise ConnectionError("Not connected to device")
        
        # Send the first command (0x0a) to trigger the protocol sequence that returns ALLNAMES
        response = await self._send_protocol_command(0x0a)
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
    
    async def _send_audio_control_command(self, zone_id: int, control_type: str, value: int) -> bool:
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
        if not self.writer:
            _LOGGER.warning("Not connected to device")
            return False
        
        if zone_id < 1 or zone_id > 8:
            _LOGGER.warning(f"Invalid zone ID: {zone_id}. Must be 1-8")
            return False
        
        # Map control types to command codes
        command_codes = {
            'balance': 0x05,  # 8205 from capture analysis
            'bass': 0x03,     # 8203 - swapped with treble
            'treble': 0x02    # 8202 - swapped with bass
        }
        
        if control_type not in command_codes:
            _LOGGER.warning(f"Invalid control type: {control_type}. Must be 'balance', 'bass', or 'treble'")
            return False
        
        command_code = command_codes[control_type]
        
        # Convert value to hex based on control type
        if control_type == 'balance':
            # Balance: -100 to +100 -> 0x01 to 0x3d (1 to 61)
            # Based on MatrioLog13.txt: 0x01=min left, 0x1f=middle, 0x3d=max right
            if value < -100 or value > 100:
                _LOGGER.warning(f"Invalid balance value: {value}. Must be -100 to +100")
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
                _LOGGER.warning(f"Invalid {control_type} value: {value}. Must be -12 to +12")
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
            result = await self._send_and_await_response(packet)
            if result:
                _LOGGER.debug(f"Sent {control_type} command for zone {zone_id}: value={value} (0x{hex_value:02x})")
                return True
            else:
                _LOGGER.debug(f"{control_type} command for zone {zone_id} failed - no response")
                return False
                
        except Exception as e:
            _LOGGER.debug(f"Failed to send {control_type} command: {e}")
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
    
    async def set_balance(self, zone_id: int, balance: int) -> bool:
        """
        Set balance for individual zone
        
        Args:
            zone_id: Zone ID (1-8)
            balance: Balance value (-100 to +100, where -100 is full left, +100 is full right, 0 is center)
        
        Returns:
            bool: True if command sent successfully
        """
        return await self._send_audio_control_command(zone_id, 'balance', balance)
    
    async def set_bass(self, zone_id: int, bass: int) -> bool:
        """
        Set bass level for individual zone
        
        Args:
            zone_id: Zone ID (1-8)
            bass: Bass level (-12 to +12, where -12 is minimum, +12 is maximum, 0 is neutral)
        
        Returns:
            bool: True if command sent successfully
        """
        return await self._send_audio_control_command(zone_id, 'bass', bass)
    
    async def set_treble(self, zone_id: int, treble: int) -> bool:
        """
        Set treble level for individual zone
        
        Args:
            zone_id: Zone ID (1-8)
            treble: Treble level (-12 to +12, where -12 is minimum, +12 is maximum, 0 is neutral)
        
        Returns:
            bool: True if command sent successfully
        """
        return await self._send_audio_control_command(zone_id, 'treble', treble)

    async def request_zone_sync(self) -> bool:
        """
        Actively request a fresh full zone-status resync from the device,
        and wait for that specific round-trip to complete.

        The write goes out here, but the response arrives asynchronously on
        the persistent _reader_loop (which is the sole reader of
        self.reader) and is decoded there, merged into self.zones, and
        delivered via state_callback exactly like a broadcast - this call
        just awaits the outcome _reader_loop reports back via
        _sync_result_future (see _finish_sync / _process_sync_chunk).

        Held under _command_lock for the whole round-trip (not just the
        write) so this can never overlap with an in-flight zone command -
        without that, a sync response and a command's ack could each get
        delivered to the wrong waiter in _reader_loop.

        Uses a locally-captured reference to the result future (rather than
        re-reading self._sync_result_future after the await points below)
        so a concurrent connect()/disconnect() clearing that attribute
        can't turn this into an `await None` crash.

        Returns:
            bool: True if the device responded with a valid sync packet.
        """
        if not self.writer:
            _LOGGER.debug("request_zone_sync: not connected, skipping")
            return False

        async with self._command_lock:
            if self._awaiting_sync:
                _LOGGER.debug("request_zone_sync: a sync request is already in flight, skipping")
                return False

            self._awaiting_sync = True
            self._sync_buffer = b""
            self._sync_chunk_count = 0
            self._sync_started_monotonic = time.monotonic()
            sync_future = asyncio.get_running_loop().create_future()
            self._sync_result_future = sync_future

            try:
                self.writer.write(self.HNG_SYNC_REQUEST_PACKET)
                await asyncio.wait_for(self.writer.drain(), timeout=self.COMMAND_WRITE_TIMEOUT)
                _LOGGER.debug("Zone sync request sent")
            except Exception as e:
                _LOGGER.error(f"Failed to send zone sync request: {e}")
                self._reset_sync_state()
                return False

            try:
                # _reader_loop resolves this via _finish_sync/_process_sync_chunk
                # once the round-trip completes or is abandoned (bounded by
                # SYNC_ABANDON_TIMEOUT). The extra margin here is only a
                # defensive fallback in case _reader_loop itself stops
                # ticking - it is not the primary timeout mechanism.
                return await asyncio.wait_for(sync_future, timeout=self.SYNC_ABANDON_TIMEOUT + 2.0)
            except asyncio.TimeoutError:
                _LOGGER.warning("request_zone_sync: no result from reader loop past the abandon timeout")
                self._reset_sync_state()
                return False

    async def trigger_hng_sync(self) -> Dict[str, Any] | None:
        """
        Trigger HNG sync packet and decode all zone states
        
        Returns:
            Dict containing decoded zone states or None if failed
        """
        if not self.writer:
            _LOGGER.error("Not connected to device")
            return None
        
        try:
            _LOGGER.debug("Triggering HNG sync...")
            
            # Use the existing protocol command that we know works
            self.writer.write(self.HNG_SYNC_REQUEST_PACKET)
            await self.writer.drain()
            
            # Wait for HNG_SYNC_COMMAND response
            sync_response = await asyncio.wait_for(self.reader.read(1024), timeout=5.0)
            if len(sync_response) == 0:
                _LOGGER.debug("No sync response received")
                return None
            
            _LOGGER.debug("Received sync response: %d bytes", len(sync_response))
            
            # Wait for ALLNAMES response
            allnames_response = await asyncio.wait_for(self.reader.read(1024), timeout=5.0)
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
                # Expected/routine when called against a partial buffer
                # while an active sync response is still arriving in
                # multiple chunks (see request_zone_sync/_process_sync_chunk)
                # - callers that need to know extraction ultimately failed
                # after gathering all expected data log their own warning.
                _LOGGER.debug("HNG sync signature not found in packet data (yet)")
                return None
            
            # Extract the HNG sync packet - try both 68-byte and 96-byte sizes
            hng_start = hng_pos
            
            # A framed 68-byte response can be followed by another coalesced
            # packet, so identify it by its terminator before using total
            # buffered length to select the 96-byte form.
            hng_end_68 = hng_start + self.SYNC_PACKET_SHORT_BYTES
            if (
                hng_end_68 <= len(data)
                and data[hng_end_68 - len(self.SYNC_PACKET_TERMINATOR):hng_end_68]
                == self.SYNC_PACKET_TERMINATOR
            ):
                hng_packet = data[hng_start:hng_end_68]
                _LOGGER.debug("Extracted 68-byte HNG sync packet: %d bytes", len(hng_packet))
                return hng_packet.hex()

            hng_end_96 = hng_start + self.SYNC_PACKET_COMPLETE_BYTES
            if hng_end_96 <= len(data):
                hng_packet = data[hng_start:hng_end_96]
                _LOGGER.debug("Extracted 96-byte HNG sync packet: %d bytes", len(hng_packet))
                return hng_packet.hex()

            # Preserve the generic extractor's existing short-packet fallback.
            # The active sync path reaches this only after its completeness
            # check has verified the terminator, so fragmented long packets
            # are still held for more data there.
            if hng_end_68 <= len(data):
                hng_packet = data[hng_start:hng_end_68]
                _LOGGER.debug("Extracted 68-byte HNG sync packet: %d bytes", len(hng_packet))
                return hng_packet.hex()
            
            # Also routine while more chunks of an active sync response are
            # still arriving - see comment above.
            _LOGGER.debug("HNG sync packet extends beyond received data (yet)")
            return None
            
        except Exception as e:
            _LOGGER.error("Failed to extract HNG sync packet: %s", e)
            return None
    
    async def get_zone_states(self, input_mappings: Dict[int, str]) -> Dict[str, Any]:
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
        
        hng_result = await self.trigger_hng_sync()
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
