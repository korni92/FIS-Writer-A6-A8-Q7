#include "app_base.h"
#include "ui_main.h"
#include "can_mmi.h"

BaseApp* current_app = nullptr;

void os_switch_app(BaseApp* new_app) {
    // 1. Close old APP
    if (current_app != nullptr) {
        current_app->onStop();
    }

    // 2. OS-Hardware-Management: Go back to Audi Trip Computer?
    if (new_app == nullptr && current_app != nullptr) {
        Serial.println("OS KERNEL: Schließe ESP-Menü, gebe Tacho an Audi zurück...");
        ui.stop_zone(0x02); // Zone 2 hart schließen
        snooped_top_dirty = true; // Zwingt main.ino, sofort den OEM-Radiosender wiederherzustellen
    }

    // 3. New App
    current_app = new_app;

    // 4. Neue App starten (Die App checkt in onStart selbst, ob ein FullRedraw oder SmoothSwap nötig ist)
    if (current_app != nullptr) {
        current_app->onStart();
    }
}

// Global Helper Fuctions for App development
void os_active_wait(uint32_t ms) {
    uint32_t start = millis();
    while (millis() - start < ms) {
        ui.poll_events(); // Tacho bei Laune halten
        vTaskDelay(pdMS_TO_TICKS(10)); // FreeRTOS atmen lassen
    }
}
