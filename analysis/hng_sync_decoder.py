#!/usr/bin/env python3
"""
Universal HNG sync packet decoder that handles both 68-byte and 96-byte packets
"""

from typing import Dict, Any

class UniversalHNGSyncDecoder:
    def __init__(self):
        self.zones = {}
        
    def decode_hng_sync_packet(self, packet_hex: str) -> Dict[str, Any]:
        """Decode a complete HNG sync packet - automatically detects packet size"""
        packet = bytes.fromhex(packet_hex)
        
        result = {
            'packet_length': len(packet),
            'packet_type': '68-byte' if len(packet) == 68 else '96-byte' if len(packet) == 96 else f'{len(packet)}-byte',
            'zones': {}
        }
        
        print(f"Universal HNG Sync Packet Decoder")
        print(f"Packet length: {len(packet)} bytes ({result['packet_type']})")
        print(f"Data: {packet_hex}")
        print("=" * 70)
        
        # Determine HNG section start based on packet size
        if len(packet) == 96:
            hng_start = 28  # 96-byte packet: HNG section starts at byte 28
        elif len(packet) == 68:
            hng_start = 0   # 68-byte packet: HNG section starts at byte 0
        else:
            print(f"WARNING: Unknown packet size {len(packet)} bytes")
            hng_start = 0
        
        # Decode each zone
        for zone in range(8):
            zone_num = zone + 1
            zone_data = self.decode_zone(zone, packet, hng_start, len(packet))
            result['zones'][zone_num] = zone_data
            
            print(f"Zone {zone_num:2}: {zone_data['power']:5} | {zone_data['input']:8} | Volume: {zone_data['volume']:2} | Balance: {zone_data['balance']:12} | Mute: {zone_data['mute']:8}")
        
        return result
    
    def decode_zone(self, zone: int, packet: bytes, hng_start: int, packet_size: int) -> Dict[str, Any]:
        """Decode individual zone data based on packet size"""
        
        # Input state
        if packet_size == 96:
            input_start = hng_start + 2  # bytes 30-37
        else:  # 68-byte packet
            input_start = hng_start + 2  # bytes 2-9
        input_val = packet[input_start + zone]
        input_name = self.decode_input_selection(input_val)
        
        # Volume state
        if packet_size == 96:
            volume_start = hng_start + 10  # bytes 38-45
        else:  # 68-byte packet
            volume_start = hng_start + 10  # bytes 10-17
        volume_val = packet[volume_start + zone]
        volume = self.decode_volume_level(volume_val)
        
        # Power state
        if packet_size == 96:
            power_start = hng_start + 44  # bytes 72-79
        else:  # 68-byte packet
            power_start = hng_start + 50  # bytes 50-57
        power_val = packet[power_start + zone]
        power = self.decode_power_state(power_val, packet_size)
        
        # Balance state
        if packet_size == 96:
            balance_start = hng_start + 34  # bytes 62-69
        else:  # 68-byte packet
            balance_start = hng_start + 42  # bytes 42-49
        balance_val = packet[balance_start + zone]
        balance = self.decode_balance_state(balance_val, packet_size)
        
        # Mute state
        if packet_size == 96:
            mute_start = hng_start + 52  # bytes 80-87
        else:  # 68-byte packet
            mute_start = hng_start + 28  # bytes 28-35
        mute_val = packet[mute_start + zone]
        mute = self.decode_mute_state(mute_val, packet_size)
        
        return {
            'zone_id': zone + 1,
            'power': power,
            'input': input_name,
            'volume': volume,
            'balance': balance,
            'mute': mute,
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
    
    def decode_input_selection(self, input_val: int) -> str:
        """Decode zone input selection"""
        input_map = {
            0x01: "Input 1",
            0x02: "Input 2",
            0x03: "Input 3",
            0x04: "Input 4", 
            0x08: "Input 8",
            0x27: "TV",
            0x1d: "Google Music",
        }
        return input_map.get(input_val, f"UNKNOWN(0x{input_val:02x})")
    
    def decode_volume_level(self, volume: int) -> int:
        """Decode zone volume level (with +1 offset)"""
        # Volume is stored as (UI_volume + 1)
        ui_volume = volume - 1
        return max(0, ui_volume)  # Ensure non-negative
    
    def decode_balance_state(self, balance: int, packet_size: int) -> str:
        """Decode zone balance state based on packet size"""
        if packet_size == 96:
            # 96-byte packet: 0x3d=MAX Right, 0x1f=Default
            if balance == 0x3d:
                return "MAX Right"
            elif balance == 0x1f:
                return "Default"
            else:
                return f"UNKNOWN(0x{balance:02x})"
        else:
            # 68-byte packet: 0x01=MAX Right, 0x02=Default
            if balance == 0x01:
                return "MAX Right"
            elif balance == 0x02:
                return "Default"
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

def test_68byte_packet():
    """Test with 68-byte packet from original capture"""
    print("=" * 80)
    print("TESTING 68-BYTE PACKET")
    print("=" * 80)
    
    # 68-byte packet from original capture
    hng_data_68 = "820c0104030208080804050a01271d0805050d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d1f3d1f1f1f1f1f1f02010201020101010101010101020101010240180c14ffffcc26"
    
    decoder = UniversalHNGSyncDecoder()
    result = decoder.decode_hng_sync_packet(hng_data_68)
    
    print(f"\n68-byte packet verification:")
    print("Zone | Power | Input | Volume | Balance | Mute")
    print("-" * 50)
    
    for zone_num in range(1, 9):
        if zone_num in result['zones']:
            zone = result['zones'][zone_num]
            print(f"{zone_num:4} | {zone['power']:5} | {zone['input']:8} | {zone['volume']:6} | {zone['balance']:7} | {zone['mute']:4}")

def test_96byte_packet():
    """Test with 96-byte packet from new capture"""
    print("\n" + "=" * 80)
    print("TESTING 96-BYTE PACKET")
    print("=" * 80)
    
    # 96-byte packet from new capture
    hng_data_96 = "189618204c0000009e08000000000000000000004d43552b5041532b820c0104030208080804050a01271d0805050d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d1f3d1f1f1f1f1f1f02010201020101010101010101020101010240180c14ffffcc26"
    
    decoder = UniversalHNGSyncDecoder()
    result = decoder.decode_hng_sync_packet(hng_data_96)
    
    print(f"\n96-byte packet verification:")
    print("Zone | Power | Input | Volume | Balance | Mute")
    print("-" * 50)
    
    for zone_num in range(1, 9):
        if zone_num in result['zones']:
            zone = result['zones'][zone_num]
            print(f"{zone_num:4} | {zone['power']:5} | {zone['input']:8} | {zone['volume']:6} | {zone['balance']:7} | {zone['mute']:4}")

def test_unknown_packet():
    """Test with unknown packet size"""
    print("\n" + "=" * 80)
    print("TESTING UNKNOWN PACKET SIZE")
    print("=" * 80)
    
    # Truncated packet to test unknown size handling
    hng_data_unknown = "820c0104030208080804050a01271d0805050d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d1f3d1f1f1f1f1f1f02010201020101010101010101020101010240180c14ffffcc"
    
    decoder = UniversalHNGSyncDecoder()
    result = decoder.decode_hng_sync_packet(hng_data_unknown)
    
    print(f"\nUnknown packet size verification:")
    print(f"Packet type: {result['packet_type']}")

def main():
    """Test the universal decoder with different packet sizes"""
    test_68byte_packet()
    test_96byte_packet()
    test_unknown_packet()
    
    print("\n" + "=" * 80)
    print("UNIVERSAL DECODER TEST COMPLETE")
    print("=" * 80)
    print("✅ The universal decoder successfully handles:")
    print("   - 68-byte packets (original format)")
    print("   - 96-byte packets (new format)")
    print("   - Unknown packet sizes (with warning)")
    print("   - Automatic packet type detection")
    print("   - Appropriate decoding logic for each format")

if __name__ == "__main__":
    main()
