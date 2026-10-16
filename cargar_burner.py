#!/usr/bin/env python3
"""
Cargador de Burner Code para Phison PS3111-S11 en Linux.
Sube el cargador a la memoria SRAM volátil del SSD y activa el modo VUC (SATABURN).
Posteriormente, un reinicio suave (Warm Reboot) hacia Windows permite flashear la NAND
sin que la controladora pierda la energía de los 5V ni el código cargado en RAM.
"""

import sys
import os
import pathlib

def main():
    if len(sys.argv) < 3:
        print("Uso: sudo python3 cargar_burner.py /dev/sdX ruta/al/firmware.BIN")
        print("Ejemplo: sudo python3 cargar_burner.py /dev/sda firmware/SBFM01.2_08082018.BIN")
        sys.exit(1)

    dev_path = pathlib.Path(sys.argv[1])
    bin_path = pathlib.Path(sys.argv[2])

    if not dev_path.exists():
        print(f"Error: El dispositivo '{dev_path}' no existe.")
        sys.exit(1)

    if not bin_path.exists():
        print(f"Error: El archivo de firmware '{bin_path}' no existe.")
        sys.exit(1)

    # Intento de importación de psychite
    try:
        from phison_s11 import drive as s11_drive
        from phison_s11 import firmware as s11_firmware
    except ImportError:
        print("[!] La librería 'psychite' no está en el path del sistema.")
        print("    Instalando/clonando psychite localmente...")
        os.system("git clone https://github.com/trulycrisp/psychite.git /tmp/psychite && pip install -e /tmp/psychite")
        from phison_s11 import drive as s11_drive
        from phison_s11 import firmware as s11_firmware

    print(f"=== Cargando Burner en {dev_path} desde {bin_path.name} ===")

    raw = bin_path.read_bytes()
    fw = s11_firmware.Firmware.from_bytes(raw)
    burner = fw.burner_code

    with s11_drive.Drive(dev_path) as d:
        print(f"[*] Modo actual de la controladora: {d.mode}")
        if d.mode == s11_drive.Mode.BURNER:
            print("[+] El Burner ya está cargado y activo en la SRAM.")
        else:
            print("[*] Subiendo secciones IRAM a la controladora...")
            for sec in burner.iram_sections:
                d.vuc_program_pram(sec.burner_address, bytes(sec.code))
            print("[*] Ejecutando salto al Burner en RAM (VUC Jump)...")
            d.vuc_jump()
            if burner.sram_section_crypt:
                print("[*] Programando sección SRAM cifrada...")
                d.vuc_program_pram_icode(burner.sram_section_crypt)
            print("[*] Desbloqueando modo de ingeniería VUC...")
            d.vuc_unlock()

        ident = d.cmd_identify_device()
        print(f"[+] Estado resultante: {d.mode} | Modelo: {ident.model} | Firmware: {ident.firmware}")

        if d.mode == s11_drive.Mode.BURNER:
            print("\n" + "="*60)
            print(" ¡ÉXITO! Burner activo en memoria volátil.")
            print(" IMPORTANTE: NO APAGUES EL PC (cortaría la alimentación de la RAM).")
            print(" Realiza un reinicio suave (sudo reboot) hacia Windows para flashear.")
            print("="*60)

if __name__ == "__main__":
    main()
