#ifndef APP_LAUNCHER_H
#define APP_LAUNCHER_H

#include "app_base.h"

class AppLauncher : public BaseApp {
private:
    int cursor = 0;
    int view_start = 0;
    static const int num_items = 4;
    const char* menu_items[num_items] = {
        "Live Data",
        "Diagnostics",
        "Settings",
        "Close Menu"
    };

    // helperfunction to set curser and text in shadow buffer
    void updateShadowBuffer();

public:
    void onStart() override;
    void onStop() override;
    void onTick() override;
    void handleInput(InputEvent cmd) override;
    void onRedraw() override;
};

// a global instance in the launcher, that can be opened from anywhere
extern AppLauncher app_launcher;

#endif
