"""Stable identity for the exact projection returned to the interface."""
import hashlib
import json
from django.core.serializers.json import DjangoJSONEncoder

CALCULATION_VERSION = 'financial-engine-v1'


def projection_version(data):
    content = {key: value for key, value in data.items() if key not in ('projection_version', 'generated_at')}
    encoded = json.dumps({'engine': CALCULATION_VERSION, 'projection': content}, cls=DjangoJSONEncoder, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode()).hexdigest()
