#include "can_cluster.h"
#include "bap_transport.h"
#include "gateway.h"
#include "can_data.h"

uint8_t tx_seq_tacho = 0;
bool tacho_connected = false;

uint8_t get_last_tx_seq() {
    int8_t last_seq = tx_seq_tacho - 1;
    if (last_seq < 0) last_seq = 15;
    return (uint8_t)last_seq;
}

bool wait_for_tacho_msg(twai_message_t *msg, uint32_t timeout_ms) {
    return bap_wait_for_msg(q_tacho_rx, msg, timeout_ms);
}

void ack_tacho(uint8_t seq) {
    bap_send_ack(twai_bus_tacho, 0x490, seq);
}

bool tacho_send_data_and_wait_ack(uint8_t* payload, uint8_t len, bool is_end) {
    bool success = bap_send_data_and_wait_ack(twai_bus_tacho, 0x490, q_tacho_rx, &tx_seq_tacho, payload, len, is_end);
    if (!success) {
        disconnect_tacho(); // error or 0xA8 from cluster -> channel close
    }
    return success;
}

bool tacho_send_multi_frame(uint8_t* payload, uint8_t total_len) {
    bool success = bap_send_multi_frame(twai_bus_tacho, 0x490, q_tacho_rx, &tx_seq_tacho, payload, total_len);
    if (!success) {
        disconnect_tacho(); // error or 0xA8 from cluster -> channel close
    }
    return success;
}

void force_tacho_sync() {
    Serial.println("--- FORCE SYNC: Spamme 00-Frames ---");
    uint8_t dummy_payload[7] = {0};
    for(int i=0; i<8; i++) {
        tacho_send_data_and_wait_ack(dummy_payload, 7, false);
    }
}

// FEATURE: reading payload and 5s timeout if no messages are comming
bool tacho_wait_data_and_ack(uint8_t* out_payload, uint8_t* out_len) {
    twai_message_t rx;
    uint32_t absolute_start = millis();
    uint32_t ping_start = millis();
    
    while (millis() - absolute_start < 5000) { 
        if (wait_for_tacho_msg(&rx, 50)) {
            ping_start = millis(); // Tacho lebt!

            uint8_t type = rx.data[0] & 0xF0;
            uint8_t seq = rx.data[0] & 0x0F;
            
            if (rx.data[0] == TP_RESET) return false;
            if (rx.data[0] == TP_PING || rx.data[0] == TP_PONG) continue; 

            if (type == OP_DATA_END) { 
                ack_tacho(seq + 1); 
                if (rx.data_length_code > 1 && rx.data[1] == OP_ERROR) return false;
                
                // get payload
                if (out_payload && out_len) {
                    *out_len = rx.data_length_code - 1;
                    memcpy(out_payload, &rx.data[1], *out_len);
                }
                return true;
            }
        } else if (millis() - ping_start > 2500) {
            // no pings and no data -> channel close
            return false;
        }
    }
    return false; // absolute 5ms
}

void disconnect_tacho() {
    if (tacho_connected) {
        Serial.println("!!! VERBINDUNGSABBRUCH ZUM TACHO !!! Sende Kanal-Reset (A8)...");
        uint8_t reset_payload[] = {TP_RESET}; // 0xA8
        send_to_tacho(reset_payload, 1);
        tacho_connected = false;
        
        // IMPORTANT: empty cluster queue, that there are no old data when reconnect
        xQueueReset(q_tacho_rx); 
    }
}

void disconnect_tacho_gracefully() {
    if (!tacho_connected) return; // if there is no connection, dont do anything

    Serial.println("\n--- Gebe Tacho-Zonen frei (Zündung AUS) ---");
    
    // empty zones before disconnect (Opcode 34)
    uint8_t payload1[] = {0x34, 0x01, 0x01};
    tacho_send_data_and_wait_ack(payload1, 3);
    
    uint8_t payload2[] = {0x34, 0x01, 0x02};
    tacho_send_data_and_wait_ack(payload2, 3);
    
    uint8_t payload3[] = {0x34, 0x01, 0x03}; 
    tacho_send_data_and_wait_ack(payload3, 3);

    Serial.println("--- Sende A8 Disconnect ---");
    disconnect_tacho(); 
}

void perform_tacho_handshake() {
    while (!tacho_connected) {
        Serial.println("\n--- STARTE TACHO HANDSHAKE ---");
        
        uint8_t reset_payload[] = {TP_RESET};
        send_to_tacho(reset_payload, 1);
        vTaskDelay(pdMS_TO_TICKS(100)); 
        
        tx_seq_tacho = 0;
        xQueueReset(q_tacho_rx); 

        bool got_pong = false;
        for (int versuch = 0; versuch < 5; versuch++) {
            uint8_t open_req[] = {TP_OPEN, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF};
            send_to_tacho(open_req, 6);

            twai_message_t rx;
            uint32_t start_wait = millis();
            while(millis() - start_wait < 100) { 
                if (wait_for_tacho_msg(&rx, 20)) {
                    if (rx.data[0] == TP_PONG) { got_pong = true; break; } 
                    else if (rx.data[0] == TP_RESET) break;
                }
            }
            if (got_pong) break; 
        }

        if (!got_pong) {
            send_to_tacho(reset_payload, 1);
            vTaskDelay(pdMS_TO_TICKS(5000));
            continue; 
        }

        // wait for ignition
        if (!is_kl15_on) Serial.println("--- WARTE AUF ZUENDUNG (KL15) ---");
        while (!is_kl15_on) {
            twai_message_t flush_msg;
            wait_for_tacho_msg(&flush_msg, 500); 
            vTaskDelay(pdMS_TO_TICKS(100));
        }
        Serial.println("--- Zuendung erkannt! Gebe Tacho 1.0s ---");
        vTaskDelay(pdMS_TO_TICKS(1000));

        // parameter polling
        bool param_ready = false;
        while (!param_ready && is_kl15_on) {
            uint8_t p1[] = {0x00, 0x02, 0x4D, 0x02};
            if(!tacho_send_data_and_wait_ack(p1, 4)) break; // A8 Error -> Restart Handshake
            
            uint8_t rx_buf[8];
            uint8_t rx_len = 0;
            if(!tacho_wait_data_and_ack(rx_buf, &rx_len)) {
                // cluster pinged, but no parameters -> retry
                Serial.println("-> Tacho ignoriert Parameter. Warte 1s und frage erneut...");
                vTaskDelay(pdMS_TO_TICKS(1000));
                continue; 
            }

            if (rx_len >= 5 && rx_buf[0] == 0x01 && rx_buf[1] == 0x03 && rx_buf[2] == 0x48) {
                if (rx_buf[4] == 0x02) {
                    param_ready = true;
                    Serial.println("-> Tacho Parameter 1 READY (02 02)!");
                } else {
                    Serial.println("-> Tacho Standby (01 02). Warte 1s...");
                    vTaskDelay(pdMS_TO_TICKS(1000));
                }
            } else {
                param_ready = true; // unkown answere, continou anyway
            }
        }
        if (!param_ready) continue; // if TP brakes -> reconnect

        uint8_t p2[] = {0x00, 0x02, 0x4D, 0x01};
        if(!tacho_send_data_and_wait_ack(p2, 4)) continue;
        if(!tacho_wait_data_and_ack()) continue;
        
        uint8_t p4[] = {0x02, 0x01, 0x48};
        if(!tacho_send_data_and_wait_ack(p4, 3)) continue;
        if(!tacho_wait_data_and_ack()) continue;

        uint8_t z1[] = {OP_SUBSCRIBE, 0x01, 0x01};
        if(!tacho_send_data_and_wait_ack(z1, 3)) continue;
        if(!tacho_wait_data_and_ack()) continue;
        
        uint8_t z2[] = {OP_SUBSCRIBE, 0x01, 0x02};
        if(!tacho_send_data_and_wait_ack(z2, 3)) continue;
        if(!tacho_wait_data_and_ack()) continue;
        
        uint8_t z3[] = {OP_SUBSCRIBE, 0x01, 0x03};
        if(!tacho_send_data_and_wait_ack(z3, 3)) continue;
        if(!tacho_wait_data_and_ack()) continue;

        Serial.println("--- TACHO HANDSHAKE ERFOLGREICH ---");
        tacho_connected = true;
    }
}
