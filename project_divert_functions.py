#!/usr/bin/env python
# coding: utf-8

# A massive help with this code come from: https://hackersandslackers.com/extract-data-from-complex-json-python/
# 
# Without Todd's article I fear I may have been lost forever!

import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import math

suppliers = pd.read_csv('data/df3.csv')
sites = pd.read_excel('sites.xlsx')
divert_output = pd.read_csv('divert_db.csv')
reuse_offset = pd.read_csv('reuse_offset.csv')
recycle_offset = pd.read_excel('recycle_offset.csv')
carbon_equivalencies = pd.read_excel('carbon_equivalencies.csv')

divert_output['reuse_offset'] = ''
divert_output['recycle_offset'] = ''
divert_output['reuse_offset'] = pd.to_numeric(divert_output['reuse_offset'])
divert_output['recycle_offset'] = pd.to_numeric(divert_output['recycle_offset'])
reuse_offset.set_index(keys='material', inplace=True)

API_KEY = 'REMOVED_GOOGLE_MAPS_API_KEY'

def google_maps_distance(destinations, origins):
    """Fetch distance between two points."""
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


def landfill_monetary_calculator_input(tonnage):
    
    print('Landfill Monetary Cost: {}'.format((tonnage * 100) + 114))
    
def landfill_monetary_calculator(divert_output):
    
    divert_output.landfill_monetary = (divert_output.tonnage * 100) + 114
    

def landfill_carbon_transport_cost(suppliers, origin):
   
    landfill_distance = shortest_ditance_calculator_input(suppliers, 'Landfill', origin, 1)
    landfill_cost = landfill_distance * 0.85

    return landfill_cost

def mrf_carbon_transport_cost(suppliers, origin):
    
    mrf_distance = shortest_ditance_calculator_input(suppliers, 'MRF', origin, 1)
    mrf_cost = mrf_distance * 0.85

    return mrf_cost

def mrf_to_reproccessor_carbon_transport_cost(suppliers, origin):
    
    mrf_distance = shortest_ditance_calculator_input2(suppliers, 'MRF', origin, 1)
    mrf_cost = mrf_distance * 0.85

    return mrf_cost

def divert_carbon_transport_cost(suppliers, origin):
    
    divert_distance = shortest_ditance_calculator_charity_input(suppliers, 'Charity', origin, 1)
    divert_cost = divert_distance * 0.85
    
    return divert_cost

def transport_carbon_cost_calculator_input(project, sites, suppliers):
    
    postcode = sites['site_postcode'][sites['project_title'] == project].to_list()[0]
    
    sites_list = list(sites.project_title)
    print('Site: {} \nPostcode: {} \n'.format(project, postcode))
    if project in sites_list:
        print('Landfill Transport Carbon: {} \n'.format(landfill_carbon_transport_cost(suppliers, postcode)))  
            
        print('MRF Transport Carbon: {} \n'.format(mrf_carbon_transport_cost(suppliers, postcode)))
            
        print('MRF to Reproccessor Transport Carbon: {}'.format(mrf_to_reproccessor_carbon_transport_cost(suppliers, postcode)*1.2))
            
        #df['divert_transport_carbon'].loc[i] = divert_carbon_transport_cost(suppliers, postcode)
                  

def reuse_offset_calculator(divert_output, reuse_offset):
    for i, row in divert_output.iterrows():
        mat = divert_output['waste_stream'].loc[i]
        g=reuse_offset.index
        g=g.to_list()
        if mat in g:
            divert_output['reuse_offset'].loc[i] = divert_output.tonnage.loc[i] * reuse_offset.loc[f'{mat}', 'Emission Factor (kg CO2 equivalents/ tonne)']
            
def recycle_offset_calculator(divert_output, recycle_offset):
    for i, row in divert_output.iterrows():
        mat = divert_output['waste_stream'].loc[i]
        g=recycle_offset.index
        g=g.to_list()
        if mat in g:
            divert_output['recycling_offset'].loc[i] = divert_output.tonnage.loc[i] * recycle_offset.loc[f'{mat}', 'Emission Factor (kg CO2 equivalents/ tonne or sq m)']
        else:
            divert_output['recycle_offset'][i] = (divert_output['reuse_offset'][i] * 0.85)
            

def equivalency_calculator(carbon_offset, carbon_equivalencies):
    for i, row in carbon_equivalencies.iterrows():
        print(carbon_equivalencies.equivalency[i], ':', math.floor(carbon_offset/carbon_equivalencies['emission factor (kg co2 equivalents/ tonne)'][i]))
        
        
def numeric_distance(origin, destination):
    try:
        values = google_maps_distance(destination, origin)
        if not values:
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
        return 0.0
