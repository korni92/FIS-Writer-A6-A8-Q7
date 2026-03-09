#ifndef SETTINGS_REGISTRY_H
#define SETTINGS_REGISTRY_H

#include <Arduino.h>
#include <vector>
#include <Preferences.h>
#include <functional> // Wichtig für Callbacks!

typedef std::function<void(uint8_t)> SettingChangeCallback;

class SettingItem {
public:
    String id; 
    String name;
    std::vector<String> options;
    uint8_t value;
    bool is_expanded;
    std::vector<SettingItem*> children;
    SettingChangeCallback onChange;

    SettingItem(String save_id, String display_name, std::vector<String> opts, uint8_t defaultVal, SettingChangeCallback cb = nullptr) {
        id = save_id;
        name = display_name;
        options = opts;
        value = defaultVal;
        is_expanded = false;
        onChange = cb;
    }

    void addChild(SettingItem* child) {
        children.push_back(child);
    }
};

class SettingsRegistry {
private:
    Preferences prefs;
public:
    std::vector<SettingItem*> root_items;

    void init();
    void addRootItem(SettingItem* item);
    void loadValues(SettingItem* item);
    void saveValue(SettingItem* item);
};

extern SettingsRegistry global_settings;
extern SettingItem* s_theme;
extern SettingItem* s_car_model;
extern SettingItem* s_auto;
extern SettingItem* s_top;  
extern SettingItem* s_top_custom_l; 
extern SettingItem* s_top_custom_r; 

#endif
