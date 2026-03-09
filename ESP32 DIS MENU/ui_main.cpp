extern bool os_fully_booted;
#include "ui_main.h"
#include "settings_registry.h"
#include "can_cluster.h"
#include "can_data.h"
#include "can_mmi.h"

// global instanz of display managers
DISDisplayManager ui;

// ==============================================================================
// 1. SETUP & HIGH-LEVEL API (SHADOW BUFFER)
// ==============================================================================

DISDisplayManager::DISDisplayManager() {
    clearBuffer();
}

void DISDisplayManager::clearBuffer() {
    for (int i = 1; i <= 9; i++) {
        memset(lines[i].text, 0, sizeof(lines[i].text));
        lines[i].color = 0x00;
        lines[i].dirty = true; // first commit = clean everything
        lines[i].is_empty = true;
    }
    indicator_dirty = true;
    current_highlight_line = 0;
    current_arrow_cfg = 0;
}

void DISDisplayManager::setLine(uint8_t line_id, const char* text, uint8_t color) {
    if (line_id >= 1 && line_id <= 9) {
        // smart tracking = did something change?
        if (strcmp(lines[line_id].text, text) != 0 || lines[line_id].color != color) {
            strncpy(lines[line_id].text, text, 19);
            lines[line_id].text[19] = '\0';
            lines[line_id].color = color;
            lines[line_id].dirty = true; // only updating what is necessary
        }
        lines[line_id].is_empty = (strlen(text) == 0);
    }
}

void DISDisplayManager::setIndicator(uint8_t line_idx, uint8_t arrow_cfg) {
    // Only mark when the curser moved
    if (current_highlight_line != line_idx || current_arrow_cfg != arrow_cfg) {
        current_highlight_line = line_idx;
        current_arrow_cfg = arrow_cfg;
        indicator_dirty = true;
    }
}

// ==============================================================================
// 2. SMART COMMITS (COMPARE STORGAE VS. HARDWARE)
// ==============================================================================

bool DISDisplayManager::commitMiddleZone() {
    bool text_changed = false;
    
    // check if there are text updates in 05 - 09
    for (int i = 5; i <= 9; i++) {
        if (lines[i].dirty) text_changed = true;
    }

    if (text_changed) {
        // focus to middle zone 02
        claim_zone(0x02); 

        for (int i = 5; i <= 9; i++) {
            if (lines[i].dirty) {
                if (lines[i].is_empty) write_raw_line(i, " ", 0x00);
                else write_raw_line(i, lines[i].text, lines[i].color);
                lines[i].dirty = false; 
            }
        }
        
        if (indicator_dirty) {
            send_raw_highlight(current_highlight_line, current_arrow_cfg);
            indicator_dirty = false;
        }

        // Render!
        return release_zone(0x02); 
    } 
    else if (indicator_dirty) {
        // --- ONLY CURSER MOVED ---
        
        // focus has to be at zone 02
        // if radio stole focus to zone 01
        claim_zone(0x02); 
        
        send_raw_highlight(current_highlight_line, current_arrow_cfg);
        indicator_dirty = false;
        
        // render new curser
        return release_zone(0x02); 
    }
    
    return true; // nothing to do!
}

bool DISDisplayManager::commitTopZone() {
    Serial.println("UI: Committing Top Zone (01)...");
    claim_zone(0x01);
    
    // Just write ESP32 to init clean
    write_raw_line(0x01, "ESP32", 0x00);
    
    return release_zone(0x01);
}

bool DISDisplayManager::commitFullRedraw() {
    // 1. FIRST build zone 02 menu middle part
    claim_zone(0x02);
    
    // only using line 05 - 09 middle part
    for (int i = 5; i <= 9; i++) {
        if (lines[i].is_empty) {
            write_raw_line(i, " ", 0x00);
        } else {
            write_raw_line(i, lines[i].text, lines[i].color);
        }
        lines[i].dirty = false;
    }
    
    if (indicator_dirty) {
        send_raw_highlight(current_highlight_line, current_arrow_cfg);
        indicator_dirty = false;
    }
    
    if (!release_zone(0x02)) return false;

    // 2. Build zone 01 above the zone 02
    // check if everything is correct
    return updateTopLine();
}

// ==============================================================================
// 3. LOW-LEVEL API
// ==============================================================================

void DISDisplayManager::write_raw_line(uint8_t line_id, const char* text, uint8_t color) {
    uint8_t text_len = strlen(text);
    if (text_len > 18) text_len = 18; 
    
    uint8_t payload_len = 2 + text_len; 
    uint8_t full_payload[25]; 
    full_payload[0] = OP_WRITE_TEXT;
    full_payload[1] = payload_len;
    full_payload[2] = line_id;
    full_payload[3] = color;
    memcpy(&full_payload[4], text, text_len);
    
    uint8_t total_bytes = text_len + 4;
    tacho_send_multi_frame(full_payload, total_bytes);
}

void DISDisplayManager::send_raw_highlight(uint8_t line_idx, uint8_t arrow_cfg) {
    uint8_t payload[] = {OP_INDICATOR, 0x02, line_idx, arrow_cfg};
    tacho_send_data_and_wait_ack(payload, 4);
}

void DISDisplayManager::switch_source(uint8_t source_id) {
    uint8_t payload[] = {OP_SOURCE, 0x01, source_id};
    tacho_send_data_and_wait_ack(payload, 3);
}

void DISDisplayManager::claim_zone(uint8_t zone_id) {
    // SMART TRACKING: are we in the right zone?
    if (current_active_zone == zone_id) {
        // perfect, pointer is correct, no update needed
        return; 
    }

    uint8_t payload[] = {0x36, 0x01, zone_id};
    tacho_send_data_and_wait_ack(payload, 3);
    
    // update the zone we are
    current_active_zone = zone_id;
}

bool DISDisplayManager::release_zone(uint8_t zone_id) {
    uint8_t payload[] = {OP_RELEASE, 0x01, zone_id};
    
    for (int retry = 0; retry < 3; retry++) { 
        if (!tacho_send_data_and_wait_ack(payload, 3)) return false;
        
        twai_message_t rx;
        uint32_t start = millis();
        
        while (millis() - start < 3000) {
            if (wait_for_tacho_msg(&rx, 50)) {
                if (rx.data[0] == TP_PING || rx.data[0] == TP_PONG) {
                    start = millis();
                    continue;
                }

                uint8_t type = rx.data[0] & 0xF0;
                uint8_t seq = rx.data[0] & 0x0F;
                
                if (type == OP_DATA_END) {
                    ack_tacho(seq + 1); 
                    
                    if (rx.data_length_code >= 5 && rx.data[1] == OP_CONFIRM && rx.data[3] == zone_id) {
                        uint8_t status = rx.data[4];
                        
                        if (status == 0x03 || status == 0x04) {
                            return true; 
                        } 
                        // FEATURE: cluster Busy (02) oder Eviction (00) at release!
                        else if (status == 0x02 || status == 0x00) {
                            Serial.printf("-> Cluster blockiert Release für Zone %02X (Status %02X). Sende STOP (34)!\n", zone_id, status);
                            stop_zone(zone_id); // give zone directly back (like MMI does)
                            needs_redraw = true; // tells os to try again after 2seconds
                            return false; 
                        }
                    } 
                } else if (rx.data[0] == TP_RESET) {
                    return false;
                }
            }
        }
    }
    return false;
}

void DISDisplayManager::stop_zone(uint8_t zone_id) {
    uint8_t payload[] = {OP_STOP, 0x01, zone_id};
    tacho_send_data_and_wait_ack(payload, 3);
    
    if (zone_id == 0x02) {
        is_oem_screen = true;
    }
    
    // if we close active zone, cluster looses track
    if (current_active_zone == zone_id) {
        current_active_zone = 0x00; 
    }
}

void DISDisplayManager::poll_events() {
    twai_message_t rx;
    // empty queue without blocking(Timeout = 0)
    while (wait_for_tacho_msg(&rx, 0)) {
        if (rx.data[0] == TP_PING || rx.data[0] == TP_PONG) continue;

        uint8_t type = rx.data[0] & 0xF0;
        uint8_t seq = rx.data[0] & 0x0F;

        if (type == OP_DATA_END) {
            ack_tacho(seq + 1); // ALWAYS ACK!

            // check asynchrone pushout
            if (rx.data_length_code >= 5 && rx.data[1] == OP_CONFIRM) {
                uint8_t zone = rx.data[3];
                uint8_t status = rx.data[4];

                if (status == 0x00) {
                    Serial.printf("!!! TACHO VERDRAENGT UNS ASYNCHRON AUS ZONE %02X (Status 00) !!!\n", zone);
                    stop_zone(zone); // make space (34)
                    needs_redraw = true; // tell OS to rebuild menu
                }
            }
        }
    }
}

void DISDisplayManager::primeGraphicsBuffer() {
    Serial.println("UI: Priming Graphics Buffer (OEM MMI Workaround)...");
    
    // 1. Top Zone claimen
    claim_zone(0x01);
    
    // use MMI Daten or "LOADING..."
    if (strlen(snooped_top_line) > 0) {
        write_raw_line(0x01, snooped_top_line, snooped_top_color);
    } else {
        write_raw_line(0x01, "LOADING...", 0x00);
    }
    
    // 2. Middle Zone claimen (while top zone is open!)
    claim_zone(0x02);
    
    // 3. dummy data for the middle
    write_raw_line(0x05, " ", 0x00);
    
    // 4. just release top zone.
    release_zone(0x01);
    
    Serial.println("UI: Priming beendet. Zone 02 VRAM ist pre-allocated.");
}

bool DISDisplayManager::updateTopLine() {
    if (!s_car_model || !s_top || !s_top_custom_l || !s_top_custom_r) return false;

    uint8_t car_model = s_car_model->value; // 0 = A6/Q7, 1 = A8
    uint8_t top_mode = s_top->value;        // 0 = OEM, 1 = Custom

    // 40 seccond timer to protect cluster at boot
    // In this time we stay in OEM mode
    if (!os_fully_booted) {
        top_mode = 0; 
    }

    bool target_is_split = (car_model == 1 && top_mode == 1);

    // try to prevent ghost pictures
    if (is_top_line_split && !target_is_split) {
        // split top line to oem top line (line 02,03,04 delete)
        claim_zone(0x01);
        write_raw_line(0x02, " ", 0x00);
        write_raw_line(0x03, " ", 0x00);
        write_raw_line(0x04, " ", 0x00);
        release_zone(0x01);
        is_top_line_split = false;
        vTaskDelay(pdMS_TO_TICKS(50)); // let cluster time
    }
    else if (!is_top_line_split && target_is_split) {
        // OEM to split top line (line 01 delete)
        claim_zone(0x01);
        write_raw_line(0x01, " ", 0x00);
        release_zone(0x01);
        is_top_line_split = true;
        vTaskDelay(pdMS_TO_TICKS(50));
    }

    // redraw
    claim_zone(0x01);

    if (target_is_split) {
        // A8 CUSTOM (SPLIT SCREEN
        // middle 03 = MMI
        if (strlen(snooped_top_line) == 0) write_raw_line(0x03, " ", 0x00);
        else write_raw_line(0x03, snooped_top_line, snooped_top_color);

        // left (later data from vehicle_data.h)
        if (s_top_custom_l->value == 1) write_raw_line(0x02, "1.2 Bar", 0x01);
        else if (s_top_custom_l->value == 2) write_raw_line(0x02, "95 C", 0x01);
        else write_raw_line(0x02, " ", 0x00);

        // right (later data from vehicle_data.h)
        if (s_top_custom_r->value == 1) write_raw_line(0x04, "1.2 Bar", 0x01);
        else if (s_top_custom_r->value == 2) write_raw_line(0x04, "95 C", 0x01);
        else write_raw_line(0x04, " ", 0x00);
    } 
    else {
        // A6/Q7 ODER A8 OEM
        if (top_mode == 1) { 
            // A6/Q7 Custom Modus (whole line 01)
            write_raw_line(0x01, "ESP32 A6 Custom", 0x01);
        } else { 
            // OEM for all cars!
            if (strlen(snooped_top_line) == 0) write_raw_line(0x01, " ", 0x00);
            else write_raw_line(0x01, snooped_top_line, snooped_top_color);
        }
    }

    return release_zone(0x01);
}

void DISDisplayManager::applyTheme(uint8_t source_id) {
    Serial.printf("UI: Applying Theme %02X with Zone 02 Focus Shift...\n", source_id);
    claim_zone(0x02);
    write_raw_line(0x05, " ", 0x00); 
    switch_source(source_id);
    release_zone(0x02);
    
    // remember states
    active_theme = source_id;
    is_oem_screen = false;
}
