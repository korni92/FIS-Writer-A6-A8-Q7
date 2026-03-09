#include <string.h>
#include "can_mmi.h"
#include "bap_transport.h"
#include "gateway.h"
#include "can_data.h"

uint8_t tx_seq_mmi = 0;
bool mmi_connected = false;
uint32_t last_mmi_rx = 0; 
bool param1_sent = false;

// MMI snooper variables
char snooped_top_line[20] = "";
uint8_t snooped_top_color = 0x00;
bool snooped_top_dirty = false;

// buffer to reconstruct chuncked messages (multi-frame)
uint8_t rx_payload_buffer[100];
uint8_t rx_payload_len = 0;

void process_snooped_mmi_payload(uint8_t* payload, uint8_t len) {
    if (len >= 4 && payload[0] == OP_WRITE_TEXT) { // 0xE0
        uint8_t line_id = payload[2];
        uint8_t color_id = payload[3];

        if (line_id == 0x01) { // only top line for oem mode line id 01
            uint8_t text_len = payload[1] - 2; // lenght we expect
            if (text_len > 18) text_len = 18;

            char new_text[20] = {0};
            memcpy(new_text, &payload[4], text_len);
            new_text[text_len] = '\0';

            // did data in line id 01 change?
            if (strcmp(snooped_top_line, new_text) != 0 || snooped_top_color != color_id) {
                strcpy(snooped_top_line, new_text);
                snooped_top_color = color_id;
                snooped_top_dirty = true; // tells main.ino to redraw
                
                Serial.printf("\n>>> MMI SNOOPER: Top Line Update: '%s' (Farbe: %02X) <<<\n", snooped_top_line, snooped_top_color);
            }
        }
    }
}

// OWN TASK FOR MMI, so it doesnt get blocked by cluster stuff
void task_mmi_protocol(void *arg) {
    while (1) {
        handle_mmi_protocol(); // Unsere Funktion
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void init_mmi_handler() {
    last_mmi_rx = millis();
    // starts mmi can as own background prozess (priority 4)
    xTaskCreatePinnedToCore(task_mmi_protocol, "mmi_proto", 4096, NULL, 4, NULL, 0);
}

// wrapper function
bool wait_for_mmi_msg(twai_message_t *msg, uint32_t timeout_ms) {
    return bap_wait_for_msg(q_mmi_rx, msg, timeout_ms);
}

void ack_mmi(uint8_t seq) {
    bap_send_ack(twai_bus_auto, 0x491, seq);
}

bool mmi_send_data_and_wait_ack(uint8_t* payload, uint8_t len, bool is_end = true) {
    return bap_send_data_and_wait_ack(twai_bus_auto, 0x491, q_mmi_rx, &tx_seq_mmi, payload, len, is_end);
}
// --------------------------

void handle_mmi_protocol() {
    twai_message_t msg;
    
    if (mmi_connected && millis() - last_mmi_rx > 2000) {
        uint8_t ping[] = {TP_PING};
        send_to_mmi(ping, 1);
        last_mmi_rx = millis(); 
    }

    if (wait_for_mmi_msg(&msg, 10)) {
        last_mmi_rx = millis(); 
        uint8_t b0 = msg.data[0];
        uint8_t type = b0 & 0xF0;
        uint8_t rx_seq = b0 & 0x0F;

        print_raw_can("AUTO(MMI)->ESP", &msg);

        if (b0 == TP_OPEN) {
            Serial.println("MMI fordert Open an (A0). Sende A1 Pong...");
            tx_seq_mmi = 0;
            param1_sent = false; 
            rx_payload_len = 0; // Buffer reset
            uint8_t pong[] = {TP_PONG, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF};
            send_to_mmi(pong, 6);
            mmi_connected = true;
        }
        else if (b0 == TP_PONG) {
            // ignore
        }
        else if (b0 == TP_PING) {
            uint8_t pong[] = {TP_PONG, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF};
            send_to_mmi(pong, 6);
        }
        else if (b0 == TP_RESET) {
            Serial.println("!!! MMI hat Reset (A8) gesendet!");
            mmi_connected = false;
        }
        else if (type == OP_DATA_END || type == OP_DATA_BODY) {
            
            // 1. copie data in the reconstructed buffer
            uint8_t chunk_len = msg.data_length_code - 1;
            if (rx_payload_len + chunk_len < sizeof(rx_payload_buffer)) {
                memcpy(&rx_payload_buffer[rx_payload_len], &msg.data[1], chunk_len);
                rx_payload_len += chunk_len;
            }

            // 2. ack MMI frame
            if (type == OP_DATA_END) {
                ack_mmi(rx_seq + 1); 
            }

            // 3. if message is empty, we still work with it
            if (type == OP_DATA_END) { 
                // --- SNOOPING START ---
                process_snooped_mmi_payload(rx_payload_buffer, rx_payload_len);
                // --- SNOOPING ENDE ---

                vTaskDelay(pdMS_TO_TICKS(50)); 
                uint8_t* payload = rx_payload_buffer;
                uint8_t len = rx_payload_len;

                // fake cluster answere to keep MMI channel open
                if (len >= 4 && payload[0] == 0x00 && payload[1] == 0x02 && payload[2] == 0x4D && payload[3] == 0x02) {
                    if (!is_kl15_on) {
                        uint8_t resp[] = {0x01, 0x03, 0x48, 0x01, 0x02}; // Standby
                        mmi_send_data_and_wait_ack(resp, 5);
                    } else {
                        uint8_t resp[] = {0x01, 0x03, 0x48, 0x02, 0x02}; // Ready
                        mmi_send_data_and_wait_ack(resp, 5);
                    }
                }
                else if (len >= 4 && payload[0] == 0x00 && payload[1] == 0x02 && payload[2] == 0x4D && payload[3] == 0x01) {
                    uint8_t resp[] = {0x01, 0x03, 0x48, 0x02, 0x01};
                    mmi_send_data_and_wait_ack(resp, 5);
                }
                else if (len >= 3 && payload[0] == 0x02 && payload[1] == 0x01 && payload[2] == 0x48) {
                    uint8_t r1[] = {0x03, 0x10, 0x48, 0x0B, 0x50, 0x08, 0x0C};
                    mmi_send_data_and_wait_ack(r1, 7, false); 
                    
                    uint8_t r2[] = {0x45, 0x30, 0x39, 0x00, 0x00, 0x01, 0x00};
                    mmi_send_data_and_wait_ack(r2, 7, false); 
                    
                    uint8_t r3[] = {0x02, 0x01, 0x01, 0x10};
                    mmi_send_data_and_wait_ack(r3, 4, true);  
                }
                else if (len >= 3 && payload[0] == OP_SUBSCRIBE && payload[1] == 0x01) {
                    uint8_t zone = payload[2];
                    uint8_t resp[] = {0x31, 0x03, zone, 0x01, 0x04};
                    mmi_send_data_and_wait_ack(resp, 5);
                }
                else if (len >= 3 && payload[0] == OP_RELEASE && payload[1] == 0x01) {
                    uint8_t zone = payload[2];
                    uint8_t resp[] = {OP_CONFIRM, 0x02, zone, 0x03}; 
                    mmi_send_data_and_wait_ack(resp, 4);
                }
                else if (len >= 3 && payload[0] == OP_STOP && payload[1] == 0x01) {
                    uint8_t zone = payload[2];
                    uint8_t resp[] = {OP_CONFIRM, 0x02, zone, 0x04}; 
                    mmi_send_data_and_wait_ack(resp, 4);
                }

                // free buffer for next message
                rx_payload_len = 0; 
            }
        }
    }
}
