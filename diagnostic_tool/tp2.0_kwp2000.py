import can
import time
import sys
import os
import threading
import queue
import msvcrt

# --- KONFIGURATION ---
CAN_INTERFACE = 'pcan'
CAN_CHANNEL   = 'PCAN_USBBUS1'
CAN_BITRATE   = 500000 
RX_ID_TP20    = 0x300

os.system("") # ANSI Farben aktivieren für Windows

class TP20DiagnosticTool:
    def __init__(self, ecu_id, channel=CAN_CHANNEL, bitrate=CAN_BITRATE):
        self.ecu_id = ecu_id
        try:
            self.bus = can.Bus(interface=CAN_INTERFACE, channel=channel, bitrate=bitrate, state=can.bus.BusState.ACTIVE)
        except Exception as e:
            print(f"[!] PCAN Fehler: {e}")
            sys.exit(1)
            
        self.tx_id = 0
        self.tx_seq = 0
        self.rx_queue = queue.Queue()
        
        self.running = True
        self.current_input = ""
        self.prompt_text = ""
        self.show_can_trace = False
        
        self.listener_thread = threading.Thread(target=self._can_listener, daemon=True)
        self.listener_thread.start()

    def set_prompt(self, text):
        self.prompt_text = text
        sys.stdout.write(f"\r\033[K{self.prompt_text}{self.current_input}")
        sys.stdout.flush()

    def log_info(self, prefix, text, data_hex=""):
        line = f"[{prefix}] {text}"
        if data_hex:
            line += f" | {data_hex}"
        sys.stdout.write(f"\r\033[K{line}\n")
        sys.stdout.write(f"{self.prompt_text}{self.current_input}")
        sys.stdout.flush()

    def send_pcan(self, msg_id, data, desc=""):
        msg = can.Message(arbitration_id=msg_id, data=data, is_extended_id=False)
        self.bus.send(msg)
        if self.show_can_trace:
            self.log_info("TX", f"ID: {hex(msg_id):<5} {desc:<12}", bytes(data).hex(' ').upper())

    def _can_listener(self):
        while self.running:
            msg = self.bus.recv(timeout=0.1)
            if not msg: continue
            
            valid_ids = [0x200 + self.ecu_id, RX_ID_TP20]
            if msg.arbitration_id not in valid_ids:
                continue 

            if msg.arbitration_id == RX_ID_TP20 and msg.data[0] == 0xA3:
                self.send_pcan(self.tx_id, [0xA1, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF], "(AUTO-PONG)")
                continue 
            
            if self.show_can_trace:
                self.log_info("RX", f"ID: {hex(msg.arbitration_id):<5}              ", bytes(msg.data).hex(' ').upper())

            self.rx_queue.put(msg)

    def wait_for_frame(self, target_id, timeout=1.5):
        start = time.time()
        while time.time() - start < timeout:
            try:
                msg = self.rx_queue.get(timeout=0.1)
                if msg.arbitration_id == target_id:
                    return msg
            except queue.Empty:
                pass
        return None

    def setup_tp20(self):
        self.log_info("SYS", f"Verbinde mit ECU {hex(self.ecu_id)}...")
        self.send_pcan(0x200, [self.ecu_id, 0xC0, 0x00, 0x10, 0x00, 0x03, 0x01], "(CH SETUP)")
        
        resp = self.wait_for_frame(0x200 + self.ecu_id)
        if resp and resp.data[1] == 0xD0:
            self.tx_id = resp.data[4] + (resp.data[5] << 8)
            self.send_pcan(self.tx_id, [0xA0, 0x0F, 0x8A, 0xFF, 0x32, 0xFF], "(PARAMS)")
            
            a1_resp = self.wait_for_frame(RX_ID_TP20)
            if a1_resp and a1_resp.data[0] == 0xA1:
                self.tx_seq = 0
                self.log_info("SYS", "Kanal erfolgreich geöffnet!")
                return True
        return False

    def execute_kwp(self, service, params=[], quiet=False):
        while not self.rx_queue.empty(): self.rx_queue.get() 

        payload = [service] + params
        header = [0x10 | (self.tx_seq % 16), 0x00, len(payload)]
        self.send_pcan(self.tx_id, header + payload, f"(KWP {hex(service)})")

        ack = self.wait_for_frame(RX_ID_TP20)
        if not ack or (ack.data[0] & 0xF0) != 0xB0:
            return None
        
        self.tx_seq = ack.data[0] & 0x0F

        data_buffer = bytearray()
        start_data = time.time()
        
        while time.time() - start_data < 4.0: 
            frame = self.wait_for_frame(RX_ID_TP20)
            if not frame: continue

            pci = frame.data[0] & 0xF0
            rx_seq = frame.data[0] & 0x0F

            if pci in (0x00, 0x10, 0x20):
                if len(data_buffer) == 0:
                    if len(frame.data) > 3: data_buffer.extend(frame.data[3:])
                else:
                    if len(frame.data) > 1: data_buffer.extend(frame.data[1:])
                
                self.send_pcan(self.tx_id, [0xB0 | ((rx_seq + 1) % 16)], "(ACK OUT)")

                if pci == 0x10 or pci == 0x00:
                    if len(data_buffer) >= 3 and data_buffer[0] == 0x7F:
                        nrc = data_buffer[2]
                        if nrc == 0x78: 
                            if self.show_can_trace and not quiet:
                                self.log_info("KWP", "NRC 0x78: Response Pending...")
                            data_buffer = bytearray() 
                            start_data = time.time()  
                            continue
                        else:
                            if not quiet:
                                self.log_info("KWP", f"NRC Fehler: {hex(nrc)} für Service {hex(data_buffer[1])}")
                            return None
                    return data_buffer
        return None

    def print_ecu_info(self):
        print("-" * 75)
        teilenummer = "Unbekannt"
        bauteil = "Unbekannt"
        codierung = "Unbekannt"
        wsc = "Unbekannt"
        
        # WICHTIG: Kurze Pause, damit die ECU nach dem Start der Diagnose-Session bereit ist!
        time.sleep(0.2)
        
        res_9b = self.execute_kwp(0x1A, [0x9B], quiet=True)
        if res_9b and len(res_9b) >= 2 and res_9b[0] == 0x5A and res_9b[1] == 0x9B:
            data = res_9b
            
            if len(data) >= 14:
                tn = "".join(chr(b) for b in data[2:14] if 32 <= b <= 126).strip()
                if tn: teilenummer = tn
            
            version = ""
            if len(data) >= 18:
                version = "".join(chr(b) for b in data[14:18] if 32 <= b <= 126).strip()
            
            if len(data) >= 22:
                coding_int = int.from_bytes(data[19:22], byteorder='big')
                codierung = f"{coding_int:07d}"
            
            # WSC / Betriebsnummer inklusive Importer
            if len(data) >= 28:
                imp_int = int.from_bytes(data[22:24], byteorder='big')
                wsc_int = int.from_bytes(data[26:28], byteorder='big')
                
                wsc_parts = []
                if imp_int != 0 and imp_int != 65535:
                    wsc_parts.append(f"Imp: {imp_int}")
                if wsc_int != 0 and wsc_int != 65535:
                    wsc_parts.append(f"WSC {wsc_int}")
                
                if wsc_parts:
                    wsc = " ".join(wsc_parts)
            
            if len(data) > 28:
                bauteil_str = "".join(chr(b) for b in data[28:] if 32 <= b <= 126).strip()
                bauteil = f"{bauteil_str} {version}".strip()
                
        print(f"   Steuergerät-Teilenummer: {teilenummer}")
        print(f"  Bauteil und/oder Version: {bauteil}")
        print(f"                 Codierung: {codierung}")
        print(f"            Betriebsnummer: {wsc}")
        print("-" * 75)

    def advanced_id(self):
        self.log_info("SYS", "Lese Erweiterte ID-Daten aus...")
        print("-" * 75)
        
        time.sleep(0.1) # KWP Delay
        res_86 = self.execute_kwp(0x1A, [0x86], quiet=True)
        if res_86 and res_86[0] == 0x5A:
            d86 = res_86[2:]
            print("\nErweiterte Identifikation")
            try:
                sn = "".join(chr(b) if 32 <= b <= 126 else '' for b in d86[1:15]).strip()
                ident = "".join(chr(b) if 32 <= b <= 126 else '' for b in d86[16:23]).strip()
                date = "".join(chr(b) if 32 <= b <= 126 else '' for b in d86[23:31]).strip()
                rev = "".join(chr(b) if 32 <= b <= 126 else '' for b in d86[31:34]).strip()
                pruef = "".join(chr(b) if 32 <= b <= 126 else '' for b in d86[39:43]).strip()
                herst = "".join(chr(b) if 32 <= b <= 126 else '' for b in d86[43:47]).strip()
                
                print(f"              Seriennummer: {sn}")
                print(f"            Identifikation: {ident}")
                print(f"                  Revision: {rev}")
                print(f"                     Datum: {date}")
                print(f"          Prüfstandsnummer: {pruef}")
                print(f"          Herstellernummer: {herst}")
            except Exception:
                pass

        time.sleep(0.2) # WICHTIG: Delay, da das Steuergerät Zeit zum Verarbeiten braucht
        res_9c = self.execute_kwp(0x1A, [0x9C], quiet=True)
        if res_9c and res_9c[0] == 0x5A:
            d9c = res_9c[2:]
            print("\nFlash Status")
            try:
                prog_status = format(d9c[0], '08b') if len(d9c) > 0 else "N/A"
                versuche = str(d9c[1]) if len(d9c) > 1 else "N/A"
                erfolgreich = str(d9c[2]) if len(d9c) > 2 else "N/A"
                voraus = format(d9c[3], '08b') if len(d9c) > 3 else "N/A"
                
                flash_tool = "Unbekannt"
                if len(d9c) >= 10:
                    flash_tool = f"{d9c[4]:05d} {int.from_bytes(d9c[5:7], byteorder='big'):03d} {int.from_bytes(d9c[7:10], byteorder='big'):05d}"
                
                flash_date = "Unbekannt"
                if len(d9c) > 10:
                    flash_date = "".join(chr(b) for b in d9c[10:] if 32 <= b <= 126).strip()
                
                print(f"  Programmierungs Versuche: {versuche}")
                print(f"     Erfolgreiche Versuche: {erfolgreich}")
                print(f"    Programmierungs Status: {prog_status}")
                print(f"           Voraussetzungen: {voraus}")
                print(f"         Flash Tool Nummer: {flash_tool}")
                print(f"               Flash Datum: {flash_date}")
            except Exception:
                pass
                
        time.sleep(0.1) # KWP Delay
        res_91 = self.execute_kwp(0x1A, [0x91], quiet=True)
        if res_91 and res_91[0] == 0x5A:
            hw = "".join(chr(b) if 32 <= b <= 126 else '' for b in res_91[2:]).strip()
            if hw and not hw[0].isalnum():
                hw = hw[1:]
            if hw:
                print("\nSonstiges")
                print(f"            Hardwarenummer: {hw}")

        print("-" * 75)

    def live_mwb(self, start_block):
        block = start_block
        self.set_prompt("") 
        
        anim_chars = "|/-\\"
        anim_idx = 0
        
        while True:
            anim = anim_chars[anim_idx % 4]
            anim_idx += 1
            
            res = self.execute_kwp(0x21, [block], quiet=True)
            if res and len(res) >= 2 and res[0] == 0x61:
                data_bytes = res[2:]
                parsed_str = ""
                for i in range(0, min(12, len(data_bytes)), 3):
                    if i + 2 < len(data_bytes):
                        typ, a, b = data_bytes[i], data_bytes[i+1], data_bytes[i+2]
                        parsed_str += f"{i//3 + 1}:[{typ:02X}]{a:02X} {b:02X} | "
                
                sys.stdout.write(f"\r\033[K[{anim}] [MWB {block:<3}] {parsed_str}[+/-] Block [Q] Exit")
            else:
                sys.stdout.write(f"\r\033[K[{anim}] [MWB {block:<3}] Lese Daten...{' '*20} [+/-] Block [Q] Exit")
            sys.stdout.flush()

            if msvcrt.kbhit():
                char = msvcrt.getch().upper()
                if char == b'+' and block < 255:
                    block += 1
                elif char == b'-' and block > 1:
                    block -= 1
                elif char == b'Q':
                    print() 
                    break
            time.sleep(0.05)

    def live_actuator_test(self):
        self.log_info("STELLGLIED", "Prüfe Routine-Verfügbarkeit...")
        chk = self.execute_kwp(0x31, [0xB8, 0x00, 0x00], quiet=True)
        if not chk or chk[0] != 0x71:
            self.log_info("ERR", "Stellglieddiagnose wird nicht unterstützt oder blockiert!")
            return

        self.log_info("STELLGLIED", "Verfügbar! Auto-Status ist aktiviert.")
        self.set_prompt("") 
        
        status_str = "Warte auf Start..."
        test_active = False
        
        anim_chars = "|/-\\"
        anim_idx = 0
        
        while True:
            anim = anim_chars[anim_idx % 4]
            anim_idx += 1
            
            if test_active:
                res = self.execute_kwp(0x31, [0xBA, 0x01, 0x02], quiet=True)
                if res and len(res) >= 4:
                    status_str = res[4:].hex(' ').upper()
                else:
                    status_str = "Beendet/Warte..."
                    test_active = False

            sys.stdout.write(f"\r\033[K[{anim}] [STATUS] {status_str:<25} | [1] Start | [3] Next | [Q] Exit")
            sys.stdout.flush()

            if msvcrt.kbhit():
                char = msvcrt.getch().upper()
                if char == b'1':
                    res_start = self.execute_kwp(0x31, [0xB8, 0x01, 0x02], quiet=True) 
                    if res_start:
                        test_active = True 
                        
                elif char == b'3':
                    if test_active:
                        self.execute_kwp(0x31, [0xBA, 0x01, 0x02], quiet=True) 
                        time.sleep(0.05)
                        res_next = self.execute_kwp(0x31, [0xB9, 0x01, 0x02], quiet=True) 
                        if not res_next:
                            test_active = False 
                            
                elif char == b'Q':
                    print() 
                    self.log_info("SYS", "Beende Stellglieddiagnose...")
                    self.execute_kwp(0x10, [0x81], quiet=True) 
                    time.sleep(0.1)
                    self.execute_kwp(0x10, [0x89], quiet=True) 
                    break
            
            time.sleep(0.1)

    def manage_dtcs(self):
        while True:
            cmd = self.get_input_async("\n[Fehler] [1] Lesen | [2] Löschen | [Q] Zurück: ").strip().upper()
            
            if cmd == '1':
                self.log_info("DTC", "Lese Fehlerspeicher aus...")
                res = self.execute_kwp(0x18, [0x02, 0xFF, 0x00], quiet=True)
                if not res: 
                    res = self.execute_kwp(0x18, [0x00, 0xFF, 0x00], quiet=True)
                
                if res and res[0] == 0x58:
                    num_dtcs = res[1] 
                    if num_dtcs == 0:
                        self.log_info("DTC", "Keine Fehler gespeichert! (System sauber)")
                    else:
                        self.log_info("DTC", f"{num_dtcs} Fehlercodes gefunden:")
                        for i in range(num_dtcs):
                            offset = 2 + (i * 3) 
                            if offset + 2 < len(res):
                                dtc_high = res[offset]
                                dtc_low = res[offset+1]
                                status = res[offset+2]
                                vag_code = (dtc_high << 8) | dtc_low
                                self.log_info("DTC", f" -> Code: {vag_code:05d} (Raw: {dtc_high:02X}{dtc_low:02X}) | Fehlerstatus: {status:02X}")
                else:
                    self.log_info("ERR", "Fehler beim Auslesen des Speichers.")
                    
            elif cmd == '2':
                self.log_info("DTC", "Sende Löschbefehl (14 FF 00)...")
                res = self.execute_kwp(0x14, [0xFF, 0x00], quiet=True)
                if res and res[0] == 0x54:
                    self.log_info("DTC", "Löschbefehl vom Steuergerät akzeptiert!")
                    self.log_info("SYS", "Hinweis: Permanente Hardwarefehler kommen nach dem Löschen sofort wieder.")
                else:
                    self.log_info("ERR", "Der Tacho hat den Löschbefehl abgelehnt.")
                    
            elif cmd == 'Q':
                break

    def shutdown(self):
        self.running = False
        time.sleep(0.2)
        self.bus.shutdown()

    def get_input_async(self, prompt):
        self.set_prompt(prompt)
        self.current_input = ""
        while True:
            if msvcrt.kbhit():
                char = msvcrt.getch()
                if char in (b'\r', b'\n'): 
                    sys.stdout.write('\n')
                    res = self.current_input
                    self.current_input = ""
                    return res
                elif char == b'\x08': 
                    if len(self.current_input) > 0:
                        self.current_input = self.current_input[:-1]
                        self.set_prompt(self.prompt_text)
                else:
                    try:
                        self.current_input += char.decode('utf-8')
                        self.set_prompt(self.prompt_text)
                    except UnicodeDecodeError:
                        pass
            time.sleep(0.01)

def main():
    print("\033[2J\033[H", end="") 
    print("="*60)
    print(" VAG TP 2.0 / KWP2000 DIAGNOSE ".center(60, "="))
    print("="*60)
    
    ecu_hex = input("ECU ID (Hex, z.B. 07 für Tacho): ")
    try:
        ecu_id = int(ecu_hex, 16)
    except ValueError:
        return

    tool = TP20DiagnosticTool(ecu_id)
    
    try:
        if tool.setup_tp20():
            tool.execute_kwp(0x10, [0x89], quiet=True) 
            
            # Die Pause nach dem Session-Wechsel ist am wichtigsten:
            time.sleep(0.3)
            
            tool.print_ecu_info() 
            
            while True:
                cmd = tool.get_input_async("\nHauptmenü -> [1] MWB | [2] Fehler | [3] Stellglied | [4] Erw. ID | [T] Trace | [Q] Exit: ").strip().upper()
                
                if cmd == '1':
                    block = tool.get_input_async("Start Messwerteblock (1-255): ")
                    if block.isdigit():
                        tool.live_mwb(int(block))
                            
                elif cmd == '2':
                    tool.manage_dtcs()
                            
                elif cmd == '3':
                    tool.live_actuator_test()

                elif cmd == '4':
                    tool.advanced_id()
                    
                elif cmd == 'T':
                    tool.show_can_trace = not tool.show_can_trace
                    tool.log_info("SYS", f"CAN-Trace ist jetzt {'AN' if tool.show_can_trace else 'AUS'}")
                    
                elif cmd == 'Q':
                    break
                    
                tool.send_pcan(tool.tx_id, [0xA3])
    finally:
        tool.set_prompt("Beende Verbindung...\n")
        if tool.tx_id != 0:
            tool.send_pcan(tool.tx_id, [0xA8])
        tool.shutdown()

if __name__ == "__main__":
    main()
