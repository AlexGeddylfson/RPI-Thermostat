import Adafruit_DHT
import RPi.GPIO as GPIO
import requests
from datetime import datetime
import pytz
import time
from flask import Flask, jsonify
from flask_cors import CORS
import threading

app = Flask(__name__)
CORS(app)

# Set up the DHT sensor
DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = 14

# Server endpoint
api_url = "http://SERVERIP:5000/api/receive_data"

# Device ID (change this to match your device's ID)
device_id = "DEVICE NAME"

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
            sensor_data = get_sensor_data()

            # Convert temperature to Fahrenheit and round to the nearest 0.5 degrees
            sensor_data["temperature"] = celsius_to_fahrenheit_rounded(sensor_data["temperature"])

            # Get current UTC time
            utc_time = datetime.now(pytz.utc)

            # Replace 'your_timezone' with your actual timezone
            local_timezone = pytz.timezone('America/New_York')
            local_time = utc_time.astimezone(local_timezone)

            # Manually adjust the time offset
            local_time = local_time.replace(tzinfo=None) - local_timezone.utcoffset(local_time.replace(tzinfo=None))

            # Convert the timestamp to a string
            sensor_data["timestamp"] = local_time.strftime("%Y-%m-%d %H:%M")

            # Send data to the server
            send_data_to_server(sensor_data)

            # Wait for 2 minutes before the next iteration
            time.sleep(120)

            # Print sensor data
            print("Sensor Data:")
            print(f"Device ID: {sensor_data['device_id']}")
            print(f"Temperature: {sensor_data['temperature']} °F")
            print(f"Humidity: {sensor_data['humidity']}%")
            print(f"Timestamp: {sensor_data['timestamp']}")
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


# Run the Flask app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001)
