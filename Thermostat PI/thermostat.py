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

# Set up GPIO pins for the relay module
RELAY_PINS = config_data["relay_pins"]
GPIO.setmode(GPIO.BCM)
for pin in RELAY_PINS:
    GPIO.setup(pin, GPIO.OUT)

# Set up the DHT sensor
DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = config_data["dht_sensor_pin"]

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

# This is to prevent the relays from spamming all the channels with power to the HVAC system
# DO NOT MODIFY THIS AS IT CAN LEAD TO COMPRESSOR/SYSTEM FAILURE!!!!!
# Initialize GPIO pins
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PINS, GPIO.OUT)

# Add a short delay
time.sleep(5.0)  # Adjust the delay duration as needed

def read_temperature():
    humidity, temperature_celsius = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
    temperature_fahrenheit = (temperature_celsius * 9/5) + 32  # Convert to Fahrenheit
    return temperature_fahrenheit

# Define the URL for your API endpoint using the "vm-server" URL from config.json
api_url = f"{config_data['vm-server']}/api/receive_data"
    # Function to send data to the VM
def send_data_to_vm(data):
    try:
        response = requests.post(api_url, json=data)
        if response.status_code == 200:
            print("Data sent successfully.")
        else:
            print(f"Failed to send data, status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending data: {str(e)}")


    

def control_relay(relay, state):
    if state == 1:
        GPIO.output(RELAY_PINS[relay - 1], 0)  # Turn off the selected relay
    else:
        GPIO.output(RELAY_PINS[relay - 1], 1)  # Turn on the selected relay

# Define a timer for requesting the last user setting and current temperature every 2 minutes
def request_user_setting_and_temperature():
    while True:
        user_setting = get_user_setting()
        current_temperature_fahrenheit = read_temperature()

        if user_setting is not None:
            print(f"Last User Setting: {user_setting}°F")
            print(f"Current Temperature: {current_temperature_fahrenheit}°F")

        time.sleep(120)  # Sleep for 2 minutes

# Function to get the state of each relay
def get_relay_states():
    relay_states = {}
    for relay_number, pin in RELAY_NAMES.items():
        state = GPIO.input(pin)
        state_name = RELAY_STATES.get(relay_number, 'Unknown')
        relay_states[state_name] = 'On' if state else 'Off'
    return relay_states

# Define the main function for updating relay states
def update_relay_states():
    while True:
        current_temperature_fahrenheit = read_temperature()
        user_setting = get_user_setting()

        if user_setting is not None:
            print(f"Last User Setting: {user_setting}°F")
            print(f"Current Temperature: {current_temperature_fahrenheit}°F")

            if current_temperature_fahrenheit > user_setting:
                # Turn on cooling mode
                control_relay(3, 1)  # Turn on Cool relay
                control_relay(1, 1)  # Turn on Fan relay
                control_relay(2, 1)  # Turn off RevVal relay
                control_relay(4, 0)  # Turn off Heat relay
            elif current_temperature_fahrenheit < user_setting:
                # Turn on heating mode
                control_relay(4, 1)  # Turn on Heat relay
                control_relay(1, 1)  # Turn on Fan relay
                control_relay(2, 0)  # Turn off RevVal relay
                control_relay(3, 0)  # Turn off Cool relay
            else:
                # Turn off all relays
                GPIO.output(RELAY_PINS, GPIO.LOW)
        else:
            print("User setting not available, using default behavior")

        time.sleep(300)  # Sleep for 5 minutes (adjust as needed)

# Create threads to run the functions concurrently
import threading

request_user_setting_thread = threading.Thread(target=request_user_setting_and_temperature)
update_relay_states_thread = threading.Thread(target=update_relay_states)

# Dictionary to map relay numbers to state names
RELAY_STATES = {
    1: 'Fan',
    2: 'RevVal',
    3: 'Cool',
    4: 'Heat',
}

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
        sensor_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        response = send_data_to_vm(sensor_data)
        print(response)  # Print the response to the terminal for monitoring

        # Sleep for 2.5 minutes (adjust as needed)
        time.sleep(150)

if __name__ == '__main__':
    request_user_setting_thread.start()
    update_relay_states_thread.start()
    send_data_thread = Thread(target=send_data_periodically)
    send_data_thread.daemon = True  # Allow the thread to exit when the main program exits
    send_data_thread.start()
    app.run(host='0.0.0.0', port=5001)
