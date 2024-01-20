import os
from time import sleep
import wifi
import socketpool
import mdns
import board
import analogio
import digitalio
import microcontroller
import busio
import adafruit_lps2x
from simpleio import map_range

from adafruit_httpserver import (
    Server, Request, Response,
    REQUEST_HANDLED_RESPONSE_SENT,
)

device_name = os.getenv('DEVICE_NAME')
wifi_ssid = os.getenv('WIFI_SSID')
wifi_password = os.getenv('WIFI_PASSWORD')


led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

def led_on():
    led.value = True

def led_off():
    led.value = False

def led_blink():
    led.value = True
    sleep(0.2)
    led.value = False
    sleep(0.2)
    led.value = True
    sleep(0.2)
    led.value = False


# boot
led_on()
print(f'[boot] device name: {device_name}')
print(f'[boot] connecting to wifi: {wifi_ssid}')
wifi.radio.hostname = device_name
wifi.radio.connect(wifi_ssid, wifi_password)
ip_address = str(wifi.radio.ipv4_address)
print(f'[boot] ip address: {ip_address}')
print(f'[boot] starting mdns server')
mdns_server = mdns.Server(wifi.radio)
mdns_server.hostname = device_name
mdns_server.advertise_service(service_type="_http", protocol="_tcp", port=80)
print(f'[boot] starting web server')
pool = socketpool.SocketPool(wifi.radio)
server = Server(pool, "/static", debug = False)
server.start(ip_address)
print(f'[boot] web server at: http://{device_name}.local/')
led_off()


# initialize sensors
adc = analogio.AnalogIn(board.A2)
i2c = board.STEMMA_I2C()
lps = adafruit_lps2x.LPS22(i2c)

# web server: index
INDEX_TEMPLATE = """<!DOCTYPE html>
<html>
  <head>
    <title>{device_name}</title>
  </head>
  <body>
    <h1>{device_name}</h1>
    <p>
      <a href="http://{device_name}.local/">
        http://{device_name}.local/
      </a>
    </p>
    <dl>
        <dt>cpu temperature</dt>
        <dd>{cpu_temp} C</dd>
        <dt>ssid</dt>
        <dd>{wifi_ssid}</dd>
        <dt>signal strength</dt>
        <dd>-{wifi_rssi} dBm</dd>
        <dt>ip address</dt>
        <dd>{ip_address}</dd>
        <dt>metrics</dt>
        <dd><a href='/metrics'>/metrics</a></dd>
    </dl>
  </body>
</html>
"""

@server.route("/")
def base(request: Request):
    return Response(request, INDEX_TEMPLATE.format(
        device_name = device_name,
        cpu_temp = microcontroller.cpu.temperature,
        ip_address = ip_address,
        wifi_ssid = wifi_ssid,
        wifi_rssi = wifi.radio.tx_power, 
    ), content_type="text/html")



# web server: metrics
METRICS_TEMPLATE = """# {device_name} metrics
#
# TYPE wifi_signal_strenght gauge
# HINT wifi_signal_strength Wifi signal strength in dBm.
wifi_signal_strength{{device_type="pico-w",device_name="{device_name}",sensor_name="pico-w"}} -{wifi_rssi}
#
# TYPE cpu_temperature gauge
# HINT cpu_temperature CPU temperature in degree Celsius.
cpu_temperature{{device_type="pico-w",device_name="{device_name}",sensor_name="pico-w"}} {cpu_temp}
#
# TYPE wind_speed_m_s gauge
# HINT wind_speed_m_s Wind speed in meters per second.
wind_speed_m_s{{device_type="pico-w",device_name="{device_name}",sensor_name="anemometer"}} {wind_speed_m_s}
#
# TYPE wind_speed_ft_s gauge
# HINT wind_speed_ft_s Wind speed in feet per second.
wind_speed_ft_s{{device_type="pico-w",device_name="{device_name}",sensor_name="anemometer"}} {wind_speed_ft_s}
#
# TYPE wind_speed_mp_h gauge
# HINT wind_speed_mp_h Wind speed in miles per hour.
wind_speed_mp_h{{device_type="pico-w",device_name="{device_name}",sensor_name="anemometer"}} {wind_speed_mp_h}
#
# TYPE pressure_hpa gauge
# HINT pressure_hpa Barometric pressure in hPa.
pressure_hpa{{device_type="pico-w",device_name="{device_name}",sensor_name="lps22"}} {lps22_pressure_hpa}
#
# TYPE ambient_temperature_c gauge
# HINT ambient_temperature_c Ambient temperature in degree Celsius.
ambient_temperature_c{{device_type="pico-w",device_name="{device_name}",sensor_name="lps22"}} {lps22_temperature_c}
#
# TYPE ambient_temperature_f gauge
# HINT ambient_temperature_f Ambient temperature in degree Fahrenheit.
ambient_temperature_f{{device_type="pico-w",device_name="{device_name}",sensor_name="lps22"}} {lps22_temperature_f}
"""

@server.route("/metrics")
def base(request: Request):
    voltage = adc.value / 65535 * 3.3
    ms = map_range(voltage, 0.418, 2, 0, 32.4)
    return Response(request, METRICS_TEMPLATE.format(
        device_name         = device_name,
        cpu_temp            = microcontroller.cpu.temperature,
        wifi_rssi           = wifi.radio.tx_power,
        wind_speed_m_s      = ms,
        wind_speed_ft_s     = ms * 3.28084,
        wind_speed_mp_h     = ms * 2.23694,
        lps22_pressure_hpa  = lps.pressure,
        lps22_temperature_c = lps.temperature,
        lps22_temperature_f = (1.8 * lps.temperature) + 32.0,
    ), content_type="text/plain; version=0.0.4")


# main loop
while True:
    try:
        poll_result = server.poll()
        if poll_result == REQUEST_HANDLED_RESPONSE_SENT:
            led_blink()
            pass
    except OSError as error:
        print('error:', error)
        continue
