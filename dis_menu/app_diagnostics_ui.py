# app_diagnostics_ui.py
from app_core import DISApp, tr
from symbols import Symbols
import time
import os
import logging

logger = logging.getLogger("DIAG_UI")

ECU_LIST = [
    {"name": "Engine Electronics", "id": 0x01},
    {"name": "Transmission Electronics", "id": 0x02},
    {"name": "Brake Electronics", "id": 0x03},
    {"name": "Access/Start Authorization", "id": 0x31},
    {"name": "Seat Adjustment (Passenger)", "id": 0x35},
    {"name": "Control Head Front", "id": 0x3F},
    {"name": "Heating/Air Conditioning", "id": 0x2C},
    {"name": "Central Electronics", "id": 0x20},
    {"name": "Media Player I", "id": 0x58},
    {"name": "Radio (Digital)", "id": 0x4F},
    {"name": "Airbag", "id": 0x05},
    {"name": "Steering Wheel Electronics", "id": 0x2A},
    {"name": "Instrument Cluster", "id": 0x07},
    {"name": "Auxiliary Heating", "id": 0x2F},
    {"name": "CAN-Gateway", "id": 0x1F},
    {"name": "Media Player II", "id": 0x50},
    {"name": "Heating/Air Conditioning (Rear)", "id": 0x45},
    {"name": "Level ControlI", "id": 0x04},
    {"name": "Seat Adjustment (Driver)", "id": 0x26},
    {"name": "Navigation", "id": 0x5B},
    {"name": "Roof Electronics", "id": 0x27},
    {"name": "Lane Change Assistant", "id": 0x1C},
    {"name": "Door Electronics Driver", "id": 0x22},
    {"name": "Comfort System", "id": 0x21},
    {"name": "Sound System", "id": 0x53},
    {"name": "Door Electronics Passenger", "id": 0x52},
    {"name": "Parking Brake", "id": 0x19},
    {"name": "Headlight Aim Control", "id": 0x06},
    {"name": "Radio (Analog)", "id": 0x52},
    {"name": "TV-Tuner", "id": 0x57},
    {"name": "Lane Departure Warning", "id": 0x1A},
    {"name": "Information Electr.", "id": 0x4D},
    {"name": "Battery Regulation", "id": 0x33},
    {"name": "Door Electronics Rear Left", "id": 0x24},
    {"name": "Tire Pressure Monitoring", "id": 0x29},
    {"name": "Voice Control", "id": 0x5C},
    {"name": "Trailer", "id": 0x43},
    {"name": "Back-Up Camera", "id": 0x49},
    {"name": "Door Electronics Rear Right", "id": 0x25},
    {"name": "Parking Aid", "id": 0x2D},
    {"name": "Telephone", "id": 0x5A}    
]

DIAG_MENU = [
    {"name": "ECU ID", "action": "id"},
    {"name": "Ext. ID", "action": "ext_id"},
    {"name": "Meas. Blocks", "action": "mwb"},
    {"name": "Fault Codes", "action": "fault_menu"}, # Nested Menu
    {"name": "Output Test", "action": "out_test"}
]

FAULT_MENU = [
    {"name": "Read Faults", "action": "read_dtc"},
    {"name": "Clear Faults", "action": "clear_dtc"}
]

class AppDiagnostics(DISApp):
    def __init__(self, ui, reg, diag_backend):
        super().__init__(ui, reg, "Diagnostics", Symbols.SIM)
        self.diag = diag_backend
        self.state = "ecu_list"
        self.cursor = 0
        self.view_start = 0
        
        self.ecu_name = ""
        self.info_pages = []
        self.info_cursor = 0
        
        self.mwb_block = 1
        self.dtc_list = []
        self.dtc_cursor = 0
        
        self.out_test_active = False
        self.out_test_status = "Ready"
        self.last_top_text = ""
        
        # Parse fault_list.txt at boot
        self.fault_dict = {}
        self._load_fault_list()

    def on_tick(self):
        # Poll the actuator status every 500ms when the test is active
        if self.state == "out_test" and self.out_test_active:
            if not hasattr(self, 'last_out_poll'): 
                self.last_out_poll = 0
                
            if time.time() - self.last_out_poll > 0.5:
                status = self.diag.output_test_status()
                
                if status:
                    if self.out_test_status != status:
                        self.out_test_status = status
                        self.render(force=True)
                else:
                    self.out_test_active = False
                    self.out_test_status = "Ended/Idle"
                    self.render(force=True)
                    
                self.last_out_poll = time.time()   

    def _load_fault_list(self):
        if os.path.exists("fault_list.txt"):
            try:
                with open("fault_list.txt", "r", encoding='utf-8') as f:
                    for line in f:
                        parts = line.strip().split('\t')
                        if len(parts) == 2:
                            # Map P000100 -> Text
                            self.fault_dict[parts[0].strip()] = parts[1].strip()
            except Exception as e:
                logger.error(f"Failed to load fault_list.txt: {e}")

    def _wrap_text(self, text, max_len=18, max_lines=3):
        """Intelligently wraps DTC descriptions across cluster lines"""
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + (1 if current_line else 0) <= max_len:
                current_line += (" " if current_line else "") + word
            else:
                if current_line: lines.append(current_line)
                current_line = word
                if len(current_line) > max_len: current_line = current_line[:max_len]
        if current_line: lines.append(current_line)
        while len(lines) < max_lines: lines.append("")
        return lines[:max_lines]

    def _set_top_line(self, text):
        """Claims Zone 1 to protect bandwidth and provide context"""
        if text != self.last_top_text:
            self.ui.claim_zone(0x01)
            self.ui.write_line(0x01, " ")
            self.ui.write_line(0x02, f" {text}"[:18], Symbols.COLOR_HEADER_WHITE)
            self.ui.write_line(0x04, " ")
            self.ui.release_zone(0x01)
            self.last_top_text = text

    def on_focus(self):
        super().on_focus()
        self.state = "ecu_list"
        self.cursor = 0
        self.view_start = 0
        self.last_top_text = ""
        self.diag.disconnect()

    def on_blur(self):
        super().on_blur()
        self.diag.disconnect()

    def _show_loading(self, line1, line2=""):
        self.ui.claim_zone(0x02)
        self.ui.write_line(0x05, self.app_icon + list(f" {tr('Please Wait')}".encode('cp1252')), Symbols.COLOR_HEADER_WHITE)
        self.ui.write_line(0x06, "", force=True)
        self.ui.write_line(0x07, f"   {tr(line1)}", Symbols.COLOR_BODY_WHITE, force=True)
        self.ui.write_line(0x08, f"   {tr(line2)}", Symbols.COLOR_BODY_WHITE, force=True)
        self.ui.write_line(0x09, "", force=True)
        self.ui.set_highlight(0, 0, force=True)
        self.ui.release_zone(0x02)

    def on_up(self):
        if self.state in ["ecu_list", "diag_menu", "fault_menu"]:
            if self.cursor > 0:
                self.cursor -= 1
                if self.cursor < self.view_start: self.view_start -= 1
        elif self.state == "dtc_pager":
            if self.dtc_cursor > 0: self.dtc_cursor -= 1
        elif self.state == "mwb":
            if self.mwb_block < 255: self.mwb_block += 1
        elif self.state == "pager":
            if self.info_cursor > 0: self.info_cursor -= 1
        self.render()

    def on_down(self):
        if self.state == "ecu_list":
            if self.cursor < len(ECU_LIST) - 1:
                self.cursor += 1
                if self.cursor >= self.view_start + 4: self.view_start += 1
        elif self.state == "diag_menu":
            if self.cursor < len(DIAG_MENU) - 1:
                self.cursor += 1
                if self.cursor >= self.view_start + 4: self.view_start += 1
        elif self.state == "fault_menu":
            if self.cursor < len(FAULT_MENU) - 1:
                self.cursor += 1
                if self.cursor >= self.view_start + 4: self.view_start += 1
        elif self.state == "dtc_pager":
            if self.dtc_cursor < len(self.dtc_list) - 1: self.dtc_cursor += 1
        elif self.state == "mwb":
            if self.mwb_block > 1: self.mwb_block -= 1
        elif self.state == "pager":
            if self.info_cursor < len(self.info_pages) - 1: self.info_cursor += 1
        self.render()

    def on_ok(self):
        if self.state == "ecu_list":
            ecu = ECU_LIST[self.cursor]
            self._show_loading("Connecting...", ecu["name"])
            
            if self.diag.connect(ecu["id"]):
                self.ecu_name = self.diag.get_ecu_name()
                if self.ecu_name == "Unknown ECU": self.ecu_name = ecu["name"]
                self.state = "diag_menu"
                self.cursor = 0
                self.view_start = 0
            else:
                self._show_loading("Connection", "Failed!")
                time.sleep(2)
            self.render(force=True)
            
        elif self.state == "diag_menu":
            action = DIAG_MENU[self.cursor]["action"]
            if action == "id":
                self._show_loading("Reading Data...")
                self.info_pages = self.diag.get_ecu_id_pages()
                self.info_cursor = 0
                self.state = "pager"
            elif action == "ext_id":
                self._show_loading("Reading Data...")
                self.info_pages = self.diag.get_ext_id_pages()
                self.info_cursor = 0
                self.state = "pager"
            elif action == "mwb":
                self.mwb_block = 1
                self.state = "mwb"
            elif action == "fault_menu":
                self.state = "fault_menu"
                self.cursor = 0
                self.view_start = 0
            elif action == "out_test":
                self.out_test_active = False
                self.out_test_status = "Ready"
                self.state = "out_test"
            self.render(force=True)

        elif self.state == "fault_menu":
            action = FAULT_MENU[self.cursor]["action"]
            if action == "read_dtc":
                self._show_loading("Reading Faults...")
                self.dtc_list = self.diag.read_dtcs_list()
                self.dtc_cursor = 0
                self.state = "dtc_pager"
            elif action == "clear_dtc":
                self._show_loading("Clearing Faults...")
                success = self.diag.clear_dtcs()
                self._show_loading("Clear OK!" if success else "Clear Failed!")
                time.sleep(2)
                self.state = "fault_menu"
            self.render(force=True)
            
        elif self.state == "out_test":
            if not self.out_test_active:
                self._show_loading("Starting Test...")
                if self.diag.output_test_start():
                    self.out_test_active = True
                    self.out_test_status = "Running..."
                else:
                    self.out_test_status = "Not Supported"
            else:
                self._show_loading("Next Step...")
                if self.diag.output_test_next():
                    self.out_test_status = "Next Step..."
                else:
                    self.out_test_active = False
                    self.out_test_status = "Ended/Idle"
            self.render(force=True)

    def on_back(self):
        if self.state == "diag_menu":
            self.diag.disconnect()
            self.state = "ecu_list"
            self.cursor = 0
            self.view_start = 0
        elif self.state in ["pager", "mwb", "fault_menu", "out_test"]:
            if self.state == "out_test": self.diag.stop_routines()
            self.state = "diag_menu"
            self.cursor = 0
            self.view_start = 0
        elif self.state == "dtc_pager":
            self.state = "fault_menu"
            self.cursor = 0
            self.view_start = 0
        elif self.state == "ecu_list":
            self.on_blur()
        self.render(force=True)

    def render(self, force=False):
        if self.state == "loading": return 
        
        # --- Top Line Management ---
        if self.state == "dtc_pager":
            if self.dtc_list:
                self._set_top_line(f"{tr('FAULT')} {self.dtc_cursor + 1}/{len(self.dtc_list)}")
            else:
                self._set_top_line(f"{tr('FAULTS')}: 0")
        else:
            self._set_top_line("DIAGNOSTICS")

        # --- Main Screen Management ---
        self.ui.claim_zone(0x02)
        
        lines = ["", "", "", ""]
        arrows = 0
        hl_line = 0
        header_text = ""

        if self.state == "ecu_list":
            header_text = "Select ECU"
            for i in range(4):
                idx = self.view_start + i
                if idx < len(ECU_LIST):
                    lines[i] = tr(ECU_LIST[idx]["name"])[:18]
            hl_line = self.cursor - self.view_start + 1
            if self.view_start > 0: arrows |= 1
            if self.view_start + 4 < len(ECU_LIST): arrows |= 2

        elif self.state == "diag_menu":
            header_text = self.ecu_name
            for i in range(4):
                idx = self.view_start + i
                if idx < len(DIAG_MENU):
                    lines[i] = tr(DIAG_MENU[idx]["name"])[:18]
            hl_line = self.cursor - self.view_start + 1
            if self.view_start > 0: arrows |= 1
            if self.view_start + 4 < len(DIAG_MENU): arrows |= 2

        elif self.state == "fault_menu":
            header_text = "Fault Codes"
            for i in range(4):
                idx = self.view_start + i
                if idx < len(FAULT_MENU):
                    lines[i] = tr(FAULT_MENU[idx]["name"])[:18]
            hl_line = self.cursor - self.view_start + 1

        elif self.state == "dtc_pager":
            header_text = self.ecu_name
            if not self.dtc_list:
                lines[0] = "No Faults Found!"
            else:
                dtc = self.dtc_list[self.dtc_cursor]
                desc = self.fault_dict.get(dtc["hex"], "UNKNOWN FAULT")
                
                lines[0] = f"Code: {dtc['vag']:05d}"
                wrapped = self._wrap_text(desc, max_len=18, max_lines=3)
                lines[1] = wrapped[0]
                lines[2] = wrapped[1]
                lines[3] = wrapped[2]

            if self.dtc_cursor > 0: arrows |= 1
            if self.dtc_cursor < len(self.dtc_list) - 1: arrows |= 2
            hl_line = 0 # No highlight box, just full text!

        elif self.state == "pager":
            header_text = self.ecu_name
            page = self.info_pages[self.info_cursor]
            lines = [page[0][:18], page[1][:18], page[2][:18], page[3][:18]]
            if self.info_cursor > 0: arrows |= 1
            if self.info_cursor < len(self.info_pages) - 1: arrows |= 2
            hl_line = 0

        elif self.state == "mwb":
            header_text = f"Meas. Block {self.mwb_block}"
            mwb_vals = self.diag.read_mwb(self.mwb_block)
            for i in range(4):
                if i < len(mwb_vals): lines[i] = mwb_vals[i][:18]
            arrows = 3 
            hl_line = 0

        elif self.state == "out_test":
            header_text = "Output Test"
            lines[0] = self.out_test_status[:18]
            lines[1] = "  Start Test" if not self.out_test_active else "  Next Step"
            hl_line = 2

        # Draw the header
        self.ui.write_line(0x05, list(f" {header_text}".encode('cp1252')[:18]), Symbols.COLOR_HEADER_WHITE, force)

        # Draw the body
        for i in range(4):
            self.ui.write_line(0x06 + i, lines[i], Symbols.COLOR_BODY_WHITE, force)
            
        self.ui.set_highlight(hl_line, arrows, force)
        self.ui.release_zone(0x02)
