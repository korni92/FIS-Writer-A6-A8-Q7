/* 
Quick and dirty to use the cluster on the bench without the car and to get rid of most warning lights and messages.
It's made for my car, so it's for ACC and dynmanic headlight.

You also need to know your 0x65F message content to get rid of component protection warning and SAFE message.
Just replace yours data in sendVIN and make sure to place it at the correct mux.

Hardware ESP32-S3-Zero with SN65 CAN transiver

With simulator option via serial console
*/

#include "driver/twai.h"

#define TX_PIN 4
#define RX_PIN 5

// --- INTERAKTIVE WERTE (Manuelle Steuerung) ---
float currentRPM = 850.0;     // Drehzahl (U/min)
float currentPedal = 0.0;     // Gaspedal (%)
float currentTorque = 15.0;   // Wunschmoment (%)
float currentOilTemp = 90.0;  // Öltemperatur (°C)
float currentBoost = 1.0;     // Ladedruck (Bar)
float currentTempC = 21.5;    // Außentemperatur (°C)

String serialBuffer = "";     // Puffer für serielle Eingaben

// --- SIMULATION / AUTO-REV EINSTELLUNGEN ---
bool demoMode = false;        // Status der Simulation
const float SIM_IDLE_RPM = 850.0;   // Leerlauf-Drehzahl
const float SIM_MAX_RPM = 5500.0;   // Maximale Drehzahl beim Gasgeben
const float SIM_MAX_PEDAL = 80.0;   // Maximale Gaspedalstellung (%)
const float SIM_MAX_TORQUE = 65.0;  // Maximales Drehmoment (%)
const float SIM_IDLE_BOOST = 1.0;   // Ladedruck im Leerlauf (Bar)
const float SIM_MAX_BOOST = 1.3;    // Ladedruck beim Gasgeben (Bar)
const float SIM_BASE_OIL = 90.0;    // Basis-Öltemperatur (°C)


// --- TIMER ---
unsigned long last540Time = 0; // 10ms
unsigned long last1A0Time = 0; // 20ms
unsigned long last5A0Time = 0; // 20ms
unsigned long last480Time = 0; // 20ms
unsigned long last280Time = 0; // 20ms 
unsigned long last5C0Time = 0; // 20ms 
unsigned long last590Time = 0; // 50ms 
unsigned long last050Time = 0; // 100ms
unsigned long last2C5Time = 0; // 100ms
unsigned long last3E2Time = 0; // 100ms 
unsigned long last550Time = 0; // 100ms
unsigned long last555Time = 0; // 100ms 
unsigned long last568Time = 0; // 100ms
unsigned long last394Time = 0; // 100ms 
unsigned long last65FTime = 0; // 1000ms

const int INTERVAL_540 = 10;
const int INTERVAL_1A0 = 20;
const int INTERVAL_5A0 = 20;
const int INTERVAL_480 = 20;
const int INTERVAL_280 = 20;    
const int INTERVAL_5C0 = 20;
const int INTERVAL_590 = 50;    
const int INTERVAL_050 = 100;   
const int INTERVAL_2C5 = 100;   
const int INTERVAL_3E2 = 100;   
const int INTERVAL_550 = 100;   
const int INTERVAL_555 = 100;   
const int INTERVAL_568 = 100;
const int INTERVAL_394 = 100;
const int INTERVAL_65F = 1000;

// --- ZÄHLER ---
uint8_t counter_2C5 = 0;
uint8_t counter_050 = 0;
uint8_t counter_568 = 0;
uint8_t counter_1A0 = 0;
uint8_t counter_5A0 = 0;
uint8_t counter_540 = 0;
uint8_t counter_5C0 = 0;
uint8_t counter_590 = 0;
uint8_t counter_394 = 0;

// MUX / SEQUENZ INDIZES
uint8_t vin_mux_sequence[] = {0, 1, 0, 2};
uint8_t vin_mux_index = 0;
uint8_t seq_480_index = 0;

// Status-Merker
bool busOffReported = false;

// Daten Motorstg (Replay) - OBD2 Lampe deaktiviert
const uint8_t data_480[15][8] = {
  {0xC1, 0x00, 0xBC, 0xD7, 0x00, 0x08, 0x0C, 0xA6},
  {0x20, 0x00, 0xC2, 0xD7, 0x00, 0x08, 0x0C, 0x39},
  {0x20, 0x00, 0xC8, 0xD7, 0x00, 0x08, 0x0C, 0x33},
  {0x20, 0x00, 0xCE, 0xD7, 0x00, 0x08, 0x0C, 0x35},
  {0x20, 0x00, 0xD4, 0xD7, 0x00, 0x08, 0x0C, 0x2F},
  {0x52, 0x00, 0xDA, 0xD7, 0x00, 0x08, 0x0C, 0x53},
  {0x52, 0x00, 0xE0, 0xD7, 0x00, 0x08, 0x0C, 0x69},
  {0x52, 0x00, 0xE6, 0xD7, 0x00, 0x08, 0x0C, 0x6F},
  {0x52, 0x00, 0xEC, 0xD7, 0x00, 0x08, 0x0C, 0x65},
  {0xA8, 0x00, 0xF2, 0xD7, 0x00, 0x08, 0x0C, 0x81},
  {0xA8, 0x00, 0xF8, 0xD7, 0x00, 0x08, 0x0C, 0x8B},
  {0xA8, 0x00, 0xFE, 0xD7, 0x00, 0x08, 0x0C, 0x8D},
  {0xA8, 0x00, 0x04, 0xD8, 0x00, 0x08, 0x0C, 0x78},
  {0xC1, 0x00, 0x0A, 0xD8, 0x00, 0x08, 0x0C, 0x1F},
  {0xC1, 0x00, 0x10, 0xD8, 0x00, 0x08, 0x0C, 0x05}
};

void printHelp() {
  Serial.println("\n--- SIMULATOR BEFEHLE ---");
  Serial.println("Tippe Buchstabe + Wert (z.B. R3000) und druecke Enter:");
  Serial.printf(" [R] Drehzahl (aktuell: %.0f U/min)\n", currentRPM);
  Serial.printf(" [C] Aussentemp (aktuell: %.1f Grad C)\n", currentTempC);
  Serial.printf(" [O] Oeltemp    (aktuell: %.1f Grad C)\n", currentOilTemp);
  Serial.printf(" [B] Ladedruck  (aktuell: %.2f Bar)\n", currentBoost);
  Serial.printf(" [P] Gaspedal   (aktuell: %.1f %%)\n", currentPedal);
  Serial.printf(" [T] Drehmoment (aktuell: %.1f %%)\n", currentTorque);
  Serial.println(" [S] Auto-Rev Simulation AN/AUS schalten");
  Serial.println(" [?] Diese Hilfe anzeigen");
  Serial.println("-------------------------\n");
}

void processSerialCommand(String input) {
  input.trim();
  if (input.length() == 0) return;
  
  char cmd = toupper(input.charAt(0));
  float val = input.substring(1).toFloat();

  switch(cmd) {
    case 'R': currentRPM = val;     Serial.printf("-> Drehzahl gesetzt auf: %.0f\n", currentRPM); break;
    case 'C': currentTempC = val;   Serial.printf("-> Aussentemperatur gesetzt auf: %.1f\n", currentTempC); break;
    case 'O': currentOilTemp = val; Serial.printf("-> Oeltemperatur gesetzt auf: %.1f\n", currentOilTemp); break;
    case 'B': currentBoost = val;   Serial.printf("-> Ladedruck gesetzt auf: %.2f\n", currentBoost); break;
    case 'P': currentPedal = val;   Serial.printf("-> Gaspedal gesetzt auf: %.1f%%\n", currentPedal); break;
    case 'T': currentTorque = val;  Serial.printf("-> Wunschmoment gesetzt auf: %.1f%%\n", currentTorque); break;
    case 'S': 
      demoMode = !demoMode; 
      Serial.printf("-> Auto-Rev Simulation: %s\n", demoMode ? "AKTIV" : "AUSGESCHALTET"); 
      break;
    case '?': 
    case 'H': printHelp(); break;
    default: Serial.println("Unbekannter Befehl. Tippe '?' fuer Hilfe.");
  }
}

void handleSerialInput() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        processSerialCommand(serialBuffer);
        serialBuffer = ""; 
      }
    } else {
      serialBuffer += c;
    }
  }
}

// Hilfsfunktion für weiche Übergänge in der Simulation
float mapFloat(float x, float in_min, float in_max, float out_min, float out_max) {
  return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

void updateSimulation() {
  if (!demoMode) return;

  // Ein Zyklus dauert 4000 Millisekunden (4 Sekunden)
  unsigned long t = millis() % 4000; 

  if (t < 1000) {
    // Phase 1: Gas geben (0 bis 1 Sekunde)
    currentPedal  = mapFloat(t, 0, 1000, 0.0, SIM_MAX_PEDAL);
    currentRPM    = mapFloat(t, 0, 1000, SIM_IDLE_RPM, SIM_MAX_RPM);
    currentTorque = mapFloat(t, 0, 1000, 15.0, SIM_MAX_TORQUE);
    currentBoost  = mapFloat(t, 0, 1000, SIM_IDLE_BOOST, SIM_MAX_BOOST);
  } else if (t < 2500) {
    // Phase 2: Vom Gas gehen, Drehzahl fällt (1 bis 2,5 Sekunden)
    currentPedal  = 0.0;
    currentRPM    = mapFloat(t, 1000, 2500, SIM_MAX_RPM, SIM_IDLE_RPM);
    currentTorque = mapFloat(t, 1000, 2500, SIM_MAX_TORQUE, 15.0);
    currentBoost  = mapFloat(t, 1000, 2500, SIM_MAX_BOOST, SIM_IDLE_BOOST);
  } else {
    // Phase 3: Leerlauf halten (2,5 bis 4 Sekunden)
    currentPedal  = 0.0;
    currentRPM    = SIM_IDLE_RPM;
    currentTorque = 15.0;
    currentBoost  = SIM_IDLE_BOOST;
  }

  // Öltemperatur schwankt ganz langsam und sanft um den Basiswert herum (+/- 2 Grad)
  currentOilTemp = SIM_BASE_OIL + (sin(millis() / 2000.0) * 2.0);
}

void setup() {
  Serial.begin(115200);
  
  // FIX FÜR ESP32-S3: Warten, bis der PC die USB-Verbindung geöffnet hat.
  unsigned long startWait = millis();
  while (!Serial && (millis() - startWait < 3000)) {
    delay(10);
  }
  
  delay(500); // Kurzer Puffer für den Serial Monitor zum Synchronisieren
  
  Serial.println("\n--- Audi A8 Sim ---");
  printHelp();

  twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)TX_PIN, (gpio_num_t)RX_PIN, TWAI_MODE_NORMAL);
  g_config.tx_queue_len = 30; 
  
  twai_timing_config_t t_config = TWAI_TIMING_CONFIG_500KBITS(); 
  twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

  if (twai_driver_install(&g_config, &t_config, &f_config) == ESP_OK) {
    Serial.println("TWAI Treiber installiert.");
  } else {
    Serial.println("Fehler bei der Installation!");
    return;
  }
  
  if (twai_start() == ESP_OK) {
    Serial.println("TWAI Treiber gestartet. Sende Daten...");
  } else {
    Serial.println("Fehler beim Starten!");
    return;
  }
}

void loop() {
  // 0. Serielle Eingaben prüfen
  handleSerialInput();
  
  // 1. Simulations-Werte im Hintergrund berechnen (falls aktiv)
  updateSimulation();

  // Bus Status überwachen
  twai_status_info_t status_info;
  twai_get_status_info(&status_info);

  if (status_info.state == TWAI_STATE_BUS_OFF) {
    if (!busOffReported) {
      Serial.println("Bus-Off");
      busOffReported = true;
    }
    twai_initiate_recovery();
    delay(20);
    return;
  } 
  else if (status_info.state == TWAI_STATE_STOPPED) {
    twai_start();
    delay(20);
    return;
  }
  else if (status_info.state == TWAI_STATE_RUNNING) {
    if (busOffReported) {
      Serial.println("Bus OK");
      busOffReported = false;
    }
  }

  // Normale Sende Logik
  unsigned long currentMillis = millis();

  if (currentMillis - last540Time >= INTERVAL_540) {
    last540Time = currentMillis;
    sendGetriebe();
  }

  if (currentMillis - last1A0Time >= INTERVAL_1A0) {
    last1A0Time = currentMillis;
    sendBremse1();
  }

  if (currentMillis - last5A0Time >= INTERVAL_5A0) {
    last5A0Time = currentMillis;
    sendBremse2();
  }

  if (currentMillis - last480Time >= INTERVAL_480) {
    last480Time = currentMillis;
    sendMotor();
  }

  if (currentMillis - last280Time >= INTERVAL_280) {
    last280Time = currentMillis;
    sendMotor1();
  }

  if (currentMillis - last5C0Time >= INTERVAL_5C0) {
    last5C0Time = currentMillis;
    sendEPB();
  }

  if (currentMillis - last590Time >= INTERVAL_590) {
    last590Time = currentMillis;
    sendLuftfederung();
  }

  if (currentMillis - last2C5Time >= INTERVAL_2C5) {
    last2C5Time = currentMillis;
    sendKlemme15();
  }

  if (currentMillis - last050Time >= INTERVAL_050) {
    last050Time = currentMillis;
    sendAirbag1();
  }

  if (currentMillis - last3E2Time >= INTERVAL_3E2) {
    last3E2Time = currentMillis;
    sendKlima();
  }

  if (currentMillis - last550Time >= INTERVAL_550) {
    last550Time = currentMillis;
    sendAirbag2();
  }

  if (currentMillis - last555Time >= INTERVAL_555) {
    last555Time = currentMillis;
    sendMotor7();
  }

  if (currentMillis - last568Time >= INTERVAL_568) {
    last568Time = currentMillis;
    sendACC();
  }

  if (currentMillis - last394Time >= INTERVAL_394) {
    last394Time = currentMillis;
    sendLWR();
  }

  if (currentMillis - last65FTime >= INTERVAL_65F) {
    last65FTime = currentMillis;
    sendVIN();
  }
}

// --- HILFSFUNKTIONEN FÜR DIE NACHRICHTEN ---

void sendKlima() {
  twai_message_t message = { .identifier = 0x3E2, .data_length_code = 8 };
  uint8_t tempRaw = (uint8_t)((currentTempC + 50.0) * 2.0);
  message.data[0] = 0x00; 
  message.data[1] = tempRaw; 
  message.data[2] = 0x13; 
  message.data[3] = 0x03; 
  message.data[4] = 0x63; 
  message.data[5] = 0x00; 
  message.data[6] = 0x82; 
  message.data[7] = 0xFF; 
  twai_transmit(&message, pdMS_TO_TICKS(5));
}

void sendMotor1() {
  twai_message_t message = { .identifier = 0x280, .data_length_code = 8 };
  uint16_t rpmRaw = (uint16_t)(currentRPM * 4.0);
  uint8_t pedalRaw = (uint8_t)(currentPedal / 0.4);
  uint8_t torqueRaw = (uint8_t)(currentTorque / 0.39);

  message.data[0] = 0x01; 
  message.data[1] = 0x18; 
  message.data[2] = rpmRaw & 0xFF;        
  message.data[3] = (rpmRaw >> 8) & 0xFF; 
  message.data[4] = 0x18; 
  message.data[5] = pedalRaw; 
  message.data[6] = 0x17; 
  message.data[7] = torqueRaw; 
  twai_transmit(&message, pdMS_TO_TICKS(5));
}

void sendMotor7() {
  twai_message_t message = { .identifier = 0x555, .data_length_code = 8 };
  uint8_t oilTempRaw = (uint8_t)(currentOilTemp + 60.0);
  uint8_t boostRaw = (uint8_t)(currentBoost / 0.02);

  message.data[0] = 0xE9; 
  message.data[1] = 0x00;
  message.data[2] = 0x7E;
  message.data[3] = 0x01;
  message.data[4] = boostRaw;   
  message.data[5] = 0x01;
  message.data[6] = 0x0C;
  message.data[7] = oilTempRaw; 
  twai_transmit(&message, pdMS_TO_TICKS(5));
}

void sendBremse1() {
  twai_message_t message = { .identifier = 0x1A0, .data_length_code = 8 };
  message.data[0] = 0x00; message.data[1] = 0x00; message.data[2] = 0x00; message.data[3] = 0x00;
  message.data[4] = 0xFE; message.data[5] = 0xFE; message.data[6] = 0x00;
  message.data[7] = 0x90 + counter_1A0;
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++counter_1A0 > 0x0F) counter_1A0 = 0;
}

void sendBremse2() {
  twai_message_t message = { .identifier = 0x5A0, .data_length_code = 8 };
  message.data[0] = 0x81; message.data[1] = 0x00; message.data[2] = 0x00;
  message.data[3] = (counter_5A0 << 4);
  message.data[4] = 0x00; message.data[5] = 0x38; message.data[6] = 0x0A; message.data[7] = 0xF0;
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++counter_5A0 > 0x0F) counter_5A0 = 0;
}

void sendGetriebe() {
  twai_message_t message = { .identifier = 0x540, .data_length_code = 8 };
  message.data[0] = (counter_540 << 4);
  message.data[1] = 0x00; message.data[2] = 0xFF; message.data[3] = 0x00;
  message.data[4] = 0xFF; message.data[5] = 0x00; message.data[6] = 0x00;
  uint8_t d8_array[4] = {0x0F, 0x26, 0x26, 0x0F};
  message.data[7] = d8_array[counter_540 % 4];
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++counter_540 > 0x0F) counter_540 = 0;
}

void sendMotor() {
  twai_message_t message = { .identifier = 0x480, .data_length_code = 8 };
  memcpy(message.data, data_480[seq_480_index], 8);
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++seq_480_index >= 15) seq_480_index = 0;
}

void sendEPB() {
  twai_message_t message = { .identifier = 0x5C0, .data_length_code = 8 };
  message.data[0] = counter_5C0; 
  message.data[1] = 0x00; 
  message.data[2] = 0x81; 
  message.data[3] = 0xA6; 
  message.data[4] = 0x20; 
  message.data[5] = 0x00; 
  message.data[6] = 0x00;
  message.data[7] = message.data[0] ^ message.data[1] ^ message.data[2] ^ 
                    message.data[3] ^ message.data[4] ^ message.data[5] ^ 
                    message.data[6];
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++counter_5C0 > 0x0F) counter_5C0 = 0;
}

void sendLuftfederung() {
  twai_message_t message = { .identifier = 0x590, .data_length_code = 8 };
  message.data[1] = counter_590;                  
  message.data[0] = counter_590 ^ 0x03;           
  message.data[2] = 0x43;
  message.data[3] = 0x00;
  message.data[4] = 0x40;
  message.data[5] = 0xFE;
  message.data[6] = 0xFE;
  message.data[7] = 0x00;
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++counter_590 > 0x0F) counter_590 = 0;
}

void sendKlemme15() {
  twai_message_t message = { .identifier = 0x2C5, .data_length_code = 4 };
  message.data[0] = 0x47; message.data[1] = counter_2C5;
  message.data[2] = 0x00; message.data[3] = 0xD7 - counter_2C5;
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++counter_2C5 > 0x0F) counter_2C5 = 0;
}

void sendVIN() {
  twai_message_t message = { .identifier = 0x65F, .data_length_code = 8 };
  uint8_t current_mux = vin_mux_sequence[vin_mux_index];
  if (current_mux == 0) {
    uint8_t data[8] = {0x00, 0x86, 0xF7, 0x32, 0xE0, 0x57, 0x41, 0x55}; memcpy(message.data, data, 8);
  } else if (current_mux == 1) {
    uint8_t data[8] = {0x01, 0x5A, 0x5A, 0x5A, 0x34, 0x45, 0x39, 0x37}; memcpy(message.data, data, 8);
  } else if (current_mux == 2) {
    uint8_t data[8] = {0x02, 0x4E, 0x30, 0x31, 0x37, 0x37, 0x36, 0x37}; memcpy(message.data, data, 8);
  }
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++vin_mux_index > 3) vin_mux_index = 0;
}

void sendAirbag1() {
  twai_message_t message = { .identifier = 0x050, .data_length_code = 4 };
  message.data[0] = 0x00; message.data[1] = 0xA0;
  message.data[2] = (counter_050 << 4); 
  message.data[3] = message.data[0] ^ message.data[1] ^ message.data[2];
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++counter_050 > 0x0F) counter_050 = 0;
}

void sendAirbag2() {
  twai_message_t message = { .identifier = 0x550, .data_length_code = 3 };
  message.data[0] = 0x8A; message.data[1] = 0x0A; message.data[2] = 0x80;
  twai_transmit(&message, pdMS_TO_TICKS(5));
}

void sendACC() {
  twai_message_t message = { .identifier = 0x568, .data_length_code = 8 };
  message.data[0] = 0xFD ^ counter_568; message.data[1] = counter_568; 
  message.data[2] = 0xFE; message.data[3] = 0x03; message.data[4] = 0x00;
  message.data[5] = 0x00; message.data[6] = 0x00; message.data[7] = 0x00;
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++counter_568 > 0x0F) counter_568 = 0;
}

void sendLWR() {
  twai_message_t message = { .identifier = 0x394, .data_length_code = 8 };
  message.data[0] = 0x0B;
  message.data[1] = 0x81;
  message.data[2] = 0x7E;
  message.data[3] = 0x5D;
  message.data[4] = 0x00;
  message.data[5] = 0x00;
  message.data[6] = 0x00;
  message.data[7] = (counter_394 << 4);
  twai_transmit(&message, pdMS_TO_TICKS(5));
  if (++counter_394 > 0x0F) counter_394 = 0;
}
