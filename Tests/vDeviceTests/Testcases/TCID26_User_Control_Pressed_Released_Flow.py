"""
/**
 * @file TCID26_User_Control_Pressed_Released_Flow.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID26_User_Control_Pressed_Released_Flow
 * @details Exercises the sink's user-control path in both directions, and carries this
 *          suite's device-level boundary-value coverage for it.
 *
 *          Outbound leg: org.rdk.HdmiCecSink.sendUserControlPressed is dispatched over
 *          JSON-RPC and its success acknowledgement asserted, then
 *          org.rdk.HdmiCecSink.sendUserControlReleased is dispatched and asserted in turn.
 *          The two APIs are asymmetric by contract - pressed carries a key code alongside
 *          the logical address, released carries the logical address alone - and both are
 *          driven from the command constants in HdmiCECSink_Curl.py, so no address or key
 *          code is restated here and neither can drift out of step with the fixtures.
 *
 *          Inbound leg: three UserControlPressed frames are injected through the vComponent
 *          emulation API, each closed by a UserControlReleased frame. The three key codes
 *          are the NOMINAL value, the MINIMUM value and the upper BYTE BOUNDARY value, which
 *          is the same three-point sweep the sink L1 suite already applies to these two APIs
 *          as sendUserControlPressed_MinKeyCode and sendUserControlPressed_BoundaryKeyCode
 *          (and their sendUserControlReleased_ counterparts). Reusing that idiom at device
 *          level is deliberate: it is the established repository convention for a
 *          parameterised API rather than a shape invented here.
 *
 *          The rejected-argument half of the boundary set is deliberately NOT attempted at
 *          this level and is not missing from the estate: sendUserControlPressed and
 *          sendUserControlReleased are each already asserted at L1 with
 *          _InvalidLogicalAddress, _InvalidKeyCode, _MissingParams, _MalformedJSON,
 *          _NegativeValues and _StringValues variants. Those cases need to observe a
 *          REJECTION, and this suite's command constants expose only well-formed requests,
 *          so duplicating them here would add no coverage and could only weaken the split.
 *
 *          Closing probe: getDeviceList is read once at the end as a liveness check. It is
 *          not a key-delivery assertion, as the expected-result section below sets out, but a
 *          burst of six injected frames that left the plugin unable to answer would be a
 *          genuine regression, and this is the only consequence of the flow that the L3
 *          transport can observe.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - is running WPEFramework
 *    with the org.rdk.HdmiCecSink plugin activated and reachable over JSON-RPC.
 *  - Init_Devicelist_Populate has seeded the CEC topology, so the logical address carried by
 *    the outbound command constants resolves to a real emulated peer - the Audio System,
 *    which is this suite's bootstrap peer - rather than to an empty address.
 *  - The vComponent emulation API is reachable, since the three inbound key codes arrive as
 *    posted YAML command documents rather than as anything this module builds itself.
 *  - No continuous integration workflow in this repository executes this suite; this case is
 *    authored for device-level execution and has not been run.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - Both outbound calls are acknowledged with {"success": true}, all six injected frames
 *    are accepted with HTTP 200, and the closing getDeviceList probe still answers.
 *  - The OnKeyPressEvent and OnKeyReleaseEvent notifications the injected frames provoke are
 *    NOT observable at this level and nothing is asserted about them. This suite reaches the
 *    plugin over one-shot curl, which cannot subscribe to a Thunder notification channel, so
 *    an event assertion here would be unfounded. That is a limit of THIS level, not a gap in
 *    the estate: both events are asserted by the sink's own suites - L1
 *    onKeyPressEvent_SubscribedClient_ReceivesAddressAndKeyCode,
 *    onKeyPressEvent_BoundaryOperands_AreForwardedVerbatim,
 *    onKeyPressEvent_NoSubscriber_ProducesNoClientNotification and
 *    onKeyReleaseEvent_SubscribedClient_ReceivesLogicalAddress, and L2
 *    InjectUserControlPressedFrameAndVerifyEvent (with minimum, maximum-named and
 *    out-of-range key-code variants) and InjectUserControlReleasedFrameAndVerifyEvent. Where
 *    the coverage register still lists them among the events uncovered even by the sink's own
 *    L2 suite, that entry is the register's PRE-CHANGE BASELINE.
 *
 * @pass_criteria
 *  - All six required YAML posts return HTTP 200, both JSON-RPC calls acknowledge
 *    {"success": true}, the closing probe parses as an object whose result carries
 *    success true and an integer numberofdevices, the guaranteed closing
 *    UserControlReleased cleanup is accepted, and run_test() returns True.
 *
 * @failure_criteria
 *  - A response mismatch, a failed or silently skipped emulation post, a JSON parsing
 *    failure, an unreachable endpoint or an unavailable device-level prerequisite;
 *    run_test() then returns False.
 *  - The cleanup operation (the closing UserControlReleased) cannot be confirmed, which is reported
 *    as its own finding and fails this case even when every measurement above holds.
 */
"""


import time
import re
import json
from pathlib import Path

from utils import (
    send_curl_command,
    send_vcomponent_command,
    sanitise_for_log,
    HDMICEC_CMD_BASE,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing,
    CEC_FRAME_PACING_SECONDS,
)
import HdmiCECSink_Curl as HdmiCecSinkApis


def _post_hdmicec(yaml_file):
    """Post a HdmiCec vComponent YAML command."""
    http_code, body = send_vcomponent_command(f"{HDMICEC_CMD_BASE}/{yaml_file}")
    log_info(f"  vComponent POST {yaml_file}: HTTP {http_code}  {sanitise_for_log(body)}")
    return http_code == 200


def _result_object(response_text):
    """Return the JSON-RPC result mapping from a response body, or an empty mapping.

    A JSON-RPC error envelope carries "error" instead of "result", and a malformed body could
    carry a non-object "result" or not be an object at all. Every such case collapses to {} so
    the caller reports a MISSING FIELD rather than raising AttributeError out of run_test(),
    which owes its caller a bool on every path. A body that is not JSON at all still raises
    json.JSONDecodeError, which run_test() handles as the documented failure. Three call sites
    share this - the two outbound acknowledgements and the closing probe - which is why it is
    factored out here, in the idiom TCID23_Short_Audio_Descriptor_Flow established.
    Args:
        response_text: Raw response string as returned by utils.send_curl_command
    Returns:
        The "result" mapping when the body is a JSON object carrying one, otherwise {}.
    """
    body = json.loads(response_text)
    if not isinstance(body, dict):
        return {}
    result = body.get("result")
    return result if isinstance(result, dict) else {}


# FIXTURE NAMES ARE LOAD-BEARING, AND A MISSPELLING IS SILENT AT THE POINT OF USE. utils
# resolves the name against HDMICEC_CMD_BASE and returns (0, "YAML file not found: <path>")
# when the document does not exist, so a wrong name does not raise - it merely fails its post.
# That matters more on this module than on any other in the suite, because this is the module
# that carries the boundary sweep: a silently skipped Min or Boundary post would quietly
# reduce the sweep to the nominal case while every remaining check still passed, and the
# missing coverage would be invisible in a green log. Every post below is therefore captured
# into a named flag and all six are required together rather than fired and forgotten. The
# four filenames used here were verified against vcomponent_configurations/commands/ on disk.
#
# The body is logged but never parsed. utils reports the status the vComponent actually
# returned and is fail-closed about it: a silent, refused or failing vComponent yields 0
# together with curl's own diagnosis rather than a manufactured 200, and even a genuine 200
# may carry an empty body. `body` is therefore diagnostic text for a human reading the log,
# never a JSON document to decode.


# FRAMING OF THE SIX INJECTED DOCUMENTS - DIRECTED FROM LOGICAL ADDRESS 5, AND CHOSEN, NOT
# INHERITED.
#
# run_test() posts the Device_-prefixed documents, whose payloads are directed with header
# 0x50 (initiator 5, destination 0). Process_-prefixed equivalents exist beside them -
# Process_User_Control_Pressed and Process_User_Control_Released, header 0x40, initiator 4 -
# and the sink handlers would accept either, because process(UserControlPressed) and
# process(UserControlReleased) apply no destination filter. So this is a genuine choice, and
# it is settled by the topology rather than by taste: Init_Devicelist_Populate seeds the audio
# system at logical address 5 as this suite's bootstrap peer, and the sink's outbound key-event
# constants in HdmiCECSink_Curl.py target that same address. Injecting from 5 therefore keeps
# both legs of this flow describing one conversation with one device. Address 4 also holds a
# seeded peer - the SONY playback device - so a frame from 4 would be legitimate too; it would
# simply describe a second device, which is not what this sweep is comparing.
#
# One family is used throughout for that reason. Do not mix the two sets below: the point of
# the sweep is that the three documents differ ONLY in their key-code operand, so changing
# the header on one of them would turn a controlled comparison into two unrelated variables.


# THE OPCODE THE THREE PRESS FIXTURES ARE REQUIRED TO CARRY. CEC <User Control Pressed> is 0x44 and
# <User Control Released> is 0x45; the sink dispatches them at
# HdmiCecSinkImplementation.cpp:295-305. Both are named here so _verify_fixture_sweep can require the
# fixtures to be what this module says they are, rather than posting whatever the documents happen to
# contain.
OPCODE_USER_CONTROL_PRESSED = 0x44
OPCODE_USER_CONTROL_RELEASED = 0x45

# THE THREE-POINT SWEEP, AND THE ONE DOCUMENT THAT CLOSES EACH OF ITS PRESSES. The key codes live in
# the YAML documents and nowhere else, so no operand value appears in this file: adding a fourth key
# code means adding a fourth fixture and naming it here, which is the intended cost. The description
# beside each filename is what the diagnostics call it, so a refused post names the arm of the sweep
# that was lost rather than a filename a reader has to map back.
PRESS_FIXTURES = (
    ("Device_User_Control_Pressed.yaml", "the nominal key code"),
    ("Device_User_Control_Pressed_Min.yaml", "the minimum key code"),
    ("Device_User_Control_Pressed_Boundary.yaml", "the boundary key code"),
)
RELEASE_FIXTURE = "Device_User_Control_Released.yaml"

# Bounded budget for the closing inventory observation. A poll ceiling, never a duration anything
# waits out: it returns the moment the inventory agrees and reports its last sample on expiry.
OBSERVE_TIMEOUT_S = 15.0
OBSERVE_POLL_S = 0.5

# The press this module currently has outstanding, as the description a diagnostic should use, or
# None when every press it has issued has been closed. Read by _ensure_key_released so the guaranteed
# closing release can say whether it actually closed something or was the harmless no-op it usually
# is - which is the difference between "this case cleaned up after an early exit" and "this case
# completed its own pairing".
_press_outstanding = None

# Matches the payload list a vComponent cec_message document declares, so an expectation can be
# DERIVED from the frame each fixture actually carries instead of restated beside it - the same
# technique Init_Devicelist_Populate.verify_seed_payload_consistency() uses on the seed payloads.
_PAYLOAD_PATTERN = re.compile(r'payload:\s*\[(.*?)\]', re.S)


def _payload_bytes(yaml_name):
    """Return the CEC frame bytes a fixture declares, or None with a reason.

    Args:
        yaml_name: Command-document filename relative to utils.HDMICEC_CMD_BASE.
    Returns:
        (list_of_ints, None) on success, or (None, reason).
    """
    path = Path(HDMICEC_CMD_BASE) / yaml_name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"cannot read {yaml_name}: {exc}"
    match = _PAYLOAD_PATTERN.search(text)
    if not match:
        return None, f"{yaml_name} declares no payload list"
    values = []
    for token in match.group(1).split(","):
        token = token.strip().strip('"').strip("'")
        if not token:
            continue
        try:
            values.append(int(token, 16))
        except ValueError:
            return None, f"{yaml_name} carries a non-hexadecimal payload byte {token!r}"
    return values, None


def _verify_fixture_sweep():
    """Prove the three press fixtures form a genuine sweep before any frame is injected.

    WHAT A SWEEP HAS TO BE FOR THE COMPARISON TO MEAN ANYTHING. The three documents must differ in
    exactly one variable - the key-code operand - so this checks all four conditions that make that
    true, and reports which one failed:

      * every press fixture carries at least a header, the <User Control Pressed> opcode and a key
        code, so a truncated document is not posted as though it were a key press;
      * all three declare the SAME header, so the sweep is one peer pressing three keys rather than
        three peers pressing one each;
      * all three declare opcode 0x44, so a document re-purposed to another opcode is refused
        instead of quietly leaving the sweep one arm short;
      * the three key codes are DISTINCT, which is the entire point - two fixtures sharing an
        operand would make the sweep a two-point one while every check downstream still passed.

    The closing release document is checked against the same header and its own opcode, because a
    release framed from another initiator would not close the presses it follows.
    Returns:
        (key_codes, None) with the three codes in fixture order, or (None, reason).
    """
    headers = {}
    key_codes = []
    for yaml_name, description in PRESS_FIXTURES:
        payload, reason = _payload_bytes(yaml_name)
        if payload is None:
            return None, reason
        if len(payload) < 3:
            return None, (
                f"{yaml_name} ({description}) declares {len(payload)} payload byte(s); a "
                "<User Control Pressed> frame needs a header, an opcode and a key code"
            )
        if payload[1] != OPCODE_USER_CONTROL_PRESSED:
            return None, (
                f"{yaml_name} ({description}) carries opcode 0x{payload[1]:02X}, not the "
                f"<User Control Pressed> 0x{OPCODE_USER_CONTROL_PRESSED:02X} this sweep injects"
            )
        headers[yaml_name] = payload[0]
        key_codes.append(payload[2])

    release_payload, reason = _payload_bytes(RELEASE_FIXTURE)
    if release_payload is None:
        return None, reason
    if len(release_payload) < 2:
        return None, (
            f"{RELEASE_FIXTURE} declares {len(release_payload)} payload byte(s); a "
            "<User Control Released> frame needs a header and an opcode"
        )
    if release_payload[1] != OPCODE_USER_CONTROL_RELEASED:
        return None, (
            f"{RELEASE_FIXTURE} carries opcode 0x{release_payload[1]:02X}, not the "
            f"<User Control Released> 0x{OPCODE_USER_CONTROL_RELEASED:02X} that closes a press"
        )
    headers[RELEASE_FIXTURE] = release_payload[0]

    distinct_headers = set(headers.values())
    if len(distinct_headers) != 1:
        return None, (
            "the injected documents do not share one header, so the sweep would not be one peer "
            f"pressing three keys: {{{', '.join(f'{name}: 0x{value:02X}' for name, value in headers.items())}}}"
        )

    if len(set(key_codes)) != len(key_codes):
        return None, (
            f"the three press fixtures do not carry distinct key codes "
            f"({[f'0x{code:02X}' for code in key_codes]}), so the sweep covers fewer points than "
            "it reports"
        )

    return key_codes, None


def _published_request(argv):
    """Decode the JSON-RPC request a HdmiCECSink_Curl constant carries, or None with a reason.

    The payload sits in the argv element after "-d". Decoding it means the logical address this
    module checks the topology for is DERIVED from the constants it actually sends, rather than
    restated beside them where it could drift from them unnoticed.
    Args:
        argv: A command definition from HdmiCECSink_Curl.py, in argv form.
    Returns:
        (request_mapping, None) on success, or (None, reason).
    """
    try:
        payload = argv[argv.index("-d") + 1]
    except (ValueError, IndexError):
        return None, "the command constant carries no -d payload"
    try:
        request = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, f"the command constant's -d payload is not valid JSON: {exc}"
    if not isinstance(request, dict):
        return None, "the command constant's -d payload is not a JSON object"
    return request, None


def _acknowledged(argv, label):
    """Dispatch one published call and report whether it acknowledged success.

    Both outbound user-control methods answer with success alone - sendUserControlPressed takes a
    logical address and a key code, sendUserControlReleased the address only (IHdmiCecSink.h:275,
    :281) - so the acknowledgement is the whole of what either can be asserted on, and a call whose
    reply is discarded is indistinguishable from one that never left the host.

    Args:
        argv: A command definition from HdmiCECSink_Curl.py.
        label: How the call should be named in the diagnostics.
    Returns:
        True when the reply is a JSON-RPC result reporting success True; False otherwise, with the
        reason already logged.
    """
    response = send_curl_command(argv)
    if not response:
        log_error(f"✖ {label} command not sent")
        return False
    # send_curl_command reports a transport failure by RETURNING the truthy sentinel
    # "< No response from WPEFramework >", so an emptiness test alone would read a dead endpoint as
    # a healthy one.
    if response.startswith("< No response"):
        log_error(f"✖ no response from WPEFramework for {label}")
        return False
    log_warning(f"  {label} response: {sanitise_for_log(response)}")
    try:
        result = _result_object(response)
    except json.JSONDecodeError:
        log_error(f"✖ {label} reply is not valid JSON")
        return False
    if result.get("success") is not True:
        log_error(
            f"✖ {label} did not acknowledge success "
            f"(success={sanitise_for_log(result.get('success'), max_chars=32)})"
        )
        return False
    log_success(f"✔ {label} acknowledged")
    return True


def _ensure_key_released():
    """Inject a closing UserControlReleased frame and report whether it was accepted.

    Returns (ok, detail).

    The flow pairs every injected press with an injected release, which is what keeps it
    state-neutral on the happy path. But a press and its release are two separate posts with
    guards between them, so any early return in between - a rejected post, an unacknowledged
    outbound call, an exception - left a key HELD DOWN on the sink. That is precisely the
    stuck-key fault the coverage register's OnKeyReleaseEvent rationale warns about, and it
    would leak into whichever case the suite runs next.

    The release is therefore also issued from run_test()'s finally block, on every path. A
    release with no outstanding press is harmless - process(UserControlReleased) simply clears a
    state that is already clear - so the extra post costs nothing and removes the need to reason
    about which exit path was taken.
    """
    global _press_outstanding
    outstanding = _press_outstanding
    _press_outstanding = None

    if _post_hdmicec(RELEASE_FIXTURE):
        if outstanding is None:
            return True, "closing UserControlReleased injected; no press was outstanding"
        return True, (
            f"closing UserControlReleased injected; it closed the press left outstanding by "
            f"{outstanding}"
        )
    if outstanding is None:
        return False, (
            "the closing UserControlReleased frame was not accepted by the emulator; no press was "
            "outstanding, so no key is held, but the emulator refused a post"
        )
    return False, (
        "the closing UserControlReleased frame was not accepted by the emulator and "
        f"{outstanding} is still outstanding, so a key may be held down for subsequent cases"
    )


def _device_inventory():
    '''Return (readable, count, sorted_logical_addresses) from the published getDeviceList method.

    readable is False when the reply could not be read as a JSON-RPC result reporting success,
    which is deliberately distinct from an empty inventory.
    '''
    response = send_curl_command(HdmiCecSinkApis.get_device_list)
    if not response or response.startswith("< No response"):
        return False, None, None
    try:
        result = _result_object(response)
    except json.JSONDecodeError:
        return False, None, None
    if result.get("success") is not True:
        return False, None, None
    device_list = result.get("deviceList")
    if not isinstance(device_list, list):
        return False, None, None
    addresses = sorted(
        device["logicalAddress"]
        for device in device_list
        if isinstance(device, dict) and isinstance(device.get("logicalAddress"), int)
    )
    return True, result.get("numberofdevices"), addresses

def run_test():
    '''Drive the outbound user-control pair, sweep three inbound key codes, verify liveness.

    Every injected press is closed by an injected release inside the flow, and a further
    release is issued from the finally block below so that no exit path - early return or
    exception - can leave a key held down on the sink. The restoration reports its own verdict
    and this case fails if either half fails.
    Returns:
        True when both outbound calls are acknowledged, all six emulation posts are accepted,
        the closing probe reports success with an integer device count, and the guaranteed
        closing release is accepted; False on a transport failure, a failed post, a response
        mismatch, a body that is not valid JSON, or a release that could not be confirmed.
    '''
    start_time = time.perf_counter()

    try:
        flow_ok = _run_user_control_flow()
    finally:
        cleanup_ok, cleanup_detail = _ensure_key_released()
        if cleanup_ok:
            log_info(f"  Cleanup: {cleanup_detail}")
        else:
            # Reported independently of the measurement: a key left held is a different defect
            # from a failed assertion here, and it affects later cases rather than this one.
            log_error(
                "TCID26_User_Control_Pressed_Released_Flow cleanup FAILED: a key may still be "
                f"held down for subsequent cases - {cleanup_detail}"
            )

    if flow_ok and cleanup_ok:
        elapsed_time = time.perf_counter() - start_time
        log_success(log_with_timing("TCID26_User_Control_Pressed_Released_Flow Passed ✅", elapsed_time))
        return True

    log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
    return False


def _run_user_control_flow():
    """The outbound pair, the three-key inbound sweep and the closing inventory invariant.

    Returns True when every assertion holds. The verdict line and the guaranteed closing release
    live in run_test(), so an early return here still reaches them.
    """
    global _press_outstanding

    log_info(
        "Executing the user-control flow: outbound pressed and released, then inbound "
        "nominal, minimum and boundary key codes, each press closed by a release"
    )

    # ── FIXTURE CONSISTENCY, BEFORE ANY FRAME IS INJECTED ────────────────────────────────────────
    # The sweep's whole claim is that three documents differ in exactly one variable. That is a
    # property of the fixture tree rather than of the plugin, so it is proven here rather than
    # assumed: a document re-addressed, re-purposed to another opcode, truncated, or edited to
    # repeat a key code would leave every check below passing while the sweep silently lost an arm.
    key_codes, reason = _verify_fixture_sweep()
    if key_codes is None:
        log_error(f"✖ {reason}")
        log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
        return False
    log_success(
        "✔ the fixture set is a genuine three-point sweep: one shared header, opcode "
        f"0x{OPCODE_USER_CONTROL_PRESSED:02X} throughout, and three distinct key codes "
        f"{[f'0x{code:02X}' for code in key_codes]}"
    )

    # ── THE OUTBOUND TARGET, DERIVED FROM THE CONSTANTS THIS MODULE SENDS ────────────────────────
    # Both constants must name the same logical address, or the release would not close the press.
    # The value is read out of the constants rather than written here, so it cannot drift from
    # them, and the topology is then required to actually contain that peer - the precondition this
    # module's commentary describes in prose, checked rather than assumed.
    targets = {}
    for argv, label in (
        (HdmiCecSinkApis.send_user_control_pressed, "sendUserControlPressed"),
        (HdmiCecSinkApis.send_user_control_released, "sendUserControlReleased"),
    ):
        request, reason = _published_request(argv)
        if request is None:
            log_error(f"✖ {label}: {reason}")
            log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
            return False
        params = request.get("params")
        address = params.get("logicalAddress") if isinstance(params, dict) else None
        if not isinstance(address, int):
            log_error(
                f"✖ the {label} constant carries logicalAddress {address!r}, expected an integer"
            )
            log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
            return False
        targets[label] = address
    if len(set(targets.values())) != 1:
        log_error(
            f"✖ the two outbound constants target different logical addresses: {targets} - the "
            "release would not close the press it follows"
        )
        log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
        return False
    target_address = next(iter(targets.values()))

    # ── BEFORE-PROBE: THE INVENTORY THE CLOSING OBSERVATION IS MEASURED AGAINST ──────────────────
    # Read before anything is dispatched, and required to be readable: Init_Devicelist_Populate
    # guarantees a seeded topology before the first case runs, so an unreadable list means the
    # precondition never held and every claim below would rest on it.
    readable, before_count, before_addresses = _device_inventory()
    if not readable:
        log_error(
            "✖ the device list could not be read before the flow - either the endpoint is dead "
            "(send_curl_command returns the truthy \"< No response from WPEFramework >\" "
            "sentinel), the reply is not JSON, or it did not acknowledge success"
        )
        log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
        return False
    if not isinstance(before_count, int):
        log_error(
            f"✖ the device list reports numberofdevices {before_count!r}, expected an integer - "
            "the closing comparison would be against None"
        )
        log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
        return False
    if target_address not in before_addresses:
        log_error(
            f"✖ the outbound constants target logical address {target_address}, which is not in "
            f"the discovered topology {before_addresses} - the outbound leg would address nothing"
        )
        log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
        return False
    log_info(
        f"Before: {before_count} devices at {before_addresses}, outbound target "
        f"{target_address} present"
    )

    # ── ACT 1 - OUTBOUND PRESS ───────────────────────────────────────────────────────────────────
    # sendUserControlPressed takes a logical address AND a key code (IHdmiCecSink.h:275) and answers
    # with success only, so the acknowledgement is the whole of what it can be asserted on. Both
    # parameter values are carried by the command constant itself and are never restated here.
    log_info("Dispatching the outbound sendUserControlPressed call")
    if not _acknowledged(HdmiCecSinkApis.send_user_control_pressed, "sendUserControlPressed"):
        log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
        return False
    _press_outstanding = "the outbound sendUserControlPressed call"

    # ── ACT 2 - OUTBOUND RELEASE, WHICH CLOSES ACT 1 ─────────────────────────────────────────────
    # sendUserControlReleased takes the logical address ALONE (IHdmiCecSink.h:281) - the asymmetry
    # with pressed is by contract, since a release identifies no key - and likewise answers with
    # success only. This call is not an optional extra: without it the outbound leg would leave the
    # peer holding the key this case just pressed, which is the stuck-key condition
    # _ensure_key_released exists for. Ordering is load-bearing, not stylistic.
    log_info("Dispatching the outbound sendUserControlReleased call to close the press")
    if not _acknowledged(HdmiCecSinkApis.send_user_control_released, "sendUserControlReleased"):
        log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
        return False
    _press_outstanding = None

    # ── ACTS 3 TO 8 - THE INBOUND BOUNDARY SWEEP. THIS IS THE REASON THIS MODULE EXISTS. ─────────
    #
    # Three UserControlPressed frames are injected, differing ONLY in their key-code operand -
    # nominal, minimum, upper byte boundary, all three proven distinct above - and each is closed by
    # the same UserControlReleased frame. That is the same three-point sweep the sink L1 suite
    # applies to these APIs as sendUserControlPressed_MinKeyCode and
    # sendUserControlPressed_BoundaryKeyCode, lifted to device level rather than reinvented.
    #
    # Each press is paired with its release IN SEQUENCE rather than the three presses being fired
    # and then released together. Pairing them keeps at most one key outstanding at any moment, so
    # a failure part-way through cannot leave two or three keys held; and it means the sink observes
    # three complete press-release cycles, which is what a real remote sends.
    #
    # EVERY POST IS REQUIRED, AND REQUIRED AT THE POINT IT IS MADE. utils resolves a filename
    # against HDMICEC_CMD_BASE and returns (0, "YAML file not found: ...") rather than raising, so a
    # refused or misnamed document does not fail loudly: tolerating one would report a pass on a run
    # that never delivered part of the sweep - a dropped Min or Boundary press silently shrinks this
    # case to the nominal key code, and a dropped release leaves a key held. Neither shortfall is
    # visible downstream, so each is caught where it happens.
    for yaml_name, description in PRESS_FIXTURES:
        log_info(f"Injecting the inbound UserControlPressed frame with {description}")
        if not _post_hdmicec(yaml_name):
            log_error(
                f"✖ required injection refused - the press carrying {description} was never "
                f"delivered ({yaml_name})"
            )
            log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
            return False
        _press_outstanding = f"the injected press carrying {description}"
        time.sleep(CEC_FRAME_PACING_SECONDS)

        log_info(f"Injecting the UserControlReleased frame to close {description}")
        if not _post_hdmicec(RELEASE_FIXTURE):
            log_error(
                f"✖ required injection refused - the release closing {description} was never "
                f"delivered ({RELEASE_FIXTURE})"
            )
            log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
            return False
        _press_outstanding = None
        time.sleep(CEC_FRAME_PACING_SECONDS)
        log_success(f"✔ delivered the press carrying {description} and the release closing it")

    # ── CLOSING OBSERVATION - AN INVARIANT, NOT A LIVENESS CHECK ─────────────────────────────────
    # Equality, not liveness, and not a guess at a direction: neither
    # HdmiCecSinkProcessor::process(const UserControlPressed &, const Header &) nor its
    # UserControlReleased counterpart calls addDevice or touches deviceList at all, and every
    # injected frame initiates from an address the suite already seeded, so the inventory MUST be
    # identical. That makes this a real invariant - six frames that added, dropped or renumbered a
    # peer would be a genuine regression - and it is polled on a bounded monotonic budget so a busy
    # plugin is waited for rather than raced.
    log_info("Reading the device list as the closing inventory invariant")
    deadline = time.monotonic() + OBSERVE_TIMEOUT_S
    while True:
        after_readable, after_count, after_addresses = _device_inventory()
        if after_readable and (after_count, after_addresses) == (before_count, before_addresses):
            break
        if time.monotonic() >= deadline:
            if not after_readable:
                log_error(
                    "✖ the device inventory became unreadable after the flow - six injected "
                    "frames that left the plugin unable to answer is a regression"
                )
            else:
                log_error(
                    "✖ the user-control flow changed the device inventory: "
                    f"{before_count}/{before_addresses} -> {after_count}/{after_addresses}. "
                    "Neither user-control handler touches deviceList, so it must be identical"
                )
            log_error("TCID26_User_Control_Pressed_Released_Flow Failed ❌")
            return False
        time.sleep(OBSERVE_POLL_S)
    log_success(f"✔ inventory unchanged: {after_count} devices at exactly {after_addresses}")

    # NOT asserted, and NOT implied anywhere in this module: that any key press or key release
    # actually reached the sink's handlers, and that OnKeyPressEvent or OnKeyReleaseEvent fired.
    # Those are Thunder notifications, and this suite's one-shot curl transport cannot subscribe to
    # a notification channel, so there is no observation to make here - only an assumption that
    # could be dressed up as one. Inventing an event assertion at this level would be a false green.
    #
    # Those two events are NOT unverified in the estate, though - they are simply verified somewhere
    # this transport cannot reach. The sink L1 suite asserts them directly
    # (onKeyPressEvent_SubscribedClient_ReceivesAddressAndKeyCode,
    # onKeyPressEvent_BoundaryOperands_AreForwardedVerbatim,
    # onKeyPressEvent_NoSubscriber_ProducesNoClientNotification,
    # onKeyReleaseEvent_SubscribedClient_ReceivesLogicalAddress) and the sink L2 suite asserts them
    # from injected frames (InjectUserControlPressedFrameAndVerifyEvent plus its minimum /
    # maximum-named / out-of-range key-code variants, and
    # InjectUserControlReleasedFrameAndVerifyEvent). The coverage register's listing of both events
    # as uncovered is its pre-change baseline, not the current state.
    log_info(
        "Key delivery itself is not observable over this transport: OnKeyPressEvent and "
        "OnKeyReleaseEvent are Thunder notifications, asserted by the sink's own L1 and L2 suites"
    )
    return True
