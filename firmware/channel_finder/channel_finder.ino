// Channel finder - TEMPORARY test sketch.
// Scans every row-mux channel (0-15) against every column-mux channel (0-15)
// and streams all 256 readings, so python/find_channels.py can tell exactly
// which pair of mux channels each physical point is wired to.
// Same pins as the main firmware. Flash tactile_shirt.ino back afterwards.

const uint8_t COL_SEL[4] = {33, 25, 26, 27};
const uint8_t ROW_SEL[4] = {21, 22, 23, 14};
#define ADC_PIN 36
#define SETTLE_US 300

void selectChannel(const uint8_t pins[4], uint8_t ch) {
  for (uint8_t b = 0; b < 4; b++) digitalWrite(pins[b], (ch >> b) & 1);
}

void setup() {
  Serial.begin(250000);
  for (uint8_t b = 0; b < 4; b++) {
    pinMode(COL_SEL[b], OUTPUT);
    pinMode(ROW_SEL[b], OUTPUT);
  }
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
}

// One line per scan: M,<256 millivolt values, row-mux channel major>
void loop() {
  Serial.print("M");
  for (uint8_t r = 0; r < 16; r++) {
    selectChannel(ROW_SEL, r);
    for (uint8_t c = 0; c < 16; c++) {
      selectChannel(COL_SEL, c);
      delayMicroseconds(SETTLE_US);
      analogRead(ADC_PIN);
      uint32_t mv = (analogReadMilliVolts(ADC_PIN) + analogReadMilliVolts(ADC_PIN)) / 2;
      Serial.print(',');
      Serial.print(mv);
    }
  }
  Serial.println();
}
