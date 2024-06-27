#!/bin/bash

# Number of retries
MAX_RETRIES=4
# Wait time between retries in seconds
WAIT_TIME=5
# Activate the virtual environment
source /home/poseidon/refillstation/bin/activate
# Command to execute your Python program
COMMAND="/home/poseidon/refillstation/bin/python3 /home/poseidon/refillstation/refill_main.py"

# Retry loop
for (( i=1; i<=$MAX_RETRIES; i++ ))
do
    echo "Attempt $i..."
    $COMMAND
    # Check the exit status
    if [ $? -eq 0 ]; then
        echo "Program executed successfully."
        deactivate
        exit 0
    else
        echo "Attempt $i failed."
    fi
    # Wait before next retry
    if [ $i -lt $MAX_RETRIES ]; then
        echo "Waiting $WAIT_TIME seconds before next attempt..."
        sleep $WAIT_TIME
    fi
done

echo "Max retries reached. Exiting."
exit 1
