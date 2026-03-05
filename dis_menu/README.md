To run main_sim.py


![main_menu](https://github.com/user-attachments/assets/9f26c7b9-54db-4d87-ade1-339cc1b869fe)

### main_sim.py
Role: The OS Kernel & Master Orchestrator.
Function: 
This is the entry point of the software. It holds the main event loop (engine_loop), initializes all hardware and apps, and routes button inputs to the currently active app. It also acts as the master conductor for the Top Line (Zone 0x01), running a background service to draw custom data there. Crucially, it protects the hardware state machine by pausing background drawings during Theme Swaps (Virtual Cockpit transition) or when Diagnostics are running.

### dis_hal.py (Hardware Abstraction Layer)
Role: Physical CAN & Transport Layer.
Function: Contains the CANDriver class for raw PCAN communication (sending/polling frames) and the MMIProtocol class. It handles the low-level Audi proprietary handshakes, heartbeat (ping/pong) signals, ACK sequences (0xB0), and chunks large data payloads into 7-byte CAN frames.

### dis_ui.py
Role: The Display Manager.
Function: Acts as the bridge between apps and the HAL. It handles the logic for initializing, claiming, and releasing display "Zones" (0x01 Top Line, 0x02 Main Body). It translates strings into Audi CP1252 byte arrays and maintains a screen_cache so that the OS only sends CAN traffic when the text actually changes, preventing bus overloads.
