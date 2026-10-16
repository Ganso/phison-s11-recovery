#!/usr/bin/env python3
"""
Patch script for Phison PS3111-S11 official firmware flasher (DLMC / fw_sbfm012.exe).

Enables flashing bricked drives using the hybrid Linux/Windows strategy:
1. Bypass the startup check that aborts if the drive is already running in Burner mode (SBBM).
2. Bypass the 10% progress check requiring factory Boot Code (SBRM).
3. Bypass the 15% ISPProgramPRAM call (which hangs under Windows 11 storahci driver
   because Windows blocks multi-sector SRAM transfers; the Burner is already active in SRAM).
4. Bypass the ATA Security query and invalid HandShake jump, proceeding directly to 30%
   (ReadSystemInfo, EraseAllBlock, PreFormat/InfoBlock rebuild, and NAND flash programming).
"""

import sys
import os
import hashlib

def patch_binary(input_path: str, output_path: str):
    if not os.path.exists(input_path):
        print(f"Error: input file '{input_path}' not found.")
        sys.exit(1)

    with open(input_path, "rb") as f:
        data = bytearray(f.read())

    print(f"Loaded '{input_path}' ({len(data)} bytes).")
    sha256_orig = hashlib.sha256(data).hexdigest()
    print(f"Original SHA-256: {sha256_orig}")

    # Patch 1: Bypass Burner check on startup
    # Target offset 0xfc6f: original is '8b 01 8b 10 6a 01 ff d2 ...' (calls error popup)
    # We replace 34 bytes with 'jmp 0xfae5' (e9 71 fe ff ff) + 29 NOPs
    expected_p1 = bytes.fromhex("8b018b106a01ffd2")
    if data[0xfc6f : 0xfc6f + 8] != expected_p1:
        print("Warning: bytes at 0xfc6f do not match expected signature for fw_sbfm012.")
    
    p1 = bytes.fromhex("e971feffff") + b"\x90" * 29
    assert len(p1) == 34
    data[0xfc6f : 0xfc6f + 34] = p1
    print("[+] Patch 1 applied: Bypass initial Burner mode block (0xfc6f -> jmp 0xfae5).")

    # Patch 2: Bypass Boot Code requirement at 10%
    # Target offset 0xfb5e: original is '6a 00 e8 7b 20 00 00 84 c0 ...' (checks SBR mode)
    # Replace 15 bytes with 'jmp 0xfc91' (e9 2e 01 00 00) + 10 NOPs
    p2 = bytes.fromhex("e92e010000") + b"\x90" * 10
    assert len(p2) == 15
    data[0xfb5e : 0xfb5e + 15] = p2
    print("[+] Patch 2 applied: Bypass 10% Boot Code requirement (0xfb5e -> jmp 0xfc91).")

    # Patch 3: Bypass ISPProgramPRAM (15% SRAM upload)
    # Target offset 0x14620 (entry point of ISPProgramPRAM)
    # In Windows 11 storahci, multi-sector transfers to SRAM fail with:
    # "ISPProgramPRAM failed on Section_0, Loop_..."
    # Since Burner is already loaded into SRAM from Linux, we return TRUE (1) immediately:
    # mov $1, %al; ret  -> b0 01 c3
    data[0x14620 : 0x14623] = bytes.fromhex("b001c3")
    print("[+] Patch 3 applied: ISPProgramPRAM returns TRUE immediately (0x14620 -> mov $1, %al; ret).")

    # Patch 4: Bypass ATA Security check and jump directly to 30% (ReadSystemInfo)
    # Target offset 0xfd2b: replace 5 bytes with 'jmp 0xfdbe' (e9 8e 00 00 00)
    # Avoids calling GetSecurityProtectStatus (0x2d80) and skips HandShake with uninitialized pointers
    p4 = bytes.fromhex("e98e000000")
    assert len(p4) == 5
    data[0xfd2b : 0xfd2b + 5] = p4
    print("[+] Patch 4 applied: Jump directly to 30% ReadSystemInfo & EraseAllBlock (0xfd2b -> jmp 0xfdbe).")

    with open(output_path, "wb") as f:
        f.write(data)

    sha256_patched = hashlib.sha256(data).hexdigest()
    print(f"\nSuccessfully wrote patched binary to '{output_path}'.")
    print(f"Patched SHA-256: {sha256_patched}")

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 patch_flasher.py <input_fw_sbfm012.exe> <output_fw_sbfm012_directo.exe>")
        sys.exit(1)

    patch_binary(sys.argv[1], sys.argv[2])

if __name__ == "__main__":
    main()
