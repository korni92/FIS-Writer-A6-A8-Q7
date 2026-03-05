To run main_sim.py


![main_menu](https://github.com/user-attachments/assets/9f26c7b9-54db-4d87-ade1-339cc1b869fe)

## 1. Core OS & Hardware Abstraction (The Kernel)
These files manage the physical hardware, the CAN bus, and the main operating system loop.

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

## 2. System Services (Middleware)
These files provide shared resources and data to all the applications.

### app_core.py
Role: Global Services & Base Classes.
Function: Houses the ConfigStore (saving/loading settings to disk), the TranslationEngine (tr() for multi-language support), and the LiveDataManager which holds the active CAN data and live layout structures. It also defines the base DISApp class that all visual apps inherit from.

### can_provider.py
Role: Vehicle Data Parser.
Function: Runs silently in the background, listening to raw vehicle CAN IDs (e.g., 0x280, 0x555). It decodes these raw hexadecimal frames into human-readable Python variables like rpm, speed, and boost so the UI can display them.

### symbols.py
Role: Asset Library.
Function: A simple dictionary of constants containing the specific hex codes for Audi's custom font characters (like the Car Icon, Factory Icon, arrows, degrees Celsius) and the proprietary color codes (Theme, Red, White).

## 3. User Applications (The Frontend)
These are the isolated modules that take over the screen when selected.

### app_launcher.py
Role: Main Menu.
Function: Automatically scans the OS app registry at boot and generates the visual list of available apps. It handles the cursor logic to launch apps when you press OK.

### app_settings.py
Role: System Configuration UI.
Function: Renders a nested dropdown menu for system settings. Allows the user to toggle languages, themes, autostart preferences, and customize what variables appear on the left and right sides of the Top Line.

## app_livedata.py
Role: Dynamic Dashboard Viewer.
Function: Reads the live_config.json file and renders complex, user-defined gauge pages. It handles logic for multi-item lists, single-item focus pages, conditional warning colors, and ASCII progress bars.

### app_diagnostics_ui.py
Role: VCDS Scanner Frontend.
Function: The visual interface for diagnostics. It manages the complex state machine required for navigating ECU lists, reading Measuring Blocks, paginating through Fault Codes, and executing Output Tests. It also claims the Top Line to display "DIAGNOSTICS".

### app_diagnostics_con.py
Role: VCDS Scanner Backend.
Function: The highly sensitive TP2.0 and KWP2000 communication protocol handler. It negotiates dynamic CAN IDs with ECUs, enforces Block Size rules, sends keep-alive ACKs, and decodes the raw diagnostic hex payloads into usable data for the UI.

## 4. Configuration & External Tools
These are the data files and external scripts that drive the dynamic parts of the system.

### config_editor.html
Role: Web-based Dashboard Designer.
Function: A standalone offline HTML tool. Users can import their JSON layout, use drop-downs to map out exact screen lines, set up warning thresholds, and see a live pixel-accurate visual preview of the Audi cluster before exporting the file back to the OS.

### live_config.json
Role: Dashboard Layout File.
Function: The generated JSON file that tells app_livedata.py exactly what data to put on what line, what colors to use, and where to draw progress bars.

### config.json
Role: Non-Volatile Memory (NVM).
Function: A simple JSON file created by app_core.py to remember user settings across reboots (e.g., preserving the Green theme or German language).

### lang.json
Role: Language Dictionary.
Function: Maps English string keys to other languages (e.g., "Diagnostics": "Diagnose"). Read by the translation engine.

### fault_list.txt
Role: DTC Lookup Table.
Function: A tab-separated text file used by the Diagnostics App to convert raw hex fault codes (e.g., P000100) into human-readable descriptions (e.g., "Fuel Volume Regulator Control Circuit/Open").


## Adding an APP
1. How to Add a Completely New App
Adding a new app involves creating a standalone class and registering it in the OS kernel.

### Step 1: Create the App File (e.g., app_example.py)
Every app must inherit from DISApp (found in app_core.py). This gives it the standard button hooks (on_up, on_ok, etc.) and screen states.

### Step 2: Register it in main_sim.py
Open main_sim.py, import your new app, and add exactly one line to the self.app_registry. The AppLauncher will automatically see it and generate a menu entry for you!

