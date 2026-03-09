#include "bap_transport.h"
#include "can_data.h"
#include "gateway.h"

bool bap_wait_for_msg(QueueHandle_t q, twai_message_t *msg, uint32_t timeout_ms) {
    return xQueueReceive(q, msg, pdMS_TO_TICKS(timeout_ms)) == pdPASS;
}

void bap_send_ack(twai_handle_t bus, uint32_t tx_id, uint8_t seq) {
    twai_message_t msg = {};
    msg.identifier = tx_id;
    msg.data_length_code = 1;
    msg.data[0] = OP_ACK | (seq % 16);
    twai_transmit_v2(bus, &msg, 0);
    
    if (tx_id == 0x490) print_raw_can("ESP32 -> TACHO", &msg);
    else print_raw_can("ESP32 -> MMI", &msg);
}

// for single frames (claims, releases, highlights)
bool bap_send_data_and_wait_ack(twai_handle_t bus, uint32_t tx_id, QueueHandle_t q, uint8_t* seq_counter, uint8_t* payload, uint8_t len, bool is_end) {
    uint8_t current_seq = *seq_counter;
    uint8_t header = (is_end ? OP_DATA_END : OP_DATA_BODY) | current_seq;
    
    twai_message_t frame = {};
    frame.identifier = tx_id;
    frame.data_length_code = len + 1;
    frame.data[0] = header;
    memcpy(&frame.data[1], payload, len);
    
    twai_transmit_v2(bus, &frame, 0);
    
    if (tx_id == 0x490) print_raw_can("ESP32 -> TACHO", &frame);
    else print_raw_can("ESP32 -> MMI", &frame);

    if (!is_end) {
        *seq_counter = (*seq_counter + 1) % 16;
        vTaskDelay(pdMS_TO_TICKS(10)); 
        return true;
    }

    uint8_t expected_ack = (current_seq + 1) % 16;
    twai_message_t rx_msg;
    uint32_t start = millis();
    
    while (millis() - start < 1500) { 
        if (bap_wait_for_msg(q, &rx_msg, 50)) {
            uint8_t b0 = rx_msg.data[0];
            
            if (b0 == TP_PING || b0 == TP_PONG) {
                start = millis();
                continue;
            }
            
            if ((b0 & 0xF0) == OP_ACK) {
                *seq_counter = b0 & 0x0F; 
                return true;
            } 
            else if ((b0 & 0xF0) == 0x90) { 
                uint8_t wait_ms = (b0 & 0x0F) * 10;
                if (wait_ms == 0) wait_ms = 100;
                
                Serial.printf("-> Hardware Busy (9X). Warte %d ms und resende...\n", wait_ms);
                vTaskDelay(pdMS_TO_TICKS(wait_ms));
                twai_transmit_v2(bus, &frame, 0); 
                if (tx_id == 0x490) print_raw_can("ESP32 -> TACHO (RETRY)", &frame);
                start = millis(); 
            } 
            else if (b0 == TP_RESET) {
                Serial.println("!!! GLOBAL TP: Hardware hat Kanal geschlossen (A8)!");
                return false; 
            }
            else if ((b0 & 0xF0) == OP_DATA_END && rx_msg.data_length_code > 1 && rx_msg.data[1] == OP_ERROR) {
                Serial.printf("!!! GLOBAL TP: Hardware meldet Fehler (09)!\n");
                bap_send_ack(bus, tx_id, (b0 & 0x0F) + 1);
                return false; 
            }
        }
    }
    
    Serial.printf("!!! TIMEOUT: Kein ACK für Seq %d erhalten!\n", current_seq);
    *seq_counter = expected_ack;
    return true; 
}

// block transmit for long texts
bool bap_send_multi_frame(twai_handle_t bus, uint32_t tx_id, QueueHandle_t q, uint8_t* seq_counter, uint8_t* payload, uint8_t total_len) {
    uint8_t start_seq = *seq_counter;
    int retries = 0;

    while (retries < 3) {
        uint8_t current_seq = start_seq; //IMPORTANT: Byte retry use the old seq counter
        uint8_t offset = 0;
        
        // 1. All frames in one black sending at once
        while (offset < total_len) {
            uint8_t chunk_size = total_len - offset;
            if (chunk_size > 7) chunk_size = 7;
            bool is_end = (offset + chunk_size >= total_len);
            
            uint8_t header = (is_end ? OP_DATA_END : OP_DATA_BODY) | (current_seq % 16);
            
            twai_message_t frame = {};
            frame.identifier = tx_id;
            frame.data_length_code = chunk_size + 1;
            frame.data[0] = header;
            memcpy(&frame.data[1], &payload[offset], chunk_size);
            
            twai_transmit_v2(bus, &frame, 0);
            
            if (tx_id == 0x490) print_raw_can(retries > 0 ? "ESP32 -> TACHO (BLOCK-RETRY)" : "ESP32 -> TACHO", &frame);
            else print_raw_can("ESP32 -> MMI", &frame);
            
            offset += chunk_size;
            
            if (!is_end) {
                current_seq = (current_seq + 1) % 16;
                vTaskDelay(pdMS_TO_TICKS(10)); // 10ms pause, seen in can logs 
            }
        }
        
        // 2. wait for ACK for the whole block
        uint8_t expected_ack = (current_seq + 1) % 16;
        twai_message_t rx_msg;
        uint32_t start_time = millis();
        bool got_ack = false;
        bool got_busy = false;
        
        while (millis() - start_time < 1500) {
            if (bap_wait_for_msg(q, &rx_msg, 50)) {
                uint8_t b0 = rx_msg.data[0];
                
                if (b0 == TP_PING || b0 == TP_PONG) {
                    start_time = millis();
                    continue;
                }
                
                if ((b0 & 0xF0) == OP_ACK) {
                    *seq_counter = b0 & 0x0F; 
                    got_ack = true;
                    break;
                } 
                else if ((b0 & 0xF0) == 0x90) { 
                    uint8_t wait_ms = (b0 & 0x0F) * 10;
                    if (wait_ms == 0) wait_ms = 100;
                    
                    Serial.printf("-> Hardware Busy (9X). Warte %d ms und resende KOMPLETTEN BLOCK...\n", wait_ms);
                    vTaskDelay(pdMS_TO_TICKS(wait_ms));
                    got_busy = true;
                    break; 
                }
                else if (b0 == TP_RESET) {
                    Serial.println("!!! GLOBAL TP: Hardware hat Kanal geschlossen (A8)!");
                    return false; 
                }
                else if ((b0 & 0xF0) == OP_DATA_END && rx_msg.data_length_code > 1 && rx_msg.data[1] == OP_ERROR) {
                    Serial.printf("!!! GLOBAL TP: Hardware meldet Fehler (09)!\n");
                    bap_send_ack(bus, tx_id, (b0 & 0x0F) + 1);
                    return false; 
                }
            }
        }
        
        // 3. check and result
        if (got_ack) {
            vTaskDelay(pdMS_TO_TICKS(10)); // short brake after success, time fot the cluster to render
            return true; 
        }
        
        if (got_busy) {
            retries++;
            // loop starts from the beginning
            continue; 
        }
        
        Serial.printf("!!! TIMEOUT: Kein ACK für Block (Seq %d) erhalten!\n", current_seq);
        *seq_counter = expected_ack;
        return true; 
    }
    
    return false;
}
