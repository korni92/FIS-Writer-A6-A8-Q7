#ifndef CAN_DATA_H
#define CAN_DATA_H

#include <Arduino.h>

// Application Protocol OP Codes
#define OP_DATA_END    0x10
#define OP_DATA_BODY   0x20
#define OP_ACK         0xB0

#define OP_CLAIM       0x36
#define OP_RELEASE     0x32
#define OP_SUBSCRIBE   0x30
#define OP_STOP        0x34
#define OP_CONFIRM     0x3B
#define OP_WRITE_TEXT  0xE0
#define OP_INDICATOR   0xE4
#define OP_SOURCE      0xE2
#define OP_ERROR       0x09

// Transport Protocol Bytes
#define TP_PING        0xA3
#define TP_OPEN        0xA0
#define TP_PONG        0xA1
#define TP_RESET       0xA8   
#define TP_BUSY        0x9A

// Global Car Status
extern bool is_kl15_on; 
extern bool is_klS_on;  

#endif
