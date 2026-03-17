#ifndef STACK_MMI_H
#define STACK_MMI_H

#include <Arduino.h>
#include "hal_can.h"

enum MmiState {
    MMI_OFFLINE,
    MMI_CONNECTED
};

MmiState stack_mmi_get_state();

// --- SHADOW VRAM (drawer principle) ---
struct BapLine {
    char text[20];
    uint8_t color;
    bool is_dirty;
    bool is_empty;
};

struct Zone01_Cabinet {
    BapLine lines[4]; // Index 0-3 = LineID 0x01-0x04
};

struct Zone02_Cabinet {
    BapLine lines[5]; // Index 0-4 = LineID 0x05-0x09
    uint8_t cursor_line;
    uint8_t cursor_arrow;
    bool cursor_dirty;
};

struct Zone03_Cabinet {
    BapLine lines[4]; // Index 0-3 = LineID 0x0A-0x0D
    uint8_t nav_arrows[8];
    bool arrows_dirty;
    uint8_t nav_distance[8];
    bool distance_dirty;
};

struct MmiShadowVRAM {
    uint8_t color_theme;
    bool theme_dirty;
    
    Zone01_Cabinet z1;
    Zone02_Cabinet z2;
    Zone03_Cabinet z3;
};

extern MmiShadowVRAM mmi_vram;

// trigger-flags for the UI when MMI sends OP_RELEASE or OP_STOP
extern bool snooped_top_commit;
extern uint8_t snooped_active_theme;
extern bool snooped_theme_dirty;
extern bool snooped_middle_commit;
extern bool snooped_stop_z1;
extern bool snooped_stop_z2;
extern bool snooped_stop_z3;

void stack_mmi_init();
void stack_mmi_tick(); 
void stack_mmi_rx(const can_msg_t* msg); 
void stack_mmi_force_redraw_flags();

#endif
