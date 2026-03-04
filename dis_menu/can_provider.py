class LiveCANDataProvider:
    def __init__(self):
        # Internal state dictionary to hold the latest values.
        self.data = {
            'rpm': 0.0,
            'oil_temp': 0.0,
            'boost': 0.0,
            'temp_c': 0.0,
            'pedal': 0.0,
            'torque': 0.0,
            'speed': 0.0 
        }

    def get_available_variables(self):
        """Returns the dictionary of all supported CAN variables so the OS can build the config file."""
        return {
            "rpm": {"name": "RPM", "unit": "/min", "decimals": 0},
            "speed": {"name": "Speed", "unit": "km/h", "decimals": 0},
            "oil_temp": {"name": "Oil Temp", "unit": "°C", "decimals": 0},
            "pedal": {"name": "Pedal", "unit": "%", "decimals": 0},
            "boost": {"name": "Boost", "unit": "bar", "decimals": 2},
            "torque": {"name": "Torque", "unit": "Nm", "decimals": 0},
            "temp_c": {"name": "Out Temp", "unit": "°C", "decimals": 1}
        }
    
    def parse_message(self, msg, bus_name="cluster"):
        """
        Parses incoming CAN frames and updates the internal state.
        bus_name is prepared for the Teensy multi-bus routing (drivetrain, comfort, etc.)
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
            
        # Add your real Speed CAN ID here when you find it!
        # elif aid == 0xXXX and len(data) >= X:
        #     self.data['speed'] = ...

    def get_value(self, key):
        """Returns the latest float value for a given key."""
        return self.data.get(key, 0.0)
