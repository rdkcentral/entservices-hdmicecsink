"""
/**
 * @file TCID32_Invalid_ARC_Routing_Nochange.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID32_Invalid_ARC_Routing_Nochange
 * @details Validates that a malformed org.rdk.HdmiCecSink.setupARCRouting request perturbs nothing
 *          this transport can read, and REQUIRES the reply it produces to be an acknowledgement.
 *          Four steps, in this order: read and require the three baseline observations - HDMI-CEC
 *          enabled, a well-formed active route, a boolean audio-connected flag; dispatch the
 *          malformed request and require it to be acknowledged; then re-read all three
 *          observations and require each to be unchanged, each on a bounded monotonic poll. The misspelled key lives in HdmiCECSink_Curl.setup_arc_routing_invalid -
 *          `{"ennabled": true}` instead of `{"enabled": true}` - and only there, so nothing about
 *          the malformed shape is restated in this module.
 *
 *          THE MALFORMED REQUEST MUST BE ACKNOWLEDGED, AND THAT IS A DERIVED OUTCOME RATHER THAN A
 *          PLUGIN CHOICE THIS CASE PINS ARBITRARILY. Thunder's generated registration calls
 *          inbound.FromString(parameters) and discards the result
 *          (Thunder/Source/core/JSONRPC.h, InternalRegister), so the misspelled "ennabled" leaves
 *          the generated Enabled member at its default of false, and
 *          HdmiCecSinkImplementation::SetupARCRouting is entered with enabled == false and sets
 *          success = true unconditionally. The reply is therefore a result envelope reporting
 *          success True, which is what utils.require_ack requires here - and requiring it is what
 *          separates a plugin that absorbed the request from a request that never arrived. An
 *          error envelope, the transport sentinel, a non-object body, an unparsable string and a
 *          result reporting anything but True all fail.
 *
 *          WHICH BRANCH ACTUALLY OCCURS, AND WHY IT MATTERS TO THIS CASE. Thunder's JSON
 *          deserialiser silently ABSORBS an unknown member instead of failing: when Find(label)
 *          returns nullptr it parks the value on the field-name element and parsing continues
 *          (Thunder/Source/core/JSON.h). So `{"ennabled": true}` most likely arrives with
 *          params.Enabled never set, which converts to false, and SetupARCRouting therefore runs
 *          stopArc() rather than being rejected. This module reports which branch it saw instead
 *          of assuming the comfortable one.
 *
 *          THE ARC-STATE INVARIANT, AND WHY IT IS DERIVED RATHER THAN OBSERVED. ARC routing state
 *          has NO GETTER on the interface: HdmiCecSinkImplementation::SetupARCRouting publishes
 *          only a success flag, and the state it moves - m_currentArcRoutingState - is
 *          reported outward solely through the arcInitiationEvent / arcTerminationEvent
 *          notifications (ArcTerminationEvent, IHdmiCecSink.h:76), which reach registered
 *          COM-RPC/JSON-RPC subscribers rather than a one-shot curl request/response. So the
 *          invariant cannot be READ. It can, however, be DERIVED from two facts, and the
 *          derivation is stated here rather than left implicit:
 *            * stopArc() returns IMMEDIATELY when m_currentArcRoutingState is already
 *              ARC_STATE_ARC_TERMINATED or ARC_STATE_REQUEST_ARC_TERMINATION - a bare guarded
 *              return that sends no frame, starts no timer and fires no notification
 *              (HdmiCecSinkImplementation.cpp:1622-1640);
 *            * ARC IS terminated by the time this case runs. m_currentArcRoutingState is
 *              ARC_STATE_ARC_TERMINATED from construction (:635); TCID20_ARC_Initiation_Flow is
 *              the only case that enables ARC, and TCID21_ARC_Termination_Flow publishes a
 *              cleanup() hook that takes it back down which SuitManager runs UNCONDITIONALLY,
 *              including for a case it skipped; and no case registered between 21 and 32 calls
 *              setupARCRouting.
 *          Therefore, whichever branch the reply classification reveals, the ARC state cannot move:
 *          a rejection applies nothing, and an absorption applies enabled=false whose stopArc() is
 *          a no-op on an already-terminated machine. Step 1's requirement that HDMI-CEC be ENABLED
 *          is what keeps that reasoning about ARC rather than about a disabled plugin, since
 *          stopArc() also returns at its first line when cecEnableStatus is not true (:1622-1626).
 *
 *          WHAT IS READ AND COMPARED. Three observations, each required to be well formed before
 *          it is compared and each re-read on a bounded monotonic poll: getEnabled, because a
 *          malformed ARC request must not disable HDMI-CEC; getActiveRoute, because routing is what
 *          the case name is about; and
 *          getAudioDeviceConnectedStatus as a second, independent invariant.
 *
 *          THE COMPARISON IS GUARDED AGAINST PASSING ON NO EVIDENCE. Two absent members would
 *          each resolve to None and compare equal, which would green this case without observing
 *          anything. Both bodies are therefore required to carry a "result" mapping AND to report
 *          success True with a boolean `available` before any value comparison is believed, which
 *          is the same shape TCID07_Get_Active_Route requires of a well-formed reply. Only then
 *          are the route fields compared, and `length` / `pathList` are compared as
 *          present-or-absent on both sides because the television being its own active source
 *          yields available true with ActiveRoute "TV" and neither field - a legitimate reply
 *          shape TCID07 documents.
 *
 *          THE OPERATION UNDER TEST IS REQUIRED TO HAVE BEEN ANSWERED. The malformed
 *          setupARCRouting reply is the one response this module deliberately does not inspect
 *          the CONTENT of: whether the plugin reports a JSON-RPC error or a result with success
 *          false is its own choice and must not become a pass criterion here. But it is now
 *          required to have COME BACK as a JSON-RPC envelope carrying either member, because an
 *          undelivered request - refused connection, timeout, empty body - cannot perturb the
 *          route or the connected flag either, so both invariants below would hold trivially and
 *          this case would report a pass without the plugin ever having seen the malformed
 *          argument. Delivery is asserted; the verdict inside the envelope is not.
 *
 *          THIS CASE IS SELF-RESTORING BY CONSTRUCTION. It dispatches exactly one write, and that
 *          write is malformed and expected to be rejected; every other request is a read. No
 *          valid enable or disable is sent, so nothing here can re-arm the ARC state that
 *          TCID21_ARC_Termination_Flow took down at position 21, and no restore clause is needed
 *          on any path. That matters for suite ordering: SuitManager.py runs this case at
 *          position 32, after the idempotency pair 30/31 and immediately before
 *          TCID33_Process_Yaml_Health_Check, and leaving ARC enabled here would silently change
 *          the state those neighbours were written against.
 *
 *          ADDRESSED BY DESIGN, NOT BY MEASUREMENT. COVERAGE_GAPS.md ranks the missing sink
 *          vDeviceTests suite 22nd at priority P1 (#gap-plugin-sink-vdevicetests). In the §4b API
 *          table `SetupARCRouting` is recorded as covered by the sink's own L2 suite
 *          (SetupARCRouting_COMRPC and SetupARCRouting_JSONRPC in
 *          ../../L2Tests/tests/HdmiCecSink_L2Test.cpp) with NO E2E leg, and both of those L2
 *          cases exercise the WELL-FORMED argument only. TCID20 and TCID21 are AUTHORED to supply
 *          the positive end-to-end initiation and termination halves and this module the NEGATIVE
 *          leg neither the L2 suite nor those two cases cover - the malformed-parameter path.
 *          Runtime validation and measured coverage remain deferred until a device or emulator
 *          environment is available.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable over the JSON-RPC endpoint.
 *  - HDMI-CEC is enabled and Init_Devicelist_Populate has run, so the topology is seeded.
 *  - TCID21_ARC_Termination_Flow left ARC neutral; this case neither reads nor changes that.
 *  - AUTHORED, NOT EXECUTED in this repository: no workflow here runs this suite.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - HDMI-CEC reads enabled on both sides of the malformed request.
 *  - The active route read after the malformed request equals the one read before it, and the
 *    audio-device connected status is likewise unchanged.
 *  - The malformed setupARCRouting request is ACKNOWLEDGED - a result envelope reporting
 *    success True - which utils.require_ack asserts. @details derives that outcome from Thunder's
 *    registration template rather than assuming it.
 *  - No ARC routing state change is claimed, because none is observable from this transport.
 *
 * @pass_criteria
 *  - HDMI-CEC reads enabled before and after, the malformed setupARCRouting write is
 *    acknowledged with success True, all four state reads classify as JSON-RPC result objects
 *    reporting success True, both route reads carry a boolean available, their available /
 *    ActiveRoute / length / pathList values are equal, the two connected-status reads agree,
 *    and run_test() returns True.
 *
 * @failure_criteria
 *  - HDMI-CEC reads other than enabled on either side, a request is not dispatched, a response
 *    is the no-response sentinel, the malformed setupARCRouting write is refused or not
 *    acknowledged, any state read is not a JSON-RPC result object or reports success other than
 *    True, either route read carries a non-boolean available, the baseline connected status is
 *    not a boolean, any compared route field still differs after the bounded settle, the
 *    connected-status values still differ after it, a parse error occurs, or run_test() returns
 *    False.
 */
"""

import time
import json

# The utils names this module uses, and only those. Every diagnostic here is either a step record
# (log_info) or a verdict (log_success/log_error): a negative-path case whose findings arrive at
# warning level is easy to read past.
from utils import (
    send_curl_command,
    require_ack,
    sanitise_for_log,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_with_timing,
    CEC_FRAME_PACING_SECONDS,
)
import HdmiCECSink_Curl as HdmiCecSinkApis

# Bounded budget for the invariant re-reads. A poll ceiling, never a duration anything waits out:
# each wait returns the moment the state it is watching agrees, and reports its last reading on
# expiry so "never agreed" is distinguishable from "could not be read".
OBSERVE_TIMEOUT_S = 8.0
OBSERVE_POLL_S = 0.25


def _result_object(response_text):
    """Return the JSON-RPC result mapping from a response body, or an empty mapping.

    A JSON-RPC error envelope carries "error" instead of "result", and a malformed body could carry
    a non-object "result" or not be an object at all. Every such case collapses to {} so the caller
    reports a MISSING FIELD rather than raising AttributeError out of run_test(). Narrowing here is what keeps the
    module free of a broad `except Exception`: the only exception a caller can see is
    json.JSONDecodeError, handled where it can occur rather than swept up together with every
    programming defect in the file.
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


def _envelope(response_text):
    """Classify a JSON-RPC reply as ("error", None), ("result", mapping) or (None, None).

    Applied to the FOUR STATE READS this case compares - the two getActiveRoute replies and the two
    getAudioDeviceConnectedStatus replies - each of which must be a result envelope before its
    values are believed; a refusal or a non-envelope means there is nothing to compare rather than
    an invariant that held. The malformed setupARCRouting reply does not come through here: it is
    asserted by utils.require_ack, which requires the acknowledgement @details derives.
    Returns:
        ("error", None) for an error envelope, ("result", mapping) for a result object, and
        (None, None) when the body is the transport sentinel, is not JSON, or is not a JSON-RPC
        envelope at all.
    """
    if not response_text or response_text.startswith("< No response"):
        return None, None
    try:
        body = json.loads(response_text)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(body, dict):
        return None, None
    if "error" in body:
        return "error", None
    result = body.get("result")
    if isinstance(result, dict):
        return "result", result
    return None, None


def _route_fields(result):
    """Reduce a getActiveRoute result mapping to the tuple this case compares.

    `length` and `pathList` are read with .get() and so collapse to None when absent, which is a
    legitimate reply shape rather than an error: the television being its own active source yields
    available true with ActiveRoute "TV" and neither field, as TCID07_Get_Active_Route documents.
    Comparing them as present-or-absent on BOTH sides is therefore the correct treatment - it
    detects a field appearing, disappearing or changing, without demanding a field the plugin is not
    obliged to send. The well-formedness of the reply is established separately before this tuple is
    believed.
    Args:
        result: The "result" mapping from a getActiveRoute reply
    Returns:
        A tuple of the four route-describing fields, in a fixed order.
    """
    return (
        result.get("available"),
        result.get("ActiveRoute"),
        result.get("length"),
        result.get("pathList"),
    )


def _read_active_route():
    """Return the route tuple, or None when the reply is missing or not well formed.

    WELL-FORMEDNESS FIRST, VALUES SECOND. Requiring success True and a boolean `available` is what
    stops two empty or two error bodies from comparing equal and greening this case on no
    observation at all. This is the same reply shape TCID07_Get_Active_Route requires.
    """
    response = send_curl_command(HdmiCecSinkApis.get_active_route)
    # utils.send_curl_command reports a transport failure by RETURNING the TRUTHY sentinel
    # "< No response from WPEFramework >", so the prefix form is the detection contract.
    if not response or response.startswith("< No response"):
        return None
    try:
        result = _result_object(response)
    except json.JSONDecodeError:
        return None
    if result.get("success") is not True or not isinstance(result.get("available"), bool):
        return None
    return _route_fields(result)


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


def _wait_until(read, expected):
    """Poll `read` until it returns `expected`; returns (matched, last_reading).

    Bounded by OBSERVE_TIMEOUT_S on a monotonic clock. The last reading is returned so a caller can
    distinguish "never agreed" from "could not be read at all" - different causes, different
    messages.
    """
    deadline = time.monotonic() + OBSERVE_TIMEOUT_S
    while True:
        observed = read()
        if observed == expected and observed is not None:
            return True, observed
        if time.monotonic() >= deadline:
            return False, observed
        time.sleep(OBSERVE_POLL_S)


def run_test():
    """Send a malformed setupARCRouting and pin every consequence this transport can reach.

    THE ARC STATE ITSELF IS NOT READABLE, and the invariant is therefore DERIVED rather than
    observed. It is set out in @expected_result with its two citations; in short, whichever way the
    framework resolves the unknown member, m_currentArcRoutingState cannot move - a rejection
    applies nothing, and an absorption applies enabled=false, whose stopArc() returns immediately
    when the state is already ARC_STATE_ARC_TERMINATED (HdmiCecSinkImplementation.cpp:1622-1640).
    WHAT IS ASSERTED: HDMI-CEC is enabled before the request and still enabled after it; the reply
    is a JSON-RPC envelope of one of exactly two admissible shapes, and a result envelope must carry
    success True; and the two readable states - the active route and the audio-connected flag - are
    unchanged.
    Returns:
        True when every assertion holds; False on any transport failure, unreadable reply,
        unclassifiable envelope, or perturbed state.
    """
    start_time = time.perf_counter()

    # Legacy intent: invalid curl param handling for setupARCRouting.
    #
    # The requests below are dispatched as named steps so a reader can see the shape of the
    # experiment: read, read, malformed write, read, read.
    #
    # THE MALFORMED WRITE IS ASSERTED, WHICH IS WHAT MAKES THE COMPARISON EVIDENCE. An unchanged
    # route proves nothing about a request that never arrived, so without this assertion a
    # transport failure would produce two identical readings and a pass. What the plugin does is
    # not an open question: Thunder's registration template calls inbound.FromString(parameters)
    # and discards the result (Thunder/Source/core/JSONRPC.h, InternalRegister), so the misspelled
    # "ennabled" leaves the generated Enabled member at its default of false and
    # HdmiCecSinkImplementation::SetupARCRouting is entered with enabled == false: it runs
    # stopArc() and answers success. The malformed request is therefore ACKNOWLEDGED, and
    # require_ack asserting that is what proves it was processed at all.
    #
    # WHAT THIS CASE DOES AND DOES NOT CLAIM, given that behaviour. It does NOT claim the request
    # is inert - absorbed as enabled == false, it takes the stopArc() path. It claims that the
    # two things a malformed ARC-routing request must not disturb are undisturbed: the ACTIVE
    # ROUTE, which is owned by active-source handling rather than by ARC setup, and the
    # AUDIO-DEVICE CONNECTED flag, which HdmiCecSinkImplementation sets from peer discovery. Both
    # are read on either side and compared. That a typo can silently take the stop path is a
    # production robustness gap of the same family as TCID29_Invalid_OSD_Setnochange's, and it is
    # reported in this module's @note rather than repaired here.
    # THE ENABLED PRECONDITION, READ RATHER THAN ASSUMED. Every invariant below is about what a
    # malformed request must not disturb, and none of them means anything while HDMI-CEC is off:
    # SetupARCRouting, getActiveRoute and getAudioDeviceConnectedStatus would all be answering from
    # a plugin that is not driving the bus at all. Init_Devicelist_Populate enables it at bootstrap,
    # so a false reading here is a precondition failure rather than a finding about ARC.
    enabled_before = _read_flag(HdmiCecSinkApis.get_enabled, "enabled")
    if enabled_before is not True:
        log_error(
            f"✖ HDMI-CEC reads enabled={enabled_before!r} before the malformed request, so none "
            "of the invariants this case measures would mean anything - the suite's bootstrap "
            "enable did not hold"
        )
        log_error("TCID32_Invalid_ARC_Routing_Nochange Failed")
        return False

    baseline_route = send_curl_command(HdmiCecSinkApis.get_active_route)
    baseline_audio = send_curl_command(HdmiCecSinkApis.get_audio_device_connected_status)
    if not require_ack(HdmiCecSinkApis.setup_arc_routing_invalid, "malformed setupARCRouting"):
        log_error(
            "✖ the malformed setupARCRouting was not acknowledged, so this case cannot tell a "
            "plugin that absorbed it from a request that never arrived"
        )
        log_error("TCID32_Invalid_ARC_Routing_Nochange Failed")
        return False
    # The suite's ONE documented CEC frame-pacing window, named rather than spelled as a bare 1.
    # utils.CEC_FRAME_PACING_SECONDS is 1.0, so the value is unchanged; what changes is that it
    # is now the same named constant the other 26 pacing waits in this suite use. A bare literal
    # here made this module's wait look like an ad-hoc guess and meant a change to the suite's
    # pacing model would silently miss it.
    time.sleep(CEC_FRAME_PACING_SECONDS)
    final_route = send_curl_command(HdmiCecSinkApis.get_active_route)
    final_audio = send_curl_command(HdmiCecSinkApis.get_audio_device_connected_status)

    # Transport guards. utils.send_curl_command returns the
    # "< No response from WPEFramework >" sentinel - a TRUTHY string - for every failure mode, so
    # the falsy check alone cannot catch one; the prefix form is the detection contract utils.py
    # documents for callers. Every response this case compares is guarded here; the malformed
    # write has already been required to come back as a real JSON-RPC envelope above, which
    # subsumes the sentinel check for it.
    for label, response in (
        ("baseline getActiveRoute", baseline_route),
        ("baseline getAudioDeviceConnectedStatus", baseline_audio),
        ("final getActiveRoute", final_route),
        ("final getAudioDeviceConnectedStatus", final_audio),
    ):
        if not response:
            log_error(f"✖ {label} command not sent")
            return False
        if response.startswith("< No response"):
            log_error(f"✖ {label} returned no response from WPEFramework")
            return False

    log_warning(f"Baseline route response: {sanitise_for_log(baseline_route, max_chars=2048)}")
    log_warning(f"Final route response: {sanitise_for_log(final_route, max_chars=2048)}")
    log_warning(f"Baseline audio status: {sanitise_for_log(baseline_audio, max_chars=2048)}")
    log_warning(f"Final audio status: {sanitise_for_log(final_audio, max_chars=2048)}")

    # CLASSIFY ALL FOUR READS BEFORE COMPARING ANY OF THEM. _envelope admits a result object and an
    # error envelope and rejects everything that is neither, which is what stops this case comparing
    # two unreadable bodies and calling them equal - the failure mode a negative-path case is most
    # exposed to, because "nothing changed" is exactly what a broken read looks like. The four
    # bodies are classified from the strings already logged above rather than re-fetched, so what a
    # reader sees in the transcript is what was judged.
    classified = {}
    for label, response in (
        ("baseline getActiveRoute", baseline_route),
        ("final getActiveRoute", final_route),
        ("baseline getAudioDeviceConnectedStatus", baseline_audio),
        ("final getAudioDeviceConnectedStatus", final_audio),
    ):
        shape, result = _envelope(response)
        if shape != "result":
            log_error(
                f"✖ {label} did not answer with a JSON-RPC result object "
                f"({'an error envelope' if shape == 'error' else 'not a JSON-RPC envelope at all'})"
                ", so there is nothing here to compare"
            )
            log_error("TCID32_Invalid_ARC_Routing_Nochange Failed")
            return False
        if result.get("success") is not True:
            log_error(
                f"✖ {label} reports success={sanitise_for_log(result.get('success'))}, so its "
                "contents are not a reading this case may rest on"
            )
            log_error("TCID32_Invalid_ARC_Routing_Nochange Failed")
            return False
        classified[label] = result

    # THE ACTIVE ROUTE. Compared as the four-field tuple _route_fields defines, present-or-absent on
    # both sides. `available` is additionally required to be a boolean on both, because a reply
    # missing it is a shape this case cannot read rather than a route that did not move.
    before_route = classified["baseline getActiveRoute"]
    after_result = classified["final getActiveRoute"]
    for label, result in (
        ("baseline getActiveRoute", before_route), ("final getActiveRoute", after_result)
    ):
        if not isinstance(result.get("available"), bool):
            log_error(
                f"✖ {label} carries available={sanitise_for_log(result.get('available'))} rather "
                "than a boolean, so the route it reports cannot be believed"
            )
            log_error("TCID32_Invalid_ARC_Routing_Nochange Failed")
            return False

    baseline_fields = _route_fields(before_route)
    after_route = _route_fields(after_result)
    if after_route != baseline_fields:
        # Given a bounded second chance before failing. The route is owned by active-source
        # handling, which runs off the plugin's own poll and decode path, so an immediate re-read
        # taken microseconds after a write can legitimately catch a transient - and _wait_until
        # returns the instant it agrees, or the LAST reading it saw, which is the one worth naming.
        settled, last_route = _wait_until(_read_active_route, baseline_fields)
        if not settled:
            log_error(
                f"✖ the active route moved across the malformed request: {baseline_fields} -> "
                f"{after_route}, still {last_route} after {OBSERVE_TIMEOUT_S:.0f}s. ARC setup does "
                "not own the active route, so a malformed ARC request must not perturb it"
            )
            log_error("TCID32_Invalid_ARC_Routing_Nochange Failed")
            return False
        after_route = last_route

    # THE AUDIO-DEVICE CONNECTED FLAG. `is not None` is not enough on its own here - two absent
    # members both read None and would compare equal - so the baseline is required to be a boolean
    # before it is used as the expectation.
    connected_before = classified["baseline getAudioDeviceConnectedStatus"].get("connected")
    connected_after = classified["final getAudioDeviceConnectedStatus"].get("connected")
    if not isinstance(connected_before, bool):
        log_error(
            f"✖ the baseline audio-device connected status reads "
            f"{sanitise_for_log(connected_before)} rather than a boolean, so there is no baseline "
            "for the after-read to be compared against"
        )
        log_error("TCID32_Invalid_ARC_Routing_Nochange Failed")
        return False

    if connected_after != connected_before:
        connected_ok, connected_after = _wait_until(
            lambda: _read_flag(HdmiCecSinkApis.get_audio_device_connected_status, "connected"),
            connected_before,
        )
        if not connected_ok:
            log_error(
                f"✖ audio device connected reads {connected_after!r} after the malformed request, "
                f"expected the baseline {connected_before!r}"
            )
            log_error("TCID32_Invalid_ARC_Routing_Nochange Failed")
            return False

    # AND STILL ENABLED. Read again on the far side, because a malformed request that took the
    # plugin's CEC stack down with it would leave every invariant above trivially satisfied.
    enabled_after = _read_flag(HdmiCecSinkApis.get_enabled, "enabled")
    if enabled_after is not True:
        log_error(
            f"✖ HDMI-CEC reads enabled={enabled_after!r} after the malformed request, so the "
            "request disturbed considerably more than ARC routing"
        )
        log_error("TCID32_Invalid_ARC_Routing_Nochange Failed")
        return False

    log_success(
        f"✔ invariants hold: CEC enabled, active route {after_route}, audio "
        f"connected={connected_after}"
    )
    log_info(
        "ARC state itself is not readable from this transport; the invariant that it did not move "
        "is DERIVED from stopArc()'s already-terminated guard and from TCID21's unconditional "
        "cleanup - see @expected_result"
    )

    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID32_Invalid_ARC_Routing_Nochange Passed", elapsed_time))
    return True
