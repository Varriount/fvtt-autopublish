__version__ = "0.1.0"

import json
import os
import re
import sys
from functools import partial
from getpass import getpass
from typing import Any, Dict, Optional, Sequence

import click
import mechanize
from click import Choice, Command, BadParameter
from mechanize import FormNotFoundError, HTMLForm, Browser


stderr_print = partial(print, file=sys.stderr)


# Constants
PASSWORD_ENV_VARIABLE = "FVTT_PASSWORD"
MAX_VERSION_COUNT = 1000

ADMIN_URL = "foundryvtt.com"
LOGIN_URL = f"https://{ADMIN_URL}"
MODULE_URL_FMT = f"https://{ADMIN_URL}/packages/{{module_id}}/edit"
LOGIN_COOKIE_NAME = "sessionid"


class LOGIN_FORM:
    HTML_ID = "login-form"
    USERNAME_KEY = "login_username"
    PASSWORD_KEY = "login_password"


class PACKAGE_FORM:
    HTML_ID = "package-form"

    VERSION_KEY = "version"
    NOTES_KEY = "notes"
    MANIFEST_KEY = "manifest"
    MINIMUM_CORE_VERSION_KEY = "required_core_version"
    VERIFIED_CORE_VERSION_KEY = "compatible_core_version"
    MAXIMUM_CORE_VERSION_KEY = "maximum_core_version"

    MANIFEST_KEY_TO_FORM_KEY_MAP = {
        # We don't include the manifest URL key here, as the manifest URL in the manifest
        # is a stable link to the latest manifest version, and we want a link to a specific
        # version's manifest.
        "version": VERSION_KEY,
        "changelog": NOTES_KEY,
        "compatibility.minimum": MINIMUM_CORE_VERSION_KEY,
        "compatibility.verified": VERIFIED_CORE_VERSION_KEY,
        "compatibility.maximum": MAXIMUM_CORE_VERSION_KEY,
        # Deprecated fields
        "minimumCoreVersion": MINIMUM_CORE_VERSION_KEY,
        "compatibleCoreVersion": VERIFIED_CORE_VERSION_KEY,
    }

    CLI_KEY_TO_FORM_KEY_MAP = {
        "module_version": VERSION_KEY,
        "changelog": NOTES_KEY,
        "manifest_url": MANIFEST_KEY,
        "minimum_core_version": MINIMUM_CORE_VERSION_KEY,
        "verified_core_version": VERIFIED_CORE_VERSION_KEY,
        "maximum_core_version": MAXIMUM_CORE_VERSION_KEY,
        # Deprecated fields
        "compatible_core_version": VERIFIED_CORE_VERSION_KEY,
    }


# Extend Help Formatting
class ExtCommand(Command):
    original_write_dl = click.formatting.HelpFormatter.write_dl
    original_wrap_text = click.formatting.wrap_text

    def extended_write_dl(self, rows, col_max=10, col_spacing=2):
        return ExtCommand.original_write_dl(rows, col_max, col_spacing)

    def extended_wrap_text(
        self,
        text,
        width=78,
        initial_indent="",
        subsequent_indent="",
        preserve_paragraphs=False,
    ):
        result = ExtCommand.original_wrap_text(
            text=text,
            width=width,
            initial_indent=initial_indent,
            subsequent_indent=subsequent_indent,
            preserve_paragraphs=preserve_paragraphs,
        )

        result = re.sub(
            r"\n\n[|]([^|]*?)[|]([^|]*?)[|]",
            lambda m: "\n" + m[1] + m[2].replace("\n", "\n" + m[1]),
            result,
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
    """,
)
@click.option(
    "--username",
    help="""
        The username of the account that will be used to access the FoundryVTT
        module administration site.

        Note: This is case-sensitive.

        |||
    """,
    required=True,
)
@click.option(
    "--password-source",
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
    type=Choice(
        ["environment", "input", "raw-input"],
        case_sensitive=False,
    ),
    default="input",
)
@click.option(
    "--module-id",
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
    "--manifest-url",
    help="""
        The manifest URL of the module version being published.

        NOTE:

        |  |This is *NOT* the same as the "manifest" URL in the manifest file
        itself!|

        |  |The "manifest" URL in the manifest file should be a stable link
        that always points to the *latest* manifest file.|

        |  |The URL used for THIS option should point to the manifest file
        associated with the *specific module version* being published.|
    """,
    metavar="URL",
    default=None,
)
@click.option(
    "--manifest-file",
    help="""
        Path of a module manifest file to read information from.

        When this option is used, certain values in the manifest file will be
        used as the default values for certain parameters.

        ||Parameters affected by this option will explicitly state so in their
        description.|
    """,
    metavar="FILE_PATH",
    default=None,
)
@click.option(
    "--module-version",
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
    "--changelog-url",
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
    "--minimum-core-version",
    help="""
        The oldest version of Foundry required for the module to run properly.

        If this option is not used, then a manifest file with a
        `"compatibility": {"minimum": VERSION}` key *MUST* be specified via the
        "--manifest-file" option, in which case the value associated with that
        key will be used as the value for this option instead.
    """,
    metavar="VERSION",
    default=None,
)
@click.option(
    "--verified-core-version",
    "--compatible-core-version",
    help="""
        The newest version of Foundry that the module will properly run on.

        If this option is not used, then a manifest file with a
        `"compatibility": {"verified": VERSION}` key *MUST* be specified via the
        "--manifest-file" option, in which case the value associated with that
        key will be used as the value for this option instead.
    """,
    metavar="VERSION",
    default=None,
)
@click.option(
    "--maximum-core-version",
    help="""
        The newest version of Foundry that the module will properly run on.

        If this option is not used, then a manifest file with a
        `"compatibility": {"maximum": VERSION}` key *MUST* be specified via the
        "--manifest-file" option, in which case the value associated with that
        key will be used as the value for this option instead.
    """,
    metavar="VERSION",
    default=None,
)
@click.option("--comptaible-core-version", hidden=True)
def main(
    username: str,
    password_source: str,
    module_id: int,
    manifest_file: str,
    **kwargs,
):
    new_version_data = {}

    # Apply CLI data, if given
    for cli_key, form_key in PACKAGE_FORM.CLI_KEY_TO_FORM_KEY_MAP.items():
        cli_value = kwargs.get(cli_key)
        if cli_value is None:
            continue

        new_version_data[form_key] = cli_value

    # Read in and apply manifest data to new version data, if given.
    if manifest_file is not None:
        manifest_data = read_manifest(manifest_file)

        # If present, copy a manifest key to its relevant form key.
        for manifest_key, form_key in PACKAGE_FORM.MANIFEST_KEY_TO_FORM_KEY_MAP.items():
            if form_key in new_version_data:
                continue

            manifest_value = get_item_from_dotted_path(manifest_data, manifest_key)
            if manifest_value is None:
                continue

            new_version_data[form_key] = manifest_value

    # Read in password
    try:
        password = read_password(password_source)
    except ValueError as exc:
        raise BadParameter("Couldn't read password: " + str(exc))
    if len(password) == 0:
        stderr_print("Warning: Supplied password was empty!")

    # Now that all the data we require has been gathered, start by initializing
    # the browser object and logging in.
    browser = mechanize.Browser()

    # ## Login ## #
    # Navigate to the login page.
    browser.open(LOGIN_URL)

    # Select and fill out the "login" form.
    browser.select_form(id=LOGIN_FORM.HTML_ID)
    fill_out_login_form(browser, username, password)
    browser.submit()

    # ## Configuration page ## #
    # Navigate to the configuration page.
    module_config_url = MODULE_URL_FMT.format(module_id=module_id)
    browser.open(module_config_url)

    # Select and fill out the "module versions" form.
    try:
        browser.select_form(id=PACKAGE_FORM.HTML_ID)
    except FormNotFoundError:
        stderr_print("Error encountered!")
        stderr_print("Debug information:")
        for key, value in get_debug_browser_information(browser):
            stderr_print(f"  {key}: {value}")
        stderr_print()
        stderr_print("Unable to find package configuration form.")
        stderr_print(f"Are login credentials correct?")
        stderr_print(f"The current page URL should be {module_config_url}")
        return
    fill_out_version_form(browser, new_version_data)
    browser.submit()


def fill_out_login_form(browser, username: str, password: str):
    browser[LOGIN_FORM.USERNAME_KEY] = username
    browser[LOGIN_FORM.PASSWORD_KEY] = password


def fill_out_version_form(browser, new_version_data: Dict):
    # Fill out the form fields with data describing the new version.
    form: HTMLForm = browser.form
    for field_name, field_value in new_version_data.items():
        # YAML/JSON fields may be numbers, however the form field only accepts strings.
        control = form.find_control(name=field_name)
        control.disabled = False
        control.value = str(field_value)


def get_item_from_dotted_path(container, path):
    components = path.split(".")

    value = container
    for index, component in enumerate(components):
        if isinstance(value, str):
            partial_path = str.join(".", components[0:index])
            raise ValueError(f"Unexpected string at {partial_path} (full path: {path})")
        if isinstance(value, Sequence):
            partial_path = str.join(".", components[0:index])
            raise ValueError(f"Unexpected list at {partial_path} (full path: {path})")
        else:
            value = value.get(component)
    return value


def read_manifest(file_path: str) -> Dict[Any, Any]:
    with open(file_path, "r") as fh:
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
        raise ValueError(f"Invalid password input method: {method}")


def get_debug_browser_information(browser: Browser):
    yield "Current page URL", browser.geturl()
    yield "Current page title", browser.title()
    yield "Currently stored cookies", [cookie.name for cookie in browser.cookiejar]
    # yield "Page content", browser.response()


# def get_debug_form_information(form: HTMLForm):
#     yield "Form name", form.name
#     yield "Form encoding", form.form_encoding
#     yield "Form method", form.method
#     yield "Form action", form.action
#     yield "Form attrs", form.attrs
#     response = form.click()
#     yield response.get_data()
#     yield response.get_method()
#     yield response.__getattr__()
#     yield response.get_type()
#     yield response.get_full_url()
#     yield response.get_host()
