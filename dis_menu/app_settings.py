# app_settings.py
from app_core import DISApp, GLOBAL_SETTINGS, tr, LIVE_DATA
from symbols import Symbols

class AppSettings(DISApp):
    def __init__(self, ui, reg):
        super().__init__(ui, reg, "Settings", Symbols.FACTORY)
        self.cursor = 0
        self.view_start = 0
        self.flat_list = []
        self._flatten_menu()

    def on_focus(self):
        super().on_focus()
        self.cursor = 0
        self.view_start = 0
        for item in GLOBAL_SETTINGS:
            self._collapse_all(item)
        self._flatten_menu()

    def _collapse_all(self, item):
        item.is_expanded = False
        for child in item.children:
            self._collapse_all(child)

    def _flatten_menu(self):
        self.flat_list = []
        for item in GLOBAL_SETTINGS:
            self._flatten_recursive(item, indent=0)

    def _flatten_recursive(self, item, indent):
        self.flat_list.append({"type": "node", "item": item, "indent": indent})
        if item.is_expanded:
            for i, opt_name in enumerate(item.options):
                self.flat_list.append({
                    "type": "option", "item": item, "indent": indent + 1, 
                    "opt_idx": i, "opt_str": opt_name
                })
                if i == item.val and item.children and opt_name == "Custom":
                    for child in item.children:
                        self._flatten_recursive(child, indent + 1)

    def on_up(self):
        if self.cursor > 0:
            self.cursor -= 1
            if self.cursor < self.view_start: self.view_start -= 1
        self.render()

    def on_down(self):
        if self.cursor < len(self.flat_list) - 1:
            self.cursor += 1
            if self.cursor >= self.view_start + 4: self.view_start += 1
        self.render()

    def on_ok(self):
        entry = self.flat_list[self.cursor]
        is_theme_change = False
        
        if entry["type"] == "node":
            entry["item"].is_expanded = not entry["item"].is_expanded
        elif entry["type"] == "option":
            entry["item"].val = entry["opt_idx"]
            
            if entry["item"].name == "Theme":
                # We flag this so the App DOES NOT render. Let the OS take over!
                is_theme_change = True
                
            elif entry["item"].name == "Live Config" and entry["opt_str"] == "Reload & Sync":
                LIVE_DATA.reload_and_sync()
        
        self._flatten_menu()
        
        # Only render immediately if it wasn't a theme change
        if not is_theme_change:
            self.render(force=True) 

    def on_back(self):
        self.on_blur()

    def render(self, force=False):
        self.ui.claim_zone(0x02)
        
        header = self.app_icon + list(f" {tr(self.app_name)}".encode('cp1252'))
        self.ui.write_line(0x05, header, Symbols.COLOR_HEADER_WHITE, force)
        
        for i in range(4):
            idx = self.view_start + i
            line_id = 0x06 + i
            
            if idx < len(self.flat_list):
                entry = self.flat_list[idx]
                indent_sym = Symbols.INDENT * entry["indent"]
                
                if entry["type"] == "node":
                    arrow = Symbols.ARROW_DOWN if entry["item"].is_expanded else Symbols.ARROW_RIGHT
                    disp_txt = indent_sym + arrow + list(f" {tr(entry['item'].name)}"[:18].encode('cp1252'))
                    col = Symbols.COLOR_BODY_WHITE
                    
                else:
                    disp_txt = indent_sym + list(f" {tr(entry['opt_str'])}"[:18].encode('cp1252'))
                    if entry["item"].val == entry["opt_idx"]:
                        col = Symbols.COLOR_BODY_THEME
                    else:
                        col = Symbols.COLOR_BODY_WHITE
                
                self.ui.write_line(line_id, disp_txt, col, force)
            else:
                self.ui.write_line(line_id, "", force=force)
                
        arrow_cfg = 0
        if len(self.flat_list) > 4:
            if self.view_start > 0: arrow_cfg |= 1
            if self.view_start + 4 < len(self.flat_list): arrow_cfg |= 2
            
        self.ui.set_highlight(self.cursor - self.view_start + 1, arrow_cfg, force)
        self.ui.release_zone(0x02)
