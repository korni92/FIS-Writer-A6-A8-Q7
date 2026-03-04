# app_core.py
from symbols import Symbols
from can_provider import LiveCANDataProvider
import json
import os
import logging

logger = logging.getLogger("CORE")

# --- GLOBAL STORAGE (NVM) ---
class ConfigStore:
    def __init__(self, filepath="config.json"):
        self.filepath = filepath
        self.data = {
            "sys_language": 0, "sys_autostart": 0, "sys_theme": 0,        
            "top_line_mode": 0, "top_line_left": 0, "top_line_right": 0    
        }
        self.load()

    def get(self, key): return self.data.get(key, 0)
    def set(self, key, value):
        if key in self.data and self.data[key] != value:
            self.data[key] = value
            self.save()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f: self.data.update(json.load(f))
            except Exception: pass

    def save(self):
        try:
            with open(self.filepath, 'w') as f: json.dump(self.data, f, indent=4)
        except Exception: pass

CONFIG = ConfigStore()

# --- LANGUAGE ENGINE (I18n) ---
class TranslationEngine:
    def __init__(self):
        self.dict = {}
        if os.path.exists("lang.json"):
            try:
                with open("lang.json", 'r', encoding='utf-8') as f: self.dict = json.load(f)
            except Exception: pass

    def translate(self, text):
        lang_id = str(CONFIG.get("sys_language"))
        if lang_id in self.dict and text in self.dict[lang_id]: return self.dict[lang_id][text]
        return text 

I18N = TranslationEngine()
def tr(text): return I18N.translate(text)


# --- LIVE CAN DATA MANAGER ---
class LiveDataManager:
    def __init__(self):
        self.provider = LiveCANDataProvider()
        self.configs = {"variables": {}, "pages": []}
        self.load_config()

    def load_config(self):
        if os.path.exists("live_config.json"):
            try:
                with open("live_config.json", 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.configs["variables"] = loaded.get("variables", {})
                    self.configs["pages"] = loaded.get("pages", [])
            except Exception as e:
                logger.error(f"Error parsing config: {e}")

    def reload_and_sync(self):
        """Extracts available CAN data from Provider and injects it into the config file."""
        self.load_config() # Grab latest user changes from disk first
        
        avail_vars = self.provider.get_available_variables()
        if "variables" not in self.configs:
            self.configs["variables"] = {}
            
        for k, v in avail_vars.items():
            if k not in self.configs["variables"]:
                self.configs["variables"][k] = v
            else:
                # Merge: Keep the user's custom name if they changed it, but update units/decimals
                orig_name = self.configs["variables"][k].get("name", "")
                self.configs["variables"][k].update(v)
                if orig_name: self.configs["variables"][k]["name"] = orig_name
                
        # Save back to disk so the user can import it into the Web Editor
        try:
            with open("live_config.json", 'w', encoding='utf-8') as f:
                json.dump(self.configs, f, indent=4)
            logger.info("Successfully synced live_config.json with CAN Provider!")
        except Exception as e:
            logger.error(f"Failed to sync config: {e}")
            
        # Dynamically update the Top Line Dropdown options without a reboot!
        new_names = self.get_variable_names()
        for item in GLOBAL_SETTINGS:
            if item.name == "Top Line":
                for child in item.children:
                    if child.name in ["Left Data", "Right Data"]:
                        child.options = new_names

    def get_variable_names(self):
        names = []
        for k, v in self.configs["variables"].items():
            name = v.get("name", "")
            names.append(name if name else k.upper())
        return names if names else ["No Data"]

    def get_variable_keys(self):
        keys = list(self.configs["variables"].keys())
        return keys if keys else ["none"]

    def parse_message(self, msg):
        self.provider.parse_message(msg, bus_name="cluster")

    def get_value(self, key):
        return self.provider.get_value(key)

LIVE_DATA = LiveDataManager()


# --- MENU SYSTEM ---
class MenuItem:
    def __init__(self, name, config_key=None, options=None, children=None):
        self.name = name
        self.config_key = config_key
        self.options = options if options else []
        self.children = children if children else []
        self.is_expanded = False

    @property
    def val(self): return CONFIG.get(self.config_key) if self.config_key else 0
    @val.setter
    def val(self, new_val):
        if self.config_key: CONFIG.set(self.config_key, new_val)

data_names = LIVE_DATA.get_variable_names()

GLOBAL_SETTINGS = [
    MenuItem("Language", config_key="sys_language", options=["English", "Deutsch"]),
    MenuItem("Autostart", config_key="sys_autostart", options=["Off", "On"]),
    MenuItem("Theme", config_key="sys_theme", options=["Red", "Green"]),
    MenuItem("Top Line", config_key="top_line_mode", options=["OEM", "Custom"], children=[
        MenuItem("Left Data", config_key="top_line_left", options=data_names),
        MenuItem("Right Data", config_key="top_line_right", options=data_names)
    ]),
    MenuItem("Live Config", options=["Reload & Sync"]) 
]

class DISApp:
    def __init__(self, ui_manager, app_registry, app_name, app_icon):
        self.ui = ui_manager
        self.registry = app_registry
        self.app_name = app_name
        self.app_icon = app_icon
        self.is_active = False

    def on_focus(self): self.is_active = True
    def on_blur(self):  self.is_active = False
    def on_up(self): pass
    def on_down(self): pass
    def on_ok(self): pass
    def on_back(self): pass
    def on_tick(self): pass 
    def render(self, force=False): pass
