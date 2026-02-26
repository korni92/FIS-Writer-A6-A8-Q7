# ================================================
# AUDI A8 DIS - FULL GRAPHICAL CONTROL PANEL
# Start: dis_tk_gui.py  (same folder as your other files)
# Requires: dis_payload_manager.py, a8_dis_driver.py, can_data_provider.py
# ================================================

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import time
import sys
import os
import math

sys.path.insert(0, os.path.dirname(__file__))
from dis_payload_manager import MMITester, DISPayloadManager   
from can_data_provider import LiveCANDataProvider

class DISGraphicalUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AUDI A8 DIS - Experimental Dashboard & Tester")
        self.root.geometry("1100x900")
        self.root.resizable(True, True)

        # ====================== BACKEND ======================
        self.driver = MMITester()
        self.driver.other_rx_queue = []
        
        # Override driver's receive to preserve Engine CAN data
        original_recv = self.driver._recv_filtered
        def safe_recv(timeout):
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
        self.driver._recv_filtered = safe_recv

        self.driver.show_traffic = True          
        self.manager = DISPayloadManager(self.driver)
        self.can_provider = LiveCANDataProvider()

        self.is_updating = False
        
        # --- Screen Ownership & State Tracking (DELTA UPDATES) ---
        self.screen_owned = True
        self.current_source = 0x01 # Default to Telephone, important to start telephone first
        self.reset_screen_state()

        print("=== Starting handshake & zone init ===")
        self.driver.perform_handshake()
        self.manager.init_all_zones()

        # --- DATA MODELS ---
        
        # 1. LIVE DASHBOARD MODEL
        self.signal_configs = {
            'rpm': {'key': 'rpm', 'short': 'RPM', 'unit': 'U/min', 'name': 'Drehzahl', 'min': 0.0, 'max': 6000.0},
            'oil_temp': {'key': 'oil_temp', 'short': 'Oel', 'unit': 'C', 'name': 'Öltemperatur', 'min': 50.0, 'max': 150.0},
            'boost': {'key': 'boost', 'short': 'Ladedr', 'unit': 'bar', 'name': 'Ladedruck', 'min': 0.0, 'max': 1.5},
            'temp_c': {'key': 'temp_c', 'short': 'AussT', 'unit': 'C', 'name': 'Außentemperatur', 'min': -20.0, 'max': 40.0},
            'pedal': {'key': 'pedal', 'short': 'Gas', 'unit': '%', 'name': 'Gaspedal', 'min': 0.0, 'max': 100.0},
            'torque': {'key': 'torque', 'short': 'Mom', 'unit': '%', 'name': 'Drehmoment', 'min': 0.0, 'max': 500.0},
        }
        
        self.live_items = [
            {'key': 'rpm', 'type': 'text'},
            {'key': 'boost', 'type': 'bar'},
            {'key': 'oil_temp', 'type': 'text'},
            {'key': 'pedal', 'type': 'bar'}
        ]
        self.live_view_start = 0
        self.live_highlight_idx = 0
        self.live_show_cursor = tk.BooleanVar(value=True)
        
        # 2. STATIC MENU MODEL
        self.static_items = ["Option A", "Option B", "Option C", "Option D", "Option E"]   
        self.static_view_start = 0          
        self.static_highlight_idx = 0     
        self.static_show_cursor = tk.BooleanVar(value=True)
        self.static_show_arrows = tk.BooleanVar(value=True)
        
        self.static_top = tk.StringVar(value="Static Menu")
        self.static_head = tk.StringVar(value="Settings")
        self.static_lines = [tk.StringVar() for _ in range(4)]

        # Global Settings
        self.source_var = tk.StringVar(value="Media")
        self.auto_refresh_active = tk.BooleanVar(value=False)
        self.refresh_rate_var = tk.IntVar(value=250) # Can go much faster now because of Deltas!

        # Build GUI
        self.build_ui()
        self.sync_static_lines()          
        self.render_live_screen()             

        self.root.after(30, self.keepalive_loop)
        self.root.after(self.refresh_rate_var.get(), self.auto_refresh_loop)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    # --- STATE TRACKING & SANITIZATION ---
    def reset_screen_state(self):
        """Clears the shadow buffer so the next update forces a full redraw."""
        self.screen_state = {
            '01': None, '05': None, '06': None, '07': None, '08': None, '09': None,
            'highlight': None, 'arrows': None
        }

    def sanitize_text(self, text):
        """Replaces German umlauts and ensures ASCII compliance for the cluster."""
        replacements = {
            'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
            'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue'
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text

    # --- SCREEN OWNERSHIP ---
    def retake_screen(self):
        if not self.screen_owned:
            src = 0x01 if self.source_var.get() == "Phone" else 0x06
            self.manager.switch_source(src)
            time.sleep(0.1)
            self.screen_owned = True
            self.reset_screen_state() # Force full redraw

    def release_screen_to_car(self):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.driver.send_message([0x32, 0x01, 0x02]) 
            time.sleep(0.05)
            self.driver.send_message([0x32, 0x01, 0x01]) 
            self.screen_owned = False
            self.reset_screen_state()
            messagebox.showinfo("Screen Released", "Cluster is back to normal operation.\nIt will be retaken automatically on next Push/Refresh.")
        finally:
            self.is_updating = False

    def manual_source_change(self):
        self.current_source = 0x01 if self.source_var.get() == "Phone" else 0x06
        if not self.is_updating:
            self.is_updating = True
            self.manager.switch_source(self.current_source)
            self.screen_owned = True
            self.reset_screen_state()
            self.is_updating = False

    # --- UI BUILDER (Abridged for space) ---
    def build_ui(self):
        pad = {'padx': 8, 'pady': 5}

        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill="x", **pad)
        
        ttk.Label(top_frame, text="Target Screen (E2):").pack(side=tk.LEFT, **pad)
        ttk.Radiobutton(top_frame, text="Telephone", variable=self.source_var, value="Phone", command=self.manual_source_change).pack(side=tk.LEFT)
        ttk.Radiobutton(top_frame, text="Media", variable=self.source_var, value="Media", command=self.manual_source_change).pack(side=tk.LEFT)
        
        ttk.Button(top_frame, text="🚪 Release Screen to Car (32 01 02)", command=self.release_screen_to_car).pack(side=tk.RIGHT, **pad)
        ttk.Button(top_frame, text="🐞 Toggle CAN Debug", command=self.toggle_debug).pack(side=tk.RIGHT, **pad)

        ctrl_frame = ttk.LabelFrame(self.root, text="Steering Wheel Buttons (Routes to Active Tab)")
        ctrl_frame.pack(fill="x", **pad)
        ttk.Button(ctrl_frame, text="↑ UP", width=15, command=self.btn_up).pack(side=tk.LEFT, **pad)
        ttk.Button(ctrl_frame, text="↓ DOWN", width=15, command=self.btn_down).pack(side=tk.LEFT, **pad)
        ttk.Button(ctrl_frame, text="OK", width=15, command=self.btn_ok).pack(side=tk.LEFT, **pad)
        ttk.Button(ctrl_frame, text="OK Long (Back)", width=15, command=self.btn_back).pack(side=tk.LEFT, **pad)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, **pad)

        self.tab_live = ttk.Frame(self.notebook)
        self.tab_static = ttk.Frame(self.notebook)
        self.tab_raw = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_live, text=" 📊 Live CAN Dashboard ")
        self.notebook.add(self.tab_static, text=" 📝 Static Menu Designer ")
        self.notebook.add(self.tab_raw, text=" 🧪 Raw / Smart String Injector ")

        self.build_tab_live(pad)
        self.build_tab_static(pad)
        self.build_tab_raw(pad)

    def toggle_debug(self):
        self.driver.show_traffic = not self.driver.show_traffic
        print(f"\n--- CAN DEBUG: {'ON' if self.driver.show_traffic else 'OFF'} ---")

    def build_tab_live(self, pad):
        info = ttk.Label(self.tab_live, text="Build a multi-page dynamic dashboard. Top line shows page number. Headline shows cursor item.", foreground="blue")
        info.pack(anchor="w", **pad)

        list_frame = ttk.Frame(self.tab_live)
        list_frame.pack(fill="both", expand=True, **pad)
        
        self.live_listbox = tk.Listbox(list_frame, height=10, font=("Consolas", 12))
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.live_listbox.yview)
        self.live_listbox.configure(yscrollcommand=scroll.set)
        self.live_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        scroll.pack(side=tk.RIGHT, fill="y")

        c_frame = ttk.Frame(self.tab_live)
        c_frame.pack(fill="x", **pad)
        
        ttk.Button(c_frame, text="➕ Add Data Row", command=self.add_live_item).pack(side=tk.LEFT, **pad)
        ttk.Button(c_frame, text="🗑 Delete Selected", command=self.del_live_item).pack(side=tk.LEFT, **pad)
        ttk.Checkbutton(c_frame, text="Show Cursor Header", variable=self.live_show_cursor, command=self.render_live_screen).pack(side=tk.LEFT, padx=20)

        ref_frame = ttk.LabelFrame(self.tab_live, text="Auto Refresh Controls (Only sends changes!)")
        ref_frame.pack(fill="x", **pad)
        ttk.Label(ref_frame, text="Interval (ms):").pack(side=tk.LEFT, **pad)
        ttk.Entry(ref_frame, textvariable=self.refresh_rate_var, width=8).pack(side=tk.LEFT, **pad)
        ttk.Checkbutton(ref_frame, text="ENABLE AUTO REFRESH", variable=self.auto_refresh_active).pack(side=tk.LEFT, **pad)
        ttk.Button(ref_frame, text="🔄 Render Once", command=self.render_live_screen).pack(side=tk.RIGHT, **pad)

        self.refresh_live_listbox()

    def refresh_live_listbox(self):
        self.live_listbox.delete(0, tk.END)
        for i, item in enumerate(self.live_items):
            cfg = self.signal_configs[item['key']]
            display_type = "Progress Bar" if item['type'] == 'bar' else "Text Value"
            self.live_listbox.insert(tk.END, f"{i:02d} | {cfg['name']} -> [{display_type}]")

    def add_live_item(self):
        keys = list(self.signal_configs.keys())
        key = simpledialog.askstring("Add Live Item", f"Type signal key:\n{', '.join(keys)}", initialvalue="rpm")
        if key in keys:
            dtype = simpledialog.askstring("Type", "Format: 'text' or 'bar'", initialvalue="text")
            if dtype in ['text', 'bar']:
                self.live_items.append({'key': key, 'type': dtype})
                self.refresh_live_listbox()

    def del_live_item(self):
        sel = self.live_listbox.curselection()
        if sel:
            del self.live_items[sel[0]]
            self.live_highlight_idx = max(0, min(self.live_highlight_idx, len(self.live_items)-1))
            self.refresh_live_listbox()
            self.render_live_screen()

    def build_tab_static(self, pad):
        ttk.Label(self.tab_static, text="01 Top Line:").pack(anchor="w", **pad)
        ttk.Entry(self.tab_static, textvariable=self.static_top).pack(fill="x", **pad)
        ttk.Label(self.tab_static, text="05 Headline:").pack(anchor="w", **pad)
        ttk.Entry(self.tab_static, textvariable=self.static_head).pack(fill="x", **pad)

        lines_f = ttk.LabelFrame(self.tab_static, text="Editable Viewport (06-09)")
        lines_f.pack(fill="x", **pad)
        for i in range(4):
            ttk.Entry(lines_f, textvariable=self.static_lines[i]).pack(fill="x", **pad)

        self.stat_listbox = tk.Listbox(self.tab_static, height=6)
        self.stat_listbox.pack(fill="both", expand=True, **pad)

        btn_f = ttk.Frame(self.tab_static)
        btn_f.pack(fill="x", **pad)
        ttk.Button(btn_f, text="Add", command=lambda: self.static_items.append("New")).pack(side=tk.LEFT)
        ttk.Checkbutton(btn_f, text="Cursor", variable=self.static_show_cursor).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(btn_f, text="Arrows", variable=self.static_show_arrows).pack(side=tk.LEFT)
        
        ttk.Button(self.tab_static, text="📤 PUSH STATIC DESIGN TO CLUSTER", command=self.update_static_display, style="Accent.TButton").pack(fill="x", pady=10, ipady=10)
        self.refresh_static_listbox()

    def refresh_static_listbox(self):
        self.stat_listbox.delete(0, tk.END)
        for i, t in enumerate(self.static_items):
            self.stat_listbox.insert(tk.END, f"{i:02d} | {t}")

    def sync_static_lines(self):
        for i in range(4):
            idx = self.static_view_start + i
            text = self.static_items[idx] if idx < len(self.static_items) else ""
            self.static_lines[i].set(text)

    def sync_back_static(self):
        for i in range(4):
            idx = self.static_view_start + i
            new_t = self.static_lines[i].get()
            if idx < len(self.static_items): self.static_items[idx] = new_t

    def build_tab_raw(self, pad):
        self.smart_str_var = tk.StringVar(value="01 Radio 05 Setup 06 Audio 07 Display E4 01 00")
        ttk.Label(self.tab_raw, text="Smart String Input (Regex Parser):").pack(anchor="w", **pad)
        ttk.Entry(self.tab_raw, textvariable=self.smart_str_var, font=("Consolas", 12)).pack(fill="x", **pad)
        ttk.Button(self.tab_raw, text="Inject Smart String", command=self.send_smart_str).pack(anchor="w", **pad)

    def send_smart_str(self):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.retake_screen()
            self.manager.write_smart_string(self.smart_str_var.get())
            self.reset_screen_state() # Smart string bypassed our state tracker
        finally:
            self.is_updating = False

    # --- STEERING WHEEL ROUTING ---
    def get_active_tab(self):
        return self.notebook.index(self.notebook.select())

    def btn_up(self):
        tab = self.get_active_tab()
        if tab == 0:
            if self.live_highlight_idx > 0:
                self.live_highlight_idx -= 1
                if self.live_highlight_idx < self.live_view_start:
                    self.live_view_start -= 1
                self.render_live_screen()
        elif tab == 1:
            if self.static_highlight_idx > 0:
                self.static_highlight_idx -= 1
                if self.static_highlight_idx < self.static_view_start:
                    self.static_view_start -= 1
                self.sync_static_lines()
                self.update_static_display()

    def btn_down(self):
        tab = self.get_active_tab()
        if tab == 0:
            if self.live_highlight_idx < len(self.live_items) - 1:
                self.live_highlight_idx += 1
                if self.live_highlight_idx > self.live_view_start + 3:
                    self.live_view_start += 1
                self.render_live_screen()
        elif tab == 1:
            if self.static_highlight_idx < len(self.static_items) - 1:
                self.static_highlight_idx += 1
                if self.static_highlight_idx > self.static_view_start + 3:
                    self.static_view_start += 1
                self.sync_static_lines()
                self.update_static_display()

    def btn_ok(self):
        pass 

    def btn_back(self):
        self.release_screen_to_car()


    # --- RENDERING ENGINES (DELTA OPTIMIZED) ---
    def format_live_item(self, item_cfg):
        key = item_cfg['key']
        val = self.can_provider.get_value(key)
        conf = self.signal_configs[key]
        
        if item_cfg['type'] == 'text':
            if key == 'rpm': return f"{conf['short']} {val:.0f} {conf['unit']}"
            elif key == 'boost': return f"{conf['short']} {val:.2f} {conf['unit']}"
            else: return f"{conf['short']} {val:.1f} {conf['unit']}"
            
        elif item_cfg['type'] == 'bar':
            min_v = conf['min']
            max_v = conf['max']
            pct = max(0.0, min(1.0, (val - min_v) / (max_v - min_v)))
            
            # Safe ASCII Bar: [|||||-----]
            seg = 8
            filled = int(pct * seg)
            bar_str = f"[{'|'*filled}{'-'*(seg-filled)}]"
            
            if key == 'rpm': return f"{bar_str} {val:.0f}"
            elif key == 'boost': return f"{bar_str} {val:.2f}"
            else: return f"{bar_str} {val:.1f}"

    def render_live_screen(self):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.retake_screen()

            # 1. Calculate the New State
            new_state = {}
            
            # Top
            total_pages = max(1, math.ceil(len(self.live_items) / 4))
            current_page = (self.live_view_start // 4) + 1
            new_state['01'] = f"Page {current_page}/{total_pages}"
            
            # Headline
            if self.live_show_cursor.get() and len(self.live_items) > 0:
                active_key = self.live_items[self.live_highlight_idx]['key']
                new_state['05'] = self.signal_configs[active_key]['name']
            else:
                new_state['05'] = "Live CAN Data"
                
            # Lines 06-09
            for i in range(4):
                idx = self.live_view_start + i
                line_id_str = f"0{6+i}"
                if idx < len(self.live_items):
                    text = self.format_live_item(self.live_items[idx])
                    new_state[line_id_str] = text[:16] # Crop to screen limits
                else:
                    new_state[line_id_str] = ""

            # Apply Sanitization
            for k in ['01', '05', '06', '07', '08', '09']:
                new_state[k] = self.sanitize_text(new_state[k])

            # Arrows & Highlight
            arrow = 0
            if self.live_view_start > 0: arrow |= 1
            if self.live_view_start + 4 < len(self.live_items): arrow |= 2
            new_state['arrows'] = arrow

            if self.live_show_cursor.get() and len(self.live_items) > 0:
                rel_slot = self.live_highlight_idx - self.live_view_start + 1 
                new_state['highlight'] = rel_slot if 1 <= rel_slot <= 4 else 0
            else:
                new_state['highlight'] = 0


            # 2. DIFF & TRANSMIT

            # --- TOP ZONE ---
            if new_state['01'] != self.screen_state['01']:
                self.manager.claim_zone(0x01)
                time.sleep(0.05)
                self.manager.write_text(0x01, new_state['01'])
                time.sleep(0.05)
                self.manager.release_zone(0x01)
                time.sleep(0.05)
                self.screen_state['01'] = new_state['01']

            # --- MID ZONE ---
            mid_changed = False
            for k in ['05', '06', '07', '08', '09', 'highlight', 'arrows']:
                if new_state[k] != self.screen_state[k]:
                    mid_changed = True
                    break

            if mid_changed:
                self.manager.claim_zone(0x02)
                time.sleep(0.05)
                
                # Write only the text lines that changed
                for k in ['05', '06', '07', '08', '09']:
                    if new_state[k] != self.screen_state[k]:
                        self.manager.write_text(int(k, 16), new_state[k])
                        time.sleep(0.05)
                        self.screen_state[k] = new_state[k]
                
                # If we claimed the mid zone, always send E4 to ensure cursor doesn't vanish
                self.manager.set_highlight(new_state['highlight'], new_state['arrows'], 0x00)
                time.sleep(0.05)
                self.screen_state['highlight'] = new_state['highlight']
                self.screen_state['arrows'] = new_state['arrows']
                
                self.manager.release_zone(0x02)
                time.sleep(0.05)
                
            self.refresh_live_listbox()
        finally:
            self.is_updating = False

    def update_static_display(self):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.retake_screen()
            self.sync_back_static()

            new_state = {}
            new_state['01'] = self.sanitize_text(self.static_top.get().strip()[:16])
            new_state['05'] = self.sanitize_text(self.static_head.get().strip()[:16])
            
            for i, var in enumerate(self.static_lines):
                new_state[f"0{6+i}"] = self.sanitize_text(var.get().strip()[:16])

            arrow = 0
            if self.static_show_arrows.get():
                if self.static_view_start > 0: arrow |= 1
                if self.static_view_start + 4 < len(self.static_items): arrow |= 2
            new_state['arrows'] = arrow

            if self.static_show_cursor.get() and len(self.static_items) > 0:
                rel = self.static_highlight_idx - self.static_view_start + 1
                new_state['highlight'] = rel if 1 <= rel <= 4 else 0
            else:
                new_state['highlight'] = 0

            # TOP ZONE
            if new_state['01'] != self.screen_state['01']:
                self.manager.claim_zone(0x01)
                time.sleep(0.05)
                self.manager.write_text(0x01, new_state['01'])
                time.sleep(0.05)
                self.manager.release_zone(0x01)
                time.sleep(0.05)
                self.screen_state['01'] = new_state['01']

            # MID ZONE
            mid_changed = False
            for k in ['05', '06', '07', '08', '09', 'highlight', 'arrows']:
                if new_state[k] != self.screen_state[k]:
                    mid_changed = True
                    break

            if mid_changed:
                self.manager.claim_zone(0x02)
                time.sleep(0.05)
                
                for k in ['05', '06', '07', '08', '09']:
                    if new_state[k] != self.screen_state[k]:
                        self.manager.write_text(int(k, 16), new_state[k])
                        time.sleep(0.05)
                        self.screen_state[k] = new_state[k]
                
                self.manager.set_highlight(new_state['highlight'], new_state['arrows'], 0x00)
                time.sleep(0.05)
                self.screen_state['highlight'] = new_state['highlight']
                self.screen_state['arrows'] = new_state['arrows']
                
                self.manager.release_zone(0x02)
                time.sleep(0.05)

            self.refresh_static_listbox()
        finally:
            self.is_updating = False

    # --- BACKGROUND LOOPS ---
    def keepalive_loop(self):
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
        except: pass
        self.root.after(30, self.keepalive_loop)

    def auto_refresh_loop(self):
        try: delay = max(50, int(self.refresh_rate_var.get()))
        except ValueError: delay = 250
            
        if self.auto_refresh_active.get() and not self.is_updating and self.get_active_tab() == 0:
            self.render_live_screen()
                
        self.root.after(delay, self.auto_refresh_loop)

    def on_close(self):
        try: self.driver.bus.shutdown()
        except: pass
        self.root.destroy()

if __name__ == "__main__":
    DISGraphicalUI()
