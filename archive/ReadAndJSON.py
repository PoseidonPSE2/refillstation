import RPi.GPIO as GPIO
import re
import json

import pn532.pn532 as nfc
from pn532 import *

def extract_text(data):
    # Find the start and end indices of the desired text
    start_index = data.find(b"\x02en") + len(b"\x02en")
    end_index = data.find(b"\xfe\x00")
    # Extract the text between the start and end indices
    extracted_text = data[start_index:end_index].decode('utf-8', errors='replace')
    printable_text = re.sub(r'[^ -~]', '', extracted_text)
    return printable_text

pn532 = PN532_I2C(debug=False, reset=20, req=16)

ic, ver, rev, support = pn532.get_firmware_version()
print('Found PN532 with firmware version: {0}.{1}'.format(ver, rev))

# Configure PN532 to communicate with MiFare cards
pn532.SAM_configuration()

print('Waiting for RFID/NFC card to read from!')
while True:
    # Check if a card is available to read
    uid = pn532.read_passive_target(timeout=0.5)
    print('.', end="")
    # Try again if no card is available.
    if uid is not None:
        break
print('Found card with UID:', [hex(i) for i in uid])

key_b = b'\xFF\xFF\xFF\xFF\xFF\xFF'
content = b''

# First 3 blocks not relevant
for i in range(4, 10):
    # Skip the block headers
    if i % 4 == 3:
        continue
    try:
        # Authenticate with the tag
        pn532.mifare_classic_authenticate_block(
            uid, block_number=i, key_number=nfc.MIFARE_CMD_AUTH_B, key=key_b)
        # Read block data
        block_data = pn532.mifare_classic_read_block(i)

        print('Block[', i ,']', block_data)

        content += block_data
    except nfc.PN532Error as e:
        print(e.errmsg)

trimmed_text = extract_text(content)
json_string = json.dumps(trimmed_text)

print('Found JSON:', json_string)

GPIO.cleanup()
