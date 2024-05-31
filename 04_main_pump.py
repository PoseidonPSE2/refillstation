import RPi.GPIO as GPIO
import json
import requests
import time
import logging

from pn532 import *

#-------------------- Hardware Configs --------------------
# Pin numbers in Pi
green_led_pin = 18
button_pin = 17
relais_pin = 27
blue_led_pin = 22

# Help variables to track button pressed time
button_start = time.time()
button_end = time.time()

# GPIO configurations
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Pin definition
GPIO.setup(green_led_pin, GPIO.OUT)
GPIO.setup(relais_pin, GPIO.OUT)
GPIO.setup(blue_led_pin, GPIO.OUT)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Variable to block reading while tag read being proccessed
card_read = False

#-------------------- Station Configs --------------------

# Should be correctly set for each station
stationID = 2
buttonDefaultWaterType = "Tap"
timeToPutBottle = 3

#-------------------- Backend Configs --------------------

# Define the headers and the endpoint (specifying that the content type is JSON)
endpoint = "https://poseidon-backend.fly.dev"
NFC_preferences = endpoint + "/bottles/preferences/"
water_transactions = endpoint + "/water_transactions"

headers = {"Content-Type": "application/json"}

#-------------------- Helper functions --------------------

def turn_off_all():
    turn_off_gpio(blue_led_pin)
    turn_off_gpio(green_led_pin)
    turn_off_gpio(relais_pin)

def turn_on_water_pump_for(led, relais, seconds):
    if GPIO.input(led) == GPIO.LOW and GPIO.input(relais) == GPIO.LOW:
        GPIO.output(led,GPIO.HIGH)
        GPIO.output(relais,GPIO.HIGH)
        
        time.sleep(seconds)
        
        GPIO.output(led,GPIO.LOW)
        GPIO.output(relais,GPIO.LOW)
    return True

def blink_led_n_times(n, led):
    for _ in range(n):
        GPIO.output(led, GPIO.HIGH)
        time.sleep(0.2)
        GPIO.output(led, GPIO.LOW)
        time.sleep(0.2)
    return True

def turn_on_gpio(led):
    if GPIO.input(led) == GPIO.LOW:
        GPIO.output(led,GPIO.HIGH)
    return True

def turn_off_gpio(led):
    if GPIO.input(led) == GPIO.HIGH:
        GPIO.output(led,GPIO.LOW)
    return True

def button_callback(channel):
    global button_start, button_end
    if GPIO.input(button_pin) == 1:
        # Start timer
        button_start = time.time()
        # Turn on LED
        GPIO.output(blue_led_pin, GPIO.HIGH)
        GPIO.output(relais_pin, GPIO.HIGH)

    if GPIO.input(button_pin) == 0:
        # End timer and calculate elapsed
        button_end = time.time()
        elapsed = button_end - button_start
        # Turn off LED
        GPIO.output(blue_led_pin, GPIO.LOW)
        GPIO.output(relais_pin, GPIO.LOW)
        logger.debug("Button pressed for %i" % elapsed)
        #Inform Backend
        post_water_transaction("", "", buttonDefaultWaterType, elapsed)

def post_water_transaction(bottleID, userID, waterType, seconds):
    ml = str(seconds * 100)

    body_object = {
        "station_id": stationID,
        "bottle_id": bottleID,
        "user_id": userID,
        "volume": ml,
        "water_Type": waterType
    }

    body_json = json.dumps(body_object)

    response = requests.post(url=water_transactions, data=body_json, headers=headers)
    logger.debug(response)

#-------------------- Init --------------------

turn_off_all()

# Turn on the led for knowing the programm is running
turn_on_gpio(green_led_pin)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create a logger"
logger = logging.getLogger(__name__)

# Set the callback for button pressed
GPIO.add_event_detect(button_pin, GPIO.BOTH, callback=button_callback, bouncetime=200)

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
            blink_led_n_times(3, blue_led_pin)

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
                time_on = fillVolume / 300
                turn_on_water_pump_for(blue_led_pin, relais_pin, time_on)

                logger.info('Water delivery finished')

                #Inform Backend
                # post_water_transaction(bottleID, userID, waterType, time_on)

            except:
                logger.error("server response: %s: %s" % (response, response.text))

            card_read = False

except KeyboardInterrupt:
    logger.warning("....Program terminated by user...")
    turn_off_gpio(green_led_pin)
    GPIO.cleanup()
finally:
    turn_off_all()
    GPIO.cleanup()







