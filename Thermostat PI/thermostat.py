import json
import Adafruit_DHT
import RPi.GPIO as GPIO
import time
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)
 
# Load the server addresses from the configuration file
with open('config.json') as config_file:
    config_data = json.load(config_file)

class Polling:
    def __init__(self, config_data, thermostat_controller, DHT_SENSOR, DHT_PIN):
        self.config_data = config_data
        self.thermostat_controller = thermostat_controller
        self.current_temperature = None
        self.DHT_SENSOR = DHT_SENSOR
        self.DHT_PIN = DHT_PIN
        self.device_id = config_data.get("device_id")



    def poll_sensor_data(self, max_retries=3, delay_between_retries=2):
        retries = 0
        while retries < max_retries:
            humidity, temperature = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, self.DHT_PIN)
            if humidity is not None and temperature is not None:
                self.current_temperature = round((temperature * 9/5) + 32, 1)
                current_humidity = round(humidity, 2)
                return {"temperature": self.current_temperature, "humidity": current_humidity}
            else:
                print("Error reading sensor data. Retrying...")
                retries += 1
                time.sleep(delay_between_retries)

        print("Max retries reached. Unable to read sensor data.")
        return {"temperature": None, "humidity": None}


    def get_user_setting(self):
        try:
            response = requests.get(self.config_data['vm-server'] + '/api/get_last_user_setting')
            if response.status_code == 200:
                data = response.json()
                user_setting = data.get('last_user_setting')
                if user_setting is not None:
                    return float(user_setting)
                else:
                    print('get_user_setting: User setting not found in response')
            else:
                print('get_user_setting: Failed to fetch user setting:', response.status_code)
            time.sleep(30)
        except requests.exceptions.RequestException as e:
            print(f'get_user_setting: Error fetching user setting: {str(e)}')
            time.sleep(10)        

class ThermostatController:
    def __init__(self, config_data, DHT_SENSOR, DHT_PIN, polling):
        self.RELAY_PINS = config_data["relay_pins"]
        GPIO.setup(self.RELAY_PINS, GPIO.OUT)
        self.current_state = 0  # Initial state is "Off"
        self.timer_thread = None  # Timer thread
        self.DHT_SENSOR = DHT_SENSOR
        self.DHT_PIN = DHT_PIN
        self.config_data = config_data
        self.emergency_stop_enabled = False
        self.stop_event = threading.Event()
        self.polling = polling
        self.off_between_states_counter = 0
        self.heat_mode_timer = 0
        self.off_mode_counter = 0
        self.off_mode_duration = 10  # Duration of the initial "Off" mode in seconds
        self.temperature_within_range_duration = 0
        self.time_threshold = 30  # 1 minute in seconds

        # Load configurable values from config_data
        self.cooling_set_temperature_offset = config_data.get("cooling_set_temperature_offset", 0.5)
        self.heating_set_temperature_offset = config_data.get("heating_set_temperature_offset", 0.5)
        self.temperature_difference_threshold = config_data.get("temperature_difference_threshold", 1.3)

    THERMOSTAT_STATES = {
        0: 'Off',
        2: 'Heat',
        3: 'Cool',
        4: 'Emergency Heat',
        5: 'Fan',
        6: 'Between States',
    }

    def enable_emergency_stop(self):
        self.emergency_stop_enabled = True

    def disable_emergency_stop(self):
        self.emergency_stop_enabled = False

    def get_relay_states(self):
        relay_states = {}
        for pin in self.RELAY_PINS:
            state = GPIO.input(pin)
            relay_states[f'Relay {self.RELAY_PINS.index(pin)}'] = 'On' if state == 1 else 'Off'
        return relay_states

    def update_thermostat_state(self):
        user_set_temperature = self.polling.get_user_setting()

        if self.off_mode_counter < self.off_mode_duration:
            # System is in the initial "Off" mode
            self.off_mode()
            self.off_mode_counter += 1
        else:
            if self.polling.current_temperature is not None:
                # Calculate temperature difference
                temperature_difference = abs(self.polling.current_temperature - user_set_temperature)

                if self.emergency_stop_enabled:
                    self.off_mode()
                elif temperature_difference > self.temperature_difference_threshold:
                    # If the temperature difference is greater than the threshold, adjust accordingly
                    if self.polling.current_temperature < user_set_temperature:
                        self.heat_mode(user_set_temperature)
                    elif self.polling.current_temperature > user_set_temperature:
                        self.cool_mode(user_set_temperature)
                else:
                    self.off_between_states_mode()
            else:
                # Handle the case when sensor reading fails
                print("Error reading sensor data. Retrying...")
                time.sleep(5)  # Adjust as needed

    def set_relay_states(self, fan, compressor, heat_strip, rev_val):
        GPIO.output(self.RELAY_PINS[0], GPIO.LOW if fan else GPIO.HIGH)
        GPIO.output(self.RELAY_PINS[1], GPIO.LOW if compressor else GPIO.HIGH)
        GPIO.output(self.RELAY_PINS[2], GPIO.LOW if heat_strip else GPIO.HIGH)
        GPIO.output(self.RELAY_PINS[3], GPIO.LOW if rev_val else GPIO.HIGH)

    def off_mode(self):
        self.current_state = 0
        self.set_relay_states(False, False, False, False)
        print("Off mode")

    def cool_mode(self, user_set_temperature):
        self.current_state = 3
        cooling_set_temperature = user_set_temperature - self.cooling_set_temperature_offset
        self.set_relay_states(True, True, False, False)
        self.heat_mode_timer = 0
        self.off_between_states_counter = 0
        print(f"Running Cool. Cooling set temperature: {cooling_set_temperature}°F")

        while self.current_state == 3:
            sensor_data = self.polling.poll_sensor_data()
            current_temperature = sensor_data.get("temperature")

            if current_temperature is not None:
                print(f"Current Temperature: {current_temperature}°F, Cooling set temperature: {user_set_temperature}°F")

                # Compare current temperature with cooling set temperature
                if current_temperature < user_set_temperature:
                    # Trigger off_between_states_mode
                    self.off_between_states_mode()
                    break  # Exit the loop when off_between_states_mode is triggered

            time.sleep(1)  # Poll every 1 second

    def heat_mode(self, user_set_temperature):
        self.current_state = 2
        current_temperature = None  # Initialize current_temperature

        if self.heat_mode_timer < 400:
            heating_set_temperature = user_set_temperature + self.heating_set_temperature_offset
            self.set_relay_states(True, True, False, True)
            self.off_between_states_counter = 0
            print(f"Current Temperature: {current_temperature}°F, Heating set temperature: {user_set_temperature}°F")

            self.heat_mode_timer += 1

        while self.current_state == 2:
            sensor_data = self.polling.poll_sensor_data()
            current_temperature = sensor_data.get("temperature")

            if current_temperature is not None:
                print(f"Current Temperature: {current_temperature}°F, Heating set temperature: {user_set_temperature}°F")

                # Compare rounded current temperature with heating set temperature
                if current_temperature >= heating_set_temperature:
                    # Trigger off_between_states_mode
                    self.off_between_states_mode()
                    break  # Exit the loop when off_between_states_mode is triggered

            time.sleep(1)  # Poll every 1 second

        else:
            self.current_state = 4
            heating_set_temperature = user_set_temperature
            self.set_relay_states(True, True, True, True)
            self.off_between_states_counter = 0
            print(f"Current Temperature: {current_temperature}°F, E-Heating set temperature: {user_set_temperature}°F")

            while self.current_state == 4:
                sensor_data = self.polling.poll_sensor_data()
                current_temperature = sensor_data.get("temperature")

                if current_temperature is not None:
                    print(f"Current Temperature: {current_temperature}°F, E-Heating set temperature: {user_set_temperature}°F")

                    # Compare rounded current temperature with heating set temperature
                    if current_temperature >= heating_set_temperature:
                        # Trigger off_between_states_mode
                        self.off_between_states_mode()
                        break  # Exit the loop when off_between_states_mode is triggered

                time.sleep(1)  # Poll every 1 second

    def off_between_states_mode(self):
        self.current_state = 6
        self.set_relay_states(False, False, False, False)
        print("Between States")
        self.heat_mode_timer = 0

        # Increment the counter
        self.off_between_states_counter += 1

        # Read configuration from config.json
        with open('config.json') as config_file:
            config = json.load(config_file)

        # Extract timer durations from the configuration
        timer_durations = config.get("timer_durations", {})
        timer_duration = (
            timer_durations.get("first_counter", 480) if self.off_between_states_counter == 1
            else timer_durations.get("second_counter", 240) if self.off_between_states_counter == 2
            else timer_durations.get("third_counter", 20)
        )

        print(f"Timer started for {timer_duration} seconds")

        # Use a timer to run the code for the specified duration
        timer = threading.Timer(timer_duration, self.stop_continuous_polling)
        timer.start()

        # Wait for the timer to complete before looping again
        timer.join()

    def stop_continuous_polling(self):
        # Set the stop_event to stop the continuous polling loop
        self.stop_event.set()
        print("Timer stopped after specified duration")

        # Call the update_thermostat_state method from the TemperatureController
        self.update_thermostat_state()

        print("Switched back to loop after the timer completed")

    def fan_mode(self):
        self.current_state = 5
        self.set_relay_states(True, False, False, False)
        self.off_between_states_counter = 0
        print("Running Fan")

    def update_config(self, updated_config):
        # Validate and update the config_data based on the incoming data
        for key, value in updated_config.items():
            if key in self.config_data:
                self.config_data[key] = value


# Set the pin numbering mode (use GPIO.BCM or GPIO.BOARD based on your pin numbering)
GPIO.setmode(GPIO.BCM)

# Assuming you have instances of Polling and ThermostatController
polling_instance = Polling(config_data, None, Adafruit_DHT.DHT22, config_data["dht_sensor_pin"])
thermostat_controller_instance = ThermostatController(config_data, None, None, polling_instance)

# Define a function to run the thermostat controller
def run_thermostat_controller():
    while True:
        thermostat_controller_instance.update_thermostat_state()
        time.sleep(1)  # Adjust the sleep duration as needed

# Create a thread for the thermostat controller
thermostat_thread = threading.Thread(target=run_thermostat_controller)
thermostat_thread.daemon = True
thermostat_thread.start()


# Define Flask routes
@app.route('/api/get_current_temperature', methods=['GET'])
def get_current_temperature():
    sensor_data = polling_instance.poll_sensor_data()
    current_temperature = sensor_data.get("temperature")

    if current_temperature is not None:
        rounded_temperature = round(current_temperature * 2) / 2.0
        return jsonify({'temperature': rounded_temperature})
    else:
        return jsonify({'error': 'Failed to retrieve current temperature'})

@app.route('/api/get_thermostat_state', methods=['GET'])
def fetch_thermostat_state():
    thermostat_state = thermostat_controller_instance.THERMOSTAT_STATES.get(thermostat_controller_instance.current_state, 'Unknown')
    return jsonify(state=thermostat_state)


@app.route('/api/emergency_stop', methods=['GET', 'POST'])
def control_emergency_stop():
    if request.method == 'GET':
        return jsonify({'emergency_stop_enabled': thermostat_controller_instance.emergency_stop_enabled})
    elif request.method == 'POST':
        if request.json.get('enable', False):
            thermostat_controller_instance.enable_emergency_stop()
        else:
            thermostat_controller_instance.disable_emergency_stop()
        return jsonify({'message': 'Emergency Stop ' + ('Enabled' if thermostat_controller_instance.emergency_stop_enabled else 'Disabled')})

@app.route('/api/get_config', methods=['GET'])
def get_config():
    return jsonify(config_data)

@app.route('/api/update_config', methods=['POST'])
def update_config():
    try:
        updated_data = request.json

        # Update the global config_data
        for key, value in updated_data.items():
            if key in config_data:
                config_data[key] = value

        # Update the ThermostatController instance
        thermostat_controller_instance.update_config(updated_data)

        # Save the updated config_data to config.json
        with open('config.json', 'w') as config_file:
            json.dump(config_data, config_file, indent=4)

        return jsonify(success=True, message='Configuration updated successfully')

    except Exception as e:
        return jsonify(success=False, message=f'Error updating configuration: {str(e)}')



# Run the Flask app
app.run(host='0.0.0.0', port=5001)