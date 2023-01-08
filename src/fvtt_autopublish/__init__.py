__version__ = '0.1.0'

import json
import os
import re
import sys
from getpass import getpass
from typing import Any, Dict, Optional, Mapping, Sequence

import click
from click import Choice, Command, BadParameter
import mechanize
from mechanize import FormNotFoundError


# Constants
MAX_VERSION_COUNT = 1000

ADMIN_URL = 'foundryvtt.com/admin'
LOGIN_URL = f'https://{ADMIN_URL}/login/'
MODULE_CONFIG_URL_FMT = f'https://{ADMIN_URL}/packages/package/{{module_id}}/change/'

PASSWORD_ENV_VARIABLE = "FVTT_PASSWORD"

MANIFEST_KEY_TO_FORM_KEY_MAP = {
    'version': 'version',
    # We don't use manifest here, as the manifest URL in the manifest is not
    # the one we want.
    'changelog': 'notes',
    'minimumCoreVersion': 'required_core_version',
    'compatibleCoreVersion': 'compatible_core_version',
    'compatibility.minimum': 'required_core_version',
    'compatibility.verified': 'compatible_core_version',
}

CLI_KEY_TO_FORM_KEY_MAP = {
    'module_version': 'version',
    'manifest_url': 'manifest',
    'changelog': 'notes',
    'minimum_core_version': ['required_core_version'],
    'compatible_core_version': ['compatible_core_version'],
}

# Extend Help Formatting
class ExtCommand(Command):
    original_write_dl  = click.formatting.HelpFormatter.write_dl
    original_wrap_text = click.formatting.wrap_text

    def extended_write_dl(self, rows, col_max=10, col_spacing=2):
        return ExtCommand.original_write_dl(rows, col_max, col_spacing)

    def extended_wrap_text(
            self, text, width=78, initial_indent="", subsequent_indent="",
            preserve_paragraphs=False
    ):
        result = ExtCommand.original_wrap_text(
            text                = text,
            width               = width,
            initial_indent      = initial_indent,
            subsequent_indent   = subsequent_indent,
            preserve_paragraphs = preserve_paragraphs
        )

        result = re.sub(
            r'\n\n[|]([^|]*?)[|]([^|]*?)[|]',
            lambda m: '\n' + m[1] + m[2].replace('\n', '\n' + m[1]),
            result
        )
        result = result.replace("  [required]", "[required]")
        return result

    def get_help(self, ctx):
        click.formatting.wrap_text = self.extended_wrap_text
        result = super().get_help(ctx)
        click.formatting.wrap_text = ExtCommand.original_wrap_text
        return result


@click.command(
    cls=ExtCommand,
    epilog="""
        Utility to publish new module versions to the FoundryVTT module
        administration site.
    """
)
@click.option(
    '--username',
    help="""
        The username of the account that will be used to access the FoundryVTT
        module administration site.

        Note: This is case-sensitive.

        |||
    """,
    required=True,
)
@click.option(
    '--password-source',
    help="""
        The source that the password of the account that will be used to access
        the site will be read from.

        The following sources are supported:

        |    |"input":|

        |      |Read the password from standard input. If reading from an
        interactive terminal, this will disable printing typed characters to
        the screen, and stop reading once "enter" is typed. Otherwise, standard
        input will be read until end-of-file.|

        |    |"environment":|

        |      |Read the password from the "FVTT_PASSWORD" environment
        variable.|

        |||

        |||
    """,
    required=True,
    type=Choice(['environment', 'input', 'raw-input'], case_sensitive=False),
    default='input'
)
@click.option(
    '--module-id',
    help="""
        The numeric ID of the module to publish a new version of.

        This can be found by accessing the module's configuration page on the
        FoundryVTT module administration site, and noting the numeric ID in the
        URL.

        |||
    """,
    metavar="ID",
    required=True,
)
@click.option(
    '--manifest-url',
    help="""
        The manifest URL of the module version being published.

        NOTE:

        |  |This is *NOT* the same as the "manifest" URL in the manifest file
        itself!|

        |  |The "manifest" URL in the manifest file should be a stable link
        that always points to the *latest* manifest file.|

        |  |The URL used for this option should point to the manifest file
        associated with the *specific module version* being published.|
    """,
    metavar="URL",
    default=None,
)
@click.option(
    '--manifest-file',
    help="""
        Path of a module manifest file to read information from.

        When this option is used, certain values in the manifest file will be
        used as the default values for certain parameters.

        ||Parameters affected by this option will explicitly state so in their
        description.|
    """,
    metavar="FILE",
    default=None,
)
@click.option(
    '--module-version',
    help="""
        The new module version to publish.

        This should be a label with the format "generation.major.minor", where
        "generation", "major" and "minor" are arbitrary labels.

        If this option is not used, then a manifest file with a "version" key
        *MUST* be specified via the "--manifest-file" option, in which case the
        value associated with that key will be used as the value for this
        option instead.
    """,
    metavar="VERSION",
    default=None,
)
@click.option(
    '--changelog-url',
    help="""
        The release notes URL of the module version being published

        If this option is not used, then a manifest file with a "changelog"
        key *MUST* be specified via the "--manifest-file" option, in which case
        the value associated with that key will be used as the value for this
        option instead.
    """,
    metavar="URL",
    default=None,
)
@click.option(
    '--minimum-core-version',
    help="""
        The oldest version of Foundry required for the module to run properly.

        If this option is not used, then a manifest file with a
        "minimumCoreVersion" key *MUST* be specified via the "--manifest-file"
        option, in which case the value associated with that key will be used
        as the value for this option instead.
    """,
    metavar="VERSION",
    default=None,
)
@click.option(
    '--compatible-core-version',
    help="""
        The newest version of Foundry that the module will properly run on.

        If this option is not used, then a manifest file with a
        "compatibleCoreVersion" key *MUST* be specified via the
        "--manifest-file" option, in which case the value associated with that
        key will be used as the value for this option instead.
    """,
    metavar="VERSION",
    default=None,
)
def main(
        username: str,
        password_source: str,
        module_id: int,
        manifest_file: str,
        **kwargs
):
    new_version_data = {}

    # Apply CLI data, if given
    for cli_key, form_key in CLI_KEY_TO_FORM_KEY_MAP.items():
        cli_value = kwargs.get(cli_key)
        if cli_value is None:
            continue

        new_version_data[form_key] = kwargs[cli_key]

    # Read in manifest data, if given.
    if manifest_file is not None:
        manifest_data = read_manifest(manifest_file)

        # If present, copy a manifest key to its relevant form key.
        for manifest_key, form_key in MANIFEST_KEY_TO_FORM_KEY_MAP.items():
            if form_key in new_version_data:
                continue

            manifest_value = get_item_from_path(manifest_data, manifest_key)
            if manifest_value is None:
                continue

            new_version_data[form_key] = manifest_value

    # Read in password
    try:
        password = read_password(password_source)
    except ValueError as exc:
        raise BadParameter("Couldn't read password: " + str(exc))
    if len(password) == 0:
        print('Warning: Supplied password was empty!', file=sys.stderr)

    # Now that all the data we require has been gathered, start by initializing
    # the browser object and logging in.
    br = mechanize.Browser()

    # ## Login ## #
    # Navigate to module administration site's login page.
    br.open(LOGIN_URL)

    # Select and fill out the "login" form.
    br.select_form(id='login-form')
    fill_out_login_form(br, username, password)
    br.submit()

    # ## Configuration page ## #
    # Navigate to configuration page.
    resp = br.open(MODULE_CONFIG_URL_FMT.format(module_id=module_id))

    # Select and fill out the "module versions" form.
    try:
        br.select_form(id='package_form')
    except FormNotFoundError:
        page_content = br.response().read().decode("utf8")
        print('Unable to find package configuration form.', file=sys.stderr)
        print('Are login credentials correct?', file=sys.stderr)
        print('Page content:', file=sys.stderr)
        print(re.sub(r'\n{2,}', '\n', page_content))
    fill_out_version_form(br, new_version_data)
    br.submit()
    page_content = br.response().read().decode("utf8")
    print(re.sub(r'\n{2,}', '\n', page_content))

def fill_out_login_form(br, username: str, password: str):
    br['username'] = username
    br['password'] = password


def fill_out_version_form(br, new_version_data: Dict):
    # Get the number of published module versions.
    # The `versions-TOTAL_FORMS` field_name contains the number of version forms
    # that are initially on the page.
    # We assume that the number of version forms is equal to the number of
    # published versions, plus one (representing the next version).
    version_count = int(br['versions-TOTAL_FORMS'])
    current_version_index = version_count - 2
    new_version_index = version_count - 1

    # The configuration page represents the forms for each version's fields
    # using the pattern "id_versions-{version_index}-{field_name}".
    # We define some helpers here for abstracting over this pattern.
    def versioned_field_name_for(field_name: str, version_index: int):
        return f'versions-{version_index}-{field_name}'

    # Check the boxes of versions that should be removed.
    # Note the `range` function, when given a single argument `X`, generates
    # numbers from 0 to `X - 1`. If `X` is less than or equal to 0, no numbers
    # will be generated.
    for version_index in range(version_count - MAX_VERSION_COUNT):
        # Setting a checkbox control's value automatically "checks" it.
        versioned_field_name = versioned_field_name_for(
            field_name='DELETE',
            version_index=version_index
        )
        br[versioned_field_name] = ['on']

    # Conveniently, the page comes with a blank set of form controls that
    # represent the next version to be published.
    # All we have to do is fill out the form with data describing the new version.
    for field_name, field_value in new_version_data.items():
        versioned_field_name = versioned_field_name_for(
            field_name=field_name,
            version_index=new_version_index
        )
        # YAML/JSON fields may be numbers, however the form field only accepts strings.
        br[versioned_field_name] = str(field_value)


def get_item_from_path(container, path):
    components = path.split('.')

    value = container
    for index, component in enumerate(components):
        if isinstance(value, str):
            partial_path = str.join('.', components[0:index])
            raise ValueError(f"Unexpected string at {partial_path} (full path: {path})")
        if isinstance(value, Sequence):
            raise ValueError(f"Unexpected list at {partial_path} (full path: {path})")
        else:
            value = value.get(component)
    return value


def read_manifest(file_path: str) -> Dict[Any, Any]:
    with open(file_path, 'r') as fh:
        return json.load(fh)


def read_password(method: str) -> Optional[str]:
    if method == "raw-input":
        return sys.stdin.read()
    if method == "input":
        return getpass()
    elif method == "environment":
        result = os.environ.get(PASSWORD_ENV_VARIABLE)
        if result is None:
            raise ValueError("Unable to read password: Environment variable")
        else:
            return result
    else:
        raise ValueError(f"Invalid method: {method}")
