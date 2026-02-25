import can
import time
import logging

# --- Configuration ---
CAN_INTERFACE = 'pcan'
CAN_CHANNEL   = 'PCAN_USBBUS1'
CAN_BITRATE   = 500000

CAN_ID_TX = 0x490
CAN_ID_RX = 0x491

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

    def log_traffic(self, direction, hex_data, desc):
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
        """Core listener that automatically replies to A3 PINGs to keep connection alive."""
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
        """Sleeps for X seconds while continuing to answer Keep-Alive Pings."""
        start = time.time()
        while time.time() - start < duration:
            self._recv_filtered(0.1)

    def send_data_and_wait_ack(self, payload_bytes, pkt_type=0x10):
        seq = self.tx_seq
        header = pkt_type | seq
        data = [header] + list(payload_bytes)
        
        msg = can.Message(arbitration_id=CAN_ID_TX, data=data, is_extended_id=False)
        self.bus.send(msg)
        self.log_traffic("MMI -> CLUS", bytes(data).hex(' ').upper(), f"DATA OUT (Seq {seq})")
        
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
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x02]):
            self.wait_for_cluster_message() 
        
        logger.info("\n[Delay - Keep-alives processing...]")
        self.active_sleep(2.0)
        
        logger.info("\n[Step 2 - Param 11]")
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x02]):
            self.wait_for_cluster_message()
            
        logger.info("\n[Step 3 - Param 12]")
        if self.send_data_and_wait_ack([0x00, 0x02, 0x4D, 0x01]):
            self.wait_for_cluster_message()
        
        logger.info("\n[Step 4 - Param 13 & Final Burst]")
        if self.send_data_and_wait_ack([0x02, 0x01, 0x48]):
            self.wait_for_cluster_message()

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

if __name__ == "__main__":
    tester = MMITester()
    tester.perform_handshake()
    
    if tester.is_connected:

        tester.run_keepalive_loop()
