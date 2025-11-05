import requests
import pandas as pd
from pandas import json_normalize

base = "https://services1.arcgis.com/0U8EQ1FrumPeIqDb/arcgis/rest/services/Tax_Sale_Data/FeatureServer/0/query"
params = {
    "where":"1=1",
    "outFields":"USER_TDA_NUM,USER_Sale_Date,USER_Deed_Status,USER_PARCEL",
    "outSR":4326,
    "f":"geojson"
}
gj = requests.get(base, params=params, timeout=30).json()

# Flatten: attributes + geometry.coordinates (lon, lat)
rows = []
for feat in gj.get("features", []):
    atr = feat.get("properties", {}) or feat.get("attributes", {})
    geom = feat.get("geometry", {})
    if isinstance(geom, dict) and "coordinates" in geom:
        lon, lat = geom["coordinates"]
        atr.update({"lon": lon, "lat": lat})
    rows.append(atr)

df = pd.DataFrame(rows)