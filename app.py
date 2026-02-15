#----------------------------------------------------------------------------#
# Imports
#----------------------------------------------------------------------------#
import sys
import json
import dateutil.parser
import babel
from flask import Flask, render_template, request, Response, flash, redirect, url_for, session
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy
import logging
from logging import Formatter, FileHandler
from flask_wtf import Form
from forms import *
from sqlalchemy import func
from flask_migrate import Migrate
import numpy as np
import pandas as pd
#----------------------------------------------------------------------------#
# App Config.
#----------------------------------------------------------------------------#


app = Flask(__name__)
moment = Moment(app)
app.config.from_object('config')
db = SQLAlchemy(app)


migrate = Migrate(app, db)

# TODO: connect to a local postgresql database

#----------------------------------------------------------------------------#
# Models.
#----------------------------------------------------------------------------#
class output(db.Model):
    __tablename__ = 'output'

    id = db.Column(db.Integer, primary_key=True)
    material = db.Column(db.String)
    amount = db.Column(db.Float)
    unit = db.Column(db.String(120))
    site_address = db.Column(db.String(120))
    traditional_address = db.Column(db.String(120))
    divert_address = db.Column(db.String(120))
    traditional_cost = db.Column(db.Float)
    divert_cost = db.Column(db.Float)

    # TODO: implement any missing fields, as a database migration using Flask-Migrate
    def __repr__(self):
        return '<Output {}>'.format(self.name)


@app.route('/')
def index():
    return redirect('/output')


@app.route('/output', methods=['GET'])
def create_venue_form():
    form = OutputForm()
    return render_template('calculator.html', form=form)

@app.route('/output', methods=['POST'])
def create_venue_submission():
    # TODO: insert form data as a new Venue record in the db, instead
    # TODO: modify data to be the data object returned from db insertion
    error=False
    try:
        material = request.form['material']
        amount = request.form['city']
        unit = request.form['state']
        site_address = request.form['address']
        traditional_address = request.form['phone']
        divert_address = request.form['image_link']

        output = output(material=material, amount=amount, unit=unit, site_address=site_address, traditional_address=traditional_address, divert_address=divert_address)
        db.session.add(output)
        db.session.commit()
    
    except:
        error=True
        db.session.rollback()
        print(sys.exc_info())

    finally:
        db.session.close()
    
    if error:
        flash('An error occurred. Output for ' + request.form['material']+ ' could not be calculated.')

    if not error:
        flash('Output for ' + request.form['material'] + ' was successfully listed.')
    
    return render_template('output.html')


def func(material, amount, unit, site_adderss, traditional_address, divert_address, traditional_cost, divert_cost):
    mrf_transport_carbon  = numeric_distance(traditional_address, site_address) * 0.85
    landfill_transport_carbon = mrf_transport_carbon * 1.2
    landfill_monetary_cost = (divert_output.tonnage * 100) + 114
    mrf_to_reprocessor_cost = traditional_cost
    mrf_to_reprocessor_transport_carbon = mrf_transport_carbon * 1.2
    divert_transport_carbon  = numeric_distance(divert_address, site_address) * 0.85

    g=reuse_offset.index
    g=g.to_list()
    error=False
    if mat in g:
        reuse_embodied_carbon = amount * reuse_offset.loc[f'{material}', 'Emission Factor (kg CO2 equivalents/ tonne)']
    else:
        error=True
  
    if mat in g:
        recycle_embodied_carbon = amount * recycle_offset.loc[f'{material}', 'Emission Factor (kg CO2 equivalents/ tonne or sq m)']
    else:
        recycle_embodied_carbon = (divert_output['reuse_offset'][i] * 0.85)
        
    if error:
        flash('Error.')
        
    if not error:
        flask('Done.')
        
@app.route('/output')
def show_output():
  output_query = db.session.query(output).order_by(output.id.desc()).first()

  if not output_query: 
    return render_template('errors/404.html')

  func(output_query.material, output_query.amount, output_query.unit, output_query.site_adderss, output_query.traditional_address, output_query.divert_address, output_query.traditional_cost, output_query.divert_cost)
        
  data = {
    "mrf_transport_carbon": mrf_transport_carbon,
    "landfill_transport_carbon": landfill_transport_carbon,
    "landfill_monetary_cost ": landfill_monetary_cost,
    "mrf_to_reprocessor_cost": mrf_to_reprocessor_cost,
    "mrf_to_reprocessor_transport_carbon": mrf_to_reprocessor_transport_carbon,
    "divert_transport_carbon": divert_transport_carbon,
    "reuse_embodied_carbon": reuse_embodied_carbon,
    "recycle_embodied_carbon": recycle_embodied_carbon
  }

  return render_template('show_output.html', output=data)
