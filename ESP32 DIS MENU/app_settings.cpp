#include "app_settings.h"
#include "ui_main.h"
#include "app_launcher.h"
#include "ui_symbols.h"

AppSettings app_settings;

void AppSettings::flattenRecursive(SettingItem* item, uint8_t indent) {
    // dynamic hide for options that the A6/Q7 dont have, or hidden in OEM mode
    if (item->id == "top_c_l" || item->id == "top_c_r") {
        if (s_car_model->value == 0) return; // Dont show when configured for A6/Q7
        if (s_top->value == 0) return;       // Dont show in OEM mode
    }

    FlatMenuItem node;
    node.item = item;
    node.is_node = true;
    node.indent = indent;
    node.display_text = item->name;
    flat_list.push_back(node);

    if (item->is_expanded) {
        for (uint8_t i = 0; i < item->options.size(); i++) {
            FlatMenuItem opt;
            opt.item = item;
            opt.is_node = false;
            opt.option_index = i;
            opt.indent = indent + 1;
            opt.display_text = item->options[i];
            flat_list.push_back(opt);

            // when this option is choosen, no matter it has children or not
            if (i == item->value && !item->children.empty()) {
                for (SettingItem* child : item->children) {
                    flattenRecursive(child, indent + 1);
                }
            }
        }
    }
}

void AppSettings::flattenMenu() {
    flat_list.clear();
    for (SettingItem* item : global_settings.root_items) {
        flattenRecursive(item, 0);
    }
}

void AppSettings::updateShadowBuffer() {
    ui.setLine(5, "ESP32 Settings", 0x00); 

    for (int i = 0; i < 4; i++) {
        int idx = view_start + i;
        uint8_t line_id = 6 + i; 
        
        if (idx < flat_list.size()) {
            FlatMenuItem& entry = flat_list[idx];
            
            String prefix = "";
            for(int j=0; j < entry.indent; j++) prefix += "  ";
            
            if (entry.is_node) {
                String arrow = entry.item->is_expanded ? SYM_ARROW_DOWN " " : SYM_ARROW_RIGHT " ";
                ui.setLine(line_id, (prefix + arrow + entry.display_text).c_str(), 0x00);
            } else {
                uint8_t color = (entry.item->value == entry.option_index) ? 0x01 : 0x00;
                ui.setLine(line_id, (prefix + " " + entry.display_text).c_str(), color);
            }
        } else {
            ui.setLine(line_id, "", 0x00);
        }
    }

    uint8_t arrows = 0;
    if (view_start > 0) arrows |= 0x01;  
    if (view_start + 4 < flat_list.size()) arrows |= 0x02; 
    ui.setIndicator((cursor - view_start) + 1, arrows);
}

void AppSettings::onStart() {
    Serial.println("AppSettings: onStart");
    
    uint8_t target_theme = (s_theme->value == 1) ? 0x06 : 0x01; 
    bool needs_full_redraw = (ui.is_oem_screen || ui.active_theme != target_theme);
    
    if (needs_full_redraw) {
        ui.applyTheme(target_theme); 
        os_active_wait(50); 
    }
    
    for (SettingItem* item : global_settings.root_items) item->is_expanded = false;
    cursor = 0;
    view_start = 0;
    flattenMenu();
    
    ui.clearBuffer(); 
    updateShadowBuffer();
    
    if (needs_full_redraw) {
        if (!ui.commitFullRedraw()) ui.needs_redraw = true; 
    } else {
        ui.commitMiddleZone(); 
    }
}

void AppSettings::onStop() {
    Serial.println("AppSettings: onStop (Pausiert im Hintergrund)");
}

void AppSettings::onTick() {}

// uses InputEvent
void AppSettings::handleInput(InputEvent cmd) {
    bool redraw_needed = false;
    bool force_full_redraw = false;

    if (cmd == BTN_UP && cursor > 0) {
        cursor--;
        if (cursor < view_start) view_start--;
        redraw_needed = true;
    } 
    else if (cmd == BTN_DOWN && cursor < flat_list.size() - 1) {
        cursor++;
        if (cursor >= view_start + 4) view_start++;
        redraw_needed = true;
    }
    else if (cmd == BTN_OK && flat_list.size() > 0) {
        FlatMenuItem& entry = flat_list[cursor];
        
        if (entry.is_node) {
            entry.item->is_expanded = !entry.item->is_expanded;
            flattenMenu(); 
            redraw_needed = true;
        } else {
            entry.item->value = entry.option_index;
            global_settings.saveValue(entry.item); 
            flattenMenu(); 
            redraw_needed = true;
            
            if (entry.item->id == "sys_theme") {
                force_full_redraw = true;
            }
        }
    }
    else if (cmd == BTN_MODE) { // MODE-Taste geht zurück zum Launcher!
        os_switch_app(&app_launcher);
        return;
    }

    if (redraw_needed) {
        updateShadowBuffer();
        if (force_full_redraw) {
            ui.commitFullRedraw();
        } else {
            ui.commitMiddleZone(); 
        }
    }
}

void AppSettings::onRedraw() {
    ui.clearBuffer(); 
    updateShadowBuffer();
    if (!ui.commitFullRedraw()) ui.needs_redraw = true;
}
