#ifndef APP_BASE_H
#define APP_BASE_H

#include <Arduino.h>

// Inputs to use by other codes (to translate CAN commands to buttons or monitor commands to buttons)
enum InputEvent {
    BTN_UP,
    BTN_DOWN,
    BTN_OK,
    BTN_MODE,
    BTN_OK_LONG,
    BTN_MODE_LONG,
    BTN_NONE
};

// baseclass: every App needs these
class BaseApp {
public:
    virtual ~BaseApp() {}
    
    // opened 1x when app is opened
    virtual void onStart() = 0;
    
    // when other app is opened or menu closed
    virtual void onStop() = 0;
    
    // run trough every loop, good for live data view
    virtual void onTick() = 0; 
    
    // inputs to control
    virtual void handleInput(InputEvent cmd) = 0;
    
    // when cluster claimed its screen and app needs to be redrawn
    virtual void onRedraw() = 0;
};

// global pointer to the app that is shown on the display
extern BaseApp* current_app;

// global system function to switch the app
void os_switch_app(BaseApp* new_app);
void os_active_wait(uint32_t ms);

#endif
