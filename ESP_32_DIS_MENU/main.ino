#include <Arduino.h>
#include <esp_task_wdt.h>
#include "nvs_flash.h" 
#include "driver/gpio.h"
#include "esp_sleep.h"
#include "lang.h"

// --- LEVEL 1 to 3 (Hardware, Router, State Machines) ---
#include "hal_can.h"
#include "gateway.h"
#include "stack_tacho.h"
#include "stack_mmi.h"
#include "bap_transport.h"

// --- LEVEL 4 to 6 (Daten, UI, Apps) ---
#include "can_data.h"  // kl15 status
#include "ui_main.h"
#include "settings_registry.h"
#include "app_base.h"
#include "app_settings.h"
#include "app_launcher.h"
#include "app_livedata.h"

// --- Hardware Pins ---
#define PIN_RX_MMI    19
#define PIN_RX_TACHO  11

// --- System variables ---
bool last_kl15_state = false;
bool needs_priming = true; 
uint32_t tacho_connect_time = 0;
bool os_fully_booted = false;
static uint32_t last_topline_update = 0;

// Remember last states to detect connection flanks (disconnect/connect)
TachoState last_tacho_state = TACHO_OFFLINE;

// =========================================================================
// CENTRAL INPUT PROCESSING & CAN PARSER
// =========================================================================
void process_system_input(InputEvent event) {
    if (event == BTN_NONE) return;

    // 1. Open App Launcher on MODE long press (only if no app is active and cluster is ready)
    if (event == BTN_MODE_LONG && current_app == nullptr && stack_tacho_get_state() == TACHO_READY) {  
        Serial.println("[INPUT] Öffne ESP-Menü...");
        os_switch_app(&app_launcher); 
        return; 
    }

    // 2. Forward input to active app
    if (current_app != nullptr && stack_tacho_get_state() == TACHO_READY) {
        // --- ZONE LOCK CHECK ---
        // When the cluster locks a zone, it means the cluster needs it, we block all input to that zone to prevent conflicts.
        // BTN_MODE is an exception, because the user should always be able to break out of a locked zone by opening the launcher.
        if (ui.is_zone_locked[0x02] && event != BTN_MODE) {
            Serial.println("[INPUT] Abgewiesen: Zone 02 ist vom Tacho gesperrt!");
        } else {
            current_app->handleInput(event);
        }
    }
}

// --- MFSW CAN-PARSER ---
// Is called when ID 5C4 is received.
void parse_mfl_can_message(const uint8_t* data) {
    static uint8_t last_d0 = 0;
    static uint8_t last_d2 = 0;
    
    uint8_t d0 = data[0];
    uint8_t d2 = data[2];
    
    InputEvent event = BTN_NONE;

    // --- flank detection from car behaviour ---
    
    // MODE button (left)
    if (d0 == 0x02 && last_d0 == 0x01) event = BTN_MODE;      // Release after short press
    if (d0 == 0x00 && last_d0 == 0x04) event = BTN_MODE_LONG; // Release after long press (directly to 00)
    
    // OK Taste (Scrollrad Links drücken)
    if (d0 == 0x20 && last_d0 == 0x10) event = BTN_OK;        // Release after short press
    if (d0 == 0x00 && last_d0 == 0x40) event = BTN_OK_LONG;   // Release after long press (directly to 00)
    
    // Scroll wheel left (Up / Down)
    if (d2 == 0x01 && last_d2 != 0x01) event = BTN_UP;
    if (d2 == 0x0F && last_d2 != 0x0F) event = BTN_DOWN;

    last_d0 = d0;
    last_d2 = d2;

    // push event to central handler
    if (event != BTN_NONE) {
        process_system_input(event);
    }
}


// =========================================================================
// SETUP
// =========================================================================
void setup() {
    Serial.begin(115200);
    
    Serial.println("\n--- ESP32 Kaltstart ---");
    delay(1000); // short delay to allow serial monitor to connect on reset
    
    // NVS initialize for settings storage.
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    
    Serial.println("\n=== Audi A8 DIS OS startet ===");

    // --- BUILD GLOBAL SETTINGS ---
    s_theme = new SettingItem("sys_theme", STR_THEME, {STR_WHITE_GREEN, STR_RED_MEDIA}, 1, [](uint8_t val) {
        uint8_t t = (val == 1) ? 0x06 : 0x01;
        ui.applyTheme(t);
    });
    
    s_language = new SettingItem("sys_lang", STR_LANGUAGE, {STR_ENGLISH, STR_DEUTSCH, STR_ESPANOL, STR_FRANCAIS, STR_POLSKI, STR_CESTINA}, 0, [](uint8_t val) { 
        set_language(val); 
        ui.needs_redraw = true;
        snooped_top_commit = true; 
    });
    
    s_car_model = new SettingItem("sys_car", STR_CAR_MODEL, {STR_A6_Q7, STR_A8}, 1, [](uint8_t val) {
        snooped_top_commit = true; 
    });

    s_debug = new SettingItem("sys_debug", STR_DEBUG_LEVEL, {STR_OFF, STR_TEXT, STR_ONLY_MMI, STR_ONLY_TACHO, STR_ALL}, 4, [](uint8_t val) {
        debug_level = val;
        Serial.printf("\n[SYSTEM] Debug-Level geaendert auf: %d\n", debug_level);
    });
    
    s_auto = new SettingItem("sys_auto", STR_AUTOSTART, {STR_OFF, STR_MENU, STR_LIVE_DATA}, 0);
    s_top = new SettingItem("sys_top", STR_TOP_LINE, {STR_OEM_AUDI, STR_CUSTOM}, 0, [](uint8_t val) { snooped_top_commit = true; }); 
    s_top_custom_l = new SettingItem("top_c_l", STR_LEFT_DATA, {STR_EMPTY, STR_BOOST, STR_OIL_TEMP}, 1, [](uint8_t val) { snooped_top_commit = true; }); 
    s_top_custom_r = new SettingItem("top_c_r", STR_RIGHT_DATA, {STR_EMPTY, STR_BOOST, STR_OIL_TEMP}, 2, [](uint8_t val) { snooped_top_commit = true; });
    
    s_top->addChild(s_top_custom_l); 
    s_top->addChild(s_top_custom_r); 
    global_settings.addRootItem(s_theme);
    global_settings.addRootItem(s_language);
    global_settings.addRootItem(s_car_model); 
    global_settings.addRootItem(s_auto);
    global_settings.addRootItem(s_top);
    global_settings.addRootItem(s_debug);
    global_settings.init(); 
    set_language(s_language->value);
    debug_level = s_debug->value;

    // --- START SUBSYSTEM ---
    gateway_init();      // Start HAL and Router
    stack_tacho_init();  // Start cluster-logic
    stack_mmi_init();    // Start MMI-Snooper

    // --- APP BEHAVIOR CONFIGURE ---
    app_launcher.reset_on_start = true;  // Launcher vergisst die Position und startet oben
    app_settings.reset_on_start = true;

    // --- REGISTER APPS IN LAUNCHER ---
    // This order is shown on the car display
    app_launcher.registerApp(SYM_CAR, STR_LIVE_DATA, &app_livedata);    // live_data
    app_launcher.registerApp(SYM_FAX, STR_DIAGNOSTICS, nullptr);  // placehlder for future diagnostics app
    app_launcher.registerApp(SYM_FACTORY, STR_SETTINGS, &app_settings); // settings
    app_launcher.registerApp(SYM_BIG_SPACE, STR_CLOSE_MENU, nullptr);   // nullptr closes the menu when selected
    
    last_kl15_state = is_kl15_on;
    os_switch_app(nullptr); 

    // =========================================================================
    // BI-DIRECTONAL WAKE-ON-CAN CONFIGUREN
    // =========================================================================
    gpio_wakeup_enable((gpio_num_t)PIN_RX_MMI, GPIO_INTR_LOW_LEVEL);   // Pin 19
    gpio_wakeup_enable((gpio_num_t)PIN_RX_TACHO, GPIO_INTR_LOW_LEVEL); // Pin 11
    
    // activates GPIO wakeup functionality. The ESP32 will wake up from deep sleep when the specified GPIOs are triggered.
    esp_sleep_enable_gpio_wakeup();

    // --- HARDWARE WATCHDOG ACTIVATION ---
    // 3 sec timeout, only monitor the main loop task (idle_core_mask=0), trigger panic (reset) on timeout
    esp_task_wdt_config_t twdt_config = {
        .timeout_ms = 3000,
        .idle_core_mask = 0,    // IDLE CORE MONITORING: 0 = loop(), 1 = Core 0, 2 = Core 1, 3 = both cores
        .trigger_panic = true   // hard-reset when the watchdog is not fed in time. WARNING: If you set this to false, the ESP32 will NOT reset on watchdog timeout, which can lead to a frozen state if your loop gets stuck. Only set to false if you have another mechanism to recover from hangs!
    };
    esp_task_wdt_init(&twdt_config); 
    esp_task_wdt_add(NULL); // survialance for the current task (loop)

    Serial.println("System: Bi-direktionales Wake-on-CAN ist scharfgestellt.");
    Serial.println("\n=== OS BEREIT (Warte auf Zuendung) ===");
}

// =========================================================================
// LOOP
// =========================================================================
void loop() {
    // feed watchdog at the beginning
    esp_task_wdt_reset();

    // =========================================================================
    // 1. ROUTER & STATE MACHINES (Have to be fast!)
    // =========================================================================
    gateway_tick();
    stack_mmi_tick();
    stack_tacho_tick(is_kl15_on);
    bap_async_tick();

    // check status for cluster connection (flank detection for connect/disconnect)
    TachoState current_tacho_state = stack_tacho_get_state();
    
    // =========================================================================
    // 2. IGNITION STATUS CHECK (falnk detection for kl15 on/off)
    // =========================================================================
    static bool kl15_was_on = true; // remember last state to detect flanks

    if (!is_kl15_on && kl15_was_on) {
        kl15_was_on = false; // fllank detected, dont check again until it turns on again
        
        Serial.println("\n>>> Zuendung AUS: Stoppe Apps & leere VRAM <<<");
        
        if (current_app != nullptr) {
            current_app->onStop();
            current_app = nullptr;
        }
        
        memset(&mmi_vram, 0, sizeof(MmiShadowVRAM)); 
        ui.current_active_zone = 0x00; 
        ui.is_top_line_split = false;
        os_fully_booted = false;
    } 
    else if (is_kl15_on && !kl15_was_on) {
        kl15_was_on = true; //Ignition is on again, re-enable flank detection
    }
        
    // =========================================================================
    // 3. CONNECTION TRANSITION CHECK (flank detection)
    // =========================================================================
    if (current_tacho_state == TACHO_READY && last_tacho_state != TACHO_READY) {
        Serial.println("\n*** VERBINDUNG ZUM TACHO HERGESTELLT ***");
        tacho_connect_time = millis(); 
        needs_priming = true; 
        os_fully_booted = false;
        ui.clearBuffer();
        if (current_app != nullptr) ui.needs_redraw = true; 
    } 
    else if (current_tacho_state != TACHO_READY && last_tacho_state == TACHO_READY) {
        Serial.println("\n*** VERBINDUNGSABBRUCH ZUM TACHO ***");
        ui.current_active_zone = 0x00; 
    }
    last_tacho_state = current_tacho_state;


    // =========================================================================
    // 4. ONLY RUN, WHEN CLUSTER IS READY (UI & APPS)
    // =========================================================================
    if (current_tacho_state == TACHO_READY) {

        // --- MMI COMMIT PIPELINE ---
        if (snooped_stop_z1) { snooped_stop_z1 = false; if(ui.is_oem_screen) ui.stop_zone(0x01); }
        if (snooped_stop_z2) { snooped_stop_z2 = false; if(ui.is_oem_screen) ui.stop_zone(0x02); }
        if (snooped_stop_z3) { snooped_stop_z3 = false; if(ui.is_oem_screen) ui.stop_zone(0x03); }

        // --- DIRECT START WITHOUT DELAY ---
        if (needs_priming) {
            ui.primeGraphicsBuffer();
            needs_priming = false;
            
            os_fully_booted = true;    // Custom Top Line is now allowed in updateTopLine()
            snooped_top_commit = true; //foreces updateTopLine to draw immediately
            
            Serial.println("\n>>> Tacho geprimed. Aktiviere Custom TopLine & Autostart sofort <<<");
            if (s_auto->value == 1 && current_app == nullptr) {
                os_switch_app(&app_launcher);
            }
        }

        if (mmi_vram.theme_dirty || snooped_middle_commit || ui.force_oem_redraw) {
            if (!ui.is_oem_screen) {
                mmi_vram.theme_dirty = false;
                snooped_middle_commit = false; 
            } else {
                if (ui.force_oem_redraw) stack_mmi_force_redraw_flags();
                
                if (mmi_vram.theme_dirty) {
                    ui.req_commit_theme = true;
                    ui.active_theme = mmi_vram.color_theme;
                    mmi_vram.theme_dirty = false;
                }
                if (snooped_middle_commit || ui.force_oem_redraw) {
                    ui.req_commit_z2 = true;
                    snooped_middle_commit = false;
                }
                ui.force_oem_redraw = false;
            }
        }
        
        static uint32_t last_redraw_time = 0;
        if (ui.needs_redraw && current_app != nullptr) {
            if (millis() - last_redraw_time > 2000) {
                last_redraw_time = millis();
                ui.needs_redraw = false; 
                current_app->onRedraw(); 
            }
        }

        if (snooped_top_commit && !needs_priming) {  
            Serial.println("--- Zeichne Top Line (Smart Mode) ---");
            if (ui.updateTopLine()) {
                snooped_top_commit = false; 
            }
        }

        // When we are NOT in the ESP menu (OEM screen visible)
        // AND the custom top line is activated
        if (current_app == nullptr && s_top != nullptr && s_top->value == 1) {
            
            // every 1000ms, force an update of the values
            if (millis() - last_topline_update > 1000) {
                snooped_top_commit = true; //forces the router to call updateTopLine() in the UI, which will redraw the top line with the latest values from the settings (e.g. if the user changed from boost to oil temp)
                last_topline_update = millis();
            }
        }

        // --- THE MOST IMPORTANT CALL: TICK ---
        ui.tick();

        if (current_app != nullptr) {
            current_app->onTick();
        }
    }

    // =========================================================================
    // 5. INPUT ABSTRACTION (Serial -> InputEvent)
    // =========================================================================
    if (Serial.available() > 0) {
        char cmd = Serial.read();
        
        // --- 1. Hotkeys for quick Debugging ( 0 - 4) ---
        if (cmd >= '0' && cmd <= '4') {
            uint8_t new_level = cmd - '0';
            debug_level = new_level; // sets filter active immediately
            if (s_debug != nullptr) {
                s_debug->value = new_level; // update the value in the settings menu (only RAM)
            }
            Serial.printf("\n[SYSTEM] Debug-Level per Hotkey auf %d gesetzt (Temporaer)!\n", debug_level);
        } 
        // --- 2. normal button simulation ---
        else if (cmd != '\r' && cmd != '\n') {
            InputEvent event = BTN_NONE;
            if (cmd == 'w') event = BTN_UP;
            else if (cmd == 's') event = BTN_DOWN;
            else if (cmd == 'e') event = BTN_OK;
            else if (cmd == 'm') event = BTN_MODE;
            else if (cmd == 'l') event = BTN_OK_LONG; 

            // This allows us to simulate button presses via the serial console
            process_system_input(event);
        }
    }
    
    // Short delay for FreeRTOS (5ms is enough since we are not blocking anymore!)
    vTaskDelay(pdMS_TO_TICKS(5));

    // =========================================================================
    // 6. POWER MANAGEMENT (LIGHT SLEEP / BUS-RUHE)
    // =========================================================================
    // When ignition is off AND there was NO CAN activity for 5 seconds
    if (!is_kl15_on && (millis() - last_bus_activity > 5000)) {
        
        if (debug_level > 0) {
            //If we are in debug mode, we do NOT go to sleep, to allow debugging via serial console. We just print a warning every 5 seconds to remind the user to set debug level to 0 for proper sleep functionality.
            // to prevent disconneting serial from usb
            static uint32_t last_warn = 0;
            if (millis() - last_warn > 5000) {
                Serial.println("[POWER] Bus ruhig. Sleep blockiert durch Debug-Level > 0");
                last_warn = millis();
            }
        }
        else {
            Serial.println("\n[POWER] CAN-Bus ist ruhig. Gehe in Light Sleep...");
            Serial.flush(); 
            
            //watchdog for sleep mode disable!
            esp_task_wdt_delete(NULL);
            
            esp_light_sleep_start();
            
            // ESP32 wakes up -> reactivate watchdog immediately!
            esp_task_wdt_add(NULL);
            
            Serial.println("\n[POWER] Wake-Up durch CAN-Aktivitaet!");
            last_bus_activity = millis(); 
        }
    }
}
