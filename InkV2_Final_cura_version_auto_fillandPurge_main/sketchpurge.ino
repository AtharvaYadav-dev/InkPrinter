/*********************************************************************
 * STM32F411CE Blackpill
 * BTN1 : Clockwise Start / Stop -> Now Controlled via Serial (FILL)
 * BTN2 : Anticlockwise Start / Stop -> Now Controlled via Serial (PURGE)
 *********************************************************************/

#include <Arduino.h>

/*********************************************************************
 * Pin Definitions
 *********************************************************************/
#define STEP_PIN    PB10
#define DIR_PIN     PB2
#define LED_PIN     PC13
#define IR_SENSOR_PIN PA0

// Adjust this value according to your stepper driver microstepping and motor
#define STEPS_PER_MM 100 

/*********************************************************************
 * Hardware Timer
 *********************************************************************/
HardwareTimer StepTimer(TIM2);

/*********************************************************************
 * Motion Variables
 *********************************************************************/
volatile bool motorRunning = false;
volatile bool stepState = false;
volatile uint32_t pulseCount = 0;
volatile uint32_t targetPulses = 0;

bool direction = true;      // true = CW (FILL), false = CCW (PURGE)

volatile bool isHoming = false;
int initialIRState = 0;

/*********************************************************************
 * Timer Interrupt
 *********************************************************************/
void StepTimerISR()
{
    if(!motorRunning)
        return;

    if (targetPulses > 0 && pulseCount >= targetPulses) {
        motorRunning = false;
        targetPulses = 0;
        GPIOB->BSRR = GPIO_BSRR_BR10; // Ensure step pin is LOW
        return;
    }

    if(stepState)
    {
        GPIOB->BSRR = GPIO_BSRR_BR10;
        stepState = false;
        pulseCount++;
    }
    else
    {
        GPIOB->BSRR = GPIO_BSRR_BS10;
        stepState = true;
    }
}

/*********************************************************************
 * Setup
 *********************************************************************/
void setup()
{
    pinMode(STEP_PIN, OUTPUT);
    pinMode(DIR_PIN, OUTPUT);
    pinMode(LED_PIN, OUTPUT);
    pinMode(IR_SENSOR_PIN, INPUT_PULLUP);

    digitalWrite(STEP_PIN, LOW);
    digitalWrite(DIR_PIN, LOW);

    // Start Serial for USB and Serial1 for TX/RX pins
    Serial.begin(115200);
    Serial1.begin(115200);

    StepTimer.setOverflow(150, MICROSEC_FORMAT);
    StepTimer.attachInterrupt(StepTimerISR);
    StepTimer.resume();
}

/*********************************************************************
 * Helper for Processing Serial Commands
 *********************************************************************/
void processCommand(String cmd) {
    cmd.trim();
    if (cmd == "STOP") {
        motorRunning = false;
        targetPulses = 0;
        isHoming = false;
        GPIOB->BSRR = GPIO_BSRR_BR10;
        return;
    }

    if (cmd == "HOME") {
        direction = true;
        digitalWrite(DIR_PIN, HIGH);
        pulseCount = 0;
        stepState = false;
        GPIOB->BSRR = GPIO_BSRR_BR10;
        targetPulses = 0; // Continuous
        motorRunning = true;
        isHoming = true;
        initialIRState = digitalRead(IR_SENSOR_PIN);
        return;
    }

    if (cmd.startsWith("FILL")) {
        float distance = 0.0;
        if (cmd.length() > 5) {
            distance = cmd.substring(5).toFloat();
        }
        if (direction != true || !motorRunning) {
            direction = true;
            digitalWrite(DIR_PIN, HIGH);
            pulseCount = 0;
            targetPulses = 0;
        }
        stepState = false;
        GPIOB->BSRR = GPIO_BSRR_BR10;
        if (distance > 0.0) {
            targetPulses += (uint32_t)(distance * STEPS_PER_MM);
        } else {
            targetPulses = 0; // Continuous
        }
        motorRunning = true;
        isHoming = false;
    } else if (cmd.startsWith("PURGE")) {
        float distance = 0.0;
        if (cmd.length() > 6) {
            distance = cmd.substring(6).toFloat();
        }
        if (direction != false || !motorRunning) {
            direction = false;
            digitalWrite(DIR_PIN, LOW);
            pulseCount = 0;
            targetPulses = 0;
        }
        stepState = false;
        GPIOB->BSRR = GPIO_BSRR_BR10;
        if (distance > 0.0) {
            targetPulses += (uint32_t)(distance * STEPS_PER_MM);
        } else {
            targetPulses = 0; // Continuous
        }
        motorRunning = true;
        isHoming = false;
    }
}

/*********************************************************************
 * Loop
 *********************************************************************/
String inputString1 = "";
String inputStringUSB = "";

void loop()
{
    // Homing check
    if (isHoming && motorRunning) {
        if (digitalRead(IR_SENSOR_PIN) != initialIRState) {
            motorRunning = false;
            isHoming = false;
            GPIOB->BSRR = GPIO_BSRR_BR10;
            Serial.println("HOMED");
            Serial1.println("HOMED");
        }
    }

    // Read from Serial1 (RX/TX pins)

    while (Serial1.available()) {
        char inChar = (char)Serial1.read();
        if (inChar == '\n' || inChar == '\r') {
            if (inputString1.length() > 0) {
                processCommand(inputString1);
                inputString1 = "";
            }
        } else {
            inputString1 += inChar;
        }
    }
    
    // Read from USB Serial
    while (Serial.available()) {
        char inChar = (char)Serial.read();
        if (inChar == '\n' || inChar == '\r') {
            if (inputStringUSB.length() > 0) {
                processCommand(inputStringUSB);
                inputStringUSB = "";
            }
        } else {
            inputStringUSB += inChar;
        }
    }

    digitalWrite(LED_PIN, motorRunning ? LOW : HIGH); // Assuming active low LED
}