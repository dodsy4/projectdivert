"""Image and compliance file storage (local disk or S3)."""

import os
import uuid
try:
    import boto3
except Exception:  # pragma: no cover - optional dependency
    boto3 = None
from flask import current_app, request, url_for
from werkzeug.utils import secure_filename
import logging

logger = logging.getLogger(__name__)


ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}


MAX_MATERIAL_IMAGES = 10


ALLOWED_COMPLIANCE_UPLOAD_EXTENSIONS = {
    '.pdf',
    '.png',
    '.jpg',
    '.jpeg',
    '.webp',
    '.heic',
    '.heif',
}


COMPLIANCE_IMAGE_UPLOAD_EXTENSIONS = {
    '.png',
    '.jpg',
    '.jpeg',
    '.webp',
    '.heic',
    '.heif',
}


def normalize_image_filename(image_ref):
    value = str(image_ref or '').strip()
    if not value:
        return ''
    basename = os.path.basename(value)
    if '.' in basename:
        return basename
    return basename + '.png'


def _save_material_image(uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        return ''

    original_name = secure_filename(uploaded_file.filename)
    _stem, ext = os.path.splitext(original_name)
    ext = ext.lower()

    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError('Only PNG, JPG, JPEG, and WEBP images are supported.')

    unique_name = '{}{}'.format(uuid.uuid4().hex[:12], ext)
    target_dir = os.path.join(current_app.static_folder, 'img')
    os.makedirs(target_dir, exist_ok=True)
    uploaded_file.save(os.path.join(target_dir, unique_name))
    return unique_name


def _save_material_images(uploaded_files, limit=MAX_MATERIAL_IMAGES):
    saved = []
    for uploaded_file in uploaded_files[:limit]:
        saved_name = _save_material_image(uploaded_file)
        if saved_name:
            saved.append(saved_name)
    return saved


def _compliance_upload_root():
    configured = current_app.config.get('COMPLIANCE_UPLOAD_DIR') or os.path.join(
        'static',
        'uploads',
        'compliance',
    )
    if os.path.isabs(configured):
        return configured
    return os.path.join(current_app.root_path, configured)


def _compliance_storage_backend():
    backend = str(current_app.config.get('COMPLIANCE_STORAGE_BACKEND') or 'local').strip().lower()
    return backend or 'local'


def _compliance_s3_client():
    if boto3 is None:
        raise RuntimeError('boto3 dependency is not installed')

    kwargs = {}
    region = str(current_app.config.get('COMPLIANCE_S3_REGION') or '').strip()
    endpoint_url = str(current_app.config.get('COMPLIANCE_S3_ENDPOINT_URL') or '').strip()
    access_key_id = str(current_app.config.get('COMPLIANCE_S3_ACCESS_KEY_ID') or '').strip()
    secret_access_key = str(current_app.config.get('COMPLIANCE_S3_SECRET_ACCESS_KEY') or '').strip()

    if region:
        kwargs['region_name'] = region
    if endpoint_url:
        kwargs['endpoint_url'] = endpoint_url
    if access_key_id:
        kwargs['aws_access_key_id'] = access_key_id
    if secret_access_key:
        kwargs['aws_secret_access_key'] = secret_access_key

    return boto3.client('s3', **kwargs)


def _coerce_compliance_upload_extension(original_name, mimetype):
    original_name = secure_filename(original_name or '')
    _stem, ext = os.path.splitext(original_name)
    ext = ext.lower()
    if ext:
        return ext

    mimetype = str(mimetype or '').strip().lower()
    mapping = {
        'application/pdf': '.pdf',
        'image/png': '.png',
        'image/jpeg': '.jpg',
        'image/webp': '.webp',
        'image/heic': '.heic',
        'image/heif': '.heif',
    }
    return mapping.get(mimetype, '')


def _build_compliance_storage_key(request_id, document_type, ext):
    unique_name = '{}-{}{}'.format(document_type, uuid.uuid4().hex[:16], ext)
    backend = _compliance_storage_backend()
    if backend == 's3':
        prefix = str(current_app.config.get('COMPLIANCE_S3_PREFIX') or 'compliance').strip().strip('/')
        parts = [prefix] if prefix else []
        parts.extend(['request-{}'.format(request_id), unique_name])
        return '/'.join(parts)
    return os.path.join('uploads', 'compliance', 'request-{}'.format(request_id), unique_name).replace(
        os.sep, '/'
    )


def _build_compliance_s3_public_url(storage_key):
    public_base = str(current_app.config.get('COMPLIANCE_S3_PUBLIC_BASE_URL') or '').strip().rstrip('/')
    if public_base:
        return '{}/{}'.format(public_base, storage_key)

    bucket = str(current_app.config.get('COMPLIANCE_S3_BUCKET') or '').strip()
    endpoint_url = str(current_app.config.get('COMPLIANCE_S3_ENDPOINT_URL') or '').strip().rstrip('/')
    region = str(current_app.config.get('COMPLIANCE_S3_REGION') or '').strip()

    if endpoint_url and bucket:
        return '{}/{}/{}'.format(endpoint_url, bucket, storage_key)
    if bucket and region and region != 'us-east-1':
        return 'https://{}.s3.{}.amazonaws.com/{}'.format(bucket, region, storage_key)
    if bucket:
        return 'https://{}.s3.amazonaws.com/{}'.format(bucket, storage_key)
    return storage_key


def _build_compliance_signed_upload(request_id, document_type, original_name, mimetype):
    bucket = str(current_app.config.get('COMPLIANCE_S3_BUCKET') or '').strip()
    if not bucket:
        raise RuntimeError('COMPLIANCE_S3_BUCKET is not configured')

    ext = _coerce_compliance_upload_extension(original_name, mimetype)
    if ext not in ALLOWED_COMPLIANCE_UPLOAD_EXTENSIONS:
        raise ValueError(
            'Only PDF, PNG, JPG, JPEG, WEBP, HEIC, and HEIF files are supported.'
        )
    if (
        document_type == 'proof_of_collection_photo'
        and ext not in COMPLIANCE_IMAGE_UPLOAD_EXTENSIONS
    ):
        raise ValueError('Proof-of-collection uploads must be image files.')

    sanitized_name = secure_filename(original_name or '')
    storage_key = _build_compliance_storage_key(request_id, document_type, ext)
    content_type = str(mimetype or '').strip() or 'application/octet-stream'
    expires_in = int(current_app.config.get('COMPLIANCE_S3_PRESIGN_EXP_SECONDS') or 900)
    client = _compliance_s3_client()
    upload_url = client.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': bucket,
            'Key': storage_key,
            'ContentType': content_type,
        },
        ExpiresIn=expires_in,
        HttpMethod='PUT',
    )

    return {
        'backend': 's3',
        'method': 'PUT',
        'upload_url': upload_url,
        'headers': {
            'Content-Type': content_type,
        },
        'expires_in_seconds': expires_in,
        'upload': {
            'backend': 's3',
            'file_url': _build_compliance_s3_public_url(storage_key),
            'storage_key': storage_key,
            'static_path': None,
            'original_filename': sanitized_name or '{}{}'.format(document_type, ext),
            'content_type': content_type,
        },
    }


def _save_compliance_upload_local(uploaded_file, request_id, document_type, ext, original_name):
    storage_key = _build_compliance_storage_key(request_id, document_type, ext)
    target_dir = os.path.join(_compliance_upload_root(), 'request-{}'.format(request_id))
    os.makedirs(target_dir, exist_ok=True)

    absolute_path = os.path.join(current_app.static_folder, storage_key.replace('uploads/', 'uploads/', 1))
    absolute_dir = os.path.dirname(absolute_path)
    os.makedirs(absolute_dir, exist_ok=True)
    uploaded_file.save(absolute_path)
    size_bytes = os.path.getsize(absolute_path)

    return {
        'backend': 'local',
        'file_url': url_for('static', filename=storage_key, _external=True),
        'storage_key': storage_key,
        'static_path': storage_key,
        'original_filename': original_name,
        'content_type': str(uploaded_file.mimetype or '').strip() or None,
        'size_bytes': size_bytes,
    }


def _save_compliance_upload_s3(uploaded_file, request_id, document_type, ext, original_name):
    bucket = str(current_app.config.get('COMPLIANCE_S3_BUCKET') or '').strip()
    if not bucket:
        raise RuntimeError('COMPLIANCE_S3_BUCKET is not configured')

    storage_key = _build_compliance_storage_key(request_id, document_type, ext)
    content_type = str(uploaded_file.mimetype or '').strip() or 'application/octet-stream'
    file_bytes = uploaded_file.read()
    size_bytes = len(file_bytes)

    client = _compliance_s3_client()
    client.put_object(
        Bucket=bucket,
        Key=storage_key,
        Body=file_bytes,
        ContentType=content_type,
        Metadata={
            'request-id': str(request_id),
            'document-type': document_type,
            'original-filename': original_name,
        },
    )

    return {
        'backend': 's3',
        'file_url': _build_compliance_s3_public_url(storage_key),
        'storage_key': storage_key,
        'static_path': None,
        'original_filename': original_name,
        'content_type': content_type,
        'size_bytes': size_bytes,
    }


def _save_compliance_upload(uploaded_file, request_id, document_type):
    if not uploaded_file or not uploaded_file.filename:
        raise ValueError('file is required')

    max_bytes = int(current_app.config.get('COMPLIANCE_UPLOAD_MAX_BYTES') or 0)
    if request.content_length and max_bytes and request.content_length > max_bytes:
        raise ValueError('Uploaded file is too large.')

    original_name = secure_filename(uploaded_file.filename)
    ext = _coerce_compliance_upload_extension(original_name, uploaded_file.mimetype)
    if ext not in ALLOWED_COMPLIANCE_UPLOAD_EXTENSIONS:
        raise ValueError(
            'Only PDF, PNG, JPG, JPEG, WEBP, HEIC, and HEIF files are supported.'
        )
    if (
        document_type == 'proof_of_collection_photo'
        and ext not in COMPLIANCE_IMAGE_UPLOAD_EXTENSIONS
    ):
        raise ValueError('Proof-of-collection uploads must be image files.')

    backend = _compliance_storage_backend()
    if backend == 's3':
        upload_info = _save_compliance_upload_s3(
            uploaded_file,
            request_id,
            document_type,
            ext,
            original_name or '{}{}'.format(document_type, ext),
        )
    else:
        upload_info = _save_compliance_upload_local(
            uploaded_file,
            request_id,
            document_type,
            ext,
            original_name or '{}{}'.format(document_type, ext),
        )

    size_bytes = int(upload_info.get('size_bytes') or 0)
    if max_bytes and size_bytes > max_bytes:
        if upload_info.get('backend') == 'local' and upload_info.get('static_path'):
            absolute_path = os.path.join(current_app.static_folder, upload_info['static_path'])
            try:
                os.remove(absolute_path)
            except OSError:
                logger.warning('Failed removing oversized compliance upload %s.', absolute_path)
        raise ValueError('Uploaded file is too large.')

    return upload_info


def _decode_material_images(image_link1, image_link2, image_link3):
    refs = [
        str(image_link1 or '').strip(),
        str(image_link2 or '').strip(),
        str(image_link3 or '').strip(),
    ]
    if not any(refs):
        return []

    combined = ''.join(refs)
    images = []
    if combined.startswith('multi:'):
        payload = combined[len('multi:'):]
        images = [normalize_image_filename(item) for item in payload.split(',') if item.strip()]
    else:
        images = [normalize_image_filename(item) for item in refs if item]

    return images[:MAX_MATERIAL_IMAGES]


def _encode_material_images(image_refs):
    normalized = [normalize_image_filename(item) for item in image_refs if str(item or '').strip()]
    normalized = normalized[:MAX_MATERIAL_IMAGES]
    if not normalized:
        return '', '', ''

    payload = 'multi:' + ','.join(normalized)
    if len(payload) > 360:
        raise ValueError('Image filenames are too long. Please use fewer images or shorter filenames.')

    part1 = payload[:120]
    part2 = payload[120:240] if len(payload) > 120 else ''
    part3 = payload[240:360] if len(payload) > 240 else ''
    return part1, part2, part3


def _serialize_material(material):
    image_links = _decode_material_images(material.image_link1, material.image_link2, material.image_link3)
    return {
        "id": material.id,
        "material": material.waste_stream,
        "amount": material.amount,
        "condition": material.condition,
        "postcode": material.postcode,
        "image_link1": material.image_link1,
        "image_link2": material.image_link2,
        "image_link3": material.image_link3,
        "image_links": image_links,
    }


def _group_materials(materials):
    grouped = {}
    for material in materials:
        city = material.city if material.city else "Unknown"
        county = material.county if material.county else "Unknown"
        key = (city, county)
        grouped.setdefault(key, []).append(_serialize_material(material))

    data = []
    for city, county in sorted(grouped.keys()):
        data.append(
            {
                "city": city,
                "county": county,
                "materials": grouped[(city, county)],
            }
        )
    return data
