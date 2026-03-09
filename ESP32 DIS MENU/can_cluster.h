#ifndef CAN_CLUSTER_H
#define CAN_CLUSTER_H

#include <Arduino.h>
#include "driver/twai.h"

extern bool tacho_connected;

void perform_tacho_handshake();
void disconnect_tacho();
void disconnect_tacho_gracefully();
bool tacho_send_data_and_wait_ack(uint8_t* payload, uint8_t len, bool is_end = true);
bool tacho_send_multi_frame(uint8_t* payload, uint8_t total_len);

// FEATURE: optional pointer to read payloads
bool wait_for_tacho_msg(twai_message_t *msg, uint32_t timeout_ms);
bool tacho_wait_data_and_ack(uint8_t* out_payload = nullptr, uint8_t* out_len = nullptr);
void ack_tacho(uint8_t seq);

uint8_t get_last_tx_seq(); 
void force_tacho_sync(); 

#endif
