struct VehicleData {
    float rpm = 0.0f;
    float oil_temp = 0.0f;
    float boost = 0.0f;
    float temp_c = 0.0f;
    float pedal = 0.0f;
    float torque = 0.0f;
    float speed = 0.0f;

    // called from task_bus_auto_rx
    void parse_can_message(uint32_t aid, uint8_t* data, uint8_t len) {
        if (aid == 0x280 && len >= 8) {          
            rpm = ((data[3] << 8) | data[2]) / 4.0f;
            pedal = data[5] * 0.4f;
            torque = data[7] * 0.39f;
        } else if (aid == 0x555 && len >= 8) {        
            oil_temp = data[7] - 60.0f;
            boost = data[4] * 0.02f;
        } else if (aid == 0x3E2 && len >= 2) {        
            temp_c = (data[1] / 2.0f) - 50.0f;
        }
    }
};

extern VehicleData car_data;
