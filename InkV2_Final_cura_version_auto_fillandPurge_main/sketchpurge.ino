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

bool direction = true;      // true = CW, false = CCW

/*********************************************************************
 * Timer Interrupt
 *********************************************************************/
void StepTimerISR()
{
    if(!motorRunning)
        return;

    if(stepState)
    {
        GPIOB->BSRR = GPIO_BSRR_BR10;
        stepState = false;
    }
    else
    {
        GPIOB->BSRR = GPIO_BSRR_BS10;
        stepState = true;
        pulseCount++;
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
    if (cmd.indexOf("FILL") != -1) {
        if (motorRunning && direction == true) {
            motorRunning = false;
            stepState = false;
            GPIOB->BSRR = GPIO_BSRR_BR10;
        } else {
            direction = true;
            digitalWrite(DIR_PIN, HIGH);
            pulseCount = 0;
            stepState = false;
            GPIOB->BSRR = GPIO_BSRR_BR10;
            motorRunning = true;
        }
    } else if (cmd.indexOf("PURGE") != -1) {
        if (motorRunning && direction == false) {
            motorRunning = false;
            stepState = false;
            GPIOB->BSRR = GPIO_BSRR_BR10;
        } else {
            direction = false;
            digitalWrite(DIR_PIN, LOW);
            pulseCount = 0;
            stepState = false;
            GPIOB->BSRR = GPIO_BSRR_BR10;
            motorRunning = true;
        }
    }
}

/*********************************************************************
 * Loop
 *********************************************************************/
String inputString1 = "";
String inputStringUSB = "";

void loop()
{
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