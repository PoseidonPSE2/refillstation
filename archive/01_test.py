import board
import busio
import time
from adafruit_pn532.i2c import PN532_I2C

# Create I2C interface
i2c = busio.I2C(board.SCL, board.SDA)

# Create PN532 object
pn532 = PN532_I2C(i2c, debug=False)

# Configure PN532 to communicate with NFC/RFID tags
pn532.SAM_configuration()

# Define MIFARE Classic key
key = b"\x00\x00\x00\x00\x00\x00"
key2 = b'\xFF\xFF\xFF\xFF\xFF\xFF'


while True:
    # Check if a tag is present
    uid = pn532.read_passive_target(timeout=0.5)
    if uid is not None:
        print("Found tag with UID:", [hex(i) for i in uid])
        # Authenticate to the tag
        if pn532.mifare_classic_authenticate_block(uid, 4, 0x61, key2):
            # Read block 4
            block_4_data = pn532.mifare_classic_read_block(4)
            print("Block 4 data:", block_4_data)
            # Read block 5
            block_5_data = pn532.mifare_classic_read_block(5)
            print("Block 5 data:", block_5_data)
        else:
            print("Authentication failed!")
    # Wait for two seconds
    time.sleep(2)
