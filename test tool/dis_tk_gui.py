# ================================================
# AUDI A8 DIS - FULL GRAPHICAL CONTROL PANEL
# Start: dis_tk_gui.py  (same folder as your other files)
# Requires the FIXED versions of:
#   dis_payload_manager.py   (with the 3-param set_highlight + 0x09 error handling)
#   a8_dis_driver.py         (or the MMITester from dis_payload_manager)
# ================================================

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import time
import sys
import os

# Import the fixed classes (use the latest fixed dis_payload_manager)
sys.path.insert(0, os.path.dirname(__file__))
from dis_payload_manager import MMITester, DISPayloadManager   # <-- fixed version with your E4 improvements

class DISGraphicalUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AUDI A8 DIS - Steering Wheel Simulator")
        self.root.geometry("820x720")
        self.root.resizable(True, True)

        # backend
        self.driver = MMITester()
        self.driver.show_traffic = True          # set False for clean UI
        self.manager = DISPayloadManager(self.driver)

        print("=== Starting handshake & zone init ===")
        self.driver.perform_handshake()
        self.manager.init_all_zones()

        # data model
        self.menu_items = ["Option A", "Option B", "Option C", "Option D", 
                          "Option E", "Option F", "Option G", "Option H"]   # default list
        self.view_start = 0          # which item is in line 06
        self.highlight_index = 0     # global item index (cursor position)

        # tk var
        self.source_var = tk.StringVar(value="Media")
        self.top_var = tk.StringVar(value="Test OP Highlight")
        self.head_var = tk.StringVar(value="Headlinebar")
        self.line_vars = [tk.StringVar() for _ in range(4)]   # 06,07,08,09
        self.show_cursor_var = tk.BooleanVar(value=True)

        # build ui
        self.build_ui()
        self.sync_visible_lines()          # fill the 4 visible entries
        self.update_display()              # initial render on cluster

        # Background CAN keep-alive (heartbeats + ACKs)
        self.root.after(30, self.keepalive_loop)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def build_ui(self):
        pad = {'padx': 8, 'pady': 4}

        # source selector
        src_frame = ttk.LabelFrame(self.root, text=" Menu Source (E2) ")
        src_frame.pack(fill="x", **pad)
        ttk.Radiobutton(src_frame, text="📱 Telephone", variable=self.source_var, 
                       value="Phone", command=self.change_source).pack(side=tk.LEFT, **pad)
        ttk.Radiobutton(src_frame, text="🎵 Media", variable=self.source_var, 
                       value="Media", command=self.change_source).pack(side=tk.LEFT, **pad)

        # TOP LINE (Zone 01)
        ttk.Label(self.root, text="01 Top Line").pack(anchor="w", **pad)
        ttk.Entry(self.root, textvariable=self.top_var, width=80).pack(fill="x", **pad)

        # HEADLINE (05)
        ttk.Label(self.root, text="05 Headline").pack(anchor="w", **pad)
        ttk.Entry(self.root, textvariable=self.head_var, width=80).pack(fill="x", **pad)

        # VISIBLE 4 LINES (06-09)
        lines_frame = ttk.LabelFrame(self.root, text="Visible Lines on Cluster (always 06-09)")
        lines_frame.pack(fill="x", **pad)
        for i, label in enumerate(["06 Line 1", "07 Line 2", "08 Line 3", "09 Line 4"]):
            ttk.Label(lines_frame, text=label).grid(row=i, column=0, sticky="w", **pad)
            ttk.Entry(lines_frame, textvariable=self.line_vars[i], width=70).grid(row=i, column=1, sticky="ew", **pad)
        lines_frame.columnconfigure(1, weight=1)

        # menu items
        list_frame = ttk.LabelFrame(self.root, text="Full Menu Items (scroll with UP/DOWN - more than 4 = arrows)")
        list_frame.pack(fill="both", expand=True, **pad)

        self.listbox = tk.Listbox(list_frame, height=12, font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)

        self.listbox.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.pack(side=tk.RIGHT, fill="y")

        self.listbox.bind("<Double-Button-1>", self.edit_list_item)

        btn_list = ttk.Frame(list_frame)
        ttk.Button(btn_list, text="➕ Add Item", command=self.add_item).pack(side=tk.LEFT, **pad)
        ttk.Button(btn_list, text="🗑 Delete Selected", command=self.delete_item).pack(side=tk.LEFT, **pad)
        ttk.Button(btn_list, text="Clear All Items", command=self.clear_all_items).pack(side=tk.LEFT, **pad)
        btn_list.pack()

        # control buttons (from steering wheel)
        ctrl_frame = ttk.LabelFrame(self.root, text="Steering Wheel Buttons")
        ctrl_frame.pack(fill="x", **pad)

        ttk.Button(ctrl_frame, text="↑ UP", width=12, command=self.btn_up).grid(row=0, column=0, **pad)
        ttk.Button(ctrl_frame, text="↓ DOWN", width=12, command=self.btn_down).grid(row=0, column=1, **pad)
        ttk.Button(ctrl_frame, text="OK", width=12, command=self.btn_ok).grid(row=0, column=2, **pad)
        ttk.Button(ctrl_frame, text="OK Long (Back)", width=15, command=self.btn_back).grid(row=0, column=3, **pad)

        # Cursor checkbox
        ttk.Checkbutton(ctrl_frame, text="Show Highlight Cursor (bar on selected line)", 
                       variable=self.show_cursor_var, command=self.update_display).grid(row=1, column=0, columnspan=4, sticky="w", **pad)

        # Big UPDATE button
        ttk.Button(self.root, text="🔄 UPDATE DISPLAY NOW", command=self.update_display).pack(fill="x", pady=8)

        # Populate listbox once
        self.refresh_listbox()

    def refresh_listbox(self):
        self.listbox.delete(0, tk.END)
        for i, text in enumerate(self.menu_items):
            self.listbox.insert(tk.END, f"{i:02d} | {text}")

    def sync_visible_lines(self):
        """Copy current view into the 4 editable entries"""
        for i in range(4):
            idx = self.view_start + i
            text = self.menu_items[idx] if idx < len(self.menu_items) else ""
            self.line_vars[i].set(text)

    def sync_back_to_items(self):
        """When user edits the visible entries, push changes back to the full list"""
        for i in range(4):
            idx = self.view_start + i
            new_text = self.line_vars[i].get().strip()
            if idx < len(self.menu_items):
                self.menu_items[idx] = new_text
            elif new_text:  # user added text beyond current list
                while len(self.menu_items) <= idx:
                    self.menu_items.append("")
                self.menu_items[idx] = new_text

    # steering wheel actions
    def btn_up(self):
        if self.highlight_index > 0:
            self.highlight_index -= 1
            # auto-scroll view to keep cursor visible
            if self.highlight_index < self.view_start:
                self.view_start = max(0, self.highlight_index - 3)
            self.sync_visible_lines()
            self.update_display()

    def btn_down(self):
        if self.highlight_index < len(self.menu_items) - 1:
            self.highlight_index += 1
            if self.highlight_index > self.view_start + 3:
                self.view_start = self.highlight_index - 3
            self.sync_visible_lines()
            self.update_display()

    def btn_ok(self):
        if 0 <= self.highlight_index < len(self.menu_items):
            item = self.menu_items[self.highlight_index]
            messagebox.showinfo("OK Pressed", f"Selected:\n{item}\n(Index {self.highlight_index})")
            # TODO: later you can load sub-menu here

    def btn_back(self):
        messagebox.showinfo("OK Longpress", "Back command sent (you can extend this to release zones etc.)")
        self.manager.switch_source(0x06)   # example: go back to Media

    # listbox editing
    def edit_list_item(self, event=None):
        sel = self.listbox.curselection()
        if not sel: return
        idx = sel[0]
        old = self.menu_items[idx]
        new = simpledialog.askstring("Edit Menu Item", "New text:", initialvalue=old)
        if new is not None:
            self.menu_items[idx] = new
            self.refresh_listbox()
            self.sync_visible_lines()
            self.update_display()

    def add_item(self):
        new = simpledialog.askstring("Add new menu item", "Text:")
        if new:
            self.menu_items.append(new)
            self.refresh_listbox()
            self.update_display()

    def delete_item(self):
        sel = self.listbox.curselection()
        if sel:
            idx = sel[0]
            del self.menu_items[idx]
            if self.highlight_index >= len(self.menu_items):
                self.highlight_index = max(0, len(self.menu_items)-1)
            self.refresh_listbox()
            self.sync_visible_lines()
            self.update_display()

    def clear_all_items(self):
        if messagebox.askyesno("Clear", "Delete ALL menu items?"):
            self.menu_items.clear()
            self.highlight_index = 0
            self.view_start = 0
            self.refresh_listbox()
            self.sync_visible_lines()
            self.update_display()

    # can send
    def change_source(self):
        src = 0x01 if self.source_var.get() == "Phone" else 0x06
        self.manager.switch_source(src)

    def update_display(self):
        self.sync_back_to_items()          # important: push any edits from the 4 entries

        # Zone 01 - Top line
        top_text = self.top_var.get().strip()
        if top_text:
            self.manager.claim_zone(0x01)
            self.manager.write_text(0x01, top_text)
        else:
            self.manager.release_zone(0x01) 

        # Zone 02 - Everything else
        self.manager.claim_zone(0x02)
        self.manager.write_text(0x05, self.head_var.get().strip())

        # Visible 4 lines
        for i, var in enumerate(self.line_vars):
            line_id = 0x06 + i
            self.manager.write_text(line_id, var.get().strip())

        # HIGHLIGHT + ARROWS
        total = len(self.menu_items)
        arrow = 0
        if self.view_start > 0:
            arrow |= 1          # up
        if self.view_start + 4 < total:
            arrow |= 2          # down

        if self.show_cursor_var.get() and total > 0:
            rel_slot = self.highlight_index - self.view_start + 1   # 1..4
            if 1 <= rel_slot <= 4:
                # normal cursor on visible line
                self.manager.set_highlight(rel_slot, arrow, 0x00)
            else:
                # cursor off-screen → hide bar, show only arrows
                self.manager.set_highlight(0x00, arrow, 0x00)
        else:
            # no cursor at all → only arrows (if any)
            self.manager.set_highlight(0x00, arrow, 0x00)

        self.manager.release_zone(0x02)

        # final release of top zone if it was used
        if top_text:
            self.manager.release_zone(0x01)

        self.refresh_listbox()   # visual feedback

    # background CAN
    def keepalive_loop(self):
        try:
            self.driver._recv_filtered(0.01)
        except:
            pass
        self.root.after(30, self.keepalive_loop)

    def on_close(self):
        try:
            self.driver.bus.shutdown()
        except:
            pass
        self.root.destroy()


if __name__ == "__main__":
    DISGraphicalUI()
