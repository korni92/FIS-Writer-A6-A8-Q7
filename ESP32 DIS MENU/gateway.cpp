#include "gateway.h"
#include "can_data.h"
#include "can_cluster.h"

twai_handle_t twai_bus_auto;   
twai_handle_t twai_bus_tacho;  

QueueHandle_t q_tacho_rx; 
QueueHandle_t q_mmi_rx;   

// setting which DEBUG level is shown in monitor (2 all data)
uint8_t debug_level = 2;

// variables for car status
bool is_kl15_on = false;
bool is_klS_on = false;

//Debug output
void print_raw_can(const char* prefix, twai_message_t* msg) {
    // Level 0 and 1: No RAW CAN data, Level 2 all combined
    if (debug_level < 2) return; 
    
    // Level 3: show only CAN cluster side
    if (debug_level == 3 && strstr(prefix, "MMI") != nullptr) return;
    
    // Level 4:show only CAN MMI side
    if (debug_level == 4 && strstr(prefix, "TACHO") != nullptr) return;

    // Eigentlicher Print-Befehl
    Serial.printf("%-15s | ID: 0x%03X | Len: %d | Data: ", prefix, msg->identifier, msg->data_length_code);
    for(int i = 0; i < msg->data_length_code; i++) {
        Serial.printf("%02X ", msg->data[i]);
    }
    Serial.println();
}

void send_to_tacho(uint8_t* data, uint8_t len) {
    twai_message_t msg = {};
    msg.identifier = 0x490; 
    msg.data_length_code = len;
    memcpy(msg.data, data, len);
    twai_transmit_v2(twai_bus_tacho, &msg, 0);
    print_raw_can("ESP32 -> TACHO", &msg);
}

void send_to_mmi(uint8_t* data, uint8_t len) {
    twai_message_t msg = {};
    msg.identifier = 0x491; 
    msg.data_length_code = len;
    memcpy(msg.data, data, len);
    twai_transmit_v2(twai_bus_auto, &msg, 0);
    print_raw_can("ESP32 -> MMI", &msg);
}

void task_bus_auto_rx(void *arg) {
    twai_message_t msg;
    while (1) {
        if (twai_receive_v2(twai_bus_auto, &msg, portMAX_DELAY) == ESP_OK) {
            
            // check ignition status
            if (msg.identifier == 0x2C5 && msg.data_length_code >= 1) {
                // Bit 0 = Klemme S (Schlüssel steckt)
                // Bit 1 = Klemme 15 (Zündung ein)
                bool new_klS = (msg.data[0] & 0x01) != 0;
                bool new_kl15 = (msg.data[0] & 0x02) != 0;

                if (new_kl15 != is_kl15_on) {
                    is_kl15_on = new_kl15;
                    Serial.printf(">>> ZUENDUNG (Kl.15) ist jetzt %s <<<\n", is_kl15_on ? "AN" : "AUS");
                }
                is_klS_on = new_klS;
            }
            // ------------------------------------------------

            if (msg.identifier == 0x490) {
                xQueueSend(q_mmi_rx, &msg, 0); 
            } else if (msg.identifier != 0x491) {
                twai_transmit_v2(twai_bus_tacho, &msg, 0);
            }
        }
    }
}

void task_bus_tacho_rx(void *arg) {
    twai_message_t msg;
    uint8_t pong[] = {TP_PONG, 0x0F, 0x8A, 0xFF, 0x4A, 0xFF}; 
    
    while (1) {
        if (twai_receive_v2(twai_bus_tacho, &msg, portMAX_DELAY) == ESP_OK) {
            if (msg.identifier == 0x491) {
                print_raw_can("TACHO -> ESP32", &msg);
                
                if (msg.data[0] == TP_PING) { 
                    send_to_tacho(pong, 6); 
                }
                xQueueSend(q_tacho_rx, &msg, 0); 
                
            } else if (msg.identifier != 0x490) {
                if (MMI_ANGESCHLOSSEN) {
                    twai_transmit_v2(twai_bus_auto, &msg, 0);
                }
            }
        }
    }
}

void gateway_init() {
    q_tacho_rx = xQueueCreate(50, sizeof(twai_message_t));
    q_mmi_rx = xQueueCreate(50, sizeof(twai_message_t));

    twai_timing_config_t t_config = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

    twai_general_config_t g_config_auto = TWAI_GENERAL_CONFIG_DEFAULT(GPIO_NUM_18, GPIO_NUM_19, TWAI_MODE_NORMAL);
    g_config_auto.controller_id = 0; 
    ESP_ERROR_CHECK(twai_driver_install_v2(&g_config_auto, &t_config, &f_config, &twai_bus_auto));
    ESP_ERROR_CHECK(twai_start_v2(twai_bus_auto));

    twai_general_config_t g_config_tacho = TWAI_GENERAL_CONFIG_DEFAULT(GPIO_NUM_10, GPIO_NUM_11, TWAI_MODE_NORMAL);
    g_config_tacho.controller_id = 1; 
    ESP_ERROR_CHECK(twai_driver_install_v2(&g_config_tacho, &t_config, &f_config, &twai_bus_tacho));
    ESP_ERROR_CHECK(twai_start_v2(twai_bus_tacho));

    xTaskCreatePinnedToCore(task_bus_auto_rx, "auto_rx", 4096, NULL, 5, NULL, 0);
    xTaskCreatePinnedToCore(task_bus_tacho_rx, "tacho_rx", 4096, NULL, 6, NULL, 0); 
}
