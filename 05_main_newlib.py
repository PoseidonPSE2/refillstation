import json
from math import floor
import re
import requests
import time
import logging

from gpiozero import LED, Button

from pn532 import *
import pn532.pn532 as nfc

#-------------------- Constants --------------------

# Pin numbers in Pi
TAP_RELAIS_PIN = 4
TAP_BUTTON_PIN = 17
GREEN_LED_PIN = 23
BLUE_LED_PIN = 27

# Water types
TAP_WATER = "tap"
MINERAL_WATER = "mineral"

# Should be correctly set for each station
STATION_ID = 2

# Calculated speed of pump ml/s
PUMP_SPEED = 38

# Time between reading RFID and starting pump
TIMEOUT_PUT_BOTTLE = 3

# Key to encrypt information in NFC
NFC_KEY = b'\xFF\xFF\xFF\xFF\xFF\xFF'

# Define the headers and the endpoint (specifying that the content type is JSON)
ENDPOINT_BASE = "https://poseidon-backend.fly.dev"
ENDPOINT_BOTTLE_PREF = ENDPOINT_BASE + "/bottles/preferences/"
ENDPOINT_WATER_TRANS = ENDPOINT_BASE + "/water_transactions"

REQUEST_HEADERS = {"Content-Type": "application/json"}

#-------------------- Hardware Configs --------------------

# Help variables to track button pressed time
button_start = time.time()
button_end = time.time()

# Pin definition
tap_button = Button(TAP_BUTTON_PIN)
green_led = LED(GREEN_LED_PIN)
blue_led = LED(BLUE_LED_PIN)
tap_pump = LED(TAP_RELAIS_PIN)

# Blue led shoud indicate when the button is pressed
tap_button.when_pressed = blue_led.on
tap_button.when_released = blue_led.off

# Variable to block reading while tag read being proccessed
card_read = False

# Variable to hold the time when the button is pressed
pressed_time = 0

# Variable to hold the duration the button was held
hold_duration = 0

#-------------------- Helper functions --------------------

def extract_text(data):
    # Find the start and end indices of the desired text
    start_index = data.find(b"\x02en") + len(b"\x02en")
    end_index = data.find(b"\xfe\x00")
    # Extract the text between the start and end indices
    extracted_text = data[start_index:end_index].decode('utf-8', errors='replace')
    printable_text = re.sub(r'[^ -~]', '', extracted_text)
    return printable_text

def read_nfc_content(starting_block, ending_block):
    content = b''
    # First 3 blocks not relevant
    for i in range(starting_block, ending_block):
        # Skip the block headers
        if i % 4 == 3:
            continue
        try:
            # Authenticate with the tag
            pn532.mifare_classic_authenticate_block(uid, block_number=i, key_number=nfc.MIFARE_CMD_AUTH_B, key=NFC_KEY)
            
            # Read block data
            block_data = pn532.mifare_classic_read_block(i)

            content += block_data
        except nfc.PN532Error as e:
            logger.error(e.errmsg)

    return extract_text(content)

def turn_off_all():
    green_led.off()
    blue_led.off()
    tap_pump.off()

def turn_on_water_pump_for(seconds):
    blue_led.on()
    tap_pump.on()

    time.sleep(seconds)
    
    blue_led.off()
    tap_pump.off() 
    return True

def blink_led_n_times(n, led):
    for _ in range(n):
        led.on()
        time.sleep(0.2)
        led.off()
        time.sleep(0.2)
    return True

def tap_button_pressed():
    global pressed_time
    pressed_time = time.time()
    blue_led.on()
    tap_pump.on()

def tap_button_released():
    global hold_duration
    hold_duration = time.time() - pressed_time
    blue_led.off()
    tap_pump.off()
    logger.info(f"Tap water button released! Held for {hold_duration:.2f} seconds.")
    post_water_transaction(TAP_WATER, hold_duration, True)

def post_water_transaction(waterType, seconds, guest=False, bottleID=0, userID=0):
    ml = floor(seconds * PUMP_SPEED)

    if guest:
        body_object = {
        "stationId": STATION_ID,
        "volume": ml,
        "waterType": waterType,
        "guest": True
        }
    else:
        body_object = {
            "stationId": STATION_ID,
            "bottleId": bottleID,
            "userId": userID,
            "volume": ml,
            "waterType": waterType
        }

    body_json = json.dumps(body_object)

    logger.debug("Posting object: %s, to endpoint: %s", body_json, ENDPOINT_WATER_TRANS)

    response = requests.post(url=ENDPOINT_WATER_TRANS, data=body_json, headers=REQUEST_HEADERS)
    logger.debug(response)

#-------------------- Init --------------------

turn_off_all()

# Attach the functions to the button's events
tap_button.when_pressed = tap_button_pressed
tap_button.when_released = tap_button_released

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
            # Read the NFC-ID found in the memory
            nfc_content = read_nfc_content(4, 6)
            tag_id = ':'.join(['{:02X}'.format(byte) for byte in uid])
            logger.debug('RFID-Tag with UID: %s, RFID-Tag content: %s', tag_id, nfc_content)

            # Signal something was read
            blink_led_n_times(3, blue_led)

            request_endpoint = ENDPOINT_BOTTLE_PREF + nfc_content

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
                logger.info("Data found for id %s %s" % (nfc_content, json_response))

                if waterType.lower() == "tap":
                    # Wait for the bottle to be placed
                    time.sleep(TIMEOUT_PUT_BOTTLE)

                    logger.info('Tap water delivery started')

                    # More or less one second each 100 ml
                    time_on = fillVolume / PUMP_SPEED
                    turn_on_water_pump_for(time_on)

                    logger.info('Tap water delivery finished')

                    #Inform Backend
                    post_water_transaction(waterType, time_on, False, bottleID, userID)

            except:
                logger.error("server response: %s: %s" % (response, response.text))

            card_read = False

except KeyboardInterrupt:
    logger.warning("....Program terminated by user...")
finally:
    turn_off_all()







