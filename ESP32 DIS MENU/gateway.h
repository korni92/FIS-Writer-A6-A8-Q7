#ifndef GATEWAY_H
#define GATEWAY_H

#include <Arduino.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "driver/twai.h"

#define MMI_ANGESCHLOSSEN true 

// DEBUG: 0=OFF, 1=JUST TEXT, 2=TEXT + ALL CAN, 3=CAN CLUSTER RAW CAN AND TEXT, 4=CAN MMI RAW CAN AND TEXT
extern uint8_t debug_level;
extern twai_handle_t twai_bus_auto;   
extern twai_handle_t twai_bus_tacho;  

// global queues
extern QueueHandle_t q_tacho_rx; 
extern QueueHandle_t q_mmi_rx;   

void gateway_init();
void print_raw_can(const char* prefix, twai_message_t* msg);
void send_to_tacho(uint8_t* data, uint8_t len);
void send_to_mmi(uint8_t* data, uint8_t len);

#endif
