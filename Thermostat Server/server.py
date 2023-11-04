from flask import Flask, render_template, request, jsonify
import mysql.connector
import pytz
from datetime import datetime
from flask_cors import CORS
import json


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

@app.route('/')
def index():
    cursor = db.cursor(dictionary=True)
    select_query = "SELECT device_id, temperature, humidity, timestamp FROM sensor_data"
    cursor.execute(select_query)
    data = cursor.fetchall()
    cursor.close()
    return render_template('index.html', data=data)

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
    if not data:
        return jsonify({'message': 'Invalid data format'}), 400

    cursor = db.cursor()
    insert_query = "INSERT INTO sensor_data (device_id, temperature, humidity, timestamp) VALUES (%s, %s, %s, NOW())"
    cursor.execute(insert_query, (data.get('device_id'), data.get('temperature'), data.get('humidity')))
    db.commit()
    cursor.close()
    return jsonify(data)



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
