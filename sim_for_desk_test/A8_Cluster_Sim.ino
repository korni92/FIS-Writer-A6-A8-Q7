/* 
Quick and dirty to use the cluster on the bench without the car and to get rid of most warning lights and messages.
It's made for my car, so it's for ACC and dynmanic headlight.

You also need to know your 0x65F message content to get rid of component protection warning and SAFE message.
Just replace yours data in sendVIN and make sure to place it at the correct mux.

Hardware ESP32-S3-Zero with SN65 CAN transiver
*/

#include "driver/twai.h"

#define TX_PIN 4
#define RX_PIN 5

// Timer
unsigned long last540Time = 0; // 10ms
unsigned long last1A0Time = 0; // 20ms
unsigned long last5A0Time = 0; // 20ms
unsigned long last480Time = 0; // 20ms
unsigned long last5C0Time = 0; // 20ms 
unsigned long last050Time = 0; // 100ms
unsigned long last2C5Time = 0; // 100ms
unsigned long last550Time = 0; // 100ms
unsigned long last568Time = 0; // 100ms
unsigned long last394Time = 0; // 100ms 
unsigned long last65FTime = 0; // 1000ms

const int INTERVAL_540 = 10;
const int INTERVAL_1A0 = 20;
const int INTERVAL_5A0 = 20;
const int INTERVAL_480 = 20;
const int INTERVAL_5C0 = 20;
const int INTERVAL_050 = 100;   
const int INTERVAL_2C5 = 100;   
const int INTERVAL_550 = 100;   
const int INTERVAL_568 = 100;
const int INTERVAL_394 = 100;
const int INTERVAL_65F = 1000;

// Zähler
uint8_t counter_2C5 = 0;
uint8_t counter_050 = 0;
uint8_t counter_568 = 0;
uint8_t counter_1A0 = 0;
uint8_t counter_5A0 = 0;
uint8_t counter_540 = 0;
uint8_t counter_5C0 = 0;
uint8_t counter_394 = 0;

// MUX / SEQUENZ INDIZES
uint8_t vin_mux_sequence[] = {0, 1, 0, 2};
uint8_t vin_mux_index = 0;
uint8_t seq_480_index = 0;

// Status-Merker
bool busOffReported = false;

// Daten Motorstg (Replay)
const uint8_t data_480[15][8] = {
  {0xC1, 0x08, 0xBC, 0xD7, 0x00, 0x08, 0x0C, 0xA6},
  {0x20, 0x08, 0xC2, 0xD7, 0x00, 0x08, 0x0C, 0x39},
  {0x20, 0x08, 0xC8, 0xD7, 0x00, 0x08, 0x0C, 0x33},
  {0x20, 0x08, 0xCE, 0xD7, 0x00, 0x08, 0x0C, 0x35},
  {0x20, 0x08, 0xD4, 0xD7, 0x00, 0x08, 0x0C, 0x2F},
  {0x52, 0x08, 0xDA, 0xD7, 0x00, 0x08, 0x0C, 0x53},
  {0x52, 0x08, 0xE0, 0xD7, 0x00, 0x08, 0x0C, 0x69},
  {0x52, 0x08, 0xE6, 0xD7, 0x00, 0x08, 0x0C, 0x6F},
  {0x52, 0x08, 0xEC, 0xD7, 0x00, 0x08, 0x0C, 0x65},
  {0xA8, 0x08, 0xF2, 0xD7, 0x00, 0x08, 0x0C, 0x81},
  {0xA8, 0x08, 0xF8, 0xD7, 0x00, 0x08, 0x0C, 0x8B},
  {0xA8, 0x08, 0xFE, 0xD7, 0x00, 0x08, 0x0C, 0x8D},
  {0xA8, 0x08, 0x04, 0xD8, 0x00, 0x08, 0x0C, 0x78},
  {0xC1, 0x08, 0x0A, 0xD8, 0x00, 0x08, 0x0C, 0x1F},
  {0xC1, 0x08, 0x10, 0xD8, 0x00, 0x08, 0x0C, 0x05}
};

void setup() {
  //Serial.begin(115200);
  //delay(1000);
  //Serial.println("--- Audi A8 Sim ---");

  twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)TX_PIN, (gpio_num_t)RX_PIN, TWAI_MODE_NORMAL);
  // Sende-Warteschlange erhöhen
  g_config.tx_queue_len = 10; 
  
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

  // 1. Getriebe (ID 0x540) - 10ms
  if (currentMillis - last540Time >= INTERVAL_540) {
    last540Time = currentMillis;
    sendGetriebe();
  }

  // 2. Bremse 1 (ID 0x1A0) - 20ms
  if (currentMillis - last1A0Time >= INTERVAL_1A0) {
    last1A0Time = currentMillis;
    sendBremse1();
  }

  // 3. Bremse 2 (ID 0x5A0) - 20ms
  if (currentMillis - last5A0Time >= INTERVAL_5A0) {
    last5A0Time = currentMillis;
    sendBremse2();
  }

  // 4. Motor (ID 0x480) - 20ms
  if (currentMillis - last480Time >= INTERVAL_480) {
    last480Time = currentMillis;
    sendMotor();
  }

  // 5. EPB Parkbremse (ID 0x5C0) - 20ms
  if (currentMillis - last5C0Time >= INTERVAL_5C0) {
    last5C0Time = currentMillis;
    sendEPB();
  }

  // 6. Zündung (ID 0x2C5) - 100ms
  if (currentMillis - last2C5Time >= INTERVAL_2C5) {
    last2C5Time = currentMillis;
    sendKlemme15();
  }

  // 7. Airbag 1 (ID 0x050) - 100ms
  if (currentMillis - last050Time >= INTERVAL_050) {
    last050Time = currentMillis;
    sendAirbag1();
  }

  // 8. Airbag 2 (ID 0x550) - 100ms
  if (currentMillis - last550Time >= INTERVAL_550) {
    last550Time = currentMillis;
    sendAirbag2();
  }

  // 9. ACC (ID 0x568) - 100ms
  if (currentMillis - last568Time >= INTERVAL_568) {
    last568Time = currentMillis;
    sendACC();
  }

  // 10. LWR / AFS (ID 0x394) - 100ms
  if (currentMillis - last394Time >= INTERVAL_394) {
    last394Time = currentMillis;
    sendLWR();
  }

  // 11. Fahrgestellnummer (ID 0x65F) - 1000ms
  if (currentMillis - last65FTime >= INTERVAL_65F) {
    last65FTime = currentMillis;
    sendVIN();
  }
}

// Hilfsfunktion für die Nachrichten

void sendBremse1() {
  twai_message_t message = { .identifier = 0x1A0, .data_length_code = 8 };
  message.data[0] = 0x00; message.data[1] = 0x00; message.data[2] = 0x00; message.data[3] = 0x00;
  message.data[4] = 0xFE; message.data[5] = 0xFE; message.data[6] = 0x00;
  message.data[7] = 0x90 + counter_1A0;
  twai_transmit(&message, 0);
  if (++counter_1A0 > 0x0F) counter_1A0 = 0;
}

void sendBremse2() {
  twai_message_t message = { .identifier = 0x5A0, .data_length_code = 8 };
  message.data[0] = 0x81; message.data[1] = 0x00; message.data[2] = 0x00;
  message.data[3] = (counter_5A0 << 4);
  message.data[4] = 0x00; message.data[5] = 0x38; message.data[6] = 0x0A; message.data[7] = 0xF0;
  twai_transmit(&message, 0);
  if (++counter_5A0 > 0x0F) counter_5A0 = 0;
}

void sendGetriebe() {
  twai_message_t message = { .identifier = 0x540, .data_length_code = 8 };
  message.data[0] = (counter_540 << 4);
  message.data[1] = 0x00; message.data[2] = 0xFF; message.data[3] = 0x00;
  message.data[4] = 0xFF; message.data[5] = 0x00; message.data[6] = 0x00;
  uint8_t d8_array[4] = {0x0F, 0x26, 0x26, 0x0F};
  message.data[7] = d8_array[counter_540 % 4];
  twai_transmit(&message, 0);
  if (++counter_540 > 0x0F) counter_540 = 0;
}

void sendMotor() {
  twai_message_t message = { .identifier = 0x480, .data_length_code = 8 };
  memcpy(message.data, data_480[seq_480_index], 8);
  twai_transmit(&message, 0);
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

  twai_transmit(&message, 0);
  if (++counter_5C0 > 0x0F) counter_5C0 = 0;
}

void sendKlemme15() {
  twai_message_t message = { .identifier = 0x2C5, .data_length_code = 4 };
  message.data[0] = 0x47; message.data[1] = counter_2C5;
  message.data[2] = 0x00; message.data[3] = 0xD7 - counter_2C5;
  twai_transmit(&message, 0);
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
  twai_transmit(&message, 0);
  if (++vin_mux_index > 3) vin_mux_index = 0;
}

void sendAirbag1() {
  twai_message_t message = { .identifier = 0x050, .data_length_code = 4 };
  message.data[0] = 0x00; message.data[1] = 0xA0;
  message.data[2] = (counter_050 << 4); 
  message.data[3] = message.data[0] ^ message.data[1] ^ message.data[2];
  twai_transmit(&message, 0);
  if (++counter_050 > 0x0F) counter_050 = 0;
}

void sendAirbag2() {
  twai_message_t message = { .identifier = 0x550, .data_length_code = 3 };
  message.data[0] = 0x8A; message.data[1] = 0x0A; message.data[2] = 0x80;
  twai_transmit(&message, 0);
}

void sendACC() {
  twai_message_t message = { .identifier = 0x568, .data_length_code = 8 };
  message.data[0] = 0xFD ^ counter_568; message.data[1] = counter_568; 
  message.data[2] = 0xFE; message.data[3] = 0x03; message.data[4] = 0x00;
  message.data[5] = 0x00; message.data[6] = 0x00; message.data[7] = 0x00;
  twai_transmit(&message, 0);
  if (++counter_568 > 0x0F) counter_568 = 0;
}

void sendLWR() {
  twai_message_t message = { .identifier = 0x394, .data_length_code = 8 };
  
  // Statische Werte aus Trace
  message.data[0] = 0x0B;
  message.data[1] = 0x81;
  message.data[2] = 0x7E;
  message.data[3] = 0x5D;
  message.data[4] = 0x00;
  message.data[5] = 0x00;
  message.data[6] = 0x00;
  
  // Zähler ins obere Nibble von Byte 7 schreiben (z.B. 0x10, 0x20...)
  message.data[7] = (counter_394 << 4);
  
  twai_transmit(&message, 0);
  if (++counter_394 > 0x0F) counter_394 = 0;
}
