# app_launcher.py
from app_core import DISApp, tr
from symbols import Symbols

class AppLauncher(DISApp):
    def __init__(self, ui, reg):
        super().__init__(ui, reg, "Main Menu", Symbols.CAR)
        self.cursor = 0
        self.view_start = 0
        self.app_list = []

    def on_focus(self):
        super().on_focus()
        self.app_list = [app for name, app in self.registry.items() if name != "Launcher"]
        self.app_list.append("CLOSE") 

    def on_up(self):
        if self.cursor > 0: 
            self.cursor -= 1
            if self.cursor < self.view_start: self.view_start -= 1
        self.render()

    def on_down(self):
        if self.cursor < len(self.app_list) - 1: 
            self.cursor += 1
            if self.cursor >= self.view_start + 4: self.view_start += 1
        self.render()

    def on_ok(self):
        if not self.app_list: return
        selected = self.app_list[self.cursor]
        if selected == "CLOSE":
            self.on_blur() 
            return
        self.on_blur()
        selected.on_focus()
        selected.render(force=True)

    def on_back(self):
        pass

    def render(self, force=False):
        self.ui.claim_zone(0x02)
        
        header = self.app_icon + list(f" {tr(self.app_name)}".encode('cp1252'))
        self.ui.write_line(0x05, header, Symbols.COLOR_HEADER_WHITE, force)

        for i in range(4):
            idx = self.view_start + i
            line_id = 0x06 + i
            if idx < len(self.app_list):
                col = Symbols.COLOR_BODY_WHITE
                if self.app_list[idx] == "CLOSE":
                    disp_txt = list(f"   {tr('Close Menu')}".encode('cp1252'))
                else:
                    target_app = self.app_list[idx]
                    disp_txt = target_app.app_icon + list(f" {tr(target_app.app_name)}"[:18].encode('cp1252'))
                self.ui.write_line(line_id, disp_txt, col, force)
            else:
                self.ui.write_line(line_id, "", force=force)

        arrow_cfg = 0
        if len(self.app_list) > 4:
            if self.view_start > 0: arrow_cfg |= 1
            if self.view_start + 4 < len(self.app_list): arrow_cfg |= 2
            
        self.ui.set_highlight(self.cursor - self.view_start + 1, arrow_cfg, force)
        self.ui.release_zone(0x02)
