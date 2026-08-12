"""
/**
 * @file TCID17_Request_Active_Source_Flow.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID17_Request_Active_Source_Flow
 * @details Exercises the sink's active-source negotiation end to end and asserts a TRANSITION
 *          rather than a shape. The active source is first driven to a known "none" state - the
 *          peer is announced and then withdrawn, which is the only deterministic route to it,
 *          because updateInActiveSource clears the selection only when the withdrawing address is
 *          the one currently selected - then org.rdk.HdmiCecSink.requestActiveSource asks the bus
 *          who holds it, two BROADCAST CEC frames are injected through the vComponent so an
 *          already-configured emulated peer answers, and the sink must end up reporting EXACTLY
 *          the peer those frames announce. A run in which nothing moved therefore fails, which a
 *          shape-only check on the after-probe could not distinguish from a successful one.
 *
 *          The pair of injected frames is deliberate. <Request Active Source> (0x4F 0x85) drives
 *          process(RequestActiveSource) and <Active Source> (0x4F 0x82 0x30 0x00) drives
 *          process(ActiveSource), announcing physical address 3.0.0.0 from logical address 4 -
 *          SONY, the playback device the authoritative topology places on the television's third
 *          HDMI input. Both are BROADCAST because each of those handlers early-returns on
 *          directed framing: a directed frame would be accepted by the vComponent and then
 *          silently discarded by the plugin, leaving a green test that exercised nothing. The
 *          peer side comes ONLY from those frames, emitted by the topology
 *          Init_Devicelist_Populate already seeded; nothing here reconfigures the device under
 *          test to answer as its own peer, because role flipping and role inversion are out of
 *          scope for this suite and an active-source exchange is precisely where that shortcut
 *          would otherwise be tempting.
 *
 *          THE AFTER-PROBE IS ASSERTED AGAINST AN EXACT ACTIVE SOURCE, not against the shape of
 *          the result block. Requiring only "available is a boolean" passes on a sink that
 *          discarded both frames, and requiring only "available is true" passes on whatever
 *          holder an earlier case happened to leave behind - so neither predicate could tell this
 *          flow from no flow at all. The exact outcome is DERIVED rather than guessed, and it is
 *          deterministic because this case's own last state-changing step decides it:
 *            - HdmiCecSinkProcessor::process(const ActiveSource &, const Header &) calls
 *              addDevice(4) and then updateActiveSource(4, msg);
 *            - updateActiveSource proceeds whenever the announcing address differs from the
 *              television's own allocated address - 4 against 0 - and then unconditionally sets
 *              deviceList[4].m_isActiveSource, deviceList[4].update(3.0.0.0) and
 *              m_currentActiveSource = 4;
 *            - GetActiveSource reports that entry back: available true, logicalAddress 4,
 *              physicalAddress from PhysicalAddress::toString() which is dotted - "3.0.0.0" - and
 *              port from the first nibble as "HDMI" followed by (nibble - 1), so "HDMI2".
 *          The <Request Active Source> injected first cannot disturb that: it drives
 *          setActiveSource(true), which either returns early because the television is not the
 *          current active source - its `isResponse` guard - or claims the source for the
 *          television, and in either case the <Active Source> that follows overwrites the result.
 *          That ordering is what makes the exact assertion sound rather than merely plausible.
 *
 *          The sink also publishes an active-source notification, which a device-level curl case
 *          cannot subscribe to, so no event assertion appears below and none is claimed - the
 *          published read is what carries the verdict instead.
 *
 * @precondition
 *  - The org.rdk.HdmiCecSink plugin is active and reachable via the JSON-RPC endpoint.
 *  - Init_Devicelist_Populate has seeded the emulated topology, so a peer exists to answer the
 *    request and to be reported as the active source.
 *  - The vComponent HTTP API is reachable, so the YAML frame injections below land on the bus.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - requestActiveSource is acknowledged, both broadcast injections are accepted, and the
 *    after-probe reports the peer the injected <Active Source> announced: available true,
 *    logical address 4, physical address 3.0.0.0, port HDMI2.
 *
 * @pass_criteria
 *  - Every required YAML post returns HTTP 200, requestActiveSource answers with
 *    result.success True, the after-probe parses with result.success True, result.available
 *    True, result.logicalAddress 4, result.physicalAddress "3.0.0.0" and result.port "HDMI2",
 *    and run_test() returns True.
 *
 * @failure_criteria
 *  - A response mismatch, a rejected vComponent post, a command failure, a JSON parsing
 *    error, or an unreachable endpoint; the after-probe reporting no active source, a different
 *    logical address, a different physical address or a different port - each of which means the
 *    injected announcement was not processed as the announcing peer claiming the bus;
 *    run_test() then returns False.
 */
"""


import time
import json
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

# log_with_timing is imported and deliberately not called: every case in this suite draws the
# same symbol set from utils.py so the import band stays uniform across the Testcases directory,
# and the pass path below inlines the HDMICEC_TIMING_ENABLED decision because it needs to choose
# the log level the message is routed through - log_with_timing only returns text. The flow cases
# additionally take send_vcomponent_command and HDMICEC_CMD_BASE, which the query cases do not.

# THE EXPECTED ACTIVE SOURCE, DERIVED FROM THE DOCUMENT THIS CASE POSTS.
# vcomponent_configurations/commands/Process_Active_Source.yaml carries the raw frame
# ["0x4F", "0x82", "0x30", "0x00"]: header 0x4F is initiator 4 to destination 0x F (broadcast),
# 0x82 is <Active Source>, and the two operand bytes are a PhysicalAddress whose nibbles are
# 3.0.0.0 (Operands.hpp packs byte0 as n0<<4|n1 and byte1 as n2<<4|n3).
#
# They are named constants rather than literals inside the assertion so the three values that
# must move together if the topology ever moves are declared in one place, next to the document
# that produces them. A YAML reader would couple them harder still, and is deliberately not
# introduced: no module in this suite parses fixture CONTENT - TCID33 discovers filenames and
# nothing more - and adding a parser here would be test-harness machinery no finding asks for.
EXPECTED_ACTIVE_SOURCE_LA = 4
EXPECTED_ACTIVE_SOURCE_PHYSICAL = "3.0.0.0"
# GetActiveSource builds the port string from the first nibble of the physical address:
# nibble 0 reports "TV", any other nibble n reports "HDMI" followed by n - 1
# (HdmiCecSinkImplementation::GetActiveSource). Nibble 3 is therefore the television's third HDMI
# input, reported as HDMI2.
EXPECTED_ACTIVE_SOURCE_PORT = "HDMI2"


def _post_hdmicec(yaml_file):
    """Post a HdmiCec vComponent YAML command."""
    # HTTP 200 is the only acceptance, and utils.send_vcomponent_command is fail-closed about it:
    # a missing document, a refused path, a curl failure and the "applied the YAML then closed
    # the connection without answering" case (curl exit 52) all arrive here as code 0 rather than
    # being laundered into a synthetic 200. The body is logged verbatim and never parsed, because
    # on those paths it carries curl's diagnosis rather than a response document - so every
    # filename below is verified against the fixture tree, a typo being otherwise invisible.
    http_code, body = send_vcomponent_command(f"{HDMICEC_CMD_BASE}/{yaml_file}")
    log_info(f"  vComponent POST {yaml_file}: HTTP {http_code}  {sanitise_for_log(body)}")
    return http_code == 200


# ── THE ANNOUNCED PEER, TAKEN FROM THE FIXTURES THEMSELVES ────────────────────────────────────
# Process_Active_Source.yaml carries payload ["0x4F", "0x82", "0x30", "0x00"]: header 0x4F is
# initiator 4 with destination 0xF (broadcast), opcode 0x82 is <Active Source>, and the two operand
# bytes are the nibble-packed physical address 3.0.0.0 - SONY's own address in this suite's
# topology. HdmiCecSinkProcessor::process(const ActiveSource &, const Header &) accepts broadcast
# only and then calls addDevice(4) and updateActiveSource(4, 3.0.0.0), so the outcome is fully
# determined rather than one plausible outcome among several: getActiveSource must afterwards report
# that address.
#
# PhysicalAddress::toString() renders {0x30, 0x00} as "3.0.0.0" and GetActiveSource derives the port
# from getByteValue(0), which is 3, as "HDMI" + (3 - 1) - hence "HDMI2" (ccec/Operands.hpp;
# HdmiCecSinkImplementation::GetActiveSource).
#
# ONE SOURCE OF TRUTH, AND IT IS THE FIXTURE. These three are BOUND to the EXPECTED_ACTIVE_SOURCE_*
# values rather than restated, because _is_announced_peer compares Step 1's readings against them:
# any disagreement between the two families would mean the wait for the peer to take the bus could
# never be satisfied and would only ever expire.
ANNOUNCED_LOGICAL_ADDRESS = EXPECTED_ACTIVE_SOURCE_LA
ANNOUNCED_PHYSICAL_ADDRESS = EXPECTED_ACTIVE_SOURCE_PHYSICAL
ANNOUNCED_PORT = EXPECTED_ACTIVE_SOURCE_PORT

# Process_In_Active_Source.yaml carries ["0x40", "0x9D", "0x30", "0x00"]: header 0x40 is initiator 4
# DIRECTED to the sink at 0, which is what process(InActiveSource) requires - it ignores broadcast.
# updateInActiveSource clears m_currentActiveSource when it is the announcing address, so posting it
# after the announcement above drives getActiveSource to available false. That pair is what makes a
# deterministic BEFORE state establishable at all.
INACTIVE_SOURCE_YAML = "Process_In_Active_Source.yaml"
ACTIVE_SOURCE_YAML = "Process_Active_Source.yaml"

# Bounded budgets. Poll intervals, never a duration anything waits for: each loop leaves on the
# first reading that satisfies it and reports honestly when the budget expires.
TRANSITION_TIMEOUT_S = 10.0
TRANSITION_POLL_S = 0.25


def _active_source():
    '''Return the sink's active-source block as a dict, or None when it cannot be read.

    None means the reply was not a JSON-RPC result reporting success - a falsy response, the
    transport sentinel, an unparseable body, a non-object body, a non-object result, or success not
    True - which is deliberately distinct from a successful reply reporting no active source.
    '''
    response = send_curl_command(HdmiCecSinkApis.get_active_source)
    if not response or response.startswith("< No response"):
        return None
    try:
        envelope = json.loads(response)
    except json.JSONDecodeError:
        return None
    result = envelope.get("result") if isinstance(envelope, dict) else None
    if not isinstance(result, dict) or result.get("success") is not True:
        return None
    return result


def _wait_for_active_source(predicate, description):
    '''Poll getActiveSource until predicate(result) holds; returns (satisfied, last_result).

    Bounded with a monotonic clock, so no wall-clock adjustment can shorten or extend the budget.
    An unreadable reply does not satisfy the predicate and does not end the wait - the device may
    answer on the next poll - but it is the value returned if the budget expires, so the caller can
    tell "never became true" from "could not be read".
    '''
    deadline = time.monotonic() + TRANSITION_TIMEOUT_S
    last = None
    while True:
        result = _active_source()
        if result is not None:
            last = result
            if predicate(result):
                return True, last
        if time.monotonic() >= deadline:
            log_error(
                f"✖ {description} was not observed within {TRANSITION_TIMEOUT_S:.0f}s; "
                f"last reading {last!r}"
            )
            return False, last
        time.sleep(TRANSITION_POLL_S)


def _is_announced_peer(result):
    '''True when the active-source block names exactly the peer the fixture announces.'''
    return (
        result.get("available") is True
        and result.get("logicalAddress") == ANNOUNCED_LOGICAL_ADDRESS
        and result.get("physicalAddress") == ANNOUNCED_PHYSICAL_ADDRESS
    )


# The active-source block observed before this case arranged anything, handed to cleanup(). None
# means it was never captured, so there is nothing to put back.
_captured_active_source = None


def cleanup():
    '''Put the sink's notion of the active source back where this case found it.

    The suite's fixtures can announce exactly one peer as active source and can clear the selection,
    so this hook can restore exactly two states: "no active source" and "the announced peer". When
    the captured state was a DIFFERENT peer it cannot be reproduced - no fixture announces another
    address - and that residual is reported rather than papered over with a synthetic value, which
    would be a second uncontrolled change dressed up as a cleanup.

    SuitManager runs this unconditionally, so it assumes nothing about how far run_test() got.
    Idempotent: the capture is consumed on read.
    Returns:
        True when there was nothing to restore or the captured state was reproduced and confirmed;
        False when a required post was refused, the restore could not be confirmed, or the captured
        state names a peer no fixture can announce.
    '''
    global _captured_active_source
    if _captured_active_source is None:
        log_info("TCID17 cleanup: no active-source state was captured, nothing to restore")
        return True

    captured = _captured_active_source
    _captured_active_source = None

    current = _active_source()
    if current is not None and (
        current.get("available") == captured.get("available")
        and current.get("logicalAddress") == captured.get("logicalAddress")
    ):
        log_info("TCID17 cleanup: the active source is already as it was found")
        return True

    if captured.get("available") is not True:
        log_info("TCID17 cleanup: restoring 'no active source'")
        if not _post_hdmicec(ACTIVE_SOURCE_YAML) or not _post_hdmicec(INACTIVE_SOURCE_YAML):
            log_error("TCID17 cleanup: a required post was refused, active source left as it is")
            return False
        cleared, last = _wait_for_active_source(
            lambda result: result.get("available") is not True, "the active source clearing"
        )
        if not cleared:
            log_error(f"TCID17 cleanup: the active source did not clear; last reading {last!r}")
            return False
        log_success("TCID17 cleanup: no active source, as found")
        return True

    if captured.get("logicalAddress") == ANNOUNCED_LOGICAL_ADDRESS:
        log_info(f"TCID17 cleanup: re-announcing LA {ANNOUNCED_LOGICAL_ADDRESS} as active source")
        if not _post_hdmicec(ACTIVE_SOURCE_YAML):
            log_error("TCID17 cleanup: the announcement was refused, active source left as it is")
            return False
        restored, last = _wait_for_active_source(
            _is_announced_peer, "the announced peer becoming active source again"
        )
        if not restored:
            log_error(f"TCID17 cleanup: the peer did not become active source; last {last!r}")
            return False
        log_success("TCID17 cleanup: announced peer restored as active source")
        return True

    log_warning(
        "TCID17 cleanup: the active source found at entry was LA "
        f"{captured.get('logicalAddress')}, which no fixture in this suite can announce, so it "
        "cannot be reproduced. Residual reported: the active source is now LA "
        f"{ANNOUNCED_LOGICAL_ADDRESS}. Closing this would need a per-peer <Active Source> fixture."
    )
    return False


def run_test():
    '''Negotiate the active source and require the announced peer to become the active source.

    The flow is arranged so that the assertion is a TRANSITION rather than a shape check: the
    active source is first driven to a known "none" state, then requestActiveSource is dispatched,
    the peer answers through the injected fixtures, and the sink must end up reporting exactly the
    peer those fixtures announce. A run in which nothing moved therefore fails.
    Returns:
        True when the deterministic before state was established, requestActiveSource was
        acknowledged, every required injection was accepted, and the sink then reported the
        announced peer as active source; False on any transport failure, a rejected injection, an
        unreadable reply, or an absent transition.
    '''
    start_time = time.perf_counter()

    # CAPTURE, before anything is arranged, so cleanup() can put back what was found rather than
    # what this case created.
    global _captured_active_source
    _captured_active_source = _active_source()
    log_warning(f"Active source at entry: {_captured_active_source!r}")
    if _captured_active_source is None:
        log_error("✖ getActiveSource could not be read at entry")
        log_error("TCID17_Request_Active_Source_Flow Failed ❌")
        return False

    # ── ARRANGE: drive the active source to a KNOWN state ──────────────────────────────────────
    # Announcing the peer and then withdrawing it is the only deterministic route to "no active
    # source": updateInActiveSource clears the selection only when the withdrawing address is the
    # one currently selected, so the announcement must come first. Both posts are REQUIRED - a
    # refused fixture means the before state is unknown, and an assertion against an unknown before
    # state is exactly what this case is being fixed not to do.
    log_info("TCID17 Step 1: drive the active source to a known 'none' state")
    if not _post_hdmicec(ACTIVE_SOURCE_YAML):
        log_error("✖ the <Active Source> announcement was refused")
        log_error("TCID17_Request_Active_Source_Flow Failed ❌")
        return False
    claimed, _ = _wait_for_active_source(_is_announced_peer, "the announced peer taking the source")
    if not claimed:
        log_error("TCID17_Request_Active_Source_Flow Failed ❌")
        return False
    if not _post_hdmicec(INACTIVE_SOURCE_YAML):
        log_error("✖ the <Inactive Source> withdrawal was refused")
        log_error("TCID17_Request_Active_Source_Flow Failed ❌")
        return False
    cleared, before = _wait_for_active_source(
        lambda result: result.get("available") is not True, "the active source clearing"
    )
    if not cleared:
        log_error("TCID17_Request_Active_Source_Flow Failed ❌")
        return False
    log_success(f"✔ before state established: available={before.get('available')!r}")

    # ── ACT: ask over JSON-RPC, then let the peer answer through the fixtures ───────────────────
    log_info("TCID17 Step 2: requestActiveSource over JSON-RPC")
    curl_response = send_curl_command(HdmiCecSinkApis.request_active_source)
    if not curl_response:
        log_error("✖ requestActiveSource command not sent")
        log_error("TCID17_Request_Active_Source_Flow Failed ❌")
        return False
    # send_curl_command reports every transport failure with the TRUTHY "< No response from
    # WPEFramework >" sentinel, so the falsy check above cannot see one; testing the prefix utils.py
    # documents is what separates an unreachable device from a malformed payload.
    if curl_response.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        log_error("TCID17_Request_Active_Source_Flow Failed ❌")
        return False
    log_warning(f"Response: {curl_response}")

    # ACT, PART 2 - supply the peer side by injecting broadcast frames from the emulated devices
    # the topology already carries. The settle waits are bounded and fixed: the sink processes
    # each frame on its own listener thread, and one second is the cadence this suite uses between
    # injections. No polling loop and no wall-clock deadline appear here, so the case costs the
    # same on every run.
    ok1 = _post_hdmicec("Process_Request_Active_Source.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)
    ok2 = _post_hdmicec("Process_Active_Source.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)

    if not (ok1 and ok2):
        log_error("✖ required vComponent emulation posts failed")
        return False

    # SHARED STATE. On a passing run the residual is KNOWN, not incidental: logical address 4
    # holds the active source at 3.0.0.0, because that is what the assertions below require. That
    # is the effect under test, and there is nothing to restore it to - the value it replaced was
    # itself whatever an earlier case left behind. TCID18_Set_Active_Source_Flow is the next entry
    # in the suite's declared order; it re-establishes this same state as its own first act and
    # then moves the source to the television, so the residual is consumed rather than leaked and
    # TCID18 does not depend on this case having run. No restore is attempted here, since writing
    # a synthetic value back would be a second uncontrolled change rather than a cleanup.
    log_info("Executing the curl command get active source (after)")
    after = send_curl_command(HdmiCecSinkApis.get_active_source)

    if not after:
        log_error("✖ final getActiveSource command not sent")
        return False

    if after.startswith("< No response"):
        log_error("✖ no response from WPEFramework")
        return False

    log_warning(f"Final active source: {after}")

    try:
        # The before-probe and the acknowledgement are parsed alongside the after-probe so that a
        # malformed body anywhere in the flow is reported as the JSON failure it is.
        before_result = json.loads(before).get("result", {})
        request_ack = json.loads(curl_response).get("result", {})
        after_body = json.loads(after)
        result = after_body.get("result", {})

        ack_ok = request_ack.get("success") is True
        has_success = result.get("success") is True

        log_info(
            f"  Active source available before: {before_result.get('available')}"
            f"  after: {result.get('available')}"
        )
        log_info(
            f"  Active source after: logicalAddress={result.get('logicalAddress')} "
            f"physicalAddress={result.get('physicalAddress')!r} port={result.get('port')!r}"
        )

        if not ack_ok:
            log_error("✖ requestActiveSource did not report success")
            log_warning(f"Actual  : {json.dumps(request_ack, indent=2, sort_keys=True)}")
            log_error("TCID17_Request_Active_Source_Flow Failed ❌")
            return False

        if not has_success:
            log_error("✖ the after-probe getActiveSource did not report success")
            log_warning(f"Actual  : {json.dumps(after_body, indent=2, sort_keys=True)}")
            log_error("TCID17_Request_Active_Source_Flow Failed ❌")
            return False

        # THE EXACT OUTCOME, FIELD BY FIELD. Each expectation is one of the module constants
        # above, every one of them derived from the bytes of the document posted in ACT PART 2 and
        # from the handler chain that consumes it - see @details. Reported one field at a time so
        # a failure names WHICH part of the announcement did not land: availability distinguishes
        # "the frame was discarded" from "a different peer holds the source", the logical address
        # distinguishes the announcing peer from any other, the physical address proves the
        # operand was read rather than defaulted, and the port proves the sink derived the route
        # from that operand rather than carrying a stale one.
        if result.get("available") is not True:
            log_error(
                "✖ the after-probe reports no active source, so the injected broadcast "
                "<Active Source> was not processed - a discarded frame leaves the sink with "
                "m_currentActiveSource at -1 and that is exactly this reading"
            )
            log_warning(f"Actual  : {json.dumps(after_body, indent=2, sort_keys=True)}")
            log_error("TCID17_Request_Active_Source_Flow Failed ❌")
            return False

        for field, expected in (
            ("logicalAddress", EXPECTED_ACTIVE_SOURCE_LA),
            ("physicalAddress", EXPECTED_ACTIVE_SOURCE_PHYSICAL),
            ("port", EXPECTED_ACTIVE_SOURCE_PORT),
        ):
            actual = result.get(field)
            if actual != expected:
                log_error(
                    f"✖ the after-probe reports {field}={actual!r}, expected {expected!r} - the "
                    "value the injected <Active Source> announcement establishes"
                )
                log_warning(f"Actual  : {json.dumps(after_body, indent=2, sort_keys=True)}")
                log_error("TCID17_Request_Active_Source_Flow Failed ❌")
                return False

        log_success(
            f"✔ active source is the announcing peer: logical address "
            f"{EXPECTED_ACTIVE_SOURCE_LA} at {EXPECTED_ACTIVE_SOURCE_PHYSICAL} on "
            f"{EXPECTED_ACTIVE_SOURCE_PORT}"
        )
        elapsed_time = time.perf_counter() - start_time
        log_success(log_with_timing("TCID17_Request_Active_Source_Flow Passed ✅", elapsed_time))
        return True
    except json.JSONDecodeError:
        log_error("Invalid JSON response")
        log_error("TCID17_Request_Active_Source_Flow Failed ❌")
        return False
    # NOTHING MAY FOLLOW THE except HANDLER ABOVE.  The try/except that closes this function ends
    # in a terminal `return False`, so any statement added after it is unreachable and Python will
    # never execute a line of it.  Assert the active-source transition once, in the reachable flow
    # above, against EXPECTED_ACTIVE_SOURCE_* - which are derived from the values
    # vcomponent_configurations/commands/Process_Active_Source.yaml actually produces
    # (["0x4F","0x82","0x30","0x00"] is physical address 3.0.0.0, which GetActiveSource reports on
    # HDMI2).  A second copy of that assertion is how two copies drift apart.
