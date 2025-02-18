from contextlib import contextmanager
from itertools import islice, cycle

from django.conf import settings
from django.db import connection, connections, router

try:
    from django.apps import apps, AppConfig
    get_model = apps.get_model
except ImportError:
    from django.db.models.loading import get_model
    AppConfig = None
from django.core import mail


@contextmanager
def schema_context(schema_name, db=None):
    from django.db import connection, connections
    if not db and schema_name == get_public_schema_name():
        db = 'default'
    tenant = get_tenant_model().objects.using('default').get(schema_name=schema_name)
    if not db and tenant.schema_name == get_public_schema_name():
        db = 'default'
    else:
        db = tenant.db_string
    if db:
        connection = connections[db]

    previous_tenant = connection.tenant
    try:
        connection.set_schema(schema_name)
        yield
    finally:
        if previous_tenant is None:
            connection.set_schema_to_public()
        else:
            connection.set_tenant(previous_tenant)


def get_db_string(schema_name):
    if schema_name == get_public_schema_name():
        db_string = 'default'
    else:
        options = [*settings.DATABASES]
        options.remove('default')
        connections['default'].set_schema_to_public()
        try:
            last = get_tenant_model().objects.using('default').exclude(schema_name=get_public_schema_name()).latest('id')
        except:
            last = None
        if not last or last.db_string == 'default':
            db_string = options[0]
        else:
            last_index = options.index(last.db_string)
            starting_at_last_index = islice(cycle(options), last_index + 1, None)
            db_string = next(starting_at_last_index)
    return db_string

@contextmanager
def tenant_context(tenant, db=None):
    from django.db import connection, connections
    if not db and tenant.schema_name == get_public_schema_name():
        db = 'default'
    else:
        db = tenant.db_string
    if db:
        connection = connections[db]

    previous_tenant = connection.tenant
    try:
        connection.set_tenant(tenant)
        yield
    finally:
        if previous_tenant is None:
            connection.set_schema_to_public()
        else:
            connection.set_tenant(previous_tenant)


def get_tenant_model():
    return get_model(*settings.TENANT_MODEL.split("."))


def get_public_schema_name():
    return getattr(settings, 'PUBLIC_SCHEMA_NAME', 'public')


def get_limit_set_calls():
    return getattr(settings, 'TENANT_LIMIT_SET_CALLS', False)


def clean_tenant_url(url_string):
    """
    Removes the TENANT_TOKEN from a particular string
    """
    if hasattr(settings, 'PUBLIC_SCHEMA_URLCONF'):
        if (settings.PUBLIC_SCHEMA_URLCONF and
                url_string.startswith(settings.PUBLIC_SCHEMA_URLCONF)):
            url_string = url_string[len(settings.PUBLIC_SCHEMA_URLCONF):]
    return url_string


def remove_www_and_dev(hostname):
    """
    Legacy function - just in case someone is still using the old name
    """
    return remove_www(hostname)


def remove_www(hostname):
    """
    Removes www. from the beginning of the address. Only for
    routing purposes. www.test.com/login/ and test.com/login/ should
    find the same tenant.
    """
    if hostname.startswith("www."):
        return hostname[4:]

    return hostname


def django_is_in_test_mode():
    """
    I know this is very ugly! I'm looking for more elegant solutions.
    See: http://stackoverflow.com/questions/6957016/detect-django-testing-mode
    """
    return hasattr(mail, 'outbox')


def schema_exists(schema_name, db=None):
    from django.db import connection, connections
    if has_multiple_db() and not db:
        return False
    if db:
        connection = connections[db]
    cursor = connection.cursor()

    # check if this schema already exists in the db
    sql = 'SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE LOWER(nspname) = LOWER(%s))'
    cursor.execute(sql, (schema_name,))

    row = cursor.fetchone()
    if row:
        exists = row[0]
    else:
        exists = False

    cursor.close()

    return exists


def app_labels(apps_list):
    """
    Returns a list of app labels of the given apps_list, now properly handles
     new Django 1.7+ application registry.

    https://docs.djangoproject.com/en/1.8/ref/applications/#django.apps.AppConfig.label
    """
    if AppConfig is None:
        return [app.split('.')[-1] for app in apps_list]
    return [AppConfig.create(app).label for app in apps_list]


class MultipleDBError(Exception):
    """Raised when muliple DB's are defined in settings but not
    specified during usage"""
    pass


def has_multiple_db():
    """
    checks if multile databases are defined in settings
    """
    if len(settings.DATABASES) > 1:
        return True
    return False
