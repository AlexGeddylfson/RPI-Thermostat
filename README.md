

# Thermostat Control System

This project is a thermostat control system that allows you to monitor and control temperature settings through a web interface or native app. It consists of two main components: a Flask-based web application for control and data display and a Raspberry Pi-based temperature sensor system for data collection. You can find more information on the app [here](https://github.com/AlexGeddylfson/Thermostat-App).

## Physical Dependencies

1. A VM or physical machine running some sort of Apache/Nginx web server, and python.
2. A Raspberry Pi with a DHT22 temperature and humidity sensor, a 30V 4 channel relay, and mine has a 7 inch touch screen. (you can do without)
3. Basic knowledge of your specific HVAC system and the willingness to modify this code to work with anything other than a 6 wire system that has an orange wire for the energized reversal valve for COOLING. **(NOTE)** You can probably just wire up the pins that will respond as you would need them to for your specific system. 
**EG:** With a 6 wire system, the same pin for heat may be used to energize the heat for a 4 wire furnace while ignoring the heat strips pinout.  

## Getting Started 
### Assuming this is running in Ubuntu/Debian

On your VM/Physical machine you will want to install apache/nginx, mysql, and python as well as prepare the database and the wsgi mod which allows your python and apache to work in harmony. 
1. ```sudo apt update```
2. ```sudo apt install apache2 ibapache2-mod-wsgi python3 libexpat1 python3-pip```
3. ```sudo a2enconf mod-wsgi | sudo a2enmod cgi``` to allow the wsgi mod to run in apache
4. ```sudo systemctl restart apache2``` to restart apache and complete that side of the configuration. 
5. You will copy the contents of the Thermostat Server and modify the config.json to match your environment. Then either run the server.py or add it as a service by running these commands. In lieu of the legacy HTML included in this, you can use the build of the web app that is included in the Thermostat-App [here](https://github.com/AlexGeddylfson/Thermostat-App/releases). This will unify the app and web app making it one smooth experience.
6. ```sudo nano /etc/systemd/system/thermostatserver.service``` | adding this into the service file. 
```
[Unit]
Description=Thermostat Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 "/LOCATION/OF/YOUR/.PY/HERE
WorkingDirectory=/YOUR/WORKING/DIRECTORY/HERE
Restart=always
User=YOURUSERHERE

[Install]
WantedBy=multi-user.target
```
6.  You will want to pip install these packages | ```pip install Flask, render_template, request, jsonify, mysql.connector, pytz, datetime, flask_cors, json```
7.  Add the index.html file in the root of the folder to your /var/www/html directory. This is the UI. 
8.  Setup your SQL and get it ready to prepare a database. 
9.  Run ```CREATE DATABASE thermostat_data; | 
USE thermostat_data;```

-- Table to store temperature and humidity data
```
CREATE TABLE sensor_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(255),
    temperature DECIMAL(5, 2),
    humidity DECIMAL(5, 2),
    timestamp TIMESTAMP,
    ip_address VARCHAR(15)
);
```
-- Table to store user-set temperature values
```
CREATE TABLE user_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(255),
    target_temperature DECIMAL(5, 2),
    timestamp TIMESTAMP
);
```
-- Table to store outside temperature
```
CREATE TABLE outside_temperature (
    id INT AUTO_INCREMENT PRIMARY KEY,
    temperature DECIMAL(5, 2),
    timestamp TIMESTAMP
);
```
10. ``` sudo systemctl daemon-reload | sudo systemctl start thermostatserver.service ```
This should conclude the setup for the server side of this. This will allow you to store the temp/humididy/deviceid as well as the user settings when the user selects a temp to change the thermostat to. This will log the IP address the request came from as well as time stamps all around for every interaction. 


## Raspberry Pi Setup
### Assuming the same setup as I have with a Raspberry Pi 4 running raspbian, with a DHT22, and a 30V 4 channel relay.  

1. ```sudo apt update```
2. ```sudo apt install python3 libexpat1 python3-pip```
3. ```pip install Flask, render_template, request, jsonify, mysql.connector, pytz, datetime, flask_cors, json```
4. Copy the contents of Thermostat Pi into a working directory you wanna run it from and modify the config.json to match your environment. 
5. You will copy the contents of the Thermostat Pi and then either run the thermostat.py or add it as a service by running these commands. ``` sudo nano /etc/systemd/system/thermostat.service``` | adding this into the service file. 
```
[Unit]
Description=Thermostat Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 "/LOCATION/OF/YOUR/.PY/HERE
WorkingDirectory=/YOUR/WORKING/DIRECTORY/HERE
Restart=always
User=YOURUSERHERE

[Install]
WantedBy=multi-user.target
```

6. ``` sudo systemctl daemon-reload | sudo systemctl start thermostat.service | sudo systemctl start thermostat.service```
This should start the thermostat which will read the dht22 and report info to the webUI and the database on timers set within the python. 

## Show and tell!
Here are some of the screenshots I have from the app showing various states and settings. 

This is one of the thermostat in the between_states mode. After having run a previous mode. Polling to see if it needs another state change. 
![image](https://github.com/AlexGeddylfson/RPI-Thermostat/assets/8376599/609ca249-3731-47d1-a962-5ef1438af91d)

This is the Previous States screen. This shows the previous 20 states. 
![image](https://github.com/AlexGeddylfson/RPI-Thermostat/assets/8376599/b8a2972f-df75-484d-acbc-07e979a366ce)

And here is the Historical Temperatures. This will show the prevoius 200 reported temperatures. 
![image](https://github.com/AlexGeddylfson/RPI-Thermostat/assets/8376599/06d76689-ca42-41b8-902b-775f07e7a728)



