#ifndef BAP_TRANSPORT_H
#define BAP_TRANSPORT_H

#include <Arduino.h>
#include "driver/twai.h"
#include "freertos/queue.h"

// global transport functions for MMI Can and Cluster Can
bool bap_wait_for_msg(QueueHandle_t q, twai_message_t *msg, uint32_t timeout_ms);
void bap_send_ack(twai_handle_t bus, uint32_t tx_id, uint8_t seq);
bool bap_send_data_and_wait_ack(twai_handle_t bus, uint32_t tx_id, QueueHandle_t q, uint8_t* seq_counter, uint8_t* payload, uint8_t len, bool is_end);
bool bap_send_multi_frame(twai_handle_t bus, uint32_t tx_id, QueueHandle_t q, uint8_t* seq_counter, uint8_t* payload, uint8_t total_len);

#endif
