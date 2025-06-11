import h3
import folium
import os
import webbrowser
import pandas as pd
import requests
from mapbox import Geocoder
import branca.colormap as cm
import geojson
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

mapboxToken = "pk.eyJ1IjoicHJhZnVsZGV2IiwiYSI6ImNtYmdoMG0yMTFiZXQybHFuejNiNzFsZWwifQ.3wEV9mcJ_U-nyrmwYqu-lw"
datasetId = "cmbi0p7u40dqe1upgof4b94qc"
username = 'prafuldev'
url = f'https://api.mapbox.com/datasets/v1/{username}/{datasetId}/features?access_token={mapboxToken}'



def compute_h3_and_boundaries(row, resolution=8):
    # Extract latitude and longitude from the current row
    lat = row['Latitude']
    lng = row['Longitude']

    # Convert lat/lng to an H3 cell index at the specified resolution
    cell = h3.latlng_to_cell(lat, lng, resolution)

    # Get the geographic boundary (polygon) of the H3 cell as a list of lat/lng points
    boundaries = h3.cell_to_boundary(cell)

    # Return the cell index and its boundary as a pandas Series for assignment
    return pd.Series([cell, boundaries])


# Load the CSV data with specified encoding to avoid decode errors
data = pd.read_csv('311_service_data_2024.csv', encoding='latin-1')

# Filter
data = data[data['Case Summary'] == 'Alarm Permit']

# Remove rows missing latitude or longitude coordinates
data = data.dropna(subset=['Latitude', 'Longitude'])

# Keep only latitude and longitude columns for further processing
data = data[['Latitude', 'Longitude']]

# Apply the H3 computation function to each row, adding 'cell' and 'Boundaries' columns
data[['cell', 'Boundaries']] = data.apply(compute_h3_and_boundaries, axis=1)

# Aggregate counts of points per H3 cell
data_count = data.groupby('cell').size().reset_index(name='Count')

# Merge the polygon boundaries back to the aggregated counts (one boundary per cell)
data_count = data_count.merge(data[['cell', 'Boundaries']].drop_duplicates(), on='cell', how='left')

# Initialize a Folium map centered on the average coordinates of the dataset
map = folium.Map(location=[data['Latitude'].mean(), data['Longitude'].mean()], zoom_start=12, tiles='cartodbpositron')

# Add Mapbox tile layer on top of the base map (requires your Mapbox access token)
folium.TileLayer(
    tiles=f'https://api.mapbox.com/styles/v1/mapbox/streets-v11/tiles/{{z}}/{{x}}/{{y}}?access_token={mapboxToken}',
    attr='Mapbox',
    name='Mapbox Streets',
    max_zoom=18,
    tile_size=512,
    zoom_offset=-1
).add_to(map)

# Create a color scale for counts (from light pink to red)
colormap = cm.LinearColormap(colors=['#fb4c5e', '#242873'], vmin=data_count['Count'].min(), vmax=80)

# Loop through each H3 cell with its count and polygon boundary
for _, row in data_count.iterrows():
    boundaries = row['Boundaries']  # List of lat/lng points outlining the hexagon
    count = row['Count']  # Number of category in this hex

    # Get a color from the colormap based on the count
    color = colormap(count)

    # Add the hexagon polygon to the map with the color and popup showing count
    folium.Polygon(
        locations=boundaries,
        color=color,
        weight=1,
        fill=True,
        fill_opacity=0.7,
        popup=f'Count: {count}'
    ).add_to(map)

## NEW CODE
hex_polygons = []  # For merged union

for _, row in data_count.iterrows():
    boundaries = row['Boundaries']
    count = row['Count']
    color = colormap(count)
    # Convert to shapely polygon for union
    hex_polygons.append(Polygon([(lng, lat) for lat, lng in boundaries]))

# --- Union all hexagons into one polygon ---
merged_polygon = unary_union(hex_polygons)
merged_polygon = merged_polygon.simplify(tolerance=0.005, preserve_topology=True)
merged_polygon = merged_polygon.buffer(0.0005, join_style="round", cap_style="round")


if isinstance(merged_polygon, MultiPolygon):
    for part in merged_polygon.geoms:
        coords = [(lat, lng) for lng, lat in part.exterior.coords]
        folium.Polygon(
            locations=coords,
            color='black',
            weight=3,
            fill=False,
            popup='Merged Area'
        ).add_to(map)

# --- Add color scale legend ---
colormap.add_to(map)
## END

# Save the map to an HTML file and open it in the default web browser
map_path = 'map.html'
map.save(map_path)
webbrowser.open('file://' + os.path.realpath(map_path))
