import RPi.GPIO as GPIO
import json
import requests
import time

from pn532 import *

led = 18
button = 17

start_time = None
button_pressed = False

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(led, GPIO.OUT)
GPIO.setup(button, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

def turn_on_led_for(seconds):
    GPIO.output(led,GPIO.HIGH)
    time.sleep(seconds)
    GPIO.output(led,GPIO.LOW)
    return True

def button_callback(channel):
    global start_time, button_pressed
    if GPIO.input(button) == GPIO.LOW:
        start_time = time.time()
        button_pressed = True
    else:
        if start_time is not None:
            duration = time.time() - start_time
            print("Button pressed for {:.2f} seconds".format(duration))
            start_time = None
            button_pressed = False

# Define the headers and the endpoint (specifying that the content type is JSON)
tag_id_endpoint = "https://webhook.site/fdb9b6e1-fc04-4272-89b7-c10fbe2015fb"
headers = {'Content-Type': 'application/json'}

# Variable to block reading while tag read being proccessed
card_read = False

GPIO.add_event_detect(button, GPIO.BOTH, callback=button_callback, bouncetime=200)


pn532 = PN532_I2C(debug=False, reset=20, req=16)

ic, ver, rev, support = pn532.get_firmware_version()
print('Found PN532 with firmware version: {0}.{1}'.format(ver, rev))

# Configure PN532 to communicate with MiFare cards
pn532.SAM_configuration()

print('Waiting for RFID/NFC card to read from!')
try:
    while True:
        if GPIO.input(button) == GPIO.HIGH:
            print("Button was pushed!")

        # Check if a card is available to read
        uid = pn532.read_passive_target(timeout=0.5)
                
        # Try again if no card is available.
        if uid is not None:
            card_read = True

        if card_read == True:
            tag_id = ':'.join(['{:02X}'.format(byte) for byte in uid])
            print('Found card with UID:', tag_id)
            print('Fetching data for given id.')
            
            json_request = {
                "tag_id": tag_id
            }

            # Send the get request with the JSON data
            response = requests.get(tag_id_endpoint, data=json_request, headers=headers)
            json_response = json.loads(response.text)

            # Access the properties
            user_id = json_response['User_ID']
            milliliter = json_response['Milliliter']

            # Print the response
            print(json_response)

            # More or less one second each 100 ml
            turn_on_led_for(milliliter / 100)

            print('Water succesfully delivered.')

            card_read = False

except KeyboardInterrupt:
    print("Program terminated by user.")
    GPIO.cleanup()







