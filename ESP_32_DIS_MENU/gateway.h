#ifndef GATEWAY_H
#define GATEWAY_H

#include <Arduino.h>
#include "hal_can.h"

// --- initialization ---
void gateway_init();

// --- The router task (called in loop()) ---
void gateway_tick();

// --- hooks to layer 3 (state machines) ---
// its declared here as extern, so that the router can pass the packets
// handle over the stacks without creating include loops.
extern uint8_t debug_level;
void print_raw_can(const char* prefix, const can_msg_t* msg);
extern void stack_mmi_rx(const can_msg_t* msg);   // for 0x490
extern void stack_tacho_rx(const can_msg_t* msg); // for 0x491
extern volatile uint32_t last_bus_activity; //for light sleep

#endif
