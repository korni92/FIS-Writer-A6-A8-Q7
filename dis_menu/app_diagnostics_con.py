# app_diagnostics_con.py
import time
import logging

logger = logging.getLogger("DIAG_CON")

class DiagnosticsConnection:
    """Backend TP2.0 & KWP2000 Handler"""
    def __init__(self, can_drv):
        self.can = can_drv
        self.ecu_id = 0
        self.tx_id = 0
        self.tx_seq = 0
        self.rx_queue = []
        self.rx_id_tp20 = 0x300 
        self.show_trace = False
        self.can.register_cluster_callback(self.parse_message)

    def _log_trace(self, direction, msg_id, data):
        """Helper to output RAW CAN trace if enabled by OS Kernel"""
        if self.show_trace:
            data_hex = " ".join([f"{x:02X}" for x in data])
            logger.info(f"[DIAG {direction}] ID:0x{msg_id:03X} DATA: [{data_hex}]")

    def _send_frame(self, target_id, data):
        """Wraps standard CAN transmission to inject tracing"""
        self._log_trace("TX", target_id, data)
        self.can.send_cluster(target_id, data)

    def parse_message(self, msg):
        valid_ids = [0x200 + self.ecu_id, self.rx_id_tp20]
        if msg.arbitration_id in valid_ids:
            self._log_trace("RX", msg.arbitration_id, msg.data)
            
            # Auto-ACK for TP2.0 setup channel
            if msg.arbitration_id == self.rx_id_tp20 and len(msg.data) > 0 and msg.data[0] == 0xA3:
                self._send_frame(self.tx_id, [0xA1, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF])
            else:
                self.rx_queue.append(msg)

    def _wait_for_frame(self, target_id, timeout=1.5):
        start = time.time()
        while time.time() - start < timeout:
            self.can.poll() 
            for i, msg in enumerate(self.rx_queue):
                if msg.arbitration_id == target_id:
                    return self.rx_queue.pop(i)
            time.sleep(0.001) 
        return None

    def connect(self, ecu_id):
        logger.info(f"Attempting TP2.0 Connection to ECU 0x{ecu_id:02X}")
        self.ecu_id = ecu_id
        self.rx_queue.clear()
        time.sleep(0.3) 
        
        self._send_frame(0x200, [self.ecu_id, 0xC0, 0x00, 0x10, 0x00, 0x03, 0x01])
        resp = self._wait_for_frame(0x200 + self.ecu_id)
        
        if resp and resp.data[1] == 0xD0:
            self.tx_id = resp.data[4] + (resp.data[5] << 8)
            self._send_frame(self.tx_id, [0xA0, 0x0F, 0x8A, 0xFF, 0x32, 0xFF])
            
            a1_resp = self._wait_for_frame(self.rx_id_tp20)
            if a1_resp and a1_resp.data[0] == 0xA1:
                self.tx_seq = 0
                if self.execute_kwp(0x10, [0x89]):
                    time.sleep(0.3) # Give ECU time to switch to diag session
                    return True
        return False

    def execute_kwp(self, service, params=[], quiet=True):
        self.rx_queue.clear()
        payload = [service] + params
        header = [0x10 | (self.tx_seq % 16), 0x00, len(payload)]
        
        if not quiet and not self.show_trace: 
            logger.info(f"KWP TX: {[hex(x) for x in payload]}")
            
        self._send_frame(self.tx_id, header + payload)

        ack = self._wait_for_frame(self.rx_id_tp20, timeout=1.0)
        if not ack or (ack.data[0] & 0xF0) != 0xB0: return None
            
        self.tx_seq = ack.data[0] & 0x0F
        data_buffer = bytearray()
        start_data = time.time()
        
        while time.time() - start_data < 4.0: 
            frame = self._wait_for_frame(self.rx_id_tp20, timeout=0.2)
            if not frame: continue

            pci = frame.data[0] & 0xF0
            rx_seq = frame.data[0] & 0x0F

            if pci in (0x00, 0x10, 0x20):
                # 1. Extract Data
                if len(data_buffer) == 0:
                    if len(frame.data) > 3: data_buffer.extend(frame.data[3:])
                else:
                    if len(frame.data) > 1: data_buffer.extend(frame.data[1:])
                
                # 2. Always ACK the frame to keep the stream moving
                self._send_frame(self.tx_id, [0xB0 | ((rx_seq + 1) % 16)])

                # 3. If it's the LAST frame (0x10 or 0x00), process it
                if pci in (0x00, 0x10):
                    # Handle NRC 0x78 (Response Pending) -> Reset timer and keep waiting
                    if len(data_buffer) >= 3 and data_buffer[0] == 0x7F and data_buffer[2] == 0x78:
                        data_buffer.clear()
                        start_data = time.time()
                        continue
                        
                    return list(data_buffer)

        return None

    def get_ecu_name(self):
        time.sleep(0.2) # Delay to prevent overwhelming slow ECUs
        res = self.execute_kwp(0x1A, [0x9B])
        if res and len(res) > 28 and res[0] == 0x5A:
            version = "".join(chr(b) for b in res[14:18] if 32 <= b <= 126).strip()
            bauteil_str = "".join(chr(b) for b in res[28:] if 32 <= b <= 126).strip()
            return f"{bauteil_str} {version}".strip()
        return "Unknown ECU"

    def get_ecu_id_pages(self):
        time.sleep(0.2)
        res = self.execute_kwp(0x1A, [0x9B])
        pages = []
        if res and len(res) >= 14 and res[0] == 0x5A:
            tn = "".join(chr(b) for b in res[2:14] if 32 <= b <= 126).strip()
            version = "".join(chr(b) for b in res[14:18] if 32 <= b <= 126).strip() if len(res)>=18 else ""
            codierung = f"{int.from_bytes(res[19:22], byteorder='big'):07d}" if len(res) >= 22 else ""
            wsc = f"Imp:{int.from_bytes(res[22:24], byteorder='big')} WSC:{int.from_bytes(res[26:28], byteorder='big')}" if len(res) >= 28 else ""
            bauteil = "".join(chr(b) for b in res[28:] if 32 <= b <= 126).strip() if len(res)>28 else ""
            
            pages.append(["Part Number:", tn[:16], tn[16:32], ""])
            pages.append(["Component:", bauteil[:16], bauteil[16:32], version[:16]])
            pages.append(["Coding:", codierung[:16], "Shop Code:", wsc[:16]])
        else:
            pages.append(["Read Error", "Or Not Supported", "", ""])
        return pages

    def get_ext_id_pages(self):
        time.sleep(0.1)
        res = self.execute_kwp(0x1A, [0x86])
        pages = []
        if res and res[0] == 0x5A:
            d86 = res[2:]
            sn = "".join(chr(b) if 32 <= b <= 126 else '' for b in d86[1:15]).strip()
            ident = "".join(chr(b) if 32 <= b <= 126 else '' for b in d86[16:23]).strip()
            date = "".join(chr(b) if 32 <= b <= 126 else '' for b in d86[23:31]).strip()
            rev = "".join(chr(b) if 32 <= b <= 126 else '' for b in d86[31:34]).strip()
            
            pages.append(["Serial Number:", sn[:16], sn[16:32], ""])
            pages.append(["Identification:", ident[:16], ident[16:32], ""])
            pages.append(["Revision:", rev[:16], "Date:", date[:16]])
        else:
            pages.append(["Read Error", "Or Not Supported", "", ""])
        return pages

    def read_mwb(self, block):
        res = self.execute_kwp(0x21, [block])
        parsed = []
        if res and len(res) >= 2 and res[0] == 0x61:
            data_bytes = res[2:]
            for i in range(0, min(12, len(data_bytes)), 3):
                if i + 2 < len(data_bytes):
                    typ, a, b = data_bytes[i], data_bytes[i+1], data_bytes[i+2]
                    parsed.append(f"[{typ:02X}] {a:02X} {b:02X}")
        return parsed

    def read_dtcs_list(self):
        res = self.execute_kwp(0x18, [0x02, 0xFF, 0x00]) or self.execute_kwp(0x18, [0x00, 0xFF, 0x00])
        dtcs = []
        if res and res[0] == 0x58:
            num = res[1]
            for i in range(num):
                offset = 2 + (i * 3)
                if offset + 2 < len(res):
                    high = res[offset]
                    low = res[offset+1]
                    vag_code = (high << 8) | low
                    hex_code = f"P{high:02X}{low:02X}00" 
                    dtcs.append({"vag": vag_code, "hex": hex_code})
        return dtcs

    def clear_dtcs(self):
        res = self.execute_kwp(0x14, [0xFF, 0x00])
        return res and res[0] == 0x54

    def output_test_start(self):
        chk = self.execute_kwp(0x31, [0xB8, 0x00, 0x00])
        if chk and chk[0] == 0x71:
            time.sleep(0.3) 
            return self.execute_kwp(0x31, [0xB8, 0x01, 0x02]) is not None
        return False

    def output_test_next(self):
        self.execute_kwp(0x31, [0xBA, 0x01, 0x02]) 
        time.sleep(0.05)
        return self.execute_kwp(0x31, [0xB9, 0x01, 0x02]) is not None

    def output_test_status(self):
        res = self.execute_kwp(0x31, [0xBA, 0x01, 0x02])
        if res and len(res) >= 4:
            return bytes(res[4:]).hex(' ').upper()
        return None

    def stop_routines(self):
        self.execute_kwp(0x10, [0x81]) 
        time.sleep(0.1)
        self.execute_kwp(0x10, [0x89]) 

    def disconnect(self):
        if self.tx_id != 0:
            self.stop_routines()
            self._send_frame(self.tx_id, [0xA8])
            self.tx_id = 0
            logger.info("TP2.0 Channel Closed.")
