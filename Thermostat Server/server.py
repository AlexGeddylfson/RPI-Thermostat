from flask import Flask, render_template, request, jsonify
import mysql.connector
import pytz
from datetime import datetime
from flask_cors import CORS
import json
from flask_caching import Cache
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# Load the database configuration from the configuration file
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# MySQL database connection
db = mysql.connector.connect(
    host=config["database_config"]["host"],
    user=config["database_config"]["user"],
    password=config["database_config"]["password"],
    database=config["database_config"]["database_name"]
)

# Function to convert UTC timestamp to EST
def convert_utc_to_est(utc_timestamp):
    utc = pytz.utc.localize(utc_timestamp)
    est = utc.astimezone(pytz.timezone('America/New_York'))
    return est

# Function to format timestamp in a user-friendly way
def format_timestamp(timestamp):
    return timestamp.strftime("%Y-%m-%d %I:%M")

# Flask-Caching setup
cache = Cache(app, config={'CACHE_TYPE': 'simple', 'CACHE_DEFAULT_TIMEOUT': 30})

@app.route('/')
def index():
    cursor = db.cursor(dictionary=True)
    select_query = "SELECT device_id, temperature, humidity, timestamp, ip_address FROM sensor_data"
    cursor.execute(select_query)
    data = cursor.fetchall()
    cursor.close()
    return render_template('index.html', data=data)

@app.route('/modes')
def mode_updates():
    try:
        cursor = db.cursor(dictionary=True)
        select_query = "SELECT * FROM mode_updates ORDER BY timestamp DESC LIMIT 20"
        cursor.execute(select_query)
        mode_updates = cursor.fetchall()
        return render_template('modes.html', mode_updates=mode_updates)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()

@app.route('/api/modes')
def mode_updates_api():
    try:
        cursor = db.cursor(dictionary=True)
        select_query = "SELECT * FROM mode_updates ORDER BY timestamp DESC LIMIT 20"
        cursor.execute(select_query)
        mode_updates = cursor.fetchall()
        return jsonify(mode_updates)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
    
@app.route('/api/sensor_data')
def sensor_data_api():
    try:
        cursor = db.cursor(dictionary=True)
        select_query = "SELECT device_id, temperature, timestamp FROM sensor_data ORDER BY timestamp DESC LIMIT 200"
        cursor.execute(select_query)
        sensor_data = cursor.fetchall()

        return jsonify(sensor_data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()

@app.route('/userinfo')
def userinfo():
    cursor = db.cursor(dictionary=True)
    select_query = "SELECT id, device_id, target_temperature, timestamp FROM user_settings"
    cursor.execute(select_query)
    user_data = cursor.fetchall()
    cursor.close()
    return render_template('userinfo.html', user_data=user_data)

@app.route('/api/receive_data', methods=['POST'])
def receive_data():
    data = request.json
    print("Received data:", data)  # Add this line for debugging
    if not data:
        return jsonify({'message': 'Invalid data format'}), 400

    # Get the IP address from the incoming request
    ip_address = request.remote_addr

    cursor = db.cursor()

    # Generate server timestamp with seconds only
    server_timestamp = datetime.utcnow().replace(microsecond=0)

    insert_query = "INSERT INTO sensor_data (device_id, temperature, humidity, timestamp, ip_address) VALUES (%s, %s, %s, %s, %s)"
    cursor.execute(insert_query, (data.get('device_id'), data.get('temperature'), data.get('humidity'), server_timestamp, ip_address))
    db.commit()
    cursor.close()

    return jsonify(data)

@app.route('/app')
def app_dashboard():
    try:
        cursor = db.cursor(dictionary=True)
        select_query = (
            "SELECT device_id, MAX(ip_address) AS ip_address "
            "FROM sensor_data "
            "WHERE timestamp >= NOW() - INTERVAL 24 HOUR "
            "GROUP BY device_id "
            "HAVING ip_address IS NOT NULL AND ip_address != ''"
        )
        cursor.execute(select_query)
        devices_data = cursor.fetchall()
        cursor.close()

        # Extract device names and IP addresses
        devices_json = [{'device_id': device['device_id'], 'ip_address': device['ip_address']} for device in devices_data]

        # Return JSON response
        return jsonify(devices_json)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/update_mode', methods=['POST'])
def update_mode():
    try:
        data = request.json
        print("Received mode update:", data)  # Add this line for debugging
        if not data or 'mode' not in data:
            return jsonify({'message': 'Invalid data format or missing mode'}), 400

        device_id = data.get('device_id', request.remote_addr)  # Get the user's IP address if device_id is not provided
        mode = data.get('mode')

        cursor = db.cursor()
        insert_query = "INSERT INTO mode_updates (device_id, mode, timestamp) VALUES (%s, %s, NOW())"
        cursor.execute(insert_query, (device_id, mode))
        db.commit()
        cursor.close()

        return jsonify({'message': 'Mode update inserted successfully.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/update_temperature', methods=['POST'])
def update_temperature():
    try:
        new_temperature = float(request.json.get('temperature'))
        device_id = request.remote_addr  # Get the user's IP address

        # Insert the new temperature setpoint along with the client's IP into your 'user_settings' table
        cursor = db.cursor()
        insert_query = "INSERT INTO user_settings (device_id, target_temperature, timestamp) VALUES (%s, %s, NOW())"
        cursor.execute(insert_query, (device_id, new_temperature))
        db.commit()
        cursor.close()

        return jsonify({'message': 'Temperature setpoint inserted successfully.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/get_last_user_setting', methods=['GET'])
@cache.cached(timeout=30)  # Cache for 30 seconds
def get_last_user_setting():
    try:
        cursor = db.cursor()
        select_query = "SELECT target_temperature FROM user_settings ORDER BY timestamp DESC LIMIT 1"
        cursor.execute(select_query)
        data = cursor.fetchone()
        cursor.close()

        if data:
            return jsonify({'last_user_setting': data[0]})
        else:
            return jsonify({'message': 'No user setting found in the database.'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
