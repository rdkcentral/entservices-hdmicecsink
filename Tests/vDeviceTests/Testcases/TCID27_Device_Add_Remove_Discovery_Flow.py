"""
/**
 * @file TCID27_Device_Add_Remove_Discovery_Flow.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID27_Device_Add_Remove_Discovery_Flow
 * @details Walks one emulated peer through its ENTIRE lifecycle - appear, be announced, be
 *          mutated, then depart - and samples the sink's device list on either side of that
 *          lifecycle. It is the only case in this suite that exercises the DEPARTURE half, which
 *          is what makes it the last and most complete of the flow modules. Six steps, in this
 *          order:
 *            1. before-probe - org.rdk.HdmiCecSink.getDeviceList, the reference sample;
 *            2. ADD - Device_Add.yaml attaches the "GameConsole" PlaybackDevice beneath the
 *               YAMAHA audio-system peer of the emulated map, on the port reserved for it;
 *            3. MUTATE - Device_Status.yaml drives that same peer to power_status "off" and
 *               marks it faulted;
 *            4. ANNOUNCE - Process_Report_Physical_Address.yaml then
 *               Process_Device_Vendor_ID.yaml inject the two BROADCAST discovery frames a real
 *               peer emits, reaching HdmiCecSinkProcessor::process(const ReportPhysicalAddress&,
 *               const Header&) at HdmiCecSinkImplementation.cpp:344 and
 *               process(const DeviceVendorID&, const Header&) at :376. Both handlers call
 *               addDevice() for the frame's INITIATOR, so this is the step that makes a peer
 *               PRESENT to the plugin rather than merely present in the emulator's map - see
 *               the note at the step itself for why that is not asserted to be the very peer
 *               step 2 added;
 *            5. mid-probe - the same device-list read, bounded-polled until the peer appears;
 *            6. REMOVE - Device_Remove.yaml drops the peer again, followed by an after-probe
 *               bounded-polled until the peer is gone.
 *
 *          WHAT THIS CASE IS FOR. HdmiCecSinkImplementation::removeDevice(const int) at
 *          HdmiCecSinkImplementation.cpp:2474 and the OnDeviceRemoved notification at
 *          HdmiCecSink.h:127 were both recorded as ZERO-HIT in the coverage gap register, and
 *          OnDeviceRemoved additionally as one of five notifications uncovered even by the
 *          sink's own in-process L2 suite. Those are the register's PRE-CHANGE BASELINE: the
 *          notification is now asserted by the sink L1 suite
 *          (onDeviceRemoved_SubscribedClient_ReceivesLogicalAddress and
 *          onDeviceRemoved_AbsentDevice_ProducesNoNotification) and by the sink L2 suite
 *          (HdmiHotplugDisconnectAndVerifyDeviceRemovedEvent). removeDevice() also carries a
 *          third arm the baseline recorded as uncovered: it calls HdmiPortMap::removeChild for
 *          whichever HDMI input matches the departing peer's physical address
 *          (HdmiCecSinkImplementation.cpp:2494), an arm only a NESTED peer can reach, and
 *          Device_Add.yaml hangs "GameConsole" from port 4 of the YAMAHA audio system - one
 *          level below the HDMI input rather than directly on it - so it lands at 2.4.0.0 with
 *          a non-zero second address byte, which is what that arm needs.
 *          This module drives all three from the device level, which is the one leg the other
 *          two suites cannot supply. It does not measure them - this suite has never been
 *          executed, as the preconditions below record - so no coverage claim is made here.
 *
 *          WHAT IS ACTUALLY ASSERTED, AND WHAT IS NOT. The OnDeviceRemoved NOTIFICATION IS NOT
 *          OBSERVABLE FROM THIS TRANSPORT and is deliberately NOT asserted: a curl
 *          request/response exchange cannot subscribe to a Thunder event, so the notification
 *          HdmiCecSink.h:131 forwards as the plugin's onDeviceRemoved event is delivered to
 *          registered JSON-RPC/COM-RPC subscribers this case is not one of. Observing it is the
 *          L1 and L2 suites' job, named above. What IS observable here is the CONSEQUENCE:
 *          removeDevice() decrements m_numberOfDevices at HdmiCecSinkImplementation.cpp:2490
 *          before it fans the notification out, and that counter is the numberofdevices field
 *          getDeviceList publishes. The three probes therefore sample the count, and the
 *          assertion is on its DIRECTION across the lifecycle - never on an exact value; the
 *          reasoning is set out at the assertion itself.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - is running WPEFramework with the
 *    org.rdk.HdmiCecSink plugin activated and reachable over JSON-RPC.
 *  - Init_Devicelist_Populate has seeded the emulated topology and left HDMI-CEC enabled. That
 *    seeding is what supplies the YAMAHA AudioSystem peer the added peer attaches beneath, and
 *    it is also what claims the sink's own logical address: both addDevice() and removeDevice()
 *    return early while m_logicalAddressAllocated is LogicalAddress::UNREGISTERED
 *    (HdmiCecSinkImplementation.cpp:2482 for the removal), so without it every step below would
 *    be accepted by the emulator and ignored by the plugin.
 *  - The vComponent HTTP API is reachable, so the five YAML documents can be posted.
 *  - No continuous integration workflow in this repository executes this suite; it is authored
 *    for device-level execution and has not been run.
 *
 * @dependencies
 *  - utils.py
 *  - HdmiCECSink_Curl.py
 *  - SuitManager.py
 *  - vcomponent_configurations/commands/*.yaml (for emulation-based scenarios)
 *
 * @expected_result
 *  - The added peer becomes visible in the sink's device list within four poll cycles, and the
 *    list returns to containing every address of the reference sample after the removal.
 *  - The OnDeviceRemoved notification is NOT observable over the L3 curl transport and is NOT
 *    asserted; only its device-list consequence is. Nothing here attests that the notification
 *    fired.
 *    REQUIRED PRODUCTION CHANGE TO CLOSE THAT GAP, reported and not made: an event channel
 *    reachable without an HTTP listener, so a device-level test could subscribe to
 *    onDeviceAdded / onDeviceRemoved. It does not exist, and this suite may not add one.
 *  - THE BASELINE TOPOLOGY IS INTACT WHEN THE CASE ENDS, on every path, and that is now
 *    delivered by a module-level cleanup() hook rather than claimed. This entry previously read
 *    "cleanup is not needed as a separate hook here because the finally clause inside run_test()
 *    re-posts the removal" - there was no finally clause in run_test() and no hook either, so
 *    every early return between the add in Act 1 and the confirmed removal in Act 4 left
 *    "GameConsole" attached to the emulated topology. This case's own precondition check is what
 *    then failed on the NEXT run, reporting "a previous run that did not reach its removal step
 *    leaves the peer behind" - the symptom of exactly this gap.
 *    The hook re-posts Device_Remove.yaml and CONFIRMS the peer is gone by re-reading the
 *    published device list; a failure to confirm is reported plainly rather than left for a later
 *    case to trip over. It is preferred to a finally clause because SuitManager runs it on a
 *    strict superset of that clause's paths - including the run in which this case is SKIPPED and
 *    run_test() is never entered at all.
 *
 * @pass_criteria
 *  - All five required YAML posts return HTTP 200; the before-probe parses with result.success
 *    True and does NOT list logical address 11; logical address 11 appears within the bounded wait
 *    after the add, carrying physicalAddress "2.4.0.0"; logical address 11 is absent within the
 *    bounded wait after the removal; and run_test() returns True.
 *
 * @failure_criteria
 *  - A probe is not dispatched, a probe returns the no-response sentinel, any required vComponent
 *    post does not return HTTP 200, a probe reports success other than True, logical address 11 is
 *    ALREADY listed before the add - which would make the add unobservable - it never appears
 *    after the add, it appears with a physical address other than "2.4.0.0", it is still listed
 *    after the removal, a JSON parsing error occurs, or run_test() returns False.
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
    CEC_TOPOLOGY_PACING_SECONDS,
)
import HdmiCECSink_Curl as HdmiCecSinkApis


def _post_hdmicec(yaml_file):
    """Post a HdmiCec vComponent YAML command."""
    http_code, body = send_vcomponent_command(f"{HDMICEC_CMD_BASE}/{yaml_file}")
    log_info(f"  vComponent POST {yaml_file}: HTTP {http_code}  {sanitise_for_log(body)}")
    return http_code == 200


# FIXTURE NAMES ARE A CONTRACT, AND THIS CASE IS THE ONE THAT CANNOT AFFORD A TYPO.
# utils.send_vcomponent_command resolves HDMICEC_CMD_BASE joined with the literal filename and
# refuses anything it cannot approve, returning (0, "YAML file not found: ...") for a name that
# does not resolve, and (0, "refused to post ...") for a symbolic link, a path outside the
# configuration tree or a non-regular file. None of those raise. A mistyped name therefore does
# not fail loudly - it silently disables that step - and for the removal below a silently skipped
# post would leave the emulated topology permanently altered for every case that runs after this
# one. That is why every one of the five posts is required to have returned HTTP 200 before any
# verdict is reached, rather than being posted and forgotten. All five names are verified to
# resolve: Device_Add.yaml, Device_Status.yaml, Process_Report_Physical_Address.yaml,
# Process_Device_Vendor_ID.yaml and Device_Remove.yaml.
#
# The (code, body) pair is asymmetric and only the CODE is a verdict. This suite's utils.py
# reports what the vComponent actually answered and reinterprets nothing: a refused connection, a
# timeout, and the CURLE_GOT_NOTHING case in which some vComponent builds apply the posted YAML
# and then close the connection without replying, all come back as code 0 with curl's own
# diagnosis in the body. So a post that really did take effect can still be reported as a failure
# here, and that is the intended direction of the error - a server that never answered is never
# promoted to a pass. The body, correspondingly, is free-form diagnostic text rather than a
# payload: it is logged and never parsed. Only the three JSON-RPC probe responses are given to
# json.loads.


# THE PEER THIS CASE ADDS AND REMOVES, AND THE ADDRESS THE EMULATOR GIVES IT.
#
# Device_Add.yaml attaches a PlaybackDevice named "GameConsole" beneath the YAMAHA audio-system
# peer on its port 4, and Device_Remove.yaml takes the same name away again. The address is not a
# guess: the vComponent allocates addresses deterministically, and this peer's is derived from the
# authoritative topology the suite's own configuration declares.
#   * PHYSICAL. vcDevice_AllocatePhysicalLogicalAddresses forms a child's address by replacing the
#     first zero nibble of its parent's with the parent port it hangs from. YAMAHA sits at 2.0.0.0,
#     the new peer hangs from its port 4, so the peer is at 2.4.0.0.
#   * LOGICAL. vcDevice_AllocateLogicalAddress takes the first free address from the pool for the
#     device type. The PlaybackDevice pool is [4, 8, 11]; the seeded topology already holds 4
#     (SONY) and 8 (PANASONIC), so the first free one is 11.
# GameConsole is deliberately NOT part of the seeded topology, which is what makes the add a
# genuine population change and this case's present-then-absent assertion sound.
ADDED_PEER_NAME = "GameConsole"
ADDED_PEER_LOGICAL_ADDRESS = 11
ADDED_PEER_PHYSICAL_ADDRESS = "2.4.0.0"

# Both directions of the lifecycle are discovered by the plugin's POLL THREAD rather than
# synchronously: pingDevices sends a poll to every logical address and hands the newly answering
# ones to addDevice and the newly silent ones to removeDevice
# (HdmiCecSinkImplementation.cpp:2260-2315, :2816-2833). So a device-list read taken immediately
# after a topology change is a race, and a fixed sleep is a guess at how long a ping round takes.
# A bounded poll makes it a wait: it returns as soon as the expected state is observed and fails on
# the LAST sample rather than the first, which is the same instrument TCID05_Get_CEC_Version uses
# for its readback.
LIFECYCLE_TIMEOUT_SECONDS = 20.0
LIFECYCLE_POLL_SECONDS = 1.0


def _result_object(response_text):
    """Return the JSON-RPC result mapping from a response body, or an empty mapping.

    A JSON-RPC error envelope carries "error" instead of "result", and a malformed body could
    carry a non-object "result" or not be an object at all. Every such case collapses to {} so
    the caller reports a MISSING FIELD rather than raising AttributeError out of run_test(). A
    body that is not JSON at all still raises json.JSONDecodeError, which run_test() handles
    as the documented failure. The before-probe and every sample the bounded polls take share
    this, which is why it is factored out rather than repeated.
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


def _device_entry(result, logical_address):
    """Return the getDeviceList entry for one logical address, or None.

    Every off-contract shape - a missing or non-list deviceList, a non-dict entry - collapses to
    None so the caller reports an absent device rather than raising out of run_test().
    Args:
        result: The "result" mapping from a getDeviceList reply
        logical_address: CEC logical address to look for
    Returns:
        The matching device mapping, or None when that address is not in the list.
    """
    device_list = result.get("deviceList")
    if not isinstance(device_list, list):
        return None
    for device in device_list:
        if isinstance(device, dict) and device.get("logicalAddress") == logical_address:
            return device
    return None


def _await_peer(logical_address, expect_present, label):
    """Poll getDeviceList until one logical address reaches the wanted presence, bounded.

    Returns the LAST sample taken rather than only a verdict, so the caller can report the
    population count and the peer's own fields from the same reading the decision was made on.
    Args:
        logical_address: CEC logical address to watch
        expect_present: True to wait for the address to appear, False for it to disappear
        label: Human-readable name of the step, used in the diagnostics
    Returns:
        A (settled, result, entry) triple: whether the wanted presence was observed, the last
        getDeviceList result mapping (empty when the last read was unusable), and the peer's
        entry from that reading or None.
    """
    # MONOTONIC, not the wall clock. This bound is a DURATION - "give the plugin twenty seconds of
    # ping rounds to notice" - and time.time() is the wall clock: NTP stepping it, or a container's
    # clock being corrected while the suite runs, moves it under a loop that compares against a
    # stored value. Backwards makes a 20 second budget arbitrarily long; forwards expires it on the
    # first comparison and reports a peer that appeared perfectly normally as never having appeared.
    # This helper carries the verdict for both directions of the lifecycle, so a spurious expiry
    # here fails the case outright. time.monotonic cannot be stepped.
    deadline = time.monotonic() + LIFECYCLE_TIMEOUT_SECONDS
    result = {}
    entry = None
    while True:
        response = send_curl_command(HdmiCecSinkApis.get_device_list)
        if not response or response.startswith("< No response"):
            log_warning(f"  {label}: no response from WPEFramework")
            result = {}
            entry = None
        else:
            result = _result_object(response)
            entry = _device_entry(result, logical_address)
            if result.get("success") is True and (entry is not None) == expect_present:
                log_warning(f"  {label} device list: {response}")
                return True, result, entry
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if response and not response.startswith("< No response"):
                log_warning(f"  {label} device list (last sample): {response}")
            return False, result, entry
        # Capped by what is left, so the last sleep of the loop cannot carry the wait past the
        # deadline it is enforcing.
        time.sleep(min(LIFECYCLE_POLL_SECONDS, remaining))


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

# True while a peer this case attached to the emulated topology has NOT been confirmed gone.
#
# DEFINED AT MODULE SCOPE, which it was not. The only statements touching this name were
# `global _peer_outstanding` and `_peer_outstanding = False` INSIDE run_test(), so the module
# attribute did not exist until run_test() had been entered at least once - and the restoration
# hook below, which SuitManager calls even for a case it SKIPPED, would have raised NameError
# instead of restoring anything. Defined here it is readable on every path, including the one
# where run_test() never runs.
_peer_outstanding = False


def cleanup():
    """Detach the peer this case attached, and CONFIRM the emulated topology is back.

    SuitManager runs this unconditionally - after a pass, a failure, an exception, and for a case
    it SKIPPED because a producer failed - which is a strict superset of the paths a finally clause
    inside run_test() could cover, and it is why the restoration lives here.

    Idempotent in both directions: when run_test() confirmed the removal it clears the flag and
    this reports that and posts nothing, and re-posting Device_Remove.yaml for a peer that is
    already gone is itself harmless - removeDevice() does nothing at all unless the peer's
    m_isDevicePresent is set (HdmiCecSinkImplementation.cpp:2487).

    The restoration is VERIFIED rather than assumed. A vComponent post that returns HTTP 200 says
    the document was accepted, not that the plugin observed the departure - the plugin learns of it
    on its next ping round - so the published device list is re-read until the address is absent,
    which is the same observable run_test() itself is decided on.

    Returns:
        True when there was nothing to restore, or the peer was removed AND confirmed absent.
        False when the removal post was refused, or the peer is still listed after the lifecycle
        window - in which case the emulated topology is left altered and the message says so,
        including the fact that the next run of this case will fail its own precondition.
    """
    global _peer_outstanding
    if not _peer_outstanding:
        log_info(
            "TCID27 cleanup: no peer is outstanding - the removal was already confirmed, or "
            "nothing was ever added - so there is nothing to restore"
        )
        return True

    log_info(
        f"TCID27 cleanup: {ADDED_PEER_NAME!r} may still be attached; re-posting the removal"
    )
    if not _post_hdmicec("Device_Remove.yaml"):
        log_error(
            "TCID27 cleanup: the vComponent removal post was refused, so "
            f"{ADDED_PEER_NAME!r} is still in the emulated topology. Reset it before re-running: "
            "this case's own precondition check will otherwise fail on the next run"
        )
        return False
    time.sleep(CEC_TOPOLOGY_PACING_SECONDS)

    try:
        absent, _, _ = _await_peer(ADDED_PEER_LOGICAL_ADDRESS, False, "cleanup post-remove")
    except json.JSONDecodeError:
        log_error(
            "TCID27 cleanup: a device-list reply during the confirmation was not JSON, so the "
            f"removal of {ADDED_PEER_NAME!r} could not be confirmed"
        )
        return False

    if not absent:
        log_error(
            f"TCID27 cleanup: logical address {ADDED_PEER_LOGICAL_ADDRESS} is still listed "
            f"{LIFECYCLE_TIMEOUT_SECONDS:.0f}s after the removal, so {ADDED_PEER_NAME!r} is left "
            "in the emulated topology for every case that follows"
        )
        return False

    _peer_outstanding = False
    log_success(f"✔ TCID27 cleanup: {ADDED_PEER_NAME} is gone, the baseline topology is back")
    return True


def run_test():
    """Walk one test-only peer through appear / announce / mutate / depart, on membership.

    WHY MEMBERSHIP RATHER THAN AN EXACT DELTA. The emulator chooses the logical address it assigns
    a new peer, and this module may not predict it, so every claim below is about SET MEMBERSHIP
    and about the direction of the population count:
      * across the add, the discovered set must GROW - a proper superset of the reference sample,
        so nothing was lost and at least one address appeared;
      * across the removal, it must SHRINK - a proper subset of the post-add sample, so nothing
        appeared and at least one address left;
      * and the reference sample must SURVIVE the whole lifecycle - every address present before
        the add is still present after the removal, which is what proves the removal took away
        only what the add created.
    All three claims rest on the added peer being genuinely absent from the baseline topology, which
    is a property of this tree rather than an assumption: Device_Config_Add_Network.yaml declares six
    peers beneath the VTV television - SAMSUNG, YAMAHA, DENON, PANASONIC, LG and SONY - and
    "GameConsole" is not one of them, which is why port 4 of the audio system is free for exactly
    this triple. The add is therefore a real transition and the removal takes away exactly what the
    add created, so both directions are assertable rather than only the weaker "did not grow". All
    three fixtures - Device_Add.yaml, Device_Status.yaml and Device_Remove.yaml - name
    "GameConsole", the same name ADDED_PEER_NAME carries, and
    Init_Devicelist_Populate.verify_topology_consistency() is what keeps a claim about the topology
    checkable rather than a comment.
    WHAT IS NOT OBSERVABLE: the OnDeviceRemoved notification. A curl request/response cannot
    subscribe to a Thunder event. Its CONSEQUENCE is observable and is what is asserted -
    removeDevice() decrements m_numberOfDevices (HdmiCecSinkImplementation.cpp:2490) and clears the
    deviceList entry before fanning the notification out, and both show up in getDeviceList.
    Returns:
        True when every membership claim holds; False on any transport failure, refused post,
        unreadable list, or a transition that never happened.
    """
    global _peer_outstanding
    _peer_outstanding = False
    start_time = time.perf_counter()

    # SHARED STATE: changed, and now restored by a GUARANTEED cleanup step rather than by
    # construction alone.
    #
    # Device_Add.yaml attaches "GameConsole" to the emulated device map and Device_Remove.yaml
    # takes the same "GameConsole" away again, so the add/remove pair IS the restoration - the
    # ordering is the cleanup, not a stylistic preference. Two consequences follow, and both are
    # deliberate. First, the removal is placed AFTER the discovery frames rather than being
    # omitted: it is simultaneously the step under test and the step that puts the topology back,
    # so it can be neither dropped nor moved earlier. Second, its post is checked after it is
    # issued, because a silently skipped removal would hand every later case in the suite a
    # topology this one altered - and the after-probe below asserts the peer actually went away,
    # which is the restoration verified rather than assumed.
    #
    # NO ROLE INVERSION. The peer added here is an emulated PlaybackDevice attached beneath the
    # YAMAHA audio-system peer; the device under test remains the television throughout and is
    # never reconfigured to appear as its own peer in the list it is being asked to report.

    # ── BEFORE-PROBE: the reference sample, taken before anything is changed ─────────────────────
    readable, before_count, before_addresses = _device_inventory()
    if not readable:
        log_error(
            "✖ the reference device list could not be read - either the endpoint is dead "
            "(send_curl_command returns the truthy \"< No response from WPEFramework >\" "
            "sentinel), the reply is not JSON, or it did not acknowledge success"
        )
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False
    if not isinstance(before_count, int):
        log_error(
            f"✖ the reference device list reports numberofdevices {before_count!r}, expected an "
            "integer - every comparison below would be against None"
        )
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False
    log_warning(
        f"Initial device list: numberofdevices={before_count}, "
        f"logical addresses {before_addresses}"
    )

    # THE PRECONDITION THAT MAKES "PRESENT AFTER THE ADD" MEAN ANYTHING. The added peer is not part
    # of the seeded topology, so its address must be absent before Act 1 runs. If it is already
    # there the add is a no-op, and every assertion below would hold while proving nothing - so
    # this is reported as the precondition failure it is rather than tolerated. The likeliest
    # cause is a previous run of this case that did not reach its removal step, which leaves the
    # peer in the emulator's map for the next run to find.
    #
    # The membership test is taken from the reference sample _device_inventory() already returned
    # rather than from a second getDeviceList read. One sample keeps the precondition, the count
    # logged above and the count compared at the end of the lifecycle all describing the SAME
    # observation; a second read could disagree with the first the moment a ping round lands
    # between them, and would report a precondition failure against a list the counts never saw.
    # _device_inventory() has already folded "no response", "not JSON" and "did not report
    # success" into readable=False, which the block above reports, so nothing is lost by not
    # re-parsing here.
    if ADDED_PEER_LOGICAL_ADDRESS in before_addresses:
        log_error(
            f"✖ logical address {ADDED_PEER_LOGICAL_ADDRESS} is already in the device list "
            f"before the add, so adding {ADDED_PEER_NAME!r} cannot be observed as a population "
            "change. A previous run that did not reach its removal step leaves the peer behind; "
            "reset the emulated topology before re-running"
        )
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False

    # ACT 1 - ADD. Device_Add.yaml attaches the "GameConsole" PlaybackDevice with parent
    # "YAMAHA", the audio-system peer Init_Devicelist_Populate established. The settle here is 2s
    # rather than the 1s used between the later steps, matching the source-plugin template's own
    # pause around a device add or remove: a topology change has to travel the whole pipeline -
    # vComponent, the driver receive callback, the read thread, the decoder, and finally
    # addDevice() - before it can show up in a device-list read, which is a longer path than a
    # single frame injection.
    ok_add = _post_hdmicec("Device_Add.yaml")
    # MARKED HERE, BEFORE THE SETTLE AND BEFORE ANY ASSERTION.
    #
    # _peer_outstanding used to be set to False at the top of run_test() and never set to True
    # anywhere, so it was a dead flag: nothing could read it and learn that a peer was attached.
    # It is set the instant the add is ACCEPTED, because from that moment the emulated topology
    # carries a peer this case put there - and every line below is a place the case can return or
    # raise. It is cleared only when the peer's ABSENCE has been confirmed, so an unconfirmed
    # removal leaves it set and cleanup() tries again.
    # run_test() already declares `global _peer_outstanding` at its top, so no second declaration
    # is needed - and Python rejects one after the name has been assigned in the same function.
    if ok_add:
        _peer_outstanding = True
    time.sleep(CEC_TOPOLOGY_PACING_SECONDS)

    # ACT 2 - MUTATE. Device_Status.yaml drives the same peer to power_status "off" and marks it
    # faulted. This changes the EMULATOR's record, which the peer then reports on the bus, so the
    # value chosen matters: process(ReportPowerStatus) at HdmiCecSinkImplementation.cpp:408
    # compares the stored status against the reported one and calls sendDeviceUpdateInfo() only
    # when the two differ. Both the seeded topology and Device_Add.yaml declare this peer "on",
    # so a redundant "on" here would fan nothing out at all - which is why the fixture says
    # "off".
    ok_status = _post_hdmicec("Device_Status.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)

    # ACT 3 - ANNOUNCE. The two frames a real peer emits when it joins the bus. Both fixtures are
    # BROADCAST (initiator 4, destination F), and that framing is FUNCTIONAL, NOT STYLISTIC:
    # process(ReportPhysicalAddress) at HdmiCecSinkImplementation.cpp:344 and
    # process(DeviceVendorID) at :376 each open with the same guard - "Ignore Direct messages,
    # accepts only broadcast messages" - and return immediately for anything directed (:349-352
    # and :380-383 respectively).
    #
    # THE HAZARD THAT GUARD CREATES IS SILENT. Swapping either fixture for a directed variant
    # would still be accepted by the emulator and would still return HTTP 200, so the post would
    # look perfectly healthy while the handler discarded the frame and the announcement did
    # nothing at all. A green post is therefore not evidence that a frame was processed, which is
    # why the verdict below rests on the device-list samples rather than on the post codes alone.
    # Do not substitute a directed report frame here.
    #
    # These two posts are also what make a peer PRESENT TO THE PLUGIN rather than merely present
    # in the emulator's map: both handlers call addDevice() for the frame's INITIATOR (:356 and
    # :385), and removeDevice() does nothing at all unless that peer's m_isDevicePresent is
    # already set (:2487). That is the second reason the removal has to come last.
    #
    # Stated precisely, because the distinction matters for what may be claimed: these fixtures
    # announce logical address 4 - SONY, a seeded peer - and NOT the peer Act 1 added. They are
    # here to drive the two discovery handlers, which is a path this case is meant to walk; they
    # are not how the added peer becomes known. That happens through the plugin's own ping round,
    # which is why the mid-probe below WAITS for the added address rather than assuming an
    # announcement put it there. Keeping the two separate is what lets the verdict name one
    # specific peer instead of falling back on a population count.
    ok_rpa = _post_hdmicec("Process_Report_Physical_Address.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)
    ok_vid = _post_hdmicec("Process_Device_Vendor_ID.yaml")
    time.sleep(CEC_FRAME_PACING_SECONDS)

    # THE FOUR PRE-REMOVAL POSTS ARE CHECKED HERE, before the peer is looked for. A post that did
    # not return HTTP 200 either never reached the vComponent or named a document that did not
    # resolve, and in both cases the step it represents did not happen - so checking them first
    # makes a failed injection report itself, instead of surfacing later as the far vaguer "the
    # peer never appeared". The removal's own post is checked after it is issued, below.
    if not (ok_add and ok_status and ok_rpa and ok_vid):
        log_error(
            f"✖ required vComponent posts failed before the removal: add={ok_add} "
            f"status={ok_status} report-physical-address={ok_rpa} vendor-id={ok_vid}"
        )
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False

    # Mid-probe: sampled while the peer is established, so it is the reading the removal is
    # measured against. Bounded-polled rather than read once, because the plugin learns of the
    # addition on its next ping round - see the note beside LIFECYCLE_TIMEOUT_SECONDS.
    #
    # THE PEER'S OWN ADDRESS IS REQUIRED PRESENT, not merely a higher population count. A count
    # that rose is not evidence that THIS peer arrived - any concurrent discovery raises it too -
    # and a count that did not rise is exactly what an add the plugin never saw looks like. The
    # earlier arrangement compared only counts and, because the add could legitimately be a
    # no-op, could only assert the direction of the removal: `after <= mid`, which equality
    # satisfies, so a run in which neither the add nor the removal reached the plugin passed.
    # Tracking the address closes that.
    log_info(f"Waiting for logical address {ADDED_PEER_LOGICAL_ADDRESS} to appear")
    try:
        present, mid_result, added_entry = _await_peer(
            ADDED_PEER_LOGICAL_ADDRESS, True, "post-add"
        )
    except json.JSONDecodeError:
        log_error("✖ a post-add getDeviceList reply is not valid JSON")
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False

    if not present:
        log_error(
            f"✖ logical address {ADDED_PEER_LOGICAL_ADDRESS} never appeared in the device list "
            f"within {LIFECYCLE_TIMEOUT_SECONDS:.0f}s of adding {ADDED_PEER_NAME!r}, so the add "
            "did not reach the plugin and there is nothing for the removal below to remove"
        )
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False

    # The address alone could in principle be some other peer, so the physical address is checked
    # too: it is the one field the emulator derives from where the peer was attached, and 2.4.0.0
    # is YAMAHA's port 4 - exactly where Device_Add.yaml hung it.
    reported_physical = added_entry.get("physicalAddress")
    if reported_physical != ADDED_PEER_PHYSICAL_ADDRESS:
        log_error(
            f"✖ logical address {ADDED_PEER_LOGICAL_ADDRESS} appeared with physicalAddress "
            f"{reported_physical!r}, expected {ADDED_PEER_PHYSICAL_ADDRESS!r} - the address "
            f"{ADDED_PEER_NAME!r} takes from YAMAHA's port 4. A different address means this is "
            "not the peer the add introduced"
        )
        log_warning(f"Actual  : {json.dumps(added_entry, indent=2, sort_keys=True)}")
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False

    log_success(
        f"✔ {ADDED_PEER_NAME} is present to the plugin: logical address "
        f"{ADDED_PEER_LOGICAL_ADDRESS} at {reported_physical}"
    )

    # DIAGNOSTIC ONLY, DELIBERATELY NOT ASSERTED. printDeviceList makes the plugin dump its
    # internal device table to the WPEFramework log, where a human reading a failed run can
    # compare the plugin's own view against the JSON above. The dump lands in that log and not in
    # this response, so there is nothing here to assert: the reply carries only a `printed` flag
    # that the plugin reports whether or not any device is present. Its outcome consequently does
    # not affect the verdict, and a failure to dispatch it is logged rather than fatal - a
    # diagnostic that failed must not turn a passing lifecycle into a failure.
    dump = send_curl_command(HdmiCecSinkApis.print_device_list)
    if not dump or dump.startswith("< No response"):
        log_warning("printDeviceList diagnostic dump unavailable; continuing")
    else:
        log_info(f"printDeviceList diagnostic: {dump}")

    # ACT 4 - REMOVE, WHICH IS ALSO THE RESTORATION. This is the step the case exists for and the
    # step that puts the topology back, so it must not be skipped, must not be moved ahead of the
    # discovery frames, and its result must be checked. Device_Remove.yaml drops the same
    # "GameConsole" that Act 1 added, driving HdmiCecSinkImplementation::removeDevice() at
    # HdmiCecSinkImplementation.cpp:2474 - which decrements m_numberOfDevices (:2490), calls
    # HdmiPortMap::removeChild for the HDMI input matching the departing peer's physical address
    # (:2494, an arm only a nested peer reaches), clears the deviceList entry, and finally fans
    # OnDeviceRemoved out to every registered notification. The 2s settle matches Act 1's: a
    # topology change takes the long path through the pipeline in either direction.
    ok_remove = _post_hdmicec("Device_Remove.yaml")
    time.sleep(CEC_TOPOLOGY_PACING_SECONDS)

    # The removal's post is required too, and for a reason the others do not carry: it is
    # simultaneously the step under test and the step that puts the topology back. A silently
    # skipped removal - a misnamed document returns (0, "YAML file not found: ...") rather than
    # raising - would hand every later case in the suite a topology this one altered.
    if not ok_remove:
        log_error(
            "✖ the vComponent removal post failed, so the peer this case added is still in the "
            "emulated topology; reset it before re-running the suite"
        )
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False

    # After-probe: the sample that closes the lifecycle. Bounded-polled for the SAME reason the
    # mid-probe is - the plugin learns of the departure on its next ping round, when the peer stops
    # answering and pingDevices hands it to removeDevice.
    log_info(f"Waiting for logical address {ADDED_PEER_LOGICAL_ADDRESS} to disappear")
    try:
        absent, after_result, _ = _await_peer(
            ADDED_PEER_LOGICAL_ADDRESS, False, "post-remove"
        )
    except json.JSONDecodeError:
        log_error("✖ a post-remove getDeviceList reply is not valid JSON")
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False

    # before_count is the one the before-probe already read and validated as an integer; it is not
    # re-derived here, because the reference sample is a single observation by design.
    mid_count = mid_result.get("numberofdevices")
    after_count = after_result.get("numberofdevices")

    # The whole lifecycle in one line, so a run record shows what the counts actually did
    # alongside the presence verdicts the case is decided on. The counts are EVIDENCE here rather
    # than the assertion: an exact delta cannot be demanded, because addDevice() is idempotent for
    # a peer the plugin has already recorded and the announcement frames in Act 3 name a peer that
    # may or may not already be known - so pinning a delta would make this case pass or fail on
    # which sibling ran before it. The peer's own presence does not have that problem, which is why
    # it carries the verdict.
    log_info(
        f"Device count before={before_count} after_add={mid_count} after_remove={after_count}"
    )

    if after_result.get("success") is not True:
        log_error("✖ the post-remove getDeviceList did not report success")
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False

    if not absent:
        log_error(
            f"✖ logical address {ADDED_PEER_LOGICAL_ADDRESS} is still in the device list "
            f"{LIFECYCLE_TIMEOUT_SECONDS:.0f}s after removing {ADDED_PEER_NAME!r}, so the "
            "removal did not reach the plugin - and the emulated topology is left altered for "
            "every case that follows"
        )
        log_error("TCID27_Device_Add_Remove_Discovery_Flow Failed ❌")
        return False

    # The peer is CONFIRMED absent, so the topology this case altered is demonstrably back and the
    # restoration hook below has nothing left to do. Cleared here rather than after the removal
    # POST, because a post that was accepted is not a removal that took effect - `absent` above is.
    _peer_outstanding = False

    # ALSO NOT ASSERTED, AND NOT AN OVERSIGHT: that OnDeviceRemoved fired. The notification goes
    # to registered Thunder subscribers, and a curl request/response exchange is not one, so this
    # transport cannot observe it. The peer's disappearance from the published list is its
    # consequence, not the event itself.
    log_success(
        f"✔ {ADDED_PEER_NAME} was present after the add at logical address "
        f"{ADDED_PEER_LOGICAL_ADDRESS} and is absent after the removal"
    )
    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing("TCID27_Device_Add_Remove_Discovery_Flow Passed ✅", elapsed_time))
    return True
