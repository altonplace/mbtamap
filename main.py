import requests
import json
import time
import math
import logging

# Change name to match and add your API_KEY
from Globals import *

log_level = logging.INFO

# create logger
logger = logging.getLogger('MBTALocator')
logger.setLevel(log_level)

# create file handler which logs even debug messages
fh = logging.FileHandler('app.log')
fh.setLevel(log_level)

# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(log_level)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

# Try to import the Raspi modules and default to the mock version if not found
# This allows the app to run locally
mock_lights = False
try:
    import board
    import neopixel
except NotImplementedError:
    logger.info('Mocking Lights.')
    mock_lights = True
    pass


class ApiRequest(object):
    def __init__(self):
        self.api_url = 'https://api-v3.mbta.com/'
        self.headers = {"X-API-Key": API_KEY}

    def call_api(self, url):
        try:
            r = requests.get(url, headers=self.headers)
            json_response = json.loads(r.text)
            logger.info('API response: {}'.format(json_response))
            return json_response
        except Exception as e:
            logger.error(e)

    def build_api_url(self, endpoint, api_filter=None):
        if api_filter:
            url = self.api_url + endpoint + '?' + api_filter
        else:
            url = self.api_url + endpoint
        return url


class Train(ApiRequest):
    def __init__(self, api_filter=None):
        super().__init__()
        self.api_method = 'vehicles'
        self.api_filter = api_filter
        self.trains = []

    def get_vehicles(self):

        url = self.build_api_url(self.api_method, self.api_filter)
        vehicles = self.call_api(url)

        for obj in vehicles['data']:
            vehicle = obj['attributes']

            # Convert Direction to text
            if vehicle['direction_id'] == 1:
                direction = 'North'
            elif vehicle['direction_id'] == 0:
                direction = 'South'
            else:
                direction = None

            train_dict = dict(stop_sequence=vehicle['current_stop_sequence'],
                              bearing=vehicle['bearing'],
                              latitude=vehicle['latitude'],
                              longitude=vehicle['longitude'],
                              number=vehicle['label'],
                              status=vehicle['current_status'],
                              direction=direction
                              )
            self.trains.append(train_dict)

        return self.trains

    def map_to_stop_number(self, s_list):
        """
        Map a the vehicles to the closest stop
        :param s_list: List of dicts containing name, latitude, longitude, and number
        :return: Train list with stop index added
        """
        if not self.trains:
            self.get_vehicles()

        for vehicle in self.trains:
            distance_list = []
            for stop in s_list:
                lat1 = stop['latitude']
                lat2 = vehicle['latitude']
                lon1 = stop['longitude']
                lon2 = vehicle['longitude']
                distance = point_distance(lat1, lon1, lat2, lon2)
                distance_list.append(distance)

            for idx, i in enumerate(zip(distance_list, s_list)):
                distance = i[0]
                stop = i[1]
                if idx == 0:
                    if distance < 0.2:
                        logger.debug('found at stop', s_list[idx]['name'])
                        vehicle['stop_num'] = stop['number']
                        break
                    else:
                        logger.debug('Setting stop to initital val {}'.format(stop['name']))
                        vehicle['stop_num'] = stop['number'] + 1
                if idx >= 1:
                    if distance < 0.2:
                        logger.debug('found at stop', s_list[idx]['name'])
                        vehicle['stop_num'] = stop['number']
                        break
                    elif distance < distance_list[idx - 1]:
                        logger.debug('found closer match')
                        vehicle['stop_num'] = stop['number'] + 1
                        logger.debug('setting to btw {} and {}'.format(s_list[idx-1]['name'], stop['name']))

                    else:
                        break

        return self.trains


class Stop(ApiRequest):
    def __init__(self, api_filter=None):
        super().__init__()
        self.api_method = 'stops'
        self.api_filter = api_filter
        self.stop_list = []

    def get_stops(self):
        url = self.build_api_url(self.api_method, self.api_filter)
        stops = self.call_api(url)
        for stop in stops['data']:
            stop_dict = dict(name=stop['attributes']['name'],
                             latitude=stop['attributes']['latitude'],
                             longitude=stop['attributes']['longitude'],
                             id=stop['id'])
            self.stop_list.append(stop_dict)
        return self.stop_list

    def assign_locations(self, num_lights):
        """
        Get the spacing of the stops based on the number of leds
        :param num_lights:
        :return:
        """
        if not self.stop_list:
            self.get_stops()

        stop_spacing = math.floor(round(num_lights / len(self.stop_list)))

        stop_index = 0
        for stop in self.stop_list:
            stop['number'] = stop_index
            stop_index += stop_spacing

        return self.stop_list


class Lights(object):
    def __init__(self, num_lights):
        self.num_pixels = num_lights
        self.__pixel = neopixel.NeoPixel(board.D18, num_lights, auto_write=False)

    def __setitem__(self, key, value):
        self.__pixel[key] = value

    def __getitem__(self, idx):
        return self.__pixel[idx]

    def show(self):
        # Create a ASCII version for logging
        pix_list = []
        for p in self.__pixel:
            if p == (0, 0, 0):
                pix_list.append('-')
            else:
                pix_list.append('o')
        logger.info(''.join(pix_list))

        # Send the command to change the lights
        self.__pixel.show()


class LightMock(object):
    def __init__(self, num_lights):
        self.num_pixels = num_lights
        self.__pixel = [''] * num_lights

    def __setitem__(self, key, value):
        self.__pixel[key] = value

    def __getitem__(self, idx):
        return self.__pixel[idx]

    def show(self):
        logger.info(''.join(self.__pixel))
        return ''.join(self.__pixel)


def point_distance(lat1, lon1, lat2, lon2):
    """Distance in kms between two points"""
    lat1 = math.radians(abs(lat1))
    lat2 = math.radians(abs(lat2))
    lon1 = math.radians(abs(lon1))
    lon2 = math.radians(abs(lon2))

    # approximate radius of earth in km
    r = 6373.0
    delta_lon = lon2 - lon1
    delta_lat = lat2 - lat1

    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = r * c
    return distance


def get_data(api_filter, num_lights):
    stops = Stop(api_filter)
    trains = Train(api_filter)

    logger.info('getting stops...')
    stop_list = stops.assign_locations(num_lights)
    logger.info('retrieved stops: {}'.format(stop_list))

    logger.info('getting trains...')
    train_list = trains.map_to_stop_number(stop_list)
    logger.info('retrieved trains: {}'.format(train_list))

    light_list = []

    for train in train_list:
        stop_num = train['stop_num']
        light_list.append(stop_num)

    return light_list


if __name__ == '__main__':

    if mock_lights:
        pixels = LightMock(40)
        light_on = 'O'
        light_off = '-'

    else:
        pixels = Lights(40)
        light_on = (20, 2, 0)
        light_off = (0, 0, 0)

    while True:

        # filter for O line
        orange_filter = "filter%5Broute%5D=Orange"

        pixel_list = get_data(orange_filter, 40)

        for pix in range(40):
            if pix in pixel_list:
                pixels[pix] = light_on
            else:
                pixels[pix] = light_off

        pixels.show()

        time.sleep(5)
