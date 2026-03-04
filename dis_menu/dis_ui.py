# dis_ui.py
import time
import logging

logger = logging.getLogger("DIS_UI")

class DISDisplayManager:
    """Layer 3: Zone Management & UI Engine"""
    def __init__(self, mmi_protocol):
        self.mmi = mmi_protocol
        self.screen_cache = {}

    def init_zone(self, zone_id):
        logger.info(f"Initializing Zone 0x{zone_id:02X}")
        self.mmi.send_multi_frame([0x30, 0x01, zone_id])
        self.mmi.wait_for_cluster_message(timeout=2.0)

    def claim_zone(self, zone_id):
        logger.info(f"Claiming Zone 0x{zone_id:02X}")
        self.mmi.send_multi_frame([0x36, 0x01, zone_id])

    def release_zone(self, zone_id):
        logger.info(f"Releasing/Committing Zone 0x{zone_id:02X}")
        for _ in range(6): 
            if self.mmi.send_multi_frame([0x32, 0x01, zone_id]):
                status = self.mmi.wait_for_confirmation(zone_id)
                if status == 'SUCCESS': 
                    logger.info(f"Zone 0x{zone_id:02X} Update Confirmed by Cluster!")
                    return True
                elif status == 'BUSY': 
                    logger.warning(f"Cluster Busy. Retrying release of 0x{zone_id:02X}...")
                    time.sleep(2.0)
                elif status == 'FREE': 
                    time.sleep(0.5)
        logger.error(f"Failed to release Zone 0x{zone_id:02X}")
        return False

    def stop_zone(self, zone_id):
        logger.info(f"Stopping Zone 0x{zone_id:02X} (Returning to OEM)")
        self.mmi.send_multi_frame([0x34, 0x01, zone_id])
        self.mmi.wait_for_confirmation(zone_id)

    def switch_source(self, source_hex):
        logger.info(f"Switching Source to 0x{source_hex:02X}")
        self.mmi.send_multi_frame([0xE2, 0x01, source_hex])
        
    def switch_source_and_rebuild(self, source_hex):
        """Forces the cluster to clear its state and redraws completely."""
        logger.info(f"HARD RESET: Switching Source to 0x{source_hex:02X}")
        
        # 1. KILL EVERYTHING: Free up the cluster's rendering pipeline
        self.stop_zone(0x01)
        self.stop_zone(0x02)
        
        # 2. Switch Theme now that the pipeline is idle
        self.mmi.send_multi_frame([0xE2, 0x01, source_hex])
        
        # 3. Dummy Claim & Release to flush the hardware buffer
        self.mmi.send_multi_frame([0x36, 0x01, 0x02]) 
        self.release_zone(0x02) 
        
        # 4. Give the cluster a long pause to execute the color shift
        time.sleep(1.0) 
        
        # 5. Destroy the Python cache so everything redraws from scratch
        self.screen_cache.clear()
        logger.info("HARD RESET Complete. Handing control back to OS.")
    
    def _compile_to_bytes(self, payload):
        if isinstance(payload, list): return payload
        if isinstance(payload, str): return list(payload.encode('cp1252', errors='replace'))
        return []

    def write_line(self, line_id, payload, color=0x00, force=False):
        b_data = self._compile_to_bytes(payload)
        cache_key = f"{line_id}_{color}_{b_data}"
        
        if not force and self.screen_cache.get(line_id) == cache_key:
            return False 
            
        debug_str = "".join([chr(b) if 32 <= b <= 126 else f"[{b:02X}]" for b in b_data])
        logger.info(f"Writing Line 0x{line_id:02X} (Color {color}): {debug_str}")
            
        length = 0x02 + len(b_data)
        can_payload = [0xE0, length, line_id, color] + b_data
        
        self.mmi.send_multi_frame(can_payload)
        self.screen_cache[line_id] = cache_key
        return True 

    def set_highlight(self, line_id, arrow_cfg=0x00, force=False):
        cache_key = f"hl_{line_id}_{arrow_cfg}"
        if not force and self.screen_cache.get('highlight') == cache_key:
            return False
            
        logger.info(f"Setting Highlight Indicator: Line {line_id}, Arrows: 0x{arrow_cfg:02X}")
        self.mmi.send_multi_frame([0xE4, 0x02, line_id, arrow_cfg])
        self.screen_cache['highlight'] = cache_key
        return True
