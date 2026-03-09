#include "app_launcher.h"
#include "ui_main.h"
#include "can_mmi.h"
#include "settings_registry.h"
#include "app_settings.h" 

AppLauncher app_launcher;

void AppLauncher::updateShadowBuffer() {
    ui.setLine(5, "ESP32 Main Menu", 0x00); 

    for (int i = 0; i < 4; i++) {
        int idx = view_start + i;
        uint8_t line_id = 6 + i; 
        
        if (idx < num_items) {
            ui.setLine(line_id, menu_items[idx], 0x01); 
        } else {
            ui.setLine(line_id, "", 0x01); 
        }
    }

    uint8_t arrows = 0;
    if (view_start > 0) arrows |= 0x01;  
    if (view_start + 4 < num_items) arrows |= 0x02; 
    ui.setIndicator((cursor - view_start) + 1, arrows);
}

void AppLauncher::onStart() {
    Serial.println("AppLauncher: onStart");
    
    uint8_t target_theme = (s_theme->value == 1) ? 0x06 : 0x01; 
    
    if (ui.is_oem_screen || ui.active_theme != target_theme) {
        ui.applyTheme(target_theme); 
        os_active_wait(50); 
        
        ui.clearBuffer(); 
        updateShadowBuffer();
        if (!ui.commitFullRedraw()) ui.needs_redraw = true; 
    } else {
        ui.clearBuffer(); 
        updateShadowBuffer();
        ui.commitMiddleZone(); 
    }
}

void AppLauncher::onStop() {
    Serial.println("AppLauncher: onStop (Pausiert im Hintergrund)");
}

void AppLauncher::onTick() {}

// uses input event
void AppLauncher::handleInput(InputEvent cmd) {
    bool cursor_moved = false;

    if (cmd == BTN_UP && cursor > 0) {
        cursor--;
        if (cursor < view_start) view_start--;
        cursor_moved = true;
    } 
    else if (cmd == BTN_DOWN && cursor < num_items - 1) {
        cursor++;
        if (cursor >= view_start + 4) view_start++;
        cursor_moved = true;
    }
    else if (cmd == BTN_OK) {
        if (cursor == 3) { // "Close Menu"
            os_switch_app(nullptr); 
        } 
        else if (cursor == 2) { 
            os_switch_app(&app_settings); 
        } 
        else {
            Serial.printf("Würde jetzt App-Index %d starten...\n", cursor);
        }
    }

    if (cursor_moved) {
        updateShadowBuffer();
        ui.commitMiddleZone(); 
    }
}

void AppLauncher::onRedraw() {
    Serial.println("AppLauncher: onRedraw (Auto-Restore...)");
    ui.clearBuffer(); 
    updateShadowBuffer();
    
    if (!ui.commitFullRedraw()) {
        ui.needs_redraw = true;
    }
}
