#include "hal_can.h"
#include "driver/twai.h"

// =========================================================================
//HARDWARE PINS (NEED TO MATCH YOUR BOARD!)
// =========================================================================
#define PIN_TX_MMI    18
#define PIN_RX_MMI    19

#define PIN_TX_TACHO  10
#define PIN_RX_TACHO  11

// =========================================================================
// SPI / MCP2515 CONFIGURATION
// =========================================================================
// #define USE_MCP2515

#ifdef USE_MCP2515
#include <mcp_can.h>
#define SPI_CS_COMFORT 10
MCP_CAN mcp_comfort(SPI_CS_COMFORT);
#endif

// =========================================================================
// TWAI HANDLES
// =========================================================================
twai_handle_t twai_bus_mmi;
twai_handle_t twai_bus_tacho;

// --- INITIALIZATION ---
void hal_can_init() {
    Serial.println("HAL: Initialisiere physikalische CAN-Controller...");

    // 1. configuration for MMI side (BUS_TACHO_IN)
    twai_general_config_t g_config_mmi = TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)PIN_TX_MMI, (gpio_num_t)PIN_RX_MMI, TWAI_MODE_NORMAL);
    g_config_mmi.controller_id = 0;  // <--- TWAI 0
    g_config_mmi.tx_queue_len = 50;
    g_config_mmi.rx_queue_len = 50;
    
    twai_timing_config_t t_config_mmi = TWAI_TIMING_CONFIG_500KBITS(); 
    twai_filter_config_t f_config_mmi = TWAI_FILTER_CONFIG_ACCEPT_ALL();

    if (twai_driver_install_v2(&g_config_mmi, &t_config_mmi, &f_config_mmi, &twai_bus_mmi) == ESP_OK) {
        if (twai_start_v2(twai_bus_mmi) == ESP_OK) {
            Serial.println("HAL: TWAI 0 (MMI-Seite) ERFOLGREICH GESTARTET!");
        } else {
            Serial.println("HAL: FEHLER beim Starten von TWAI 0 (MMI)!");
        }
    } else {
        Serial.println("HAL: FEHLER bei der Installation von TWAI 0 (MMI)!");
    }

    // 2. configuration for cluster side (BUS_TACHO_OUT)
    twai_general_config_t g_config_tacho = TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)PIN_TX_TACHO, (gpio_num_t)PIN_RX_TACHO, TWAI_MODE_NORMAL);
    g_config_tacho.controller_id = 1;  // <--- TWAI 1
    g_config_tacho.tx_queue_len = 50;
    g_config_tacho.rx_queue_len = 50;
    
    twai_timing_config_t t_config_tacho = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t f_config_tacho = TWAI_FILTER_CONFIG_ACCEPT_ALL();

    if (twai_driver_install_v2(&g_config_tacho, &t_config_tacho, &f_config_tacho, &twai_bus_tacho) == ESP_OK) {
        if (twai_start_v2(twai_bus_tacho) == ESP_OK) {
            Serial.println("HAL: TWAI 1 (Tacho-Seite) ERFOLGREICH GESTARTET!");
        } else {
            Serial.println("HAL: FEHLER beim Starten von TWAI 1 (Tacho)!");
        }
    } else {
        Serial.println("HAL: FEHLER bei der Installation von TWAI 1 (Tacho)!");
    }

#ifdef USE_MCP2515
    if (mcp_comfort.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK) {
        mcp_comfort.setMode(MCP_NORMAL);
        Serial.println("HAL: Komfort-CAN (MCP2515) OK!");
    }
#endif
}

// --- SEND ---
bool hal_can_send(CanBusID bus, const can_msg_t* msg) {
    if (msg == nullptr) return false;

    twai_message_t hw_msg = {};
    hw_msg.identifier = msg->id;
    hw_msg.data_length_code = msg->dlc;
    hw_msg.extd = msg->is_extended ? 1 : 0;
    memcpy(hw_msg.data, msg->data, msg->dlc);

    switch (bus) {
        case BUS_TACHO_OUT:
            return (twai_transmit_v2(twai_bus_tacho, &hw_msg, 0) == ESP_OK);
        case BUS_TACHO_IN:
            return (twai_transmit_v2(twai_bus_mmi, &hw_msg, 0) == ESP_OK);
        case BUS_COMFORT:
#ifdef USE_MCP2515
            return (mcp_comfort.sendMsgBuf(msg->id, msg->is_extended ? 1 : 0, msg->dlc, msg->data) == CAN_OK);
#endif
        default: return false;
    }
}

// --- RECEIVE (Zero-Latency, Non-Blocking) ---
bool hal_can_receive(CanBusID bus, can_msg_t* msg) {
    if (msg == nullptr) return false;

    twai_message_t hw_msg;
    esp_err_t err = ESP_FAIL;

    switch (bus) {
        case BUS_TACHO_OUT:
            err = twai_receive_v2(twai_bus_tacho, &hw_msg, 0); // 0 = not blocking
            break;
        case BUS_TACHO_IN:
            err = twai_receive_v2(twai_bus_mmi, &hw_msg, 0);
            break;
        case BUS_COMFORT:
#ifdef USE_MCP2515
            if (mcp_comfort.checkReceive() == CAN_MSGAVAIL) {
                mcp_comfort.readMsgBuf(&msg->id, &msg->dlc, msg->data);
                msg->is_extended = mcp_comfort.isExtendedFrame();
                return true;
            }
#endif
            return false;
        default: return false;
    }

    if (err == ESP_OK) {
        msg->id = hw_msg.identifier;
        msg->dlc = hw_msg.data_length_code;
        msg->is_extended = hw_msg.extd;
        memcpy(msg->data, hw_msg.data, hw_msg.data_length_code);
        return true;
    }

    return false;
}

// BUS-OFF RECOVERY TICK
// This fuction handles hardware crashes (e.g. due to voltage spikes or loose connections)
void hal_can_tick() {
    twai_status_info_t status;
    
    // 1. Check MMI Bus
    if (twai_get_status_info_v2(twai_bus_mmi, &status) == ESP_OK) {
        if (status.state == TWAI_STATE_BUS_OFF) {
            Serial.println("HAL: [FATAL] MMI CAN BUS-OFF! Initiiere Recovery...");
            twai_initiate_recovery_v2(twai_bus_mmi);
        } else if (status.state == TWAI_STATE_STOPPED && status.msgs_to_tx == 0) {
            twai_start_v2(twai_bus_mmi);
            Serial.println("HAL: MMI CAN Recovery abgeschlossen. Bus läuft wieder.");
        }
    }

    // 2. Check Cacho Bus
    if (twai_get_status_info_v2(twai_bus_tacho, &status) == ESP_OK) {
        if (status.state == TWAI_STATE_BUS_OFF) {
            Serial.println("HAL: [FATAL] TACHO CAN BUS-OFF! Initiiere Recovery...");
            twai_initiate_recovery_v2(twai_bus_tacho);
        } else if (status.state == TWAI_STATE_STOPPED && status.msgs_to_tx == 0) {
            twai_start_v2(twai_bus_tacho);
            Serial.println("HAL: TACHO CAN Recovery abgeschlossen. Bus läuft wieder.");
        }
    }
}
