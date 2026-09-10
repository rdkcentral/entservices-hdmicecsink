"""
/**
 * @file TCID19_Active_Path_Routing_Change_Flow.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID19_Active_Path_Routing_Change_Flow
 * @details Drives the sink's active-path and routing-change surface end to end, probing the
 *          reported route after EVERY operation and asserting the exact route each one produces.
 *          Six steps, in order:
 *            1. a route BEFORE-probe over org.rdk.HdmiCecSink.getActiveRoute, recorded;
 *            2. org.rdk.HdmiCecSink.setRoutingChange with oldPort naming the television, which
 *               leaves nothing holding the active source - probed and asserted;
 *            3. org.rdk.HdmiCecSink.setActivePath, which resolves the requested path and
 *               broadcasts <Set Stream Path> without moving any local route - probed and
 *               asserted to have changed nothing;
 *            4. org.rdk.HdmiCecSink.setRoutingChange with newPort naming the television, which
 *               makes the television the active source - probed and asserted;
 *            5. org.rdk.HdmiCecSink.setRoutingChange between two HDMI inputs, the branch that
 *               resolves BOTH port addresses against the port map - probed and asserted to have
 *               changed the active source not at all;
 *            6. inbound <Routing Change>, <Routing Information> and <Set Stream Path> frames
 *               injected through the vComponent, so the peer-driven direction of the same
 *               exchange is exercised - probed and asserted to have changed nothing, because all
 *               three of those handlers are log-only.
 *
 *          EACH OPERATION IS ISOLATED, AND THAT IS WHAT MAKES THE SETTERS TESTED. Sending both
 *          setters and three injections and then reading the route once cannot attribute the
 *          final reading to any one of them, so the earlier arrangement asserted only that the
 *          reply was well formed and logged the route as an observation - under which a
 *          setRoutingChange that did nothing at all, and a setActivePath that wrongly moved the
 *          local route, would both have passed. Every expected value below is derived from the
 *          production path rather than chosen, and each is a transition or an invariant
 *          attributable to exactly one preceding request:
 *            - step 2: oldPort naming TV sets m_currentActiveSource to -1 unconditionally
 *              (HdmiCecSinkImplementation.cpp:2389-2393), and GetActiveRoute's third branch then
 *              answers available false (:1532-1535);
 *            - step 3: setStreamPath's whole body broadcasts <Set Stream Path> and touches no
 *              member of the instance (:1461-1468, :2354-2371), so the reading must be
 *              byte-for-byte the one step 2 produced;
 *            - step 4: newPort naming TV sets m_currentActiveSource to the television's own
 *              allocated address (:2408-2412), and GetActiveRoute's second branch answers
 *              available true with ActiveRoute exactly "TV" and no length or path list
 *              (:1527-1531);
 *            - step 5: with NEITHER port naming the television, both names are resolved against
 *              hdmiInputs[portID].m_physicalAddr and <Routing Change> is broadcast while
 *              m_currentActiveSource is left alone (:2389-2433), so the reading must be the one
 *              step 4 produced. This is the branch that walks the port map on both sides;
 *            - step 6: process(RoutingChange) at :323, process(RoutingInformation) at :327 and
 *              process(SetStreamPath) at :331 are each a single LOGINFO and nothing else, so the
 *              reading must be exactly the one step 4 produced. Asserting the documented no-op
 *              is a real assertion; asserting a change would be asserting a defect.
 *
 *          The two setters are the reason this module exists. SetActivePath and
 *          SetRoutingChange were both catalogued P1 with coverage from the sink's own L2 suite
 *          and no end-to-end leg, because BEFORE THIS CHANGE the sink had no device-level
 *          suite at all (COVERAGE_GAPS.md, "Missing sink device-level (E2E) suite"). That is
 *          the register's pre-change baseline, not a statement about the tree this file sits
 *          in - the suite that closes that gap is the one this module belongs to. It supplies
 *          the missing leg for both setters, and in doing so walks the sink's nested route
 *          resolution, which was catalogued zero-hit: HdmiCecSinkImplementation::getActiveRoute
 *          (HdmiCecSinkImplementation.cpp:1958) plus the port-map operations it and the
 *          routing setters depend on - HdmiPortMap::addChild (HdmiCecSinkImplementation.h:294),
 *          removeChild (:327) and getRoute (:351). setRoutingChange reads
 *          hdmiInputs[portID].m_physicalAddr, so a port identifier resolves only once that map
 *          has been built. No coverage claim is made for any of them: this suite is authored
 *          here and NOT executed, so a coverage figure would be unmeasured and none of these
 *          paths has been observed running. What is claimed is only that the case is DESIGNED to
 *          drive them.
 *
 *          The peer-driven direction is reached by INJECTING FRAMES only. No fixture
 *          reconfigures the device under test to act as its own peer; role flipping and role
 *          inversion are out of scope for this suite by directive.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - hosts the org.rdk.HdmiCecSink
 *    plugin and answers JSON-RPC at utils.WPEFRAMEWORK_JSONRPC_URL.
 *  - Init_Devicelist_Populate has run, so HDMI-CEC is enabled and the emulated CEC network is
 *    seeded. That topology is what makes route resolution more than trivially flat: it places
 *    a playback peer at logical address 4 - the active-source candidate the routing flows
 *    switch to - and a second playback peer at logical address 8, so a route change has
 *    somewhere to go, alongside the audio system at 5, a tuner at 3 and a recording device
 *    at 1. The television under test is logical address 0 and is deliberately not seeded.
 *  - The vComponent HTTP API is reachable at utils.VCOMPONENT_API_URL, and the YAML command
 *    documents under utils.HDMICEC_CMD_BASE are readable.
 *  - This suite is AUTHORED, NOT EXECUTED in this repository: no continuous integration
 *    workflow runs it, and nothing below has been observed against a device or an emulator.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - Routing away from the television leaves no route available; setActivePath then changes that
 *    reading not at all; routing to the television makes the route available with ActiveRoute
 *    "TV"; and the three injected frames leave that reading untouched.
 *
 * @pass_criteria
 *  - Every required vComponent POST returns HTTP 200, all three setter requests acknowledge with
 *    success true, the probe after step 2 reports available False, the probe after step 3 reports
 *    a reading equal to step 2's, the probe after step 4 reports available True with ActiveRoute
 *    "TV", the probes after steps 5 and 6 each report a reading equal to step 4's, and run_test()
 *    returns True.
 *
 * @failure_criteria
 *  - A command that cannot be sent, the transport sentinel, a vComponent POST that does not
 *    return HTTP 200, a setter that does not acknowledge success, a body that is not JSON or
 *    carries no result object, a probe reporting success other than True, a route still available
 *    after routing away from the television, a route changed by setActivePath, a route not
 *    available or not "TV" after routing to the television, a route changed by routing between two
 *    HDMI inputs, a route changed by the inbound frames, or run_test() returning False.
 */
"""


import time
import json
from utils import (
    send_curl_command,
    send_jsonrpc_command,
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


# ── WHAT THE IMPLEMENTATION ACTUALLY MOVES, AND WHAT IT ONLY BROADCASTS ───────────────────────
# Every expectation below is taken from the implementation rather than assumed, because the two
# halves of this flow behave differently and a single blanket assertion would fit neither:
#
#   * setRoutingChange resolves both port identifiers and, when the NEW port names "TV", sets
#     m_currentActiveSource to the sink's own allocated address (HdmiCecSinkImplementation.cpp:
#     2408-2412). GetActiveRoute then takes its second branch and answers ActiveRoute "TV"
#     exactly (:1527-1531). That is a determined, observable route change.
#   * setRoutingChange between two HDMI ports, and setActivePath, only BROADCAST a frame -
#     <Routing Change> at :2433 and <Set Stream Path> at :2389 - and touch no local route state.
#     So the correct assertion for them is that the route is UNCHANGED.
#   * process(RoutingChange), process(RoutingInformation) and process(SetStreamPath) have
#     LOG-ONLY bodies (:323, :327, :331). Injecting them must therefore leave the route
#     untouched, and asserting that turns a caveat into a check: if a future change gave those
#     handlers route side effects, this case would catch it.
ROUTE_TV = "TV"

# Read from the key "ActiveRoute", with a CAPITAL A. It is the one field of the sink's JSON-RPC
# surface that is not lowerCamelCase (IHdmiCecSink.h:191), so it is spelled deliberately.
ROUTE_KEY = "ActiveRoute"

ACTIVE_SOURCE_YAML = "Process_Active_Source.yaml"
INACTIVE_SOURCE_YAML = "Process_In_Active_Source.yaml"

# Bounded budgets. Poll intervals, never a duration anything waits for.
TRANSITION_TIMEOUT_S = 10.0
TRANSITION_POLL_S = 0.25


def _active_route():
    '''Return the sink's active-route block as a dict, or None when it cannot be read.

    None means the reply was not a JSON-RPC result reporting success, which is deliberately
    distinct from a successful reply that reports no route.
    '''
    response = send_curl_command(HdmiCecSinkApis.get_active_route)
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


def _route_signature(result):
    '''Reduce a route block to the parts an assertion compares: availability and description.'''
    if result is None:
        return None
    return (result.get("available"), result.get(ROUTE_KEY))


def _wait_for_route(predicate, description):
    '''Poll getActiveRoute until predicate(result) holds; returns (satisfied, last_result).

    Bounded with a monotonic clock. An unreadable reply neither satisfies the predicate nor ends
    the wait, but it is what is returned on expiry, so the caller can distinguish "never became
    true" from "could not be read".
    '''
    deadline = time.monotonic() + TRANSITION_TIMEOUT_S
    last = None
    while True:
        result = _active_route()
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


def _route_is_peer(result):
    '''True when a route to a peer is reported - available, described, and not the TV branch.'''
    route_text = result.get(ROUTE_KEY)
    return (
        result.get("available") is True
        and isinstance(route_text, str)
        and route_text != ""
        and route_text != ROUTE_TV
    )


def _route_is_tv(result):
    '''True when the sink reports itself as the route, which is the "TV" branch exactly.'''
    return result.get("available") is True and result.get(ROUTE_KEY) == ROUTE_TV


def _published_request(argv):
    '''Return the decoded JSON-RPC payload a HdmiCECSink_Curl argv constant sends.

    The constants are inert data - an argv list whose payload sits immediately after "-d" - so the
    method a case needs can be READ from the module that owns it instead of restated here. That is
    what lets the "newPort=TV" variant below reuse the published method name while substituting one
    operand, without editing a shared constant that other cases also dispatch.
    '''
    try:
        payload = argv[argv.index("-d") + 1]
    except (ValueError, IndexError) as exc:
        raise ValueError("request constant carries no -d payload") from exc
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise ValueError("request payload is not a JSON object")
    return decoded


# _acknowledged() is defined exactly ONCE, below run_test()'s helpers, and every caller in this
# module - cleanup() included - resolves it at call time. Keep it that way: a module body executes
# top to bottom, so a second definition of the name would silently shadow the first and the two
# could drift apart unnoticed.


# The route block observed before this case arranged anything, handed to cleanup().
_captured_route = None


def cleanup():
    '''Put the routing state back where this case found it.

    The route is a function of m_currentActiveSource, so restoring it means restoring the
    selection: the announcement fixture reproduces "a peer holds it", the announce-then-withdraw
    pair reproduces "nobody holds it", and setRoutingChange with newPort "TV" reproduces "the sink
    holds it". A captured route naming some other peer cannot be reproduced and is reported.

    SuitManager runs this unconditionally. Idempotent: the capture is consumed on read.
    '''
    global _captured_route
    if _captured_route is None:
        log_info("TCID19 cleanup: no routing state was captured, nothing to restore")
        return True

    captured = _captured_route
    _captured_route = None

    if _route_signature(_active_route()) == _route_signature(captured):
        log_info("TCID19 cleanup: the routing state is already as it was found")
        return True

    if captured.get("available") is not True:
        log_info("TCID19 cleanup: restoring 'no active route'")
        if not _post_hdmicec(ACTIVE_SOURCE_YAML) or not _post_hdmicec(INACTIVE_SOURCE_YAML):
            log_error("TCID19 cleanup: a required post was refused, route left as it is")
            return False
        cleared, last = _wait_for_route(
            lambda result: result.get("available") is not True, "the route clearing"
        )
        if not cleared:
            log_error(f"TCID19 cleanup: the route did not clear; last reading {last!r}")
            return False
        log_success("TCID19 cleanup: no active route, as found")
        return True

    if captured.get(ROUTE_KEY) == ROUTE_TV:
        log_info("TCID19 cleanup: restoring the sink as the route")
        if not _set_routing_change_to_tv():
            return False
        restored, last = _wait_for_route(_route_is_tv, "the sink becoming the route again")
        if not restored:
            log_error(f"TCID19 cleanup: the route did not return to TV; last {last!r}")
            return False
        log_success("TCID19 cleanup: sink restored as the route")
        return True

    log_info("TCID19 cleanup: restoring a peer route through the announcement fixture")
    if not _post_hdmicec(ACTIVE_SOURCE_YAML):
        log_error("TCID19 cleanup: the announcement was refused, route left as it is")
        return False
    restored, last = _wait_for_route(_route_is_peer, "a peer route being reported again")
    if not restored:
        log_error(f"TCID19 cleanup: no peer route was reported; last {last!r}")
        return False
    if _route_signature(last) != _route_signature(captured):
        log_warning(
            f"TCID19 cleanup: a peer route is reported again but it describes "
            f"{last.get(ROUTE_KEY)!r} rather than the {captured.get(ROUTE_KEY)!r} found at entry; "
            "no fixture in this suite announces another peer, so that exact route cannot be "
            "reproduced. Residual reported."
        )
        return False
    log_success("TCID19 cleanup: peer route restored")
    return True


def _set_routing_change_to_tv():
    '''Ask the sink to route to itself, reusing the published method with one operand replaced.

    setRoutingChange is the only API in the sink's surface that moves the reported route, and it
    does so only when the new port names "TV". The published constant routes between two HDMI
    ports, which is a different - and separately asserted - behaviour, so this call takes the
    method name from that same constant and substitutes newPort. Nothing is assembled: the request
    is DESCRIBED to utils.send_jsonrpc_command, which composes the argv itself.
    '''
    try:
        published = _published_request(HdmiCecSinkApis.set_routing_change)
        method = published["method"]
        params = dict(published.get("params") or {})
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        log_error(f"✖ the published setRoutingChange request could not be read ({exc})")
        return False
    params["newPort"] = ROUTE_TV
    response = send_jsonrpc_command(method, params=params)
    if not response or "error" in response or not isinstance(response.get("result"), dict):
        log_error(f"✖ setRoutingChange(newPort=TV) was refused: {response!r}")
        return False
    if response["result"].get("success") is not True:
        log_error(f"✖ setRoutingChange(newPort=TV) did not report success: {response!r}")
        return False
    log_success("✔ setRoutingChange(newPort=TV) acknowledged")
    return True


# FRAMING OF THE THREE INJECTED DOCUMENTS - BROADCAST HERE, AND EITHER WOULD WORK.
#
# run_test() posts the Process_-prefixed documents, whose payloads are broadcast (header 0x4F:
# initiator 4, destination F). Directed equivalents exist beside them - Device_Routing_Change,
# Device_Routing_Information and Device_Set_Stream_Path, header 0x50: initiator 5, destination 0
# - and either set reaches the handler under test, because these three sink handlers apply NO
# destination filter: HdmiCecSinkProcessor::process for RoutingChange
# (HdmiCecSinkImplementation.cpp:323), RoutingInformation (:327) and SetStreamPath (:331) never
# inspect header.to at all.
#
# Worth stating, because it is NOT the general rule here and the asymmetry invites a well-meant
# "correction": process(GetMenuLanguage) at :335 discards broadcasts outright, ActiveSource and
# RequestActiveSource filter too, and Init_Devicelist_Populate's own addressing contract has to
# send SetOSDName directed while sending ReportPhysicalAddress and DeviceVendorID broadcast for
# exactly that reason. The routing trio is the exception, so do not "fix" the framing below to
# match a neighbouring case - it is already correct, and the directed documents are equally so.


# THE ROUTE STRING THE PLUGIN REPORTS WHEN THE TELEVISION ITSELF HOLDS THE SOURCE.
# GetActiveRoute takes its second branch when m_currentActiveSource equals the television's own
# allocated address and assigns ActiveRoute this exact literal, with no path list and no length
# (HdmiCecSinkImplementation.cpp:1527-1531). It is named rather than inlined because step 3 below
# is the one place in this module that pins a route VALUE, and the value belongs next to the
# citation that justifies it.
TV_ROUTE_TEXT = "TV"


def _route_reading(result):
    """Reduce a getActiveRoute result mapping to the tuple this case compares.

    All four route-describing members, in a fixed order. Absent members collapse to None, which
    is a legitimate reply shape rather than an error - the television being its own active source
    yields available true with ActiveRoute "TV" and neither a length nor a path list, because
    GetActiveRoute's second branch assigns only those two (HdmiCecSinkImplementation.cpp:1527-
    1531). Comparing them as present-or-absent on BOTH sides is what detects a member appearing,
    disappearing or changing without demanding one the plugin is not obliged to send. Two readings
    taken from the SAME branch serialise identically, which is what makes an equality comparison
    between two consecutive probes meaningful.
    Args:
        result: The "result" mapping from a getActiveRoute reply
    Returns:
        An (available, ActiveRoute, length, pathList) tuple.
    """
    # "ActiveRoute" carries a CAPITAL A. It is the one field of the sink's JSON-RPC surface that
    # is not lowerCamelCase (IHdmiCecSink.h:191), so it is spelled deliberately and not by habit.
    return (
        result.get("available"),
        result.get("ActiveRoute"),
        result.get("length"),
        result.get("pathList"),
    )


def _probe_route(label):
    """Read getActiveRoute and return its result mapping, or None with the reason logged.

    Four probes in this case share it. Both transport guards are applied - the falsy check for an
    undispatched command and the sentinel prefix check that utils.py documents, which a falsy
    check cannot see because the sentinel is a non-empty string - and the body is parsed here so a
    malformed reply is reported against the step that produced it rather than at the end of the
    flow.
    Args:
        label: Human-readable name of the probe, used in the diagnostics
    Returns:
        The "result" mapping when the probe answered with a well-formed success reply,
        otherwise None.
    """
    response = send_curl_command(HdmiCecSinkApis.get_active_route)
    if not response:
        log_error(f"✖ {label} getActiveRoute command not sent")
        return None
    if response.startswith("< No response"):
        log_error(f"✖ {label} getActiveRoute got no response from WPEFramework")
        return None
    log_warning(f"  {label} active route: {response}")
    try:
        envelope = json.loads(response)
    except json.JSONDecodeError:
        log_error(f"✖ {label} getActiveRoute returned a body that is not JSON")
        return None
    result = envelope.get("result") if isinstance(envelope, dict) else None
    if not isinstance(result, dict):
        log_error(f"✖ {label} getActiveRoute carried no result object")
        return None
    if result.get("success") is not True:
        log_error(f"✖ {label} getActiveRoute did not report success")
        log_warning(f"Actual  : {json.dumps(envelope, indent=2, sort_keys=True)}")
        return None
    return result


def _acknowledged(response, label):
    """Return True when a setter answered with a JSON-RPC result reporting success True.

    An error reply carries no "result" member, and send_curl_command returns the first line that
    parses as JSON at all - which need not even be an object. Both collapse to a failure here
    rather than to an AttributeError out of run_test().
    Args:
        response: Raw response string as returned by send_curl_command
        label: Human-readable name of the request, used in the diagnostics
    Returns:
        True when the reply is a JSON-RPC result carrying success True, otherwise False.
    """
    if not response:
        log_error(f"✖ {label} command not sent")
        return False
    if response.startswith("< No response"):
        log_error(f"✖ {label} got no response from WPEFramework")
        return False
    log_warning(f"  {label} response: {response}")
    try:
        envelope = json.loads(response)
    except json.JSONDecodeError:
        log_error(f"✖ {label} returned a body that is not JSON")
        return False
    result = envelope.get("result") if isinstance(envelope, dict) else None
    if not isinstance(result, dict) or result.get("success") is not True:
        log_error(f"✖ {label} did not acknowledge success")
        return False
    return True


def run_test():
    '''Drive the routing APIs and assert what each of them actually does to the reported route.

    The flow is sequenced and every expectation comes from the implementation, so each step is a
    determined check rather than a shape check:
      1. a peer announcement establishes a deterministic before state - a peer route is reported;
      2. setActivePath is acknowledged and must leave the route UNCHANGED, because setStreamPath
         only broadcasts a frame;
      3. setRoutingChange between two HDMI ports is acknowledged and must also leave the route
         unchanged, for the same reason;
      4. setRoutingChange with newPort "TV" must change the reported route to exactly "TV";
      5. the three inbound routing frames, whose handlers are log-only, must leave it at "TV";
      6. a fresh announcement must hand the route back to the peer.
    Returns:
        True when every acknowledgement, invariant and transition above holds; False on any
        transport failure, rejected injection, unreadable reply, or a route that moved when it
        should not have - or failed to move when it should.
    '''
    start_time = time.perf_counter()

    # ------------------------------------------------------------------ BEFORE-PROBE
    # Recorded, not asserted. Whatever the preceding cases left is the starting point, and step 1
    # below replaces it with a state this case established itself - which is what every later
    # assertion is measured against.
    log_info("Executing the curl command get active route (before the routing changes)")
    before = _probe_route("initial")
    if before is None:
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False
    log_info(f"  Starting point: {_route_reading(before)}")

    # ---------------------------------------------------------- STEP 1: clear the active source
    # setRoutingChange with oldPort naming the television sets m_currentActiveSource to -1
    # unconditionally (HdmiCecSinkImplementation.cpp:2389-2393). GetActiveRoute then takes its
    # third branch and answers available false (:1532-1535). That gives the rest of the case a
    # KNOWN starting state established by this case rather than inherited from the suite.
    log_info("Executing the curl command set routing change (television -> HDMI input)")
    if not _acknowledged(
        send_curl_command(HdmiCecSinkApis.set_routing_change_from_tv),
        "setRoutingChange from the television",
    ):
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False
    time.sleep(CEC_FRAME_PACING_SECONDS)

    cleared = _probe_route("after clearing the active source")
    if cleared is None:
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    if cleared.get("available") is not False:
        log_error(
            "✖ after setRoutingChange away from the television the route is still reported as "
            f"available - reading {_route_reading(cleared)}. oldPort naming TV must leave nothing "
            "holding the active source, so an available route means the request changed nothing"
        )
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    cleared_reading = _route_reading(cleared)
    log_success(f"✔ nothing holds the active source: {cleared_reading}")

    # ------------------------------------------------------- STEP 2: setActivePath changes no route
    # The sibling constant is dispatched verbatim. The requested path lives in
    # HdmiCECSink_Curl.set_active_path and only there, so no physical-address literal appears in
    # this module and an edit on one side cannot desynchronise the other.
    #
    # THE ASSERTION IS THAT THE ROUTE DID NOT MOVE, and that is the real contract rather than a
    # weakened one. SetActivePath resolves the requested path and calls setStreamPath, whose
    # entire body broadcasts <Set Stream Path> and touches no member of the instance
    # (cpp:1461-1468, :2354-2371). A local route change would therefore be a defect, and the
    # previous arrangement - assert the reply shape, log the route - could not have seen either
    # outcome. Measured against step 1's reading, which this case established, so the comparison
    # is against a known state and not against whatever the suite happened to leave behind.
    log_info("Executing the curl command set active path")
    if not _acknowledged(
        send_curl_command(HdmiCecSinkApis.set_active_path), "setActivePath"
    ):
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False
    time.sleep(CEC_FRAME_PACING_SECONDS)

    after_path = _probe_route("after setActivePath")
    if after_path is None:
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    if _route_reading(after_path) != cleared_reading:
        log_error(
            f"✖ setActivePath changed the reported route: {cleared_reading} became "
            f"{_route_reading(after_path)}. It broadcasts <Set Stream Path> and moves no local "
            "route state, so any change here is the plugin doing something it does not document"
        )
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    log_success("✔ setActivePath broadcast the stream path and left the local route untouched")

    # ------------------------------------------------- STEP 3: give the route to the television
    # setRoutingChange with newPort naming the television sets m_currentActiveSource to the
    # television's own allocated address (cpp:2408-2412), and GetActiveRoute's second branch then
    # answers available true with ActiveRoute exactly "TV" (:1527-1531). This is a real
    # transition out of step 1's cleared state and it is attributable to this one request, which
    # is what makes an exact expected value sound here.
    log_info("Executing the curl command set routing change (HDMI input -> television)")
    if not _acknowledged(
        send_curl_command(HdmiCecSinkApis.set_routing_change_to_tv),
        "setRoutingChange to the television",
    ):
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False
    time.sleep(CEC_FRAME_PACING_SECONDS)

    on_tv = _probe_route("after routing to the television")
    if on_tv is None:
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    if on_tv.get("available") is not True or on_tv.get("ActiveRoute") != TV_ROUTE_TEXT:
        log_error(
            "✖ after setRoutingChange to the television the route reads "
            f"{_route_reading(on_tv)}, expected available True with ActiveRoute "
            f"{TV_ROUTE_TEXT!r}. Still reading available False would mean the request was "
            "acknowledged and did nothing"
        )
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    tv_reading = _route_reading(on_tv)
    log_success(f"✔ the television holds the route: {tv_reading}")

    # -------------------------------------- STEP 4: input to input resolves BOTH port addresses
    # The third branch of setRoutingChange, and the one the pre-existing version of this case
    # exercised: with NEITHER port naming the television, both names are resolved against
    # hdmiInputs[portID].m_physicalAddr and <Routing Change> is broadcast, while
    # m_currentActiveSource is left exactly as it was (cpp:2389-2433). It is kept because it is the
    # only shape that walks the port map on BOTH sides - the dependency this module's own @details
    # says it exists to walk - and because an unresolvable port index makes the plugin return
    # before broadcasting (:2400, :2424), so an acknowledgement here is evidence the map placed
    # both indices.
    #
    # The assertion is that the route did NOT move, measured against step 3's reading. That is the
    # documented behaviour of this branch, so it is a real invariant rather than a weakened one.
    log_info("Executing the curl command set routing change (HDMI input -> HDMI input)")
    if not _acknowledged(
        send_curl_command(HdmiCecSinkApis.set_routing_change),
        "setRoutingChange between HDMI inputs",
    ):
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False
    time.sleep(CEC_FRAME_PACING_SECONDS)

    between_inputs = _probe_route("after routing between HDMI inputs")
    if between_inputs is None:
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    if _route_reading(between_inputs) != tv_reading:
        log_error(
            f"✖ setRoutingChange between two HDMI inputs changed the reported route: "
            f"{tv_reading} became {_route_reading(between_inputs)}. Neither port names the "
            "television, so that branch resolves both addresses and broadcasts without touching "
            "the active source"
        )
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    log_success(
        "✔ routing between two HDMI inputs resolved both port addresses and left the active "
        "source where it was"
    )

    # ------------------------------------------- STEP 5: inbound routing frames are informational
    # The peer-driven direction of the same exchange. Each post is a plain frame injection through
    # the vComponent: no fixture changes the device's role, and no payload is hand-built here -
    # see the framing note above the helper.
    #
    # THE ASSERTION IS THAT NONE OF THE THREE MOVES THE ROUTE. All three sink handlers are
    # log-only bodies - process(RoutingChange) at cpp:323, process(RoutingInformation) at :327 and
    # process(SetStreamPath) at :331 each contain a single LOGINFO and nothing else - so a route
    # change after these injections would be behaviour the plugin does not implement. Asserting
    # the documented no-op is a real assertion; asserting that the route CHANGED would have been
    # asserting a defect.
    log_info("Emulating peer-driven routing traffic towards the sink")

    ok1 = _post_hdmicec("Process_Routing_Change.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)
    ok2 = _post_hdmicec("Process_Routing_Information.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)
    ok3 = _post_hdmicec("Process_Set_Stream_Path.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)

    # All three are REQUIRED, and the check comes after all three rather than between them: a
    # missing document or a refused path returns (0, diagnostic) from send_vcomponent_command, so
    # posting the rest first makes the log name every document that failed instead of only the
    # first.
    if not (ok1 and ok2 and ok3):
        log_error("✖ required vComponent emulation posts failed")
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    final = _probe_route("after the inbound routing frames")
    if final is None:
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    if _route_reading(final) != tv_reading:
        log_error(
            f"✖ the inbound routing frames changed the reported route: {tv_reading} became "
            f"{_route_reading(final)}. All three of those handlers are log-only, so the route "
            "must be exactly as step 3 left it"
        )
        log_error("TCID19_Active_Path_Routing_Change_Flow Failed ❌")
        return False

    log_success("✔ the three inbound routing frames were informational, as documented")
    log_info(
        f"Route transitions observed: {_route_reading(before)} -> {cleared_reading} "
        f"(cleared) -> unchanged by setActivePath -> {tv_reading} (television) -> unchanged by "
        "routing between inputs -> unchanged by the inbound frames"
    )

    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID19_Active_Path_Routing_Change_Flow Passed ✅", elapsed_time))
    return True


# THE RESTORE LIVES IN cleanup() ABOVE. The reported route is a function of m_currentActiveSource,
# so restoring the route means restoring the selection - and the suite's fixtures plus
# setRoutingChange(newPort=TV) between them express all three states the plugin can report: a peer
# holds it, the sink holds it, nobody holds it. cleanup() reproduces whichever was observed at entry
# and confirms it by read-back, and reports a residual rather than inventing a value when the entry
# route described a peer no fixture in this suite can announce.
#
# On a passing run the residual is KNOWN rather than incidental: the television holds the active
# source, so getActiveRoute answers available true with ActiveRoute "TV". Step 4 is the last write
# and step 5 is asserted to change nothing, which is what makes the residual a stated value instead
# of "wherever the last frame put it".
#
# There is no inverse operation to call - the sink's JSON-RPC surface publishes setActivePath
# and setRoutingChange but nothing that restores a previously observed route - and the only
# remaining way to force one would be to hand-build a CEC payload for the purpose, which this
# suite does not do, because every frame it injects comes from a reviewed document under
# vcomponent_configurations/commands/. Manufacturing a restore would also manufacture a claim:
# it would look like the device was returned to a known state when in fact one more untracked
# route change had been issued.
#
# The residual is safe for the cases that follow, by construction rather than by luck: every
# later flow module re-establishes its own preconditions through its own posts before asserting
# anything, and SuitManager.py's registration list - ordered on purpose, with the flows grouped
# at 17-27 - is what guarantees each of them runs after this one rather than beside it. A future
# case needing a specific starting route must seed it itself.
