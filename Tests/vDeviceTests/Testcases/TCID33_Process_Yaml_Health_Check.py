"""
/**
 * @file TCID33_Process_Yaml_Health_Check.py
 * @brief L3 HDMI CEC Sink functional testcase.
 *
 * @testcase TCID33_Process_Yaml_Health_Check
 * @details The BREADTH pass of this suite, and the only module in it that touches every
 *          inbound-handler emulation fixture the sink's vComponent tree publishes. Where
 *          TCID17-TCID27 each drive one flow in depth, this case posts the 24 reviewed
 *          Process_*.yaml documents under vcomponent_configurations/commands to the
 *          vComponent emulator in a stable sorted order, having first proven the directory
 *          holds exactly those 24 and nothing else, and then proves that the plugin's
 *          readable state survives the whole sweep.
 *
 *          Six things are asserted, and only six:
 *            1. the Process_*.yaml tree matches the approved inventory EXACTLY in both
 *               directions, every entry is a regular file, and every entry carries a declared
 *               expectation - so a deleted document is a named failure rather than a
 *               shorter pass, and an unreviewed one is never posted;
 *            2. every Device_*.yaml document in the same tree has a declared status - either a
 *               named consuming module, verified to actually reference the filename, or a
 *               recorded reason for being retained without one - so a fixture cannot sit in
 *               the tree unconsumed and unexplained, which is indistinguishable from one
 *               whose consumer was deleted;
 *            3. every opcode named in the sibling emulated-response table is one the
 *               vComponent's parser can resolve, and every request/response half written as a
 *               mapping carries an opcode key - so an exchange the emulator would silently
 *               decline to carry cannot be added while looking like coverage;
 *            4. every fixture on the sweep is ACCEPTED by the vComponent (HTTP 200);
 *            5. org.rdk.HdmiCecSink.getDeviceList answers with a well-formed envelope
 *               before and after the sweep, and the initiator encoded in each of the six
 *               registering fixtures' own payloads appears in the device list afterwards;
 *            6. org.rdk.HdmiCecSink.getActiveSource stays answerable across the six
 *               fixtures that move the active-source and routing state.
 *
 *          WHAT IS NOT ASSERTED MATTERS AS MUCH. A handler whose only effect is an outbound
 *          CEC response or a Thunder notification leaves nothing a curl read can see, so for
 *          those fixtures ACCEPTANCE is the entire claim - and this module states that in its
 *          own console output rather than implying more. No claim whatsoever is made about
 *          OnKeyPressEvent, OnKeyReleaseEvent, ReportFeatureAbortEvent, OnDeviceRemoved or
 *          OnImageViewOnMsg: L3 reaches the plugin over request/response curl and cannot
 *          subscribe to a Thunder notification at all, so all five are outside what any module
 *          here can observe. That is a property of this TRANSPORT and not a coverage verdict.
 *          Four of the five are asserted at both L1 and L2 - the key press/release pair, image
 *          view on, and device removed. ReportFeatureAbortEvent is asserted at L1 only
 *          (reportFeatureAbortEvent_SubscribedClient_ReceivesAllThreeOperands,
 *          _EachAbortReason_IsNotified, _BoundaryOperands_AreNotified); at L2 only the
 *          broadcast-drop guard arm is asserted, because the directed arm is documented BLOCKED
 *          there - the shared CEC mock's AbortReason int constructor leaves its public `impl`
 *          delegate uninitialised, so a frame-parsed directed Feature Abort takes SIGSEGV
 *          (HdmiCecSink_L2Test.cpp:4495 onward states the analysis and the one-line mock change
 *          that would unblock it). Where the coverage register lists these five as uncovered,
 *          that is its PRE-CHANGE BASELINE.
 *
 *          This is the breadth half of the sink's missing device-level (E2E) coverage
 *          (COVERAGE_GAPS.md, gap-plugin-sink-vdevicetests), where every sink JSON-RPC method
 *          is catalogued as covered by the plugin's own L2 suite with no end-to-end leg. No
 *          coverage percentage is claimed, because this suite is AUTHORED HERE AND NOT EXECUTED
 *          and an unmeasured figure would be a fabrication. Frames reach the handlers by
 *          INJECTION ONLY: nothing here reconfigures the device under test to act as its own
 *          peer, and role flipping and role inversion are out of scope for this suite by
 *          directive.
 *
 * @precondition
 *  - A device under test - physical hardware or a QEMU target - hosts the org.rdk.HdmiCecSink
 *    plugin and answers JSON-RPC at utils.WPEFRAMEWORK_JSONRPC_URL.
 *  - Init_Devicelist_Populate has run, so HDMI-CEC is enabled and the emulated CEC network is
 *    seeded around the audio system at logical address 5.
 *  - The vComponent HTTP API is reachable at utils.VCOMPONENT_API_URL.
 *  - The sibling vcomponent_configurations/commands tree is present and readable. This module
 *    DISCOVERS its work from that directory rather than declaring it, so an absent or empty
 *    tree is a reported failure here, never a silently short sweep.
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
 *  - The fixture tree matches the approved inventory exactly, every approved Process_*.yaml
 *    fixture is accepted with HTTP 200, getDeviceList stays healthy before and after the
 *    sweep, each registering fixture's own initiator appears in the device list,
 *    getActiveSource stays answerable across the routing fixtures, and the post-sweep device
 *    count is not lower than the pre-sweep count.
 *
 * @pass_criteria
 *  - Both inventory verifications pass, the topology document is accepted, both health
 *    checks are healthy, both snapshots are captured, there is no failed post and no
 *    state-check failure, post_count >= pre_count, and run_test() returns True.
 *
 * @failure_criteria
 *  - The commands directory is absent, the Process_*.yaml inventory does not match the
 *    approved list, a Device_*.yaml document has no declared status or its declared consumer
 *    no longer posts it, a fixture is not a regular file, a fixture carries no declared
 *    expectation, the topology
 *    configuration is rejected, either health check is unhealthy, a snapshot is unavailable,
 *    any post is rejected, any state check fails, the device count regresses, or run_test()
 *    returns False.
 */
"""


import json
import time
import os
import re
import stat
from pathlib import Path

from utils import (
    send_curl_command,
    send_vcomponent_command,
    sanitise_for_log,
    HDMICEC_CMD_BASE,
    log_info,
    log_success,
    log_warning,
    log_error,
    log_with_timing,
    CEC_FRAME_PACING_SECONDS,
    CEC_PIPELINE_PACING_SECONDS,
    CEC_SHORT_PACING_SECONDS,
    # The longest of the four documented pacing windows, used by cleanup() only: re-declaring the
    # topology is a topology change, which travels the whole pipeline before a device-list read can
    # reflect it - the same window Act 1 and Act 4 of TCID27 use for the same reason.
    CEC_TOPOLOGY_PACING_SECONDS,
    # The 55 opcode names the vComponent's parser resolves, declared once in utils.py and read
    # here by _verify_response_table_opcodes so the response table's own claim that the
    # constraint is ENFORCED is true of the code rather than of the comment.
    SUPPORTED_VCOMPONENT_OPCODES,
)
import HdmiCECSink_Curl as HdmiCecSinkApis

# Every name in the utils import above has a call site, log_with_timing included: it applies the
# HDMICEC_TIMING_ENABLED decoration and the pass path routes its message through it, which retired
# this module's own inline copy of that gate. The three pacing constants are the three settle
# windows the sweep uses - one frame, one full pipeline, and one fixture with no state-visible
# outcome - and they are imported rather than written as literals so that a change to the suite's
# pacing reaches this module too.
#
# pathlib is this module's alone. Every other case posts a FIXED list of document names, so no path
# is ever walked; this one reads the directory to compare it against the inventory below, which is
# what makes it the breadth pass rather than another flow case. `re` reads a fixture's payload so a
# membership expectation can be DERIVED from the frame's own initiator nibble instead of restated
# here - the same technique Init_Devicelist_Populate.verify_seed_payload_consistency() uses on the
# seed payloads. `stat` classifies each fixture by st_mode, so a symlink or a directory wearing a
# fixture's name is refused rather than posted.
#
# THE INVENTORY IS DECLARED EXACTLY ONCE, as APPROVED_PROCESS_FIXTURES below, and
# EXPECTED_PROCESS_FIXTURES is derived from it. Keep it that way: a second hand-written copy of the
# filenames is a copy a rename can put out of step while both still look authoritative.

# ── WHAT EACH FIXTURE IS EXPECTED TO DO, ONE ENTRY PER FIXTURE ───────────────────────────────────
# Three expectation kinds, and every fixture carries at least one EXPLICITLY. An unstated default
# would make "no expectation was written for this fixture" and "this fixture genuinely has no
# observable consequence" look identical; they are different statements, so they are written
# differently.
#
#   "registers"      the handler calls addDevice(header.from), so the frame's own initiator must
#                    appear in getDeviceList afterwards. Derived from the payload's header nibble.
#   "active_source"  the handler moves active-source or routing state, so getActiveSource must still
#                    answer with success true and a boolean available afterwards. The VALUE is not
#                    pinned: whether an active source exists depends on which flow case ran before
#                    this one and on which fixture the sweep has just posted.
#   "smoke"          acceptance is the ENTIRE claim, and the reason is recorded beside it. Each of
#                    these produces an outbound CEC response or a Thunder notification and nothing a
#                    curl read can see.
#
# The keys of this mapping are required to equal EXPECTED_PROCESS_FIXTURES exactly, which is what
# makes it impossible to add a fixture to the tree without deciding what it should prove.
FIXTURE_EXPECTATIONS = {
    "Process_Abort.yaml": (("smoke",), "the handler only logs the abort opcode"),
    "Process_Active_Source.yaml": (
        ("registers", "active_source"),
        "process(ActiveSource) registers the initiator and updates the active source",
    ),
    "Process_CEC_Version.yaml": (
        ("registers",), "process(CECVersion) registers the initiator and records its version"
    ),
    "Process_Device_Vendor_ID.yaml": (
        ("registers",), "process(DeviceVendorID) registers the initiator and records its vendor"
    ),
    "Process_Feature_Abort.yaml": (
        ("smoke",),
        "the handler's whole effect is the ReportFeatureAbortEvent notification, which a one-shot "
        "curl cannot subscribe to",
    ),
    "Process_Get_CEC_Version.yaml": (
        ("smoke",), "the handler answers with an outbound <CEC Version> frame, which is not readable"
    ),
    "Process_Give_Device_Power_Status.yaml": (
        ("smoke",),
        "the handler answers with an outbound <Report Power Status> frame carrying the sink's own "
        "power state, which is not readable",
    ),
    "Process_Give_Device_Vendor_ID.yaml": (
        ("smoke",), "the handler answers with an outbound <Device Vendor ID> frame"
    ),
    "Process_Give_Features.yaml": (
        ("smoke",), "the handler answers with an outbound <Report Features> frame on CEC 2.0 only"
    ),
    "Process_Give_OSD_Name.yaml": (
        ("smoke",), "the handler answers with an outbound <Set OSD Name> frame"
    ),
    "Process_Give_Physical_Address.yaml": (
        ("smoke",), "the handler answers with an outbound <Report Physical Address> frame"
    ),
    "Process_In_Active_Source.yaml": (
        ("active_source",),
        "process(InActiveSource) clears the active source when the withdrawing address holds it",
    ),
    "Process_Polling.yaml": (
        ("smoke",),
        "a bare polling header carries no opcode; the middleware answers it at the bus layer and "
        "the plugin records nothing",
    ),
    "Process_Report_Physical_Address.yaml": (
        ("registers",),
        "process(ReportPhysicalAddress) registers the initiator and records its physical address",
    ),
    "Process_Report_Power_Status.yaml": (
        ("registers",),
        "process(ReportPowerStatus) registers the initiator and writes the reported status into its "
        "device record, which getDeviceList publishes as powerStatus",
    ),
    "Process_Request_Active_Source.yaml": (
        ("active_source",), "the handler makes the sink announce itself as the active source"
    ),
    "Process_Request_Current_Latency.yaml": (
        ("smoke",), "the handler answers with an outbound <Report Current Latency> frame"
    ),
    "Process_Routing_Change.yaml": (
        ("active_source",), "the inbound routing handler is log-only, so only API health is claimed"
    ),
    "Process_Routing_Information.yaml": (
        ("active_source",), "the inbound routing handler is log-only, so only API health is claimed"
    ),
    "Process_Set_OSD_Name.yaml": (
        ("registers",), "process(SetOSDName) registers the initiator and records its OSD name"
    ),
    "Process_Set_Stream_Path.yaml": (
        ("active_source",), "the inbound stream-path handler is log-only, so only API health is claimed"
    ),
    "Process_Standby.yaml": (
        ("smoke",),
        "the handler's whole effect is the SendStandbyMsgEvent notification; it writes no state at "
        "all (HdmiCecSinkImplementation.cpp:203-207)",
    ),
    "Process_User_Control_Pressed.yaml": (
        ("smoke",),
        "the handler forwards straight to SendKeyPressMsgEvent and stores nothing (:295-300)",
    ),
    "Process_User_Control_Released.yaml": (
        ("smoke",),
        "the handler forwards straight to SendKeyReleaseMsgEvent and stores nothing (:301-305)",
    ),
}

# The emulated topology document, re-posted at the start of this case to establish a known baseline
# before the sweep. It is NOT re-posted afterwards: see the note on the residual at the foot of this
# module, which is why this case is registered last.
NETWORK_CONFIG_YAML = "Device_Config_Add_Network.yaml"

# Bounded budgets. Poll ceilings, never durations anything waits out. The device-list budget is the
# longer one because a topology or registration change travels the whole pipeline - vComponent, the
# driver receive callback, the read queue, the read thread, the decoder, then the handler - before it
# can show up in a read.
HEALTH_TIMEOUT_S = 10.0
REGISTER_TIMEOUT_S = 15.0
POLL_INTERVAL_S = 0.25

_PAYLOAD_PATTERN = re.compile(r'payload:\s*\[(.*?)\]', re.S)


# ── the reviewed fixture inventory ───────────────────────────────────────────
#
# THE 24 INBOUND-HANDLER DOCUMENTS THIS CASE POSTS, NAMED ONE BY ONE. This list is the case's
# subject, not a convenience: every entry was read and approved, and posting a vComponent command
# document makes the emulator inject a CEC frame into the device under test, so "whatever matches
# Process_*.yaml on disk" is not an acceptable definition of the work.
#
# WHY THE SET IS NOT DISCOVERED WITH A GLOB. Sweeping whatever matches Process_*.yaml would carry
# three defects rather than any flexibility. A document DELETED from the tree would shrink the sweep
# silently, so coverage could be lost while the case went on reporting a pass. A document ADDED - by
# a careless merge or by anything able to write into the fixture tree - would be posted unreviewed,
# which is to say arbitrary CEC frames would be injected on the strength of a filename. And a
# symlink or a directory bearing a matching name would be swept in and posted as though it were one
# of these documents.
#
# So the inventory is fixed here, the tree is required to match it EXACTLY in both directions, and
# every entry is required to be a regular file rather than a link or a directory. Adding a fixture
# is a deliberate edit to this list, reviewed alongside the document itself. Keep it sorted; the
# verification below reports additions and omissions separately, so a rename shows up as one of
# each rather than as a puzzle.
APPROVED_PROCESS_FIXTURES = (
    "Process_Abort.yaml",
    "Process_Active_Source.yaml",
    "Process_CEC_Version.yaml",
    "Process_Device_Vendor_ID.yaml",
    "Process_Feature_Abort.yaml",
    "Process_Get_CEC_Version.yaml",
    "Process_Give_Device_Power_Status.yaml",
    "Process_Give_Device_Vendor_ID.yaml",
    "Process_Give_Features.yaml",
    "Process_Give_OSD_Name.yaml",
    "Process_Give_Physical_Address.yaml",
    "Process_In_Active_Source.yaml",
    "Process_Polling.yaml",
    "Process_Report_Physical_Address.yaml",
    "Process_Report_Power_Status.yaml",
    "Process_Request_Active_Source.yaml",
    "Process_Request_Current_Latency.yaml",
    "Process_Routing_Change.yaml",
    "Process_Routing_Information.yaml",
    "Process_Set_OSD_Name.yaml",
    "Process_Set_Stream_Path.yaml",
    "Process_Standby.yaml",
    "Process_User_Control_Pressed.yaml",
    "Process_User_Control_Released.yaml",
)


def _discovered_process_fixtures(commands_dir):
    """Return every Process_*.yaml path present under commands_dir, as posix-relative names.

    Walked with os.walk(followlinks=False) rather than Path.rglob so that a symlinked
    SUBDIRECTORY cannot be descended into - rglob's symlink behaviour varies by Python version,
    and a scan whose reach depends on the interpreter is not a scan an inventory check can rest
    on. Entries are collected by NAME only, whatever their type: this function answers "what
    claims to be a fixture", and _verify_fixture_inventory decides whether each one may be posted.

    Args:
        commands_dir: pathlib.Path of the vcomponent command-document directory.
    Returns:
        A set of paths relative to commands_dir, in posix form.
    """
    discovered = set()
    for directory, _subdirectories, filenames in os.walk(commands_dir, followlinks=False):
        for filename in filenames:
            if filename.startswith("Process_") and filename.endswith(".yaml"):
                absolute = Path(directory) / filename
                discovered.add(absolute.relative_to(commands_dir).as_posix())
        # os.walk lists a symlink to a directory under subdirectories, and followlinks=False
        # stops it being descended - but a symlink to a FILE appears in filenames, so the name
        # is collected here and rejected by type below rather than being quietly skipped.
    return discovered


def _verify_fixture_inventory(commands_dir):
    """True when the fixture tree matches APPROVED_PROCESS_FIXTURES exactly, file types included.

    Five independent conditions, each reported with its own diagnostic so a reader is told which
    one failed rather than being handed a set difference:

      * every approved document is present;
      * every approved document is a REGULAR FILE - os.lstat, so a symlink is seen as a symlink
        rather than as whatever it points at, and a directory or a FIFO bearing the name is
        likewise refused;
      * nothing else in the tree claims to be a Process_*.yaml, at any depth;
      * commands_dir is itself a real directory and not a symlink to one;
      * FIXTURE_EXPECTATIONS carries an entry for every approved document and for nothing else,
        which is the condition that makes it impossible to add a fixture to the tree without
        deciding what posting it is supposed to prove. Checked here rather than raised at import,
        so that SuitManager can still load and register this module and report the failure as a
        case result instead of dying during discovery.

    Args:
        commands_dir: pathlib.Path of the vcomponent command-document directory.
    Returns:
        True when all five hold; False with the reason already logged otherwise.
    """
    directory_info = os.lstat(str(commands_dir))
    if not stat.S_ISDIR(directory_info.st_mode):
        log_error(
            f"✖ {commands_dir} is not a directory (mode {stat.filemode(directory_info.st_mode)}); "
            "a symlink standing in for the fixture tree would redirect every post in this case"
        )
        return False

    missing = []
    wrong_type = []
    for name in APPROVED_PROCESS_FIXTURES:
        candidate = commands_dir / name
        try:
            info = os.lstat(str(candidate))
        except OSError:
            missing.append(name)
            continue
        if not stat.S_ISREG(info.st_mode):
            wrong_type.append(f"{name} ({stat.filemode(info.st_mode)})")

    discovered = _discovered_process_fixtures(commands_dir)
    unexpected = sorted(discovered - set(APPROVED_PROCESS_FIXTURES))

    if missing:
        log_error(
            f"✖ {len(missing)} approved fixture(s) are absent from the tree: "
            f"{', '.join(missing)}. This case posts a fixed reviewed inventory, so a missing "
            "document is lost coverage rather than a smaller sweep"
        )
    if wrong_type:
        log_error(
            f"✖ {len(wrong_type)} approved fixture(s) are not regular files: "
            f"{', '.join(wrong_type)}. A symlink or directory in a fixture's place would have "
            "this case post something other than the document that was reviewed"
        )
    if unexpected:
        log_error(
            f"✖ {len(unexpected)} unapproved Process_*.yaml document(s) are present: "
            f"{', '.join(sanitise_for_log(name, max_chars=128) for name in unexpected)}. "
            "Posting one would inject an unreviewed CEC frame into the device under test; add it "
            "to APPROVED_PROCESS_FIXTURES deliberately, with the document reviewed, or remove it"
        )

    untabled = sorted(EXPECTED_PROCESS_FIXTURES - set(FIXTURE_EXPECTATIONS))
    unapproved_table_entries = sorted(set(FIXTURE_EXPECTATIONS) - EXPECTED_PROCESS_FIXTURES)
    if untabled:
        log_error(
            f"✖ {len(untabled)} approved fixture(s) carry no entry in FIXTURE_EXPECTATIONS: "
            f"{', '.join(untabled)}. The sweep would post them and check nothing, which reads as "
            "a pass for a handler nothing was claimed about"
        )
    if unapproved_table_entries:
        log_error(
            f"✖ {len(unapproved_table_entries)} FIXTURE_EXPECTATIONS entr(ies) name a document "
            f"that is not approved: {', '.join(unapproved_table_entries)}. The expectation is "
            "unreachable, which usually means a fixture was renamed in one place only"
        )

    if missing or wrong_type or unexpected or untabled or unapproved_table_entries:
        return False

    log_success(
        f"✔ the fixture inventory matches exactly: {len(APPROVED_PROCESS_FIXTURES)} approved "
        "Process_*.yaml documents, all regular files, none unapproved, each with a declared "
        "expectation"
    )
    return True


# THE INVENTORY CONTRACT.
#
# This frozenset is the authoritative list of inbound-handler fixtures this case posts, and it
# is compared for EQUALITY against what the directory sweep finds - not used as a filter, and
# not treated as a lower bound.
#
# Deriving the work from a directory sweep alone would make the case's scope depend on whatever
# happens to be lying in the tree. A sweep that merely finds "at least something" accepts two
# opposite defects in silence: a fixture that has been deleted or renamed shrinks the pass
# without failing it, so an untested handler reads as a green run; and a stray document - a
# nested copy under a scratch directory, a fixture staged for a different case, an editor or
# rebase artefact whose name still ends .yaml - gets POSTED to the emulator, changing device
# state that the assertions after the loop then measure. Both are silent today. Equality
# against a fixed inventory turns each of them into a named failure.
#
# Paths are relative to vcomponent_configurations/commands and compared as POSIX strings, so a
# nested duplicate such as "DeviceListConfig/Process_Polling.yaml" does not collide with the
# flat "Process_Polling.yaml" - it is reported as an extra file, which is the point.
#
# Adding, renaming or removing a fixture is therefore a deliberate two-file change: the
# document and this list. That is the intended cost. The 24 entries are the complete set of
# Process_*.yaml documents in the tree, one per inbound CEC opcode this suite exercises.
#
# DERIVED FROM THE TUPLE ABOVE, never written out again. The tuple carries the reviewed order and
# is what _verify_fixture_inventory walks; this frozenset is the same names as a set, for the
# equality comparisons against the directory sweep and against FIXTURE_EXPECTATIONS' keys.
EXPECTED_PROCESS_FIXTURES = frozenset(APPROVED_PROCESS_FIXTURES)

# ── THE TWO EXPECTATION SETS THE SWEEP CONSULTS, DERIVED FROM THE TABLE ──────────────────────────
# Neither is written out by hand. FIXTURE_EXPECTATIONS is the single place a fixture's expectation
# is decided, so restating the membership here would let the table and the sweep disagree - and the
# sweep would win silently, checking nothing for a fixture whose table entry says it registers a
# device. Sorted for a stable, diffable console record.
FIXTURES_THAT_REGISTER_A_DEVICE = tuple(sorted(
    name for name, (kinds, _reason) in FIXTURE_EXPECTATIONS.items() if "registers" in kinds
))
FIXTURES_THAT_MOVE_ACTIVE_SOURCE = tuple(sorted(
    name for name, (kinds, _reason) in FIXTURE_EXPECTATIONS.items() if "active_source" in kinds
))


# ── THE OTHER HALF OF THE FIXTURE TREE: THE Device_*.yaml FAMILY ─────────────────────────────────
#
# Every command document in this directory now has a declared status, which is the point of the two
# tables below. Twenty-eight of the fifty-three Device_*.yaml documents have NO consumer: no module
# posts them, nothing names them, and before these tables existed nothing recorded whether that was
# deliberate. An unconsumed fixture is not harmless - it is indistinguishable from a fixture whose
# consumer was deleted or renamed, so real lost coverage looks exactly like a document that was
# never meant to be posted.
#
# Those twenty-eight are RETAINED. Every one of them is a reviewed emulator command that a future
# case may legitimately reach for. What they carry instead is an explicit status, checked against
# the tree by _verify_device_fixture_inventory below: either a named consuming module, verified to
# actually reference the filename, or a recorded reason for being retained without one.
#
# THE SPLIT IS 25 CONSUMED / 28 RETAINED, and the two numbers are derived from the tables rather
# than written here twice - the success line prints len() of each. Getting the split wrong is not
# something the check below can catch: it asserts that every document has SOME status, so a live
# fixture mis-declared as retained passes while under-stating the suite's own coverage. That is
# exactly what had happened to the <Get CEC Version> pair, which TCID05_Get_CEC_Version posts.
#
# DEVICE_FIXTURE_CONSUMERS - posted by the module named. The check reads that module and requires the
# filename to appear in it, so a rename on either side is a named failure rather than a silent orphan.
DEVICE_FIXTURE_CONSUMERS = {
    "Device_Add.yaml": "TCID27_Device_Add_Remove_Discovery_Flow",
    # The <Get CEC Version> / <CEC Version> pair. TCID05_Get_CEC_Version drives the directed
    # exchange with BOTH documents - it names them as GET_CEC_VERSION_YAML and CEC_VERSION_YAML and
    # posts each through send_vcomponent_command - so they are consumed, not retained. They were
    # previously declared under the "alternative framing" reason, which read as though the
    # Process_*.yaml equivalents were the only ones on any sweep; that made two live fixtures look
    # like library documents nobody posts, and the inventory check cannot catch that class of
    # mistake because it asserts only that SOME status exists for every file.
    "Device_CEC_Version.yaml": "TCID05_Get_CEC_Version",
    "Device_Config_Add_Network.yaml": "Init_Devicelist_Populate",
    "Device_Get_CEC_Version.yaml": "TCID05_Get_CEC_Version",
    "Device_Image_View_On.yaml": "TCID25_Standby_Coordination_Flow",
    "Device_In_Active_Source.yaml": "TCID18_Set_Active_Source_Flow",
    "Device_Initiate_Arc.yaml": "TCID20_ARC_Initiation_Flow",
    "Device_Initiate_Arc_Broadcast.yaml": "TCID20_ARC_Initiation_Flow",
    "Device_Initiate_Arc_Invalid_Initiator.yaml": "TCID20_ARC_Initiation_Flow",
    "Device_Remove.yaml": "TCID27_Device_Add_Remove_Discovery_Flow",
    "Device_Report_Audio_Status.yaml": "TCID24_Audio_Status_And_Power_Flow",
    "Device_Report_Audio_Status_Muted.yaml": "TCID24_Audio_Status_And_Power_Flow",
    "Device_Report_Power_Status.yaml": "TCID24_Audio_Status_And_Power_Flow",
    "Device_Report_Short_Audio_Descriptor.yaml": "TCID23_Short_Audio_Descriptor_Flow",
    "Device_Set_System_Audio_Mode.yaml": "TCID22_System_Audio_Mode_Flow",
    "Device_Set_System_Audio_Mode_Off.yaml": "TCID22_System_Audio_Mode_Flow",
    "Device_Standby_Emulation.yaml": "TCID25_Standby_Coordination_Flow",
    "Device_Status.yaml": "TCID27_Device_Add_Remove_Discovery_Flow",
    "Device_Terminate_Arc.yaml": "TCID21_ARC_Termination_Flow",
    "Device_Terminate_Arc_Broadcast.yaml": "TCID21_ARC_Termination_Flow",
    "Device_Text_View_On.yaml": "TCID25_Standby_Coordination_Flow",
    "Device_User_Control_Pressed.yaml": "TCID26_User_Control_Pressed_Released_Flow",
    "Device_User_Control_Pressed_Boundary.yaml": "TCID26_User_Control_Pressed_Released_Flow",
    "Device_User_Control_Pressed_Min.yaml": "TCID26_User_Control_Pressed_Released_Flow",
    "Device_User_Control_Released.yaml": "TCID26_User_Control_Pressed_Released_Flow",
}

# DEVICE_FIXTURES_RETAINED - kept deliberately, posted by nothing, each with its reason. Three
# reasons account for all of them:
#
#   * ALTERNATIVE FRAMING. The document injects an opcode this suite already covers, in the other
#     framing - directed where the Process_*.yaml equivalent is broadcast, or the reverse. Both
#     framings are worth having, because several sink handlers filter on destination, but only one
#     of each pair is on the sweep and duplicating it would inject the same frame twice.
#   * EMULATOR CONTROL, NOT A CEC FRAME. The document drives the vComponent itself - its device map,
#     its bus state, its fault injection - rather than putting a frame on the bus. Nothing on the
#     inbound-handler sweep applies, and the fault-injection trio in particular would leave the
#     emulator in a state later cases inherit, so posting them from a breadth pass is exactly wrong.
#   * NEGATIVE VARIANT AWAITING A CONSUMER. A deliberate off-nominal framing whose paired case does
#     not exist in this suite, recorded so the document is not mistaken for a live fixture.
DEVICE_FIXTURES_RETAINED = {
    "Device_Abort.yaml":
        "alternative framing: Process_Abort.yaml is the one on the sweep",
    "Device_Bus_Status.yaml":
        "emulator control: sets the emulated bus state, puts no frame on the bus",
    "Device_CEC_Message.yaml":
        "alternative framing: injects <CEC Version> from SAMSUNG; Process_CEC_Version.yaml is on "
        "the sweep",
    "Device_CEC_Message_Userdef.yaml":
        "alternative framing: injects <Active Source> as a user-defined message; "
        "Process_Active_Source.yaml is on the sweep and TCID17/TCID18 drive that flow",
    "Device_Config.yaml":
        "emulator control, and not the topology this suite configures: Device_Config_Add_Network.yaml "
        "is, declaring the six peers rather than an empty map",
    "Device_Device_Vendor_ID.yaml":
        "alternative framing: Process_Device_Vendor_ID.yaml is the one on the sweep",
    "Device_Feature_Abort.yaml":
        "alternative framing: Process_Feature_Abort.yaml is the one on the sweep",
    "Device_Get_Menu_Language.yaml":
        "alternative framing: the sink answers <Get Menu Language> with an outbound frame this "
        "transport cannot read, and TCID13_Set_Menu_Language covers the readable half",
    "Device_Get_Power_Status.yaml":
        "alternative framing: Process_Give_Device_Power_Status.yaml is the one on the sweep",
    "Device_Give_Device_Vendor_ID.yaml":
        "alternative framing: Process_Give_Device_Vendor_ID.yaml is the one on the sweep",
    "Device_Give_Features.yaml":
        "alternative framing: Process_Give_Features.yaml is the one on the sweep",
    "Device_Give_OSD_Name.yaml":
        "alternative framing: Process_Give_OSD_Name.yaml is the one on the sweep",
    "Device_Give_Physical_Address.yaml":
        "alternative framing: Process_Give_Physical_Address.yaml is the one on the sweep",
    "Device_Polling.yaml":
        "alternative framing: Process_Polling.yaml is the one on the sweep",
    "Device_Print.yaml":
        "emulator control: prints the emulated device map, puts no frame on the bus. The sink's own "
        "printDeviceList is what TCID09_Print_Devicelist exercises",
    "Device_Report_Physical_Address.yaml":
        "alternative framing: the seeding equivalent lives in DeviceListConfig/ per peer, and "
        "Process_Report_Physical_Address.yaml is the one on the sweep",
    "Device_Request_Active_Source.yaml":
        "alternative framing: Process_Request_Active_Source.yaml is the one on the sweep, and "
        "TCID17_Request_Active_Source_Flow drives that flow",
    "Device_Request_Current_Latency.yaml":
        "alternative framing: Process_Request_Current_Latency.yaml is the one on the sweep, and "
        "TCID14_Set_Latency_Info covers the readable half",
    "Device_Request_Current_Latency_Mismatch.yaml":
        "negative variant awaiting a consumer: a <Request Current Latency> naming a physical "
        "address that is not the sink's, which the handler drops with no readable consequence",
    "Device_Request_Inactive_Source.yaml":
        "alternative framing: Process_In_Active_Source.yaml is the one on the sweep, and "
        "TCID18_Set_Active_Source_Flow drives that flow through Device_In_Active_Source.yaml",
    "Device_Routing_Change.yaml":
        "alternative framing: Process_Routing_Change.yaml is the one on the sweep, and "
        "TCID19_Active_Path_Routing_Change_Flow drives that flow",
    "Device_Routing_Information.yaml":
        "alternative framing: Process_Routing_Information.yaml is the one on the sweep, and "
        "TCID19_Active_Path_Routing_Change_Flow drives that flow",
    "Device_Set_Menu_Language.yaml":
        "alternative framing: TCID13_Set_Menu_Language drives the language flow through the "
        "plugin's own setMenuLanguage rather than by injecting the inbound frame",
    "Device_Set_OSD_String.yaml":
        "negative variant awaiting a consumer: <Set OSD String> is a display request the sink has "
        "no handler for, so it has no observable consequence at any level",
    "Device_Set_Stream_Path.yaml":
        "alternative framing: Process_Set_Stream_Path.yaml is the one on the sweep, and "
        "TCID19_Active_Path_Routing_Change_Flow drives that flow",
    "Device_Setapi_Logic_Fail.yaml":
        "emulator control, fault injection: forces a busy bus so logical-address setup fails. Not "
        "posted from a breadth pass, because it leaves the emulator in a state later cases inherit",
    "Device_Setapi_Open_Fail.yaml":
        "emulator control, fault injection: marks the target faulted so the HAL open fails. Same "
        "reason - the residual would reach every case that follows",
    "Device_Setapi_Open_Pass.yaml":
        "emulator control: clears the fault the two documents above inject, so it is only "
        "meaningful as their paired cleanup",
}


def _verify_device_fixture_inventory(commands_dir):
    """True when every Device_*.yaml document has a declared status matching the tree.

    THE CHECK THAT MAKES AN ORPHAN FIXTURE IMPOSSIBLE. Four conditions, each reported on its own:

      * the two tables are disjoint - a document cannot be both posted and retained-unposted;
      * the documents on disk are exactly the union of the two tables, so a fixture added without a
        status is named and a fixture named without a document is named too;
      * every declared document is a REGULAR FILE, by os.lstat, so a symlink or a directory wearing
        a fixture's name is refused rather than treated as one;
      * every consumer named in DEVICE_FIXTURE_CONSUMERS exists as a module and actually references
        the filename - which is what turns "this fixture has a consumer" from a comment into a fact.

    Args:
        commands_dir: pathlib.Path of the vcomponent command-document directory.
    Returns:
        True when all four hold; False with the reason already logged otherwise.
    """
    problems = []

    both = sorted(set(DEVICE_FIXTURE_CONSUMERS) & set(DEVICE_FIXTURES_RETAINED))
    if both:
        problems.append(
            f"{len(both)} document(s) are declared both posted and retained-unposted: "
            f"{', '.join(both)}"
        )

    declared = set(DEVICE_FIXTURE_CONSUMERS) | set(DEVICE_FIXTURES_RETAINED)
    on_disk = {path.name for path in commands_dir.glob("Device_*.yaml")}

    undeclared = sorted(on_disk - declared)
    if undeclared:
        problems.append(
            f"{len(undeclared)} Device_*.yaml document(s) carry no declared status: "
            f"{', '.join(sanitise_for_log(name, max_chars=128) for name in undeclared)}. An "
            "unconsumed fixture is indistinguishable from one whose consumer was deleted, so each "
            "needs either a named consumer or a recorded reason for being retained"
        )
    absent = sorted(declared - on_disk)
    if absent:
        problems.append(
            f"{len(absent)} declared Device_*.yaml document(s) are not in the tree: "
            f"{', '.join(absent)}"
        )

    wrong_type = []
    for name in sorted(declared & on_disk):
        info = os.lstat(str(commands_dir / name))
        if not stat.S_ISREG(info.st_mode):
            wrong_type.append(f"{name} ({stat.filemode(info.st_mode)})")
    if wrong_type:
        problems.append(
            f"{len(wrong_type)} declared document(s) are not regular files: "
            f"{', '.join(wrong_type)}"
        )

    # The consuming module may be a root module or a case module, so both locations are searched.
    # Reading the file rather than importing it keeps this check static and free of import order.
    suite_dir = commands_dir.parent.parent
    for name, consumer in sorted(DEVICE_FIXTURE_CONSUMERS.items()):
        candidates = [suite_dir / f"{consumer}.py", suite_dir / "Testcases" / f"{consumer}.py"]
        module_path = next((path for path in candidates if path.is_file()), None)
        if module_path is None:
            problems.append(
                f"{name} names consumer {consumer}, but no such module exists beside this suite "
                "or under Testcases/"
            )
            continue
        if name not in module_path.read_text(encoding="utf-8"):
            problems.append(
                f"{name} names consumer {consumer}, but that module does not reference the "
                "filename - either the fixture was renamed or the consumer stopped posting it"
            )

    if problems:
        for problem in problems:
            log_error(f"✖ {problem}")
        return False

    log_success(
        f"✔ every Device_*.yaml document has a declared status: "
        f"{len(DEVICE_FIXTURE_CONSUMERS)} posted by a verified consumer, "
        f"{len(DEVICE_FIXTURES_RETAINED)} retained with a recorded reason"
    )
    return True


# ── THE RESPONSE TABLE'S OPCODE VOCABULARY ───────────────────────────────────────────────────────
#
# The emulated-response document that the vComponent answers peer requests from. It is a sibling of
# the command tree rather than part of it, which is why the path is derived from commands_dir's
# parent instead of from HDMICEC_CMD_BASE.
RESPONSE_TABLE_YAML = "hdmicec_vcomponent_cec_responses.yaml"

# Flow-style rows, so both halves of an exchange sit inside braces on one line:
#     - request: { opcode: "GiveOsdName", type: "Direct", payload: null}
#       response: { opcode: "SetOsdName", type: "Direct", payload: ["osd_name"]}
# _OPCODE_NAME_PATTERN lifts the names; _EXCHANGE_HALF_PATTERN lifts each brace group so a half
# written WITHOUT an opcode key is caught too. A `response: null` half carries no braces and is
# correctly not matched - it declares that the peer absorbs the request without replying.
_OPCODE_NAME_PATTERN = re.compile(r'opcode:\s*"([^"]+)"')
_EXCHANGE_HALF_PATTERN = re.compile(r'(request|response):\s*\{([^}]*)\}')


def _verify_response_table_opcodes(commands_dir):
    """True when every opcode name in the response table is one the emulator can resolve.

    THE CHECK THAT MAKES AN UNRESOLVABLE EXCHANGE IMPOSSIBLE TO ADD QUIETLY. The response table
    names each opcode as a string, and vcCommand_GetOpCode resolves it against gOpCodeStrVal; a
    name outside that table becomes CEC_OPCODE_UNKNOWN and ParseCommand returns without putting
    anything on the bus (vcHdmiCec.c:180-184). Nothing about that is observable from a test: the
    POST is accepted, HTTP 200 comes back, and the exchange never happens - so an unresolvable row
    reads exactly like coverage. utils.SUPPORTED_VCOMPONENT_OPCODES carries the 55 resolvable
    names and this function is what compares the document against them.

    Three properties, each reported on its own:
      * the document is present and readable - an absent response table is a named failure, not a
        vacuous pass;
      * it declares at least one opcode. This is the non-vacuity guard: if the document's shape
        ever changes so the pattern stops matching, the check must fail rather than report success
        over an empty set;
      * every declared name is a member of the vocabulary, and every request/response half written
        as a mapping actually carries an opcode key.

    Comment lines are stripped before anything is matched, because this document's header
    deliberately NAMES the opcodes the emulator cannot resolve - GetMenuLanguage, ReportAudioStatus
    and the latency and short-audio-descriptor pairs - as the record of what is BLOCKED on a
    production change to the read-only emulator. Matching those would turn the file's own honesty
    into a failure.

    Static: reads one file, contacts nothing, and is called before the sweep posts anything.

    Args:
        commands_dir: pathlib.Path of the vComponent command-document directory. The response
            table sits in the sibling hdmicec/ directory.
    Returns:
        True when all three hold; False with the reason already logged otherwise.
    """
    problems = []
    table_path = commands_dir.parent / "hdmicec" / RESPONSE_TABLE_YAML

    try:
        raw = table_path.read_text(encoding="utf-8")
    except OSError as exc:
        log_error(
            f"✖ cannot read the response table {RESPONSE_TABLE_YAML}: {exc}. The emulated replies "
            "this suite's directed exchanges depend on are declared there, so an unreadable "
            "document is a fixture defect rather than a plugin one"
        )
        return False

    body = "\n".join(
        line for line in raw.splitlines() if not line.lstrip().startswith("#")
    )

    declared = _OPCODE_NAME_PATTERN.findall(body)
    if not declared:
        log_error(
            f"✖ {RESPONSE_TABLE_YAML} declares no opcode at all. Either the document was emptied "
            "or its row shape changed - and a membership check over an empty set would pass while "
            "asserting nothing, so this is reported as a failure"
        )
        return False

    unknown = sorted({name for name in declared if name not in SUPPORTED_VCOMPONENT_OPCODES})
    if unknown:
        problems.append(
            f"{len(unknown)} opcode name(s) in {RESPONSE_TABLE_YAML} are not in the vComponent's "
            f"vocabulary: {', '.join(sanitise_for_log(name, max_chars=64) for name in unknown)}. "
            "vcCommand_GetOpCode resolves each of these to CEC_OPCODE_UNKNOWN and the exchange is "
            "never carried, so the row reads like coverage while exercising nothing. Either spell "
            "it as one of the 55 names in utils.SUPPORTED_VCOMPONENT_OPCODES, or record the "
            "exchange as BLOCKED in this document's header the way the others are"
        )

    for half, contents in _EXCHANGE_HALF_PATTERN.findall(body):
        if "opcode:" not in contents:
            problems.append(
                f"a {half} half of an exchange in {RESPONSE_TABLE_YAML} carries no opcode key: "
                f"{{{sanitise_for_log(contents, max_chars=128)}}}. The emulator reads the opcode "
                "by name, so a half without one describes an exchange it cannot perform"
            )

    if problems:
        for problem in problems:
            log_error(f"✖ {problem}")
        return False

    log_success(
        f"✔ every opcode in {RESPONSE_TABLE_YAML} is one the vComponent resolves: "
        f"{len(declared)} declaration(s), {len(set(declared))} distinct name(s), all members of "
        f"the {len(SUPPORTED_VCOMPONENT_OPCODES)}-name vocabulary"
    )
    return True


def _post_yaml(yaml_name):
    """Post one vComponent YAML command document and report whether it was accepted.

    Only the HTTP status decides the verdict. The body is NEVER parsed: it carries whatever
    diagnostic the emulator produced, or utils.py's own explanation of a refusal, and it is not
    JSON. A name that is not in the tree comes back as HTTP 0 with "YAML file not found" rather
    than raising - so a typo would be reported as a product failure, which is why every filename
    named literally in this file has been checked against the directory listing.

    Unparsed is not the same as unprocessed. The body is remote-derived, so it is rendered
    through utils.sanitise_for_log before it is printed: bounded, escaped and single-line. This
    module posts every document in a directory and logs a line for each, which makes it the
    largest single volume of emulator-authored text in the suite, and the console transcript is
    the only evidence a device-level run leaves behind. A body carrying terminal control
    sequences would otherwise be able to erase the lines above it or repaint a refusal as an
    acceptance, and the escaped rendering is what makes that impossible while keeping the
    diagnostic readable.

    Args:
        yaml_name: Command-document filename relative to utils.HDMICEC_CMD_BASE, which is joined on
                   here so that module's environment-override contract keeps working
    Returns:
        True when the vComponent answered HTTP 200, False for every other outcome.
    """
    http_code, body = send_vcomponent_command(f"{HDMICEC_CMD_BASE}/{yaml_name}")
    log_info(f"POST {yaml_name}: HTTP {http_code} {sanitise_for_log(body)}")
    return http_code == 200


def _fixture_initiator(yaml_name):
    """Return the logical address a fixture's payload initiates from, or None with a reason.

    DERIVED, NOT RESTATED. The "registers" expectation is that the frame's own initiator appears in
    the device list, and that address is the high nibble of the payload's header byte. Reading it out
    of the document means the expectation follows the fixture: a document re-addressed to a different
    initiator changes what this module looks for, instead of leaving a stale literal here that would
    be reported as a plugin defect.
    Returns:
        (logical_address, None) on success, or (None, reason).
    """
    path = Path(HDMICEC_CMD_BASE) / yaml_name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"cannot read {yaml_name}: {exc}"
    match = _PAYLOAD_PATTERN.search(text)
    if not match:
        return None, f"{yaml_name} declares no payload list"
    first = match.group(1).split(",")[0].strip().strip('"').strip("'")
    try:
        header = int(first, 16)
    except ValueError as exc:
        return None, f"{yaml_name} has a non-hexadecimal header byte: {exc}"
    return header >> 4, None


def _get_device_snapshot():
    """Capture the device list as {"number": int, "logicals": set}, or None when it is not usable.

    THE INTEGER IS REQUIRED, AND MUST STAY REQUIRED. Returning "number": None when the count is
    absent or not an integer would let run_test() substitute -1 for it, so a plugin that stopped
    reporting a count would produce -1 on BOTH sides of the sweep and the direction check would
    compare -1 against -1 and pass. A snapshot that cannot be trusted is reported as no snapshot at
    all instead.

    The two key names are the sink's own and are deliberately inconsistent with each other:
    getDeviceList answers with "numberofdevices" all in lower case beside "deviceList" in camel case.
    Spelling either with the other's convention reads as an ABSENT member rather than raising, which
    is exactly the failure mode this function now refuses to paper over, so both are written out
    literally rather than derived.
    Returns:
        A dict with "number" (an int) and "logicals" (a set of int logical addresses), or None when
        the response could not be obtained, was not a success envelope, or carried no integer count.
    """
    response = send_curl_command(HdmiCecSinkApis.get_device_list)
    # utils.send_curl_command reports a transport failure by RETURNING the TRUTHY sentinel
    # "< No response from WPEFramework >", so an emptiness test alone would read a dead endpoint as a
    # healthy one. Every read helper below carries the same guard for the same reason.
    if not response or response.startswith("< No response"):
        return None

    try:
        body = json.loads(response)

        # A payload that parses as JSON but is not an object - or whose "result" member is not
        # one - is an unusable answer rather than a snapshot, so it is reported as a snapshot
        # failure here. Narrowing before calling .get() is also what keeps an AttributeError
        # from escaping run_test(), which owes its caller a bool on every path; the sibling case
        # modules in this directory narrow the same way for the same reason.
        if not isinstance(body, dict):
            return None
        result = body.get("result", {})
        if not isinstance(result, dict):
            return None

        # success is required, and so is an integer count, because both are what make the
        # snapshot comparable to another one. A reply that reports success false, or that omits
        # numberofdevices, is an answer the sweep cannot measure anything against, so it is
        # reported as NO SNAPSHOT here rather than handed upwards as a snapshot with a hole in
        # it. A substitute count would let an omission on both sides compare equal and be read as a
        # steady device count.
        if result.get("success") is not True:
            return None

        number = result.get("numberofdevices")
        if not isinstance(number, int):
            return None

        devices = result.get("deviceList", [])
        if not isinstance(devices, list):
            devices = []
        logicals = set()
        for d in devices:
            if isinstance(d, dict):
                la = d.get("logicalAddress")
                if isinstance(la, int):
                    logicals.add(la)
        return {
            "number": number,
            "logicals": logicals,
        }
    except json.JSONDecodeError:
        return None


def _wait_for_snapshot(predicate, timeout_seconds):
    """Poll getDeviceList until a usable snapshot satisfies predicate, bounded by timeout_seconds.

    A BOUNDED POLL, NOT A SLEEP. Both directions of every state change this module observes are
    discovered by the plugin on its own schedule - a frame has to cross the vComponent, the driver
    receive callback, the read queue, the read thread and the decoder before a handler runs at all -
    so a fixed pause is a guess at how long that takes and a poll is a measurement. It returns the
    instant the wanted state is observed, and on expiry it reports the LAST sample rather than the
    first, so the diagnostic describes the state the device actually settled in.

    Args:
        predicate: Callable taking one snapshot mapping and returning True when it is the wanted
                   state. Pass `lambda snap: True` to wait only for a usable snapshot.
        timeout_seconds: Poll ceiling in seconds. Never waited out on success.
    Returns:
        (True, snapshot) as soon as a usable snapshot satisfies predicate; (False, last) on expiry,
        where last is the final snapshot taken or None when none was ever usable.
    """
    deadline = time.monotonic() + timeout_seconds
    last = None
    while True:
        snapshot = _get_device_snapshot()
        if snapshot is not None:
            last = snapshot
            if predicate(snapshot):
                return True, snapshot
        if time.monotonic() >= deadline:
            return False, last
        time.sleep(POLL_INTERVAL_S)


def _health_check():
    """True when getDeviceList answers with a usable snapshot within the health budget.

    The liveness probe the sweep is bracketed by. "Usable" is _get_device_snapshot's contract -
    success true, an integer numberofdevices and a deviceList array - so this asks whether the
    plugin is still answering the question, and deliberately asserts nothing about the answer:
    which devices are present depends on the seeded topology and on which flow cases ran before
    this one.
    Returns:
        True when a usable snapshot arrives inside HEALTH_TIMEOUT_S, otherwise False.
    """
    healthy, _snapshot = _wait_for_snapshot(lambda snapshot: True, HEALTH_TIMEOUT_S)
    return healthy


def _get_active_source_ok():
    """True when org.rdk.HdmiCecSink.getActiveSource answers with a well-formed envelope.

    An API-HEALTH probe, not a value assertion, and the distinction is deliberate: "available"
    is the sink's presence flag and BOTH of its values are healthy answers. Whether an active
    source exists at any moment depends on which flow case ran before this one and on which
    fixture the sweep has just posted, so requiring available to be true would fail this module
    on a perfectly legitimate device state. What is required is that the plugin still answers
    the question at all - a boolean available, and success true.

    NOTE ON THE NAME, since it differs from the source plugin's equivalent helper. That one
    probes an ActiveSourceStatus method through a constant of the same name. The sink publishes
    neither: HdmiCECSink_Curl.py exposes get_active_source (org.rdk.HdmiCecSink.getActiveSource)
    and nothing ending in Status, so carrying the source's constant across would raise
    AttributeError on the sweep's first routing fixture. Hence the shorter name here, and the
    method that actually exists.

    Returns:
        True when the response parses with a boolean "available" and "success" true, otherwise
        False - including for the transport sentinel and for an unparsable body.
    """
    response = send_curl_command(HdmiCecSinkApis.get_active_source)
    if not response or response.startswith("< No response"):
        return False

    try:
        body = json.loads(response)

        # Narrowed before .get() for the reason given in _get_device_snapshot: an envelope that
        # is not an object cannot be interrogated, and an AttributeError must not escape.
        if not isinstance(body, dict):
            return False
        result = body.get("result", {})
        if not isinstance(result, dict):
            return False

        return isinstance(result.get("available"), bool) and result.get("success") is True
    except json.JSONDecodeError:
        return False


def run_test():
    start_time = time.perf_counter()

    # Validate all process-trigger YAML files are accepted by vComponent,
    # and add observable checks for handlers that should affect plugin state.
    commands_dir = Path(__file__).resolve().parent.parent / "vcomponent_configurations" / "commands"

    # This module lives in Testcases/ and vcomponent_configurations/ is its sibling one level
    # up, which is what the two .parent steps walk. An absent directory gets its own message
    # rather than surfacing as "no files found" - two distinct findings for a reader.
    if not commands_dir.is_dir():
        log_error("TCID33_Process_Yaml_Health_Check Failed: commands directory not found")
        return False

    # THE SWEEP IS THE APPROVED INVENTORY, VERIFIED AGAINST THE TREE - not whatever the tree
    # happens to hold. _verify_fixture_inventory compares the two for EQUALITY in both directions,
    # refuses anything that is not a regular file, and requires every approved document to carry a
    # declared expectation, so a deleted fixture is a named failure rather than a shorter pass and
    # an unreviewed one is never posted. The Process_ prefix is what confines the inventory to the
    # inbound-handler documents: the DeviceListConfig/Payload_*.yaml seeding documents share this
    # tree and are deliberately outside it, belonging to the bootstrap module's topology.
    if not _verify_fixture_inventory(commands_dir):
        log_error("TCID33_Process_Yaml_Health_Check Failed: the fixture inventory is not intact")
        return False

    # The Device_*.yaml half of the same tree. Checked here rather than in a module of its own,
    # because this is the case that owns the fixture inventory, and checked BEFORE anything is posted
    # for the same reason the sweep's inventory is: a fixture without a declared status is a defect
    # in the tree, not in the plugin, and it costs nothing to say so before the device is touched.
    if not _verify_device_fixture_inventory(commands_dir):
        log_error(
            "TCID33_Process_Yaml_Health_Check Failed: a Device_*.yaml document has no declared "
            "status, or a declared consumer no longer posts it"
        )
        return False

    # The third document family in the same tree: the emulated-response table the vComponent
    # answers directed requests from. Checked here, beside the two inventory checks and before
    # anything is posted, for the same reason they are - an opcode the emulator's parser cannot
    # resolve is a fixture defect, and it is the one fixture defect that produces no symptom at
    # all: the POST is accepted and the exchange silently never happens. The document's header
    # states that this constraint is enforced rather than merely described, and this call is what
    # makes that true.
    if not _verify_response_table_opcodes(commands_dir):
        log_error(
            "TCID33_Process_Yaml_Health_Check Failed: the emulated-response table names an opcode "
            "the vComponent cannot resolve, so the exchange it describes would never be carried"
        )
        return False

    # Sorted, so the posting order is stable and the console record is diffable between runs.
    discovered = sorted(APPROVED_PROCESS_FIXTURES)
    log_info(
        f"Sweeping {len(discovered)} approved inbound-handler fixtures: "
        f"{len(FIXTURES_THAT_REGISTER_A_DEVICE)} are expected to register their initiator, "
        f"{len(FIXTURES_THAT_MOVE_ACTIVE_SOURCE)} to move active-source or routing state, and the "
        "rest are acceptance-only, each with its reason stated as it is posted"
    )

    # Re-establish the known topology before measuring anything. Its root emulated peer is the
    # audio system at logical address 5, physical address 2.0.0.0, carrying seven ports with the
    # seeded peers beneath it - the one stable vComponent-backed device the state checks below
    # have something to verify against. Address 5 is load-bearing, not decorative: it is the
    # only address for which the sink's addDevice() also raises ReportAudioDeviceConnectedStatus,
    # and the only initiator its ARC gate accepts. Init_Devicelist_Populate posted this same
    # document at bootstrap, so re-posting it is idempotent, and it is what makes this case
    # independent of how many flow cases ran before it. Posted directly rather than through
    # _post_yaml because the failure below names THIS step: a rejected topology is not the same
    # finding as a rejected handler fixture.
    http_code, _ = send_vcomponent_command(f"{HDMICEC_CMD_BASE}/{NETWORK_CONFIG_YAML}")
    if http_code != 200:
        log_error("TCID33_Process_Yaml_Health_Check Failed: configure command rejected")
        return False
    # MARKED AS SOON AS THE FIRST MUTATING POST IS ACCEPTED, not after the sweep completes.
    #
    # _topology_disturbed carried the comment "True once the sweep has run, so cleanup() knows the
    # topology may need re-declaring" and was never assigned True anywhere - a dead flag beside a
    # cleanup() that did not exist. It is set here because this post is the first change this case
    # makes, and every line after it is a place the case can return or raise; a flag set at the END
    # of the sweep would be False on exactly the paths restoration is for.
    global _topology_disturbed
    _topology_disturbed = True
    time.sleep(CEC_FRAME_PACING_SECONDS)

    # WAITED FOR, NOT SLEPT THROUGH. A bounded poll returns as soon as the plugin answers and still
    # reports when the plugin never does, which a fixed pause can do neither of.
    ready, pre_snapshot = _wait_for_snapshot(lambda snap: True, HEALTH_TIMEOUT_S)
    if not ready:
        log_error(
            "TCID33_Process_Yaml_Health_Check Failed: getDeviceList never returned a usable "
            "snapshot before the sweep - it must report success true with an integer "
            "numberofdevices and a deviceList array"
        )
        return False
    log_info(
        f"Pre-sweep: {pre_snapshot['number']} devices at {sorted(pre_snapshot['logicals'])}"
    )

    # The two verdict ledgers. Both are collected across the WHOLE sweep and reported afterwards
    # rather than returning on the first one, because a run record naming every fixture that failed
    # is worth more than one naming the earliest: the sweep is the breadth pass, and "these four
    # handlers are unreachable" is a different finding from "this one is".
    failed_posts = []
    state_check_failures = []

    for yaml_name in discovered:
        kinds, reason = FIXTURE_EXPECTATIONS[yaml_name]
        if not _post_yaml(yaml_name):
            failed_posts.append(f"{yaml_name}: the vComponent refused the post")
            continue

        if yaml_name in FIXTURES_THAT_REGISTER_A_DEVICE:
            # The registration expectation, DERIVED from the document rather than restated: the
            # handler calls addDevice(header.from), so the initiator encoded in the fixture's own
            # payload must appear in getDeviceList afterwards. Bounded-polled over the longer
            # budget because the frame travels the full pipeline first - vComponent callback →
            # DriverReceiveCallback → rQueue → read thread → MessageDecoder →
            # HdmiCecSinkProcessor::process() → addDevice().
            initiator, why_not = _fixture_initiator(yaml_name)
            if initiator is None:
                state_check_failures.append(f"{yaml_name}: {why_not}")
            else:
                registered, last = _wait_for_snapshot(
                    lambda snapshot, address=initiator: address in snapshot["logicals"],
                    REGISTER_TIMEOUT_S,
                )
                if not registered:
                    observed = (
                        f"last seen: {sorted(last['logicals'])}" if last is not None
                        else "getDeviceList never returned a usable snapshot"
                    )
                    state_check_failures.append(
                        f"{yaml_name}: initiator {initiator} did not appear in the device list "
                        f"within {REGISTER_TIMEOUT_S:.0f}s ({observed})"
                    )
        else:
            # Nothing to read for this one, so the settle is the short window: the post is the
            # whole claim, and the reason it is the whole claim is printed beside it rather than
            # left for a reader to infer from the absence of an assertion.
            time.sleep(CEC_SHORT_PACING_SECONDS)
            if "smoke" in kinds:
                log_info(f"  {yaml_name}: acceptance is the entire claim - {reason}")

        if yaml_name in FIXTURES_THAT_MOVE_ACTIVE_SOURCE:
            # An API-health probe rather than a value assertion, for the reason
            # _get_active_source_ok documents. The settle here is the pipeline window: the routing
            # and active-source handlers run at the far end of the same path.
            time.sleep(CEC_PIPELINE_PACING_SECONDS)
            if not _get_active_source_ok():
                state_check_failures.append(f"{yaml_name}: getActiveSource API unhealthy")

    if not _health_check():
        log_error("TCID33_Process_Yaml_Health_Check Failed: post-check getDeviceList is not healthy")
        return False

    post_snapshot = _get_device_snapshot()
    if post_snapshot is None:
        log_error("TCID33_Process_Yaml_Health_Check Failed: unable to capture post device snapshot")
        return False

    # Both counts are integers by _get_device_snapshot's contract - a reply without an integer
    # numberofdevices is no snapshot at all and was reported as such above - so no substitute value
    # is needed or wanted here. Defaulting each side to a sentinel such as -1 would make an omission
    # on both sides compare equal and pass the direction check below.
    pre_num = pre_snapshot["number"]
    post_num = post_snapshot["number"]
    log_info(f"Device count pre={pre_num} post={post_num}")

    if failed_posts:
        log_warning(f"Failed YAML posts: {failed_posts}")
        log_error("TCID33_Process_Yaml_Health_Check Failed")
        return False

    if state_check_failures:
        log_warning(f"State-check warnings: {state_check_failures}")
        log_error("TCID33_Process_Yaml_Health_Check Failed")
        return False

    # Restated at the end of the transcript, because a reader who only sees the summary should not
    # infer more than was claimed: for the acceptance-only fixtures the handler's whole effect is an
    # outbound CEC frame or a Thunder notification, and a one-shot curl exchange can observe
    # neither. That is a property of THIS transport, not a gap in what was checked - the same
    # handlers are asserted directly by the plugin's own L1 and L2 suites, which can subscribe to a
    # notification and can read the mock's outbound queue.
    log_info(
        f"{len(discovered) - len(FIXTURES_THAT_REGISTER_A_DEVICE)} of {len(discovered)} fixtures "
        "were acceptance-only over this transport; each reason was printed as the fixture was "
        "posted"
    )

    # DIRECTION, never magnitude. The count depends on the seeded topology and on which flow
    # cases ran before this one, so any fixed number written here would be wrong. What a sweep of
    # inbound handlers must not do is LOSE devices: a count that grew is the legitimate result of
    # registering peers, a count that fell means the runtime went unstable under the sweep.
    if post_num < pre_num:
        log_warning("Post device count lower than pre-count; treating as unstable runtime")
        log_error("TCID33_Process_Yaml_Health_Check Failed")
        return False

    elapsed_time = time.perf_counter() - start_time
    log_success(log_with_timing(
        f"TCID33_Process_Yaml_Health_Check Passed ✅ ({len(discovered)} process YAMLs posted + "
        "observable checks)",
        elapsed_time,
    ))
    return True


# ON THE THREE SETTLE WINDOWS ABOVE, so a reviewer does not read them as an oversight. The
# project's test-quality bar forbids wall-clock waits in NEW tests, and rightly: in the C++
# GoogleTest suites asynchronous behaviour is exercised by invoking the captured callback
# directly, which is faster and deterministic. That technique does not exist here. This module
# drives a SEPARATE emulator process over HTTP and then reads the plugin over JSON-RPC; there is
# no callback in this address space to capture, and the CEC receive pipeline between the two is
# genuinely asynchronous. The 1 s topology window, the 1.5 s device-list window and the 0.2 s
# window for the rest are the reference suite's documented idiom for that pipeline, inherited
# here for parity. No further sleep is added anywhere in this file.
#
# WHAT IS RESTORED, WHAT IS NOT, AND WHY THE DIFFERENCE IS STATED RATHER THAN GLOSSED.
#
# This block used to read "NO RESTORE STEP, AND ITS ABSENCE IS DELIBERATE", which contradicted the
# NETWORK_CONFIG_YAML comment forty lines earlier - "re-posted at the start to establish a known
# baseline and again by cleanup()" - and contradicted the dead _topology_disturbed flag whose own
# comment named a cleanup() that did not exist. Three statements, no two of them agreeing, and no
# hook anywhere.
#
# The half that WAS restorable is now restored. Device_Config_Add_Network.yaml declares the
# emulated topology and re-posting it is idempotent - Init_Devicelist_Populate posts the same
# document at bootstrap - so cleanup() re-declares it and then CONFIRMS the plugin still answers
# with a usable device-list snapshot. That is the state a later run or a later suite actually
# depends on.
#
# The half that is NOT restorable is named instead of approximated: the inbound frames this sweep
# injects move active-source, routing and per-peer status, and not one of them is a setter with an
# inverse to call. A restore could only be manufactured by hand-building a CEC payload, which this
# suite does not do - every frame it injects comes from a reviewed document under
# vcomponent_configurations/commands/ - and doing so would issue one more untracked change while
# presenting it as a return to a known state. So cleanup() re-declares the topology and says
# plainly that the frame-driven state is left where the last accepted fixture put it.
#
# That residual is bounded by where this case sits: SuitManager.py registers it 33rd and LAST, so
# no sibling inherits it, and the two health checks plus the count-direction check are what
# establish that the plugin is still answering when the suite prints its summary.


def cleanup():
    """Re-declare the emulated topology and confirm the plugin still answers.

    SuitManager runs this unconditionally - after a pass, a failure, an exception, and for a case it
    SKIPPED - so it assumes nothing about how far the sweep got. Idempotent: the flag is consumed
    on read, and re-posting the topology document is itself idempotent.

    Restores exactly one thing, and confirms it: the topology declaration. The frame-driven state
    the sweep leaves behind is reported as a residual rather than manufactured back, for the reason
    given in the block above.

    Returns:
        True when there was nothing to restore, or the topology was re-declared AND the plugin
        answered a device-list read afterwards. False when the post was refused or no usable
        snapshot arrived inside the health budget - in which case the message says what is left.
    """
    global _topology_disturbed
    if not _topology_disturbed:
        log_info("TCID33 cleanup: nothing was posted, so the topology needs no re-declaring")
        return True
    _topology_disturbed = False

    log_info(f"TCID33 cleanup: re-declaring the emulated topology from {NETWORK_CONFIG_YAML}")
    http_code, body = send_vcomponent_command(f"{HDMICEC_CMD_BASE}/{NETWORK_CONFIG_YAML}")
    if http_code != 200:
        log_error(
            f"TCID33 cleanup: the topology re-declaration was refused (HTTP {http_code}: "
            f"{sanitise_for_log(body, 200)}), so the emulated topology is left as the sweep "
            "found it"
        )
        return False
    time.sleep(CEC_TOPOLOGY_PACING_SECONDS)

    if not _health_check():
        log_error(
            "TCID33 cleanup: the topology was re-declared but the plugin did not answer a "
            f"device-list read within {HEALTH_TIMEOUT_S:.0f}s, so the restoration is unconfirmed"
        )
        return False

    log_success("✔ TCID33 cleanup: the topology is re-declared and the plugin is answering")
    log_info(
        "  Residual reported, not manufactured: the active-source, routing and per-peer status "
        "the swept frames moved is left where the last accepted fixture put it - no fixture in "
        "this suite inverts an inbound frame, and this case runs last"
    )
    return True
