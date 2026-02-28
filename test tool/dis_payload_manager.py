import can
import time
import logging
import re

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
        
        while time.time() - start_wait < 2.0:
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
            elif b0 == 0x9A:
                wait_ms = rx.data[1] if len(rx.data) > 1 else 100
                self.log_traffic("CLUS -> MMI", bytes(rx.data).hex(' ').upper(), f"CLUSTER BUSY 0x9A (Wait {wait_ms}ms)")
                time.sleep(wait_ms / 1000.0)
                self.log_traffic("MMI -> CLUS", bytes(data).hex(' ').upper(), f"RESENDING DATA {type_str} OUT (Seq {seq})")
                self.bus.send(msg)
                start_wait = time.time() 
                continue
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

    def wait_for_confirmation(self, expected_zone, timeout=3.0):
        logger.info(f"Waiting for Cluster Confirmation (0x3B) for Zone {expected_zone:02X}...")
        start_wait = time.time()
        
        while time.time() - start_wait < timeout:
            payload = self.wait_for_cluster_message(timeout=0.5)
            
            if payload:
                if payload[0] == 0x3B:
                    confirmed_zone = payload[2] if len(payload) > 2 else 0
                    status_code = payload[3] if len(payload) > 3 else 0x00
                    
                    if confirmed_zone == expected_zone and status_code == 0x03:
                        logger.info(f"✅ Confirmation received for Zone {expected_zone:02X} (Status: 03 SHOWING)")
                        return 'SUCCESS'
                    elif status_code == 0x02:
                        logger.warning(f"⏳ Cluster Busy/Warning Active (Zone {confirmed_zone:02X}, Status 02).")
                        return 'BUSY'
                    elif status_code == 0x01:
                        logger.info(f"🟢 Cluster Free (Zone {confirmed_zone:02X}, Status 01).")
                        return 'FREE'
                    else:
                        status_str = "SHOWING/OK" if status_code == 0x03 else "ERROR/ABORT"
                        logger.warning(f"⚠️ Intermediate 3B: Zone {confirmed_zone:02X}, Status {status_code:02X} ({status_str}). Waiting for target...")
                        continue
                        
                elif payload[0] == 0x09:
                    zone = payload[1] if len(payload) > 1 else 0
                    error_code = payload[4] if len(payload) > 4 else 0
                    logger.error(f"❌ Cluster ERROR 0x09 (invalid param) Zone {zone:02X} Code {error_code:02X}")
                    return 'ERROR'

        logger.warning(f"Failed to receive 0x3B confirmation for Zone {expected_zone:02X} within timeout.")
        return 'TIMEOUT'

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
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x02]): self.wait_for_cluster_message() 
        self.active_sleep(2.0)
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x02]): self.wait_for_cluster_message()
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x01]): self.wait_for_cluster_message()
        if self.send_data_and_wait_ack([0x02, 0x01, 0x48]): self.wait_for_cluster_message()

        logger.info("\n======================================")
        logger.info("   HANDSHAKE COMPLETE - CHANNEL OPEN  ")
        logger.info("======================================")
        self.is_connected = True


class DISPayloadManager:
    def __init__(self, driver):
        self.driver = driver

    def init_zone(self, zone_id):
        logger.info(f"\n>> Initializing Zone {zone_id:02X}")
        self.driver.send_message([OP_INIT, 0x01, zone_id])
        resp = self.driver.wait_for_cluster_message(timeout=2.0)
        return resp and resp[0] == 0x31

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
        # Retry loop for Busy (02) or Free (01) states
        for attempt in range(6): 
            success = self.driver.send_message([OP_RELEASE, 0x01, zone_id])
            if success:
                status = self.driver.wait_for_confirmation(zone_id)
                if status == 'SUCCESS':
                    return True
                elif status == 'BUSY':
                    logger.info("Cluster Busy! Waiting 2.0s before retrying release...")
                    time.sleep(2.0)
                    continue
                elif status == 'FREE':
                    logger.info("Cluster Free! Retrying release immediately...")
                    time.sleep(0.5)
                    continue
                elif status == 'ERROR' or status == 'TIMEOUT':
                    return False
        return False

    def write_text(self, line_id, text_str):
        text_bytes = text_str.encode('cp1252', errors='replace')
        length_byte = 0x02 + len(text_bytes)
        payload = [OP_WRITE, length_byte, line_id, 0x00] + list(text_bytes)
        return self.driver.send_message(payload)

    def set_highlight(self, p1: int, p2: int, p3: int = None):
        if p3 is None:
            payload = [OP_HIGHLIGHT, 0x02, p1, p2]
        else:
            payload = [OP_HIGHLIGHT, 0x03, p1, p2, p3]
        return self.driver.send_message(payload)

    def write_nav_bar(self, value):
        if value < 0:
            logger.info("\n>> Hiding Nav Bar (DE 00)")
            return self.driver.send_message([0xDE, 0x00])
        else:
            logger.info(f"\n>> Drawing Nav Bar: {value:02X}")
            return self.driver.send_message([0xDE, 0x01, value])

    def draw_arrow(self, line_id, hex_data_str):
        try:
            data_bytes = [int(x, 16) for x in hex_data_str.strip().split()]
            if not data_bytes: return False
            length_byte = 1 + len(data_bytes) 
            payload = [0xDC, length_byte, line_id] + data_bytes
            logger.info(f"\n>> Drawing Arrow on {line_id:02X}: {hex_data_str}")
            return self.driver.send_message(payload)
        except ValueError:
            logger.error("Invalid hex string for arrow data.")
            return False

    def send_raw_payload(self, hex_string):
        try:
            payload = [int(x, 16) for x in hex_string.strip().split()]
            if not payload: return False
            logger.info(f"\n>> Sending Raw Payload: {hex_string}")
            return self.driver.send_message(payload)
        except ValueError:
            logger.error("Invalid hex string for raw payload.")
            return False

    def write_smart_string(self, input_str: str):
        if not input_str.strip(): return
        tokens = re.split(r'\s+', input_str.strip().upper())
        i = 0
        top_line_update = None
        middle_line_updates = []
        highlight_params = None   
        source_param = None

        def is_tag(t: str) -> bool:
            return (len(t) == 2 and t[0] == '0' and t[1].isdigit()) or t in ('E4', 'E2')

        while i < len(tokens):
            token = tokens[i]
            if is_tag(token):
                tag = token
                i += 1
                if tag == 'E4':
                    params = []
                    while i < len(tokens) and len(params) < 3:
                        try:
                            params.append(int(tokens[i], 16))
                            i += 1
                        except ValueError: break
                    if len(params) >= 2: highlight_params = tuple(params)
                    continue
                elif tag == 'E2':
                    if i < len(tokens):
                        try:
                            source_param = int(tokens[i], 16)
                            i += 1
                        except ValueError: pass
                    continue
                else:
                    try:
                        line_hex = int(tag, 16)
                        text_parts = []
                        while i < len(tokens) and not is_tag(tokens[i]):
                            text_parts.append(tokens[i])
                            i += 1
                        text_clean = ' '.join(text_parts).strip()
                        if text_clean == '.': text_clean = ""
                        if line_hex == 0x01: top_line_update = (line_hex, text_clean)
                        elif line_hex in [0x00, 0x05, 0x06, 0x07, 0x08, 0x09]:
                            middle_line_updates.append((line_hex, text_clean))
                    except ValueError: pass
                    continue
            else:
                i += 1 

        has_top = top_line_update is not None
        has_mid = bool(middle_line_updates) or highlight_params is not None or source_param is not None

        if has_top:
            self.claim_zone(0x01)
            time.sleep(0.05)
            self.write_text(top_line_update[0], top_line_update[1])
            time.sleep(0.05)
            if not has_mid: self.release_zone(0x01)

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
                if len(highlight_params) == 3: self.set_highlight(*highlight_params)
                else: self.set_highlight(highlight_params[0], highlight_params[1])
                time.sleep(0.05)
            self.release_zone(0x02)
            time.sleep(0.05)

        if has_top and has_mid:
            self.release_zone(0x01)
