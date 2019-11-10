import argparse
import matplotlib.pyplot as plt
import numpy as np 
import os
import pandas as pd 
import plotly.plotly as py
import plotly.graph_objs as go
from plotly.offline import download_plotlyjs, init_notebook_mode, plot, iplot
import requests

parser = argparse.ArgumentParser()

parser.add_argument('--iaga_dir', dest='iaga_dir', action='store',
    help='Directory containing IAGA 2002 formatted data files for INTERMAG network ',
    default='data/')

args = parser.parse_args()

# get all the filenames in the data directory
filenames = [
    f for f in next(os.walk(args.iaga_dir))[2] if f.endswith(".min") and '' in f
]

# TODO protect against empty directory

# we need this to enforce requirement that data from a single date
current_date = None

# a dataframe to append the daily data from all stations
df_global = pd.DataFrame(columns=[
    "date", "station", "latitude", "longitude", "altitude", 
    "declination", "uncertainty", "declination_api"
])

hostname = "https://globalmagnet.amentum.space/api/calculate_magnetic_field"
hostname = "http://localhost:5000/api/calculate_magnetic_field"

for filename in filenames: 

    # storing header info
    header = {}

    # first pass to parse the header of the IAGA-2002 formatted data file
    with open(args.iaga_dir+'/'+filename) as myfile : 
        for i, myline in enumerate(myfile): 
            # ignore lines with poudn sign in them
            if '#' in myline : 
                pass
            # we are at the end of the header, so break loop
            elif myline.split()[0] == 'DATE':
                break
            # otherwise parse header entry into KV pair
            else : 
                key, value = myline[:24], myline[24:]
                key = ' '.join(key.split())
                value = value.split()
                if '|' in value : value.remove('|')
                value = ' '.join(value)
                # we drop key to lower case, as capitalisation inconsistent between stations
                header[key.lower()] = value 

    header_length = i

    # now read the rest of the file into a dataframe
    df = pd.read_csv(args.iaga_dir+'/'+filename, 
        skiprows=header_length, # start from end of header
        delim_whitespace=True) # delimit on any number of whitespaces
    # remove column resulting from pesky vertical bar in header
    df.drop('|', axis=1)

    # column name is concat of station code and coordinate
    x_label = header['iaga code']+'X'
    y_label = header['iaga code']+'Y'
    # some stations only provide declination data directly, use if available
    d_label = header['iaga code']+'D'
    e_label = header['iaga code']+'E'

    nan_value = 99999.00

    if d_label in df.columns : 
        valid_rows = (df[d_label] != nan_value)
    elif e_label in df.columns : 
        valid_rows = (df[e_label] != nan_value)
    else : 
        # missing or corrupted data assigned 99999.00 value in IAGA standard 
        valid_rows = (df[x_label] != nan_value) & (df[y_label] != nan_value)

    # discard invalid rows
    df = df[valid_rows]

    if(len(df) == 0) : 
        print("Zero valid entris for {} skipping ...  ".format(header['iaga code']))
        continue
    
    if d_label in df.columns:
        declinations = df[d_label]
    elif e_label in df.columns:
        declinations = df[e_label]
    else: 
        # calculate declination using Y and X components, X is in direction of true north
        declinations = np.arctan(df[y_label] / df[x_label])
        declinations = np.rad2deg(declinations)

    # stats 
    daily_mean = np.mean(declinations)
    daily_std_error = np.std(declinations) / np.sqrt(len(declinations)-1)

    # Calculate the decimal year to compare with WMM prediction  
    date = df['DATE'].values[0]
    day_of_year = df['DOY'].values[0]
    decimal_year = int(date.split('-')[0]) + day_of_year / 365.0

    try:
        if current_date is None : 
            current_date = decimal_year
        elif current_date != decimal_year : 
            raise ValueError("IAGA files must be from same day")
    except ValueError as err:
        print(err.args)

    # hit the API to calculate declination using the WMM 
    # extract paramers from header for WMM calculation using the API

    # convert longitude to -180 to 180 range from 0 to 360 used by IAGA2002
    longitude = np.float(header['geodetic longitude'])
    if longitude > 180 : longitude -= 360.0 

    latitude = header['geodetic latitude']

    altitude = header['elevation']
    if altitude == "" : altitude = 0

    # convert to kms
    altitude = float(altitude)/1000

    payload = dict(
        altitude = altitude, # [km]
        longitude = longitude, # [deg]
        latitude = latitude,
        year = decimal_year
    )

    try: 
        response = requests.get(hostname, params=payload)
    except requests.exceptions.RequestException as e:
        print(e.args)

    response_json = response.json()

    dec_api = response_json["declination"]["value"]

    # handle inconsistency in labelling between stations
    if "station name" in header : 
        station_name = header["station name"] 
    else : 
        station_name = header["station"]

    station_data = {
        "date" : decimal_year ,
        "station" : station_name,
        "latitude" : latitude, 
        "longitude" : np.float(header['geodetic longitude']) , # plotly uses (0,360)
        "altitude" : altitude, 
        "declination" : daily_mean, 
        "uncertainty" : daily_std_error,
        "declination_api" : dec_api
    }

    # append data for this station to the global dataframe
    # append doesn't happen in place so we over-write origy
    df_global = df_global.append(station_data, ignore_index = True)


# create new column in dataframe to use as label
df_global["label"] = "Station: " + df_global['station'] + '<br>' + \
    "Measured " + df_global["declination"].round(decimals=3).astype(str)  + '<br>' + \
    "Calculated " + df_global["declination_api"].round(decimals=3).astype(str)  
    
# TODO overlay markers with size according to absolute difference betw calc and measured

# TODO plot true north and magnetic north poles on map 

# Now create interactive plot using plotly
data = [
    go.Scattergeo(
        lon = df_global["longitude"],
        lat = df_global["latitude"],
        text = df_global['label'],
        marker = go.scattergeo.Marker(
            size = 10, #np.abs(df_global["declination_api"]),
            line = go.scattergeo.marker.Line(
                width=0.5 #, color='rgb(40,40,40)'
            ),
            sizemode = 'area',
            reversescale = True,
            colorscale = 'Jet',
            cmin = -45,
            color = df_global['declination_api'],
            cmax = 45,
            colorbar=dict(
                title="Calculated <br>Declination <br>(Degrees)",
                thickness = 15
            )
        ),
    )
]

layout = go.Layout(
    title=go.layout.Title(
        text="Magnetic declination values on "+date+\
" <br>measured by <a href='http://www.intermagnet.org'>INTERMAGNET</a> observatories<br>\
and calculated by \
<a href='https://www.ngdc.noaa.gov/geomag/WMM/'>WMM2015v2</a> \
using the <a href='https://amentum.space'>AMENTUM API</a>"),
    font=dict(family='Courier New, monospace', size=12, color='#7f7f7f'),
    geo=go.layout.Geo(
        resolution = 50,
        scope = 'world',
        showframe = False,
        showcoastlines = True,
        showland = True,
        landcolor = "rgb(229, 229, 229)",
        countrycolor = "rgb(255, 255, 255)" ,
        coastlinecolor = "rgb(255, 255, 255)",
        projection = go.layout.geo.Projection(
            type = 'equirectangular'
        )
    ),
)

fig = go.Figure(data=data, layout=layout)

plot(fig, filename = 'magnetic-declination-validation')
