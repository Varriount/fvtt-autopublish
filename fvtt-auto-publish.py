import json
import mechanize
import os
import re
import sys
from getpass import getpass


# Inputs
USERNAME          = os.environ.get("FOUNDRY_USERNAME") or input("Username?")
PASSWORD          = os.environ.get("FOUNDRY_PASSWORD") or getpass("Password?")
PACKAGE_ID        = os.environ.get("FOUNDRY_PACKAGE_ID") or input("Package ID?")
MAX_VERSION_COUNT = 1000

# Constants
ADMIN_URL         = 'foundryvtt.com/admin'
LOGIN_URL         = f'https://{ADMIN_URL}/login/'
MODULE_CONFIG_URL = f'https://{ADMIN_URL}/packages/package/{PACKAGE_ID}/change/'

br = mechanize.Browser()


# ## Login ## #
# Navigate to Foundry home page.
br.open(LOGIN_URL)

# Select and fill out login form.
br.select_form(id = 'login-form')
br['username'] = USERNAME
br['password'] = PASSWORD

# Submit
br.submit()


# ## Configure ## #
# The configuration page represents the forms for each version's fields using
# the pattern "versions-{version_index}-{field_name}".
# We define some helpers here for abstracting over this pattern.
def field_name_for(name, version_index):
    return f'versions-{version_index}-{name}'


def current_value_for(name):
    field_name = field_name_for(
        name          = name,
        version_index = current_version_index
    )
    return br[field_name]


# Navigate to configuration page.
br.open(MODULE_CONFIG_URL)

# Select the published module versions form.
br.select_form(id='package_form')

# Get the number of published module versions.
# The `versions-TOTAL_FORMS` field contains the number of version forms
# that are initially on the page.
# We assume that the number of version forms is equal to the number of
# published versions.
version_count         = int(br['versions-TOTAL_FORMS'])
current_version_index = version_count - 2
new_version_index     = version_count - 1

# Check the boxes of versions that should be removed.
# Note that we have to take into account the fact that we will be publishing
# a new version.
for version_index in range(version_count - MAX_VERSION_COUNT):
    # Setting a checkbox control's value automatically "checks" it.
    field_name = field_name_for(
        name          = 'DELETE',
        version_index = version_index
    )
    br['versions-{version}-DELETE'] = ['on']

# Conveniently, the page comes with a blank set of form controls that
# represent the next version to be published.
# All we have to do is copy information from the fields representing the
# currently published version, then update a subset of the new version's
# fields with new values.
names = [
    # Note, 'id' isn't here as it is supposed to be blank for new entries.
    # 'package',
    'version',
    'manifest',
    'notes',
    'required_core_version',
    'compatible_core_version',
]

for name in names:
    field_name = field_name_for(
        name          = name,
        version_index = new_version_index
    )
    br[field_name] = current_value_for(name)

updated_fields = json.loads(sys.argv[1])
for name, value in updated_fields.items():
    field_name = field_name_for(
        name          = name,
        version_index = new_version_index
    )
    br[field_name] = value

# Submit
res = br.submit()
