import RPi.GPIO as GPIO
import json
import requests
import time
import logging

from pn532 import *

#-------------------- Hardware Configs --------------------
# Pin numbers in Pi
led_pin = 18
button_pin = 17

# Help variables to track button pressed time
button_start = time.time()
button_end = time.time()

# GPIO configurations
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Pin definition
GPIO.setup(led_pin, GPIO.OUT)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Variable to block reading while tag read being proccessed
card_read = False

#-------------------- Station Configs --------------------

stationID = 2
buttonDefaultWaterType = "Tap"

#-------------------- Backend Configs --------------------

# Define the headers and the endpoint (specifying that the content type is JSON)
endpoint = "https://poseidon-backend.fly.dev"
NFC_preferences = endpoint + "/bottles/preferences/"
water_transactions = endpoint + "/water_transactions"

headers = {"Content-Type": "application/json"}

#-------------------- Helper functions --------------------

def turn_on_led_for(seconds):
    GPIO.output(led_pin,GPIO.HIGH)
    time.sleep(seconds)
    GPIO.output(led_pin,GPIO.LOW)
    return True

def button_callback(channel):
    global button_start, button_end
    if GPIO.input(button_pin) == 1:
        # Start timer
        button_start = time.time()
        # Turn on LED
        GPIO.output(led_pin,GPIO.HIGH)

    if GPIO.input(button_pin) == 0:
        # End timer and calculate elapsed
        button_end = time.time()
        elapsed = button_end - button_start
        # Turn off LED
        GPIO.output(led_pin,GPIO.LOW)
        logger.debug("Button pressed for %i" % elapsed)
        #Inform Backend
        post_water_transaction("", "", buttonDefaultWaterType, elapsed)

# To-Do add station and user id
def post_water_transaction(bottleID, userID, waterType, seconds):
    ml = str(seconds * 100)

    body_object = {
        "station_id": stationID,
        "bottle_id": bottleID,
        "user_id": userID,
        "volume": ml,
        "water_type": waterType
    }

    body_json = json.dumps(body_object)

    response = requests.post(url=water_transactions, data=body_json, headers=headers)
    logger.debug(response)

#-------------------- Init --------------------

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

                logger.info('Water delivery started')

                # More or less one second each 100 ml
                time_on = fillVolume / 100
                turn_on_led_for(time_on)

                logger.info('Water delivery finished')

                #Inform Backend
                post_water_transaction(bottleID, userID, waterType, time_on)

            except:
                logger.error("server response: %s: %s" % (response, response.text))

            card_read = False

except KeyboardInterrupt:
    logger.warning("....Program terminated by user...")
    GPIO.cleanup()







