# main_sim.py
import tkinter as tk
from tkinter import ttk
import time
import logging

from dis_hal import CANDriver, MMIProtocol
from dis_ui import DISDisplayManager
from app_core import GLOBAL_SETTINGS, CONFIG, LIVE_DATA, tr 
from app_launcher import AppLauncher
from app_settings import AppSettings
from app_livedata import AppLiveData
from app_diagnostics_con import DiagnosticsConnection
from app_diagnostics_ui import AppDiagnostics
from symbols import Symbols

logger = logging.getLogger("OS_KERNEL")

class FirmwareOS:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("DIS Firmware Base - MFSW Sim")
        self.root.geometry("450x250")
        
        ttk.Label(self.root, text="A8 DIS OS Running", font=("Helvetica", 12, "bold")).pack(pady=5)
        ttk.Label(self.root, text="[Up/Down Arrow] : Scroll\n[Left / Esc] : MODE Long (Go Back)\n[Enter] : Select / OKAY\n[M] : MODE Short (Open Menu)\n[D] : Toggle Raw CAN Debug Trace").pack(pady=5)

        # --- HARDWARE INIT ---
        self.can_drv = CANDriver()
        
        # Always parse live data in the background to keep RAM fresh
        self.can_drv.register_cluster_callback(LIVE_DATA.parse_message)
        
        # Init Diagnostics Backend
        self.diag_con = DiagnosticsConnection(self.can_drv)
        
        self.mmi = MMIProtocol(self.can_drv)
        self.ui = DISDisplayManager(self.mmi)
        self.can_debug_mode = 0
        self.mmi.show_trace = False
        self.diag_con.show_trace = False

        # --- CLUSTER HANDSHAKE ---
        self.mmi.perform_handshake()
        self.ui.init_zone(0x01)
        self.ui.init_zone(0x02)
        
        theme_hex = 0x01 if CONFIG.get("sys_theme") == 1 else 0x06
        self.ui.switch_source(theme_hex)
        
        # --- APP REGISTRY ---
        # The Launcher automatically generates its menu from this dictionary!
        self.app_registry = {}
        self.app_registry["Launcher"] = AppLauncher(self.ui, self.app_registry)
        self.app_registry["Live Data"] = AppLiveData(self.ui, self.app_registry)
        self.app_registry["Diagnostics"] = AppDiagnostics(self.ui, self.app_registry, self.diag_con)
        self.app_registry["Settings"] = AppSettings(self.ui, self.app_registry)
        
        if CONFIG.get("sys_autostart") == 1:
            self.active_app = self.app_registry["Launcher"]
            self.active_app.on_focus()
            self.active_app.render(force=True)
        else:
            self.active_app = None 

        # --- OS STATE VARIABLES ---
        self.top_line_active = False
        self.last_top_left = ""
        self.last_top_right = ""
        self.last_top_update = 0
        self.os_drawing_paused = False

        # --- EVENT BINDINGS ---
        self.root.bind("<Up>", lambda e: self._route_input("up"))
        self.root.bind("<Down>", lambda e: self._route_input("down"))
        self.root.bind("<Left>", lambda e: self._route_input("back"))
        self.root.bind("<Escape>", lambda e: self._route_input("back")) 
        self.root.bind("<Return>", lambda e: self._route_input("ok"))
        self.root.bind("m", lambda e: self._route_input("mode_short"))
        self.root.bind("d", lambda e: self._toggle_debug())

        self.root.after(10, self.engine_loop)
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
        self.root.mainloop()

    def _toggle_debug(self):
        """Cycles the Raw CAN Debug Trace target"""
        self.can_debug_mode = (self.can_debug_mode + 1) % 4
        modes = ["OFF", "CLUSTER ONLY", "DIAG ECU ONLY", "CLUSTER + DIAG ECU"]
        
        logger.info(f"OS KERNEL: Raw CAN Trace Switched To -> {modes[self.can_debug_mode]}")
        
        self.mmi.show_trace = (self.can_debug_mode in [1, 3])
        self.diag_con.show_trace = (self.can_debug_mode in [2, 3])

    def _route_input(self, action):
        if self.os_drawing_paused: return 

        if action == "mode_short":
            for app in self.app_registry.values(): app.is_active = False
            self.active_app = self.app_registry["Launcher"]
            self.active_app.on_focus()
            self.active_app.render(force=True)
            return

        if self.active_app:
            if action == "up": self.active_app.on_up()
            elif action == "down": self.active_app.on_down()
            elif action == "ok": self.active_app.on_ok()
            elif action == "back": self.active_app.on_back()
            
            currently_active = None
            for name, app in self.app_registry.items():
                if app.is_active:
                    currently_active = app
                    break
            
            if not currently_active:
                if self.active_app.app_name == "Main Menu":
                    self.active_app = None
                    self.ui.stop_zone(0x02) 
                else:
                    self.active_app = self.app_registry["Launcher"]
                    self.active_app.on_focus()
                    self.active_app.render(force=True)
            else:
                self.active_app = currently_active

    def _manage_top_line(self):
        if self.os_drawing_paused:
            return

        # =================================================================
        # CRITICAL HARDWARE PROTECTION:
        # If the Diagnostics app is open, we MUST yield the Top Line to OEM.
        # KWP2000 multi-frame messages cannot be interrupted by background 
        # Zone 0x01 redraws. The bus needs 100% stability.
        # =================================================================
        if self.active_app and self.active_app.app_name == "Diagnostics":
            if self.top_line_active:
                self.ui.stop_zone(0x01) 
                self.top_line_active = False
                self.last_top_left = ""
                self.last_top_right = ""
            return

        mode = CONFIG.get("top_line_mode")
        
        if mode == 1: # Custom Mode Active
            current_time = time.time()
            if current_time - self.last_top_update > 1.0:
                l_idx = CONFIG.get("top_line_left")
                r_idx = CONFIG.get("top_line_right")
                
                keys = LIVE_DATA.get_variable_keys()
                variables = LIVE_DATA.configs.get("variables", {})
                
                l_str = ""
                r_str = ""
                
                if l_idx < len(keys):
                    k = keys[l_idx]
                    val = LIVE_DATA.get_value(k)
                    var_def = variables.get(k, {})
                    unit = var_def.get("unit", "")
                    decs = var_def.get("decimals", 0)
                    l_str = f"{val:.{decs}f} {unit}"
                    
                if r_idx < len(keys):
                    k = keys[r_idx]
                    val = LIVE_DATA.get_value(k)
                    var_def = variables.get(k, {})
                    unit = var_def.get("unit", "")
                    decs = var_def.get("decimals", 0)
                    r_str = f"{val:.{decs}f} {unit}"

                if l_str != self.last_top_left or r_str != self.last_top_right or not self.top_line_active:
                    self.ui.claim_zone(0x01)
                    self.ui.write_line(0x01, "") 
                    self.ui.write_line(0x02, l_str, Symbols.COLOR_HEADER_WHITE)
                    self.ui.write_line(0x04, r_str, Symbols.COLOR_HEADER_WHITE)
                    self.ui.release_zone(0x01)
                    
                    self.last_top_left = l_str
                    self.last_top_right = r_str
                    self.top_line_active = True
                    
                self.last_top_update = current_time

        else: # OEM Mode Active
            if self.top_line_active:
                self.ui.stop_zone(0x01) 
                self.top_line_active = False
                self.last_top_left = ""
                self.last_top_right = ""

    def engine_loop(self):
        self.can_drv.poll()
        
        current_theme = CONFIG.get("sys_theme")
        if not hasattr(self, 'last_theme'): self.last_theme = current_theme
        
        # --- VIRTUAL COCKPIT TRANSITION SEQUENCE ---
        if current_theme != self.last_theme:
            logger.info("OS KERNEL: Virtual Cockpit Transition Initiated...")
            self.last_theme = current_theme
            
            # 1. Engage Global Drawing Pause
            self.os_drawing_paused = True
            
            # 2. Draw the "Switching Theme" Loading Screen
            self.ui.claim_zone(0x02)
            self.ui.write_line(0x05, " ") 
            self.ui.write_line(0x06, f"  {tr('Switching')}...", Symbols.COLOR_BODY_WHITE, force=True)
            self.ui.write_line(0x07, f"  {tr('Theme')}", Symbols.COLOR_BODY_WHITE, force=True)
            self.ui.write_line(0x08, " ")
            self.ui.write_line(0x09, " ")
            self.ui.set_highlight(0, 0, force=True) 
            self.ui.release_zone(0x02)
            
            # 3. Yield Top Line quietly
            if self.top_line_active:
                self.ui.stop_zone(0x01)
                self.top_line_active = False
                
            # Allow User to read text & Hardware to settle
            for _ in range(8):
                self.can_drv.poll()
                time.sleep(0.1)
                
            # 4. Execute the hardware color swap
            theme_hex = 0x01 if current_theme == 1 else 0x06
            self.ui.switch_source(theme_hex)
            
            # 5. Dummy flush the hardware pipeline
            self.ui.claim_zone(0x02)
            self.ui.release_zone(0x02)
            
            for _ in range(5):
                self.can_drv.poll()
                time.sleep(0.1)
                
            # 6. Reset caches and Resume
            self.ui.screen_cache.clear()
            self.last_top_left = ""
            self.os_drawing_paused = False
            
            if self.active_app:
                self.active_app.render(force=True)

        if self.active_app and not self.os_drawing_paused:
            self.active_app.on_tick()
            
        self._manage_top_line()
            
        self.root.after(10, self.engine_loop)

    def shutdown(self):
        self.can_drv.shutdown()
        self.root.destroy()

if __name__ == "__main__":
    FirmwareOS()
