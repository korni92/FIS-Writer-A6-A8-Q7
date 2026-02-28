import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import math
from dis_controller import DISController
from nav_arrows import KNOWN_ARROWS

class DISGraphicalUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AUDI A8 DIS - Experimental Dashboard & Tester")
        self.root.geometry("1100x950")
        self.root.resizable(True, True)

        self.controller = DISController()
        self.controller.start()

        # ====================== DATA MODELS ======================
        self.signal_configs = {
            'rpm': {'key': 'rpm', 'short': 'RPM', 'unit': 'U/min', 'name': 'Drehzahl', 'min': 0.0, 'max': 6000.0},
            'oil_temp': {'key': 'oil_temp', 'short': 'Oel', 'unit': 'C', 'name': 'Öltemperatur', 'min': 50.0, 'max': 150.0},
            'boost': {'key': 'boost', 'short': 'Ladedr', 'unit': 'bar', 'name': 'Ladedruck', 'min': 0.0, 'max': 1.5},
            'temp_c': {'key': 'temp_c', 'short': 'AussT', 'unit': 'C', 'name': 'Außentemperatur', 'min': -20.0, 'max': 40.0},
            'pedal': {'key': 'pedal', 'short': 'Gas', 'unit': '%', 'name': 'Gaspedal', 'min': 0.0, 'max': 100.0},
            'torque': {'key': 'torque', 'short': 'Mom', 'unit': '%', 'name': 'Drehmoment', 'min': 0.0, 'max': 500.0},
        }
        
        self.live_items = [{'key': 'rpm', 'type': 'text'}, {'key': 'boost', 'type': 'bar'}, {'key': 'oil_temp', 'type': 'text'}]
        self.live_view_start = 0
        self.live_highlight_idx = 0
        self.live_show_cursor = tk.BooleanVar(value=True)
        
        self.static_items = ["Option A", "Option B", "Option C"]   
        self.static_view_start = 0          
        self.static_highlight_idx = 0     
        self.static_show_cursor = tk.BooleanVar(value=True)
        self.static_show_arrows = tk.BooleanVar(value=True)
        
        self.static_top = tk.StringVar(value="Static Menu")
        self.static_head = tk.StringVar(value="Settings")
        self.static_lines = [tk.StringVar() for _ in range(4)]

        # Nav Models
        self.nav_0a = tk.StringVar(value="Experimental Nav")
        self.nav_0b = tk.StringVar(value="Top Left")
        self.nav_0c = tk.StringVar(value="Bot Left")
        self.nav_0d = tk.StringVar(value="") 
        self.nav_bar_val = tk.IntVar(value=0)
        self.raw_hex_var = tk.StringVar(value="34 01 03")

        self.source_var = tk.StringVar(value="Media")
        self.auto_refresh_active = tk.BooleanVar(value=False)
        self.refresh_rate_var = tk.IntVar(value=100) 

        self.build_ui()
        self.sync_static_lines()          
        self.render_live_screen()              

        self.root.after(30, self.keepalive_loop)
        self.root.after(self.refresh_rate_var.get(), self.auto_refresh_loop)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    # ====================== UI BUILDER ======================
    def build_ui(self):
        pad = {'padx': 8, 'pady': 5}

        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill="x", **pad)
        
        ttk.Label(top_frame, text="Target Screen (E2):").pack(side=tk.LEFT, **pad)
        ttk.Radiobutton(top_frame, text="Telephone", variable=self.source_var, value="Phone", command=self.manual_source_change).pack(side=tk.LEFT)
        ttk.Radiobutton(top_frame, text="Media", variable=self.source_var, value="Media", command=self.manual_source_change).pack(side=tk.LEFT)
        
        ttk.Button(top_frame, text="🚪 Release Screen", command=self.release_screen_to_car).pack(side=tk.RIGHT, **pad)
        ttk.Button(top_frame, text="🐞 Toggle CAN Debug", command=self.toggle_debug).pack(side=tk.RIGHT, **pad)

        ctrl_frame = ttk.LabelFrame(self.root, text="Steering Wheel Buttons (Routes to Active Tab)")
        ctrl_frame.pack(fill="x", **pad)
        ttk.Button(ctrl_frame, text="↑ UP", width=15, command=self.btn_up).pack(side=tk.LEFT, **pad)
        ttk.Button(ctrl_frame, text="↓ DOWN", width=15, command=self.btn_down).pack(side=tk.LEFT, **pad)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, **pad)

        self.tab_live = ttk.Frame(self.notebook)
        self.tab_static = ttk.Frame(self.notebook)
        self.tab_nav = ttk.Frame(self.notebook)
        self.tab_raw = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_live, text=" 📊 Live Dashboard ")
        self.notebook.add(self.tab_static, text=" 📝 Static Menu ")
        self.notebook.add(self.tab_nav, text=" 🗺️ Navigation / Experim ")
        self.notebook.add(self.tab_raw, text=" 🧪 Smart String ")

        self.build_tab_live(pad)
        self.build_tab_static(pad)
        self.build_tab_nav(pad)
        self.build_tab_raw(pad)

    def build_tab_live(self, pad):
        list_frame = ttk.Frame(self.tab_live)
        list_frame.pack(fill="both", expand=True, **pad)
        self.live_listbox = tk.Listbox(list_frame, height=10, font=("Consolas", 12))
        self.live_listbox.pack(side=tk.LEFT, fill="both", expand=True)

        c_frame = ttk.Frame(self.tab_live)
        c_frame.pack(fill="x", **pad)
        ttk.Button(c_frame, text="➕ Add", command=self.add_live_item).pack(side=tk.LEFT, **pad)
        ttk.Button(c_frame, text="🗑 Delete", command=self.del_live_item).pack(side=tk.LEFT, **pad)
        ttk.Checkbutton(c_frame, text="Cursor Header", variable=self.live_show_cursor, command=self.render_live_screen).pack(side=tk.LEFT, padx=20)

        ref_frame = ttk.LabelFrame(self.tab_live, text="Auto Refresh")
        ref_frame.pack(fill="x", **pad)
        ttk.Label(ref_frame, text="Interval (ms):").pack(side=tk.LEFT, **pad)
        ttk.Entry(ref_frame, textvariable=self.refresh_rate_var, width=8).pack(side=tk.LEFT, **pad)
        ttk.Checkbutton(ref_frame, text="ENABLE", variable=self.auto_refresh_active).pack(side=tk.LEFT, **pad)
        self.refresh_live_listbox()

    def build_tab_static(self, pad):
        ttk.Label(self.tab_static, text="01 Top Line:").pack(anchor="w", **pad)
        ttk.Entry(self.tab_static, textvariable=self.static_top).pack(fill="x", **pad)
        ttk.Label(self.tab_static, text="05 Headline:").pack(anchor="w", **pad)
        ttk.Entry(self.tab_static, textvariable=self.static_head).pack(fill="x", **pad)

        lines_f = ttk.LabelFrame(self.tab_static, text="Viewport (06-09)")
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
        ttk.Button(self.tab_static, text="📤 PUSH STATIC", command=self.update_static_display).pack(fill="x", pady=10)
        self.refresh_static_listbox()

    def build_tab_nav(self, pad):
        ctrl_f = ttk.LabelFrame(self.tab_nav, text="Zone Claiming & Tests")
        ctrl_f.pack(fill="x", **pad)
        ttk.Button(ctrl_f, text="🗺️ Enter Nav (Claim 0x03)", command=self.controller.enter_nav_mode).pack(side=tk.LEFT, **pad)
        ttk.Button(ctrl_f, text="🔙 Exit Nav (Reclaim 0x02)", command=self.controller.exit_nav_mode).pack(side=tk.LEFT, **pad)
        ttk.Button(ctrl_f, text="🧪 Test 34 01 03", command=lambda: self.controller.test_34_opcode(0x03)).pack(side=tk.LEFT, padx=10, pady=pad['pady'])

        txt_f = ttk.LabelFrame(self.tab_nav, text="Nav Text Fields")
        txt_f.pack(fill="x", **pad)
        
        ttk.Label(txt_f, text="0A (Headline):").grid(row=0, column=0, sticky='e', **pad)
        ttk.Entry(txt_f, textvariable=self.nav_0a, width=30).grid(row=0, column=1, **pad)
        
        ttk.Label(txt_f, text="0B (Top Left):").grid(row=1, column=0, sticky='e', **pad)
        ttk.Entry(txt_f, textvariable=self.nav_0b, width=30).grid(row=1, column=1, **pad)
        
        ttk.Label(txt_f, text="0C (Bot Left):").grid(row=2, column=0, sticky='e', **pad)
        ttk.Entry(txt_f, textvariable=self.nav_0c, width=30).grid(row=2, column=1, **pad)
        
        ttk.Label(txt_f, text="0D (Bot Right):").grid(row=3, column=0, sticky='e', **pad)
        ttk.Entry(txt_f, textvariable=self.nav_0d, width=30).grid(row=3, column=1, **pad)

        ttk.Button(txt_f, text="📤 PUSH TEXT TO NAV", command=self.push_nav_text).grid(row=4, column=0, columnspan=2, pady=10)

        # ====== UPGRADED ARROW GENERATOR UI ======
        arr_f = ttk.LabelFrame(self.tab_nav, text="Nav Arrows Library & Auto-Scanner")
        arr_f.pack(fill="x", **pad)
        
        # Row 0: Dictionary Loader
        ttk.Label(arr_f, text="Library:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.known_arrow_var = tk.StringVar()
        self.known_arrow_cb = ttk.Combobox(arr_f, textvariable=self.known_arrow_var, width=50)
        self.known_arrow_cb.grid(row=0, column=1, columnspan=5, sticky='w', padx=5, pady=5)
        self.known_arrow_cb.bind("<<ComboboxSelected>>", self.load_known_arrow)
        
        # Populate Combobox from nav_arrows.py
        known_list = []
        for grp, items in KNOWN_ARROWS.items():
            for hex_val, desc in items.items():
                known_list.append(f"{grp} | {hex_val} | {desc}")
        self.known_arrow_cb['values'] = known_list

        # Row 1: Manual Controls
        ttk.Label(arr_f, text="Group:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.nav_arrow_line = tk.StringVar(value="0A")
        ttk.Combobox(arr_f, textvariable=self.nav_arrow_line, values=["0A", "0B", "0C", "0D", "0E", "0F"], width=5).grid(row=1, column=1, sticky='w', padx=5, pady=5)
        
        ttk.Label(arr_f, text="Data (Hex):").grid(row=1, column=2, sticky='e', padx=5, pady=5)
        self.nav_arrow_data = tk.StringVar(value="00 00")
        ttk.Entry(arr_f, textvariable=self.nav_arrow_data, width=15).grid(row=1, column=3, sticky='w', padx=5, pady=5)
        
        ttk.Button(arr_f, text="◀ Prev", command=lambda: self.arrow_step(-1)).grid(row=1, column=4, padx=2, pady=5)
        ttk.Button(arr_f, text="Draw Arrow", command=self.push_nav_arrow).grid(row=1, column=5, padx=2, pady=5)
        ttk.Button(arr_f, text="Next ▶", command=lambda: self.arrow_step(1)).grid(row=1, column=6, padx=2, pady=5)

        # Row 2: Auto Scanner & Step Logic
        self.auto_scan_active = tk.BooleanVar(value=False)
        self.scan_interval = tk.StringVar(value="500")
        self.nav_arrow_step = tk.StringVar(value="1") 
        
        ttk.Label(arr_f, text="Step (Hex):").grid(row=2, column=2, sticky='e', padx=5, pady=5)
        ttk.Entry(arr_f, textvariable=self.nav_arrow_step, width=8).grid(row=2, column=3, sticky='w', padx=5, pady=5)
        
        ttk.Checkbutton(arr_f, text="Auto-Scan (ms):", variable=self.auto_scan_active, command=self.toggle_auto_scan).grid(row=2, column=4, columnspan=2, sticky='e', padx=5, pady=5)
        ttk.Entry(arr_f, textvariable=self.scan_interval, width=8).grid(row=2, column=6, sticky='w', padx=5, pady=5)

        # ====================================

        bar_f = ttk.LabelFrame(self.tab_nav, text="Turn Bar (0xDE) Status")
        bar_f.pack(fill="x", **pad)
        ttk.Scale(bar_f, from_=0, to=249, variable=self.nav_bar_val, orient='horizontal').pack(side=tk.LEFT, fill="x", expand=True, **pad)
        ttk.Button(bar_f, text="Draw Bar", command=self.push_nav_bar).pack(side=tk.LEFT, **pad)
        ttk.Button(bar_f, text="Hide Bar", command=self.hide_nav_bar).pack(side=tk.LEFT, **pad)

        raw_f = ttk.LabelFrame(self.tab_nav, text="Raw Command Injector (Free Hex Entry)")
        raw_f.pack(fill="x", **pad)
        ttk.Entry(raw_f, textvariable=self.raw_hex_var, font=("Consolas", 12)).pack(side=tk.LEFT, fill="x", expand=True, **pad)
        ttk.Button(raw_f, text="Send Raw Byte Sequence", command=self.send_raw_command).pack(side=tk.LEFT, **pad)

    def build_tab_raw(self, pad):
        self.smart_str_var = tk.StringVar(value="01 Radio 05 Setup 06 Audio 07 Display E4 01 00")
        ttk.Label(self.tab_raw, text="Smart String Input:").pack(anchor="w", **pad)
        ttk.Entry(self.tab_raw, textvariable=self.smart_str_var, font=("Consolas", 12)).pack(fill="x", **pad)
        ttk.Button(self.tab_raw, text="Inject Smart String", command=lambda: self.controller.send_smart_string(self.smart_str_var.get())).pack(anchor="w", **pad)

    # ====================== DATA BINDINGS ======================
    
    # --- Multi-Byte Arrow Library & Scanner Methods ---
    def load_known_arrow(self, event=None):
        sel = self.known_arrow_var.get()
        if sel:
            parts = sel.split(" | ")
            if len(parts) >= 2:
                self.nav_arrow_line.set(parts[0])
                self.nav_arrow_data.set(parts[1])
                self.push_nav_arrow()

    def arrow_step(self, direction):
        """Treats the entire space-separated hex string as a single large number and steps it."""
        data_str = self.nav_arrow_data.get().strip()
        step_str = self.nav_arrow_step.get().strip()
        
        # Remove spaces to calculate as one continuous integer
        clean_data = data_str.replace(" ", "")
        if not clean_data:
            clean_data = "00"
            
        try:
            current_val = int(clean_data, 16)
            step_val = int(step_str, 16) if step_str else 1
            
            # Determine how many bytes we are working with to handle wrapping
            byte_length = len(clean_data) // 2
            if len(clean_data) % 2 != 0:
                byte_length += 1
                
            max_val = (1 << (byte_length * 8)) - 1 # e.g. 2 bytes = 0xFFFF
            
            # Add or subtract the step
            new_val = current_val + (direction * step_val)
            
            # Wrap around cleanly (e.g. 0000 - 1 = FFFF)
            new_val = new_val % (max_val + 1)
                
            # Format back to hex with leading zeros
            new_hex = f"{new_val:0{byte_length * 2}X}"
            
            # Re-insert spaces
            formatted_hex = " ".join(new_hex[i:i+2] for i in range(0, len(new_hex), 2))
            
            self.nav_arrow_data.set(formatted_hex)
            self.push_nav_arrow()
        except ValueError:
            pass # Ignore if user typed invalid text

    def toggle_auto_scan(self):
        if self.auto_scan_active.get():
            self.auto_scan_loop()

    def auto_scan_loop(self):
        if self.auto_scan_active.get():
            self.arrow_step(1)
            try:
                interval = int(self.scan_interval.get())
            except ValueError:
                interval = 500
            self.root.after(interval, self.auto_scan_loop)
    # ---------------------------------------

    def push_nav_text(self):
        state = {
            '0A': self.nav_0a.get(),
            '0B': self.nav_0b.get(),
            '0C': self.nav_0c.get(),
            '0D': self.nav_0d.get()
        }
        self.controller.push_nav_update(state)

    def push_nav_bar(self):
        state = {'0D': "", 'bar': self.nav_bar_val.get()}
        self.controller.push_nav_update(state)

    def hide_nav_bar(self):
        state = {'0D': "", 'bar': -1}
        self.controller.push_nav_update(state)

    def push_nav_arrow(self):
        line_hex = int(self.nav_arrow_line.get(), 16)
        data_str = self.nav_arrow_data.get()
        self.controller.push_nav_arrow(line_hex, data_str)

    def send_raw_command(self):
        self.controller.send_raw_hex(self.raw_hex_var.get())

    def toggle_debug(self):
        self.controller.driver.show_traffic = not self.controller.driver.show_traffic
        print(f"\n--- CAN DEBUG: {'ON' if self.controller.driver.show_traffic else 'OFF'} ---")

    def release_screen_to_car(self):
        self.controller.release_screen_to_car()

    def manual_source_change(self):
        self.controller.switch_source_manual(self.source_var.get())

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

    def refresh_live_listbox(self):
        self.live_listbox.delete(0, tk.END)
        for i, item in enumerate(self.live_items):
            cfg = self.signal_configs[item['key']]
            display_type = "Progress Bar" if item['type'] == 'bar' else "Text Value"
            self.live_listbox.insert(tk.END, f"{i:02d} | {cfg['name']} -> [{display_type}]")

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

    def get_active_tab(self):
        return self.notebook.index(self.notebook.select())

    def btn_up(self):
        tab = self.get_active_tab()
        if tab == 0 and self.live_highlight_idx > 0:
            self.live_highlight_idx -= 1
            if self.live_highlight_idx < self.live_view_start: self.live_view_start -= 1
            self.render_live_screen()
        elif tab == 1 and self.static_highlight_idx > 0:
            self.static_highlight_idx -= 1
            if self.static_highlight_idx < self.static_view_start: self.static_view_start -= 1
            self.sync_static_lines()
            self.update_static_display()

    def btn_down(self):
        tab = self.get_active_tab()
        if tab == 0 and self.live_highlight_idx < len(self.live_items) - 1:
            self.live_highlight_idx += 1
            if self.live_highlight_idx > self.live_view_start + 3: self.live_view_start += 1
            self.render_live_screen()
        elif tab == 1 and self.static_highlight_idx < len(self.static_items) - 1:
            self.static_highlight_idx += 1
            if self.static_highlight_idx > self.static_view_start + 3: self.static_view_start += 1
            self.sync_static_lines()
            self.update_static_display()

    def format_live_item(self, item_cfg):
        key = item_cfg['key']
        val = self.controller.get_live_value(key) 
        conf = self.signal_configs[key]
        
        if item_cfg['type'] == 'text':
            if key == 'rpm': return f"{conf['short']} {val:.0f} {conf['unit']}"
            elif key == 'boost': return f"{conf['short']} {val:.2f} {conf['unit']}"
            else: return f"{conf['short']} {val:.1f} {conf['unit']}"
            
        elif item_cfg['type'] == 'bar':
            min_v, max_v = conf['min'], conf['max']
            pct = max(0.0, min(1.0, (val - min_v) / (max_v - min_v)))
            filled = int(pct * 8)
            bar_str = f"[{'|'*filled}{'-'*(8-filled)}]"
            
            if key == 'rpm': return f"{bar_str} {val:.0f}"
            elif key == 'boost': return f"{bar_str} {val:.2f}"
            else: return f"{bar_str} {val:.1f}"

    def render_live_screen(self):
        new_state = {}
        total_pages = max(1, math.ceil(len(self.live_items) / 4))
        current_page = (self.live_view_start // 4) + 1
        new_state['01'] = f"Page {current_page}/{total_pages}"
        
        if self.live_show_cursor.get() and len(self.live_items) > 0:
            active_key = self.live_items[self.live_highlight_idx]['key']
            new_state['05'] = self.signal_configs[active_key]['name']
        else:
            new_state['05'] = "Live CAN Data"
            
        for i in range(4):
            idx = self.live_view_start + i
            line_id_str = f"0{6+i}"
            if idx < len(self.live_items):
                new_state[line_id_str] = self.format_live_item(self.live_items[idx])[:16] 
            else:
                new_state[line_id_str] = ""

        arrow = 0
        if self.live_view_start > 0: arrow |= 1
        if self.live_view_start + 4 < len(self.live_items): arrow |= 2
        new_state['arrows'] = arrow

        if self.live_show_cursor.get() and len(self.live_items) > 0:
            rel_slot = self.live_highlight_idx - self.live_view_start + 1 
            new_state['highlight'] = rel_slot if 1 <= rel_slot <= 4 else 0
        else:
            new_state['highlight'] = 0

        self.controller.push_update(new_state)
        self.refresh_live_listbox()

    def update_static_display(self):
        self.sync_back_static()
        new_state = {}
        new_state['01'] = self.static_top.get().strip()[:16]
        new_state['05'] = self.static_head.get().strip()[:16]
        for i, var in enumerate(self.static_lines):
            new_state[f"0{6+i}"] = var.get().strip()[:16]

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

        self.controller.push_update(new_state)
        self.refresh_static_listbox()

    def keepalive_loop(self):
        self.controller.process_messages()
        self.root.after(30, self.keepalive_loop)

    def auto_refresh_loop(self):
        try: delay = max(50, int(self.refresh_rate_var.get()))
        except ValueError: delay = 250
            
        if self.auto_refresh_active.get() and self.get_active_tab() == 0:
            self.render_live_screen()
                
        self.root.after(delay, self.auto_refresh_loop)

    def on_close(self):
        self.controller.shutdown()
        self.root.destroy()

if __name__ == "__main__":
    DISGraphicalUI()
