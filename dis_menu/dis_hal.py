# dis_hal.py
import can
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s (HAL): %(message)s')
logger = logging.getLogger(__name__)

class CANDriver:
    def __init__(self, interface='pcan', channel='PCAN_USBBUS1', bitrate=500000):
        self.bus_cluster = can.Bus(interface=interface, channel=channel, bitrate=bitrate, state=can.bus.BusState.ACTIVE)
        self.rx_callbacks = []

    def register_cluster_callback(self, callback):
        self.rx_callbacks.append(callback)

    def send_cluster(self, arbitration_id, data):
        msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=False)
        self.bus_cluster.send(msg)

    def poll(self):
        try:
            while True:
                msg = self.bus_cluster.recv(timeout=0.002)
                if not msg: break
                for cb in self.rx_callbacks:
                    cb(msg)
        except Exception:
            pass

    def shutdown(self):
        self.bus_cluster.shutdown()


class MMIProtocol:
    """Layer 2: Audi MMI Session & Transport Protocol (Seq Counters, Handshake)"""
    def __init__(self, can_driver):
        self.can = can_driver
        self.can.register_cluster_callback(self._rx_handler)
        
        self.tx_seq = 0
        self.rx_queue = []
        self.is_connected = False
        self.show_trace = False

    def _log_trace(self, dir_str, data, desc):
        if not self.show_trace: return
        hex_str = bytes(data).hex(' ').upper()
        pad = " " * (25 - len(hex_str))
        print(f"{dir_str}: {hex_str}{pad} | {desc}")

    def _rx_handler(self, msg):
        if msg.arbitration_id == 0x491:
            if msg.data and msg.data[0] == 0xA3:
                self._log_trace("CLUS -> MMI", [0xA3], "HEARTBEAT (PING IN)")
                pong = [0xA1, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF]
                self.can.send_cluster(0x490, pong)
                self._log_trace("MMI -> CLUS", pong, "HEARTBEAT (PONG)")
            else:
                self.rx_queue.append(msg)

    def _wait_for_frame(self, timeout=1.0):
        start = time.time()
        while time.time() - start < timeout:
            if self.rx_queue: return self.rx_queue.pop(0)
            self.can.poll() 
            time.sleep(0.01)
        return None

    def send_ack(self, seq_to_send):
        ack_payload = [0xB0 | (seq_to_send % 16)]
        self.can.send_cluster(0x490, ack_payload)
        self._log_trace("MMI -> CLUS", ack_payload, f"ACK OUT (Seq {seq_to_send % 16})")

    def send_data_and_wait_ack(self, payload_chunk, is_end=True):
        """
        CRITICAL FIX: payload_chunk MUST ONLY BE 7 BYTES MAX!
        The header byte is dynamically generated here and prepended to the array.
        """
        seq = self.tx_seq
        header = 0x10 if is_end else 0x20
        header |= seq
        
        full_payload = [header] + list(payload_chunk)
        self.can.send_cluster(0x490, full_payload)
        
        type_str = "END" if is_end else "BODY"
        self._log_trace("MMI -> CLUS", full_payload, f"DATA {type_str} OUT (Seq {seq})")
        
        if not is_end:
            self.tx_seq = (seq + 1) % 16
            time.sleep(0.01) # Small gap between body frames
            return True

        expected_ack = (seq + 1) % 16
        start_wait = time.time()
        
        while time.time() - start_wait < 2.0:
            rx = self._wait_for_frame(0.05)
            if not rx: continue
            
            b0 = rx.data[0]
            if (b0 & 0xF0) == 0xB0 and (b0 & 0x0F) == expected_ack:
                self._log_trace("CLUS -> MMI", rx.data, f"ACK IN (Seq {expected_ack})")
                self.tx_seq = expected_ack
                return True
            elif b0 == 0x9A:
                wait_ms = rx.data[1] if len(rx.data) > 1 else 100
                self._log_trace("CLUS -> MMI", rx.data, f"CLUSTER BUSY 0x9A (Wait {wait_ms}ms)")
                time.sleep(wait_ms / 1000.0)
                self.can.send_cluster(0x490, full_payload) 
                start_wait = time.time() 
            elif (b0 & 0xF0) in [0x10, 0x20]:
                self.rx_queue.append(rx) 
                
        logger.warning(f"Timeout waiting for ACK on Seq {seq}")
        return False

    def send_multi_frame(self, payload_bytes):
        """
        Chunks a large byte array into exactly 7-byte segments.
        Then passes it to send_data_and_wait_ack which prepends the 1-byte Protocol Header.
        """
        offset = 0
        total = len(payload_bytes)
        while offset < total:
            chunk = payload_bytes[offset:offset+7]
            offset += 7
            is_last = (offset >= total)
            if not self.send_data_and_wait_ack(chunk, is_end=is_last):
                return False
        return True

    def wait_for_cluster_message(self, timeout=2.0):
        start_wait = time.time()
        payloads = []
        
        while time.time() - start_wait < timeout:
            rx = self._wait_for_frame(0.05)
            if not rx: continue
            
            b0 = rx.data[0]
            high_nib = b0 & 0xF0
            rx_seq = b0 & 0x0F
            
            if high_nib == 0x20:
                self._log_trace("CLUS -> MMI", rx.data, f"DATA BODY IN (Seq {rx_seq})")
                payloads.extend(rx.data[1:])
            elif high_nib == 0x10:
                self._log_trace("CLUS -> MMI", rx.data, f"DATA END IN (Seq {rx_seq})")
                payloads.extend(rx.data[1:])
                self.send_ack((rx_seq + 1) % 16)
                return payloads
        return None

    def wait_for_confirmation(self, expected_zone, timeout=3.0):
        start_wait = time.time()
        while time.time() - start_wait < timeout:
            payload = self.wait_for_cluster_message(timeout=0.5)
            if payload:
                if payload[0] == 0x3B:
                    confirmed_zone = payload[2] if len(payload) > 2 else 0
                    status_code = payload[3] if len(payload) > 3 else 0x00
                    if confirmed_zone == expected_zone and status_code in [0x03, 0x04]:
                        return 'SUCCESS'
                    elif status_code == 0x02: return 'BUSY'
                    elif status_code == 0x01: return 'FREE'
                elif payload[0] == 0x09:
                    return 'ERROR'
        return 'TIMEOUT'

    def perform_handshake(self):
        logger.info("Starting MMI Handshake...")
        self.rx_queue.clear()
        self.tx_seq = 0
        self.can.send_cluster(0x490, [0xA0, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF])
        
        while True:
            rx = self._wait_for_frame(0.5)
            if rx and rx.data[0] == 0xA1: break
                
        time.sleep(1.0) 
        
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x02]): self.wait_for_cluster_message() 
        time.sleep(2.0)
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x02]): self.wait_for_cluster_message()
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x01]): self.wait_for_cluster_message()
        if self.send_data_and_wait_ack([0x02, 0x01, 0x48]): self.wait_for_cluster_message()

        logger.info("MMI Handshake Complete. Channel Open.")
        self.is_connected = True
