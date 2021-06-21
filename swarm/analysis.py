"""
Author: I. Cornelius
Copyright Amentum Pty Ltd 2021
"""
import argparse
import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
import numpy as np
import os, sys
sys.path.append(os.environ['CDF_LIB'])
import pandas as pd
import chart_studio.plotly as py
import plotly.graph_objs as go
from plotly.offline import download_plotlyjs, init_notebook_mode, plot, iplot
from PyAstronomy import pyasl
import pysatMagVect as psmv
import requests
from spacepy import pycdf

# TODO automatically download and unzip from the SWARM server for the current day

parser = argparse.ArgumentParser()

parser.add_argument(
    "--host",
    dest="host",
    action="store",
    help="Alternative host for testing (e.g. on-premises API server)",
    default="https://geomag.amentum.io",
)

parser.add_argument('--cdf_file', dest='cdf_file', action='store',
    help='SWARM CDF FILE ',
    default='')

parser.add_argument(
    "--api_key",
    dest="api_key",
    action="store",
    help="valid API key obtained from https://developer.amentum.io",
    default=""    
)

args = parser.parse_args()

cdf = pycdf.CDF(args.cdf_file)

df = pd.DataFrame(
    columns = [
        'time', 'decimal_year', 'latitude', 'longitude', 'decl_swarm', 'decl_api'])

hostname = args.host + "/wmm/magnetic_field"

earth_radius = 6371.0 # [km] assumed by pysatMagVect

# Reduce the number of API calls to avoid exceeding the limit
reduction_factor = 100

for i, timestamp in enumerate(cdf['Timestamp']):

    # limit number of API calls
    if i%reduction_factor != 0 : continue 

    latitude_geocentric = cdf['Latitude'][i]
    longitude_geocentric = cdf['Longitude'][i]
    radius_geocentric = cdf['Radius'][i]

    altitude_geocentric = radius_geocentric/1000.0 - earth_radius # [km]

    # convert from geocentric to geodetic coordinates
    x, y, z = psmv.geocentric_to_ecef(
        latitude_geocentric, longitude_geocentric, altitude_geocentric)
     
    # calculate elevation
    latitude, longitude, altitude = psmv.ecef_to_geodetic(x, y, z)
    
    # calculate decimal year 
    decimal_year = pyasl.decimalYear(timestamp)

    # calculate experimental declination 
    bx, by, bz = cdf['B_NEC'][i]
    
    decl_swarm = np.arctan(by / bx)
    decl_swarm = np.rad2deg(decl_swarm)

    # make API call to fetch declination 
    params = dict(
        altitude = altitude, # [km]
        longitude = longitude, # [deg]
        latitude = latitude,
        year = decimal_year
    )
    headers = {
        "API-Key" : args.api_key
    }

    try: 
        response = requests.get(hostname, params=params, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(response.json())
        print(e.args)
    except requests.exceptions.RequestException as e:
        print(response.json())
        print(e.args)

    response_json = response.json()

    decl_api = response_json["declination"]["value"]

    new_row = {
        'time' : timestamp.strftime("%H:%M:%S"),
        'decimal_year' : decimal_year,
        'latitude' : latitude, 
        'longitude' : longitude, 
        'decl_swarm' : decl_swarm, 
        'decl_api' : decl_api
    }

    df = df.append(new_row, ignore_index = True)

# Now create interactive map plot using plotly

# create new column in dataframe to use as label

df["label"] = \
    "Time: " + df['time'] + '<br>' + \
    "Measured: " + df["decl_swarm"].round(decimals=3).astype(str)  + '<br>' + \
    "Calculated: " + df["decl_api"].round(decimals=3).astype(str)  

# define the marker for the 
marker = go.scattergeo.Marker(
    size = 5, 
    line = go.scattergeo.marker.Line( width=0.5 ),
    sizemode = 'area',
    reversescale = True,
    colorscale = 'Jet',
    cmin = -45,
    color = df['decl_api'],
    cmax = 45,
    colorbar=dict(
        title="Declination <br> (Degrees)",
        thickness = 15
    )
)

# define the data to scatter plot onto the map
data = [
    go.Scattergeo(
        lon = df["longitude"],
        lat = df["latitude"],
        text = df['label'],
        marker = marker
    )
]

# geographic map layout defintion
layout = go.Layout(
    title=go.layout.Title(
        text="Magnetic declination values measured by the \
<a href='https://earth.esa.int/web/guest/swarm/data-access'>SWARM-A</a> satellite <br>\
and calculated by the <a href='https://www.ngdc.noaa.gov/geomag/WMM/'>World Magnetic Model</a> \
using the <a href='https://amentum.space'>AMENTUM API</a> <br>\
on " + timestamp.strftime("%Y-%m-%d")),
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

# the default figure defined
fig = go.Figure(data=data, layout=layout)

# TODO uncomment this to plot without UI controls 
#plot(fig, filename = 'magnetic-declination-validation-swarm')

# UI control - a range slider using dash components that slices the data
# by time to enable visualisation of partial orbits
# (the SWARM sats make approx 15 orbits per day) 

# Launch a dash application to build the UI

app = dash.Dash()

def get_marks():
    """
    Returns a dictionary containin keys (decimalyear values) and tick labels 
    in (hour:minute) format.  

    """    
    # copy the latest timestamp 
    ts = timestamp
    
    # create datetime objects every 3 hours (otherwise plot is crowded)
    ticks_datetime = [
        ts.replace(hour=h, minute=0, second=0) for h in range(0,24,3)
    ]

    # convert those values to decimal year ticks
    ticks_dec_year = [pyasl.decimalYear(ts) for ts in ticks_datetime]

    # construct tick labels
    tick_labels = [ts.strftime("%H:%M") for ts in ticks_datetime]

    # construct dictionary of key (decimal year) and values (tick labels) required by dash
    return dict(zip(ticks_dec_year, tick_labels))

# Create a Dash layout

# ensures smooth range slide
decimal_year_step  = (df['decimal_year'].max() - df['decimal_year'].min()) / 1000.0

app.layout = html.Div([
    # the plotly graph
    dcc.Graph(id = 'plot', figure = fig),
    # range slider p element
    html.P([
        html.Label("Choose time window"),
        dcc.RangeSlider(
            id = 'slider',
            min = df['decimal_year'].min(), # use decimal year 
            max = df['decimal_year'].max(),
            step = decimal_year_step,
            dots = False,
            updatemode = 'mouseup',
            marks = get_marks(),
            value = [
                df['decimal_year'].min(),
                df['decimal_year'].min() + decimal_year_step*90.0
            ]
        )
    ], style = {
        'width':'50%', 
        'margin':25, 
        'color': '#7f7f7f', 
        'fontSize': 10, 
        'textAlign' : 'center',
        'fontFamily' : 'Courier New, monospace'
        } 
    ),
], style = {
   'display': 'flex',
    'flex-direction' : 'column',
   'align-items': 'center',
   'justify-content': 'center'
}
) # style to match that used by plotly graph

# the value of RangeSlider causes Graph to update using this callback

@app.callback(
    output=Output('plot', 'figure'),
    inputs=[Input('slider', 'value')]
)
def update_figure(year_range):
    """ 
    Triggered by user interaction with the rangeslider
    """
    # filter dataset according to min/max of slider
    filtered_df = df[
        (df.decimal_year < year_range[1]) & (df.decimal_year > year_range[0])
    ] 

    # update the color values 
    marker.color = filtered_df['decl_api']

    # replace the figure data with filtered data
    data = [
        go.Scattergeo(
            lon = filtered_df["longitude"],
            lat = filtered_df["latitude"],
            text = filtered_df['label'],
            marker = marker
        )
    ]

    # create new figure object to return to dash widget, no change in layout
    fig = go.Figure(data=data, layout=layout)

    return fig

# start the dash server
if __name__ == '__main__':
    app.run_server(debug = True)



