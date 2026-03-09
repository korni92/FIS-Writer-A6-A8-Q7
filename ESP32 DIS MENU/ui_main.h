#ifndef UI_MAIN_H
#define UI_MAIN_H

#include <Arduino.h>
#include <string.h>
#include "driver/twai.h"

// structure for shadow buffer
struct DisplayLine {
    char text[20];
    uint8_t color;
    bool dirty;      // true = must be send over can
    bool is_empty;   // true = delete line or hide
};

class DISDisplayManager {
private:
    DisplayLine lines[10]; 
    
    // actual curser state (Opcode E4)
    uint8_t current_highlight_line;
    uint8_t current_arrow_cfg;
    bool indicator_dirty;

    // private low level function
    void claim_zone(uint8_t zone_id);
    bool release_zone(uint8_t zone_id);
    void write_raw_line(uint8_t line_id, const char* text, uint8_t color);
    void send_raw_highlight(uint8_t line_idx, uint8_t arrow_cfg);

public:
    DISDisplayManager();

    bool needs_redraw = false;
    bool is_oem_screen = true;     
    uint8_t active_theme = 0xFF;   
    uint8_t current_active_zone = 0x00; // 0x00 = no, 0x01 = Top, 0x02 = Middle

    // high-level api for apps
    void clearBuffer();
    void setLine(uint8_t line_id, const char* text, uint8_t color = 0x00);
    void setIndicator(uint8_t line_idx, uint8_t arrow_cfg);
    void applyTheme(uint8_t source_id);
    bool is_top_line_split = false; // true = line 02,03,04 activ | false = line 01 aktiv

    bool commitMiddleZone(); 
    bool commitTopZone();    
    bool commitFullRedraw(); 
    
    void primeGraphicsBuffer();

    // System-function
    void switch_source(uint8_t source_id);
    void stop_zone(uint8_t zone_id);
    void poll_events(); 
    bool updateTopLine();
};

extern DISDisplayManager ui;

#endif
