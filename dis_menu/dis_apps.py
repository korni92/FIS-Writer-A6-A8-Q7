# dis_apps.py
from symbols import Symbols

class MenuItem:
    """Helper class to build tree-based menus for C++ migration"""
    def __init__(self, name, type="action", options=None, children=None):
        self.name = name
        self.type = type # "action", "dropdown", "select"
        self.options = options if options else []
        self.children = children if children else []
        self.val = 0
        self.is_expanded = False

# The Global Registry built as a tree
GLOBAL_SETTINGS = [
    MenuItem("Theme", type="dropdown", options=["Red/Media", "Green/Phone"]),
    MenuItem("Top Line", type="dropdown", options=["OEM", "Custom"], children=[
        MenuItem("Left Data", type="dropdown", options=["Oil Temp", "Speed", "RPM"]),
        MenuItem("Right Data", type="dropdown", options=["Oil Temp", "Speed", "RPM"])
    ])
]

class DISApp:
    def __init__(self, ui_manager, app_registry):
        self.ui = ui_manager
        self.registry = app_registry
        self.is_active = False

    def on_focus(self): self.is_active = True
    def on_blur(self):  self.is_active = False
    def on_up(self): pass
    def on_down(self): pass
    def on_ok(self): pass
    def on_back(self): pass
    def on_tick(self): pass 
    def render(self, force=False): pass


class SettingsApp(DISApp):
    def __init__(self, ui, reg):
        super().__init__(ui, reg)
        self.cursor = 0
        self.view_start = 0
        self.flat_list = []
        self._flatten_menu()

    def _flatten_menu(self):
        """Flattens the menu tree into a 1D list based on what is expanded."""
        self.flat_list = []
        for item in GLOBAL_SETTINGS:
            self.flat_list.append((item, 0)) # (Item, Indent Level)
            if item.is_expanded and item.type == "dropdown":
                
                # If the dropdown has children (like Top Line -> Left/Right)
                if item.children and item.options[item.val] == "Custom":
                    for child in item.children:
                        self.flat_list.append((child, 1))
                        # Note: Deep nesting (children of children) would need recursion,
                        # but keeping it 1-level deep is safer for a 4-line display.

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
        item, _ = self.flat_list[self.cursor]
        
        if item.type == "dropdown":
            if item.options:
                item.val = (item.val + 1) % len(item.options)
            
            # If this dropdown has structural children (like Custom Top Line), expand it
            if item.children:
                item.is_expanded = (item.options[item.val] == "Custom")
            
            self._flatten_menu()
            
            # If theme changed, force a UI hardware rebuild
            if item.name == "Theme":
                theme_hex = 0x01 if item.val == 1 else 0x06
                self.ui.switch_source_and_rebuild(theme_hex)
                
        self.render(force=True)

    def on_back(self):
        self.on_blur()

    def render(self, force=False):
        self.ui.claim_zone(0x02)
        
        header = Symbols.FACTORY + list(" Settings".encode('cp1252'))
        self.ui.write_line(0x05, header, Symbols.COLOR_INVERT, force)
        
        for i in range(4):
            idx = self.view_start + i
            line_id = 0x06 + i
            
            if idx < len(self.flat_list):
                item, indent = self.flat_list[idx]
                
                # Build the prefix (Indent + Arrow)
                prefix = []
                if indent > 0: prefix.extend(Symbols.INDENT)
                
                if item.type == "dropdown":
                    if item.is_expanded: prefix.extend(Symbols.ARROW_DOWN)
                    else: prefix.extend(Symbols.ARROW_RIGHT)
                    
                # Build the text
                opt_str = f" {item.options[item.val]}" if item.options else ""
                disp_txt = prefix + list(f" {item.name}{opt_str}"[:18].encode('cp1252'))
                
                # Active item gets COLOR_DEFAULT (Red/Green), Inactive gets COLOR_INVERT (White)
                col = Symbols.COLOR_DEFAULT if idx == self.cursor else Symbols.COLOR_INVERT
                self.ui.write_line(line_id, disp_txt, col, force)
            else:
                self.ui.write_line(line_id, "", force=force)
                
        # Calculate Arrows ONLY if list > 4
        arrow_cfg = 0
        if len(self.flat_list) > 4:
            if self.view_start > 0: arrow_cfg |= 1
            if self.view_start + 4 < len(self.flat_list): arrow_cfg |= 2
            
        self.ui.set_highlight(self.cursor - self.view_start + 1, arrow_cfg, force)
        self.ui.release_zone(0x02)
