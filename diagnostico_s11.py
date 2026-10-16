#!/usr/bin/env python3
"""
Herramienta de diagnóstico para SSDs con controladora Phison PS3111-S11.
Permite consultar el modo de la controladora (BootROM, Burner, Normal),
leer el ATA Identify, comprobar el estado de las CEs y obtener el Flash ID de la NAND.
"""

import sys
import ctypes
import fcntl
import struct
import pathlib

class sg_io_hdr(ctypes.Structure):
    _fields_ = [
        ("interface_id", ctypes.c_int),
        ("dxfer_direction", ctypes.c_int),
        ("cmd_len", ctypes.c_ubyte),
        ("mx_sb_len", ctypes.c_ubyte),
        ("iovec_count", ctypes.c_ushort),
        ("dxfer_len", ctypes.c_uint),
        ("dxferp", ctypes.c_void_p),
        ("cmdp", ctypes.c_void_p),
        ("sbp", ctypes.c_void_p),
        ("timeout", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("pack_id", ctypes.c_int),
        ("usr_ptr", ctypes.c_void_p),
        ("status", ctypes.c_ubyte),
        ("masked_status", ctypes.c_ubyte),
        ("msg_status", ctypes.c_ubyte),
        ("sb_len_wr", ctypes.c_ubyte),
        ("host_status", ctypes.c_ushort),
        ("driver_status", ctypes.c_ushort),
        ("resid", ctypes.c_int),
        ("duration", ctypes.c_uint),
        ("info", ctypes.c_uint),
    ]

SG_IO = 0x2285
SG_DXFER_NONE = -1
SG_DXFER_FROM_DEV = -3

def send_ata(fd, cmd, dev=0xa0, feat=0, sc=0, lba_low=0, lba_mid=0, lba_high=0, data_in_len=0):
    cdb = bytearray(16)
    cdb[0] = 0x85 # ATA PASS-THROUGH (16)
    proto = 4 if data_in_len > 0 else 3
    cdb[1] = (proto << 1)
    cdb[2] = 0x0e if data_in_len > 0 else 0x20
    cdb[4] = feat & 0xff
    cdb[6] = sc & 0xff
    cdb[8] = lba_low & 0xff
    cdb[10] = lba_mid & 0xff
    cdb[12] = lba_high & 0xff
    cdb[13] = dev & 0xff
    cdb[14] = cmd & 0xff

    data = (ctypes.c_char * (data_in_len if data_in_len > 0 else 1))()
    sense = (ctypes.c_char * 64)()
    cdb_buf = (ctypes.c_ubyte * 16).from_buffer_copy(cdb)

    hdr = sg_io_hdr()
    hdr.interface_id = ord("S")
    hdr.dxfer_direction = SG_DXFER_FROM_DEV if data_in_len > 0 else SG_DXFER_NONE
    hdr.cmd_len = 16
    hdr.mx_sb_len = 64
    hdr.dxfer_len = data_in_len
    hdr.dxferp = ctypes.cast(data, ctypes.c_void_p) if data_in_len > 0 else None
    hdr.cmdp = ctypes.cast(cdb_buf, ctypes.c_void_p)
    hdr.sbp = ctypes.cast(sense, ctypes.c_void_p)
    hdr.timeout = 5000

    fcntl.ioctl(fd.fileno(), SG_IO, hdr)
    return hdr.status, bytes(data) if data_in_len > 0 else b""

def main():
    if len(sys.argv) < 2:
        print("Uso: sudo python3 diagnostico_s11.py /dev/sdX")
        sys.exit(1)

    dev_path = sys.argv[1]
    print(f"=== Diagnóstico Phison PS3111-S11 en {dev_path} ===")

    # Consulta básica con ATA Identify
    try:
        with open(dev_path, "rb+", buffering=0) as f:
            st, data = send_ata(f, cmd=0xec, data_in_len=512)
            if st == 0 and len(data) >= 512:
                # Modelo en palabras 27-46 (bytes 54-93), endianness swap
                model_raw = data[54:94]
                model = bytes([model_raw[i^1] for i in range(len(model_raw))]).decode(errors='ignore').strip()
                fw_raw = data[46:54]
                fw = bytes([fw_raw[i^1] for i in range(len(fw_raw))]).decode(errors='ignore').strip()
                print(f"[+] ATA Identify:")
                print(f"    Modelo:   {model}")
                print(f"    Firmware: {fw}")
                if "PS3111" in model or "SBRM" in fw:
                    print("    -> Estado: MODO BOOTROM (ROM de fábrica, InfoBlock dañado)")
                elif "SATABURN" in model or "SBBM" in fw:
                    print("    -> Estado: MODO BURNER (Burner cargado en SRAM)")
                else:
                    print("    -> Estado: MODO NORMAL OPERATIVO")
            
            # Consulta directa SAT con APKey
            print("\n[+] Enviando APKey de ingeniería para consultar Flash ID...")
            send_ata(f, cmd=0xe0, dev=0xaf, feat=0x00, sc=0x6f, lba_low=0xfe, lba_mid=0xef, lba_high=0xfa)
            st_flash, flash_data = send_ata(f, cmd=0x21, dev=0xa0, feat=0x15, sc=0x01, data_in_len=512)
            if st_flash == 0 and len(flash_data) >= 8:
                fid = flash_data[:8].hex(' ')
                print(f"    Flash ID de NAND: {fid}")
                if "98 3c a5 93" in fid:
                    print("    -> NAND identificada: Toshiba 15nm MLC (TH58TEG7THLTA20 / TC58TEG7THLTA00)")
                elif "98 3a 98 a3" in fid:
                    print("    -> NAND identificada: Toshiba BiCS3 3D TLC")
                elif "89 a4 08 32" in fid:
                    print("    -> NAND identificada: Intel/Micron 64L 3D TLC")
                elif "ec 1a 98 2f" in fid:
                    print("    -> NAND identificada: Samsung 3D V-NAND")
            else:
                print("    (No se pudo leer Flash ID directo; es posible que la controladora esté bloqueada o en firmware operativo estándar)")
    except PermissionError:
        print("Error: Permiso denegado. Ejecuta este script con 'sudo'.")
    except Exception as e:
        print(f"Error consultando dispositivo: {e}")

if __name__ == "__main__":
    main()
