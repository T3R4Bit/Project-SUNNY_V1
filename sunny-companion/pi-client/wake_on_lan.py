"""Send a Wake-on-LAN magic packet to power on the desktop PC.

No dependency needed -- a magic packet is just 6 bytes of 0xFF followed
by the target MAC address repeated 16 times, sent as a UDP broadcast.
Requires the target machine's WoL to be enabled in BIOS/OS and the
device sending this to be on the same LAN/broadcast domain.
"""

from __future__ import annotations

import argparse
import socket

MAGIC_PACKET_PORT = 9


def build_magic_packet(mac_address: str) -> bytes:
    cleaned = mac_address.replace(":", "").replace("-", "").lower()
    if len(cleaned) != 12 or any(c not in "0123456789abcdef" for c in cleaned):
        raise ValueError(f"'{mac_address}' is not a valid MAC address")
    mac_bytes = bytes.fromhex(cleaned)
    return b"\xff" * 6 + mac_bytes * 16


def send_magic_packet(mac_address: str, broadcast_ip: str = "255.255.255.255") -> None:
    packet = build_magic_packet(mac_address)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast_ip, MAGIC_PACKET_PORT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mac_address", help="Target PC's MAC address, e.g. AA:BB:CC:DD:EE:FF")
    parser.add_argument(
        "--broadcast-ip",
        default="255.255.255.255",
        help="Broadcast address for the local network (default: 255.255.255.255)",
    )
    args = parser.parse_args()
    send_magic_packet(args.mac_address, args.broadcast_ip)
    print(f"Magic packet sent to {args.mac_address}")
