#ifndef BAP_TRANSPORT_H
#define BAP_TRANSPORT_H

#include <Arduino.h>
#include "hal_can.h"

// --- asynchrone states ---
enum BapTxState {
    TX_IDLE,          //bus empty, next job can start
    TX_WAIT_ACK,      // order is out, waiting for Bx or 9x
    TX_MULTI_PACING,  // 10ms break between 0x20 multi-frames
    TX_RECOVER_9X,    //recieved 9X -> adjust seq counter and fire immediately!
    TX_FAIL           //fail after 3 retries
};

// ---  struct for ONE send job ---
struct BapTxJob {
    CanBusID bus;        // choosing the bus to send on
    uint32_t tx_id;      // 0x490
    uint8_t payload[30]; // data to send (max 30 bytes, because of multi-frame)
    uint8_t len;         // lenght of data what will be sent
    bool is_multi_frame; // is is part of a multi-frame message? (0x10 or 0x20)
    bool wait_ack;       // waitung for ACK (B0)
    uint8_t* seq_ptr;    // ponter to external sequence counter (e.g. &tacho_tx_seq)
};

// --- Job-Queue (ring buffer) ---
#define TX_QUEUE_SIZE 64
extern BapTxJob tx_queue[TX_QUEUE_SIZE];
extern volatile uint8_t tx_head;
extern volatile uint8_t tx_tail;

// --- asyncrone manager functions ---
extern BapTxState current_tx_state;
void bap_async_tick();

//-- hook for the router
// here the router throws ALL ACKs (B0) and Confirms (3B) in
void bap_transport_rx_hook(const can_msg_t* msg);

// --- send fuctions for the UI (these only throw jobs into the queue!) ---
bool bap_send_data_and_wait_ack(CanBusID bus, uint32_t tx_id, uint8_t* seq, const uint8_t* payload, uint8_t len, bool wait_ack);
bool bap_send_multi_frame(CanBusID bus, uint32_t tx_id, uint8_t* seq_counter, uint8_t* payload, uint8_t total_len);
void bap_send_ack(CanBusID bus, uint32_t tx_id, uint8_t seq);

// --- unused meanwhile
bool bap_wait_for_rx(uint32_t timeout_ms, can_msg_t* out_msg);

#endif
