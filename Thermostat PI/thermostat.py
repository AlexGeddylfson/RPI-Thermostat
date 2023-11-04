#!/usr/bin/env python3

import requests
import json
import Adafruit_DHT
from datetime import datetime
import pytz
import time
import RPi.GPIO as GPIO
from flask import Flask, request, jsonify
from flask_cors import CORS
from threading import Thread

app = Flask(__name__)
CORS(app)

# Load the server addresses from the configuration file
with open('config.json') as config_file:
    config_data = json.load(config_file)

    # Define the URL for your API endpoint using the "vm-server" URL from config.json
api_url = f"{config_data['vm-server']}/api/receive_data"

# Set up GPIO pins for the relay module
RELAY_PINS = config_data["relay_pins"]
GPIO.setmode(GPIO.BCM)

# Initialize all relays to the OFF state
# This is to prevent the relays from spamming all the channels with power to the HVAC system
# DO NOT MODIFY THIS AS IT CAN LEAD TO COMPRESSOR/SYSTEM FAILURE!!!!! 
for pin in RELAY_PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH)

# Set up the DHT sensor
DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = config_data["dht_sensor_pin"]

def read_temperature():
    humidity, temperature_celsius = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
    temperature_fahrenheit = (temperature_celsius * 9/5) + 32  # Convert to Fahrenheit
    return temperature_fahrenheit

# Function to get the user setting from your server
def get_user_setting():
    while True:
        try:
            response = requests.get(config_data['vm-server'] + '/api/get_last_user_setting')
            if response.status_code == 200:
                data = response.json()
                user_setting = data.get('last_user_setting')
                if user_setting is not None:
                    user_setting = float(user_setting)
                return user_setting
            else:
                print('Failed to fetch user setting:', response.status_code)
                time.sleep(30)  # Wait for half a minute before retrying
        except requests.exceptions.RequestException as e:
            print(f'Error fetching user setting: {str(e)}')
            time.sleep(60)  # Wait for 1 minute before retrying

# Define thermostat states
THERMOSTAT_STATES = {
    0: "Off",
    1: "Fan Only",
    2: "Heat",
    3: "Cool",
}

current_thermostat_state = 0  # Initialize to "Off"

def request_user_setting_and_temperature():
    global current_thermostat_state  # Declare current_thermostat_state as global
    while True:
        user_setting = get_user_setting()
        current_temperature_fahrenheit = read_temperature()
        temperature_achieved_time = None  # Initialize temperature_achieved_time here

        if user_setting is not None:
            print(f"Last User Setting: {user_setting}°F")
            print(f"Current Temperature: {current_temperature_fahrenheit}°F")

        # Check if the user-set temperature is achieved
        if current_thermostat_state != 0:  # Not in "Off" state
            if current_temperature_fahrenheit > user_setting:
                if temperature_achieved_time is None:
                    temperature_achieved_time = time.time()
                    print("Temperature achieved. Relay control allowed.")
                elif time.time() - temperature_achieved_time >= 60:  # 1 minute in seconds
                    current_thermostat_state = 0  # Set to "Off"
                    temperature_achieved_time = None
                    print("Temperature achieved for 1 minute. Turning off.")
            else:
                temperature_achieved_time = None

        time.sleep(30)  # Sleep for 2 minutes

# Define a variable for the delay in seconds before transitioning to another state
DELAY_BEFORE_TRANSITION = 20  # You can adjust the delay as needed

# Function to update the thermostat state with a delay
def update_thermostat_state_with_delay(temperature, user_setting):
    global current_thermostat_state, state_change_time

    # Get the current time
    current_time = time.time()

    # Calculate the time elapsed since the last state change
    time_elapsed = current_time - state_change_time

    # Check if it's time to transition to a new state
    if time_elapsed >= DELAY_BEFORE_TRANSITION:
        if user_setting is not None:
            if temperature > user_setting:
                current_thermostat_state = 3  # Cool mode
            elif temperature < user_setting:
                current_thermostat_state = 2  # Heat mode
            else:
                current_thermostat_state = 1  # Fan only
        else:
            if all(GPIO.input(pin) == GPIO.HIGH for pin in RELAY_PINS):
                current_thermostat_state = 0  # Off
            else:
                current_thermostat_state = 1  # Fan only
    else:
        current_thermostat_state = 0  # Stay in "Off" during the delay

# Initialize the state change time
state_change_time = time.time()

# In your main loop where you update relay states
def update_relay_states_with_delay():
    last_relay_off_time = None  # Initialize the variable to None

    while True:
        current_temperature_fahrenheit = read_temperature()
        user_setting = get_user_setting()

        if user_setting is not None:
            update_thermostat_state_with_delay(current_temperature_fahrenheit, user_setting)
            print(f"Last User Setting: {user_setting}°F")
        else:
            # Use the default temperature setting when the user setting is not available
            user_setting = DEFAULT_TEMPERATURE_SETTING
            print(f"User setting not available, using default setting: {user_setting}°F")

        print(f"Current Temperature: {current_temperature_fahrenheit}°F")
        print(f"Thermostat State: {THERMOSTAT_STATES[current_thermostat_state]}")

        # Control relays based on current_thermostat_state
        control_relays_based_on_state(current_thermostat_state)

        # Check if enough time has passed before switching to another state
        if last_relay_off_time is not None and time.time() - last_relay_off_time < 20:
            continue  # Stay in the current state

        # Update the state change time after a state change
        state_change_time = time.time()

        # Calculate the time elapsed since the last state change
        time_elapsed = state_change_time - state_change_time  # Initialize as 0

        while time_elapsed < DELAY_BEFORE_TRANSITION:
            # Get the current time
            current_time = time.time()

            # Recalculate the time elapsed
            time_elapsed = current_time - state_change_time

            # Sleep for a short interval
            time.sleep(1)

        # Add a delay to the state changes
        time.sleep(10)  # Adjust this delay as needed

        # Record the time when the relays were last turned off
        last_relay_off_time = time.time()

        if current_thermostat_state in [COOLING_MODE, HEATING_MODE]:
            # Delay 20 seconds with "Off" relay before switching to the cooling or heating relay
            GPIO.output(RELAY_PINS[0], GPIO.HIGH)  # Turn off "Off" relay
            time.sleep(20)
            GPIO.output(RELAY_PINS[0], GPIO.LOW)  # Turn on "Off" relay



# Define global variables
relay_control_allowed = True
temperature_achieved_time = None
fan_override_time = None
relay_change_time = None

# Define the cooling and heating modes
COOLING_MODE = 3  # Cool
HEATING_MODE = 2  # Heat
FAN_MODE = 1 # Fan
OFF_MODE = 0 # OFF


last_relay_off_time = None  # Initialize the variable to None

def control_relays_based_on_state(state):
    global current_thermostat_state, relay_control_allowed, temperature_achieved_time, last_relay_off_time

    # Read current temperature and user setting
    current_temperature = read_temperature()
    user_setting = get_user_setting()

    # Calculate the temperature difference
    temperature_difference = abs(current_temperature - user_setting)

    # Check if enough time has passed before switching to another state
    if last_relay_off_time is not None and time.time() - last_relay_off_time < 20:
        return  # Stay in the current state

    # Reset the last_relay_off_time if we are turning on the relays
    last_relay_off_time = None

    # Check if the temperature is within the acceptable range to turn off heating and cooling modes
    temperature_within_range = temperature_difference <= 0.5

    # Turn off all relays initially
    GPIO.output(RELAY_PINS, GPIO.HIGH)

    if state == 0:  # Off
        if relay_control_allowed:
            GPIO.output(RELAY_PINS[0], GPIO.HIGH)  
            GPIO.output(RELAY_PINS[0], GPIO.HIGH)  
            GPIO.output(RELAY_PINS[0], GPIO.HIGH)  
            GPIO.output(RELAY_PINS[0], GPIO.HIGH)  

    elif state == 1:  # Fan Only
        if relay_control_allowed:
            GPIO.output(RELAY_PINS[0], GPIO.LOW)  # Turn on Fan relay
            GPIO.output(RELAY_PINS[1], GPIO.HIGH)  # Turn off Cool relay
            GPIO.output(RELAY_PINS[2], GPIO.HIGH)  # Turn off Heat relay
            GPIO.output(RELAY_PINS[3], GPIO.HIGH)  # Turn off RevVal relay

    elif state == HEATING_MODE:  # Heat
        if relay_control_allowed and not temperature_within_range:
            GPIO.output(RELAY_PINS[0], GPIO.LOW)  # Turn on Fan relay
            GPIO.output(RELAY_PINS[1], GPIO.HIGH)  # Turn off Cool relay
            GPIO.output(RELAY_PINS[2], GPIO.LOW)  # Turn on Heat relay
            GPIO.output(RELAY_PINS[3], GPIO.HIGH)  # Turn off RevVal relay
        elif temperature_within_range:
            last_relay_off_time = time.time()

    elif state == COOLING_MODE:  # Cool
        if relay_control_allowed and not temperature_within_range:
            GPIO.output(RELAY_PINS[0], GPIO.LOW)  # Turn on Fan relay
            GPIO.output(RELAY_PINS[1], GPIO.LOW)  # Turn on Cool relay
            GPIO.output(RELAY_PINS[2], GPIO.HIGH)  # Turn off Heat relay
            GPIO.output(RELAY_PINS[3], GPIO.LOW)  # Turn on RevVal relay
        elif temperature_within_range:
            last_relay_off_time = time.time()

    # For other relay(s) not mentioned in these conditions, they are turned off in all modes
    # [...]

    # Record the time when the relays were last turned off
    if all(GPIO.input(pin) == GPIO.HIGH for pin in RELAY_PINS):
        last_relay_off_time = time.time()




# Update the relay states based on the initial thermostat state
control_relays_based_on_state(current_thermostat_state)

# Now you can add an API endpoint to get the current thermostat state
@app.route('/api/get_thermostat_state', methods=['GET'])
def get_thermostat_state():
    if all(GPIO.input(pin) == GPIO.HIGH for pin in RELAY_PINS):
        return jsonify({'state': "Off"})
    else:
        return jsonify({'state': THERMOSTAT_STATES[current_thermostat_state]})


# Create threads to run the functions concurrently
import threading

request_user_setting_thread = threading.Thread(target=request_user_setting_and_temperature)
update_relay_states_thread = threading.Thread(target=update_relay_states_with_delay)

@app.route('/api/get_relay_states', methods=['GET'])
def get_relay_states():
    relay_states = {}
    for relay_name, pin in RELAY_NAMES.items():
        state = GPIO.input(pin)
        relay_states[relay_name] = 'On' if state == 1 else 'Off'
    return jsonify(relay_states)

# Function to get current temperature and humidity
def get_sensor_data():
    humidity, temperature = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, DHT_PIN)
    device_id = config_data["device_id"]  # Get the device_id from the config
    return {
        "device_id": device_id,
        "temperature": temperature,
        "humidity": humidity
    }

# Function to convert temperature from Celsius to Fahrenheit and round to the nearest 0.5 degrees
def celsius_to_fahrenheit_rounded(temperature_celsius):
    temperature_fahrenheit = (temperature_celsius * 9/5) + 32
    rounded_temperature = round(temperature_fahrenheit * 2) / 2
    return rounded_temperature

# Function to send data to the VM
def send_data_to_vm(data):
    response = requests.post(api_url, json=data)
    return response.text

@app.route('/api/get_current_temperature', methods=['GET'])
def get_current_temperature():
    # Read the current temperature from your sensor and convert it to Fahrenheit with 0.5 rounding
    sensor_data = get_sensor_data()
    temperature = sensor_data["temperature"]
    temperature_fahrenheit = round((temperature * 9/5) + 32, 1)
    return jsonify({'temperature': temperature_fahrenheit})

@app.route('/api/current_data', methods=['GET'])
def get_current_sensor_data():
    # Get the current sensor data, convert temperature and round humidity
    sensor_data = get_sensor_data()
    sensor_data["temperature"] = celsius_to_fahrenheit_rounded(sensor_data["temperature"])
    sensor_data["humidity"] = round(sensor_data["humidity"])
    return jsonify(sensor_data)

def send_data_periodically():
    while True:
        sensor_data = get_sensor_data()
        sensor_data["temperature"] = celsius_to_fahrenheit_rounded(sensor_data["temperature"])
        sensor_data["humidity"] = round(sensor_data["humidity"])
        sensor_data["device_id"] = "Downstairs"  # Set your device_id
        sensor_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:M")
        
        response = send_data_to_vm(sensor_data)
        print(response)  # Print the response to the terminal for monitoring
        
        # Sleep for 2.5 minutes (adjust as needed)
        time.sleep(150)



if __name__ == '__main__':
    request_user_setting_thread.start()
    update_relay_states_thread = threading.Thread(target=update_relay_states_with_delay)  # Use the modified function
    update_relay_states_thread.start()
    send_data_thread = Thread(target=send_data_periodically)
    send_data_thread.daemon = True  # Allow the thread to exit when the main program exits
    send_data_thread.start()
    app.run(host='0.0.0.0', port=5001)
