import can
import time
import logging
import re
import msvcrt  # Windows-specific non-blocking input

# --- Configuration ---
# Interface: 'pcan' for Peak System PCAN-USB
# Channel: Usually 'PCAN_USBBUS1'. Try 'PCAN_USBBUS2' if no traffic appears.
CAN_INTERFACE = 'pcan'
CAN_CHANNEL   = 'PCAN_USBBUS1'
CAN_BITRATE   = 500000

# CAN IDs
CAN_ID_MMI     = 0x490  # We listen to this to track sequence, and inject ON this ID
CAN_ID_CLUSTER = 0x491  # We listen to this for active confirmation

# Protocol Constants
PKT_TYPE_END   = 0x10  # Last frame of a message (or single frame)
PKT_TYPE_BODY  = 0x20  # Middle frame of a multi-frame message
PKT_TYPE_ACK   = 0xB0  # Acknowledgment (sent by MMI or Cluster)

# Heartbeat Signatures (Both directions allowed now)
HB_PING_BYTE   = 0xA3 
HB_ACK_PREFIX  = [0xA1, 0x0F]

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

class DISInjector:
    def __init__(self, channel=CAN_CHANNEL, interface=CAN_INTERFACE, bitrate=CAN_BITRATE):
        logger.info(f"Attempting to connect to {interface}/{channel} @ {bitrate}bps...")
        try:
            # state=can.bus.BusState.ACTIVE ensures we are not in passive mode
            self.bus = can.Bus(interface=interface, channel=channel, bitrate=bitrate, state=can.bus.BusState.ACTIVE)
            logger.info("  -> Success! CAN Bus connected.")
        except can.CanError as e:
            logger.error(f"  -> FAILED to open CAN bus.")
            logger.error(f"  -> Error details: {e}")
            logger.error("  -> TIP: Make sure SavvyCAN is CLOSED. PCAN cannot be shared.")
            exit(1)
        
        # State tracking
        self.next_seq_num = 0  
        self.is_active = False
        self.last_activity_ts = 0
        self.total_msgs_received = 0
        
        # Basic AUDSCII Map
        self.audscii_map = {}

    def shutdown(self):
        self.bus.shutdown()

    def _get_next_seq(self):
        """Returns the next valid sequence number."""
        return self.next_seq_num

    def _update_seq(self, new_seq):
        """Updates our local tracker after we inject a frame."""
        self.next_seq_num = new_seq

    def _to_audscii(self, text):
        """Converts string to list of bytes for DIS."""
        out = []
        for char in text:
            val = ord(char)
            if val in self.audscii_map:
                out.append(self.audscii_map[val])
            else:
                out.append(val)
        return out

    def listen(self, print_traffic=False, duration=0.0):
        """
        Listens for CAN traffic and synchronizes the sequence counter.
        Returns the last CAN message object received (if any) to allow checking ACKs.
        """
        start_time = time.time()
        last_msg = None

        while True:
            # Check if we should exit loop
            if duration > 0:
                if (time.time() - start_time) > duration:
                    break
                remaining = duration - (time.time() - start_time)
                timeout = min(remaining, 0.01) if remaining > 0 else 0
            else:
                timeout = 0 # Non-blocking single pass
                
            msg = self.bus.recv(timeout=timeout)
            
            if msg is None:
                if duration == 0: break
                else: continue 
            
            last_msg = msg
            self.total_msgs_received += 1
            can_id = msg.arbitration_id
            data = msg.data
            
            if len(data) == 0: continue

            if can_id in [CAN_ID_MMI, CAN_ID_CLUSTER]:
                
                byte0 = data[0]
                high_nibble = byte0 & 0xF0
                low_nibble  = byte0 & 0x0F
                
                desc = ""
                sync_msg = ""
                
                # --- Protocol Decoding & Sequence Sync ---
                
                if byte0 == 0xA3:
                    desc = "HEARTBEAT (PING)"
                    self.is_active = True
                elif byte0 == 0xA1:
                    desc = "HEARTBEAT (RESP)"
                    self.is_active = True

                elif high_nibble == PKT_TYPE_ACK:
                    desc = f"ACK (Seq {low_nibble})"
                    # CORRECT LOGIC: Only trust ACKs coming FROM the Cluster (0x491)
                    if can_id == CAN_ID_CLUSTER:
                        self.next_seq_num = low_nibble
                        sync_msg = f"[SEQ->{low_nibble}]"
                    else:
                        sync_msg = "[SEQ IGN]" 

                elif high_nibble in [PKT_TYPE_END, PKT_TYPE_BODY]:
                    type_str = "END" if high_nibble == PKT_TYPE_END else "BODY"
                    desc = f"DATA {type_str} (Seq {low_nibble})"
                    # CORRECT LOGIC: Only trust DATA coming FROM the MMI (0x490)
                    if can_id == CAN_ID_MMI:
                        self.next_seq_num = (low_nibble + 1) % 16
                        sync_msg = f"[SEQ->{self.next_seq_num}]"
                    else:
                        sync_msg = "[SEQ IGN]"

                else:
                    desc = f"UNKNOWN ({hex(byte0)})"

                # --- Debug Printing ---
                if print_traffic:
                    hex_data = data.hex(' ').upper()
                    label = "MMI->DIS" if can_id == CAN_ID_MMI else "DIS->MMI"
                    pad = " " * (20 - len(hex_data))
                    print(f"\r{label} {hex(can_id)}: {hex_data}{pad} | {desc:<20} {sync_msg}    ")
        
        return last_msg

    def send_ack(self, sequence_num):
        """Sends an ACK frame on MMI ID 0x490 for the given sequence."""
        ack_pkt = [PKT_TYPE_ACK + sequence_num]
        try:
            msg = can.Message(arbitration_id=CAN_ID_MMI, data=ack_pkt, is_extended_id=False)
            self.bus.send(msg)
            print(f"\rINJECTED {hex(CAN_ID_MMI)}: {bytes(ack_pkt).hex(' ').upper()}             | ACK (Seq {sequence_num}) >>>")
        except can.CanError as e:
            logger.error(f"Failed to send ACK: {e}")

    def inject_frame_raw(self, payload_bytes):
        """
        Splits payload into CAN frames and injects them.
        Returns True if the transaction completed (ACKs received), False otherwise.
        """
        total_len = len(payload_bytes)
        offset = 0
        success = True
        
        # Log the starting sequence
        print(f"\r[DEBUG] Injection Start. Using Seq: {self._get_next_seq()}")
        
        while offset < total_len:
            remaining = total_len - offset
            
            if remaining > 7:
                chunk_size = 7
                pkt_type = PKT_TYPE_BODY
            else:
                chunk_size = remaining
                pkt_type = PKT_TYPE_END

            chunk = payload_bytes[offset : offset + chunk_size]
            
            # --- BYTE 0 LOGIC ---
            seq = self._get_next_seq()
            header_byte = pkt_type | seq
            
            can_data = [header_byte] + list(chunk)
            
            try:
                msg = can.Message(arbitration_id=CAN_ID_MMI, data=can_data, is_extended_id=False)
                self.bus.send(msg)
                
                hex_data = bytes(can_data).hex(' ').upper()
                print(f"\rINJECTED {hex(CAN_ID_MMI)}: {hex_data}            | DATA (Seq {seq}) >>>")
                
                # Update tracker locally immediately after sending
                self._update_seq((seq + 1) % 16)
                offset += chunk_size
                
                # Listen specifically for an ACK from Cluster
                # We listen for a short window (50ms)
                start_wait = time.time()
                got_ack = False
                while (time.time() - start_wait) < 0.05:
                    last_msg = self.listen(print_traffic=True, duration=0.01)
                    if last_msg and last_msg.arbitration_id == CAN_ID_CLUSTER:
                        byte0 = last_msg.data[0]
                        if (byte0 & 0xF0) == PKT_TYPE_ACK:
                            # Verify ACK sequence? (Usually ack = seq + 1, but we trust the bus update)
                            got_ack = True
                            break
                
                if not got_ack and pkt_type == PKT_TYPE_END:
                    success = False

            except can.CanError as e:
                logger.error(f"CAN Send Error: {e}")
                success = False
                break
        
        return success

    def wait_for_cluster_data_and_ack(self, timeout=0.5):
        """
        Waits for the Cluster to send a Data Packet (usually 0x3B...)
        and replies with the correct ACK.
        """
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            msg = self.listen(print_traffic=True, duration=0.01)
            if msg and msg.arbitration_id == CAN_ID_CLUSTER:
                byte0 = msg.data[0]
                high_nibble = byte0 & 0xF0
                low_nibble = byte0 & 0x0F
                
                # If Cluster sends DATA (End or Body)
                if high_nibble in [PKT_TYPE_END, PKT_TYPE_BODY]:
                    # We need to ACK this immediately
                    ack_seq = (low_nibble + 1) % 16
                    self.send_ack(ack_seq)
                    return True
        return False

    def send_release(self, zone_id):
        """
        Sends the Release/Confirm packet (0x32 0x01 0x01/02).
        Retries up to 3 times if no ACK is received.
        """
        # zone_id: 0x01 for Top, 0x02 for Middle
        payload = [0x32, 0x01, zone_id]
        
        for attempt in range(3):
            if self.inject_frame_raw(payload):
                return True
            time.sleep(0.05) # Wait before retry
            
        logger.warning(f"Release failed after 3 attempts for zone {hex(zone_id)}")
        return False

    # --- User Specific Commands ---

    def claim_top_line(self):
        if not self.is_active: return False
        payload = [0x36, 0x01, 0x01] 
        return self.inject_frame_raw(payload)

    def claim_middle_line(self):
        if not self.is_active: return False
        payload = [0x36, 0x01, 0x02]
        return self.inject_frame_raw(payload)

    def write_text(self, line_num, text_str):
        if not self.is_active: return False
        chars = self._to_audscii(text_str)
        length_byte = 0x02 + len(chars)
        # Byte 1: Opcode(E0), Byte 2: Len, Byte 3: Line, Byte 4: Sep(00), Byte 5+: Text
        payload = [0xE0, length_byte, line_num, 0x00] + chars
        return self.inject_frame_raw(payload)
        
    def write_smart_string(self, input_str):
        if not self.is_active:
            logger.warning("Skipping Smart Write: Bus not active")
            return
        
        # Regex updated to capture empty content
        pattern = r'\b(0[0-9])\s+(.*?)(?=\s+0[0-9]\b|$)'
        matches = re.findall(pattern, input_str)
        
        if not matches:
            logger.warning(f"No valid line tags found in: '{input_str}'")
            return

        # Separate Top Line vs Middle Lines
        top_line_update = None
        middle_line_updates = []

        for line_str, text_content in matches:
            try:
                line_hex = int(line_str, 16)
                text_clean = text_content.strip()
                
                # Treat '.' as an explicit instruction to clear the line
                if text_clean == '.':
                    text_clean = ""
                
                if line_hex == 0x01:
                    top_line_update = (line_hex, text_clean)
                elif line_hex in [0x00, 0x05, 0x06, 0x07, 0x08, 0x09]:
                    middle_line_updates.append((line_hex, text_clean))
            except ValueError:
                logger.error(f"Failed to parse line number: {line_str}")

        # --- LOGIC: Handle Whole Screen (Nested) or Individual Parts ---

        has_top = (top_line_update is not None)
        has_mid = (len(middle_line_updates) > 0)

        # 1. Start Top Claim
        if has_top:
            self.claim_top_line()
            self.listen(print_traffic=True, duration=0.05)
            # Write Top Text
            line_hex, text_clean = top_line_update
            self.write_text(line_hex, text_clean)
            self.listen(print_traffic=True, duration=0.05)

        # 2. Perform Middle Sequence (Nested inside Top if both exist)
        if has_mid:
            # Claim Middle
            self.claim_middle_line()
            self.listen(print_traffic=True, duration=0.05)
            
            # Write ALL Middle Lines
            for line_hex, text_clean in middle_line_updates:
                self.write_text(line_hex, text_clean)
                self.listen(print_traffic=True, duration=0.05)
            
            # Release Middle
            if self.send_release(0x02):
                self.wait_for_cluster_data_and_ack()
            
            # Pause briefly
            self.listen(print_traffic=True, duration=0.05)

        # 3. Finish Top Release (If we started it)
        if has_top:
            if self.send_release(0x01):
                self.wait_for_cluster_data_and_ack()

# --- Main Execution ---

if __name__ == "__main__":
    injector = DISInjector()
    
    debug_active = False
    typing_active = False
    input_buffer = ""

    logger.info("Starting Main Loop.")
    logger.info("CONTROLS:")
    logger.info("  [d] Toggle Debug Traffic (Filtered)")
    logger.info("  [i] Type Manual Command (e.g. '01 Top 05 Header 09 .')")
    logger.info("Waiting for Active Comms (0xA3 / 0xA1)...")
    
    start_time = time.time()
    warned_about_no_traffic = False

    try:
        while True:
            # 1. Keyboard Input
            if msvcrt.kbhit():
                key = msvcrt.getch()
                
                if typing_active:
                    if key == b'\r': # Enter
                        print()
                        if input_buffer:
                            logger.info(f"Processing: {input_buffer}")
                            debug_was_active = debug_active
                            debug_active = True 
                            injector.write_smart_string(input_buffer)
                            debug_active = debug_was_active 
                        typing_active = False
                        input_buffer = ""
                        print("Exited Command Mode.")
                    elif key == b'\x1b': # Escape
                        print("\nCancelled.")
                        typing_active = False
                        input_buffer = ""
                    elif key == b'\x08': # Backspace
                        if len(input_buffer) > 0:
                            input_buffer = input_buffer[:-1]
                            print('\b \b', end='', flush=True)
                    else:
                        try:
                            char = key.decode('cp437')
                            input_buffer += char
                            print(char, end='', flush=True)
                        except:
                            pass
                else:
                    if key.lower() == b'd':
                        debug_active = not debug_active
                        status = "ON" if debug_active else "OFF"
                        print(f"\n--- DEBUG TRAFFIC: {status} ---")
                    elif key.lower() == b'i':
                        typing_active = True
                        input_buffer = ""
                        print("\nCOMMAND MODE (Type string, Enter to send, Esc to cancel):")
                        print("> ", end='', flush=True)

            # 2. Drain CAN buffer
            show_traffic = debug_active and not typing_active
            injector.listen(print_traffic=show_traffic, duration=0)
            
            # 3. Health Check
            if injector.total_msgs_received == 0 and not warned_about_no_traffic:
                if time.time() - start_time > 3.0:
                    logger.warning("!!! NO TRAFFIC RECEIVED !!!")
                    warned_about_no_traffic = True

            time.sleep(0.001)

    except KeyboardInterrupt:
        logger.info("Stopping...")
        injector.shutdown()
