#ifndef HAL_CAN_H
#define HAL_CAN_H

#include <Arduino.h>
#include <stdint.h>
#include <stdbool.h>

enum CanBusID {
    BUS_TACHO_IN = 0, // MMI/CAR side (TWAI 1)
    BUS_TACHO_OUT,    // cluster side (TWAI 2)
    BUS_COMFORT,      // comfort-CAN (SPI MCP2515 1)
    BUS_DIAG,         // diag-CAN (SPI MCP2515 2)
    BUS_DRIVE,        // drivetrain-CAN (SPI MCP2515 3)
    NUM_CAN_BUSES
};

struct can_msg_t {
    uint32_t id;
    uint8_t dlc;
    uint8_t data[8];
    bool is_extended;
};

void hal_can_init();
bool hal_can_send(CanBusID bus, const can_msg_t* msg);
bool hal_can_receive(CanBusID bus, can_msg_t* msg);

void hal_can_tick();

#endif
