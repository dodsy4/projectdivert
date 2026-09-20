"""Web routes."""

import requests
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func
import project_divert_lca
from werkzeug.security import check_password_hash, generate_password_hash
from flask_login import current_user, login_required, login_user, logout_user
from forms import CharityForm1, CharityForm2, CharityForm3, CharityForm4, CharityForm5, FilterForm, MaterialForm, OutputForm, RequestForm, WasteRemovalRequestForm
from projectdivert.extensions import db
from projectdivert.models.catalog import DiversionEstimate, Material, MaterialRequest
from projectdivert.models.charity import Charity
from projectdivert.models.user import User
from projectdivert.services.geo import PostcodeLookupUnavailable
from projectdivert.services.lca_glue import assess_diversion_estimate
from projectdivert.services.uploads import MAX_MATERIAL_IMAGES, _decode_material_images, _encode_material_images, _save_material_images, _serialize_material
from projectdivert.services.waste_requests import WasteRequestError, create_waste_request
from projectdivert.services.utils import _require_form_fields, _require_positive_number, utcnow
from projectdivert.services import notifications

bp = Blueprint('web', __name__)


#----------------------------------------------------------------------------#
# Controllers.
#----------------------------------------------------------------------------#
@bp.route('/first', methods=['GET'])
def first_get():
    form = FilterForm()
    return render_template('forms/first.html', form=form)



@bp.route('/first', methods=['POST'])
def first_post():
    postcode = request.form.get('postcode', '').strip()
    radius = request.form.get('radius', '').strip()
    if not postcode or not radius:
        flash('Please provide both postcode and radius.')
        return redirect('/first')
    return redirect(f"/materials?postcode={postcode}&radius={radius}")



@bp.route('/map')
def map():
    postcode = request.args.get('postcode', '').strip()
    radius_raw = request.args.get('radius', '').strip()
    filter_applied = False

    materials_query = Material.query.filter(Material.latitude.isnot(None), Material.longitude.isnot(None))
    materials_with_coords = materials_query.all()

    if postcode and radius_raw:
        try:
            radius_miles = int(radius_raw)
            if radius_miles <= 0:
                raise ValueError
            endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
            resp = requests.get(endpoint, timeout=10)
            payload = resp.json()
            result = payload.get('result')
            if not result:
                raise ValueError

            target_long = result.get('longitude')
            target_lat = result.get('latitude')
            radius_km = radius_miles * 1.60934
            materials_with_coords = materials_query.filter(
                func.acos(
                    func.sin(func.radians(target_lat)) * func.sin(func.radians(Material.latitude))
                    + func.cos(func.radians(target_lat))
                    * func.cos(func.radians(Material.latitude))
                    * func.cos(func.radians(Material.longitude) - (func.radians(target_long)))
                )
                * 6371
                <= radius_km
            ).all()
            filter_applied = True
        except Exception:
            flash('Could not apply postcode/radius map filter. Showing all mapped materials.')

    markers = []
    for material in materials_with_coords:
        image_links = _decode_material_images(material.image_link1, material.image_link2, material.image_link3)
        markers.append(
            {
                "id": material.id,
                "material": material.waste_stream,
                "amount": material.amount,
                "city": material.city,
                "county": material.county,
                "postcode": material.postcode,
                "lat": material.latitude,
                "lng": material.longitude,
                "preview_image": image_links[0] if image_links else '',
            }
        )
    return render_template(
        'pages/map.html',
        markers=markers,
        google_maps_api_key=current_app.config.get('GOOGLE_MAPS_API_KEY') or '',
        filter_postcode=postcode,
        filter_radius=radius_raw,
        filter_applied=filter_applied,
    )



@bp.route('/')
def index():
    return redirect('/materials')



@bp.route('/home')
def home():
    return render_template('pages/home.html')



@bp.route('/login', methods=['GET', 'POST'])
def login_page():
    setup_form = CharityForm1()

    if current_user.is_authenticated:
        return redirect('/materials')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash('Please enter both email and password.')
            return render_template('pages/login.html', form=setup_form), 400

        user = User.query.filter(func.lower(User.email) == email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid email or password.')
            return render_template('pages/login.html', form=setup_form), 401

        login_user(user)
        flash('Logged in successfully.')
        next_url = request.args.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('/materials')

    return render_template('pages/login.html', form=setup_form)



@bp.route('/register', methods=['GET', 'POST'])
def register_page():
    if current_user.is_authenticated:
        return redirect('/materials')

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not name or not email or not password:
            flash('Please complete all required fields.')
            return render_template('pages/register.html'), 400
        if password != confirm_password:
            flash('Passwords do not match.')
            return render_template('pages/register.html'), 400
        if len(password) < 8:
            flash('Password must be at least 8 characters.')
            return render_template('pages/register.html'), 400
        if User.query.filter(func.lower(User.email) == email).first():
            flash('An account with that email already exists.')
            return render_template('pages/register.html'), 409

        try:
            user = User(
                name=name[:120],
                email=email,
                password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
                role='customer',
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Account created successfully.')
            return redirect('/materials')
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Registration failed.')
            flash('Could not create account right now.')
            return render_template('pages/register.html'), 500

    return render_template('pages/register.html')



@bp.route('/logout', methods=['POST'])
@login_required
def logout_page():
    logout_user()
    flash('You have been logged out.')
    return redirect('/materials')



@bp.route('/output', methods=['GET'])
def create_output_form():
    form = OutputForm()
    return render_template('forms/calculator.html', form=form)



@bp.route('/output', methods=['POST'])
def create_output_submission():
    error=False
    try:
        form = _require_form_fields(
            request.form,
            [
                'material',
                'amount',
                'unit',
                'site_address',
                'traditional_address',
                'divert_address',
                'traditional_cost',
                'divert_cost',
            ],
        )

        material = form['material']
        if material == 'Other':
            custom_material = request.form.get('custom_output_material', '').strip()
            if not custom_material:
                raise ValueError('Please enter a material when selecting Other.')
            material = custom_material[:120]
        amount = _require_positive_number(form['amount'], 'amount')
        unit = form['unit']
        site_address = form['site_address']
        traditional_address = form['traditional_address']
        divert_address = form['divert_address']
        traditional_cost = _require_positive_number(form['traditional_cost'], 'traditional cost', allow_zero=True)
        divert_cost = _require_positive_number(form['divert_cost'], 'divert cost', allow_zero=True)

        estimate = DiversionEstimate(
            material=material,
            amount=amount,
            unit=unit,
            site_address=site_address,
            traditional_address=traditional_address,
            divert_address=divert_address,
            traditional_cost=traditional_cost,
            divert_cost=divert_cost,
        )
        db.session.add(estimate)
        db.session.commit()
    
    except ValueError as exc:
        error=True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error=True
        db.session.rollback()
        current_app.logger.exception('Output submission failed.')

    finally:
        db.session.close()
    
    if error:
        flash('An error occurred. Output for ' + request.form.get('material', 'material')+ ' could not be calculated.')

    if not error:
        flash('Output for ' + material + ' was successfully listed.')
    
    return redirect("/result")



@bp.route('/result')
def show_output():
    estimate = db.session.query(DiversionEstimate).order_by(DiversionEstimate.id.desc()).first()
    if not estimate:
        return render_template('errors/404.html')

    try:
        result = assess_diversion_estimate(estimate)
    except (ValueError, project_divert_lca.LcaDataError) as exc:
        flash(str(exc))
        return redirect('/output')

    return render_template('pages/output.html', output=result)


def _create_account_submission(account_type):
    error = False
    try:
        form = request.form
        selected_type = form.get('account_type', '').strip()
        if selected_type == 'Other':
            selected_type = (
                form.get('other_description', '').strip()
                or form.get('other_type', '').strip()
                or form.get('other', '').strip()
                or 'Other'
            )
            selected_type = selected_type[:120]
        if not selected_type:
            selected_type = account_type
        if not selected_type:
            selected_type = 'Charity'

        charity = Charity(
            name=form.get('name'),
            type=selected_type,
            email=form.get('email'),
            reg_num=form.get('reg_num'),
            address1=form.get('address1'),
            city1=form.get('city1'),
            county1=form.get('county1'),
            postcode1=form.get('postcode1'),
            address2=form.get('address2'),
            city2=form.get('city2'),
            county2=form.get('county2'),
            postcode2=form.get('postcode2'),
            address3=form.get('address3'),
            city3=form.get('city3'),
            county3=form.get('county3'),
            postcode3=form.get('postcode3'),
            phone=form.get('phone'),
            facebook_link=form.get('facebook_link'),
            website=form.get('website'),
        )
        db.session.add(charity)
        db.session.commit()
    except Exception:
        error = True
        db.session.rollback()
        current_app.logger.exception('Account submission failed.')
    finally:
        db.session.close()

    if error:
        flash('Error. Account was not uploaded.')
    else:
        flash('Account was successfully uploaded.')

    return redirect('/first')



@bp.route('/submitdetails1', methods=['GET'])
@bp.route('/submit_details1', methods=['GET'])
def create_account_form1():
    form = CharityForm1()
    return render_template('forms/new_account.html', form=form)



@bp.route('/submit_details1', methods=['POST'])
def create_account_submission1():
    return _create_account_submission('Charity')



@bp.route('/submit_details2', methods=['GET'])
def create_account_form2():
    form = CharityForm2()
    return render_template('forms/new_account.html', form=form)



@bp.route('/submit_details2', methods=['POST'])
def create_account_submission2():
    return _create_account_submission('Community Group')



@bp.route('/submit_details3', methods=['GET'])
def create_account_form3():
    form = CharityForm3()
    return render_template('forms/new_account.html', form=form)



@bp.route('/submit_details3', methods=['POST'])
def create_account_submission3():
    return _create_account_submission('Education')



@bp.route('/submit_details4', methods=['GET'])
def create_account_form4():
    form = CharityForm4()
    return render_template('forms/new_account.html', form=form)



@bp.route('/submit_details4', methods=['POST'])
def create_account_submission4():
    return _create_account_submission('Social Enterprise')



@bp.route('/submit_details5', methods=['GET'])
def create_account_form5():
    form = CharityForm5()
    return render_template('forms/new_account_other.html', form=form)



@bp.route('/submit_details5', methods=['POST'])
def create_account_submission5():
    return _create_account_submission(request.form.get('other'))


#----------------------------------------------------------------------------#
# Materials Dashboard
#----------------------------------------------------------------------------#
@bp.route('/material_input', methods=['GET'])
def create_material_form():
    form = MaterialForm()
    return render_template('forms/new_material.html', form=form)



@bp.route('/material_input', methods=['POST'])
def create_material_submission():
    
    error=False
    try:
        form = _require_form_fields(
            request.form,
            ['waste_stream', 'amount', 'county', 'postcode'],
        )

        waste_stream = form['waste_stream']
        if waste_stream == 'Other':
            custom_waste_stream = request.form.get('custom_waste_stream', '').strip()
            if not custom_waste_stream:
                raise ValueError('Please enter a custom material type when selecting Other.')
            waste_stream = custom_waste_stream[:120]
        amount = form['amount']
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        county = form['county']
        postcode = form['postcode']
        endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
        response = requests.get(endpoint, timeout=10)
        payload = response.json()
        result = payload.get('result') if isinstance(payload, dict) else None
        if not result:
            raise ValueError('Please enter a valid postcode.')
        longitude = result.get('longitude')
        latitude = result.get('latitude')
        if longitude is None or latitude is None:
            raise ValueError('Please enter a valid postcode.')
        dimensions = request.form.get('dimensions', '').strip()
        condition = request.form.get('condition', '').strip()
        uploaded_images = request.files.getlist('image_files')
        if uploaded_images:
            image_refs = _save_material_images(uploaded_images, limit=MAX_MATERIAL_IMAGES)
        else:
            image_refs = [
                request.form.get('image_link1', '').strip(),
                request.form.get('image_link2', '').strip(),
                request.form.get('image_link3', '').strip(),
            ]

        image_link1, image_link2, image_link3 = _encode_material_images(image_refs)


        material_listing = Material(
            waste_stream=waste_stream, amount=amount, address=address, city=city, county=county,
            postcode=postcode, dimensions=dimensions, condition=condition,
            image_link1=image_link1, image_link2=image_link2, image_link3=image_link3,
            longitude=longitude, latitude=latitude)

        db.session.add(material_listing)
        db.session.commit()
    
    except ValueError as exc:
        error=True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error=True
        db.session.rollback()
        current_app.logger.exception('Material submission failed.')

    finally:
        db.session.close()
    
    if error:
        flash('Error. Material was not uploaded.')

    if not error:
        flash('Material was successfully uploaded.')
        
    return redirect('/materials')



@bp.route('/materials')
def materials():
    search_term = request.args.get('search_term', '').strip()
    postcode = request.args.get('postcode', '').strip()
    radius_raw = request.args.get('radius', '').strip()
    filter_applied = False
    materials_data = []
    base_query = Material.query

    if search_term:
        base_query = base_query.filter(Material.waste_stream.ilike(f'%{search_term}%'))
        filter_applied = True

    if postcode and radius_raw:
        try:
            radius_miles = int(radius_raw)
            if radius_miles <= 0:
                raise ValueError
            endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
            resp = requests.get(endpoint, timeout=10)
            payload = resp.json()
            result = payload.get('result')
            if not result:
                raise ValueError

            target_long = result.get('longitude')
            target_lat = result.get('latitude')
            radius_km = radius_miles * 1.60934
            filtered_materials = base_query.filter(
                func.acos(
                    func.sin(func.radians(target_lat)) * func.sin(func.radians(Material.latitude))
                    + func.cos(func.radians(target_lat))
                    * func.cos(func.radians(Material.latitude))
                    * func.cos(func.radians(Material.longitude) - (func.radians(target_long)))
                )
                * 6371
                <= radius_km
            ).all()
            materials_data = [_serialize_material(material) for material in filtered_materials]
            filter_applied = True
        except Exception:
            flash('Could not apply postcode/radius filter. Showing all materials.')

    if not filter_applied:
        all_materials = base_query.all()
        materials_data = [_serialize_material(material) for material in all_materials]

    return render_template(
        'pages/materials.html',
        materials=materials_data,
        search_term=search_term,
        filter_postcode=postcode,
        filter_radius=radius_raw,
        filter_applied=filter_applied,
    )



@bp.route('/materials/search', methods=['POST'])
def search_materials():

    search_term = request.form.get('search_term', '')
    search_result = db.session.query(Material).filter(Material.waste_stream.ilike(f'%{search_term}%')).all()
    data = []

    for result in search_result:
        data.append({
            "id": result.id,
            "name": result.waste_stream,
        })
  
    response={
        "count": len(search_result),
        "data": data
    }
  
    return render_template('pages/search_materials.html', results=response, search_term=request.form.get('search_term', ''))



@bp.route('/materials/<int:material_id>')
def show_material(material_id):
  
    material = Material.query.get(material_id)

    if not material:
        return render_template('errors/404.html')

    data = {
        "id": material.id,
        "material": material.waste_stream,
        "amount": material.amount,
        "city": material.city,
        "county": material.county,
        "address": material.address,
        "dimensions": material.dimensions,
        "condition": material.condition,
        "image_link1": material.image_link1,
        "image_link2": material.image_link2,
        "image_link3": material.image_link3,
        "image_links": _decode_material_images(material.image_link1, material.image_link2, material.image_link3),
    }

    return render_template('pages/show_material.html', material=data)



@bp.route('/materials_filtered/<string:location_id>')
def show_site_material(location_id):
    all_areas = Material.query.filter(Material.city == location_id)
    all_areas = Material.query.with_entities(func.count(Material.id), Material.city, Material.county).group_by(Material.city, Material.county).all()
    data = []

    for area in all_areas:
        if area.city == location_id:
            area_projects = Material.query.filter_by(county=area.county).filter_by(city=area.city).all()
        
            project_data = []
        
            for material in area_projects:
                project_data.append({
                    "id": material.id,
                    "material": material.waste_stream, 
                    "amount": material.amount,
                    "condition": material.condition,
                    "postcode": material.postcode,
                    })
        
        
            data.append({
                "city": area.city,
                "county": area.county, 
                "materials": project_data
                })

    
    return render_template('pages/materials.html', areas=data)


#  Create Request
#  ----------------------------------------------------------------
@bp.route('/material/<int:mat_id>/request', methods=['GET'])
def create_material_request(mat_id):
    form = RequestForm()
    return render_template('forms/new_request.html', form=form)



@bp.route('/material/<int:mat_id>/request', methods=['POST'])
def request_material_form(mat_id):

    error=False
    email_sent = False
    try:
        material = Material.query.get(mat_id)
        if not material:
            return render_template('errors/404.html'), 404

        email = request.form.get('email', '').strip()
        if not email and current_user.is_authenticated:
            email = current_user.email
        if not email:
            raise ValueError('Requester email is required.')

        message = request.form['message']
        
        qui = MaterialRequest(mat_id=mat_id, e_id=email, message=message)
        db.session.add(qui)
        db.session.commit()

        company_email = (current_app.config.get('REQUEST_NOTIFICATION_EMAIL') or '').strip()
        if company_email:
            base_url = (current_app.config.get('APP_BASE_URL') or request.url_root.rstrip('/')).rstrip('/')
            listing_url = '{}{}'.format(base_url, url_for('web.show_material', material_id=mat_id))
            subject = 'New material request: {}'.format(material.waste_stream or 'Material')
            body = (
                'You received a new material request.\n\n'
                'Material: {material}\n'
                'Material ID: {mat_id}\n'
                'Requester Email: {email}\n'
                'Message: {message}\n'
                'Listing URL: {listing_url}\n'
            ).format(
                material=material.waste_stream or 'Material',
                mat_id=mat_id,
                email=email,
                message=message or '(no message)',
                listing_url=listing_url,
            )
            email_sent = notifications._send_material_request_email(company_email, subject, body)
        else:
            current_app.logger.warning('REQUEST_NOTIFICATION_EMAIL not set; request email notification skipped.')
    
    except ValueError as exc:
        error=True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error=True
        db.session.rollback()
        current_app.logger.exception('Material request submission failed.')

    finally:
        db.session.close()
    
    if error:
        flash('Error. Request was not sent.')

    if not error:
        if email_sent:
            flash('Request sent and emailed to the company.')
        else:
            flash('Request saved. Email notification is not configured yet.')
        
    return redirect('/materials')



@bp.route('/waste-removal/request', methods=['GET'])
@bp.route('/waste_removal/request', methods=['GET'])
def create_waste_removal_request_form():
    form = WasteRemovalRequestForm()
    if not form.match_radius_miles.data:
        form.match_radius_miles.data = 25
    if current_user.is_authenticated:
        if current_user.name:
            form.requester_name.data = current_user.name
        if current_user.email:
            form.requester_email.data = current_user.email
    # Same clock the submission is validated against, so the form cannot
    # offer a value the server will then reject.
    min_pickup_iso = utcnow().replace(second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M')
    return render_template('forms/waste_removal_request.html', form=form, min_pickup_iso=min_pickup_iso)



def _waste_request_error_message(exc):
    """Turn a service validation error into something to show a person.

    The service phrases errors for the API, in field names; the form has always
    spoken prose, and naming the missing fields is more use here than a bare
    count.
    """
    if exc.fields and str(exc) == 'Missing required field(s)':
        return 'Missing required field(s): {}.'.format(', '.join(exc.fields))
    message = str(exc)
    return message if message.endswith('.') else '{}.'.format(message)


def _waste_removal_notification_body(created):
    """The plain-text email sent to the team for a new request."""
    booking = created.booking
    closest = created.closest_candidate
    return (
        'A new waste removal request was submitted.\n\n'
        'Request ID: {request_id}\n'
        'Requester Name: {requester_name}\n'
        'Requester Email: {requester_email}\n'
        'Material Type: {material_type}\n'
        'Waste Amount: {waste_amount} {waste_unit}\n'
        'Pickup Address: {pickup_address}\n'
        'Pickup City: {pickup_city}\n'
        'Pickup County: {pickup_county}\n'
        'Pickup Postcode: {pickup_postcode}\n'
        'Scheduled Pickup: {scheduled_pickup}\n'
        'Match Radius (miles): {match_radius_miles}\n'
        'Dispatch Offers Created: {offers_created}\n'
        'Closest Provider Candidate: {closest_provider}\n'
        'Provider Notifications Sent: {provider_notifications_sent}\n'
        'Estimated Drive Time: {drive_time}\n'
        'Notes: {notes}\n'
        'Status: {status}\n'
    ).format(
        request_id=booking.id,
        requester_name=booking.requester_name,
        requester_email=booking.requester_email,
        material_type=booking.material_type,
        waste_amount=booking.waste_amount,
        waste_unit=booking.waste_unit,
        pickup_address=booking.pickup_address,
        pickup_city=booking.pickup_city or '(not provided)',
        pickup_county=booking.pickup_county or '(not provided)',
        pickup_postcode=booking.pickup_postcode,
        scheduled_pickup=booking.scheduled_pickup_at.strftime('%Y-%m-%d %H:%M'),
        match_radius_miles=created.match_radius_miles,
        offers_created=created.offers_created,
        closest_provider=(
            '{} ({} miles)'.format(closest['provider_name'], closest['distance_miles'])
            if closest else 'No provider found within radius'
        ),
        provider_notifications_sent=created.provider_notifications_sent,
        drive_time=(
            created.drive_time['text'] if created.drive_time
            else ('Unable to calculate (Google Maps API unavailable)' if closest else 'N/A')
        ),
        notes=booking.notes or '(none)',
        status=booking.status,
    )


@bp.route('/waste-removal/request', methods=['POST'])
@bp.route('/waste_removal/request', methods=['POST'])
def create_waste_removal_request_submission():
    error = False
    email_sent = False
    email_configured = False
    created = None
    try:
        created = create_waste_request(dict(request.form))

        notification_email = (current_app.config.get('WASTE_REMOVAL_NOTIFICATION_EMAIL') or '').strip()
        email_configured = bool(notification_email)
        if notification_email:
            email_sent = notifications._send_material_request_email(
                notification_email,
                'New waste removal request: {}'.format(created.booking.material_type),
                _waste_removal_notification_body(created),
            )
        else:
            current_app.logger.warning(
                'WASTE_REMOVAL_NOTIFICATION_EMAIL not set; waste removal email notification skipped.'
            )
    except WasteRequestError as exc:
        error = True
        db.session.rollback()
        flash(_waste_request_error_message(exc))
    except PostcodeLookupUnavailable as exc:
        # Say it is the service and not their postcode, so they retry rather
        # than re-checking a postcode that was correct all along.
        error = True
        db.session.rollback()
        flash('{} Please try again in a moment.'.format(exc))
    except ValueError as exc:
        error = True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error = True
        db.session.rollback()
        current_app.logger.exception('Waste removal request submission failed.')
    finally:
        db.session.close()

    if error:
        flash('Waste removal request could not be submitted.')
    else:
        if created.offers_created:
            flash(
                'Waste removal request submitted. Notified {} closest providers; awaiting first acceptance.'.format(
                    created.offers_created,
                )
            )
        else:
            flash(
                'Waste removal request submitted. No provider found within {} miles yet.'.format(
                    round(created.match_radius_miles or 0, 2),
                )
            )
        if created.provider_notifications_sent:
            flash('Provider notifications sent: {}.'.format(created.provider_notifications_sent))
        if email_sent:
            flash('Request details emailed to the team.')
        elif email_configured:
            flash('Request saved but email delivery failed.')
        else:
            flash('Request saved. Email notification is not configured yet.')

    return redirect('/waste-removal/request')
