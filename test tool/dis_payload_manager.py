import can
import time
import logging
import re
import msvcrt

# --- Configuration ---
CAN_INTERFACE = 'pcan'
CAN_CHANNEL   = 'PCAN_USBBUS1'
CAN_BITRATE   = 500000

CAN_ID_TX = 0x490
CAN_ID_RX = 0x491

# Protocol Constants
OP_CLAIM     = 0x36
OP_RELEASE   = 0x32
OP_INIT      = 0x30
OP_WRITE     = 0xE0
OP_SOURCE    = 0xE2
OP_HIGHLIGHT = 0xE4

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


# LAYER 1: CAN BUS DRIVER

class MMITester:
    def __init__(self, channel=CAN_CHANNEL, interface=CAN_INTERFACE, bitrate=CAN_BITRATE):
        logger.info("=== AUDI A8 DIS - MMI SIMULATOR & TESTER ===")
        try:
            self.bus = can.Bus(interface=interface, channel=channel, bitrate=bitrate, state=can.bus.BusState.ACTIVE)
            logger.info(f"Connected to {interface}/{channel}. TX: 0x490 | RX: 0x491")
        except can.CanError as e:
            logger.error(f"Failed to open CAN bus: {e}")
            exit(1)
            
        self.tx_seq = 0
        self.rx_queue = []
        self.is_connected = False
        self.show_traffic = False

    def log_traffic(self, direction, hex_data, desc):
        if not self.show_traffic: return
        pad = " " * (25 - len(hex_data))
        print(f"{direction}: {hex_data}{pad} | {desc}")

    def send_raw(self, payload, desc):
        msg = can.Message(arbitration_id=CAN_ID_TX, data=payload, is_extended_id=False)
        self.bus.send(msg)
        self.log_traffic("MMI -> CLUS", bytes(payload).hex(' ').upper(), desc)

    def send_ack(self, seq_to_send):
        payload = [0xB0 | (seq_to_send % 16)]
        msg = can.Message(arbitration_id=CAN_ID_TX, data=payload, is_extended_id=False)
        self.bus.send(msg)
        self.log_traffic("MMI -> CLUS", bytes(payload).hex(' ').upper(), f"ACK OUT (Seq {seq_to_send % 16})")

    def _recv_filtered(self, timeout):
        start = time.time()
        while time.time() - start < timeout:
            rx = self.bus.recv(timeout=0.01)
            if not rx: continue
            
            if rx.arbitration_id == CAN_ID_RX:
                b0 = rx.data[0]
                if b0 == 0xA3:
                    self.log_traffic("CLUS -> MMI", "A3", "HEARTBEAT (PING IN)")
                    self.send_raw([0xA1, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF], "HEARTBEAT (PONG)")
                    continue
                return rx
        return None

    def active_sleep(self, duration):
        start = time.time()
        while time.time() - start < duration:
            self._recv_filtered(0.1)

    def send_data_and_wait_ack(self, payload_bytes, pkt_type=0x10):
        seq = self.tx_seq
        header = pkt_type | seq
        data = [header] + list(payload_bytes)
        
        msg = can.Message(arbitration_id=CAN_ID_TX, data=data, is_extended_id=False)
        self.bus.send(msg)
        
        type_str = "END" if pkt_type == 0x10 else "BODY"
        self.log_traffic("MMI -> CLUS", bytes(data).hex(' ').upper(), f"DATA {type_str} OUT (Seq {seq})")
        
        if pkt_type == 0x20:
            self.tx_seq = (seq + 1) % 16
            time.sleep(0.01)
            return True

        expected_ack = (seq + 1) % 16
        start_wait = time.time()
        while time.time() - start_wait < 1.0:
            rx = self._recv_filtered(0.05)
            if not rx: continue
            
            b0 = rx.data[0]
            high_nib = b0 & 0xF0
            rx_seq = b0 & 0x0F
            
            if high_nib == 0xB0:
                if rx_seq == expected_ack:
                    self.log_traffic("CLUS -> MMI", bytes(rx.data).hex(' ').upper(), f"ACK IN (Seq {rx_seq})")
                    self.tx_seq = expected_ack
                    return True
            elif high_nib in [0x10, 0x20]:
                self.rx_queue.append(rx)
                
        logger.warning(f"Timeout waiting for ACK on Seq {seq}")
        return False

    def wait_for_cluster_message(self, timeout=2.0):
        start_wait = time.time()
        payloads = []
        
        while time.time() - start_wait < timeout:
            if self.rx_queue:
                rx = self.rx_queue.pop(0)
            else:
                rx = self._recv_filtered(0.05)
                if not rx: continue
            
            b0 = rx.data[0]
            high_nib = b0 & 0xF0
            rx_seq = b0 & 0x0F
            
            if high_nib == 0x20:
                self.log_traffic("CLUS -> MMI", bytes(rx.data).hex(' ').upper(), f"DATA BODY IN (Seq {rx_seq})")
                payloads.extend(rx.data[1:])
                
            elif high_nib == 0x10:
                self.log_traffic("CLUS -> MMI", bytes(rx.data).hex(' ').upper(), f"DATA END IN (Seq {rx_seq})")
                payloads.extend(rx.data[1:])
                
                ack_to_send = (rx_seq + 1) % 16
                self.send_ack(ack_to_send)
                return payloads
                
        logger.warning("Timeout waiting for cluster data.")
        return None

    def send_message(self, payload_bytes):
        total_len = len(payload_bytes)
        offset = 0
        
        while offset < total_len:
            chunk = payload_bytes[offset:offset+7]
            offset += 7
            is_last = (offset >= total_len)
            
            pkt_type = 0x10 if is_last else 0x20
            success = self.send_data_and_wait_ack(chunk, pkt_type=pkt_type)
            
            if not success and is_last:
                return False
        return True

    def wait_for_confirmation(self, expected_zone: int):
        """Wait for 0x3B confirmation OR gracefully handle 0x09 error from cluster."""
        logger.info(f"Waiting for Cluster Confirmation (0x3B) for Zone {expected_zone:02X}...")
        payload = self.wait_for_cluster_message(timeout=2.0)

        if payload:
            if payload[0] == 0x3B and len(payload) > 2 and payload[2] == expected_zone:
                logger.info(f"✅ Confirmation received for Zone {expected_zone:02X}")
                return True

            elif payload[0] == 0x09:   # Cluster error (invalid highlight etc.)
                zone = payload[1] if len(payload) > 1 else 0
                extra = ' '.join(f'{b:02X}' for b in payload[2:]) if len(payload) > 2 else ''
                logger.error(f"❌ Cluster ERROR 0x09 (invalid param) Zone {zone:02X} | {extra}")
                return True   # continue anyway - keep-alive stays alive

        logger.warning(f"Failed to receive 0x3B confirmation for Zone {expected_zone:02X}")
        return False

    def perform_handshake(self):
        self.rx_queue.clear()
        self.tx_seq = 0

        logger.info("\n--- 1. OPEN REQUEST ---")
        self.send_raw([0xA0, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF], "OPEN REQUEST")
        
        while True:
            rx = self._recv_filtered(0.5)
            if rx and rx.data[0] == 0xA1:
                self.log_traffic("CLUS -> MMI", bytes(rx.data).hex(' ').upper(), "OPEN RESPONSE")
                break
                
        logger.info("\n--- 2. PING-PONG STABILIZATION (~1 sec) ---")
        self.active_sleep(1.0)

        logger.info("\n--- 3. PARAMETER EXCHANGE & FINAL BURST ---")
        logger.info("\n[Step 1 - Param 10]")
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x02]): self.wait_for_cluster_message() 
        logger.info("\n[Delay - Keep-alives processing...]")
        self.active_sleep(2.0)
        logger.info("\n[Step 2 - Param 11]")
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x02]): self.wait_for_cluster_message()
        logger.info("\n[Step 3 - Param 12]")
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x01]): self.wait_for_cluster_message()
        logger.info("\n[Step 4 - Param 13 & Final Burst]")
        if self.send_data_and_wait_ack([0x02, 0x01, 0x48]): self.wait_for_cluster_message()

        logger.info("\n======================================")
        logger.info("   HANDSHAKE COMPLETE - CHANNEL OPEN  ")
        logger.info("======================================")
        self.is_connected = True

    def run_keepalive_loop(self):
        logger.info("\nEntering background keep-alive loop. Press Ctrl+C to exit.")
        try:
            while True:
                self._recv_filtered(0.5)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.bus.shutdown()



# LAYER 2: PAYLOAD FORMATTER

class DISPayloadManager:
    def __init__(self, driver):
        self.driver = driver

    def init_zone(self, zone_id):
        logger.info(f"\n>> Initializing Zone {zone_id:02X}")
        self.driver.send_message([OP_INIT, 0x01, zone_id])
        resp = self.driver.wait_for_cluster_message(timeout=2.0)
        if resp and resp[0] == 0x31:
            logger.info(f"   ✅ Zone {zone_id:02X} Initialized successfully.")
            return True
        logger.warning(f"   ❌ Failed to initialize Zone {zone_id:02X}.")
        return False

    def init_all_zones(self):
        self.init_zone(0x01)
        time.sleep(0.1)
        self.init_zone(0x02)
        time.sleep(0.1)
        self.init_zone(0x03)
        time.sleep(0.1)

    def switch_source(self, source_id):
        logger.info(f"\n>> Switching Display Source to {source_id:02X}")
        return self.driver.send_message([OP_SOURCE, 0x01, source_id])

    def claim_zone(self, zone_id):
        return self.driver.send_message([OP_CLAIM, 0x01, zone_id])

    def release_zone(self, zone_id):
        success = self.driver.send_message([OP_RELEASE, 0x01, zone_id])
        if success:
            return self.driver.wait_for_confirmation(zone_id)
        return False

    def write_text(self, line_id, text_str):
        text_bytes = text_str.encode('ascii', errors='replace')
        length_byte = 0x02 + len(text_bytes)
        payload = [OP_WRITE, length_byte, line_id, 0x00] + list(text_bytes)
        return self.driver.send_message(payload)

    def set_highlight(self, p1: int, p2: int, p3: int | None = None):
        """Send E4 with 2 or 3 control bytes (supports AA BB CC)."""
        if p3 is None:
            logger.info(f"\n>> Setting Highlight: [{p1:02X} {p2:02X}]")
            payload = [OP_HIGHLIGHT, 0x02, p1, p2]
        else:
            logger.info(f"\n>> Setting Highlight: [{p1:02X} {p2:02X} {p3:02X}]")
            payload = [OP_HIGHLIGHT, 0x03, p1, p2, p3]
        return self.driver.send_message(payload)

    def write_smart_string(self, input_str: str):
        """Robust token parser - correctly handles E4 with 2 or 3 params + standalone E4."""
        if not input_str.strip():
            return

        tokens = re.split(r'\s+', input_str.strip().upper())
        i = 0

        top_line_update = None
        middle_line_updates = []
        highlight_params = None   # tuple of 2 or 3 ints
        source_param = None

        def is_tag(t: str) -> bool:
            return (len(t) == 2 and t[0] == '0' and t[1].isdigit()) or t in ('E4', 'E2')

        while i < len(tokens):
            token = tokens[i]
            if is_tag(token):
                tag = token
                i += 1

                if tag == 'E4':
                    # Collect 2 or 3 hex parameters after E4
                    params = []
                    while i < len(tokens) and len(params) < 3:
                        try:
                            params.append(int(tokens[i], 16))
                            i += 1
                        except ValueError:
                            break
                    if len(params) >= 2:
                        highlight_params = tuple(params)
                    continue

                elif tag == 'E2':
                    if i < len(tokens):
                        try:
                            source_param = int(tokens[i], 16)
                            i += 1
                        except ValueError:
                            pass
                    continue

                else:
                    # Normal line tag (01, 05-09, 00)
                    try:
                        line_hex = int(tag, 16)
                        # Collect text until next tag
                        text_parts = []
                        while i < len(tokens) and not is_tag(tokens[i]):
                            text_parts.append(tokens[i])
                            i += 1
                        text_clean = ' '.join(text_parts).strip()
                        if text_clean == '.':
                            text_clean = ""

                        if line_hex == 0x01:
                            top_line_update = (line_hex, text_clean)
                        elif line_hex in [0x00, 0x05, 0x06, 0x07, 0x08, 0x09]:
                            middle_line_updates.append((line_hex, text_clean))
                    except ValueError:
                        pass
                    continue

            else:
                i += 1  # skip junk

        # Execution logic
        has_top = top_line_update is not None
        has_mid = bool(middle_line_updates) or highlight_params is not None or source_param is not None

        if has_top:
            self.claim_zone(0x01)
            time.sleep(0.05)
            self.write_text(top_line_update[0], top_line_update[1])
            time.sleep(0.05)
            if not has_mid:
                self.release_zone(0x01)

        if has_mid:
            self.claim_zone(0x02)
            time.sleep(0.05)

            if source_param is not None:
                self.switch_source(source_param)
                time.sleep(0.05)

            for line_hex, text_clean in middle_line_updates:
                self.write_text(line_hex, text_clean)
                time.sleep(0.05)

            if highlight_params is not None:
                if len(highlight_params) == 3:
                    self.set_highlight(*highlight_params)
                else:
                    self.set_highlight(highlight_params[0], highlight_params[1])
                time.sleep(0.05)

            self.release_zone(0x02)
            time.sleep(0.05)

        if has_top and has_mid:
            self.release_zone(0x01)



# LAYER 3: USER INTERFACE

def print_menu():
    print("\n" + "="*40)
    print("      AUDI A8 DIS - CONTROL MENU")
    print("="*40)
    print(" [m] Switch to Media Screen")
    print(" [p] Switch to Phone Screen")
    print(" [i] Input Smart Text (e.g., '01 Radio 06 Line 1 E4 02 01')")
    print(" [d] Toggle CAN Debug Traffic")
    print(" [q] Quit")
    print("="*40)
    print("> ", end='', flush=True)

if __name__ == "__main__":
    driver = MMITester()
    driver.show_traffic = True 
    
    driver.perform_handshake()
    
    if not driver.is_connected:
        logger.error("Handshake failed. Exiting.")
        exit(1)

    manager = DISPayloadManager(driver)
    
    logger.info("\n--- 4. INITIALIZING DISPLAY ZONES ---")
    driver.active_sleep(0.5)
    manager.init_all_zones()
    
    typing_active = False
    input_buffer = ""
    
    driver.show_traffic = False 
    print_menu()

    try:
        while True:
            driver._recv_filtered(0.01)

            if msvcrt.kbhit():
                key = msvcrt.getch()
                
                if typing_active:
                    if key == b'\r': 
                        print()
                        if input_buffer:
                            logger.info(f"Injecting: {input_buffer}")
                            was_debug = driver.show_traffic
                            driver.show_traffic = True 
                            manager.write_smart_string(input_buffer)
                            driver.show_traffic = was_debug
                            
                        typing_active = False
                        input_buffer = ""
                        print_menu()
                        
                    elif key == b'\x1b': 
                        print("\nCancelled.")
                        typing_active = False
                        input_buffer = ""
                        print_menu()
                        
                    elif key == b'\x08': 
                        if len(input_buffer) > 0:
                            input_buffer = input_buffer[:-1]
                            print('\b \b', end='', flush=True)
                    else:
                        try:
                            char = key.decode('cp437')
                            input_buffer += char
                            print(char, end='', flush=True)
                        except: pass
                else:
                    cmd = key.lower()
                    
                    if cmd == b'd':
                        driver.show_traffic = not driver.show_traffic
                        status = "ON" if driver.show_traffic else "OFF"
                        print(f"\n--- DEBUG TRAFFIC: {status} ---")
                        if not driver.show_traffic: print_menu()
                        
                    elif cmd == b'm':
                        print("\nSwitching to Media...")
                        was_debug = driver.show_traffic
                        driver.show_traffic = True
                        manager.switch_source(0x06)
                        driver.show_traffic = was_debug
                        print_menu()
                        
                    elif cmd == b'p':
                        print("\nSwitching to Phone...")
                        was_debug = driver.show_traffic
                        driver.show_traffic = True
                        manager.switch_source(0x01)
                        driver.show_traffic = was_debug
                        print_menu()
                        
                    elif cmd == b'i':
                        typing_active = True
                        input_buffer = ""
                        print("\nCOMMAND MODE (Type string, Enter to send, Esc to cancel):")
                        print("Ex: E2 01 01 Telefon 06 Addressbook E4 01 00")
                        print("> ", end='', flush=True)
                        
                    elif cmd == b'q':
                        print("\nQuitting...")
                        break

    except KeyboardInterrupt:
        logger.info("\nStopping...")
        
    driver.bus.shutdown()
