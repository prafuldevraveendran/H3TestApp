import json
import os
import pandas as pd
import folium
import webbrowser
import h3
from folium import Map
from shapely import unary_union, MultiPolygon
from shapely.geometry import Polygon, mapping
import branca.colormap as cm
import alphashape
import networkx as nx
from alphashape import alphashape

# === CONFIG ===
INPUT_PATH = '../data/311_service_data_2024.csv'
OUTPUT_PATH = '../output/map.html'
# Use the Default public token
# https://console.mapbox.com/account/access-tokens/
MAPBOX_TOKEN = ''
H3_RESOLUTION = 8


def load_and_filter_data(path):
    data = pd.read_csv(path, encoding='latin-1')
    data = data[data['Case Summary'] == 'Alarm Permit']
    data = data.dropna(subset=['Latitude', 'Longitude'])
    data = data[['Latitude', 'Longitude']]
    data['Group'] = 'Alarm Permit'
    return data


def compute_h3_cells(data):
    def compute(row):
        lat, lng = row['Latitude'], row['Longitude']
        cell = h3.latlng_to_cell(lat, lng, H3_RESOLUTION)
        boundaries = h3.cell_to_boundary(cell)
        return pd.Series([cell, boundaries])

    data[['cell', 'Boundaries']] = data.apply(compute, axis=1)
    return data


def aggregate_counts(data):
    counts = data.groupby('cell').size().reset_index(name='Count')
    counts = counts.merge(data[['cell', 'Boundaries', 'Group']].drop_duplicates(), on='cell', how='left')
    return counts


def create_folium_map(data):
    return folium.Map(
        location=[data['Latitude'].mean(), data['Longitude'].mean()],
        zoom_start=12,
        tiles='cartodbpositron'
    )


def add_mapbox_layer(map_obj):
    folium.TileLayer(
        tiles=f'https://api.mapbox.com/styles/v1/mapbox/streets-v11/tiles/{{z}}/{{x}}/{{y}}?access_token={MAPBOX_TOKEN}',
        attr='Mapbox',
        name='Mapbox Streets',
        max_zoom=18,
        tile_size=512,
        zoom_offset=-1
    ).add_to(map_obj)


def draw_hexagons(map_obj, data_count):
    colormap = cm.LinearColormap(
        colors=['#7d9e96', '#014534'],
        vmin=data_count['Count'].min(),
        vmax=data_count['Count'].max()
    )

    for _, row in data_count.iterrows():
        folium.Polygon(
            locations=row['Boundaries'],
            color=colormap(row['Count']),
            weight=1,
            fill=True,
            fill_opacity=0.7,
            popup=f"Count: {row['Count']}"
        ).add_to(map_obj)

    colormap.add_to(map_obj)


def draw_concave_hulls(map_obj: Map, group):
    # Gather all points from all polygons in this group
    points = []
    for poly in group:
        points.extend(list(poly.exterior.coords))

    # Compute concave hull
    concave_hull = chaikin_smoothing(alphashape(points, alpha=120), 6)

    if concave_hull and isinstance(concave_hull, Polygon):
        coords = [(lat, lng) for lng, lat in concave_hull.exterior.coords]
        folium.Polygon(
            locations=coords,
            color='black',
            weight=5,
            fill=False,
            popup='Concave Hull'
        ).add_to(map_obj)


def chaikin_smoothing(polygon: Polygon, iterations: int = 1, ratio: float = 0.25) -> Polygon:
    def smooth(coords):
        l = len(coords)
        new_coords = []
        for i in range(l):
            p1 = coords[i]
            p2 = coords[(i + 1) % l]  # Wrap to the first point
            q = ((1 - ratio) * p1[0] + ratio * p2[0], (1 - ratio) * p1[1] + ratio * p2[1])
            r = (ratio * p1[0] + (1 - ratio) * p2[0], ratio * p1[1] + (1 - ratio) * p2[1])
            new_coords.extend([q, r])
        new_coords.append(new_coords[0])  # Ensure closed loop
        return new_coords

    coords = list(polygon.exterior.coords)
    if coords[0] == coords[-1]:
        coords = coords[:-1]  # Remove duplicate endpoint if already closed

    for _ in range(iterations):
        coords = smooth(coords)

    return Polygon(coords)


def draw_outline(map_obj: Map, group):
    polygons = list(group)

    # Check all elements are Polygon or MultiPolygon
    polygons = [p for p in polygons if isinstance(p, (Polygon, MultiPolygon))]

    # If none are polygons, nothing to do
    if not polygons:
        return

    smoothened = chaikin_smoothing(unary_union(polygons).simplify(0.0018), 6)
    if isinstance(smoothened, Polygon):
        coords = [(lat, lng) for lng, lat in smoothened.exterior.coords]
        folium.Polygon(
            locations=coords,
            color='black',
            weight=5,
            fill=False,
            popup='Merged Polygon'
        ).add_to(map_obj)
    return smoothened


def find_groups_of_polygons(data_with_count):
    # list of hexagons
    hex_polys = []
    for _, row in data_with_count.iterrows():
        coords = [(lng, lat) for lat, lng in row['Boundaries']]  # flip to (x,y)
        poly = Polygon(coords)
        if poly.is_valid:
            hex_polys.append(poly)

    graph = nx.Graph()
    for i in range(len(hex_polys)):
        graph.add_node(hex_polys[i])

    for i in range(len(hex_polys)):
        for j in range(i + 1, len(hex_polys)):
            if hex_polys[i].touches(hex_polys[j]) or hex_polys[i].intersects(hex_polys[j]):
                graph.add_edge(hex_polys[i], hex_polys[j])

    # Contains sets of hex_polys; each set represents a group of connected polygons.
    groups = list(nx.connected_components(graph))
    print(f"Number of groups: {len(groups)}")
    return groups


def write_polygon_to_geojson(polygon: Polygon | MultiPolygon, filepath: str):
    geojson_feature = {
        "type": "Feature",
        "geometry": mapping(polygon),
        "properties": {}
    }

    geojson = {
        "type": "FeatureCollection",
        "features": [geojson_feature]
    }

    with open(filepath, 'w') as f:
        json.dump(geojson, f, indent=2)


def main():
    data = load_and_filter_data(INPUT_PATH)
    data = compute_h3_cells(data)
    data_with_counts = aggregate_counts(data)

    map_obj = create_folium_map(data)
    add_mapbox_layer(map_obj)
    draw_hexagons(map_obj, data_with_counts)

    groups = find_groups_of_polygons(data)
    for i, group in enumerate(groups):
        # draw_concave_hulls(map_obj, group)
        polygon = draw_outline(map_obj, group)
        write_polygon_to_geojson(polygon, f"../output/{i}.geojson")

    map_obj.save(OUTPUT_PATH)
    webbrowser.open('file://' + os.path.realpath(OUTPUT_PATH))

if __name__ == "__main__":
    main()
