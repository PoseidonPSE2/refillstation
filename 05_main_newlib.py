import json
from math import floor
import requests
import time
import logging

from gpiozero import LED, Button

from pn532 import *

#-------------------- Hardware Configs --------------------
# Pin numbers in Pi
relais_pin = 4
button_pin = 17
green_led_pin = 23
blue_led_pin = 27

# Help variables to track button pressed time
button_start = time.time()
button_end = time.time()

# Pin definition
button = Button(button_pin)
green_led = LED(green_led_pin)
blue_led = LED(blue_led_pin)
pump = LED(relais_pin)

# Blue led shoud indicate when the button is pressed
button.when_pressed = blue_led.on
button.when_released = blue_led.off

# Variable to block reading while tag read being proccessed
card_read = False

# Variable to hold the time when the button is pressed
pressed_time = 0

# Variable to hold the duration the button was held
hold_duration = 0

#-------------------- Station Configs --------------------

# Should be correctly set for each station
stationID = 2
buttonDefaultWaterType = "Tap"
pumpSpeed = 200
timeToPutBottle = 3

#-------------------- Backend Configs --------------------

# Define the headers and the endpoint (specifying that the content type is JSON)
endpoint = "https://poseidon-backend.fly.dev"
NFC_preferences = endpoint + "/bottles/preferences/"
water_transactions = endpoint + "/water_transactions"

headers = {"Content-Type": "application/json"}

#-------------------- Helper functions --------------------

def turn_off_all():
    green_led.off()
    blue_led.off()
    pump.off()

def turn_on_water_pump_for(seconds):
    blue_led.on()
    pump.on()

    time.sleep(seconds)
    
    blue_led.off()
    pump.off() 
    return True

def blink_led_n_times(n, led):
    for _ in range(n):
        led.on()
        time.sleep(0.2)
        led.off()
        time.sleep(0.2)
    return True

def button_pressed():
    global pressed_time
    pressed_time = time.time()
    blue_led.on()
    pump.on()

def button_released():
    global hold_duration
    hold_duration = time.time() - pressed_time
    blue_led.off()
    pump.off()
    logger.info(f"Button released! Held for {hold_duration:.2f} seconds.")
    post_water_transaction(buttonDefaultWaterType, hold_duration, True)

def post_water_transaction(waterType, seconds, guest=False, bottleID=0, userID=0):
    ml = floor(seconds * pumpSpeed)

    if guest:
        body_object = {
        "stationId": stationID,
        "volume": ml,
        "waterType": waterType,
        "guest": True
        }
    else:
        body_object = {
            "stationId": stationID,
            "bottleId": bottleID,
            "userId": userID,
            "volume": ml,
            "waterType": waterType
        }

    body_json = json.dumps(body_object)

    logger.debug("Posting object: %s, to endpoint: %s", body_json, water_transactions)

    response = requests.post(url=water_transactions, data=body_json, headers=headers)
    logger.debug(response)

#-------------------- Init --------------------

turn_off_all()

# Attach the functions to the button's events
button.when_pressed = button_pressed
button.when_released = button_released

# Turn on the led for knowing the programm is running
green_led.on()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create a logger"
logger = logging.getLogger(__name__)

# PN532 Config
pn532 = PN532_I2C(debug=False, reset=20, req=16)
ic, ver, rev, support = pn532.get_firmware_version()
message = 'Found PN532 with firmware version: {0}.{1}'.format(ver, rev)
logger.info(message)


# Configure PN532 to communicate with MiFare cards
pn532.SAM_configuration()

#-------------------- Main Loop --------------------

logger.info('Waiting for RFID/NFC card to read from!')
try:
    while True:
        # Check if a card is available to read
        uid = pn532.read_passive_target(timeout=0.5)
                
        # Try again if no card is available.
        if uid is not None:
            card_read = True

        if card_read == True:
            # Signal something was read
            blink_led_n_times(3, blue_led)

            tag_id = ':'.join(['{:02X}'.format(byte) for byte in uid])
            logger.info('Found RFID-Tag with UID: %s' % tag_id)

            request_endpoint = NFC_preferences + tag_id

            # Send the get request with the JSON data
            response = requests.get(url=request_endpoint)
            
            try:
                json_response = json.loads(response.text)
                # Access the properties
                bottleID = json_response['id']
                userID = json_response['user_id']
                fillVolume = int(json_response['fill_volume'])
                waterType = json_response['water_type']

                # Print the response
                logger.info("Data found for id %s %s" % (tag_id, json_response))

                # Wait for the bottle to be placed
                time.sleep(timeToPutBottle)

                logger.info('Water delivery started')

                # More or less one second each 100 ml
                time_on = fillVolume / pumpSpeed
                turn_on_water_pump_for(time_on)

                logger.info('Water delivery finished')

                #Inform Backend
                post_water_transaction(waterType, time_on, False, bottleID, userID)

            except:
                logger.error("server response: %s: %s" % (response, response.text))

            card_read = False

except KeyboardInterrupt:
    logger.warning("....Program terminated by user...")
finally:
    turn_off_all()







