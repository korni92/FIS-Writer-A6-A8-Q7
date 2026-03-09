#include "settings_registry.h"

SettingsRegistry global_settings;
SettingItem* s_theme = nullptr; // VERY IMPORTANT: here is the physical location of the pinter
SettingItem* s_car_model = nullptr; 
SettingItem* s_auto = nullptr;
SettingItem* s_top = nullptr;        
SettingItem* s_top_custom_l = nullptr; 
SettingItem* s_top_custom_r = nullptr;

void SettingsRegistry::init() {
    prefs.begin("dis_settings", false);
    
    for (SettingItem* item : root_items) {
        loadValues(item);
    }
}

void SettingsRegistry::addRootItem(SettingItem* item) {
    root_items.push_back(item);
}

void SettingsRegistry::loadValues(SettingItem* item) {
    item->value = prefs.getUChar(item->id.c_str(), item->value);
    for (SettingItem* child : item->children) {
        loadValues(child);
    }
}

void SettingsRegistry::saveValue(SettingItem* item) {
    prefs.putUChar(item->id.c_str(), item->value);
    Serial.printf("Settings: Gespeichert [%s] = %d\n", item->id.c_str(), item->value);
    
    if (item->onChange != nullptr) {
        item->onChange(item->value);
    }
}
