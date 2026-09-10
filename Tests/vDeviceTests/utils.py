"""
/**
 * @file utils.py
 * @brief Endpoint resolution, command dispatch and logging helpers shared by the
 *        HDMI-CEC Sink device-level suite.
 *
 * @testcase utils
 * @details Provides shared utility functions and constants used across all HDMI CEC Sink
 *          test cases, including JSON-RPC command dispatch, vComponent YAML execution,
 *          curl-based API invocation, and structured pass/fail logging helpers.
 *
 *          This module is the single source of truth for endpoint resolution in the sink
 *          vDevice suite: a sibling module composes its request targets from the
 *          WPEFRAMEWORK_JSONRPC_URL and VCOMPONENT_API_URL values published here instead
 *          of embedding host or port literals of its own, so a single environment
 *          variable retargets the whole suite. Its consumers are HdmiCECSink_Curl.py, which
 *          publishes the structured requests, Init_Devicelist_Populate.py, which seeds the
 *          device list, SuitManager.py, which runs the suite, and the 33 Testcases/TCID*.py
 *          cases - all of which are present in this directory and written against the
 *          contract below - alongside the vcomponent_configurations/ YAML fixtures this
 *          module posts.
 *
 *          Every request this module issues is executed as an argument LIST with no shell
 *          involved, through the single hardened helper _run_curl(). A request is therefore
 *          DATA - a JsonRpcRequest of method, params, id and timeout - never a command
 *          string, which is why HdmiCECSink_Curl.py publishes structured requests rather
 *          than assembled curl lines. The endpoints are validated before use - once at import
 *          time and again in each of the three transport helpers (_jsonrpc_argv,
 *          send_curl_command via _with_validated_endpoint_and_terminator, and
 *          send_vcomponent_command) - the option terminator "--" precedes the URL in every
 *          argument list that is executed: the command definitions in HdmiCECSink_Curl.py carry
 *          it, _with_validated_endpoint_and_terminator places it in every argv send_curl_command
 *          dispatches, and _with_option_terminator inserts it in _run_curl for any argv that
 *          still lacks one. Both insertions are idempotent, so an argv that already carries a
 *          bare terminator is executed with its tokens untouched. Every invocation is bounded in
 *          time and in bytes, and a non-zero curl exit status is always reported as a failure
 *          rather than reinterpreted as a success.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - is hosting the
 *    org.rdk.HdmiCecSink plugin and answering JSON-RPC at WPEFRAMEWORK_JSONRPC_URL.
 *  - The vComponent HTTP API is serving VCOMPONENT_API_URL, and the YAML command
 *    documents under HDMICEC_CMD_BASE are readable.
 *  - No continuous integration workflow in this repository executes this suite; it is
 *    authored for device-level execution.
 *
 * @dependencies
 *  - Standard Python libraries: os, errno, json, selectors, shlex, stat, subprocess, time, re,
 *    collections, pathlib, urllib.parse
 *
 * @expected_result
 *  - Helpers return the structured result documented per function: a parsed dict, an
 *    (http_code, body) tuple, a raw response string or a decorated log message.
 *
 * @pass_criteria
 *  - Every helper returns its documented type, and a transport failure is reported
 *    through the documented failure value rather than raised at the caller.
 *
 * @failure_criteria
 *  - Subprocess errors, JSON parse failures, missing YAML documents, or unreachable
 *    JSON-RPC / vComponent endpoints.
 */
"""

import os
import errno
import json
import selectors
import shlex
import stat
import subprocess
import time
import re
from collections import namedtuple
from pathlib import Path
from urllib.parse import urlsplit



# Sentinel returned by send_curl_command when no usable response was obtained. Callers detect
# a transport failure with response.startswith("< No response"), so this string is byte-exact.
# ── CEC bus pacing: the suite's only deliberately timed constructs ──────────────────────────────
#
# DEFERRED, and named rather than scattered as magic numbers so the deferral is auditable.
#
# Every other wait in this suite was replaced with an observable condition: JSON-RPC and vComponent
# requests are synchronous, so their reply is the completion signal (see send_curl_command and
# send_vcomponent_command below), plugin readiness is observed through Controller.1.status (see
# await_plugin_ready), and device state is observed by re-reading getDeviceList until it reports what
# the test is waiting for.
#
# These four values are what remains, and they are all the SAME thing: the gap after a CEC frame has
# been handed to the emulator. Nothing observable exists to wait on there. A vComponent POST's HTTP
# 200 confirms only that the emulator accepted the document - not that the frame was carried on the
# bus, decoded, and absorbed by the middleware - and the handlers these frames exercise frequently
# have no observable outcome at all: several are bare `return` guards that increment no counter,
# change no state and raise no notification. Where an outcome IS observable the test waits for that
# outcome instead of for one of these values.
#
# Removing them would rest on an assumption that cannot be checked from here: that frames posted
# back to back are never coalesced or dropped by the transport before the middleware sees them. So
# they are recorded as deferred rather than deleted or guessed at, and they are the specific reason
# this suite is reported as not fully wait-free. Closing them needs a per-frame acknowledgement the
# device does not expose.
CEC_SHORT_PACING_SECONDS = 0.2      # a fixture with no state-visible outcome
CEC_FRAME_PACING_SECONDS = 1.0      # one injected frame
CEC_PIPELINE_PACING_SECONDS = 1.5   # a frame whose effect must reach the device list
CEC_TOPOLOGY_PACING_SECONDS = 2.0   # a device add or remove - the longest path through the pipeline


# ── the opcode names the vComponent's parser actually knows ──────────────────────────────────────
#
# THE VOCABULARY THE RESPONSE TABLE IS CHECKED AGAINST, so that "the emulator understands this
# name" is a fact a test asserts rather than a claim a comment makes.
#
# vcomponent_configurations/hdmicec/hdmicec_vcomponent_cec_responses.yaml names an opcode as a
# STRING, and the emulator resolves it through vcCommand_GetOpCode against its own table. A name
# outside that table resolves to CEC_OPCODE_UNKNOWN, whereupon ParseCommand logs
# "Opcode[<name>] Unknown" and RETURNS WITHOUT SENDING ANYTHING (vcHdmiCec.c:180-184). That
# failure is invisible from a test's point of view - the POST is accepted, HTTP 200 comes back,
# and the exchange the row describes simply never happens - so a row written in a name the parser
# does not know is worse than no row at all, because it reads like coverage. This constant plus
# TCID33_Process_Yaml_Health_Check._verify_response_table_opcodes() is what turns that from a
# silent omission into a named failure before the sweep posts anything.
#
# PROVENANCE, so a reader can re-derive it rather than trust it: these are the 55 rows of
# gOpCodeStrVal in rdk-halif-test-hdmi_cec/vcomponent/src/vcCommand.c:27-83, spelled by the CMD_*
# string macros in vcCommand.h, and they are listed below in that table's own order.
# vcCommand.h defines 57 CMD_* macros rather than 55: CMD_HOTPLUG ("HotPlug") is an opcode
# spelling that the table does not carry, and CMD_DATA_OSD_NAME ("osd_name") is a payload-symbol
# key rather than an opcode at all - which is why the macro count is not the vocabulary size.
# rdk-halif-test-hdmi_cec/** is read-only for this pass (AAP Sec. 0.10.2), so this list tracks
# that table; it does not extend it. An exchange whose opcode is absent from it cannot be
# expressed as an emulated response and is recorded as BLOCKED in the response table's header.
SUPPORTED_VCOMPONENT_OPCODES = frozenset((
    # tuner, recording and deck control
    "FeatureAbort", "ImageViewOn", "TunerStepIncrement", "TunerStepDecrement",
    "TunerDeviceStatus", "GiveTunerDeviceStatus", "RecordOn", "RecordStatus", "RecordOff",
    "TextViewOn", "RecordTvScreen", "GiveDeckStatus", "DeckStatus", "DeckControl", "Play",
    "TuneDigitalService", "TuneAnalogService", "TuneSource", "TuneChannel",
    # discovery and identity
    "GivePhysicalAddress", "ReportPhysicalAddress", "GiveOsdName", "SetOsdName",
    "GiveDeviceVendorId", "DeviceVendorId", "GiveCecVersion", "CecVersion",
    "GiveDevicePowerStatus", "ReportPowerStatus", "SetMenuLanguage", "GiveDeviceFeature",
    "ReportDeviceFeature", "SetOsdString",
    # audio
    "GiveAudioStatus", "SystemAudioModeRequest", "SetSystemAudioMode", "SystemAudioModeStatus",
    "GiveAudioModeStatus", "GiveSystemAudioModeStatus", "SetAudioRate",
    # user control and power
    "UserControlPressed", "UserControlReleased", "Standby",
    # routing and stream path
    "SetStreamPath", "RequestActiveSource", "ActiveSource", "InactiveSource", "RoutingChange",
    "RoutingInformation",
    # audio return channel
    "InitiateArc", "ReportArcInitiated", "ReportArcTerminated", "RequestArcInitiation",
    "RequestArcTermination", "TerminateArc",
))


# The import set above is the standard-library dependency contract this module publishes in
# its docstring, and every sibling module in the suite is written against it, so the two are
# kept in step deliberately:
#   * `shlex` splits a curl command string into an argv list WITHOUT a shell, and `re`
#     validates the environment-supplied endpoints. Both are load-bearing: together they are
#     why no configurable text in this suite can reach a shell (see _validated_endpoint and
#     send_curl_command).
#   * `collections.namedtuple` gives the request description below its shape, and
#     `urllib.parse.urlsplit` decomposes an endpoint for the per-call re-validation in
#     _validate_endpoint.
#   * `stat` supplies S_ISREG for the fstat check in _read_payload, which is what makes the
#     payload decision rest on an open DESCRIPTOR rather than on a path that can be swapped
#     between the check and the open.
#   * `selectors` and `time` are what make the response reader BOUNDED: the reader multiplexes
#     curl's stdout, stderr and stdin against a monotonic deadline and stops at a byte ceiling,
#     which subprocess.run() cannot do because it accumulates whatever the child produces
#     until the child exits.  See _run_curl.
#   * `tempfile` is NOT imported, and is correspondingly absent from @dependencies. The
#     template needs it for an indicator-specific YAML-rewrite path that this suite
#     deliberately does not carry; the sink posts its vComponent payloads verbatim, so an
#     import with no call site would be the only lint finding in this module.

# HDMICEC_CMD_BASE resolution order: the environment override wins outright, then the
# suite-local vcomponent_configurations/commands directory when it exists, then the
# on-device /etc path.
_BASE_DIR = Path(__file__).resolve().parent
_LOCAL_HDMICEC_CMD_BASE = _BASE_DIR / "vcomponent_configurations" / "commands"

# The whole vComponent configuration tree, which is the containment boundary every payload
# posted by send_vcomponent_command() must fall inside. Keeping the boundary one level above
# the commands directory admits the sibling hdmicec/ subtree without admitting the rest of
# the filesystem.
_LOCAL_VCOMPONENT_BASE = _BASE_DIR / "vcomponent_configurations"


def _pick_existing_dir(primary, fallback):
    if primary.is_dir():
        return str(primary)
    return fallback


HDMICEC_CMD_BASE = os.environ.get("HDMICEC_CMD_BASE") or _pick_existing_dir(
    _LOCAL_HDMICEC_CMD_BASE,
    "/etc/hdmicec/vcomponent_configurations/commands",
)

# ---------- ENDPOINT VALIDATION ----------
# The five environment variables below are the documented override contract, which means the
# endpoints are external input. curl reads an argument that begins with "-" as an OPTION, so
# an endpoint such as "--config=/tmp/attacker.curlrc" would make curl load a caller-chosen
# configuration and retarget the request; and an endpoint carrying whitespace or shell
# metacharacters is never a legitimate URL. Both are refused here, before any request is
# built. A second, positional layer sits behind that one: the "--" option terminator is placed
# immediately before the URL in every argument list this suite executes - the command definitions
# in HdmiCECSink_Curl.py and the lists built below carry it, and _with_option_terminator() inserts
# it in _run_curl for any argv that arrives without one - so an endpoint that somehow reached an
# argv unvalidated still cannot be interpreted as an option.
_ALLOWED_URL_SCHEMES = ("http", "https")

# Characters that cannot appear in a legitimate absolute URL (they must be percent-encoded).
# Their presence means the value is being used to smuggle a second argument or a command.
_FORBIDDEN_URL_CHARACTERS = (
    " ", "\t", "\n", "\r", "\v", "\f", "\0",
    '"', "'", "`", "\\", ";", "|", "&", "$", "<", ">", "(", ")", "{", "}", "*",
)


def _validate_endpoint(url, label):
    '''Validate an endpoint URL and return it unchanged, or raise ValueError.

    Accepts only a plain http/https URL with a host: no other scheme, no embedded
    credentials, no leading dash, and no character that could split the argument or reach a
    shell. Called once per endpoint at import time so a hostile or malformed override fails
    immediately and loudly, and again inside every transport helper so that a value replaced
    at run time cannot bypass the check. Those helpers are exactly three, and each calls this
    function on the endpoint it is about to dispatch: _jsonrpc_argv (send_jsonrpc_command),
    _with_validated_endpoint_and_terminator (send_curl_command, and therefore every
    HdmiCECSink_Curl.py command definition, send_jsonrpc_envelope and require_ack) and
    send_vcomponent_command's _post_payload.
    Args:
        url: Candidate endpoint URL
        label: Name of the environment variable the value came from, used in the message
    Returns:
        The validated URL, unchanged.
    Raises:
        ValueError: when the value is not a plain http/https endpoint.
    '''
    if not isinstance(url, str) or not url:
        raise ValueError(f"{label} must be a non-empty string, got {url!r}")

    if url[0] == "-":
        raise ValueError(
            f"{label} starts with '-' and would be read by curl as an option: {url!r}"
        )

    for character in _FORBIDDEN_URL_CHARACTERS:
        if character in url:
            raise ValueError(
                f"{label} contains the illegal character {character!r}: {url!r}"
            )

    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_URL_SCHEMES:
        raise ValueError(
            f"{label} must use one of {_ALLOWED_URL_SCHEMES}, got {parts.scheme!r}: {url!r}"
        )
    if not parts.hostname:
        raise ValueError(f"{label} carries no host: {url!r}")
    if parts.username or parts.password:
        raise ValueError(f"{label} must not embed credentials: {url!r}")

    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"{label} carries an invalid port: {url!r}") from exc
    if port is not None and not 0 < port < 65536:
        raise ValueError(f"{label} carries an out-of-range port {port}: {url!r}")

    return url


# Endpoint selection for local/QEMU execution.
#
# THE ENDPOINT CONTRACT - SIX ENVIRONMENT KEYS, IN THIS PRECEDENCE
# ---------------------------------------------------------------
# This module is the single source of truth for endpoint resolution in the sink vDevice
# suite and the only place in it that carries a host or port literal. Sibling modules import
# WPEFRAMEWORK_JSONRPC_URL / VCOMPONENT_API_URL from here, so retargeting the whole suite at
# a different device never means editing test code. Six keys are read, and the precedence
# below is exact - the first source set to a non-empty value wins, and the sources after it
# are then never consulted:
#
#   WPEFRAMEWORK_JSONRPC_URL  (1st for the JSON-RPC endpoint) complete URL, used verbatim.
#   JSONRPC_URL               (2nd for the JSON-RPC endpoint) LEGACY ALIAS of the above,
#                             kept so command lines written for the older suites keep
#                             working. It is consulted ONLY when WPEFRAMEWORK_JSONRPC_URL is
#                             unset or empty, and it is not mentioned anywhere else in this
#                             suite; prefer the explicit name in new work.
#   VCOMPONENT_API_URL        (1st for the vComponent endpoint) complete URL, used verbatim.
#   TARGET_HOST               (fallback host for BOTH endpoints; default 127.0.0.1) - the
#                             one place to change when a device moves.
#   JSONRPC_PORT              (fallback port for the JSON-RPC endpoint; default 9998).
#   VCOMPONENT_PORT           (fallback port for the vComponent endpoint; default 8080).
#
# So: an explicit URL beats TARGET_HOST plus a port, and for JSON-RPC the explicit
# WPEFRAMEWORK_JSONRPC_URL beats the legacy JSONRPC_URL alias. A seventh key,
# HDMICEC_CMD_BASE (above), overrides the vComponent YAML command directory, and an eighth,
# HDMICEC_TIMING_ENABLED (below), only decorates log messages; neither takes part in
# endpoint resolution.
#
# A variable that is unset OR empty falls through to the next source, so an accidentally
# blank override behaves as if it were absent rather than blanking the endpoint.
#
# HOW EACH VALUE IS CHECKED, AND WHY IT IS CHECKED HERE
# -----------------------------------------------------
# Every value is validated at DEFINITION time, once, in this module - the only place in the
# suite that carries a host or port literal - so every constant in every sibling module
# inherits the guarantee and no call site has to remember anything. Validation is by
# ALLOWLIST (a full-match pattern per value kind) with a metacharacter denylist as an
# independent second gate: TARGET_HOST must be a hostname, IPv4 address or bracketed IPv6
# literal; the two ports must be decimal and inside 1-65535, so a shape-valid 99999 is still
# refused; and a complete URL override must match a plain http(s)://host[:port][/path] AND
# carry a port in that same 1-65535 range, so `http://h:99999/x` and `http://h:0/x` are refused
# here at import rather than by every request the suite would otherwise have gone on to make.
# The range rule is therefore one rule with one meaning, whichever key expresses the endpoint.
#
# Two shapes are ACCEPTED - not refused - that look odd, and they are allowed deliberately so
# that the accepted set is exactly what the README documents and no more.  Both are stated as
# acceptances rather than as rules, because reading either of them as a rejection would mean
# believing in a guard that does not exist here:
#   * a zero-padded port such as "007" IS ACCEPTED - decimal, inside the range, and what the
#     operator typed;
#   * a TARGET_HOST containing a hyphen anywhere, INCLUDING AS ITS FIRST CHARACTER, such as
#     "-evil" or "--proxy", IS ACCEPTED.  The hyphen is in the documented host charset, and such
#     a host cannot be read by curl as an option because the value that reaches argv is never the
#     host: it is the COMPOSED URL, which always begins "http" - "http://-evil:9998/jsonrpc" is a
#     URL to curl, not an option - and the transport additionally places the "--" option
#     terminator immediately before it (see _with_validated_endpoint_and_terminator).  The
#     leading-"-" PROHIBITION applies to a whole endpoint override, not to a host, and
#     _validate_endpoint is what enforces it there.
#
# The transport is argv-based (see send_curl_command and _run_curl: no shell is ever
# involved), so this is fail-closed input hygiene rather than the primary injection control -
# and it is deliberately fail-closed: a malformed override raises at import instead of being
# silently replaced by the default, because a suite that quietly retargets itself after a typo
# would report results for a device nobody asked about.

_HOST_RE = re.compile(r"^[A-Za-z0-9._%\[\]:-]+$")
_PORT_RE = re.compile(r"^[0-9]{1,5}$")
# The path charset here is deliberately NARROWER than RFC 3986 permits, and that is the whole
# point rather than an oversight. RFC 3986 allows sub-delims -- ";", "&", "$", "'", "(", ")",
# "*", "+", "," and "!" -- inside a path, and several of those are shell metacharacters. A URL
# of `http://h:1/x;id` is a perfectly legal URL and also a shell injection once concatenated
# into a command string: the shell runs curl, then runs `id`. This was caught by testing the
# pattern rather than by reading it. Since the only endpoints this suite ever needs are
# `/jsonrpc` and `/api/postKVP`, the charset is restricted to what those require plus
# percent-encoding; query strings are not supported, and a URL needing one would have to come
# through a code change that re-examines the shell-splicing question.
_URL_RE = re.compile(
    r"^https?://[A-Za-z0-9._\[\]:-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~/%+@=-]*)?$"
)
# An independent second gate, checked for every value regardless of which pattern applies.
# The regexes above already exclude all of these, so this is unreachable today -- it exists so
# that loosening a pattern later cannot silently admit shell-active text, which is exactly how
# the `;` case above arose in the first place.
_SHELL_METACHARACTERS = set(";&|`$()<>\n\r\t\\\"' *?![]{}#")


def _validated(name, value, pattern, expectation):
    '''Return value if it matches pattern and carries no shell metacharacter.

    Two gates rather than one: `pattern` is the allowlist for this kind of value, and the
    metacharacter set is an independent check applied to every value regardless of pattern.
    The patterns already exclude everything in that set, so the second gate is unreachable
    today - it exists so that loosening a pattern later cannot silently admit shell-active
    text into a value the whole suite is composed from.

    Args:
        name: the environment variable name, so the message says which one to fix
        value: the value as read from the environment
        pattern: compiled allowlist regex the value must match in full
        expectation: human-readable description of what is allowed
    Returns:
        The value unchanged, once it is known to be safe to place in a shell string.
    Raises:
        ValueError: the value does not match, with the name, the value and the expectation.
    '''
    if not isinstance(value, str) or not pattern.match(value):
        raise ValueError(
            f"{name}={value!r} is not an accepted value for the HDMI-CEC sink vDevice suite. "
            f"Expected {expectation}. These values are spliced into the endpoints and argv lists "
            f"every curl invocation in this suite is built from, so they are allowlist-validated "
            f"once here rather than checked at each of the call sites that consume them."
        )
    # Bracketed IPv6 literals are the one accepted form that legitimately contains characters
    # from the metacharacter set, so square brackets are tolerated for the host specifically.
    offending = sorted(set(value) & (_SHELL_METACHARACTERS - set("[]")))
    if offending:
        raise ValueError(
            f"{name}={value!r} contains shell metacharacter(s) {offending!r}. "
            f"Nothing in this suite reaches a shell, but a device endpoint never legitimately "
            f"contains these characters, so the value is refused rather than carried further."
        )
    return value


def _validated_port(name, value):
    '''Return value if it is a decimal TCP port in 1-65535, else raise ValueError.

    The regex alone would admit 99999, which is not a port at all, so the numeric range is
    checked as well -- a stricter allowlist than the shape check on its own.
    '''
    _validated(name, value, _PORT_RE, "1 to 5 decimal digits")
    if not 1 <= int(value) <= 65535:
        raise ValueError(
            f"{name}={value!r} is outside the valid TCP port range 1-65535."
        )
    return value


# `or default`, NOT `os.environ.get(name, default)`, and the difference is the whole contract.
#
# A positional default applies only when the key is ABSENT. An exported-but-empty variable -
# which is what `export TARGET_HOST=${TARGET_HOST}` or `export JSONRPC_PORT=` in a wrapper
# script produces - hands back "", and "" is not a hostname or a port, so the allowlist below
# would refuse it and the whole suite would fail to import over a variable the operator never
# meant to set. `or` treats unset and empty as the same thing, which is exactly what this
# module's precedence comment above, the two URL resolutions below and the suite's README all
# state: a variable that is unset OR empty falls through to the next source. HDMICEC_CMD_BASE
# is written the same way for the same reason.
#
# An empty value therefore yields the DEFAULT; a value that is present but wrong - " ", "abc",
# "0", "99999", "h;id" - is still refused by name, because falling through on those would
# silently retarget the suite after a typo.
TARGET_HOST = _validated(
    "TARGET_HOST",
    os.environ.get("TARGET_HOST") or "127.0.0.1",
    _HOST_RE,
    "a hostname, IPv4 address, or bracketed IPv6 address using only letters, digits, "
    "dot, underscore, hyphen, colon and square brackets",
)
JSONRPC_PORT = _validated_port("JSONRPC_PORT", os.environ.get("JSONRPC_PORT") or "9998")
VCOMPONENT_PORT = _validated_port("VCOMPONENT_PORT", os.environ.get("VCOMPONENT_PORT") or "8080")


# Characters that have no place in a plain http(s)://host:port/path endpoint and that a shell
# would treat as syntax. The endpoints published by this module end up as arguments to curl
# and are never handed to a shell (see send_curl_command), so this check is defence in depth
# rather than the primary control - it stops a mistyped or hostile override at the boundary
# instead of forwarding it into a command line. Square brackets are deliberately NOT in the
# set, so an IPv6 endpoint such as http://[::1]:9998/jsonrpc remains usable.
_UNSAFE_ENDPOINT_CHARS = re.compile(r"""[\s;&|`$<>()\\'"*?!{}]""")


def _validated_endpoint(source, value):
    '''Return an endpoint URL unchanged, or raise if it carries shell-active text.
    Args:
        source: Where the value came from, named in the error message
        value: The endpoint URL to check
    Returns:
        The value unchanged when it is a plain endpoint URL.
    Raises:
        ValueError: when the value contains whitespace or a shell metacharacter, which a
                    device endpoint never legitimately does.
    '''
    match = _UNSAFE_ENDPOINT_CHARS.search(value)
    if match:
        raise ValueError(
            f"{source} contains the character {match.group(0)!r}, which is not valid in an "
            f"endpoint URL for this suite. Endpoints must be plain "
            f"http(s)://host:port/path values: {value!r}"
        )
    # Allowlist as well as denylist: the check above says what may not appear, this one says
    # what the whole value must look like, so a value that is merely nonsense (a missing
    # scheme, a five-digit-plus port, a query string) is refused here rather than handed to
    # curl to fail on later.
    if not _URL_RE.match(value):
        raise ValueError(
            f"{source} is not an accepted endpoint for this suite: {value!r}. Expected a plain "
            f"http:// or https:// URL of the form host[:port][/path], with the path restricted to "
            f"unreserved characters - RFC 3986 permits sub-delims such as ';' and '$' inside a "
            f"path and this suite deliberately does not."
        )
    # THE PATTERN IS A SHAPE CHECK, NOT A RANGE CHECK, so the numeric gate is applied too.
    #
    # _URL_RE's port group is `[0-9]{1,5}`, which admits 99999 and 0 - neither of which is a TCP
    # port. Without this line a URL-form override carrying such a port passed validation at
    # import and then failed on every single request, so the suite started and reported 33
    # failures instead of naming the one variable to fix. _validate_endpoint is the per-request
    # gate that already decomposes the URL and range-checks the port (and refuses embedded
    # credentials and a leading "-"), so it is reused here rather than duplicated: one
    # definition of "an acceptable endpoint", applied at definition time and again per request,
    # which is what its own docstring promises and what the README's override contract states.
    return _validate_endpoint(value, source)


def _resolve_endpoint(names, default, default_source):
    '''Resolve the first environment variable in `names` that holds a value, else the default.
    An unset OR empty variable falls through to the next source, which is the precedence the
    suite has always documented; whichever value wins is validated before it is published.
    Args:
        names: Environment variable names in precedence order, highest first
        default: URL composed from TARGET_HOST and the port default
        default_source: Names behind `default`, for the error message
    Returns:
        The validated winning URL.
    '''
    for name in names:
        raw = os.environ.get(name)
        if raw:
            return _validated_endpoint(name, raw)
    return _validated_endpoint(default_source, default)


WPEFRAMEWORK_JSONRPC_URL = _resolve_endpoint(
    ("WPEFRAMEWORK_JSONRPC_URL", "JSONRPC_URL"),
    f"http://{TARGET_HOST}:{JSONRPC_PORT}/jsonrpc",
    "TARGET_HOST/JSONRPC_PORT",
)
VCOMPONENT_API_URL = _resolve_endpoint(
    ("VCOMPONENT_API_URL",),
    f"http://{TARGET_HOST}:{VCOMPONENT_PORT}/api/postKVP",
    "TARGET_HOST/VCOMPONENT_PORT",
)


RESET = "\033[0m"
BOLD = "\033[1m"

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"

# Ceiling on the length of one log line. Deliberately far above anything this suite composes -
# the longest message it builds is a few hundred characters, and the widest evidence line is
# three device-list snapshots side by side - so no legitimate message is ever near it, while a
# response that arrived unbounded from a device still cannot become a screen-length log entry.
_LOG_LINE_MAX_CHARS = 16384


def _guard_log_line(msg):
    '''Neutralise control characters in a composed log line, and bound its length.

    This is the floor under every log call in the suite, and it exists because a log line is
    EVIDENCE. A device-level run leaves no artefact but its console transcript, and parts of
    almost every line in that transcript were composed from data a device sent back. A single
    ESC reaching a terminal lets that data reposition the cursor, clear the lines above it, or
    repaint a refusal as a tick; a single newline lets one response become several log records,
    one of which can be made to look exactly like this suite's own output.

    Applying the guard HERE rather than at each of the several hundred call sites is deliberate.
    Whether a particular interpolation is dangerous turns on a distinction that is easy to get
    wrong and easier to lose: a bare string from the wire prints its control bytes literally,
    while the same string inside a dict or rendered with !r is escaped already by Python's own
    repr. Enumerating the dangerous sites correctly once is possible; keeping that enumeration
    correct as the suite grows is not. At this level the property holds for every call, present
    and future, by construction.

    What it does NOT do is escape everything: printable text and non-ASCII glyphs pass through
    untouched, so this suite's own tick, warning and cross marks still render, and text that was
    already escaped by utils.sanitise_for_log is left exactly as that function rendered it. Only
    C0 controls, DEL and C1 controls are replaced, each by a visible \\xNN escape, and a
    backslash already present is NOT doubled here - doing so would double the escapes
    sanitise_for_log produced and make its output unreadable. sanitise_for_log remains the
    stronger, fully-escaping, tightly-bounded rendering for an individual value from the wire;
    this is the last line of defence for whatever reaches a log call by another route.

    Args:
        msg: The composed message. A non-str is rendered with str() first.
    Returns:
        Single-line text with no control characters, truncated to _LOG_LINE_MAX_CHARS with an
        explicit marker when it was longer.
    '''
    if not isinstance(msg, str):
        try:
            msg = str(msg)
        except Exception:  # pragma: no cover - defensive; a __str__ that raises is pathological
            return "<unprintable log message>"

    dropped = len(msg) - _LOG_LINE_MAX_CHARS
    if dropped > 0:
        msg = f"{msg[:_LOG_LINE_MAX_CHARS]}...[+{dropped} chars truncated]"

    if not any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in msg):
        # The common case by a wide margin, and identity for every message this suite composes
        # itself: scan once and return the original object rather than rebuilding it.
        return msg

    return "".join(
        f"\\x{ord(character):02x}"
        if ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F
        else character
        for character in msg
    )


def log_info(msg):
    print(f"{CYAN}{_guard_log_line(msg)}{RESET}")

def log_success(msg):
    print(f"{GREEN}{BOLD}{_guard_log_line(msg)}{RESET}")

def log_warning(msg):
    print(f"{YELLOW}{_guard_log_line(msg)}{RESET}")

def log_error(msg):
    print(f"{RED}{BOLD}{_guard_log_line(msg)}{RESET}")


def log_with_timing(msg, elapsed_time):
    '''Decorate a message with its elapsed time when HDMICEC_TIMING_ENABLED is set.
    The decorated text is returned rather than printed, so the caller keeps the choice
    of log level to route it through.
    Args:
        msg: Base message without timing
        elapsed_time: Elapsed time in seconds (float)
    Returns:
        "<msg> time consumed: <elapsed>s" when HDMICEC_TIMING_ENABLED is set in the
        environment, otherwise msg unchanged.
    '''
    if os.environ.get("HDMICEC_TIMING_ENABLED"):
        return f"{msg} time consumed: {elapsed_time:.3f}s"
    return msg


# Default character budget applied to a remote-derived string before it is logged. The
# vComponent's diagnostics and this module's own refusal explanations are a line or two; the
# budget keeps a hostile or malfunctioning endpoint from filling the run log with one response.
LOGGED_VALUE_MAX_CHARS = 512


def sanitise_for_log(value, max_chars=LOGGED_VALUE_MAX_CHARS):
    '''Render a remote-derived value as bounded, escaped, pure-ASCII text fit for a console.

    Every string in a run log that came off the wire passes through here first. The reason is
    log integrity, not tidiness: an endpoint that answers with terminal control sequences can
    otherwise reposition the cursor, clear what a previous line said, or repaint a failure as a
    tick, and the console transcript is the only evidence a device-level run leaves behind. An
    ESC, a carriage return or a backspace reaching a terminal is what makes that possible, so
    none of them reaches one from here.

    The escaping is total rather than selective. Only the printable ASCII range 0x20-0x7E
    survives literally, and a literal backslash is doubled so the escapes it introduces cannot
    be forged by a body that contains "\\x1b" as text. Everything else - C0 and C1 controls,
    DEL, newlines, tabs, and every non-ASCII code point - is replaced by a \\xNN, \\uNNNN or
    \\UNNNNNNNN escape. The result is single-line by construction, so one response can never
    become several log lines, and a body cannot fabricate a line that looks like this suite's
    own output.

    Args:
        value: Any object. A str is used as-is; anything else is rendered with str() first, so
               an HTTP status code or a parsed fragment can be passed in without ceremony.
        max_chars: Maximum number of INPUT characters rendered. The remainder is dropped and
                   its length reported, so a truncated body is visibly truncated rather than
                   silently short. Because one input character can expand to at most ten output
                   characters, the returned text is bounded by 10*max_chars plus the marker.
    Returns:
        Escaped ASCII text, with "...[+N chars truncated]" appended when the input was longer
        than the budget. Never raises: an object whose str() raises renders as "<unprintable>".
    '''
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:  # pragma: no cover - defensive; a __str__ that raises is pathological
            return "<unprintable>"

    budget = max_chars if isinstance(max_chars, int) and max_chars > 0 else LOGGED_VALUE_MAX_CHARS
    dropped = len(value) - budget
    rendered = []
    for character in value[:budget]:
        code = ord(character)
        if character == "\\":
            rendered.append("\\\\")
        elif 0x20 <= code <= 0x7E:
            rendered.append(character)
        elif code <= 0xFF:
            rendered.append(f"\\x{code:02x}")
        elif code <= 0xFFFF:
            rendered.append(f"\\u{code:04x}")
        else:
            rendered.append(f"\\U{code:08x}")

    text = "".join(rendered)
    if dropped > 0:
        text = f"{text}...[+{dropped} chars truncated]"
    return text


# ---------- REQUEST DESCRIPTION ----------
# A request is DATA, never a command line - which is what keeps the suite's request definitions
# free of quoting concerns: there is no command string anywhere for an endpoint or a parameter
# value to escape from.
#
# Two shapes express that, and both are supported deliberately. HdmiCECSink_Curl.py publishes
# each sink API as a ready-made ARGV LIST, which send_curl_command runs verbatim; a caller that
# would rather describe a request than build one uses this JsonRpcRequest and hands its fields
# to send_jsonrpc_command, which composes the argv itself. Neither route ever produces a command
# string for a shell to interpret.
JsonRpcRequest = namedtuple(
    "JsonRpcRequest",
    ["method", "params", "request_id", "timeout"],
)
# params defaults to None (omitted from the payload), the id to the value the suite's request
# definitions use, and the budget to five seconds.
JsonRpcRequest.__new__.__defaults__ = (None, 42, 5)

# Sentinel returned by send_curl_command when no usable response was obtained. Callers detect
# a transport failure with response.startswith("< No response"), so this string is byte-exact.
NO_RESPONSE_SENTINEL = "< No response from WPEFramework >"

# How long a single legacy-string exchange may take before it is abandoned. The command
# constants also pass curl's own --max-time; this is the outer bound that still applies if a
# command omits it, so a hung endpoint cannot stall a suite run indefinitely.
CURL_TIMEOUT_SECONDS = 15

# Connection budget applied to every request in addition to the caller's overall budget, and
# the extra grace given to subprocess.run so that curl's own timeout fires first and yields a
# diagnosable exit status rather than an opaque kill.
_CONNECT_TIMEOUT_SECONDS = 5
_SUBPROCESS_TIMEOUT_MARGIN_SECONDS = 5

# Upper bound on a vComponent payload this module will read and post. The suite's own YAML
# documents are a few kilobytes; the cap turns "an unexpected file was approved" into a clean
# refusal instead of an unbounded read.
_VCOMPONENT_MAX_PAYLOAD_BYTES = 1024 * 1024


def _normalise_timeout(timeout, default=5):
    '''Return a positive integer second budget, falling back to default.'''
    try:
        value = int(timeout)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# Upper bound on how much a single curl invocation may hand back on stdout and stderr
# together.  Every response this suite reads is a JSON-RPC envelope or a short vComponent
# acknowledgement - kilobytes - so the ceiling exists purely to bound a hostile or broken
# endpoint that streams at network speed for the whole timeout window.  It matches the payload
# cap deliberately: the same order of magnitude is generous for anything legitimate.
_MAX_RESPONSE_BYTES = 1024 * 1024

# Read granularity for the bounded reader.  One page-ish chunk per readable event keeps the
# loop responsive to the deadline without a syscall per byte.
_READ_CHUNK_BYTES = 65536


def _terminate_child(proc):
    '''Stop a curl that is still running, and reap it, without ever blocking indefinitely.

    SIGTERM first, because curl exits promptly on it and a terminated child yields a
    diagnosable status; SIGKILL only if it is still there after a short grace period.  The
    process is always waited for: an unreaped child would otherwise stay a zombie for the rest
    of the suite run, and its pipe file descriptors would stay open in this process.
    '''
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            pass
        proc.kill()
        proc.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        # Nothing further is available at this level; the finally block in _run_curl closes
        # the pipes either way, so no descriptor is leaked even in this case.
        pass


def _pump_child(proc, deadline, input_bytes, max_bytes):
    '''Move bytes to and from a running curl under a byte ceiling and a wall-clock deadline.

    WHY THIS EXISTS, rather than subprocess.run(..., capture_output=True): run() reads until
    the child closes its pipes and accumulates every byte in this process, with no ceiling.  A
    malicious or merely broken endpoint can therefore stream for the whole timeout window and
    exhaust this process's memory before the timeout ever fires - the timeout bounds the
    DURATION of the read, never its SIZE.  A suite that dies of memory exhaustion reports
    nothing at all, which is a worse failure than the transport error it was trying to observe.

    So stdout and stderr are read incrementally through a selector, the running total is
    checked after every chunk, and the child is killed the moment the ceiling is crossed.
    stdin is written through the SAME selector rather than up front: a server that never reads
    the request body would otherwise block this process in write() once the pipe buffer filled,
    which is the same denial of service arriving from the other direction.

    Returns:
        (stdout_bytes, stderr_bytes, overflow, timed_out)
    '''
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    total = 0
    overflow = False
    timed_out = False
    pending = memoryview(input_bytes) if input_bytes else None

    selector = selectors.DefaultSelector()
    try:
        for name in ("stdout", "stderr"):
            stream = getattr(proc, name)
            if stream is not None:
                selector.register(stream.fileno(), selectors.EVENT_READ, name)
        if pending is not None and proc.stdin is not None:
            selector.register(proc.stdin.fileno(), selectors.EVENT_WRITE, "stdin")
        elif proc.stdin is not None:
            proc.stdin.close()

        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            # Capped so the deadline is re-evaluated regularly even on a silent connection.
            for key, mask in selector.select(timeout=min(remaining, 0.5)):
                which = key.data
                if which == "stdin":
                    try:
                        written = os.write(key.fd, pending[:_READ_CHUNK_BYTES])
                    except BrokenPipeError:
                        # curl exited or stopped reading; nothing more can be delivered.
                        selector.unregister(key.fd)
                        _close_quietly(proc.stdin)
                        continue
                    except OSError:
                        selector.unregister(key.fd)
                        _close_quietly(proc.stdin)
                        continue
                    pending = pending[written:]
                    if not pending:
                        selector.unregister(key.fd)
                        # EOF on the request body is what tells curl the POST is complete.
                        _close_quietly(proc.stdin)
                    continue

                try:
                    chunk = os.read(key.fd, _READ_CHUNK_BYTES)
                except OSError:
                    chunk = b""
                if not chunk:
                    selector.unregister(key.fd)
                    continue
                captured[which].extend(chunk)
                total += len(chunk)
                if total > max_bytes:
                    overflow = True
                    break
            if overflow:
                break
    finally:
        selector.close()

    return bytes(captured["stdout"]), bytes(captured["stderr"]), overflow, timed_out


def _close_quietly(stream):
    '''Close a pipe end, tolerating one that is already closed or already broken.'''
    if stream is None:
        return
    try:
        stream.close()
    except (OSError, ValueError):
        pass


# ------------------------------------------------------------------------------------
# WHAT CURL IS ALLOWED TO BE TOLD BY ITS SURROUNDINGS.
#
# curl reads a great deal of its behaviour from places that are not this argv.  Every one of
# them is somebody else's decision about a request this suite makes and then reports on:
#
#   * ~/.curlrc (or $CURL_HOME/.curlrc).  Read before any argument is processed, and it may
#     contain ANY option - including --url, --proxy, --header, --data and --output.  A single
#     line there silently retargets every request in this suite, and the run still reports
#     whatever came back as the device's answer.
#   * the proxy variables http_proxy / https_proxy / HTTPS_PROXY / ALL_PROXY / all_proxy.
#     curl honours them for a plain http:// URL, so an exported proxy sends a request aimed at
#     a loopback JSON-RPC port to a third party instead - which both leaks the request and
#     lets the proxy's own document (its 502 page, say) arrive in place of a response.
#     no_proxy is not a defence: it only carves exceptions out of a proxy that is in effect,
#     and a hostile or merely stale value can be narrowed as easily as it can be widened.
#   * CURL_CA_BUNDLE / SSL_CERT_FILE / SSL_CERT_DIR, which decide what a TLS endpoint has to
#     prove; and NETRC / .netrc, which can attach credentials to a request.
#
# Two independent measures, because neither alone is sufficient:
#
#   1. "-q" as the FIRST parameter.  curl documents that --disable must come first to take
#      effect, and it makes curl skip its configuration file entirely.  Applied in _run_curl
#      rather than in each builder, so it cannot be forgotten by a new call site.
#   2. an explicit environment.  -q does not touch environment variables, so the child is given
#      a small allow-list instead of this process's environment: PATH so the binary resolves,
#      HOME and LANG/LC_ALL for well-defined behaviour, and nothing else.  Absence is the
#      mechanism -- no filtering of names is involved, so a variable curl gains meaning for in
#      a future version is excluded by default rather than by enumeration.
#
# "--noproxy '*'" is added as well.  It is redundant against the empty environment and
# deliberately kept: it states the intent in the argv itself, where a reader of a failing run's
# command line can see it, and it holds even if a caller ever hands _run_curl a pre-built
# environment.
# ------------------------------------------------------------------------------------
_CURL_PASSTHROUGH_ENV = ("PATH", "HOME", "LANG", "LC_ALL")
_CURL_FALLBACK_PATH = "/usr/bin:/bin"


def _curl_child_env():
    '''Return the minimal environment curl is run with (allow-list, not deny-list).'''
    env = {}
    for name in _CURL_PASSTHROUGH_ENV:
        value = os.environ.get(name)
        if value:
            env[name] = value
    # PATH is the one entry the child cannot do without: without it execve still succeeds for
    # the absolute path Popen resolved, but any curl behaviour that shells out (it has none in
    # this suite's usage) and every diagnostic that names a tool would misreport.
    env.setdefault("PATH", _CURL_FALLBACK_PATH)
    return env


def _hardened_curl_argv(argv):
    '''Return argv with "-q" first and "--noproxy '*'" present, without duplicating either.

    Both are inserted immediately after the binary, so they land before any "--" option
    terminator and can never be read as the URL or as its argument.
    '''
    argv = [str(token) for token in argv]
    if not argv:
        raise ValueError("empty curl command")

    prefix = []
    # "-q" only disables the configuration file when it is the first parameter, so it is placed
    # there.  An argv that already carries it anywhere is left alone rather than given a second
    # copy in a position where the first one may already have done the work.
    if not any(token in ("-q", "--disable") for token in argv[1:]):
        prefix.append("-q")
    # A caller that has already made its own proxy decision keeps it; this only fills the gap.
    if not any(token == "--noproxy" or token.startswith("--noproxy=") for token in argv[1:]):
        prefix.extend(("--noproxy", "*"))
    if not prefix:
        return argv
    return [argv[0]] + prefix + argv[1:]


def _with_option_terminator(argv):
    '''Return argv with "--" immediately before its trailing URL, when that is what is missing.

    curl reads any argument beginning with "-" as an OPTION, so a URL is only GUARANTEED to be
    read as an operand when the "--" terminator precedes it.  Two independent layers are wanted
    rather than one: _validate_endpoint refuses an endpoint that begins with "-" - and one
    carrying whitespace, a shell metacharacter, embedded credentials or a non-http scheme -
    before any request is built, and this function makes the guarantee POSITIONAL as well, so a
    value that reached an argv without passing that validation still cannot be read as an option.

    This is where the guarantee is established for EVERY invocation rather than per argv builder.
    utils' own lists (_jsonrpc_argv, send_vcomponent_command) and the 33 command definitions in
    HdmiCECSink_Curl.py each carry their own "--"; this function is what makes an argv assembled
    anywhere else - a hand-built list, a command copied from a run log, a definition added later
    that forgets the terminator - carry one too, because _run_curl applies it to everything it
    executes.

    It DECLINES to insert, returning the argv untouched, in exactly the three cases where
    inserting would change what curl is being asked to do:
      * the argv already carries a bare "--".  The caller placed its own terminator, and curl
        reads a second one as a URL.
      * the final token is not an http(s) URL.  There is no trailing endpoint to protect, and
        this function does not guess where the operand is.
      * the token before the final one begins with "-".  The URL-shaped token may be that
        option's VALUE ("curl -d http://x" posts a body, it does not name an endpoint), and
        separating an option from its value would corrupt the request rather than harden it.
    Idempotent: applying it to its own output is a no-op, because the first application leaves a
    bare "--" behind.
    Args:
        argv: A curl argument list, normally already hardened by _hardened_curl_argv
    Returns:
        argv with "--" inserted immediately before its final token, or argv unchanged when one of
        the three cases above applies
    '''
    argv = [str(token) for token in argv]
    if len(argv) < 2 or "--" in argv:
        return argv
    url = argv[-1]
    if not url.lower().startswith(("http://", "https://")):
        return argv
    if argv[-2].startswith("-"):
        return argv
    return argv[:-1] + ["--", url]


def _run_curl(argv, timeout, input_bytes=None):
    '''Run curl as an argument list with no shell, bounded in time AND in bytes.

    This is the ONLY place in the suite that starts a process. shell=False means the argument
    list is passed to execve untouched, so no element of it - endpoint, payload or parameter
    value - can be interpreted as a command, a redirection or a second argument.

    It is also the single place where curl's own configuration surface is closed off: every
    invocation gets "-q" as its first parameter, "--noproxy '*'", and a minimal explicit
    environment.  See the block above this function for what each of those excludes and why.

    And it is where the "--" option terminator is guaranteed rather than assumed.  Every argv
    this suite hands over already carries one, but "every caller remembered" is not a property
    anything checks, so _with_option_terminator inserts it here for any argv that does not - which
    makes "the URL is read as an operand, never as an option" true of whatever is executed rather
    than only of the lists this suite happens to ship today.

    The response is read through _pump_child, which stops at _MAX_RESPONSE_BYTES and kills the
    child rather than accumulating whatever an endpoint chooses to send.  An overflow is
    reported as a FAILURE with its own diagnostic: a truncated body is not an answer, and
    handing back the first megabyte of a stream as though it were a response would let a
    hostile endpoint decide what this suite believes.
    Args:
        argv: Complete argument list.  "--" before its URL is ensured here rather than required
              from the caller, and an argv that already carries one is left exactly as it is
        timeout: curl --max-time budget in seconds, also used to bound the read loop
        input_bytes: Optional request body delivered on curl's stdin
    Returns:
        (ok, returncode, stdout, stderr) where ok is True only when curl exited 0 within its
        budget and produced no more than the byte ceiling.  returncode is None when curl could
        not be run, exceeded its bound, or was killed for overflowing.
    '''
    deadline = time.monotonic() + timeout + _SUBPROCESS_TIMEOUT_MARGIN_SECONDS
    try:
        argv = _hardened_curl_argv(argv)
    except ValueError as exc:
        return False, None, "", f"curl could not be executed: {exc}"
    # After the hardening prefix, so "-q" and "--noproxy '*'" stay in front of the terminator
    # where curl still reads them as options.
    argv = _with_option_terminator(argv)
    try:
        proc = subprocess.Popen(
            argv,
            shell=False,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_curl_child_env(),
        )
    except (OSError, ValueError) as exc:
        return False, None, "", f"curl could not be executed: {exc}"

    try:
        stdout_bytes, stderr_bytes, overflow, timed_out = _pump_child(
            proc, deadline, input_bytes, _MAX_RESPONSE_BYTES
        )
        if overflow:
            _terminate_child(proc)
            return (
                False,
                None,
                "",
                f"the endpoint sent more than the {_MAX_RESPONSE_BYTES} byte response ceiling; "
                "curl was terminated and the partial body discarded",
            )
        if timed_out:
            _terminate_child(proc)
            return False, None, "", f"curl exceeded its {timeout}s budget and was terminated"

        # Both pipes reached EOF, so the child is finishing; still bounded, because a curl that
        # closed its outputs and then hung would otherwise wait here for ever.
        remaining = max(deadline - time.monotonic(), 0.1)
        try:
            returncode = proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            _terminate_child(proc)
            return False, None, "", f"curl exceeded its {timeout}s budget and was terminated"
    finally:
        # Always: reap the child if it is somehow still running, and close every pipe this
        # process holds.  subprocess.run() did both implicitly; Popen does not.
        _terminate_child(proc)
        _close_quietly(proc.stdin)
        _close_quietly(proc.stdout)
        _close_quietly(proc.stderr)

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return returncode == 0, returncode, stdout, stderr


# Written by curl at the very end of its output because of "-w".  The body is everything
# before it, so the marker is a newline plus the numeric status and nothing else; splitting on
# the LAST newline keeps a body that itself contains newlines intact.
_HTTP_CODE_WRITE_OUT = "\n%{http_code}"


def _split_http_status(stdout):
    '''Split curl output produced with _HTTP_CODE_WRITE_OUT into (body, status).

    Returns status None when no numeric status is present, which is itself a failure: it means
    curl did not complete a request/response exchange, so there is nothing to believe about
    whatever text did arrive.
    '''
    if not stdout:
        return "", None
    body, _, tail = stdout.rpartition("\n")
    candidate = tail.strip()
    if candidate.isdigit():
        return body, int(candidate)
    # No trailing status: the whole output is unattributed text.
    return stdout, None


def _jsonrpc_argv(payload, timeout):
    '''Build the argument list for one JSON-RPC POST.

    The endpoint is re-validated here rather than trusted from module scope, and "--" is
    placed immediately before it so curl cannot read it as an option.

    "-w" is included so the HTTP STATUS comes back alongside the body.  Without it curl exits 0
    for any completed exchange, including a 500 or a 404 that carries a body - and a body is
    exactly what a server returns with an error status, so "curl exited 0 and something came
    back" is not evidence that the request was served.
    '''
    url = _validate_endpoint(WPEFRAMEWORK_JSONRPC_URL, "WPEFRAMEWORK_JSONRPC_URL")
    return [
        "curl", "-sS",
        "-w", _HTTP_CODE_WRITE_OUT,
        "--connect-timeout", str(min(_CONNECT_TIMEOUT_SECONDS, timeout)),
        "--max-time", str(timeout),
        "-H", "Content-Type: application/json",
        "-X", "POST",
        "--data", json.dumps(payload),
        "--",
        url,
    ]


def _dispatch_jsonrpc(method, params, request_id, timeout):
    '''Post one JSON-RPC request and return (ok, body, diagnostic).

    THREE independent conditions must all hold before a body is handed back, because each one
    fails in a way the others cannot see:

      * curl exited 0.  A transport failure never yields a body.
      * the HTTP status is 2xx.  curl exits 0 for a COMPLETED exchange whatever the status, so
        a 500 or a 404 carrying a JSON body used to be returned as an answer - and an error
        status is precisely when a server sends a body.  A 401 page or a proxy's 502 document
        is not a JSON-RPC response.
      * the body is non-empty.

    The remaining two conditions - that the body is exactly one valid JSON-RPC envelope, and
    that its id matches the one sent - are enforced by the caller against the parsed envelope,
    where the request id is known.
    '''
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params

    ok, returncode, stdout, stderr = _run_curl(
        _jsonrpc_argv(payload, timeout), timeout
    )
    if not ok:
        # Bounded and escaped HERE rather than at the log call.  This diagnostic is returned to
        # callers that interpolate it into a log line, and its content is curl's stderr or the
        # endpoint's own output - so the value crosses a function boundary before it is printed,
        # and whichever caller prints it must not have to remember that.
        detail = stderr.strip() or stdout.strip()
        diagnostic = f"curl exited {returncode}"
        if detail:
            diagnostic = f"{diagnostic}: {sanitise_for_log(detail)}"
        return False, "", diagnostic

    body_text, status = _split_http_status(stdout)
    if status is None:
        return False, "", (
            "curl exited 0 but reported no HTTP status, so no request/response exchange "
            "completed"
        )
    if not 200 <= status < 300:
        detail = body_text.strip()
        diagnostic = f"the endpoint answered HTTP {status}, which is not a success status"
        if detail:
            # sanitise_for_log both bounds the length and escapes control bytes; the manual
            # 200-character slice it replaces did the first and not the second, so an error page
            # containing an ESC still reached the terminal.
            diagnostic = f"{diagnostic}; body: {sanitise_for_log(detail, 200)}"
        return False, "", diagnostic

    body = body_text.strip()
    if not body:
        return False, "", f"the endpoint answered HTTP {status} with an empty body"

    return True, body, ""


def _no_duplicate_keys(pairs):
    '''json object_pairs_hook that refuses an object with a repeated key.

    json.loads keeps the LAST value for a duplicated key and says nothing, so
    {"result": {"success": false}, "result": {"success": true}} decodes to a success and a
    reader of the raw body sees a refusal.  This suite hands the RAW TEXT back to its callers
    and they parse it again, so a body whose meaning depends on which parser is asked cannot be
    treated as an answer at all.  Raising here makes the whole decode fail, which is what the
    callers already handle as "not an envelope".
    '''
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r} in a JSON object")
        seen[key] = value
    return seen


def _parse_jsonrpc_envelope(body):
    '''Return the decoded JSON-RPC 2.0 envelope, or None when the body is not exactly one.

    A complete envelope is a JSON object carrying "jsonrpc": "2.0" together with EXACTLY ONE of
    a result member or an error member. An error envelope IS a valid response - the device
    answered - so it is returned to the caller rather than suppressed.

    Five ways of not being an envelope are refused, and each was reachable before:

      * not JSON at all, or JSON followed by anything else.  json.loads refuses trailing data,
        so this also rejects a body that is one envelope plus a second document, a log line or
        an HTML error page appended to it.
      * not a JSON object: an array is refused, which is what makes a JSON-RPC BATCH response
        inadmissible here.  A batch answers several requests; this suite issues one request per
        exchange, so a batch cannot be attributed to it, and taking element zero would be a
        guess.
      * "jsonrpc" that is not exactly the string "2.0".
      * BOTH result and error present, or NEITHER.  The specification says a response carries
        one or the other, never both; an envelope with both is self-contradictory, and the
        previous test ("neither present") accepted it - after which envelope_result() would
        report a result for a response that also announced a failure.
      * a repeated key anywhere in the document (see _no_duplicate_keys).
    '''
    try:
        decoded = json.loads(body, object_pairs_hook=_no_duplicate_keys)
    except (TypeError, ValueError):
        return None
    if not isinstance(decoded, dict):
        return None
    if decoded.get("jsonrpc") != "2.0":
        return None
    has_result = "result" in decoded
    has_error = "error" in decoded
    if has_result == has_error:
        # Both, or neither.
        return None
    return decoded


def send_jsonrpc_command(method, params=None, request_id=1, timeout=5):
    '''Send a JSON-RPC request to WPEFramework and return parsed response dict.
    Returns None when request fails or response is not JSON.
    Args:
        method: Fully qualified JSON-RPC method, e.g. "org.rdk.HdmiCecSink.1.getEnabled"
        params: Optional params object; omitted from the payload entirely when None
        request_id: JSON-RPC request id echoed back by the target
        timeout: curl --max-time budget in seconds
    Returns:
        Parsed response dict on success, None on any transport or parse failure.
    '''
    budget = _normalise_timeout(timeout)
    # A transport failure, a non-2xx status, an empty body, a body that is not a JSON-RPC
    # envelope, or an envelope answering a DIFFERENT request all yield None. The caller is never
    # handed a synthesised success object, so an unreachable or misbehaving device reads as a
    # failure rather than as a pass.
    ok, body, diagnostic = _dispatch_jsonrpc(method, params, request_id, budget)
    if not ok:
        log_warning(f"Inside Utils.py : {method} not dispatched - {diagnostic}")
        return None

    envelope = _parse_jsonrpc_envelope(body)
    if envelope is None:
        log_warning(
            f"Inside Utils.py : {method} answered with something that is not a single valid "
            "JSON-RPC 2.0 envelope"
        )
        return None

    # THE ID MUST MATCH.  JSON-RPC pairs a response to its request by id, and this suite issues
    # one request per exchange, so an envelope carrying a different id is not this call's
    # answer - it is a stale, cached or fabricated response, and treating it as this call's
    # result would attribute somebody else's outcome to this test.  Compared loosely on the
    # string form because a JSON id may legitimately arrive as 42 or "42".
    if "id" not in envelope or str(envelope.get("id")) != str(request_id):
        log_warning(
            f"Inside Utils.py : {method} answered with id {envelope.get('id')!r} but the "
            f"request carried id {request_id!r}; the response does not belong to this request"
        )
        return None

    return envelope


def activate_plugin(callsign):
    '''Activate an RDK plugin via Controller.1.activate.
    Returns True on success, False otherwise.
    Args:
        callsign: Plugin callsign to activate, e.g. "org.rdk.HdmiCecSink"
    Returns:
        True when the controller answered with a result, False on any error,
        on a missing result member, or when the controller was unreachable.
    '''
    # The request id is the one the source plugin's vDevice suite already uses for this
    # call - entservices-hdmicecsource/Tests/vDeviceTests/SuitManager.py and its utils.py
    # both send 1234567890 - and the planned sink SuitManager.py will carry the same value
    # in its own copy of this helper. Keeping them in step makes activation calls easy to
    # correlate in a WPEFramework trace regardless of which module issued them.
    response = send_jsonrpc_command(
        "Controller.1.activate",
        params={"callsign": callsign},
        request_id=1234567890,
    )
    if not response:
        return False
    if "error" in response:
        return False
    return "result" in response


def _request_id_from_argv(argv):
    '''Return the JSON-RPC id carried by a curl argv's request body, or None.

    The suite's command definitions all pass their body with -d/--data, so the id the target is
    expected to echo is recoverable from the command itself.  None means "no id could be
    established", which is not treated as an id mismatch - it is simply one check that cannot be
    applied to that command.
    '''
    data_flags = ("-d", "--data", "--data-raw", "--data-ascii", "--data-binary")
    for index, token in enumerate(argv):
        if token in data_flags and index + 1 < len(argv):
            candidate = argv[index + 1]
        elif token.startswith("--data=") or token.startswith("--data-raw="):
            candidate = token.split("=", 1)[1]
        else:
            continue
        try:
            decoded = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(decoded, dict) and "id" in decoded:
            return decoded["id"]
    return None


def send_jsonrpc_envelope(curl_command, label):
    '''Dispatch a suite command definition and return its reply envelope, or None.

    The shared front half of every assertion a test case makes about a JSON-RPC call. It returns
    a value ONLY when all five of these hold, and logs the specific reason for the failure
    otherwise, naming `label` so a run log says which of a case's several calls went wrong:

      * the command was dispatched and a reply came back - the NO_RESPONSE_SENTINEL is refused
        here, and refused by prefix, because it is a truthy string and an emptiness test alone
        would read a dead endpoint as a healthy one;
      * the reply is syntactically valid JSON;
      * the reply is a JSON object rather than an array or a scalar;
      * it declares jsonrpc 2.0;
      * its id is the id the command sent, so the envelope describes THIS call.

    send_curl_command already enforces the transport half of that - curl's exit status, a 2xx
    HTTP status, exactly one envelope, and the matching id - so a caller only needing a reply is
    safe without this. What this adds is the same guarantee re-established where a VERDICT is
    formed: a test whose result is "the plugin acknowledged this write" or "the plugin refused
    this call" cannot rest that result on a helper's internal behaviour, because an envelope
    belonging to another request carries another request's answer.

    Args:
        curl_command: A command definition from HdmiCECSink_Curl.py, argv or string form.
        label: How this call should be named in a diagnostic, e.g. "baseline setVendorId".
    Returns:
        The parsed envelope as a dict, or None when any condition above failed.
    '''
    response = send_curl_command(curl_command)
    if not response:
        log_error(f"✖ {label}: command not sent")
        return None
    if response.startswith("< No response"):
        log_error(f"✖ {label}: no usable response from WPEFramework")
        return None

    try:
        envelope = json.loads(response)
    except ValueError:
        log_error(
            f"✖ {label}: reply is not valid JSON "
            f"({sanitise_for_log(response, max_chars=256)})"
        )
        return None

    if not isinstance(envelope, dict):
        log_error(
            f"✖ {label}: reply is valid JSON but not a JSON-RPC envelope "
            f"({type(envelope).__name__})"
        )
        return None
    if envelope.get("jsonrpc") != "2.0":
        log_error(
            f"✖ {label}: reply does not declare jsonrpc 2.0 "
            f"(jsonrpc={sanitise_for_log(envelope.get('jsonrpc'), max_chars=32)})"
        )
        return None

    sent_id = expected_request_id(curl_command)
    if sent_id is None:
        log_error(
            f"✖ {label}: the command definition carries no readable JSON-RPC id, so the reply "
            "cannot be correlated to it"
        )
        return None
    if str(envelope.get("id")) != str(sent_id):
        log_error(
            f"✖ {label}: reply answers request id "
            f"{sanitise_for_log(envelope.get('id'), max_chars=32)}, not the {sent_id} that was "
            "sent, so it describes a different call"
        )
        return None

    return envelope


def envelope_result(envelope):
    '''Return an envelope's "result" mapping, or None when there is not one.

    A JSON-RPC 2.0 reply carries result or error and never both, so None here means "this reply
    is not an answer" - either it is a refusal, or its result is an off-contract type. Returning
    None for a non-mapping result rather than raising is what lets a caller state the shape
    requirement as one condition instead of guarding every field read.
    '''
    if not isinstance(envelope, dict):
        return None
    result = envelope.get("result")
    return result if isinstance(result, dict) else None


def envelope_error(envelope):
    '''Return an envelope's "error" mapping, or None when there is not one.'''
    if not isinstance(envelope, dict):
        return None
    error = envelope.get("error")
    return error if isinstance(error, dict) else None


def require_ack(curl_command, label):
    '''True only when a write was dispatched AND the plugin acknowledged it.

    "Acknowledged" is the sink's published success shape: a result member carrying
    success == True, tested identically rather than truthily so that a 1, a "true" or a missing
    member is not read as agreement.

    This exists because the alternative - dispatching a write and not looking at the reply - is
    indistinguishable from not dispatching it at all. A case that writes, reads back, and finds
    the value it expected proves nothing if the write never left the host: the value it found is
    simply the value that was already there.

    Args:
        curl_command: The write command definition.
        label: How the write should be named in a diagnostic.
    Returns:
        True on an acknowledged write; False otherwise, with the reason already logged.
    '''
    envelope = send_jsonrpc_envelope(curl_command, label)
    if envelope is None:
        return False

    error = envelope_error(envelope)
    if error is not None:
        log_error(
            f"✖ {label}: refused by the plugin "
            f"(code={sanitise_for_log(error.get('code'), max_chars=32)}, "
            f"message={sanitise_for_log(error.get('message'), max_chars=192)})"
        )
        return False

    result = envelope_result(envelope)
    if result is None:
        log_error(
            f"✖ {label}: reply carries neither an error nor a result object, so the write was "
            "not acknowledged"
        )
        return False
    if result.get("success") is not True:
        log_error(
            f"✖ {label}: not acknowledged - success="
            f"{sanitise_for_log(result.get('success'), max_chars=32)}"
        )
        return False

    log_success(f"✔ {label}: acknowledged")
    return True


def expected_request_id(curl_command):
    '''Return the JSON-RPC id a suite command definition sends, or None when there is none.

    send_curl_command already refuses a reply whose id does not match the one sent, so a caller
    never has to check correlation to be safe. This exists for the caller that has to check it
    ANYWAY - a test whose verdict is "the dispatcher rejected this specific call" cannot rest
    that verdict on a helper's internal behaviour, because a reply correlated to some other
    request would carry some other request's error. Reading the id from the command definition,
    rather than repeating the literal in the test, is what keeps the two from drifting when a
    command's id changes.

    Args:
        curl_command: Either a curl argv sequence or the command STRING form, in the same two
                      shapes send_curl_command accepts.
    Returns:
        The id value as it appears in the request body, or None when the command carries no
        parseable JSON body with an id member.
    '''
    if isinstance(curl_command, str):
        try:
            argv = shlex.split(curl_command)
        except ValueError:
            return None
    else:
        argv = list(curl_command)
    return _request_id_from_argv(argv)


def _with_http_status_write_out(argv):
    '''Return argv with "-w <status marker>" inserted, unless it already carries a -w.

    Inserted immediately after the curl binary, so it lands before any "--" and before the URL
    and can never be mistaken for the URL's option terminator.
    '''
    if any(token == "-w" or token.startswith("--write-out") for token in argv):
        return list(argv)
    return [argv[0], "-w", _HTTP_CODE_WRITE_OUT] + list(argv[1:])


def _with_validated_endpoint_and_terminator(argv):
    '''Re-validate the endpoint an argv carries and put "--" immediately before it.

    THE TWO INVARIANTS THIS FUNCTION MAKES TRUE FOR THE COMMAND-DEFINITION PATH.  _jsonrpc_argv
    and send_vcomponent_command both build their own argv and both already do these two things.
    The third transport path - send_curl_command, which dispatches the constants published by
    HdmiCECSink_Curl.py - did neither: it split or copied the command and handed it straight to
    curl.  So the module header's claim that "the option terminator '--' precedes every URL", and
    _validate_endpoint's claim that it runs "again inside every transport helper", were true of
    two paths out of three.  Both are true of all three now, and they are applied HERE rather
    than restated in 30 command constants so a new constant, or a hand-written argv from a
    caller, inherits them without having to remember anything.

    WHY THE LAST ELEMENT IS THE ENDPOINT.  That is this suite's published command contract -
    HdmiCECSink_Curl.py states it as a pass criterion ("one argument per list element and the
    endpoint last") and every one of its 30 definitions ends with WPEFRAMEWORK_JSONRPC_URL.  It
    is also checked rather than assumed: the element is passed through _validate_endpoint, so an
    argv whose last element is not a plain http/https endpoint raises ValueError and the caller
    reports a failure instead of executing something unexpected.

    WHAT "--" BUYS ON TOP OF THAT VALIDATION.  Validation already refuses a value beginning with
    "-", so the terminator is a second, independent measure rather than the only one: it means
    the endpoint is positional BY CONSTRUCTION, so no future edit to the flags in front of it can
    turn it into the argument of a preceding option, and nothing curl gains in a later version can
    reinterpret it as one.

    Idempotent: an argv that already carries a bare "--" is returned with its endpoint validated
    and its tokens untouched, so passing a command through here twice changes nothing.
    Args:
        argv: Complete argument list, endpoint last
    Returns:
        A new argv list with "--" immediately before the endpoint.
    Raises:
        ValueError: when the argv is too short to carry an endpoint, or its last element is not
                    an endpoint this module accepts.
    '''
    argv = [str(token) for token in argv]
    if len(argv) < 2:
        raise ValueError(
            "curl command carries no endpoint to dispatch: " + " ".join(argv) or "empty"
        )
    _validate_endpoint(argv[-1], "the endpoint in this curl command")
    if "--" in argv[:-1]:
        return argv
    return argv[:-1] + ["--", argv[-1]]


def send_curl_command(curl_command, timeout=None):
    '''Run a curl command and return its JSON-RPC response line as a string.

    Accepts either the complete curl command STRING that HdmiCECSink_Curl.py exports, or an
    already-built argv sequence. Either way the command is executed WITHOUT A SHELL: a
    string is split into an argv list with shlex and handed straight to a bounded subprocess, so
    no part of it - least of all the environment-derived endpoint URL appended to every
    constant in HdmiCECSink_Curl.py - can ever be interpreted as shell syntax. A URL
    carrying `;`, `&&` or `$(...)` therefore becomes inert argv text that curl rejects,
    rather than a second command that runs. Shell features (pipes, redirection, command
    substitution, globbing) are consequently not supported here, by design; nothing in this
    suite uses them.

    WHAT COUNTS AS A RESPONSE, and why the bar is where it is.  This helper used to return the
    first line of curl's output that happened to parse as JSON, having consulted neither curl's
    exit status nor the HTTP status.  Two very ordinary server behaviours defeated that:

      * a server that answers 500 (or 401, or a proxy's 502) WITH a JSON body - which is
        exactly when a server sends a body - was reported as a successful response;
      * a server that sends success-looking JSON and then stalls until curl gives up at exit 28
        was reported as a successful response, because the JSON had already been printed.

    A third, from the same family, is closed by the environment and configuration handling in
    _run_curl: a request aimed at a loopback JSON-RPC port being sent to whatever an exported
    proxy variable or a ~/.curlrc line names instead, so that a third party's document arrives
    in place of the device's answer.

    All four conditions below must therefore hold, and each is checked because the others
    cannot see its failure:

      1. curl exited 0 - so the exchange completed rather than timing out or being refused;
      2. the HTTP status is 2xx - so the request was actually served;
      3. the WHOLE body is exactly one complete JSON-RPC 2.0 envelope and nothing else - so a
         document with several JSON fragments, with an HTML error page around one of them, or
         with none at all, is not silently reduced to whichever line came first;
      4. the envelope's id matches the id the command sent, when the command carried one - so a
         stale or fabricated response cannot be attributed to this request.

    The response is returned as a raw string, not a parsed object: callers run their own
    json.loads on it so that they can distinguish a malformed payload from a missing one.  The
    string returned is the exact text this function parsed, so a caller's second parse cannot
    reach a different conclusion from this one's.
    Any failure - a command that cannot be tokenised, a curl binary that is absent, a
    transport error, a non-success status, an unparsable body, an id mismatch, a response over
    the byte ceiling, or no body at all - yields the "< No response from WPEFramework >"
    sentinel, which callers detect with response.startswith("< No response").
    Args:
        curl_command: Complete curl command string, or a sequence of argv tokens
        timeout: Optional whole-second bound for this one invocation, so a caller polling
                 against its own deadline spends only the time it still has.  Omitted, or set
                 to anything that is not a positive integer, falls back to
                 CURL_TIMEOUT_SECONDS.
    Returns:
        The single JSON-RPC envelope, as the exact stripped body text, otherwise the sentinel
        string.
    '''
    try:
        if isinstance(curl_command, (list, tuple)):
            # Already structured: use it as argv verbatim, which is the shape a caller
            # should prefer when it is building a command itself.
            argv = [str(token) for token in curl_command]
        else:
            # Respect endpoint overrides even when legacy curl strings hardcode localhost.
            #
            # For this suite the substitution is a no-op: HdmiCECSink_Curl.py composes every
            # command from WPEFRAMEWORK_JSONRPC_URL directly, so no sink command string ever
            # contains the literal below. It is retained purely as compatibility for a
            # hand-written or copied legacy command that still carries the default endpoint,
            # which keeps such a string retargetable instead of silently bypassing the
            # override contract. The literal here is a search key, not an endpoint.
            if WPEFRAMEWORK_JSONRPC_URL:
                curl_command = curl_command.replace(
                    "http://127.0.0.1:9998/jsonrpc", WPEFRAMEWORK_JSONRPC_URL
                )

            # shlex.split applies the shell's QUOTING rules without a shell being involved,
            # so the argv list matches what /bin/sh would have passed to curl while nothing
            # is left to interpret operators or expansions.
            argv = shlex.split(curl_command)

        if not argv:
            raise ValueError("empty curl command")

        expected_id = _request_id_from_argv(argv)
        # The endpoint is re-validated and made positional HERE, on the same terms the other two
        # transport helpers already applied to their own argv.  Both are applied before -w and
        # before _run_curl's "-q"/"--noproxy" prefix, all of which insert immediately after the
        # binary, so the terminator stays immediately in front of the endpoint whatever else is
        # added in front of it.  A ValueError from either lands in the handler below, which
        # already documents "an endpoint this module refuses" as one of its cases.
        argv = _with_validated_endpoint_and_terminator(argv)
        argv = _with_http_status_write_out(argv)

        # Bounded in time AND in bytes by _run_curl, which reads incrementally and kills the
        # child at the response ceiling rather than accumulating whatever the endpoint chooses
        # to send.  It also reaps the child and closes every pipe on every path.
        #
        # The budget is the caller's when it supplies one, and CURL_TIMEOUT_SECONDS otherwise.
        # A caller polling against its own deadline - Init_Devicelist_Populate's discovery and
        # seed loops are the ones that do - must be able to hand each request only the time it
        # still has, or a single request can outlive the deadline the loop is enforcing and the
        # bound becomes advisory.  _normalise_timeout is what makes an unusable value fall back
        # rather than raise, so a caller cannot shorten the budget to zero by accident.
        ok, returncode, stdout, stderr = _run_curl(
            argv, _normalise_timeout(timeout, CURL_TIMEOUT_SECONDS)
        )

        if not ok:
            detail = stderr.strip() or stdout.strip()
            log_warning(
                "Inside Utils.py : send_curl_command got no usable response - curl exited "
                f"{returncode}"
                + (f": {sanitise_for_log(detail)}" if detail else "")
            )
            return NO_RESPONSE_SENTINEL

        body, status = _split_http_status(stdout)
        if status is None:
            log_warning(
                "Inside Utils.py : send_curl_command got no HTTP status back, so no "
                "request/response exchange completed"
            )
            return NO_RESPONSE_SENTINEL
        if not 200 <= status < 300:
            snippet = body.strip()
            log_warning(
                f"Inside Utils.py : the endpoint answered HTTP {status}, which is not a success "
                f"status"
                + (f"; body: {sanitise_for_log(snippet, 200)}" if snippet else "")
            )
            return NO_RESPONSE_SENTINEL

        # ONE DOCUMENT, PARSED ONCE, IN FULL.
        #
        # This used to walk the body LINE BY LINE and collect the lines that parsed as an
        # envelope.  Everything that was not on such a line was therefore ignored: a body
        # consisting of an HTML error page, a stack trace or a second JSON document with one
        # envelope line somewhere inside it was accepted, and the envelope line alone was
        # returned as "the response".  That is a parser reading past content it does not
        # understand, and the content it skipped is exactly where a discrepancy would show.
        #
        # The whole stripped body is now parsed as a single JSON-RPC envelope.  json.loads
        # refuses trailing data, so "exactly one envelope AND NOTHING ELSE" is enforced by the
        # decode itself rather than by counting matches - and a two-envelope body, which the
        # count was there to catch, fails the same way for the same reason.  The text handed
        # back is the exact text that was parsed, so a caller re-parsing it cannot reach a
        # different conclusion from this function's.
        response_text = body.strip()
        envelope = _parse_jsonrpc_envelope(response_text)
        if envelope is None:
            log_warning(
                "Inside Utils.py : the response body is not exactly one JSON-RPC 2.0 envelope "
                "(it must be a single JSON object with \"jsonrpc\": \"2.0\", exactly one of "
                "result/error, no repeated keys and nothing before or after it)"
                + (f"; body: {sanitise_for_log(response_text, 200)}" if response_text else "")
            )
            return NO_RESPONSE_SENTINEL

        if expected_id is not None:
            if "id" not in envelope or str(envelope.get("id")) != str(expected_id):
                log_warning(
                    "Inside Utils.py : the response carried id "
                    f"{sanitise_for_log(repr(envelope.get('id')), 120)} but the request sent id "
                    f"{expected_id!r}; it does not answer this request"
                )
                return NO_RESPONSE_SENTINEL

        return response_text
    except ValueError as exc:
        # An untokenisable command, or an endpoint this module refuses.  The sentinel is
        # returned rather than an empty string, because a caller testing
        # response.startswith("< No response") must see a failure as exactly that.
        log_warning(
            "Inside Utils.py : Exception in send_curl_command function: "
            f"{sanitise_for_log(str(exc))}"
        )
        return NO_RESPONSE_SENTINEL
    except OSError as exc:
        log_warning(
            f"Inside Utils.py : send_curl_command could not run curl: {sanitise_for_log(str(exc))}"
        )
        return NO_RESPONSE_SENTINEL


def _approved_configuration_roots():
    '''Return the resolved directories a vComponent payload may be read from.

    Two roots: the suite's own vcomponent_configurations tree, and the configured command
    base (HDMICEC_CMD_BASE, which a deployment may point at /etc/hdmicec/...). Both are
    resolved, so containment is decided on canonical paths.
    '''
    roots = []
    for candidate in (_LOCAL_VCOMPONENT_BASE, Path(HDMICEC_CMD_BASE)):
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


def _approved_payload_path(yaml_file_path):
    '''Resolve a YAML command path and return it, or raise ValueError explaining the refusal.

    curl's "@path" form would happily upload any file the test user can read, so the path is
    treated as untrusted input and three independent checks are applied: the supplied path
    itself must not be a symbolic link, its canonical form must sit inside an approved
    configuration root and be a regular file, and no directory between that root and the file
    may be a symbolic link. Together they close arbitrary-file disclosure (a path such as
    /etc/shadow, or a link pointing at one) and the "link planted inside the suite tree"
    variant, whichever component the link occupies.

    These are NAME checks, and a name check is only true at the moment it runs.  What makes the
    decision hold at the moment of the read is _read_payload, which opens the returned path once
    with O_NOFOLLOW and re-validates the resulting DESCRIPTOR with fstat: a file replaced by a
    symbolic link after this function returns is refused there rather than followed.  Neither
    half is sufficient alone - this one bounds WHERE a payload may come from, that one bounds
    WHAT is actually read.
    '''
    roots = _approved_configuration_roots()
    if not roots:
        raise ValueError(
            "no vComponent configuration root is available; expected "
            f"{_LOCAL_VCOMPONENT_BASE} or {HDMICEC_CMD_BASE}"
        )

    # The supplied path is examined BEFORE resolution: resolve() follows links, so a check
    # made afterwards could never see one.
    supplied = Path(os.path.abspath(yaml_file_path))
    if supplied.is_symlink():
        raise ValueError(
            f"refused to post {yaml_file_path}: {supplied} is a symbolic link"
        )

    try:
        resolved = supplied.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"YAML file not found: {yaml_file_path}") from exc

    container = None
    for root in roots:
        if resolved == root or root in resolved.parents:
            container = root
            break
    if container is None:
        raise ValueError(
            f"refused to post {yaml_file_path}: it resolves to {resolved}, outside the "
            f"approved vComponent configuration roots {[str(root) for root in roots]}"
        )

    # A symbolic link standing in for one of the directories between the root and the file
    # would otherwise smuggle in a path the containment check above cannot see, because by
    # then it has already been followed.
    try:
        relative = supplied.relative_to(container)
    except ValueError:
        relative = None
    if relative is not None:
        walked = container
        for part in relative.parts:
            walked = walked / part
            if walked.is_symlink():
                raise ValueError(
                    f"refused to post {yaml_file_path}: {walked} is a symbolic link"
                )

    if not resolved.is_file():
        raise ValueError(f"refused to post {yaml_file_path}: {resolved} is not a regular file")

    return resolved


def _read_payload(path):
    '''Read an approved YAML payload through ONE descriptor, validated after it is opened.

    THE RACE THIS CLOSES.  _approved_payload_path decides that a path is acceptable by
    inspecting the NAME - is it a symlink, does it resolve inside an approved root, is it a
    regular file.  Opening the same name afterwards is a SECOND resolution of it, and between
    the two anything that can write the containing directory can replace the file with a
    symbolic link to somewhere else.  The checks would all have passed on the file that was
    there; the bytes posted to the vComponent endpoint would come from the file that is there
    now - any file the test identity can read, /etc/shadow included on a suite running as root.

    So the file is opened ONCE with O_NOFOLLOW, and every remaining decision is made on that
    DESCRIPTOR rather than on the path:

      * O_NOFOLLOW makes the open itself fail with ELOOP if the final component is a symbolic
        link, so a link swapped in after the name checks is refused rather than followed.
      * O_NONBLOCK stops the open itself from blocking on a named pipe: a FIFO opened read-only
        without it waits in open() until a writer appears, so a FIFO swapped in after the name
        checks would hang the suite BEFORE the fstat below could refuse it.  With it, the open
        returns and the S_ISREG check does the refusing.  On a regular file it changes nothing.
      * O_CLOEXEC keeps the descriptor out of the curl this module is about to spawn; the
        payload is delivered on curl's stdin, so curl has no business holding the file too.
      * fstat on the open descriptor - not stat on the path - confirms it is a regular file and
        is within the cap.  A descriptor cannot be substituted once it is open, so what is
        measured here and what is read below are the same object by construction.
      * the read is bounded, and re-checked as it goes, because st_size is a snapshot that a
        concurrent writer can grow underneath the loop.

    Raises ValueError with the reason on any refusal, which send_vcomponent_command turns into
    a (0, diagnostic) result rather than a post.
    '''
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError as exc:
        # ELOOP here is the interesting one: it means a symbolic link now stands at a path this
        # module had already accepted as a regular file.
        raise ValueError(
            f"refused to post {path}: could not open it safely ({exc.strerror}); ELOOP means a "
            "symbolic link now stands at that path"
        ) from exc

    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(
                f"refused to post {path}: the open descriptor is not a regular file"
            )
        if info.st_size > _VCOMPONENT_MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"refused to post {path}: {info.st_size} bytes, larger than the "
                f"{_VCOMPONENT_MAX_PAYLOAD_BYTES} byte cap"
            )

        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > _VCOMPONENT_MAX_PAYLOAD_BYTES:
                raise ValueError(
                    f"refused to post {path}: it grew past the "
                    f"{_VCOMPONENT_MAX_PAYLOAD_BYTES} byte cap while being read"
                )
            chunks.append(chunk)
    finally:
        os.close(fd)

    return b"".join(chunks)


def read_fixture_text(path, max_bytes=_VCOMPONENT_MAX_PAYLOAD_BYTES):
    '''Read a vComponent fixture as text through ONE descriptor opened with O_NOFOLLOW.

    WHY THIS EXISTS ALONGSIDE _read_payload.  _read_payload is for a document about to be POSTED
    to the vComponent endpoint, so it also insists the path resolve inside an approved root.
    Several places instead read a fixture only to DERIVE AN EXPECTATION from it - the seed
    payload verifier and the topology cross-check in Init_Devicelist_Populate, and the power-status
    byte TCID24 asserts on - and those used a plain open(), which follows a symbolic link at the
    final component.  Nothing is posted and no trust boundary is crossed there (the paths are ones
    the suite itself wrote), so this was hardening rather than a hole; but the module states a
    posture of opening fixtures with O_NOFOLLOW and validating the descriptor, and a read that
    quietly does otherwise makes that statement false. One helper, used by all four call sites,
    keeps the posture and the code in step.

    The guarantees, in the same order _read_payload establishes them:
      * O_NOFOLLOW makes the open itself fail with ELOOP when the final component is a symbolic
        link, so a link swapped in for a fixture is refused rather than followed;
      * O_NONBLOCK is what makes the S_ISREG check below reachable AT ALL for a named pipe:
        opening a FIFO read-only WITHOUT it blocks in open() until a writer appears, so a FIFO
        planted where a fixture belongs would hang this suite for ever before any check ran -
        measured, not theorised (an earlier draft of this helper hung on exactly that).  On a
        regular file it has no effect on the reads below;
      * O_CLOEXEC keeps the descriptor out of any child this suite spawns;
      * fstat on the OPEN DESCRIPTOR - not stat on the path - confirms it is a regular file, so a
        FIFO or a directory standing at the path is refused rather than read;
      * the read is bounded and re-checked as it goes, because st_size is a snapshot a concurrent
        writer can grow underneath the loop.

    Every refusal is raised as an OSError, which is exactly what a plain open() would have raised
    for an unreadable path - so the existing `except OSError` at each call site reports it with
    the message it already had, and no call site had to change its error handling.
    Args:
        path: Absolute path of the fixture to read
        max_bytes: Ceiling on the bytes read, defaulting to the vComponent payload cap
    Returns:
        The file's contents decoded as UTF-8 text.
    Raises:
        OSError: when the path cannot be opened safely (ELOOP for a symlink), is not a regular
                 file, or exceeds the ceiling.
        UnicodeDecodeError: when the bytes are not valid UTF-8, as a text-mode open() would.
    '''
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(
                errno.EINVAL,
                f"not a regular file (mode {info.st_mode:o}); refusing to read it as a fixture",
                path,
            )
        if info.st_size > max_bytes:
            raise OSError(
                errno.EFBIG,
                f"{info.st_size} bytes, larger than the {max_bytes} byte fixture ceiling",
                path,
            )
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise OSError(
                    errno.EFBIG,
                    f"grew past the {max_bytes} byte fixture ceiling while being read",
                    path,
                )
            chunks.append(chunk)
    finally:
        os.close(fd)
    return b"".join(chunks).decode("utf-8")


def send_vcomponent_command(yaml_file_path, timeout=10):
    '''Post a YAML command file to the vComponent HTTP API.
    Uses: curl -sS -X POST -H "Content-Type: application/x-yaml"
               --data-binary @- <VCOMPONENT_API_URL>   (payload on stdin)
    Returns (http_code: int, body: str) tuple.
    http_code 200 indicates success.

    The YAML payload is posted verbatim, read by this module from a path it has approved
    rather than handed to curl as a filename, so no caller can turn the helper into a
    file-disclosure primitive. This suite carries no key-rewriting or alternate-plugin
    fallback path, and no curl exit status is reinterpreted, so the code a caller receives
    reflects what the vComponent actually answered: an absent, silent or failing vComponent
    is never reported as success.
    Args:
        yaml_file_path: Path to a YAML command document inside the suite's
                        vcomponent_configurations tree (or the configured HDMICEC_CMD_BASE)
        timeout: curl --max-time budget in seconds
    Returns:
        (code, body) where code is the HTTP status the vComponent actually returned - 200
        when it accepted the payload - and 0 when the request never completed, the file is
        missing, the path was refused, or curl itself failed. body carries the response or
        the diagnostic explaining the refusal.
    '''
    budget = _normalise_timeout(timeout, default=10)

    def _post_payload(payload):
        url = _validate_endpoint(VCOMPONENT_API_URL, "VCOMPONENT_API_URL")
        cmd = [
            "curl", "-sS", "-w", "\n%{http_code}",
            "--connect-timeout", str(min(_CONNECT_TIMEOUT_SECONDS, budget)),
            "--max-time", str(budget),
            "-X", "POST",
            "-H", "Content-Type: application/x-yaml",
            "--data-binary", "@-",
            "--",
            url,
        ]

        ok, returncode, stdout, stderr = _run_curl(cmd, budget, input_bytes=payload)
        if not ok:
            # Every curl transport failure - refused connection, empty reply, timeout - is a
            # failure. Reporting one as an HTTP 200 would manufacture a pass out of a server
            # that never answered.
            #
            # The one case worth naming, because it is the reason a synthetic 200 is tempting:
            # some vComponent builds apply the posted YAML and then close the connection
            # without answering, which curl reports as CURLE_GOT_NOTHING (exit 52, "Empty
            # reply from server").  Such a run really may have taken effect - but the server
            # said nothing, so this returns 0 with curl's own diagnosis and lets the caller
            # decide, rather than inventing a status the vComponent never sent.  A caller that
            # wants to proceed on that specific case can test for `curl exited 52` in the body
            # and then verify the effect through the middleware APIs.
            detail = stderr.strip() or stdout.strip() or "no diagnostic"
            return 0, f"curl exited {returncode}: {sanitise_for_log(detail)}"

        # curl output format is: <body>\n<http_code> from "-w \n%{http_code}"
        # Keep split robust even when body is empty (e.g. "\n200").
        parts = stdout.rsplit("\n", 1)
        if len(parts) == 2:
            body = parts[0]
            http_code_str = parts[1].strip()
        else:
            body = stdout.strip()
            http_code_str = "0"
        try:
            http_code = int(http_code_str)
        except ValueError:
            http_code = 0
        if http_code == 0:
            detail = stderr.strip()
            if detail:
                body = detail
        return http_code, body

    try:
        # Containment before the file is read or posted anywhere.
        #
        # The path a caller passes is normally HDMICEC_CMD_BASE joined with a fixed filename from
        # a test-case module, but HDMICEC_CMD_BASE is environment-overridable and the filename
        # arrives as a plain string, so `../` segments can reach outside the suite. The exposure is
        # already narrow - the argv form below means no shell is involved and the payload is only
        # ever POSTed, never executed - but "narrow" is not "bounded". _approved_payload_path makes
        # it bounded: it resolves the path first, so symlinks and `..` are collapsed before any
        # comparison, then requires the result to sit under this suite's own configuration tree or
        # under the configured command base, and to be a regular file reached through no symbolic
        # link at any component.
        approved = _approved_payload_path(yaml_file_path)
        payload = _read_payload(approved)
    except ValueError as exc:
        return 0, str(exc)
    except OSError as exc:
        return 0, f"could not read {yaml_file_path}: {exc}"

    try:
        return _post_payload(payload)
    except ValueError as exc:
        # A rejected endpoint is a configuration defect, reported rather than dispatched.
        # Routed through log_error rather than print, because the message interpolates the
        # exception text and an endpoint value can reach that text: a bare print would put
        # whatever control bytes it carries straight onto the terminal that IS this run's only
        # evidence.  log_* applies _guard_log_line, and sanitise_for_log bounds and escapes the
        # remote-derived part on top of it.
        log_error(
            "Inside Utils.py : Exception in send_vcomponent_command: "
            f"{sanitise_for_log(str(exc))}"
        )
        return 0, str(exc)


def await_plugin_ready(callsign, timeout=30.0, recheck_interval=0.5):
    '''Block until the controller reports the plugin activated, or the deadline expires.

    Activation is asynchronous with respect to Controller.1.activate: the call returns once the
    request is accepted, while Initialize() and the plugin's own worker threads come up afterwards.
    The state that matters is therefore an observable one - Controller.1.status@<callsign> reports
    it - so this waits for that state instead of guessing how long it takes.

    The status is read BEFORE any wait, so a plugin that is already up costs nothing, and expiry is
    returned rather than swallowed: recheck_interval is the interval between two readings of an
    observable state, and timeout is a failure deadline.

    Args:
        callsign: Plugin callsign, e.g. "org.rdk.HdmiCecSink"
        timeout: Failure deadline in seconds. Returning False means the plugin never reported
            itself activated within it, which is a condition the caller must handle.
        recheck_interval: Seconds between two readings of Controller.1.status.
    Returns:
        True once the controller reports the plugin activated; False on expiry, or when the
        controller could not be reached or answered without a usable state.
    '''
    # time.monotonic, not time.time.  This is a DURATION being measured, and time.time is the
    # wall clock: NTP stepping it, or a container's clock being corrected after start-up, moves it
    # backwards or forwards under a loop that is comparing against a stored value.  Backwards
    # turns a 30-second deadline into an arbitrarily long one; forwards expires it immediately and
    # reports a healthy plugin as never activated.  time.monotonic cannot be stepped, so the only
    # thing the deadline can be affected by is time actually passing.  The same substitution is
    # made in every other deadline loop in this suite for the same reason.
    deadline = time.monotonic() + max(0.0, float(timeout))
    interval = max(0.05, float(recheck_interval))
    while True:
        response = send_jsonrpc_command(f"Controller.1.status@{callsign}")
        if response and "error" not in response:
            if _reports_activated(response.get("result")):
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def _reports_activated(result):
    '''True when a Controller.1.status result says the plugin is activated.

    Thunder answers with a list of service descriptors, but a single object is accepted too so a
    framework revision that returns one is not misread as "not ready". Any other shape, and any
    state other than "activated", reads as not ready rather than as an error - the caller's
    deadline is what turns a persistent not-ready into a failure.
    '''
    if isinstance(result, dict):
        entries = [result]
    elif isinstance(result, list):
        entries = [entry for entry in result if isinstance(entry, dict)]
    else:
        return False
    for entry in entries:
        state = entry.get("state")
        if isinstance(state, str) and state.strip().lower() == "activated":
            return True
    return False


def is_plain_int(value):
    '''True for an integer that is not a boolean.

    THE REASON THIS EXISTS RATHER THAN isinstance(value, int) AT EACH SITE. In Python bool is a
    SUBCLASS of int, so isinstance(True, int) is True and True >= 1 is True. A field validated with
    a bare isinstance(..., int) therefore accepts a JSON boolean wherever it means to require a
    number - so a plugin answering {"numberofdevices": true} or a device entry carrying
    {"logicalAddress": false} passes a count check and a logical-address check that were written to
    reject exactly that. The suite validates numeric fields in several cases, so the rejection is
    defined once here and used at every one of them rather than restated and eventually forgotten.

    Args:
        value: Any parsed JSON value.
    Returns:
        True only for an int that is not a bool. Floats are refused too: the fields this guards -
        device counts and logical addresses - are integers in the published contract, and accepting
        3.0 where 3 is required would let an off-contract reply read as conforming.
    '''
    return isinstance(value, int) and not isinstance(value, bool)


def device_inventory(get_device_list_command):
    '''Read the CEC device population as a comparable snapshot.

    THE ONE INVENTORY HELPER FOR THE WHOLE SUITE, and it is here rather than in each case that
    needs it because several cases assert the SAME invariant - "the API under test did not disturb
    the device population" - and two copies of an inventory reader would be two definitions of what
    the population IS. Four cases used to call a `_device_inventory()` that existed in none of them,
    so the invariant they documented was never actually evaluated; this is that helper, defined once.

    The snapshot is (count, addresses) rather than the raw list on purpose. The plugin's device
    records carry fields that legitimately change while the POPULATION does not - osdName and
    vendorID arrive on later frames, powerStatus follows a peer's own state - so comparing whole
    records would report those as inventory churn. The reported count and the sorted set of logical
    addresses are the two properties that describe the population itself, and a frozenset makes the
    comparison order-insensitive, which matters because the plugin does not promise an order.

    Args:
        get_device_list_command: The getDeviceList request, as the suite's command module exports
                                 it. Passed in rather than composed here so this module stays free
                                 of any particular plugin's method names, exactly as
                                 activate_plugin() takes its callsign.
    Returns:
        (readable, count, addresses):
          * readable is False for every unusable reply - a request that was not dispatched, the
            no-response sentinel, a body that does not parse, a non-object envelope, a result that
            is not an object, a success member that is not True, or a deviceList that is not a
            list. A caller must treat False as "no invariant can be asserted", never as an empty
            population;
          * count is the reported numberofdevices, unchanged, or None when unreadable;
          * addresses is a frozenset of the integer logicalAddress values, or an empty frozenset
            when unreadable. Entries that are not objects, and objects whose logicalAddress is not
            an int, are skipped - the set is only ever keyed by something a caller can look up.
    '''
    response = send_curl_command(get_device_list_command)
    # NO_RESPONSE_SENTINEL is truthy, so the falsy check alone lets a transport failure through as
    # if it were a reply. startswith("< No response") is the suite-wide detection idiom for it.
    if not response or response.startswith("< No response"):
        return False, None, frozenset()
    try:
        envelope = json.loads(response)
    except json.JSONDecodeError:
        return False, None, frozenset()
    if not isinstance(envelope, dict):
        return False, None, frozenset()
    result = envelope.get("result")
    if not isinstance(result, dict) or result.get("success") is not True:
        return False, None, frozenset()
    device_list = result.get("deviceList")
    if not isinstance(device_list, list):
        return False, None, frozenset()
    addresses = frozenset(
        device["logicalAddress"]
        for device in device_list
        if isinstance(device, dict) and is_plain_int(device.get("logicalAddress"))
    )
    return True, result.get("numberofdevices"), addresses
