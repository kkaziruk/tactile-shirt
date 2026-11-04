// Tactile Exercise Shirt - ESP32 firmware (Lab 6)
// Scans two 6x7 Velostat pressure grids (chest + back) with four
// CD74HC4067 multiplexers, following the course schematic.
//
// Circuit (same as the course 4x4 schematic, done twice):
//   SENSE mux (MUX1): C0-C6 -> the 7 vertical strips
//                     SIG   -> ADC pin, and through 660 ohm resistor to 3V3
//   GROUND mux (MUX2): C0-C5 -> the 6 horizontal strips
//                      SIG   -> GND
//   EN -> GND and VCC -> 3V3 on all four muxes.
//
// The selected horizontal strip is grounded. The selected vertical strip
// is pulled up to 3.3V through the 660 ohm resistor. The Velostat in
// between forms a voltage divider:
//   V_adc = 3.3 * R_velostat / (R_velostat + 660)
// No pressure -> high Velostat resistance -> V_adc near 3.3V.
// Pressure    -> lower resistance          -> V_adc drops.
//
// Both sense muxes share select lines, and both ground muxes share select
// lines. The chest and back are separate circuits, so each scan step reads
// the same (row, col) point on both sensors at once on two ADC pins.

// ---------------- Pin map (course defaults) ----------------
// Sense muxes (MUX1, chest + back), S0-S3
#define SENSE_S0 33
#define SENSE_S1 25
#define SENSE_S2 26
#define SENSE_S3 27
// Ground muxes (MUX2, chest + back), S0-S3
#define GND_S0 21
#define GND_S1 22
#define GND_S2 23
#define GND_S3 14

#define ADC_CHEST 36  // VP pin: SIG of chest sense mux (ADC1_CH0)
#define ADC_BACK  39  // VN pin: SIG of back sense mux  (ADC1_CH3)

// ---------------- Grid ----------------
#define NUM_ROWS 6  // horizontal strips -> ground mux
#define NUM_COLS 7  // vertical strips   -> sense mux

// Mux channel (0-15) each strip is soldered to, in physical order.
// If a strip is on a different channel, change it here instead of rewiring.
const int ROW_CH[NUM_ROWS] = {0, 1, 2, 3, 4, 5};
const int COL_CH[NUM_COLS] = {0, 1, 2, 3, 4, 5, 6};

// ---------------- Settings ----------------
#define BAUD_RATE 250000         // same as the course code
#define SAMPLES_PER_POINT 3      // averaged per intersection
#define SETTLE_US 100            // wait after switching a channel
#define SCAN_DELAY_MS 10         // pause between frames

float chest[NUM_ROWS][NUM_COLS];
float back[NUM_ROWS][NUM_COLS];

// Set S0-S3 to the 4-bit binary value of ch (0-15). S0 is the LSB.
void selectChannel(int s0, int s1, int s2, int s3, int ch) {
  digitalWrite(s0, ch & 0x01);
  digitalWrite(s1, (ch >> 1) & 0x01);
  digitalWrite(s2, (ch >> 2) & 0x01);
  digitalWrite(s3, (ch >> 3) & 0x01);
}

// Averaged reading in volts. The first read after a switch is discarded:
// the ADC's sample capacitor still holds charge from the previous point.
float readVoltage(int pin) {
  analogRead(pin);
  float sum = 0;
  for (int i = 0; i < SAMPLES_PER_POINT; i++) {
    sum += analogRead(pin) * (3.3 / 4095.0);
  }
  return sum / SAMPLES_PER_POINT;
}

void scanMatrices() {
  for (int r = 0; r < NUM_ROWS; r++) {
    selectChannel(GND_S0, GND_S1, GND_S2, GND_S3, ROW_CH[r]);      // ground one row
    for (int c = 0; c < NUM_COLS; c++) {
      selectChannel(SENSE_S0, SENSE_S1, SENSE_S2, SENSE_S3, COL_CH[c]);  // sense one column
      delayMicroseconds(SETTLE_US);
      chest[r][c] = readVoltage(ADC_CHEST);
      back[r][c]  = readVoltage(ADC_BACK);
    }
  }
}

// One frame per line:
// F,<ms since boot>,<42 chest volts, row by row>,<42 back volts, row by row>
void sendFrame() {
  Serial.print("F,");
  Serial.print(millis());
  for (int r = 0; r < NUM_ROWS; r++)
    for (int c = 0; c < NUM_COLS; c++) {
      Serial.print(',');
      Serial.print(chest[r][c], 3);
    }
  for (int r = 0; r < NUM_ROWS; r++)
    for (int c = 0; c < NUM_COLS; c++) {
      Serial.print(',');
      Serial.print(back[r][c], 3);
    }
  Serial.println();
}

void setup() {
  Serial.begin(BAUD_RATE);

  int pins[] = {SENSE_S0, SENSE_S1, SENSE_S2, SENSE_S3,
                GND_S0, GND_S1, GND_S2, GND_S3};
  for (int i = 0; i < 8; i++) pinMode(pins[i], OUTPUT);

  analogReadResolution(12);        // 0-4095
  analogSetAttenuation(ADC_11db);  // full 0-3.3V input range

  Serial.println("Initialization complete, starting matrix scan...");
}

void loop() {
  scanMatrices();
  sendFrame();
  delay(SCAN_DELAY_MS);
}
