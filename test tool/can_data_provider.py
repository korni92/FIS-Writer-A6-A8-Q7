class LiveCANDataProvider:
    def __init__(self):
        # Internal state dictionary to hold the latest values
        self.data = {
            'rpm': 0.0,
            'oil_temp': 0.0,
            'boost': 0.0,
            'temp_c': 0.0,
            'pedal': 0.0,
            'torque': 0.0
        }

    def parse_message(self, msg):
        """
        Parses incoming CAN frames and updates the internal state.
        Add new CAN IDs here as you discover them!
        """
        aid = msg.arbitration_id
        data = msg.data
        
        # Motor1 - RPM / Pedal / Torque
        if aid == 0x280 and len(data) >= 8:          
            self.data['rpm'] = ((data[3] << 8) | data[2]) / 4.0
            self.data['pedal'] = data[5] * 0.4
            self.data['torque'] = data[7] * 0.39

        # Motor7 - Oil / Boost
        elif aid == 0x555 and len(data) >= 8:        
            self.data['oil_temp'] = data[7] - 60.0
            self.data['boost'] = data[4] * 0.02

        # Klima - Außentemperatur
        elif aid == 0x3E2 and len(data) >= 2:        
            self.data['temp_c'] = (data[1] / 2.0) - 50.0

    def get_value(self, key):
        """Returns the latest float value for a given key."""
        return self.data.get(key, 0.0)
