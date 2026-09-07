#!/usr/bin/env python
# coding: utf-8

# A massive help with this code come from: https://hackersandslackers.com/extract-data-from-complex-json-python/
# 
# Without Todd's article I fear I may have been lost forever!

import json
import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import math


def _normalize_material_column(frame):
    if 'material' not in frame.columns:
        return frame
    normalized = frame.copy()
    normalized['material'] = (
        normalized['material']
        .astype(str)
        .str.replace('\xa0', ' ', regex=False)
        .str.strip()
    )
    return normalized


def _safe_read(reader, path, **kwargs):
    """Read a bundled reference file, tolerating a missing/unreadable file.

    Several reference datasets are optional in a fresh checkout (they are seeded
    into the database and refreshed from there at runtime). Import of this module
    must never fail just because one of the source files is absent.
    """
    try:
        return reader(path, **kwargs)
    except Exception:
        return pd.DataFrame()


suppliers = _safe_read(pd.read_csv, 'data/df3.csv')
sites = _safe_read(pd.read_excel, 'sites.xlsx')
divert_output = _safe_read(pd.read_csv, 'divert_db.csv')
reuse_offset = _normalize_material_column(_safe_read(pd.read_csv, 'reuse_offset.csv'))
recycle_offset = _normalize_material_column(_safe_read(pd.read_excel, 'recycle_offset.csv'))
carbon_equivalencies = _safe_read(pd.read_excel, 'carbon_equivalencies.csv')

if not divert_output.empty:
    divert_output['reuse_offset'] = np.nan
    divert_output['recycle_offset'] = np.nan
if 'material' in reuse_offset.columns:
    reuse_offset.set_index(keys='material', inplace=True)
if 'material' in recycle_offset.columns:
    recycle_offset.set_index(keys='material', inplace=True)

API_KEY = (os.getenv('GOOGLE_MAPS_API_KEY') or '').strip()

def google_maps_distance(destinations, origins):
    """Fetch distance between two points."""
    if not API_KEY:
        raise ValueError('GOOGLE_MAPS_API_KEY is not configured.')
    destinations = ''.join(destinations)
    endpoint = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
       'units': 'imperial',
       'key': API_KEY,
       'origins': origins,
       'destinations': destinations,
    }
    r = requests.get(endpoint, params=params)
    travel_values = json_extract(r.json(), 'text')
    return travel_values

def json_extract(obj, key):
    """Recursively fetch values from nested JSON."""
    arr = []

    def extract(obj, arr, key):
        """Recursively search for values of key in JSON tree."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    extract(v, arr, key)
                elif k == key:
                    arr.append(v)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr

    values = extract(obj, arr, key)
    return values

def shortest_ditance_calculator(suppliers, sup_type, origin, n):
    
    df = suppliers[suppliers['sup_type']== sup_type]
    df.reset_index(inplace=True)
    
    destinations = []
    for i, row in df.iterrows():
        destination = str(df['lat'].loc[i]) + ',' + str(df['long'].loc[i]) + '|'
        destinations.append(destination)
    
    chunks = [destinations[x:x+25] for x in range(0, len(destinations), 25)]
    
    
    num = []
    for f in range(len(chunks)):
        my_values = []
        chunks[f][-1] = chunks[f][-1].replace('|', '')
        
        my_values=google_maps_distance(chunks[f], origin)
        
        even_i = []
        odd_i = []
        for r in range(0, len(my_values)): 
            if r % 2:
                even_i.append(my_values[r]) 
            else : 
                odd_i.append(my_values[r])
        
        distances = [s.replace('mi', '') for s in odd_i]
        distances = [s.replace(' ', '') for s in distances]
        distances = [float(r) for r in distances]
        
        num.extend(distances)
        
    # >There may be a slight problem with indexing on this front.
    
    d = np.array(num)
    
    di = d.argsort()[:n]
    
    
    for index in di:
        print('Name: {} \nCity: {} \nPostcode: {}\nDistance: {}\n'.format(df['name'].iloc[index], df['city'].iloc[index],
                                                                          df['postcode'].iloc[index], num[index]))
        
    return di[0]

def shortest_ditance_calculator_input(suppliers, sup_type, origin, n):
    
    df = suppliers[suppliers['sup_type']== sup_type]
    df.reset_index(inplace=True)
    
    destinations = []
    for i, row in df.iterrows():
        destination = str(df['lat'].loc[i]) + ',' + str(df['long'].loc[i]) + '|'
        destinations.append(destination)
    
    chunks = [destinations[x:x+25] for x in range(0, len(destinations), 25)]
    
    
    num = []
    for f in range(len(chunks)):
        my_values = []
        chunks[f][-1] = chunks[f][-1].replace('|', '')
        
        my_values=google_maps_distance(chunks[f], origin)
        
        even_i = []
        odd_i = []
        for r in range(0, len(my_values)): 
            if r % 2:
                even_i.append(my_values[r]) 
            else : 
                odd_i.append(my_values[r])
        
        distances = [s.replace('mi', '') for s in odd_i]
        distances = [s.replace(' ', '') for s in distances]
        distances = [float(r) for r in distances]
        
        num.extend(distances)
        
    # >There may be a slight problem with indexing on this front.
    
    d = np.array(num)
    
    di = d.argsort()[:n]
    
    
 
    print('Method: {} \nName: {} \nDistance: {}\n'.format(sup_type, df['name'].iloc[di[0]], num[di[0]]))
        
    return num[di[0]]

def shortest_ditance_calculator_input2(suppliers, sup_type, origin, n):
    
    df = suppliers[suppliers['sup_type']== sup_type]
    df.reset_index(inplace=True)
    
    destinations = []
    for i, row in df.iterrows():
        destination = str(df['lat'].loc[i]) + ',' + str(df['long'].loc[i]) + '|'
        destinations.append(destination)
    
    chunks = [destinations[x:x+25] for x in range(0, len(destinations), 25)]
    
    
    num = []
    for f in range(len(chunks)):
        my_values = []
        chunks[f][-1] = chunks[f][-1].replace('|', '')
        
        my_values=google_maps_distance(chunks[f], origin)
        
        even_i = []
        odd_i = []
        for r in range(0, len(my_values)): 
            if r % 2:
                even_i.append(my_values[r]) 
            else : 
                odd_i.append(my_values[r])
        
        distances = [s.replace('mi', '') for s in odd_i]
        distances = [s.replace(' ', '') for s in distances]
        distances = [float(r) for r in distances]
        
        num.extend(distances)
        
    # >There may be a slight problem with indexing on this front.
    
    d = np.array(num)
    
    di = d.argsort()[:n]
        
    return num[di[0]]


def shortest_ditance_calculator_charity(suppliers, origin, n):
    
    df = suppliers[suppliers['sup_type']== 'Charity']
    df.reset_index(inplace=True)
    
    destinations = []
    for i, row in df.iterrows():
        destination = str(df['lat'].loc[i]) + ',' + str(df['long'].loc[i]) + '|'
        destinations.append(destination)
    
    chunks = [destinations[x:x+25] for x in range(0, len(destinations), 25)]
    
    
    num = []
    for f in range(len(chunks)):
        my_values = []
        chunks[f][-1] = chunks[f][-1].replace('|', '')
        
        my_values=google_maps_distance(chunks[f], origin)
        even_i = []
        odd_i = []
        for r in range(0, len(my_values)): 
            if r % 2:
                even_i.append(my_values[r]) 
            else : 
                odd_i.append(my_values[r])
        
        distances = [s.replace('mi', '') for s in odd_i]
        distances = [s.replace(' ', '') for s in distances]
        distances = [float(r) for r in distances]
        
        
        

        num.extend(distances)
        
    # >There may be a slight problem with indexing on this front.
    
    d = np.array(num)
    
    di = d.argsort()[:n]
    
    
    for index in di:
        print('Name: {} \nCity: {} \nPostcode: {}\nDistance: {}\nEmail: {}\n'.format(df['name'].iloc[index+1], df['city'].iloc[index+1],
                                                                                     df['postcode'].iloc[index+1], num[index], df['email'].iloc[index+1]))

def shortest_ditance_calculator_charity_input(suppliers, sup_type, origin, n):
    
    df = suppliers[suppliers['sup_type']== sup_type]
    df.reset_index(inplace=True)
    
    destinations = []
    for i, row in df.iterrows():
        destination = str(df['lat'].loc[i]) + ',' + str(df['long'].loc[i]) + '|'
        destinations.append(destination)
    
    chunks = [destinations[x:x+25] for x in range(0, len(destinations), 25)]
    
    
    num = []
    for f in range(len(chunks)):
        my_values = []
        chunks[f][-1] = chunks[f][-1].replace('|', '')
        
        my_values=google_maps_distance(chunks[f], origin)
        even_i = []
        odd_i = []
        for r in range(0, len(my_values)): 
            if r % 2:
                even_i.append(my_values[r]) 
            else : 
                odd_i.append(my_values[r])
        
        distances = [s.replace('mi', '') for s in odd_i]
        distances = [s.replace(' ', '') for s in distances]
        distances = [float(r) for r in distances]
        
        
        

        num.extend(distances)
        
    # >There may be a slight problem with indexing on this front.
    
    d = np.array(num)
    
    di = d.argsort()[:n]
    
    
    #for index in di:
        #print('Name: {} \nCity: {} \nPostcode: {}\nDistance: {}\n'.format(df['name'].iloc[index+1], df['city'].iloc[index+1],
                                                                          #df['postcode'].iloc[index+1], num[index]))
        
    return di[0]


# NOTE: the transport-carbon and offset "calculator" helpers that used to live
# here (landfill_carbon_transport_cost, mrf_carbon_transport_cost,
# reuse_offset_calculator, equivalency_calculator, ...) applied undocumented
# magic multipliers (x0.85, x1.2, +114). They are retired in favour of the
# ISO 14040/14044-aligned model in project_divert_lca.py, driven by a cited
# emission-factor dataset (data/lca/emission_factors.csv).


def numeric_distance(origin, destination, return_none_on_failure=False):
    try:
        values = google_maps_distance(destination, origin)
        if not values:
            if return_none_on_failure:
                return None
            return 0.0
        d = str(values[0]).strip().lower().replace(',', '')
        if d.endswith('mi'):
            return float(d.replace('mi', '').strip())
        if d.endswith('ft'):
            return float(d.replace('ft', '').strip()) / 5280.0
        if d.endswith('km'):
            return float(d.replace('km', '').strip()) * 0.621371
        return float(d)
    except Exception:
        # Fail safe for API/rate-limit/format issues so calculator still renders.
        if return_none_on_failure:
            return None
        return 0.0
