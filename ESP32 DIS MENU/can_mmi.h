#ifndef CAN_MMI_H
#define CAN_MMI_H

#include <Arduino.h>
#include "driver/twai.h" 

extern bool mmi_connected;
extern char snooped_top_line[20];
extern uint8_t snooped_top_color;
extern bool snooped_top_dirty;

void init_mmi_handler();
void handle_mmi_protocol();
void process_snooped_mmi_payload(uint8_t* payload, uint8_t len);

#endif
