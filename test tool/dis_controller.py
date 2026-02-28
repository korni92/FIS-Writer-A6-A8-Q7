import time
from dis_payload_manager import MMITester, DISPayloadManager   
from can_data_provider import LiveCANDataProvider

class DISController:
    def __init__(self):
        self.driver = MMITester()
        self.driver.other_rx_queue = []
        
        self.original_recv = self.driver._recv_filtered
        self.driver._recv_filtered = self._safe_recv
        self.driver.show_traffic = True          

        self.manager = DISPayloadManager(self.driver)
        self.can_provider = LiveCANDataProvider()

        self.is_updating = False
        self.screen_owned = True
        self.current_source = 0x06 # Default Media
        self.mid_zone_active = False 
        self.nav_mode_active = False 
        
        self.reset_screen_state()

    def start(self):
        print("=== Starting handshake & zone init ===")
        self.driver.perform_handshake()
        self.manager.init_all_zones()

    def _safe_recv(self, timeout):
        start = time.time()
        while time.time() - start < timeout:
            rx = self.driver.bus.recv(timeout=0.01)
            if not rx: continue
            if rx.arbitration_id == 0x491:
                if rx.data and rx.data[0] == 0xA3:
                    self.driver.log_traffic("CLUS -> MMI", "A3", "HEARTBEAT (PING IN)")
                    self.driver.send_raw([0xA1, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF], "HEARTBEAT (PONG)")
                    continue
                return rx
            else:
                self.driver.other_rx_queue.append(rx)
        return None

    def process_messages(self):
        while self.driver.other_rx_queue:
            rx = self.driver.other_rx_queue.pop(0)
            self.can_provider.parse_message(rx)
        try:
            while True:
                rx = self.driver.bus.recv(timeout=0.0)
                if not rx: break
                if rx.arbitration_id == 0x491:
                    if rx.data and rx.data[0] == 0xA3:
                        self.driver.log_traffic("CLUS -> MMI", "A3", "HEARTBEAT (PING IN)")
                        self.driver.send_raw([0xA1, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF], "HEARTBEAT (PONG)")
                    else:
                        self.driver.rx_queue.append(rx)
                else:
                    self.can_provider.parse_message(rx)
        except Exception: 
            pass

    def get_live_value(self, key):
        return self.can_provider.get_value(key)

    def reset_screen_state(self):
        self.screen_state = {
            '01': None, '05': None, '06': None, '07': None, '08': None, '09': None,
            'highlight': None, 'arrows': None
        }
        self.mid_zone_active = False

    def sanitize_text(self, text):
        replacements = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue'}
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text

    def retake_screen(self, target_source=None):
        if target_source: 
            self.current_source = target_source

        if not self.screen_owned or self.nav_mode_active:
            self.manager.switch_source(self.current_source)
            time.sleep(0.05)
            self.manager.claim_zone(0x02)
            time.sleep(0.05)
            self.manager.release_zone(0x02)
            
            self.screen_owned = True
            self.nav_mode_active = False
            self.mid_zone_active = True
            self.reset_screen_state() 

    def release_screen_to_car(self):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.nav_mode_active = False
            self.driver.send_message([0x32, 0x01, 0x02]) 
            time.sleep(0.05)
            self.driver.send_message([0x32, 0x01, 0x01]) 
            self.screen_owned = False
            self.reset_screen_state()
            return True
        finally:
            self.is_updating = False

    def switch_source_manual(self, source_name):
        self.current_source = 0x01 if source_name == "Phone" else 0x06
        if not self.is_updating:
            self.is_updating = True
            try:
                self.manager.switch_source(self.current_source)
                time.sleep(0.05)
                self.manager.claim_zone(0x02)
                time.sleep(0.05)
                self.manager.release_zone(0x02)
                
                self.screen_owned = True
                self.nav_mode_active = False
                self.mid_zone_active = True
                self.reset_screen_state()
            finally:
                self.is_updating = False

    def send_smart_string(self, smart_str):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.retake_screen()
            self.manager.write_smart_string(smart_str)
            self.reset_screen_state()
        finally:
            self.is_updating = False

    def push_update(self, target_state):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.retake_screen()

            clean_state = {}
            for k in ['01', '05', '06', '07', '08', '09']:
                clean_state[k] = self.sanitize_text(target_state.get(k, ""))
            clean_state['highlight'] = target_state.get('highlight', 0)
            clean_state['arrows'] = target_state.get('arrows', 0)

            # --- TOP ZONE (01) ---
            if clean_state['01'] != self.screen_state['01']:
                self.manager.claim_zone(0x01)
                time.sleep(0.05)
                self.manager.write_text(0x01, clean_state['01'])
                time.sleep(0.05)
                self.manager.release_zone(0x01)
                time.sleep(0.05)
                self.screen_state['01'] = clean_state['01']
                self.mid_zone_active = False 

            # --- MID ZONE (05-09) ---
            text_changed = False
            for k in ['05', '06', '07', '08', '09']:
                if clean_state[k] != self.screen_state[k]:
                    text_changed = True
                    break
                    
            highlight_changed = (clean_state['highlight'] != self.screen_state['highlight']) or \
                                (clean_state['arrows'] != self.screen_state['arrows'])

            if text_changed or highlight_changed:
                if not self.mid_zone_active:
                    self.manager.claim_zone(0x02)
                    time.sleep(0.05)
                    force_highlight_resend = True
                else:
                    force_highlight_resend = False
                
                if text_changed:
                    for k in ['05', '06', '07', '08', '09']:
                        if clean_state[k] != self.screen_state[k]:
                            self.manager.write_text(int(k, 16), clean_state[k])
                            time.sleep(0.05)
                            self.screen_state[k] = clean_state[k]
                
                if highlight_changed or force_highlight_resend:
                    self.manager.set_highlight(clean_state['highlight'], clean_state['arrows'], 0x00)
                    time.sleep(0.05)
                    self.screen_state['highlight'] = clean_state['highlight']
                    self.screen_state['arrows'] = clean_state['arrows']
                
                self.manager.release_zone(0x02)
                time.sleep(0.05)
                self.mid_zone_active = True

        finally:
            self.is_updating = False

    # ====================== NAVIGATION / EXPERIMENTAL ======================
    def enter_nav_mode(self):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.manager.claim_zone(0x02)
            time.sleep(0.05)
            self.manager.write_text(0x05, "")
            time.sleep(0.05)
            self.manager.release_zone(0x02)  # FIX: Prevent 0x09 E0 crash!
            time.sleep(0.05)
            
            self.manager.claim_zone(0x03)
            time.sleep(0.05)
            
            # Send blanks to force the transition out of Telephone screen
            self.manager.write_text(0x0C, "")
            time.sleep(0.05)
            self.manager.write_text(0x0B, "")
            time.sleep(0.05)
            
            self.manager.release_zone(0x03)
            
            self.mid_zone_active = False 
            self.nav_mode_active = True
        finally:
            self.is_updating = False

    def exit_nav_mode(self):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.nav_mode_active = False
            self.manager.switch_source(self.current_source)
            time.sleep(0.05)
            self.manager.claim_zone(0x02)
            time.sleep(0.05)
            self.manager.release_zone(0x02)
            self.mid_zone_active = True
            self.reset_screen_state()
        finally:
            self.is_updating = False

    def push_nav_update(self, nav_state):
        if self.is_updating: return
        self.is_updating = True
        try:
            if not self.nav_mode_active:
                self.manager.claim_zone(0x02)
                time.sleep(0.05)
                self.manager.write_text(0x05, "")
                time.sleep(0.05)
                self.manager.release_zone(0x02)  # FIX: Prevent 0x09 E0 crash!
                time.sleep(0.05)
                self.nav_mode_active = True
                
            self.manager.claim_zone(0x03)
            time.sleep(0.05)
                
            for k in ['0A', '0B', '0C', '0D']:
                if k in nav_state and nav_state[k] is not None:
                    clean_text = self.sanitize_text(nav_state[k])
                    self.manager.write_text(int(k, 16), clean_text)
                    time.sleep(0.05)
                    
            if 'bar' in nav_state and nav_state['bar'] is not None:
                self.manager.write_nav_bar(nav_state['bar'])
                time.sleep(0.05)
                
            self.manager.release_zone(0x03)
        finally:
            self.is_updating = False

    def push_nav_arrow(self, line_id, data_str):
        if self.is_updating: return
        self.is_updating = True
        try:
            if not getattr(self, 'nav_mode_active', False):
                self.manager.claim_zone(0x02)
                time.sleep(0.05)
                self.manager.write_text(0x05, "")
                time.sleep(0.05)
                self.manager.release_zone(0x02)  # FIX: Prevent 0x09 E0 crash!
                time.sleep(0.05)
                self.nav_mode_active = True
                
            self.manager.claim_zone(0x03)
            time.sleep(0.05)

            self.manager.draw_arrow(line_id, data_str)
            time.sleep(0.05)
            self.manager.release_zone(0x03)
        finally:
            self.is_updating = False

    def test_34_opcode(self, zone_id):
        if self.is_updating: return
        self.is_updating = True
        try:
            from dis_payload_manager import logger
            logger.info(f"\n>> Sending Experimental Opcode 34 for Zone {zone_id:02X}")
            self.manager.driver.send_message([0x34, 0x01, zone_id])
            self.manager.driver.wait_for_confirmation(zone_id)
        finally:
            self.is_updating = False

    def send_raw_hex(self, hex_str):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.manager.send_raw_payload(hex_str)
        finally:
            self.is_updating = False

    def shutdown(self):
        try: 
            self.driver.bus.shutdown()
        except: 
            pass
