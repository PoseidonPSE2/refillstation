import json
import re
import sys
import threading
import requests
import time
import logging

import pn532.pn532 as nfc
import paho.mqtt.client as mqtt

from gpiozero import LED, Button
from math import floor
from pn532 import *

#-------------------- Helper functions --------------------

def initiate_panic():
    logger.info("Panic exit triggered.")
    turn_off_all()
    sys.exit()

# setting callbacks for different events to see if it works, print the message etc.
def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")

# with this callback you can see if your publish was successful
def on_publish(client, userdata, mid):
    logger.debug(f"client: {str(client)}, userdata: {str(userdata)},  mid: {str(mid)}")

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
    WHITE_LED.off()
    BLUE_LED.off()
    BLUE_PUMP.off()
    GREEN_LED.off()
    GREEN_PUMP.off()

def turn_on_water_pump_for(led, pump, seconds):
    led.on()
    pump.on()

    time.sleep(seconds)
    
    led.off()
    pump.off() 
    return True

def blink_led(led, blink_event):
    while not blink_event.is_set():
        led.off()
        time.sleep(0.2)
        led.on()
        time.sleep(0.2)

def start_blinking(led_id, led):
    global blink_controls
    blink_event = threading.Event()
    blink_event.clear()
    blink_thread = threading.Thread(target=blink_led, args=(led, blink_event))
    blink_controls[led_id] = (blink_event, blink_thread)
    blink_thread.start()
    return blink_thread

def stop_blinking(led_id):
    global blink_controls
    if led_id in blink_controls:
        blink_event, blink_thread = blink_controls[led_id]
        blink_event.set()
        blink_thread.join() # Ensure the blinking thread has finished
        del blink_controls[led_id]

def blink_led_n_times(n, led):
    for _ in range(n):
        led.off()
        time.sleep(0.2)
        led.on()
        time.sleep(0.2)
    return True

def green_button_pressed():
    global green_pressed_time
    green_pressed_time = time.time()
    GREEN_LED.on()
    GREEN_PUMP.on()

def green_button_released():
    global green_hold_duration
    green_hold_duration = time.time() - green_pressed_time
    GREEN_LED.off()
    GREEN_PUMP.off()
    logger.info(f"Tap water button released! Held for {green_hold_duration:.2f} seconds.")
    post_water_transaction(TAP_WATER, green_hold_duration, True)

def blue_button_pressed():
    global blue_pressed_time
    blue_pressed_time = time.time()
    BLUE_LED.on()
    BLUE_PUMP.on()

def blue_button_released():
    global blue_hold_duration
    blue_hold_duration = time.time() - blue_pressed_time
    BLUE_LED.off()
    BLUE_PUMP.off()
    logger.info(f"Mineral water button released! Held for {blue_hold_duration:.2f} seconds.")
    post_water_transaction(MINERAL_WATER, blue_hold_duration, True)

def post_water_transaction(waterType, seconds, guest=False, bottleID=0, userID=0):
    ml = floor(seconds * PUMP_SPEED)

    if guest:
        body_object = {
        "station_id": STATION_ID,
        "volume": ml,
        "water_type": waterType,
        "guest": True
        }
    else:
        body_object = {
            "station_id": STATION_ID,
            "bottle_id": bottleID,
            "user_id": userID,
            "volume": ml,
            "water_type": waterType
        }

    body_json = json.dumps(body_object)

    logger.debug("Posting object: %s, to endpoint: %s", body_json, ENDPOINT_WATER_TRANS)

    response = requests.post(url=ENDPOINT_WATER_TRANS, data=body_json, headers=REQUEST_HEADERS)
    logger.debug(response)

#-------------------- Constants --------------------

# Should be correctly set for each station
STATION_ID = 2

# Dictionary to store threading events and threads for each LED
blink_controls = {}

# Calculated speed of pump ml/s
PUMP_SPEED = 38

# Time between reading RFID and starting pump
TIMEOUT_PUT_BOTTLE = 3

# Pi gpio numberin
WHITE_LED_PIN = 23
PANIC_BUTTON_PIN = 24

BLUE_PUMP_PIN = 26
BLUE_BUTTON_PIN = 6
BLUE_LED_PIN = 27

GREEN_PUMP_PIN = 16
GREEN_BUTTON_PIN = 5
GREEN_LED_PIN = 22

# Water types
TAP_WATER = "tap"
MINERAL_WATER = "mineral"

# Key to encrypt information in NFC
NFC_KEY = b'\xFF\xFF\xFF\xFF\xFF\xFF'

# Define the headers and the endpoint (specifying that the content type is JSON)
ENDPOINT_BASE = "https://poseidon-backend.fly.dev"
ENDPOINT_BOTTLE_PREF = ENDPOINT_BASE + "/bottles/preferences/"
ENDPOINT_WATER_TRANS = ENDPOINT_BASE + "/water_transactions"

REQUEST_HEADERS = {"Content-Type": "application/json"}

MQTT_BROKER_ADRESS = "maqiatto.com"
MQTT_BROKER_PORT = 1883
MQTT_BASE_TOPIC = "alexresklin@gmail.com/AppData/User-"

MQTT_BROKER_USER = "alexresklin@gmail.com"
MQTT_BROKER_PW = "poseidon"

#-------------------- Hardware Configs --------------------

# Pin definition
WHITE_LED = LED(WHITE_LED_PIN)
PANIC_BUTTON = Button(PANIC_BUTTON_PIN)

BLUE_BUTTON = Button(BLUE_BUTTON_PIN)
BLUE_LED = LED(BLUE_LED_PIN)
BLUE_PUMP = LED(BLUE_PUMP_PIN, active_high=False)

GREEN_BUTTON = Button(GREEN_BUTTON_PIN)
GREEN_LED = LED(GREEN_LED_PIN)
GREEN_PUMP = LED(GREEN_PUMP_PIN, active_high=False)

# Button behavior definition
PANIC_BUTTON.when_pressed = initiate_panic

# Attach the functions to the button's events
BLUE_BUTTON.when_pressed = blue_button_pressed
BLUE_BUTTON.when_released = blue_button_released

GREEN_BUTTON.when_pressed = green_button_pressed
GREEN_BUTTON.when_released = green_button_released

# Variable to block reading while tag read being proccessed
card_read = False

#-------------------- MQTT Init --------------------

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
client.on_connect = on_connect
client.on_publish = on_publish

# set username and password
client.username_pw_set(MQTT_BROKER_USER, MQTT_BROKER_PW)

#-------------------- Init --------------------

turn_off_all()

# Turn on the led for knowing the programm is running
WHITE_LED.on()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create a logger"
logger = logging.getLogger(__name__)

# Connect to Broker
client.connect(MQTT_BROKER_ADRESS, MQTT_BROKER_PORT)

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
            # nfc_content = read_nfc_content(4, 6)
            # tag_id = ':'.join(['{:02X}'.format(byte) for byte in uid])
            # logger.debug('RFID-Tag with UID: %s, RFID-Tag content: %s', tag_id, nfc_content)
            tag_id = ':'.join(['{:02X}'.format(byte) for byte in uid])
            logger.info('Found RFID-Tag with UID: %s' % tag_id)

            # Signal something was read
            start_blinking("WHITE", WHITE_LED)
            #blink_led_n_times(3, WHITE_LED)

            request_endpoint = ENDPOINT_BOTTLE_PREF + tag_id

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

            except Exception as e:
                logger.error(f"An error occurred on decoding answer from server: {e}")

            stop_blinking("WHITE")
            WHITE_LED.on()

            isTapWater = waterType.lower() == TAP_WATER
            isMineralWater = waterType.lower() == MINERAL_WATER

            if isTapWater:
                start_blinking("GREEN", GREEN_LED)
            elif isMineralWater:
                start_blinking("BLUE", BLUE_LED)

            # Wait for the bottle to be placed
            time.sleep(TIMEOUT_PUT_BOTTLE)

            # Post to a topic based on the user id
            mqttTopic = MQTT_BASE_TOPIC + str(userID)
            
            # More or less one second each 100 ml
            timeOn = round(fillVolume / PUMP_SPEED, 2)

            data = {"duration": timeOn}
            json_string = json.dumps(data)
            client.publish(mqttTopic, json_string, qos=0)

            logger.info(f"MQTT message posted to {mqttTopic}, containing {json_string}")

            if waterType.lower() == TAP_WATER:
                logger.info(f"Tap water delivery started for {fillVolume} ml ({timeOn} seconds)")
                
                stop_blinking("GREEN")
                turn_on_water_pump_for(GREEN_LED, GREEN_PUMP, timeOn)

                logger.info(f"Tap water delivery finished for {fillVolume} ml ({timeOn} seconds)")
                
                #Inform Backend
                post_water_transaction(waterType, timeOn, False, bottleID, userID)

            elif waterType.lower() == MINERAL_WATER:
                logger.info(f"Mineral water delivery started for {fillVolume} ml ({timeOn} seconds)")
                
                stop_blinking("BLUE")
                turn_on_water_pump_for(BLUE_LED, BLUE_PUMP, timeOn)

                logger.info(f"Mineral water delivery finished for {fillVolume} ml ({timeOn} seconds)")
                
                #Inform Backend
                post_water_transaction(waterType, timeOn, False, bottleID, userID)

            card_read = False

except KeyboardInterrupt:
    logger.warning("....Programm terminated by user...")
finally:
    turn_off_all()







