#include <Arduino.h>
#include "nvs_flash.h" 
#include "gateway.h"
#include "can_cluster.h"
#include "can_mmi.h"
#include "ui_main.h"
#include "can_data.h"

// Settings and APPS
#include "settings_registry.h"
#include "app_base.h"
#include "app_settings.h"
#include "app_launcher.h"

bool last_kl15_state = false;
bool needs_priming = true; 

// XX second autostart delay variable
uint32_t tacho_connect_time = 0;
bool os_fully_booted = false;

void setup() {
    Serial.begin(115200);
    
    Serial.println("\n--- ESP32 Kaltstart - Warte 5s auf Tacho-Boot ---");
    delay(5000); 
    
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    
    Serial.println("\n=== Audi A8 DIS Gateway startet ===");

    // GLOBAL SETTINGS
    s_theme = new SettingItem("sys_theme", "Farbschema", {"Weiss/Gruen", "Rot (Media)"}, 1, [](uint8_t val) {
        uint8_t t = (val == 1) ? 0x06 : 0x01;
        ui.applyTheme(t);
    });
    
    s_car_model = new SettingItem("sys_car", "Fahrzeug", {"A6 / Q7", "A8"}, 1, [](uint8_t val) {
        snooped_top_dirty = true; 
    });
    
    s_auto = new SettingItem("sys_auto", "Autostart", {"Aus", "Menue", "Live Daten"}, 0);
    
    s_top = new SettingItem("sys_top", "Top Line Mode", {"OEM Audi", "Custom"}, 0, [](uint8_t val) {
        snooped_top_dirty = true; 
    });
    
    s_top_custom_l = new SettingItem("top_c_l", "Top Links", {"Leer", "Ladedruck", "Oel-Temp"}, 1, [](uint8_t val) {
        snooped_top_dirty = true; 
    });

    s_top_custom_r = new SettingItem("top_c_r", "Top Rechts", {"Leer", "Ladedruck", "Oel-Temp"}, 2, [](uint8_t val) {
        snooped_top_dirty = true; 
    });
    
    s_top->addChild(s_top_custom_l); 
    s_top->addChild(s_top_custom_r); 

    global_settings.addRootItem(s_theme);
    global_settings.addRootItem(s_car_model); 
    global_settings.addRootItem(s_auto);
    global_settings.addRootItem(s_top);

    global_settings.init(); 
    // ---------------------------------

    gateway_init();
    init_mmi_handler();
    
    perform_tacho_handshake();
    
    // timestamp for autostart
    tacho_connect_time = millis();
    os_fully_booted = false;

    last_kl15_state = is_kl15_on;
    os_switch_app(nullptr); 
    
    Serial.println("\n=== BEREIT (Warte 40s auf OS-Boot) ===");
}

void loop() {
    // 1. Ignition check
    if (is_kl15_on != last_kl15_state) {
        last_kl15_state = is_kl15_on;
        
        if (!is_kl15_on) {
            // IGNITION OFF
            Serial.println("\n>>> Zuendung AUS: Schliesse App & fahre System herunter <<<");
            os_switch_app(nullptr); 
            
            // disconnect gracefuly and close channel A8
            disconnect_tacho_gracefully(); 
            
            needs_priming = true; 
            os_fully_booted = false;
            // Stealth mode, there but not sendig to cluster 0x490, rest is passed trough
        } 
        else {
            // IGNITION ON
            Serial.println("\n>>> Zuendung AN: Wecke System auf <<<");
            delay(200); // Give cluster time to wake up
            
            perform_tacho_handshake();
            tacho_connect_time = millis(); // Boot-Timer start
        }
    }

    // --- 2. ONLY RUN WHEN IGNITION IS ON(Stealth Mode protection) 
    if (is_kl15_on) {
        
        // A) Watchdog: GOT A8 FROM CLUSTER WHILE IGNITION IS ON?
        if (!tacho_connected) {
            Serial.println("\n*** VERBINDUNGSABBRUCH ERKANNT - RECONNECT ***");
            perform_tacho_handshake();
            needs_priming = true; 
            tacho_connect_time = millis(); // reset timer
            os_fully_booted = false;       // reinit boot
            if (current_app != nullptr) ui.needs_redraw = true; 
        } 
        else {
            // B) normal status (onyl connected and ign on)
            ui.poll_events();

            // 40s BOOT & AUTOSTART TIMER
            if (!os_fully_booted && (millis() - tacho_connect_time > 40000)) {
                os_fully_booted = true;
                Serial.println("\n>>> OS FULLY BOOTED (40s). Aktiviere Custom TopLine & Autostart <<<");
                
                // forced draw of custom top line (when active)
                snooped_top_dirty = true; 
                
                // run autostart
                if (s_auto->value == 1 && current_app == nullptr) {
                    os_switch_app(&app_launcher);
                }
            }

            // SMARTES PRIMING
            if (needs_priming) {
                ui.primeGraphicsBuffer();
                needs_priming = false;
                snooped_top_dirty = true; 
            }

            // reconnect after pushing out
            static uint32_t last_redraw_time = 0;
            if (ui.needs_redraw && current_app != nullptr) {
                if (millis() - last_redraw_time > 2000) {
                    last_redraw_time = millis();
                    ui.needs_redraw = false; 
                    current_app->onRedraw(); 
                }
            }

            // input abstraction
            if (Serial.available() > 0) {
                char cmd = Serial.read();
                if (cmd == '\r' || cmd == '\n') return; 

                if (cmd >= '0' && cmd <= '4') {
                    debug_level = cmd - '0';
                    return;
                }

                InputEvent event = BTN_NONE;
                if (cmd == 'w') event = BTN_UP;
                else if (cmd == 's') event = BTN_DOWN;
                else if (cmd == 'e') event = BTN_OK;
                else if (cmd == 'm') event = BTN_MODE;
                else if (cmd == 'l') event = BTN_OK_LONG; 

                if (event == BTN_OK_LONG && current_app == nullptr) {  
                    os_switch_app(&app_launcher); 
                    event = BTN_NONE; 
                } 
                
                if (event != BTN_NONE && current_app != nullptr) {
                    current_app->handleInput(event);
                }
            }

            // TOP LINE RENDERING
            if (snooped_top_dirty && !needs_priming) { 
                Serial.println("--- Zeichne Top Line (Smart Mode) ---");
                if (ui.updateTopLine()) {
                    snooped_top_dirty = false;
                } else {
                    os_active_wait(50);
                }
            }

            // Live-Updates
            if (current_app != nullptr) {
                current_app->onTick();
            }
        }
    }
    
    // short brake for FreeRTOS
    vTaskDelay(pdMS_TO_TICKS(10));
}
