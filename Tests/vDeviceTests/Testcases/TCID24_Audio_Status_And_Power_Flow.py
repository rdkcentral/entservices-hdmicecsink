"""
/**
 * @file TCID24_Audio_Status_And_Power_Flow.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID24_Audio_Status_And_Power_Flow
 * @details Drives TWO COMPLETE REQUEST/RESPONSE EXCHANGES against the emulated audio system,
 *          and injects a third frame that is the mute corner case of the first - two
 *          solicitations and three replies, where the read-only cases earlier in this suite
 *          have neither. Seven steps, in this order:
 *            0. EXPECTATION DERIVATION, before any frame is injected -
 *               Device_Report_Power_Status.yaml is read and its [Power Status] operand byte is
 *               mapped through the PowerStatus::toString() table, so the value asserted in step
 *               7 follows the fixture instead of being restated here. A fixture that has been
 *               renamed, emptied, made broadcast or re-addressed is reported at this step rather
 *               than surfacing later as a mysterious mismatch;
 *            1. BEFORE-PROBE, ALL THREE PARTS ASSERTED - org.rdk.HdmiCecSink.getEnabled must
 *               read enabled True, org.rdk.HdmiCecSink.getDeviceList must carry a record for the
 *               audio system at CEC logical address 5, and
 *               org.rdk.HdmiCecSink.getAudioDeviceConnectedStatus must read connected True. All
 *               three are preconditions rather than context: with CEC disabled neither
 *               solicitation reaches the bus and both exchanges degenerate into unsolicited
 *               injections, and with no peer at address 5 there is no recipient for either
 *               solicitation and no legitimate origin for any of the three replies;
 *            2. EXCHANGE 1, OUTBOUND - org.rdk.HdmiCecSink.sendGetAudioStatusMessage, which
 *               reaches HdmiCecSinkImplementation::SendGetAudioStatusMessage
 *               (HdmiCecSinkImplementation.cpp:1690) and directs <Give Audio Status> at CEC
 *               logical address 5 through sendGiveAudioStatusMsg (:1263, sendTo
 *               LogicalAddress::AUDIO_SYSTEM at :1274);
 *            3. EXCHANGE 1, INBOUND (positive) - Device_Report_Audio_Status.yaml injects the
 *               audio system's <Report Audio Status> answer carrying volume 50 with the mute
 *               bit CLEAR, reaching HdmiCecSinkProcessor::process(const ReportAudioStatus &,
 *               const Header &) at :556 and then Process_ReportAudioStatus_msg at :1171;
 *            4. EXCHANGE 1, INBOUND (corner) - Device_Report_Audio_Status_Muted.yaml injects
 *               the SAME volume with bit 7 SET, which is the mute-decoding branch of the same
 *               handler. Posting both is what makes this module positive-plus-corner rather
 *               than happy-path only;
 *            5. EXCHANGE 2, OUTBOUND - org.rdk.HdmiCecSink.requestAudioDevicePowerStatus,
 *               which reaches RequestAudioDevicePowerStatus (:2208), directs
 *               <Give Device Power Status> at logical address 5 (:2233) and - critically -
 *               sets m_audioDevicePowerStatusRequested at :2234;
 *            6. EXCHANGE 2, INBOUND - Device_Report_Power_Status.yaml injects the audio
 *               system's <Report Power Status> answer, reaching
 *               process(const ReportPowerStatus &, const Header &) at :408;
 *            7. AFTER-PROBE, THE STATE CONSEQUENCE PLUS THREE INVARIANTS - getDeviceList must
 *               publish powerStatus for logical address 5 exactly equal to the string derived in
 *               step 0; the device count and logical-address set must be unchanged; CEC must
 *               still be enabled; and the audio system must still read connected.
 *
 *          THE ORDER OF EACH SOLICITATION AND ITS REPLY IS FUNCTIONAL, NOT COSMETIC, and for
 *          exchange 2 the code proves it: the AudioSystem-specific branch at :425 is guarded by
 *          `(header.from == LogicalAddress::AUDIO_SYSTEM) &&
 *          m_audioDevicePowerStatusRequested`, and that flag is set in exactly one place -
 *          inside RequestAudioDevicePowerStatus at :2234. Inject the reply first and the flag is
 *          still false, so reportAudioDevicePowerStatusInfo (:1277) is never reached and the
 *          exchange degenerates into an unsolicited report.
 *
 *          ALL THREE FIXTURES ARE DIRECTED (initiator 0x5, destination 0x0), AND NONE MAY BE
 *          SWAPPED FOR A BROADCAST FORM: both handlers return early on a broadcast destination
 *          (:559 for ReportAudioStatus, :411 for ReportPowerStatus), so a broadcast frame is
 *          discarded before any decoding happens. The power-status fixture must also be
 *          Device_Report_Power_Status.yaml, whose payload initiates from 0x5; the sibling
 *          Process_Report_Power_Status.yaml exists but initiates from 0x4, which satisfies the
 *          generic device-update path and misses the AudioSystem branch this module exists to
 *          drive.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - is running WPEFramework with
 *    the org.rdk.HdmiCecSink plugin activated and reachable over JSON-RPC.
 *  - Init_Devicelist_Populate has seeded the emulated topology, including the YAMAHA
 *    AudioSystem peer at CEC logical address 5, and has left HDMI-CEC ENABLED. Both
 *    conditions are load-bearing for exchange 2: RequestAudioDevicePowerStatus returns
 *    Core::ERROR_GENERAL when CEC is disabled, when no logical address has been allocated, or
 *    when the connection is absent (HdmiCecSinkImplementation.cpp:2210-2231), and the reply
 *    can only be attributed to an audio system that exists at address 5.
 *  - The vComponent HTTP API is reachable, so all three reply payloads can be injected.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - Both solicitations are acknowledged, and all three replies are injected and accepted by
 *    the emulator.
 *  - THE PEER'S POWER STATUS IS ASSERTED, AND IT IS THE STATE CONSEQUENCE THAT MAKES THIS
 *    MODULE MORE THAN AN INJECTION PROBE. process(ReportPowerStatus) does not merely notify: it
 *    writes the received status into the device record - addDevice(header.from) followed by
 *    deviceList[header.from].update(msg.status) at HdmiCecSinkImplementation.cpp:416-417 - and
 *    GetDeviceList publishes that field as powerStatus (:1403). So the operand the injected
 *    fixture carried must reappear, rendered by PowerStatus::toString()
 *    (ccec/include/ccec/Operands.hpp:593-614), in the published device list for logical address
 *    5. The expectation is DERIVED from the fixture in step 0 rather than restated, so the
 *    fixture remains the single source of truth.
 *    WHY THAT ASSERTION IS A TRANSITION PROOF. CECDeviceParams() initialises m_powerStatus to 0
 *    (HdmiCecSinkImplementation.h:150) and clear() resets it to 0 (:173), both rendering "On",
 *    so a fixture carrying operand 0x00 would be indistinguishable from a frame that never
 *    arrived. Device_Report_Power_Status.yaml therefore carries a NON-ZERO operand - 0x01,
 *    "Standby" - and the published field must MOVE from "On" to "Standby", which only a
 *    delivered and decoded frame can do. The sibling Process_Report_Power_Status.yaml, which
 *    initiates from address 4 and is not the fixture this case injects, still carries 0x00.
 *  - THE DECODED VOLUME AND MUTE STATE ARE NOT ASSERTED, because no state exists to read them
 *    back from. Process_ReportAudioStatus_msg stores neither value: it flips two internal timer
 *    flags and fans the pair out through ReportAudioStatusEvent (:1171-1195,
 *    IHdmiCecSink.h:127-130), a Thunder notification delivered to registered COM-RPC/JSON-RPC
 *    subscribers rather than to a one-shot curl request/response, and no getter returns an audio
 *    status. Exchange 1 is therefore an INJECTION-AND-INVARIANT exchange, and it is labelled as
 *    such rather than described as verified.
 *    REQUIRED PRODUCTION CHANGE TO CLOSE THAT GAP, reported and not made: a GetAudioStatus
 *    getter on Exchange::IHdmiCecSink returning the last received volume and mute state, or a
 *    vComponent endpoint reporting frames the device under test EMITTED so the outbound
 *    <Give Audio Status> could be observed. Neither exists, and this suite may not add either.
 *
 * @pass_criteria
 *  - The power-status fixture is readable and declares a directed payload initiated from logical
 *    address 5 with a [Power Status] operand; the before-probe reports enabled True, a device
 *    record for logical address 5 and connected True; sendGetAudioStatusMessage and
 *    requestAudioDevicePowerStatus each acknowledge result.success as True; all three required
 *    YAML posts return HTTP 200; getDeviceList then publishes powerStatus for logical address 5
 *    exactly equal to the derived string, with the device count and address set unchanged, CEC
 *    still enabled and the audio system still connected; and run_test() returns True.
 *
 * @failure_criteria
 *  - The power-status fixture cannot be read, declares no payload, carries a non-hexadecimal
 *    byte, has fewer than three payload bytes, initiates from an address other than 5 or is
 *    broadcast; CEC reads disabled before or after; the device inventory cannot be read or has no
 *    record for logical address 5; connected reads anything but True before or after; a request is
 *    not dispatched; a response is the no-response sentinel; ANY required vComponent post does not
 *    return HTTP 200; either solicitation does not acknowledge success; the published powerStatus
 *    never becomes the derived value within the bounded observation budget; the inventory changes
 *    across the exchanges; a JSON parsing error occurs; or run_test() returns False.
 */
"""

import time
import os
import re
import json

# The eight-symbol utils import below is the shared contract the emulation-driven ("flow")
# testcases in this suite are written against, and every symbol in it now has a call site:
# log_with_timing applies the HDMICEC_TIMING_ENABLED decoration and the pass path routes its
# message through it, which is what retired this module's own local copy of that gate. `os` and
# `re` are imported because this module DERIVES its power-status expectation by reading the
# injected fixture's operand byte rather than restating it - see _payload_operands below. Keeping the
# set identical across the flow modules is what lets one be diffed against another, so the
# resulting single "imported but unused" lint note is accepted convention here rather than an
# oversight. Every other symbol has a call site below.
from utils import (
    read_fixture_text,
    send_curl_command,
    send_vcomponent_command,
    sanitise_for_log,
    HDMICEC_CMD_BASE,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing
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
    the caller reports a MISSING FIELD rather than raising AttributeError out of run_test(). A
    body that is not JSON at all still raises json.JSONDecodeError, which run_test() handles as
    the documented failure. Four call sites share this - the two solicitation acknowledgements
    and the two connected-status probes - which is why it is factored out rather than inlined.
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


# The CEC logical address of an audio system. Both solicitations are directed at it
# (HdmiCecSinkImplementation.cpp:1274 and :2233), all three injected replies claim it as their
# initiator, and it is the address whose published powerStatus this module asserts.
AUDIO_SYSTEM_LOGICAL_ADDRESS = 5

# The fixture whose operand byte the power-status expectation is DERIVED from. Named once so the
# post and the expectation can never drift apart.
POWER_STATUS_FIXTURE = "Device_Report_Power_Status.yaml"

# PowerStatus::toString() rendered as data, mirroring ccec/include/ccec/Operands.hpp:593-614
# byte for byte: validate() accepts 0x00..0x03 and toString() indexes this table, while anything
# above 0x03 renders "Unknown" however the numeric value is spelled. Reproduced here rather than
# hardcoding one string so the expectation follows the fixture's operand instead of an assumption
# about which operand the fixture carries.
POWER_STATUS_NAMES = {
    0x00: "On",
    0x01: "Standby",
    0x02: "In transition Standby to On",
    0x03: "In transition On to Standby",
}

# Bounded budget for the reachable observations - a poll ceiling, never a duration anything waits
# out. Every wait below returns as soon as the state it is watching agrees.
OBSERVE_TIMEOUT_S = 8.0
OBSERVE_POLL_S = 0.25

_PAYLOAD_PATTERN = re.compile(r'payload:\s*\[(.*?)\]', re.S)


def _payload_operands(yaml_name):
    """Return the payload bytes a vComponent command document declares, or None with a reason.

    WHY THIS READS THE FIXTURE INSTEAD OF RESTATING ITS BYTES. The expectation this module
    asserts - the powerStatus string the sink must publish for the audio system - is a function
    of ONE byte in Device_Report_Power_Status.yaml. Copying that byte into this file would create
    two places to keep in step, and a fixture edited without a matching edit here would then be
    reported as a plugin defect. Deriving it means the fixture stays the single source of truth,
    which is the same technique Init_Devicelist_Populate.verify_seed_payload_consistency() uses
    for the seed payloads, so this is an established idiom in this suite rather than a new one.
    Args:
        yaml_name: File name of a document under utils.HDMICEC_CMD_BASE.
    Returns:
        (payload_bytes, None) on success, or (None, reason) when the document cannot be read,
        declares no payload list, or carries a non-hexadecimal byte.
    """
    path = os.path.join(HDMICEC_CMD_BASE, yaml_name)
    try:
        # utils.read_fixture_text opens with O_NOFOLLOW|O_CLOEXEC and fstats the descriptor, so a
        # symbolic link or a FIFO standing where the fixture should be is refused rather than
        # followed or blocked on.  Every refusal is an OSError, which the handler below reports.
        text = read_fixture_text(path)
    except OSError as exc:
        return None, f"cannot read {yaml_name}: {exc}"
    match = _PAYLOAD_PATTERN.search(text)
    if not match:
        return None, f"{yaml_name} declares no payload list"
    try:
        values = [
            int(token.strip().strip('"').strip("'"), 16)
            for token in match.group(1).split(",")
            if token.strip()
        ]
    except ValueError as exc:
        return None, f"{yaml_name} has a non-hexadecimal payload byte: {exc}"
    return values, None


def _device_entry(logical_address):
    """Return the published getDeviceList record for one logical address.

    Returns:
        (readable, entry_or_None, count, sorted_addresses). `readable` is False when the reply
        cannot be read or does not acknowledge success, so a caller reports "unreadable" rather
        than mistaking it for a missing device.
    """
    response = send_curl_command(HdmiCecSinkApis.get_device_list)
    if not response or response.startswith("< No response"):
        return False, None, None, None
    try:
        result = _result_object(response)
    except json.JSONDecodeError:
        return False, None, None, None
    if result.get("success") is not True:
        return False, None, None, None
    device_list = result.get("deviceList")
    if not isinstance(device_list, list):
        return False, None, None, None
    entries = [device for device in device_list if isinstance(device, dict)]
    addresses = sorted(
        device["logicalAddress"]
        for device in entries
        if isinstance(device.get("logicalAddress"), int)
    )
    match = next(
        (device for device in entries if device.get("logicalAddress") == logical_address), None
    )
    return True, match, result.get("numberofdevices"), addresses


def _read_flag(argv, field):
    """Read one boolean field out of a published getter, or None when it cannot be read."""
    response = send_curl_command(argv)
    if not response or response.startswith("< No response"):
        return None
    try:
        result = _result_object(response)
    except json.JSONDecodeError:
        return None
    if result.get("success") is not True:
        return None
    value = result.get(field)
    return value if isinstance(value, bool) else None


def _acknowledged(argv, label):
    """Send one published method and require result.success True; returns True when it holds."""
    response = send_curl_command(argv)
    if not response:
        log_error(f"✖ {label} command not sent")
        return False
    # The transport failure guard that actually fires in this suite. utils.send_curl_command
    # returns the "< No response from WPEFramework >" sentinel - a TRUTHY string - for every
    # failure mode, so a falsy check cannot catch one on its own. The prefix form is the detection
    # contract utils.py documents for callers.
    if response.startswith("< No response"):
        log_error(f"✖ {label} returned no response from WPEFramework")
        return False
    log_warning(f"Response: {response}")
    try:
        if _result_object(response).get("success") is not True:
            log_error(f"✖ {label} did not acknowledge success")
            return False
    except json.JSONDecodeError:
        log_error(f"✖ {label} reply is not valid JSON")
        return False
    log_success(f"✔ {label} acknowledged")
    return True


def _wait_for_power_status(logical_address, expected):
    """Poll getDeviceList until the device's powerStatus reads `expected`.

    Returns:
        (matched, last_observed_value_or_None). The last observation is returned so the caller can
        say WHICH value it kept reading, and None distinguishes "device absent or list unreadable"
        from "present with the wrong value".
    """
    deadline = time.monotonic() + OBSERVE_TIMEOUT_S
    while True:
        readable, entry, _, _ = _device_entry(logical_address)
        observed = entry.get("powerStatus") if (readable and entry) else None
        if observed == expected:
            return True, observed
        if time.monotonic() >= deadline:
            return False, observed
        time.sleep(OBSERVE_POLL_S)


def run_test():
    """Drive both audio exchanges and assert the one state consequence this transport can read.

    WHAT IS REACHABLE AND WHAT IS NOT, stated once because it governs every assertion below.
      * NOT reachable - the decoded VOLUME and MUTE state. Process_ReportAudioStatus_msg stores
        neither: it flips two internal timer flags and fans the pair out through
        ReportAudioStatusEvent (HdmiCecSinkImplementation.cpp:1171-1195), a Thunder notification
        a curl transport cannot subscribe to, and no getter returns an audio status.
      * REACHABLE, AND ASSERTED - the audio system's POWER STATUS. process(ReportPowerStatus)
        writes it into the device record - deviceList[header.from].update(msg.status) at :417 -
        and GetDeviceList publishes that field as powerStatus (:1403). So the injected operand
        must reappear, rendered by PowerStatus::toString(), in the published device list. The
        expectation is DERIVED from the fixture's own operand byte, not restated here.
    Returns:
        True when every assertion holds; False on any transport failure, refused post, unreadable
        reply, wrong published power status or disturbed invariant.
    """
    start_time = time.perf_counter()

    # SHARED STATE, AND THE ONE RESIDUAL THIS MODULE LEAVES BEHIND.
    #
    # ORDERING CHOSEN: unmuted first, MUTED LAST - deliberately, because muted is the corner
    # case and putting it after the positive case means a failure in the corner injection cannot
    # be mistaken for a failure in the positive one. The consequence is stated rather than
    # glossed: the last audio status the middleware recorded for the audio system is the MUTED
    # one, and this module does not restore the unmuted state. No restore is fabricated for two
    # reasons - the interface publishes NO inverse API (nothing on IHdmiCecSink clears a received
    # audio status, so a "restore" could only re-inject the unmuted frame and prove nothing), and
    # the residual alters NO user-visible plugin setting exposed by the interface (the status is
    # fanned out as a notification at HdmiCecSinkImplementation.cpp:1192 and persisted into
    # nothing a later case reads; the next case in SuitManager.py,
    # TCID25_Standby_Coordination_Flow, exercises standby rather than audio mute). Exchange 2 is
    # unaffected either way - its branch is gated on m_audioDevicePowerStatusRequested, not on
    # any audio status. No cleanup() hook is published for the same reason: there is no published
    # operation that could undo either exchange.

    # ── DERIVE THE EXPECTATION BEFORE TOUCHING THE DEVICE ───────────────────────────────────────
    # Doing this first means a fixture that has been renamed, emptied or corrupted is reported as
    # exactly that, before any frame is injected, instead of surfacing later as a mysterious
    # power-status mismatch.
    operands, reason = _payload_operands(POWER_STATUS_FIXTURE)
    if operands is None:
        log_error(f"✖ {reason}")
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False
    # ["0x50","0x90","0x00"]: header, opcode <Report Power Status>, then the single
    # [Power Status] operand. Three bytes exactly - a shorter list means the document no longer
    # carries an operand for the expectation to be derived from.
    if len(operands) < 3:
        log_error(
            f"✖ {POWER_STATUS_FIXTURE} declares {len(operands)} payload bytes, expected at least "
            "3 (header, opcode 0x90, [Power Status] operand)"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False
    if operands[0] >> 4 != AUDIO_SYSTEM_LOGICAL_ADDRESS:
        log_error(
            f"✖ {POWER_STATUS_FIXTURE} header 0x{operands[0]:02X} initiates from logical address "
            f"{operands[0] >> 4}, not the audio system at {AUDIO_SYSTEM_LOGICAL_ADDRESS} - the "
            "AudioSystem branch at HdmiCecSinkImplementation.cpp:425 would never be reached"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False
    if operands[0] & 0x0F == 0x0F:
        log_error(
            f"✖ {POWER_STATUS_FIXTURE} header 0x{operands[0]:02X} is broadcast; "
            "process(ReportPowerStatus) discards broadcast frames at :411"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False
    expected_power_status = POWER_STATUS_NAMES.get(operands[2], "Unknown")
    log_info(
        f"Derived from {POWER_STATUS_FIXTURE}: operand 0x{operands[2]:02X} must be published as "
        f"powerStatus {expected_power_status!r} for logical address "
        f"{AUDIO_SYSTEM_LOGICAL_ADDRESS}"
    )

    # ── BEFORE: asserted preconditions, not context ──────────────────────────────────────────────
    # getEnabled is a precondition with teeth for BOTH exchanges. sendGiveAudioStatusMsg() and
    # requestAudioDevicePowerStatus() are the routines that put the two solicitations on the bus,
    # and RequestAudioDevicePowerStatus returns Core::ERROR_GENERAL outright when CEC is disabled
    # (:2210-2213), while SendGetAudioStatusMessage sets success = true unconditionally
    # (:1690-1695) whatever happened underneath. Requiring enabled True closes the gap the second
    # of those leaves open.
    enabled_before = _read_flag(HdmiCecSinkApis.get_enabled, "enabled")
    if enabled_before is not True:
        log_error(
            f"✖ getEnabled reads {enabled_before!r}, expected True. With CEC disabled neither "
            "solicitation reaches the bus, so both exchanges would degenerate into unsolicited "
            "injections"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False

    readable, before_entry, before_count, before_addresses = _device_entry(
        AUDIO_SYSTEM_LOGICAL_ADDRESS
    )
    if not readable:
        log_error("✖ the device inventory could not be read before the exchanges")
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False
    if before_entry is None:
        log_error(
            f"✖ no audio system at logical address {AUDIO_SYSTEM_LOGICAL_ADDRESS} in "
            f"{before_addresses} - neither solicitation has a recipient, and all three injected "
            "replies claim that address as their initiator"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False

    # VALUE ASSERTION ON `connected`, NOT A TYPE ASSERTION, and the distinction from the sink's L2
    # suite is the reason. That suite asserts EXPECT_FALSE(connected) in
    # GetAudioDeviceConnectedStatus_COMRPC and GetAudioDeviceConnectedStatus_JSONRPC
    # (../../L2Tests/tests/HdmiCecSink_L2Test.cpp) because its in-process host discovers no audio
    # system at all. THAT DOES NOT TRANSFER HERE: this suite REQUIRES the YAMAHA audio system at
    # logical address 5 as a @precondition, addDevice() sets hdmiCecAudioDeviceConnected
    # unconditionally for that address, and nothing on any path this module drives clears it.
    connected_before = _read_flag(HdmiCecSinkApis.get_audio_device_connected_status, "connected")
    if connected_before is not True:
        log_error(
            f"✖ audio device connected reads {connected_before!r} before the exchanges, expected "
            f"True with the peer present at logical address {AUDIO_SYSTEM_LOGICAL_ADDRESS}"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False
    log_info(
        f"Before: CEC enabled, {before_count} devices at {before_addresses}, audio connected=True,"
        f" audio system powerStatus={before_entry.get('powerStatus')!r}"
    )

    # ── EXCHANGE 1 - GIVE AUDIO STATUS, then its positive and mute-corner replies ────────────────
    # The solicitation must precede both injections; see @details. Each injection is REQUIRED and
    # reported BY NAME, so a fixture renamed out from under this module surfaces as a failure
    # naming the arm that was never delivered rather than a silent skip - send_vcomponent_command
    # returns (0, "YAML file not found: ...") for a missing document, which is a truthy body with
    # a zero status.
    if not _acknowledged(HdmiCecSinkApis.send_get_audio_status_message, "sendGetAudioStatusMessage"):
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False

    # payload ["0x50","0x7A","0x32"]: opcode 0x7A (<Report Audio Status>) with ONE operand byte
    # whose bit 7 is the audio mute flag and bits 0-6 the volume - so 0x32 is volume 50 with mute
    # CLEAR. The muted document is that frame with the mute bit raised, 0x32 | 0x80 == 0xB2, so
    # the SAME volume 50 arrives muted: one operand bit is the entire difference, and it is the
    # only route from this transport into the mute-decoding branch of the same handler. Do not
    # widen or narrow either operand, and do not substitute a broadcast form - the handler returns
    # early on a broadcast destination at :559.
    for yaml_name, arm in (
        ("Device_Report_Audio_Status.yaml", "the audio status reply, volume 50 unmuted"),
        ("Device_Report_Audio_Status_Muted.yaml", "the mute corner case, volume 50 muted"),
    ):
        if not _post_hdmicec(yaml_name):
            log_error(f"✖ required injection refused - {arm} was never delivered ({yaml_name})")
            log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
            return False
        log_success(f"✔ delivered {arm}")

    # ── EXCHANGE 2 - REQUEST POWER STATUS, then the reply whose effect IS observable ─────────────
    # Order is functional here and the code proves it: the AudioSystem-specific branch at :425 is
    # guarded by m_audioDevicePowerStatusRequested, set in exactly one place - inside
    # RequestAudioDevicePowerStatus at :2234. Inject the reply first and that flag is still false,
    # so reportAudioDevicePowerStatusInfo (:1277) is never reached.
    if not _acknowledged(
        HdmiCecSinkApis.request_audio_device_power_status, "requestAudioDevicePowerStatus"
    ):
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False

    if not _post_hdmicec(POWER_STATUS_FIXTURE):
        log_error(
            f"✖ required injection refused - the audio system's power status reply was never "
            f"delivered ({POWER_STATUS_FIXTURE})"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False
    log_success("✔ delivered the audio system's <Report Power Status> reply")

    # ── AFTER: THE STATE CONSEQUENCE, then the invariants ────────────────────────────────────────
    # This is the assertion that makes the module more than an injection probe: the operand the
    # fixture carried must reappear as the audio system's published powerStatus. Polled on a
    # bounded monotonic budget, so a handler that runs on the CEC thread is waited for rather than
    # raced, and a handler that never runs is still reported.
    #
    # WHAT THIS PROVES, stated rather than left to be assumed. It proves the published field
    # agrees with the injected operand, and because the operand is NON-ZERO it also proves a
    # TRANSITION: CECDeviceParams() initialises m_powerStatus to 0 (HdmiCecSinkImplementation.h:150)
    # and clear() resets it to 0 (:173), both of which render "On", while
    # Device_Report_Power_Status.yaml carries operand 0x01 - "Standby" - so the field can only
    # read "Standby" after a delivered and decoded frame. The sibling Process_ document, which
    # initiates from address 4 and is not injected here, still carries 0x00.
    matched, observed = _wait_for_power_status(
        AUDIO_SYSTEM_LOGICAL_ADDRESS, expected_power_status
    )
    if not matched:
        log_error(
            f"✖ logical address {AUDIO_SYSTEM_LOGICAL_ADDRESS} publishes powerStatus "
            f"{observed!r}, expected {expected_power_status!r} derived from "
            f"{POWER_STATUS_FIXTURE} operand 0x{operands[2]:02X}. "
            "process(ReportPowerStatus) writes the received status into the device record at "
            "HdmiCecSinkImplementation.cpp:417 and GetDeviceList publishes it at :1403, so a "
            "mismatch means the frame never reached the handler or the handler did not record it"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False
    log_success(
        f"✔ logical address {AUDIO_SYSTEM_LOGICAL_ADDRESS} publishes powerStatus "
        f"{observed!r}, matching the injected operand"
    )

    after_readable, after_entry, after_count, after_addresses = _device_entry(
        AUDIO_SYSTEM_LOGICAL_ADDRESS
    )
    if not after_readable or after_entry is None:
        log_error("✖ the audio system's device record became unreadable after the exchanges")
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False
    if (after_count, after_addresses) != (before_count, before_addresses):
        # addDevice() is idempotent for a device already present (:2449-2470), so neither the
        # count nor the address set may move. A change here means a peer appeared or vanished
        # during the exchanges, which is a real regression rather than noise.
        log_error(
            f"✖ the exchanges disturbed the device inventory: "
            f"{before_count}/{before_addresses} -> {after_count}/{after_addresses}"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False

    enabled_after = _read_flag(HdmiCecSinkApis.get_enabled, "enabled")
    if enabled_after is not True:
        log_error(
            f"✖ getEnabled reads {enabled_after!r} after the exchanges, expected True - neither "
            "an audio status nor a power status report may disable HDMI-CEC"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False

    connected_after = _read_flag(HdmiCecSinkApis.get_audio_device_connected_status, "connected")
    if connected_after is not True:
        log_error(
            f"✖ audio device connected reads {connected_after!r} after the exchanges, expected "
            "True - neither exchange may undiscover the audio system"
        )
        log_error("TCID24_Audio_Status_And_Power_Flow Failed ❌")
        return False
    log_success(
        f"✔ invariants hold: CEC enabled, {after_count} devices at {after_addresses}, "
        "audio connected=True"
    )

    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID24_Audio_Status_And_Power_Flow Passed ✅", elapsed_time))
    return True
