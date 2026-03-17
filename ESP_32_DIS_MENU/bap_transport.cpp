#include "bap_transport.h"
#include "gateway.h"
#include "stack_tacho.h"

BapTxJob tx_queue[TX_QUEUE_SIZE];
volatile uint8_t tx_head = 0;
volatile uint8_t tx_tail = 0;

BapTxState current_tx_state = TX_IDLE;
uint32_t tx_state_timer = 0;
uint8_t current_retries = 0;

static void raw_send_frame(CanBusID bus, uint32_t tx_id, uint8_t header, const uint8_t* payload, uint8_t len) {
    can_msg_t frame = {};
    frame.id = tx_id;
    frame.dlc = len + 1;
    frame.is_extended = false;
    frame.data[0] = header;
    if (len > 0) memcpy(&frame.data[1], payload, len);
    
    hal_can_send(bus, &frame);
    print_raw_can(tx_id == 0x490 ? "ESP32 -> TACHO (UI)" : "ESP32 -> MMI (UI)", &frame);
}

void bap_send_ack(CanBusID bus, uint32_t tx_id, uint8_t seq) {
    can_msg_t msg = {};
    msg.id = tx_id;
    msg.dlc = 1;
    msg.is_extended = false;
    msg.data[0] = 0xB0 | (seq % 16); 
    hal_can_send(bus, &msg);
}

// =========================================================================
// asybcronous queue with anti-fragmentation protection
// =========================================================================
bool bap_send_data_and_wait_ack(CanBusID bus, uint32_t tx_id, uint8_t* seq, const uint8_t* payload, uint8_t len, bool wait_ack) {
    uint8_t next_head = (tx_head + 1) % TX_QUEUE_SIZE;
    if (next_head == tx_tail) {
        Serial.println("BAP TRANSPORT: FEHLER! Queue ist voll. Frame verworfen.");
        return false; 
    }

    BapTxJob& job = tx_queue[tx_head];
    job.bus = bus;
    job.tx_id = tx_id;
    memset(job.payload, 0, sizeof(job.payload));
    memcpy(job.payload, payload, len);
    job.len = len;
    job.is_multi_frame = false;
    job.wait_ack = wait_ack;
    
    job.seq_ptr = (uint8_t*)((uint32_t)(*seq)); 
    *seq = (*seq + 1) % 16; 

    tx_head = next_head;
    return true; 
}

bool bap_send_multi_frame(CanBusID bus, uint32_t tx_id, uint8_t* seq_counter, uint8_t* payload, uint8_t total_len) {
    // --- check if the COMPLETE text fits in the queue! ---
    uint8_t chunks_needed = (total_len + 6) / 7; 
    uint8_t free_space = (tx_head >= tx_tail) ? (TX_QUEUE_SIZE - 1 - tx_head + tx_tail) : (tx_tail - tx_head - 1);
    
    if (free_space < chunks_needed) {
        Serial.println("BAP TRANSPORT: SCHUTZ! Zu wenig Platz fuer komplettes Multi-Frame. Ignoriert!");
        return false; // abort before fragmentation occurs!
    }
    // ---------------------------------------------------------------------

    uint8_t offset = 0;
    while (offset < total_len) {
        uint8_t chunk_size = total_len - offset;
        if (chunk_size > 7) chunk_size = 7;
        bool is_end = (offset + chunk_size >= total_len);

        BapTxJob& job = tx_queue[tx_head];
        job.bus = bus;
        job.tx_id = tx_id;
        memset(job.payload, 0, sizeof(job.payload));
        memcpy(job.payload, &payload[offset], chunk_size);
        job.len = chunk_size;
        job.is_multi_frame = true;
        job.wait_ack = is_end; 
        
        job.seq_ptr = (uint8_t*)((uint32_t)(*seq_counter)); 
        *seq_counter = (*seq_counter + 1) % 16; 

        tx_head = (tx_head + 1) % TX_QUEUE_SIZE;
        offset += chunk_size;
    }
    return true;
}

// =========================================================================
// asyncrone postman
// =========================================================================
void bap_async_tick() {
    uint32_t now = millis();

    switch (current_tx_state) {
        
        case TX_IDLE:
            if (tx_tail != tx_head) {
                BapTxJob& job = tx_queue[tx_tail];
                
                uint8_t seq = (uint32_t)job.seq_ptr; 
                uint8_t header = (job.is_multi_frame && !job.wait_ack) ? 0x20 : 0x10;
                header |= (seq % 16);

                raw_send_frame(job.bus, job.tx_id, header, job.payload, job.len);
                
                current_retries = 0;
                tx_state_timer = now;
                
                if (job.wait_ack) {
                    current_tx_state = TX_WAIT_ACK; 
                } else {
                    current_tx_state = TX_MULTI_PACING; 
                }
            }
            break;

        case TX_MULTI_PACING:
            if (now - tx_state_timer >= 10) { 
                tx_tail = (tx_tail + 1) % TX_QUEUE_SIZE; 
                current_tx_state = TX_IDLE;
            }
            break;

        case TX_WAIT_ACK:
            if (now - tx_state_timer >= 1500) { 
                Serial.println("BAP ASYNC: Timeout! Versuche Retry...");
                current_tx_state = TX_FAIL; 
            }
            break;

        case TX_FAIL:
        case TX_RECOVER_9X:
            { 
                BapTxJob& job = tx_queue[tx_tail];
                
                if (current_retries < 3) {
                    current_retries++;
                    tx_state_timer = now;
                    
                    uint8_t seq = (uint32_t)job.seq_ptr; 
                    uint8_t header = (job.is_multi_frame && !job.wait_ack) ? 0x20 : 0x10;
                    header |= (seq % 16);
                    
                    Serial.printf("BAP ASYNC: Resend Job (Try %d, Seq %02X)...\n", current_retries, seq);
                    raw_send_frame(job.bus, job.tx_id, header, job.payload, job.len);
                    
                    if (job.wait_ack) current_tx_state = TX_WAIT_ACK;
                    else current_tx_state = TX_MULTI_PACING;
                } else {
                    Serial.println("BAP ASYNC: FATAL FAIL nach 3 Retries! Überspringe Job.");
                    
                    // --- FAST-FAIL TRIGGER ---
                    if (job.tx_id == 0x490) { 
                        stack_tacho_trigger_fatal_error();
                    }
                    
                    tx_tail = (tx_tail + 1) % TX_QUEUE_SIZE; 
                    current_tx_state = TX_IDLE;
                }
            }
            break;
    }
}

// =========================================================================
// asyncrone receiver (with time machine)
// =========================================================================
void bap_transport_rx_hook(const can_msg_t* msg) {
    if (msg->dlc == 0) return;
    uint8_t b0 = msg->data[0];
    uint8_t type = b0 & 0xF0;
    uint8_t rx_seq = b0 & 0x0F;

    if (type == 0x10) {
        uint32_t ack_id = (msg->id == 0x491) ? 0x490 : 0x491; 
        CanBusID bus = (msg->id == 0x491) ? BUS_TACHO_OUT : BUS_TACHO_IN;
        bap_send_ack(bus, ack_id, rx_seq + 1);
    }

    if (current_tx_state != TX_WAIT_ACK && current_tx_state != TX_MULTI_PACING) return;
    
    BapTxJob& active_job = tx_queue[tx_tail];
    uint32_t expected_rx_id = active_job.tx_id + 1; 
    if (msg->id != expected_rx_id) return;

    // A) successful ACK (Bx)
    uint8_t job_seq = (uint32_t)active_job.seq_ptr; 
    uint8_t expected_ack = 0xB0 | ((job_seq + 1) % 16);
    
    if (b0 == expected_ack) {
        tx_tail = (tx_tail + 1) % TX_QUEUE_SIZE; 
        current_tx_state = TX_IDLE;      
        return;
    }

    // B) Busy / Sequence Error (9X)
    if (type == 0x90) {
        Serial.printf("BAP ASYNC: 9X Fehler! Hardware will Seq %02X. Spule Kette zurueck!\n", rx_seq);
        
        // --- TIME MACHINE ---
        uint8_t search_tail = tx_tail;
        int max_search = 16; // max 16 steps (prevents finding old ghost frames!)
        bool found = false;
        
        while (max_search > 0) {
            uint8_t past_seq = (uint32_t)tx_queue[search_tail].seq_ptr;
            
            if ((past_seq % 16) == rx_seq) {
                // We put the reader exactly back to this point!
                tx_tail = search_tail;
                
                // We reset the retry counter for this new attempt
                current_retries = 0; 
                
                // set to IDLE so that the next tick fires immediately
                current_tx_state = TX_IDLE; 
                found = true;
                break;
            }
            
            // going one step back in the ring buffer
            if (search_tail == 0) search_tail = TX_QUEUE_SIZE - 1;
            else search_tail--;
            
            // when we reach the head, the queue is empty, we must abort
            if (search_tail == tx_head) break; 
            
            max_search--;
        }
        
        if (!found) {
            Serial.println("BAP ASYNC: Konnte Seq im Puffer nicht finden. Abbruch der Kette!");
            current_tx_state = TX_FAIL;
        }
        return;
    }
}
