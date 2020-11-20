import jinja2
import matplotlib
import matplotlib.pyplot as plt
import os
import pytz
import requests
import sqlite3

from pprint import PrettyPrinter
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, send_file
from geopy.geocoders import Nominatim
from io import BytesIO
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas


################################################################################
# SETUP
################################################################################

app = Flask(__name__)

# Get the API key from the '.env' file
load_dotenv()
API_KEY = os.getenv('API_KEY')

# Settings for image endpoint
# Written with help from http://dataviztalk.blogspot.com/2016/01/serving-matplotlib-plot-that-follows.html
matplotlib.use('agg')
plt.style.use('ggplot')

my_loader = jinja2.ChoiceLoader([
    app.jinja_loader,
    jinja2.FileSystemLoader('data'),
])
app.jinja_loader = my_loader

pp = PrettyPrinter(indent=4)

################################################################################
# ROUTES
################################################################################


def getWeekDay(date):
    """ This function will return a weekday """
    weekDays = ("Monday", "Tuesday", "Wednesday",
                "Thursday", "Friday", "Saturday", "Sunday")
    return weekDays[date.weekday()]


def formatDate(dateObj):
    """ This function will return a formatted date """
    return dateObj.strftime("%B %d, %Y")


def formatTime(timeObj):
    """ This function will return a formatted time """
    return timeObj.strftime("%H:%M:%S")


@app.route('/')
def home():
    """Displays the homepage with forms for current or historical data."""
    context = {
        'min_date': (datetime.now() - timedelta(days=5)),
        'max_date': datetime.now()
    }
    return render_template('home.html', **context)


def get_letter_for_units(units):
    """Returns a shorthand letter for the given units."""
    return 'F' if units == 'imperial' else 'C' if units == 'metric' else 'K'


@app.route('/results')
def results():
    """Displays results for current weather conditions."""

    city = request.args.get('city')
    units = request.args.get('units')
    url = 'http://api.openweathermap.org/data/2.5/weather'
    params = {
        'appid': API_KEY,
        'q': city,
        'units': units,
    }

    result_json = requests.get(url, params=params).json()

    # pp.pprint(result_json)

    context = {
        'date': formatDate(datetime.now()),
        'weekday': getWeekDay(datetime.now()),
        'city': result_json['name'],
        'description': result_json['weather'][0]['description'],
        'temp': result_json['main']['temp'],
        'humidity': result_json['main']['humidity'],
        'wind_speed': result_json['wind']['speed'],
        'sunrise': formatTime(datetime.fromtimestamp(result_json['sys']['sunrise'])),
        'sunset': formatTime(datetime.fromtimestamp(result_json['sys']['sunset'])),
        'units_letter': get_letter_for_units(units)
    }

    return render_template('results.html', **context)


def get_min_temp(results):
    """Returns the minimum temp for the given hourly weather objects."""
    hourly_temp = [entry['temp'] for entry in results]
    return max(hourly_temp)


def get_max_temp(results):
    """Returns the maximum temp for the given hourly weather objects."""
    hourly_temp = [entry['temp'] for entry in results]
    return min(hourly_temp)


def get_lat_lon(city_name):
    geolocator = Nominatim(user_agent='Weather Application')
    location = geolocator.geocode(city_name)
    if location is not None:
        return location.latitude, location.longitude
    return 0, 0


@app.route('/historical_results')
def historical_results():
    """Displays historical weather forecast for a given day."""
    city = request.args.get('city')
    units = request.args.get('units')
    date = request.args.get('date')
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    date_in_seconds = date_obj.strftime('%s')

    latitude, longitude = get_lat_lon(city)
    url = 'http://api.openweathermap.org/data/2.5/onecall/timemachine'
    params = {
        'appid': API_KEY,
        'units': units,
        'lat': latitude,
        'lon': longitude,
        'dt': date_in_seconds,
    }

    result_json = requests.get(url, params=params).json()
    result_current = result_json['current']
    result_hourly = result_json['hourly']

    context = {
        'city': city,
        'date': date_obj,
        'formated_date': formatDate(date_obj),
        'weekday': getWeekDay(date_obj),
        'lat': latitude,
        'lon': longitude,
        'units': units,
        'units_letter': get_letter_for_units(units),
        'description': result_json['current']['weather'][0]['description'],
        'temp': result_json['current']['temp'],
        'min_temp': get_min_temp(result_hourly),
        'max_temp': get_max_temp(result_hourly)
    }

    return render_template('historical_results.html', **context)


def extractDailyForecastData(rawData):
    """ This function clean the DailyForecastData and reurn an organized data"""
    organizedList = []
    for entry in rawData:
        organized_entry = [formatDate(datetime.fromtimestamp(entry['dt'])),
                           entry['temp']['day'],
                           entry['weather'][0]['description'],
                           entry['humidity'],
                           formatTime(datetime.fromtimestamp(
                               entry['sunrise'])),
                           formatTime(datetime.fromtimestamp(entry['sunset']))
                           ]
        organizedList.append(organized_entry)
    return organizedList


@app.route('/forecast_results')
def forecast_results():
    """Displays forecast weather for the next 7 days."""
    city = request.args.get('city')
    units = request.args.get('units')
    latitude, longitude = get_lat_lon(city)
    url = 'https://api.openweathermap.org/data/2.5/onecall'
    params = {
        'appid': API_KEY,
        'units': units,
        'lat': latitude,
        'lon': longitude,
        'exclude': 'minutely,hourly',
    }
    result_json = requests.get(url, params=params).json()

    # Uncomment the line below to see the results of the API call!
    pp.pprint(result_json)

    daily_forecast = extractDailyForecastData(result_json['daily'])

    context = {
        'city': city,
        'units_letter': get_letter_for_units(units),
        'daily_forecast': daily_forecast
    }
    return render_template('forecast_results.html', **context)


################################################################################
# IMAGES
################################################################################

def create_image_file(xAxisData, yAxisData, xLabel, yLabel):
    """
    Creates and returns a line graph with the given data.
    Written with help from http://dataviztalk.blogspot.com/2016/01/serving-matplotlib-plot-that-follows.html
    """
    fig, _ = plt.subplots()
    plt.plot(xAxisData, yAxisData)
    plt.xlabel(xLabel)
    plt.ylabel(yLabel)
    canvas = FigureCanvas(fig)
    img = BytesIO()
    fig.savefig(img)
    img.seek(0)
    return send_file(img, mimetype='image/png')


@app.route('/graph/<lat>/<lon>/<units>/<date>')
def graph(lat, lon, units, date):
    """
    Returns a line graph with data for the given location & date.
    @param lat The latitude.
    @param lon The longitude.
    @param units The units (imperial, metric, or kelvin)
    @param date The date, in the format %Y-%m-%d.
    """
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    date_in_seconds = date_obj.strftime('%s')

    url = 'http://api.openweathermap.org/data/2.5/onecall/timemachine'
    params = {
        'appid': API_KEY,
        'lat': lat,
        'lon': lon,
        'units': units,
        'dt': date_in_seconds
    }
    result_json = requests.get(url, params=params).json()

    hour_results = result_json['hourly']

    hours = range(24)
    temps = [r['temp'] for r in hour_results]
    image = create_image_file(
        hours,
        temps,
        'Hour',
        f'Temperature ({get_letter_for_units(units)})'
    )
    return image


if __name__ == '__main__':
    app.run(debug=True)
