# app_livedata.py
from app_core import DISApp, LIVE_DATA, tr
from symbols import Symbols
import time

class AppLiveData(DISApp):
    def __init__(self, ui, reg):
        super().__init__(ui, reg, "Live Data", Symbols.CAR) 
        self.current_page_idx = 0
        self.view_start = 0
        self.last_render_time = 0
        self.pages = []
        self.variables = {}

    def on_focus(self):
        super().on_focus()
        self.pages = LIVE_DATA.configs.get("pages", [])
        self.variables = LIVE_DATA.configs.get("variables", {})
        
        # EXCEPTION: We explicitly DO NOT reset view_start and current_page_idx here.
        # This allows the app to perfectly remember where the driver left off!
        
        # Safety Check: Only reset if they hot-swapped the config and the page no longer exists
        if self.pages and self.current_page_idx >= len(self.pages):
            self.current_page_idx = 0
            self.view_start = 0

    def on_up(self):
        if not self.pages: return
        page = self.pages[self.current_page_idx]
        if page.get("type") == "list" and self.view_start > 0:
            self.view_start -= 1
            self.render()

    def on_down(self):
        if not self.pages: return
        page = self.pages[self.current_page_idx]
        if page.get("type") == "list":
            items = page.get("items", [])
            if self.view_start + 4 < len(items):
                self.view_start += 1
                self.render()

    def on_ok(self):
        if self.pages:
            self.current_page_idx = (self.current_page_idx + 1) % len(self.pages)
            self.view_start = 0
            self.render(force=True)

    def on_back(self):
        self.on_blur()

    def on_tick(self):
        current_time = time.time()
        if current_time - self.last_render_time > 0.5:
            self.render(force=True)
            self.last_render_time = current_time

    def build_char_bar(self, pct):
        length = 14
        filled = int(round(max(0.0, min(1.0, pct)) * length))
        empty = length - filled
        return f"[{'|'*filled}{'.'*empty}]"

    def _evaluate_item(self, item_cfg):
        i_type = item_cfg.get("type", "empty")
        
        if i_type == "empty":
            return "", False, False
            
        if i_type == "text":
            return tr(item_cfg.get("text", "")), False, False

        key = item_cfg.get("key", "")
        val = LIVE_DATA.get_value(key)
        var_def = self.variables.get(key, {})
        
        is_warn = False
        warn_high = item_cfg.get("warn_high")
        warn_low = item_cfg.get("warn_low")
        if warn_high is not None and val >= warn_high: is_warn = True
        if warn_low is not None and val <= warn_low: is_warn = True

        c_mode = item_cfg.get("color_mode", "normal")
        color_is_theme = False
        if c_mode == "theme" or (c_mode == "warn" and is_warn):
            color_is_theme = True

        if i_type == "bar":
            vmin = item_cfg.get("min", 0.0)
            vmax = item_cfg.get("max", 100.0)
            pct = (val - vmin) / (vmax - vmin) if vmax > vmin else 0
            return self.build_char_bar(pct), color_is_theme, is_warn

        if i_type == "value":
            decs = var_def.get("decimals", 0)
            val_str = f"{val:.{decs}f}"
            prefix = tr(item_cfg.get("prefix", ""))
            suffix = tr(item_cfg.get("suffix", ""))
            return f"{prefix}{val_str}{suffix}", color_is_theme, is_warn

        return "", False, False

    def render(self, force=False):
        self.ui.claim_zone(0x02)
        
        if not self.pages:
            self.ui.write_line(0x05, "No Pages Configured", Symbols.COLOR_HEADER_WHITE, force)
            self.ui.release_zone(0x02)
            return

        page = self.pages[self.current_page_idx]
        lines = ["", "", "", "", ""] 
        colors = [Symbols.COLOR_HEADER_WHITE] + [Symbols.COLOR_BODY_WHITE] * 4
        arrows = 0
        global_warning = False

        # --- CUSTOM ABSOLUTE LAYOUT ---
        if page.get("type") == "custom":
            layout = page.get("lines", {})
            for i in range(5):
                line_key = f"0{5+i}"
                if line_key in layout:
                    txt, is_theme, is_warn = self._evaluate_item(layout[line_key])
                    lines[i] = txt[:18]
                    if is_warn: global_warning = True
                    
                    if i == 0: 
                        colors[0] = Symbols.COLOR_HEADER_RED if is_warn else Symbols.COLOR_HEADER_WHITE
                    else:
                        colors[i] = Symbols.COLOR_BODY_THEME if is_theme else Symbols.COLOR_BODY_WHITE

            lines[0] = self.app_icon + list(f" {lines[0]}".encode('cp1252'))

        # --- PRESET LIST LAYOUT ---
        elif page.get("type") == "list":
            title = tr(page.get("title", "List Data"))
            lines[0] = self.app_icon + list(f" {title}".encode('cp1252'))
            
            items = page.get("items", [])
            for i in range(4):
                idx = self.view_start + i
                if idx < len(items):
                    txt, is_theme, is_warn = self._evaluate_item(items[idx])
                    lines[i+1] = txt[:18]
                    colors[i+1] = Symbols.COLOR_BODY_THEME if is_theme else Symbols.COLOR_BODY_WHITE
                    if is_warn: global_warning = True
            
            if global_warning: colors[0] = Symbols.COLOR_HEADER_RED
            
            if len(items) > 4:
                if self.view_start > 0: arrows |= 1
                if self.view_start + 4 < len(items): arrows |= 2

        # --- WRITE TO CLUSTER ---
        for i in range(5):
            self.ui.write_line(0x05 + i, lines[i], colors[i], force)
            
        self.ui.set_highlight(0, arrows, force) 
        self.ui.release_zone(0x02)
