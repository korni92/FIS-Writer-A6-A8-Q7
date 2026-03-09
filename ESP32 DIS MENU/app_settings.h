#ifndef APP_SETTINGS_H
#define APP_SETTINGS_H

#include "app_base.h"
#include "settings_registry.h"
#include <vector>

struct FlatMenuItem {
    SettingItem* item;
    bool is_node;           
    uint8_t option_index;   
    uint8_t indent;         
    String display_text;
};

class AppSettings : public BaseApp {
private:
    int cursor = 0;
    int view_start = 0;
    std::vector<FlatMenuItem> flat_list;

    void updateShadowBuffer();
    void flattenMenu();
    void flattenRecursive(SettingItem* item, uint8_t indent);

public:
    void onStart() override;
    void onStop() override;
    void onTick() override;
    void handleInput(InputEvent cmd) override;
    void onRedraw() override;
};

extern AppSettings app_settings;

#endif
