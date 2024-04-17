import Adafruit_DHT
import RPi.GPIO as GPIO
import requests
import json
from datetime import datetime
import pytz
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
import threading

app = Flask(__name__)
CORS(app)

# Load configuration from JSON file
with open('config.json') as config_file:
    config = json.load(config_file)

# Set up the DHT sensor
DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = config.get('DHT_PIN')

# Server endpoint
api_url = config['api_url']

# Device ID
device_id = config['device_id']

# Function to get current temperature and humidity
def get_sensor_data():
    humidity, temperature = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
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

# Function to send data to the server
def send_data_to_server(data):
    response = requests.post(api_url, json=data)
    return response.text

# Main loop to read sensor data and send it to the server every 2 minutes
def sensor_data_loop():
    while True:
        try:
            # Load the updated device ID from the config
            device_id = config['device_id']
            
            sensor_data = get_sensor_data()
            
            # Convert temperature to Fahrenheit and round to the nearest 0.5 degrees
            sensor_data["temperature"] = celsius_to_fahrenheit_rounded(sensor_data["temperature"])
            
            # Update the device ID in the sensor data
            sensor_data["device_id"] = device_id

            # Send data to the server
            send_data_to_server(sensor_data)

            # Wait for 2 minutes before the next iteration
            time.sleep(120)

            # Print sensor data
            print("Sensor Data:")
            print(f"Device ID: {sensor_data['device_id']}")
            print(f"Temperature: {sensor_data['temperature']} °F")
            print(f"Humidity: {sensor_data['humidity']}%")
            print("--------------------")

        except Exception as e:
            print(f"Error: {str(e)}")
            # Handle exceptions as needed


# Start the sensor data loop in a separate thread
sensor_thread = threading.Thread(target=sensor_data_loop)
sensor_thread.daemon = True  # Allow the program to exit even if this thread is still running
sensor_thread.start()

@app.route('/api/get_current_temperature', methods=['GET'])
def get_current_temperature():
    sensor_data = get_sensor_data()
    current_temperature_celsius = sensor_data["temperature"]

    if current_temperature_celsius is not None:
        # Convert to Fahrenheit and round
        temperature_fahrenheit = celsius_to_fahrenheit_rounded(current_temperature_celsius)
        
        return jsonify({'temperature': temperature_fahrenheit})
    else:
        return jsonify({'error': 'Failed to retrieve current temperature'})

@app.route('/api/deviceid', methods=['POST'])
def update_device_id():
    try:
        data = request.json
        new_device_id = data.get('device_id')
        if new_device_id:
            config['device_id'] = new_device_id
            # Update device ID in memory
            global device_id
            device_id = new_device_id
            with open('config.json', 'w') as config_file:
                json.dump(config, config_file, indent=4)
            return jsonify({'message': 'Device ID updated successfully', 'new_device_id': new_device_id})
        else:
            return jsonify({'error': 'No device_id provided in request'})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/isthermostatcontroller', methods=['GET'])
def get_thermostat_controller_flag():
    return jsonify({'isthermostatcontroller': config.get('isthermostatcontroller', False)})

@app.route('/api/isthermostatcontroller', methods=['POST'])
def set_thermostat_controller_flag():
    data = request.json
    new_flag = data.get('isthermostatcontroller')

    # Check if the provided data is valid
    if new_flag is None or type(new_flag) is not bool:
        return jsonify({'error': 'Invalid value provided for isthermostatcontroller. Use true or false.'}), 400

    # Update the config file
    config['isthermostatcontroller'] = new_flag
    with open('config.json', 'w') as config_file:
        json.dump(config, config_file, indent=4)

    return jsonify({'message': 'isthermostatcontroller flag updated successfully'}), 200

@app.route('/api/deviceid', methods=['GET'])
def get_device_id():
    return jsonify({'device_id': config['device_id']})

# Run the Flask app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001)
