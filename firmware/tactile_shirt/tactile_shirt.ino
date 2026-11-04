// Tactile Exercise Shirt - ESP32 firmware (Lab 6)
// Scans two 6x7 Velostat pressure grids (chest + back) through CD74HC4067
// multiplexers, following the course schematic, and streams each frame
// over serial.
//
// Each sensor is read as a voltage divider:
//   SENSE (column) mux SIG -> ADC pin, and through a 660 ohm resistor to 3V3
//   GROUND (row) mux SIG   -> GND
//   EN -> GND and VCC -> 3V3 on every mux
// The selected row strip is grounded and the selected column strip is pulled
// up, so  V_adc = 3.3 * R_velostat / (R_velostat + 660).
// No pressure -> high resistance -> V near the top of the range.
// Pressure    -> lower resistance -> V drops.
//
// ---------------- Pick your wiring ----------------
// TWO_MUX = 1: both sensors share ONE column mux and ONE row mux (2 boards).
//   Chest: rows on C0-C5,  columns on C0-C6
//   Back:  rows on C6-C11, columns on C7-C13
//   One ADC pin (GPIO36).
// TWO_MUX = 0: each sensor has its own pair of muxes (4 boards).
//   Both sensors use rows C0-C5 and columns C0-C6 on their own muxes.
//   Select lines shared; chest on GPIO36, back on GPIO39, each with its
//   own 660 ohm pull-up.
#define TWO_MUX 1

// ---------------- Pins (course defaults) ----------------
const uint8_t COL_SEL[4] = {33, 25, 26, 27};  // column / sense mux S0-S3
const uint8_t ROW_SEL[4] = {21, 22, 23, 14};  // row / ground mux S0-S3
#define ADC_CHEST 36  // VP
#define ADC_BACK  39  // VN (only used when TWO_MUX = 0)

#define ROWS 6
#define COLS 7

// Which mux channel each physical strip is on, [sensor][strip].
// Run python/find_channels.py with the channel_finder sketch to get these.
//   ROW_STRIP: channel of physical rows R1..R6 (top to bottom)
//   COL_STRIP: channel of physical columns C1..C7 (left to right)
//   TRANSPOSED = 1: the row strips are on the COLUMN mux and the column
//                   strips on the ROW mux (strips swapped between muxes).
#if TWO_MUX
const uint8_t TRANSPOSED[2] = {0, 0};
const uint8_t ROW_STRIP[2][ROWS] = {{0, 1, 2, 3, 4, 5}, {6, 7, 8, 9, 10, 11}};
const uint8_t COL_STRIP[2][COLS] = {{0, 1, 2, 3, 4, 5, 6}, {7, 8, 9, 10, 11, 12, 13}};
const uint8_t ADC_PIN[2] = {ADC_CHEST, ADC_CHEST};
#else
const uint8_t TRANSPOSED[2] = {0, 0};
const uint8_t ROW_STRIP[2][ROWS] = {{0, 1, 2, 3, 4, 5}, {0, 1, 2, 3, 4, 5}};
const uint8_t COL_STRIP[2][COLS] = {{0, 1, 2, 3, 4, 5, 6}, {0, 1, 2, 3, 4, 5, 6}};
const uint8_t ADC_PIN[2] = {ADC_CHEST, ADC_BACK};
#endif

// ---------------- Settings ----------------
#define BAUD_RATE 250000
#define SAMPLES 3            // averaged per intersection
#define SETTLE_US 300        // wait after switching a mux channel
#define SCAN_DELAY_MS 10     // pause between frames

float volts[2][ROWS][COLS];

void selectChannel(const uint8_t pins[4], uint8_t ch) {
  for (uint8_t b = 0; b < 4; b++) digitalWrite(pins[b], (ch >> b) & 1);
}

// Calibrated reading in volts. The first conversion after a switch is
// discarded: the ADC's sample capacitor still holds the previous point.
float readVolts(uint8_t pin) {
  analogRead(pin);
  uint32_t mv = 0;
  for (uint8_t i = 0; i < SAMPLES; i++) mv += analogReadMilliVolts(pin);
  return mv / (1000.0f * SAMPLES);
}

void scan() {
  for (uint8_t s = 0; s < 2; s++) {
    for (uint8_t r = 0; r < ROWS; r++) {
      for (uint8_t c = 0; c < COLS; c++) {
        uint8_t rowMux = TRANSPOSED[s] ? COL_STRIP[s][c] : ROW_STRIP[s][r];
        uint8_t colMux = TRANSPOSED[s] ? ROW_STRIP[s][r] : COL_STRIP[s][c];
        selectChannel(ROW_SEL, rowMux);
        selectChannel(COL_SEL, colMux);
        delayMicroseconds(SETTLE_US);
        volts[s][r][c] = readVolts(ADC_PIN[s]);
      }
    }
  }
}

// One frame per line:
// F,<ms since boot>,<42 chest volts row by row>,<42 back volts row by row>
void sendFrame() {
  Serial.print("F,");
  Serial.print(millis());
  for (uint8_t s = 0; s < 2; s++)
    for (uint8_t r = 0; r < ROWS; r++)
      for (uint8_t c = 0; c < COLS; c++) {
        Serial.print(',');
        Serial.print(volts[s][r][c], 3);
      }
  Serial.println();
}

void setup() {
  Serial.begin(BAUD_RATE);
  for (uint8_t b = 0; b < 4; b++) {
    pinMode(COL_SEL[b], OUTPUT);
    pinMode(ROW_SEL[b], OUTPUT);
  }
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);  // ~0-3.1 V usable range
  Serial.println("Initialization complete, starting matrix scan...");
}

void loop() {
  scan();
  sendFrame();
  delay(SCAN_DELAY_MS);
}
