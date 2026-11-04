"""
/**
 * @file SuitManager.py
 * @brief SuitManager.py
 *
 * @testcase SuitManager
 * @details Orchestrates the HDMI CEC Sink L3/device-level test suite by dynamically loading
 *          and executing test case modules, activating the required RDK plugin via JSON-RPC,
 *          and reporting per-test pass/fail results with summary statistics. The suite is
 *          authored here and its runtime execution is deferred to a device or emulator
 *          environment; nothing in this repository runs it.
 *
 *          This module is the command-line entry point of the suite. It is intentionally
 *          named SuitManager.py to match the HDMI CEC Source suite's on-disk entry point
 *          exactly, so the two device-level suites stay symmetric; the spelling is the
 *          established repository convention and must not be "corrected".
 *
 *          The suite is authored for execution on a device or a vComponent emulator. This
 *          module never starts, emulates or stubs any of the services it talks to: it only
 *          dispatches requests to whatever endpoint utils.py resolves, and every request
 *          that does not reach a live target is reported as a failure.
 *
 * @precondition
 *  - WPEFramework is running and reachable at the configured JSON-RPC endpoint.
 *  - The org.rdk.HdmiCecSink plugin is available for activation.
 *  - All test case modules listed in SUITES are present under the Testcases/ directory.
 *
 * @dependencies
 *  - utils.py - the only module this one imports: endpoint resolution, the JSON-RPC dispatcher,
 *    the readiness waiter and the logging helpers
 *  - Init_Devicelist_Populate.py - loaded by name through SUITE_INIT_MODULES and run once before
 *    the first case; a False return aborts the suite
 *  - Testcases/TCID*.py - the 33 registered case modules, imported by name from the tests list
 *  - HdmiCECSink_Curl.py is a dependency of those cases rather than of this module, which builds
 *    no request of its own beyond the controller calls it composes through utils.py
 *
 * @expected_result
 *  - All registered test cases are executed in order, every declared producer/consumer
 *    dependency is honoured, every cleanup() hook runs, and results are logged.
 *
 * @pass_criteria
 *  - Each test case module's run_test() returns True and is reported as PASSED, and every
 *    cleanup() hook completes.
 *
 * @failure_criteria
 *  - Any test case returns False, raises an exception, or is skipped because a producer it
 *    depends on did not pass; any cleanup() hook fails; the plugin fails to activate or does
 *    not become ready within its budget; or suite initialization does not complete.
 */
"""

import importlib
import io
import sys
import time
from pathlib import Path
import os

# utils.await_plugin_ready is deliberately NOT imported here. It observes the controller state
# alone, and this runner needs both that state and the plugin's own declared readiness_probe to
# hold - see wait_for_plugin_ready below, which observes exactly those two things and is what
# run_suite calls. Importing the weaker helper alongside the stronger one only invites the wrong
# one to be reached for.
from utils import (
    log_error,
    sanitise_for_log,
    log_info,
    log_success,
    log_warning,
    send_jsonrpc_command,
    WPEFRAMEWORK_JSONRPC_URL,
)


# Directory holding this module. Every path the suite needs is derived from it, so the suite
# runs correctly from any working directory - `cd Tests/vDeviceTests && python3 SuitManager.py
# hdmicecsink` and `python3 entservices-hdmicecsink/Tests/vDeviceTests/SuitManager.py
# hdmicecsink` resolve Testcases/ and the init module identically. resolve() collapses symlinks
# and relative segments so the value inserted into sys.path is always absolute.
BASE_DIR = Path(__file__).resolve().parent

# The suite registry. Test case modules are registered EXPLICITLY, one quoted name per line, in
# the order they must execute - there is no filesystem globbing and no discovery library. That
# is deliberate: the declared order is part of the contract (see the ordering notes inside the
# list) and an explicit list makes an accidentally orphaned or accidentally renamed test case a
# visible import error rather than a silently skipped case.
SUITES = {
    "hdmicecsink": {
        # Same banner shape and same total width (82 characters) as the HDMI CEC Source suite's
        # banner, so the two suites' output lines up. "SINK" is two characters shorter than
        # "SOURCE", hence two extra trailing asterisks here - the asymmetry in the asterisk runs
        # is what keeps the banners symmetric.
        #
        # The LEVEL LABEL deliberately does not match the source suite's. This suite lives under
        # Tests/vDeviceTests/, which is the L3 device-level location, and every test case in it
        # is documented as L3; the source suite's banner still reads "L2" because that is its own
        # pre-existing upstream wording and relabelling it is outside this suite's remit. "L2"
        # and "L3" are the same width, so the 82-character alignment above is unaffected.
        "banner": "******************** L3 SUITE - RDK - HDMI CEC SINK ******************************",
        "module_dir": BASE_DIR / "Testcases",
        # ORDER IS LOAD-BEARING, NOT COSMETIC. The cases share one device, so an earlier case's
        # effect is a later case's precondition:
        #   * 01-09 are the early observation block. Eight of the nine are read-only queries and
        #     run first so the device is observed before it is written to. 05
        #     (Get_CEC_Version) is the one exception and is called out here rather than left to
        #     be discovered: it injects a directed <Get CEC Version> and a directed
        #     <CEC Version> onto the emulated bus and then reads the recorded version back out of
        #     getDeviceList, because the plugin publishes no getCecVersion method and the bus is
        #     the only place that surface is observable. What it writes is idempotent and
        #     identical to what Init_Devicelist_Populate.py already seeded - the same peer,
        #     opcode and operand, recorded by the same handler - so it leaves 06 through 09
        #     exactly the device they would otherwise have seen, and its position inside this
        #     block is free rather than constrained;
        #   * 10-16 are the single-API writes, and 11 (Set_Vendor_ID) must precede 12
        #     (Verify_Vendor_ID_Readback) because 12 reads back exactly what 11 wrote;
        #   * 17-27 are the multi-message flows, and 20 (ARC_Initiation_Flow) must precede 21
        #     (ARC_Termination_Flow) because there is nothing to terminate until ARC has been
        #     initiated;
        #   * 28-33 are the negative, idempotency and health cases, and 30
        #     (Repeated_Disable_Idempotent) must precede 31 (Repeated_Enable_Idempotent) so the
        #     pair leaves the CEC enabled flag restored to its enabled state.
        # Reordering, adding or removing an entry changes the suite's semantics. This list is
        # also the authoritative ordered inventory of the suite's test cases: anything that needs
        # to enumerate them reads it here rather than globbing the Testcases directory.
        "tests": [
            "TCID01_Get_Enabled_Status",
            "TCID02_Get_Devicelist",
            "TCID03_Get_OSD_Name",
            "TCID04_Get_Vendor_ID",
            "TCID05_Get_CEC_Version",
            "TCID06_Get_Active_Source",
            "TCID07_Get_Active_Route",
            "TCID08_Get_Audio_Device_Connected_Status",
            "TCID09_Print_Devicelist",
            "TCID10_Set_OSD_Name",
            "TCID11_Set_Vendor_ID",
            "TCID12_Verify_Vendor_ID_Readback",
            "TCID13_Set_Menu_Language",
            "TCID14_Set_Latency_Info",
            "TCID15_Send_Standby_Message",
            "TCID16_Send_Key_Press_Event",
            "TCID17_Request_Active_Source_Flow",
            "TCID18_Set_Active_Source_Flow",
            "TCID19_Active_Path_Routing_Change_Flow",
            "TCID20_ARC_Initiation_Flow",
            "TCID21_ARC_Termination_Flow",
            "TCID22_System_Audio_Mode_Flow",
            "TCID23_Short_Audio_Descriptor_Flow",
            "TCID24_Audio_Status_And_Power_Flow",
            "TCID25_Standby_Coordination_Flow",
            "TCID26_User_Control_Pressed_Released_Flow",
            "TCID27_Device_Add_Remove_Discovery_Flow",
            "TCID28_Invalid_VendorID_Nochange",
            "TCID29_Invalid_OSD_Setnochange",
            "TCID30_Repeated_Disable_Idempotent",
            "TCID31_Repeated_Enable_Idempotent",
            "TCID32_Invalid_ARC_Routing_Nochange",
            "TCID33_Process_Yaml_Health_Check",
        ],
        # The two JSON-RPC observables this runner polls INSTEAD OF SLEEPING. Both are cheap,
        # read-only plugin methods, and both are declared here rather than hard coded inside the
        # runner so the runner itself stays suite agnostic.
        #   * readiness_probe answers only once the plugin is activated AND dispatching its own
        #     methods, which is what "the plugin has finished initialising" actually means as an
        #     observable. Polling it replaces a fixed post-activation sleep.
        #   * settle_probe reports the one piece of plugin state that inbound CEC traffic
        #     changes - the discovered device count - so consecutive identical readings are
        #     evidence that the bus has gone quiet. Polling it replaces a fixed inter-case sleep.
        # result_key names the member of the JSON-RPC result that must be present for the answer
        # to count as an answer, so a well-formed envelope carrying a different payload is not
        # mistaken for readiness.
        "readiness_probe": {
            "method": "org.rdk.HdmiCecSink.1.getEnabled",
            "result_key": "enabled",
        },
        "settle_probe": {
            "method": "org.rdk.HdmiCecSink.1.getDeviceList",
            "result_key": "numberofdevices",
        },
    },
}

# Explicit consumer -> producers dependency model.
#
# Registration order alone is NOT a dependency mechanism: it fixes the sequence but says
# nothing about what happens when an earlier case fails, so without this map a consumer whose
# producer failed still runs and can report PASS against state that was never established.
# Every edge below is declared by the consumer module's own @precondition block, quoted here so
# the map and the modules cannot drift apart silently:
#   * TCID12 <- TCID11  "TCID11_Set_Vendor_ID has run at the preceding registration position
#     and written the vendor identifier this case reads back."
#   * TCID21 <- TCID20  "TCID20_ARC_Initiation_Flow is expected to have run immediately before
#     this case and to have left ARC enabled; this module is the half of that pair which
#     restores it."
#   * TCID31 <- TCID30  "TCID30_Repeated_Disable_Idempotent has run at the preceding position."
#
# No edge is declared for any other case, deliberately. TCID32_Invalid_ARC_Routing_Nochange is
# the case a reader is most likely to expect here, and its @precondition states the opposite:
# it "neither depends on that value nor changes it, because it compares two observations
# instead of pinning one". Declaring an edge it disclaims would make this map fiction.
#
# WHAT THE MAP DOES NOT COVER, stated rather than implied. Other residual couplings exist and are
# handled in two different ways, only one of which is a restoration:
#   * RESTORED AT THE SOURCE. TCID28 and TCID29 capture the vendor identifier and the OSD name on
#     entry and put them back in their cleanup() hooks; TCID31 restores the enabled flag the same
#     way; TCID17 puts the active source back where it found it and TCID19 does the same for the
#     route; TCID18 reproduces whichever of the three entry states it captured for the active
#     source, confirming each by re-reading it; TCID21 takes ARC back down; TCID27 detaches the
#     peer it attached and confirms the emulated topology is back; TCID33 re-declares the topology
#     its sweep walked and confirms the plugin still answers. The set of modules that publish a
#     cleanup() is exactly the set of RESTORES_ITSELF entries in RESTORATION_CONTRACT below, and
#     this list is that set - not an independent count that could fall behind it. The identity is
#     held by enforce_restoration_contract(), which refuses a cleanup() the registry does not
#     record as RESTORES_ITSELF and refuses a RESTORES_ITSELF entry that publishes no callable
#     cleanup(), so a hook added or removed without updating the registry is a start-up failure
#     rather than a stale sentence here. Their residuals do not reach a later case at all.
#   * DECLARED, NOT RESTORED, because no inverse operation exists to call.
#     TCID15_Send_Standby_Message broadcasts <Standby> and the sink's command surface publishes no
#     wake to undo it, which that module states in its own documentation rather than leaving to be
#     inferred. It is the only case in this position: every other module that leaves a residual
#     either restores it in its own hook (the bullet above) or is named in
#     UNCLASSIFIED_MUTATING_CASES below, where the boundary of what has been established is
#     declared and enforced. TCID15 is not an edge in this map because the later cases do not
#     REQUIRE its residual - each re-establishes what it needs, TCID25 by re-issuing the two
#     view-on documents in its own finally clause - and an edge would claim a dependency that the
#     consumer disclaims.
#
# A producer must be registered EARLIER than its consumer in "tests"; resolve_dependencies()
# enforces that, so a forward or circular edge is a startup error rather than a silent skip.
TEST_DEPENDENCIES = {
    "hdmicecsink": {
        "TCID12_Verify_Vendor_ID_Readback": ("TCID11_Set_Vendor_ID",),
        "TCID21_ARC_Termination_Flow": ("TCID20_ARC_Initiation_Flow",),
        "TCID31_Repeated_Enable_Idempotent": ("TCID30_Repeated_Disable_Idempotent",),
    },
}

# Bounded-wait budgets, in seconds. Every wait in this module is a bounded poll of a named
# observable rather than a fixed sleep: it returns as soon as the state it is waiting for is
# observed, and when the budget expires it says so instead of continuing silently. The poll
# intervals below are the gap BETWEEN observations, not a duration anything waits for.
PLUGIN_READY_TIMEOUT_S = 30.0
PLUGIN_READY_POLL_INTERVAL_S = 0.25
# Two identical consecutive readings are what "settled" is defined as here. One reading proves
# nothing about stability, and a third would double the cost of every inter-case gap for no
# additional evidence.
SETTLE_STABLE_READS = 2
SETTLE_TIMEOUT_S = 15.0
SETTLE_POLL_INTERVAL_S = 0.5

# Maps test suite names to their corresponding RDK plugin callsigns for activation
SUITE_PLUGIN_CALLSIGNS = {
    "hdmicecsink": "org.rdk.HdmiCecSink",
}

# Maps test suite names to the module whose run_test() must succeed BEFORE the first test case
# runs. The sink suite bootstraps its CEC device list through Init_Devicelist_Populate, and a
# False return there aborts the whole suite rather than letting every case fail on a topology
# that was never established.
SUITE_INIT_MODULES = {
    "hdmicecsink": "Init_Devicelist_Populate",
}


def normalize_suite_name(raw_name):
    '''Reduce a suite name to its comparison form so CLI spelling does not matter.
    Surrounding whitespace, underscores and hyphens are removed and the result is lower
    cased, which makes "hdmicecsink", "hdmi_cec_sink", "HDMI-CEC-SINK" and " HDMICECSink "
    all resolve to the same registry key.
    Args:
        raw_name: Suite name exactly as supplied on the command line or as a registry key.
    Returns:
        The normalized, lower-cased name with "_", "-" and outer whitespace removed.
    '''
    return raw_name.strip().replace("_", "").replace("-", "").lower()


def load_test_cases(suite_name):
    '''Import every module registered for a suite and bind its run_test entry point.
    The suite's module directory is placed on sys.path and each registered name is imported
    with importlib, in the declared order. Binding module.run_test here - rather than at call
    time - means a module that exists but does not publish run_test fails immediately and
    visibly instead of part way through a run.
    A module MAY additionally publish a callable cleanup(), which is bound here and which the
    runner then calls unconditionally - after a pass, after a failure, after an exception, and
    for a case that was skipped because its producer failed. cleanup() is the restoration half
    of a producer/consumer pair, so it must be idempotent and must not assume that run_test()
    ran or succeeded. Publishing it is optional: a case that changes nothing needs none, and
    getattr keeps a module without one perfectly valid.

    Args:
        suite_name: A key of SUITES, already normalized and matched by the caller.
    Returns:
        (banner, test_cases) where banner is the suite's banner string and test_cases is a
        list of (module_name, run_test_callable, cleanup_callable_or_None) tuples in declared
        execution order.
    Raises:
        KeyError: suite_name is not a registered suite.
        ValueError: the suite registers the same module more than once. Checked before anything
            is imported, because a duplicate is invisible everywhere else: importlib returns the
            cached module, enforce_restoration_contract() compares SETS and so cannot see a
            repeat, and the runner would simply run the case twice.
        ImportError: a registered module is missing from the suite's Testcases/ directory or
            fails while being imported. This is deliberate - a silently skipped test case
            would misreport the suite as complete.
        AttributeError: a registered module imported cleanly but publishes no run_test entry
            point, so there is nothing for the runner to call.
        TypeError: a registered module publishes a cleanup attribute that is not callable, so
            the restoration the runner is relying on could never be invoked.
    '''
    suite_config = SUITES[suite_name]
    module_dir = str(suite_config["module_dir"])

    # A DUPLICATE REGISTRATION IS REFUSED HERE, BEFORE ANY MODULE IS IMPORTED.
    #
    # Order is load-bearing in this suite - TCID12 reads back what TCID11 wrote, TCID21 restores
    # what TCID20 left up, TCID31 restores what TCID30 disabled - so a case registered twice is
    # not a harmless repetition. Its run_test() would execute at two positions, and cleanup() is
    # called once per registration, so a mutating case would restore state that a later copy of
    # itself then disturbs again, and the suite summary would report a total that does not match
    # the registered set. Nothing else in this file can see it: importlib hands back the cached
    # module the second time, and enforce_restoration_contract() reasons over sets.
    registered = list(suite_config["tests"])
    duplicated = sorted({name for name in registered if registered.count(name) > 1})
    if duplicated:
        raise ValueError(
            f"suite {suite_name!r} registers duplicate test case(s), each appearing more than "
            "once in its \"tests\" list: " + ", ".join(duplicated)
            + " - remove the duplicate, because order is load-bearing here and each registration "
            "gets its own run_test() call and its own cleanup() call"
        )

    # Putting the Testcases/ directory on sys.path is what lets the modules be imported by
    # bare name, which is why this tree needs no __init__.py and is not a package. Guarding
    # the insert keeps sys.path free of duplicates when a caller loads a suite more than once.
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    test_cases = []
    modules = {}
    for module_name in registered:
        module = importlib.import_module(module_name)
        modules[module_name] = module
        cleanup_fn = getattr(module, "cleanup", None)
        if cleanup_fn is not None and not callable(cleanup_fn):
            raise TypeError(f"{module_name}.cleanup exists but is not callable")
        test_cases.append((module_name, module.run_test, cleanup_fn))

    # Checked here, while the modules are in hand and before the caller touches the device.
    enforce_restoration_contract(suite_name, modules)

    return suite_config["banner"], test_cases


# ------------------------------------------------------------------------------------
# THE RESTORATION CONTRACT, AND WHY IT IS A REGISTRY RATHER THAN A CONVENTION.
#
# `getattr(module, "cleanup", None)` is a permissive lookup: a module that should restore state
# and simply has no hook is indistinguishable from one that needs none, and the runner reports
# both as "nothing to do". That permissiveness let a real gap sit in this suite unnoticed while
# THREE files asserted the opposite - TCID20 stated that "the restore lives in TCID21's cleanup()
# hook", TCID21's own @details described that hook, and TCID27 and TCID33 each named a restoration
# mechanism (a finally clause, a re-declared topology) that did not exist. None of those claims was
# checkable by anything, so all of them could stop being true silently.
#
# This registry makes the posture of a case a DECLARED, VALIDATED property. Each entry is one of:
#
#   RESTORES_ITSELF   the module must publish a callable cleanup(). Its own state changes are its
#                     own to undo.
#   restorer name     the module defers restoration to the NAMED case, which must be registered,
#                     must publish a callable cleanup(), and must run AFTER it. This is the shape
#                     of a producer/consumer pair such as TCID20 -> TCID21, where a hook on the
#                     producer would fire before the consumer ever ran and destroy it.
#   READ_ONLY         the module changes no device state. Verified mechanically, not trusted: the
#                     check below refuses a READ_ONLY module that publishes a cleanup() or names a
#                     restorer, either of which contradicts the classification.
#
# WHAT THIS REGISTRY DOES NOT CLAIM, stated because an omission here would read downstream as
# coverage. It enumerates the cases whose restoration posture has been ESTABLISHED. Cases absent
# from it invoke at least one mutating API or post at least one vComponent document, and their
# posture has NOT been established - they are listed in UNCLASSIFIED_MUTATING_CASES below and
# named in a warning at start-up, so the gap is visible rather than implied. Classifying them is
# open work, not a completed audit.
#
# Two forward guards keep the registry from drifting out of date in the direction it can:
#   * a module that publishes cleanup() must be registered as RESTORES_ITSELF - so a new hook
#     cannot be added without the registry learning about it;
#   * a module that declares RESTORED_BY must be registered with that same restorer - so the
#     declaration and the registry cannot disagree.
# ------------------------------------------------------------------------------------
RESTORES_ITSELF = "__self__"
READ_ONLY = "__read_only__"

RESTORATION_CONTRACT = {
    # Read-only probes: no setter, no vComponent post. That property was established by inspection
    # of every call site in these ten modules, and inspection is all it rests on - what the guards
    # below re-check is its COMPLEMENT, a READ_ONLY module that publishes a cleanup() or names a
    # restorer, either of which contradicts the classification. A setter added to one of these
    # modules later would not be caught at start-up, so it has to be caught in review.
    "TCID01_Get_Enabled_Status": READ_ONLY,
    "TCID02_Get_Devicelist": READ_ONLY,
    "TCID03_Get_OSD_Name": READ_ONLY,
    "TCID04_Get_Vendor_ID": READ_ONLY,
    "TCID05_Get_CEC_Version": READ_ONLY,
    "TCID06_Get_Active_Source": READ_ONLY,
    "TCID07_Get_Active_Route": READ_ONLY,
    "TCID08_Get_Audio_Device_Connected_Status": READ_ONLY,
    "TCID09_Print_Devicelist": READ_ONLY,
    "TCID12_Verify_Vendor_ID_Readback": READ_ONLY,
    # Self-restoring: each captures what it found, or records that it disturbed a known invariant,
    # and puts it back in its own hook.
    "TCID17_Request_Active_Source_Flow": RESTORES_ITSELF,
    "TCID18_Set_Active_Source_Flow": RESTORES_ITSELF,
    "TCID19_Active_Path_Routing_Change_Flow": RESTORES_ITSELF,
    "TCID21_ARC_Termination_Flow": RESTORES_ITSELF,
    "TCID27_Device_Add_Remove_Discovery_Flow": RESTORES_ITSELF,
    "TCID28_Invalid_VendorID_Nochange": RESTORES_ITSELF,
    "TCID29_Invalid_OSD_Setnochange": RESTORES_ITSELF,
    "TCID31_Repeated_Enable_Idempotent": RESTORES_ITSELF,
    "TCID33_Process_Yaml_Health_Check": RESTORES_ITSELF,
    # Deferred: the ARC pair. A hook on the producer would disable ARC before the consumer ran.
    "TCID20_ARC_Initiation_Flow": "TCID21_ARC_Termination_Flow",
}

# Registered cases that invoke a mutating API or post a vComponent document and whose restoration
# posture this pass did NOT establish. Named here so the boundary of the registry above is explicit
# and so start-up says so out loud; each still runs, and each still has its cleanup() called if it
# ever publishes one.
#
# THIS TUPLE IS LOAD-BEARING, NOT A NOTE. enforce_restoration_contract() compares it against the
# set it derives from the registry, and a difference is a REGISTRATION FAILURE. That is what makes
# "a case whose restoration posture nobody has established cannot be added silently" true in
# general rather than only for the cases this pass happened to look at: a new case is unclassified,
# the derived set no longer matches this tuple, and the suite refuses to start until somebody
# either classifies it in RESTORATION_CONTRACT or adds it here deliberately.
UNCLASSIFIED_MUTATING_CASES = (
    "TCID10_Set_OSD_Name",
    "TCID11_Set_Vendor_ID",
    "TCID13_Set_Menu_Language",
    "TCID14_Set_Latency_Info",
    "TCID15_Send_Standby_Message",
    "TCID16_Send_Key_Press_Event",
    "TCID22_System_Audio_Mode_Flow",
    "TCID23_Short_Audio_Descriptor_Flow",
    "TCID24_Audio_Status_And_Power_Flow",
    "TCID25_Standby_Coordination_Flow",
    "TCID26_User_Control_Pressed_Released_Flow",
    "TCID30_Repeated_Disable_Idempotent",
    "TCID32_Invalid_ARC_Routing_Nochange",
)


def enforce_restoration_contract(suite_name, modules):
    '''Validate every registered case against RESTORATION_CONTRACT, before the device is touched.

    Args:
        suite_name: A key of SUITES, used only in messages.
        modules: {module_name: imported module} for every case registered by the suite, in any
            order; the declared order is read from SUITES for the "restorer runs later" check.
    Raises:
        TypeError: a case's declared posture is not satisfied - a RESTORES_ITSELF case with no
            callable cleanup(), a deferral naming an unregistered case, a case with no cleanup(),
            or one that runs no later than the case deferring to it; a READ_ONLY case that
            publishes a cleanup() or names a restorer; a module publishing cleanup() that the
            registry does not know about; or a RESTORED_BY declaration the registry contradicts.
            Raised rather than warned because an unenforceable restoration contract is a defect in
            the suite, and a run that starts anyway leaves a device in a state nobody can name.
    '''
    order = list(SUITES[suite_name]["tests"])
    position = {name: index for index, name in enumerate(order)}
    problems = []

    for name in order:
        module = modules[name]
        hook = getattr(module, "cleanup", None)
        declared_restorer = getattr(module, "RESTORED_BY", None)
        posture = RESTORATION_CONTRACT.get(name)

        # Forward guard 1: a hook the registry does not know about.
        if callable(hook) and posture != RESTORES_ITSELF:
            problems.append(
                f"{name} publishes cleanup() but RESTORATION_CONTRACT records it as "
                f"{posture!r}; register it as RESTORES_ITSELF so the contract and the code agree"
            )
        # Forward guard 2: a declaration the registry contradicts.
        if declared_restorer is not None and posture != declared_restorer:
            problems.append(
                f"{name} declares RESTORED_BY={declared_restorer!r} but RESTORATION_CONTRACT "
                f"records {posture!r}; the two must name the same restorer"
            )

        if posture is None:
            continue  # Unclassified; reported once, below, rather than per case.
        if posture == READ_ONLY:
            if callable(hook) or declared_restorer is not None:
                problems.append(
                    f"{name} is registered READ_ONLY but names a restoration mechanism, so one of "
                    "the two is wrong"
                )
            continue
        if posture == RESTORES_ITSELF:
            if not callable(hook):
                problems.append(
                    f"{name} is registered as restoring itself but publishes no callable "
                    "cleanup(), so nothing would put its state back"
                )
            continue

        # A deferral. The named restorer must exist, restore itself, and run later.
        restorer = posture
        if restorer not in position:
            problems.append(
                f"{name} defers restoration to {restorer!r}, which is not registered in suite "
                f"{suite_name!r}, so its state would never be restored"
            )
            continue
        if not callable(getattr(modules[restorer], "cleanup", None)):
            problems.append(
                f"{name} defers restoration to {restorer!r}, which publishes no callable "
                "cleanup() - exactly the gap this check exists to catch"
            )
        if position[restorer] <= position[name]:
            problems.append(
                f"{name} defers restoration to {restorer!r}, which is registered at position "
                f"{position[restorer]} - at or before {name}'s own position {position[name]}, so "
                "the restorer would run first and have nothing to restore"
            )

    if problems:
        raise TypeError(
            f"the restoration contract for suite {suite_name!r} is not satisfied:\n  - "
            + "\n  - ".join(problems)
        )

    unclassified = [n for n in order if n not in RESTORATION_CONTRACT]
    unexpected = sorted(set(unclassified) - set(UNCLASSIFIED_MUTATING_CASES))
    stale = sorted(set(UNCLASSIFIED_MUTATING_CASES) - set(unclassified))
    if unexpected:
        problems.append(
            "these registered case(s) have no declared restoration posture and are not listed in "
            "UNCLASSIFIED_MUTATING_CASES either, so nothing states whether they leave the device as "
            "they found it: " + ", ".join(unexpected)
            + ". Classify each in RESTORATION_CONTRACT, or list it there deliberately."
        )
    if stale:
        problems.append(
            "UNCLASSIFIED_MUTATING_CASES names case(s) that are now classified or no longer "
            "registered, so the documented boundary is out of date: " + ", ".join(stale)
        )
    if problems:
        raise TypeError(
            f"the restoration contract for suite {suite_name!r} is not satisfied:\n  - "
            + "\n  - ".join(problems)
        )

    if unclassified:
        log_warning(
            f"{len(unclassified)} registered case(s) have no declared restoration posture, so it "
            "is NOT established that they leave the device as they found it: "
            + ", ".join(unclassified)
        )
        log_warning(
            "    Each still runs and each still has its cleanup() called if it publishes one. "
            "Classifying them in RESTORATION_CONTRACT is open work, deliberately not claimed here."
        )
    log_info(
        f"restoration contract satisfied: {sum(1 for p in RESTORATION_CONTRACT.values() if p == RESTORES_ITSELF)} "
        f"self-restoring, {sum(1 for p in RESTORATION_CONTRACT.values() if p not in (RESTORES_ITSELF, READ_ONLY))} "
        f"deferred, {sum(1 for p in RESTORATION_CONTRACT.values() if p == READ_ONLY)} read-only, "
        f"{len(unclassified)} unclassified"
    )


def resolve_dependencies(suite_name):
    '''Validate the suite's dependency map against its registration order and return it.
    Resolution is a startup check, not a per-case one, so an incoherent map is a loud error
    before the device is touched rather than a mis-skipped case in the middle of a run. A
    producer that is not registered, a consumer that is not registered, a case declared as its
    own producer and a producer registered at or after its consumer are all rejected - the last
    of these is what rules out circular edges, since a graph whose every edge points strictly
    backwards in a fixed order cannot contain a cycle.
    Args:
        suite_name: A key of SUITES, already normalized and matched by the caller.
    Returns:
        {consumer_name: (producer_name, ...)} containing only validated edges. An empty dict
        when the suite declares no dependencies.
    Raises:
        ValueError: any edge names an unregistered case, is self-referential, or names a
            producer that does not run strictly before its consumer.
    '''
    ordered = SUITES[suite_name]["tests"]
    position = {name: index for index, name in enumerate(ordered)}
    declared = TEST_DEPENDENCIES.get(suite_name, {})

    validated = {}
    for consumer, producers in declared.items():
        if consumer not in position:
            raise ValueError(f"dependency declared for unregistered case '{consumer}'")
        for producer in producers:
            if producer not in position:
                raise ValueError(
                    f"case '{consumer}' depends on unregistered case '{producer}'"
                )
            if producer == consumer:
                raise ValueError(f"case '{consumer}' declares itself as its own producer")
            if position[producer] >= position[consumer]:
                raise ValueError(
                    f"case '{consumer}' depends on '{producer}', which is registered at or "
                    "after it; a producer must run strictly before its consumer"
                )
        validated[consumer] = tuple(producers)

    return validated


def _probe_value(probe):
    '''Dispatch one read-only JSON-RPC probe and return (answered, value).
    A probe counts as answered only when the target returned a JSON-RPC envelope with no
    "error" member, whose "result" is an object, whose "success" member is not explicitly
    false, and which carries the probe's declared result_key. Anything weaker - a transport
    failure, an error envelope, a result that is not an object, a plugin reporting failure -
    reads as unanswered, so a plugin that is registered but not yet dispatching can never be
    mistaken for a ready one.
    Args:
        probe: {"method": fully qualified JSON-RPC method, "result_key": required member}.
    Returns:
        (True, value_of_result_key) when the probe answered; (False, None) otherwise.
    '''
    response = send_jsonrpc_command(probe["method"])
    if not response or "error" in response:
        return False, None
    result = response.get("result")
    if not isinstance(result, dict):
        return False, None
    if result.get("success") is False:
        return False, None
    key = probe["result_key"]
    if key not in result:
        return False, None
    return True, result[key]


def _plugin_state(callsign):
    '''Return the controller's reported state string for a callsign, or None.
    Controller.1.status@<callsign> answers with a list of service records in Thunder R4 and a
    single record in some builds, so both shapes are accepted and the first record's "state" is
    returned. None means the controller did not answer, answered with an error, or answered
    without a usable state - none of which is treated as activated.
    Args:
        callsign: Plugin callsign, e.g. "org.rdk.HdmiCecSink".
    Returns:
        The state string exactly as reported, or None when no state could be read.
    '''
    response = send_jsonrpc_command(f"Controller.1.status@{callsign}")
    if not response or "error" in response:
        return None
    result = response.get("result")
    if isinstance(result, list):
        result = result[0] if result else None
    if not isinstance(result, dict):
        return None
    state = result.get("state")
    return state if isinstance(state, str) else None


def wait_for_plugin_ready(callsign, probe, timeout_s=PLUGIN_READY_TIMEOUT_S,
                          interval_s=PLUGIN_READY_POLL_INTERVAL_S):
    '''Poll until the plugin is both activated and dispatching, or the budget expires.
    This is the bounded-observation replacement for a fixed post-activation sleep. Two distinct
    observables must both hold: the controller must report the callsign as activated, and the
    plugin must answer its own readiness probe. The first alone is not enough - a plugin
    transitions to activated before its JSON-RPC surface is answering - and the second alone
    would not distinguish a plugin that is up from a controller that is unreachable.
    The elapsed time is measured with monotonic(), which no clock adjustment can move
    backwards, so the budget cannot be extended or truncated by a wall-clock change mid-run.
    Args:
        callsign: Plugin callsign to observe, or a falsy value to observe the probe only.
        probe: Readiness probe as accepted by _probe_value, or None to observe state only.
        timeout_s: Upper bound on the whole wait, in seconds.
        interval_s: Gap between consecutive observations, in seconds.
    Returns:
        (True, elapsed_seconds) as soon as every declared observable holds;
        (False, elapsed_seconds) when the budget expired first.
    '''
    started = time.monotonic()
    deadline = started + max(0.0, float(timeout_s))
    while True:
        state_ok = True
        if callsign:
            state = _plugin_state(callsign)
            state_ok = state is not None and state.strip().lower() == "activated"
        probe_ok = True
        if state_ok and probe:
            probe_ok, _ = _probe_value(probe)
        if state_ok and probe_ok:
            return True, time.monotonic() - started
        if time.monotonic() >= deadline:
            return False, time.monotonic() - started
        # Sleeping the poll interval - never the whole budget - is what keeps this a bounded
        # observation: the loop leaves as soon as the state is observed.
        time.sleep(interval_s)


def wait_for_settled(probe, timeout_s=SETTLE_TIMEOUT_S, interval_s=SETTLE_POLL_INTERVAL_S,
                     stable_reads=SETTLE_STABLE_READS):
    '''Poll a probe until consecutive readings agree, or the budget expires.
    This is the bounded-observation replacement for a fixed inter-case sleep. "The bus has
    settled" is not a duration, it is a property: the plugin state that inbound CEC traffic
    changes has stopped changing. Requiring stable_reads consecutive equal readings observes
    exactly that, and returns immediately on a quiet bus instead of always paying a fixed
    pause. An unanswered probe resets the run of agreements rather than counting towards it.
    Args:
        probe: Settle probe as accepted by _probe_value, or None to skip the wait entirely.
        timeout_s: Upper bound on the whole wait, in seconds.
        interval_s: Gap between consecutive observations, in seconds.
        stable_reads: Number of consecutive equal readings that constitute settled.
    Returns:
        (True, elapsed_seconds, last_value) once the readings agree, or immediately with
        (True, 0.0, None) when no probe is declared;
        (False, elapsed_seconds, last_value) when the budget expired first.
    '''
    if not probe:
        return True, 0.0, None

    started = time.monotonic()
    deadline = started + max(0.0, float(timeout_s))
    agreements = 0
    previous = None
    have_previous = False
    while True:
        answered, value = _probe_value(probe)
        if answered:
            if have_previous and value == previous:
                agreements += 1
            else:
                agreements = 1
            previous = value
            have_previous = True
            if agreements >= max(1, int(stable_reads)):
                return True, time.monotonic() - started, value
        else:
            agreements = 0
            have_previous = False
        if time.monotonic() >= deadline:
            return False, time.monotonic() - started, previous if have_previous else None
        time.sleep(interval_s)


# The two accepted spellings of each state, as sets so a reader can see the whole accepted
# vocabulary in one place.  Anything outside both is a configuration error, not a third state.
_AUTO_ACTIVATE_TRUE = frozenset({"1", "true", "yes", "on"})
_AUTO_ACTIVATE_FALSE = frozenset({"0", "false", "no", "off"})


def _parse_auto_activate(raw):
    '''Interpret AUTO_ACTIVATE_PLUGINS, or return None when it cannot be read exactly.

    Args:
        raw: The environment value, or None when the variable is not set at all.
    Returns:
        True to activate, False to skip activation, or None when the value is neither - in which
        case an error naming both accepted vocabularies has already been logged and the caller
        must refuse to run.
    '''
    if raw is None:
        # Unset is the documented default and is not an error.
        return True
    token = raw.strip().casefold()
    if token in _AUTO_ACTIVATE_TRUE:
        return True
    if token in _AUTO_ACTIVATE_FALSE:
        return False
    log_error(
        f"AUTO_ACTIVATE_PLUGINS is set to {sanitise_for_log(raw, 64)}, which is neither a yes nor "
        "a no.  Accepted: "
        + ", ".join(sorted(_AUTO_ACTIVATE_TRUE))
        + " to activate the plugin; "
        + ", ".join(sorted(_AUTO_ACTIVATE_FALSE))
        + " to skip activation.  Refusing to run: guessing would decide whether this run "
        "activates a plugin somebody else may already have configured, and every case's result "
        "afterwards depends on which way that guess went."
    )
    return None


def _run_cleanup(tc_name, cleanup_fn):
    '''Run a case's optional cleanup() hook and report whether it completed.
    The hook is restoration, not verdict: its outcome never turns a failing case into a passing
    one or the reverse. It is called unconditionally by the runner - after a pass, a failure, an
    exception, and for a case skipped because its producer failed - so a pair whose restoring
    half never got to run as a test still restores the device.
    A broad except is correct here for the same reason it is correct around a test case: any
    exception out of a restoration attempt means the device may be dirty, and the run must
    report that rather than propagate out of the runner's finally and abandon the remaining
    cases. The text is printed, not swallowed, and is replayed under the case's own banner.
    Args:
        tc_name: Registered module name, used only in messages.
        cleanup_fn: The bound cleanup callable, or None when the module publishes none.
    Returns:
        True when there was nothing to do or the hook completed without an explicit falsy
        return; False when the hook raised or returned a falsy value other than None.
    '''
    if cleanup_fn is None:
        return True
    try:
        outcome = cleanup_fn()
    except Exception as exc:
        # log_error, not print: the exception text can carry a device response verbatim (a
        # failed restoration usually names what came back), and a bare print puts whatever
        # control bytes are in it straight onto the terminal that is this run's only evidence.
        # log_error applies utils._guard_log_line; sanitise_for_log bounds and escapes the
        # exception text itself on top of that.  Still inside the captured-output window, so the
        # message is replayed under this case's banner exactly as before.
        log_error(
            f"EXCEPTION in {tc_name}.cleanup(): "
            f"{sanitise_for_log(f'{type(exc).__name__}: {exc}')}"
        )
        return False
    # A hook that returns nothing at all has still run to completion; only an explicit falsy
    # return is a restoration failure, so `return None` and `return True` mean the same thing.
    if outcome is None:
        return True
    return bool(outcome)


def activate_plugin_via_curl(callsign):
    '''Activate an RDK plugin through Controller.1.activate and report whether it worked.
    The controller is reached over JSON-RPC at whatever endpoint utils.py resolved; no
    endpoint is hard coded here and no service is started on the suite's behalf. A response
    that never arrived, a response carrying an "error" member and a response with no
    "result" member are all failures, so an unreachable or unavailable plugin can never be
    mistaken for a successful activation.
    Args:
        callsign: Plugin callsign to activate, e.g. "org.rdk.HdmiCecSink".
    Returns:
        True only when the controller answered with a "result" member and no "error"
        member; False on a transport failure, an error response or a missing result.
    '''
    # The request id matches the one utils.activate_plugin sends for this same call, and the
    # one the HDMI CEC Source suite's SuitManager.py uses. Keeping the value in step across
    # all three makes activation calls easy to correlate in a WPEFramework trace no matter
    # which module issued them, so the duplication is deliberate rather than accidental.
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


def run_suite_init(suite_name):
    '''Run the suite's initialization module, if one is registered, and report success.
    The init module bootstraps the CEC topology the test cases depend on, so it runs exactly
    once, before the first test case. Every failure mode - an unimportable module, a module
    without a run_test entry point, an exception raised inside it, and a plain False return -
    is reported as failure so the caller can abort instead of running 33 cases against a
    device that was never prepared.
    Args:
        suite_name: A key of SUITES, already normalized and matched by the caller.
    Returns:
        True when no init module is registered for the suite, or when the registered
        module's run_test() returned a truthy value; False on any failure mode above.
    '''
    module_name = SUITE_INIT_MODULES.get(suite_name)
    if not module_name:
        return True

    # The init module sits beside this file rather than under Testcases/, so BASE_DIR is what
    # has to be importable here. On POSIX Path.as_posix() and str() agree for an absolute
    # path, so testing one form and inserting the other still means "insert only if absent".
    if BASE_DIR.as_posix() not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    # A broad except is correct at this boundary: an init module can fail while being imported
    # for any number of reasons (a syntax error, a missing sibling module, a failed
    # module-level lookup) and every one of them means the suite cannot run. The reason is
    # logged rather than swallowed, and the traceback-free message keeps the abort readable.
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        log_error(f"Init module import failed: {module_name} ({exc})")
        return False

    run_fn = getattr(module, "run_test", None)
    if not callable(run_fn):
        log_error(f"Init module missing run_test(): {module_name}")
        return False

    log_info(f"Running suite initialization: {module_name}.run_test()")
    try:
        ok = bool(run_fn())
    except Exception as exc:
        log_error(f"Suite initialization threw exception: {exc}")
        return False

    if ok:
        log_success("Suite initialization completed successfully")
    else:
        log_error("Suite initialization failed")
    return ok


def run_suite(suite_name):
    '''Activate the plugin, initialise the suite, then run every registered case in order.
    Each case's own output is captured and replayed underneath its banner so the log reads
    one case at a time. A case that returns a falsy value AND a case that raises are both
    counted as failures - the exception text is printed into that case's captured output and
    the run continues, so one broken case cannot hide the verdict of the remaining ones.

    Three properties beyond plain sequencing are enforced here:
      * Declared dependencies are honoured. A case whose producer did not PASS is SKIPPED and
        counted as skipped. It is never run and can therefore never report PASS against state
        that was never established, and skipped is never folded into passed.
      * Restoration is unconditional. Every case's optional cleanup() runs whether the case
        passed, failed, raised or was skipped, so the restoring half of a producer/consumer
        pair still restores the device when its partner failed.
      * Nothing is waited for blindly. Plugin readiness and inter-case settling are bounded
        polls of named JSON-RPC observables (see the suite's readiness_probe and settle_probe),
        so a ready device is not paid for in fixed sleeps and an unready one is reported.
    Args:
        suite_name: A key of SUITES, already normalized and matched by the caller.
    Returns:
        True only when every registered case passed and every cleanup completed; False when any
        case failed, any case was skipped, any cleanup failed, the plugin could not be activated
        or did not become ready, or suite initialization did not complete.
    '''
    banner, test_cases = load_test_cases(suite_name)
    # Resolved before the device is touched: an incoherent dependency map must stop the run
    # here, not half way through it.
    dependencies = resolve_dependencies(suite_name)
    suite_config = SUITES[suite_name]
    readiness_probe = suite_config.get("readiness_probe")
    settle_probe = suite_config.get("settle_probe")
    print(banner)

    # Activation is ON by default; export AUTO_ACTIVATE_PLUGINS=0 to skip it when the plugin is
    # already activated by other means.
    #
    # PARSED STRICTLY, AND A VALUE THAT CANNOT BE READ STOPS THE RUN.
    #
    # This used to be `... .lower() not in ("0", "false", "no")`, which is a deny-list: every
    # spelling outside those three - "off", "FALSE " with a trailing space, "disable", "n", or a
    # typo such as "flase" - was read as "activate the plugin", the opposite of what the operator
    # asked for.  In a suite whose entire purpose is to observe a device, being wrong about
    # whether this run activates the plugin decides what every case afterwards is measuring: with
    # activation unwanted but performed, the run mutates a device somebody else had already set
    # up; with it wanted but skipped, every case fails against a plugin that was never up and the
    # reason appears nowhere.
    #
    # Both states are therefore named explicitly, and anything else is refused BEFORE the first
    # request is issued - so a misspelling costs a diagnostic rather than a whole run whose
    # meaning is unknown.  Surrounding whitespace is stripped because an exported value picks it
    # up easily; case is folded because "TRUE" and "true" are plainly the same answer.
    auto_activate = _parse_auto_activate(os.environ.get("AUTO_ACTIVATE_PLUGINS"))
    if auto_activate is None:
        return False
    callsign = SUITE_PLUGIN_CALLSIGNS.get(suite_name)
    if auto_activate and callsign:
        log_info(f"Auto-activating plugin '{callsign}' via curl JSON-RPC at {WPEFRAMEWORK_JSONRPC_URL}")
        if activate_plugin_via_curl(callsign):
            log_success(f"Plugin activated: {callsign}")
            # Controller.1.activate returns once the request is accepted; Initialize() and the
            # plugin's worker threads come up after it. That readiness is observable, so it is
            # waited for rather than estimated. A plugin already up costs nothing here, and an
            # expiry is reported instead of being read as success.
            #
            # BOTH observables are required, which is why this uses the suite's declared
            # readiness_probe rather than the controller state alone. A plugin transitions to
            # "activated" BEFORE its own JSON-RPC surface begins dispatching, so the controller
            # state on its own would report ready while the first case's very first call still
            # failed; and the probe on its own would not distinguish a plugin that is up from a
            # controller that is unreachable. The probe is declared in SUITES so this runner
            # stays suite agnostic.
            log_info(
                f"Waiting for {callsign} to report itself activated and to answer "
                f"{readiness_probe['method'] if readiness_probe else 'no probe'}..."
            )
            # EXACTLY ONE POLL, and that is the whole point of the budget.
            #
            # "activated" is the framework's word for the request having been accepted; the
            # plugin is only USABLE once it dispatches its own methods.  readiness_probe is the
            # observable for that, so it is polled here rather than a fixed post-activation
            # pause being taken.  An expiry is reported and the cases still run - their own
            # assertions decide the verdict - because a slow bring-up is not by itself a failure.
            #
            # This call must not be repeated.  wait_for_plugin_ready is itself the bounded
            # observation: it returns on the first read where every declared observable holds,
            # and otherwise at PLUGIN_READY_TIMEOUT_S.  A second call therefore cannot learn
            # anything the first did not - a plugin that is up has already returned True - while
            # each extra call adds another whole budget to a bring-up that is failing, and the
            # warning below would name a budget smaller than the wait actually taken.  One call
            # keeps the worst case at PLUGIN_READY_TIMEOUT_S, which is the number reported.
            ready, ready_elapsed = wait_for_plugin_ready(callsign, readiness_probe)
            if ready:
                observed = (
                    f"answered {readiness_probe['method']}" if readiness_probe
                    else "reported itself activated"
                )
                log_success(f"{callsign} {observed} after {ready_elapsed:.2f}s")
            else:
                log_warning(
                    f"{callsign} did not answer its readiness probe within "
                    f"{PLUGIN_READY_TIMEOUT_S}s (waited {ready_elapsed:.2f}s); the cases below "
                    "will run anyway and their own assertions decide the verdict"
                )
        else:
            # Abort rather than run: every case would fail against a plugin that is not up,
            # and 33 misleading failures are worth less than one accurate one.
            log_error(f"Plugin activation failed: {callsign}")
            log_error("Check JSON-RPC endpoint reachability and plugin availability before running tests.")
            return False

    if not run_suite_init(suite_name):
        log_error("Aborting suite because initialization did not complete successfully.")
        return False

    passed = 0
    failed = 0
    skipped = 0
    failed_cases = []
    skipped_cases = []
    cleanup_failures = []
    # Per-case outcome, keyed by module name: "PASSED", "FAILED" or "SKIPPED". This is what the
    # dependency check reads, and it is why a SKIPPED producer propagates - only "PASSED"
    # satisfies a dependency, so a consumer downstream of a skipped case is skipped in turn
    # rather than running against state two failures back.
    outcomes = {}
    # Captured BEFORE the loop, and restored in the finally of every iteration. If the real
    # stream were only recoverable from inside the try, an exception raised by a case would
    # leave sys.stdout pointing at a dead buffer and silently swallow every later message.
    original_stdout = sys.stdout
    last_index = len(test_cases) - 1

    for index, (tc_name, tc_fn, tc_cleanup) in enumerate(test_cases):
        unmet = [p for p in dependencies.get(tc_name, ()) if outcomes.get(p) != "PASSED"]

        log_info(f"\n{'='*60}")
        log_info(f"{'Skipping' if unmet else 'Running'}: {tc_name}")
        log_info(f"{'='*60}")

        captured = io.StringIO()
        sys.stdout = captured
        # Bound BEFORE the try so the read after the finally can never reference an unbound name.
        # _run_cleanup is the last statement of the try and swallows every Exception, so the only
        # way past it without assigning is a BaseException - and on that path the value below is
        # never read, because the exception leaves the loop entirely.
        cleanup_ok = True
        try:
            if unmet:
                # NOT RUN, and NOT PASSED. The producer's state was never established, so any
                # verdict this case could report would be about something else.
                result = None
                for producer in unmet:
                    log_warning(
                        f"SKIPPED {tc_name}: required producer {producer} "
                        f"{outcomes.get(producer, 'did not run')}"
                    )
            else:
                try:
                    result = tc_fn()
                except Exception as exc:
                    # An exception is a FAILURE, never a skip and never a pass. The text goes
                    # into the case's own captured output so it is replayed in place, under that
                    # case's banner.
                    #
                    # Routed through log_error rather than print for the same reason as the
                    # cleanup hook above: a case that fails while handling a device response
                    # routinely puts that response into the exception, and a log line is
                    # evidence.  The exception TYPE is named as well, because "EXCEPTION in X:
                    # " with an empty message - which a bare KeyError or an AssertionError with
                    # no text produces - said nothing at all about what happened.
                    result = False
                    log_error(
                        f"EXCEPTION in {tc_name}: "
                        f"{sanitise_for_log(f'{type(exc).__name__}: {exc}')}"
                    )
            # Restoration runs while output is still captured, so its messages are replayed
            # under this case's banner, and it runs on every path above - pass, fail, exception
            # and skip alike. _run_cleanup swallows nothing but propagates nothing either, so
            # the stdout restore below is always reached.
            #
            # Its outcome is CARRIED, not recorded here.  An unrestored device is a property of
            # the RUN rather than a verdict on this case, and the summary that names it is
            # printed outside this captured-output block, so cleanup_ok travels out through the
            # finally and is appended to cleanup_failures exactly once below, next to the log
            # line that reports it.  Recording it here as well would name the same case twice in
            # `Cases whose cleanup failed: [...]` and overstate how many restorations failed.
            cleanup_ok = _run_cleanup(tc_name, tc_cleanup)
        finally:
            sys.stdout = original_stdout

        output = captured.getvalue()
        # REPLAY, not composition - and therefore the one print() in this module that must stay a
        # print().  Everything in `output` was written by the case through utils' log_* helpers,
        # so it has already passed _guard_log_line: its control bytes are already rendered as
        # visible \xNN escapes and its length is already bounded.  Guarding it a second time
        # would escape those backslashes again and turn readable evidence into noise.  The
        # invariant this rests on is checked rather than assumed: no module under Testcases/, and
        # neither HdmiCECSink_Curl.py nor Init_Devicelist_Populate.py, contains a bare print() -
        # every one of them logs through utils.  A new case that used print() directly would be
        # the thing to fix, here or there.
        print(output, end="")

        # A FAILED RESTORATION IS RECORDED HERE, EXACTLY ONCE, and this is the only place it can
        # be.
        #
        # cleanup_failures is printed in the summary and folded into the suite verdict by the
        # return statement below, so the two mechanisms built to make an unrestored device
        # visible - the summary line and the `not cleanup_failures` term in the verdict - depend
        # on this append happening. It happens once per failing case and nowhere else: one entry
        # is what makes `Cases whose cleanup failed: [...]` a count of failed restorations rather
        # than a count of the places that record them.
        #
        # It is recorded SEPARATELY from the case verdict, and deliberately so. _run_cleanup's
        # own contract is that restoration is not a verdict: a cleanup failure must not turn a
        # failing case into a passing one or the reverse, so it does not touch passed/failed/
        # skipped or outcomes[] - which the dependency map reads - and instead fails the SUITE.
        # A case can therefore legitimately read [PASS] while the run as a whole reads failed,
        # which is the accurate description of "the case proved what it claimed and then could
        # not put the device back".
        if not cleanup_ok:
            cleanup_failures.append(tc_name)
            log_error(
                f"[CLEANUP FAILED] {tc_name} - its cleanup() hook raised or reported failure, so "
                "the device may not have been restored and the cases that follow may run against "
                "state this case left behind"
            )

        if unmet:
            skipped += 1
            outcomes[tc_name] = "SKIPPED"
            skipped_cases.append(f"{tc_name} (unmet: {', '.join(unmet)})")
            log_error(f"[SKIP] {tc_name} - unmet dependencies: {', '.join(unmet)}")
        elif result:
            passed += 1
            outcomes[tc_name] = "PASSED"
            log_success(f"[PASS] {tc_name}")
        else:
            failed += 1
            outcomes[tc_name] = "FAILED"
            failed_cases.append(tc_name)
            log_error(f"[FAIL] {tc_name}")

        # Between cases, wait for the bus to go QUIET rather than pausing for a fixed period.
        # "Settled" is a property, not a duration: consecutive equal readings of the one piece of
        # plugin state that inbound CEC traffic changes - the discovered device count - are the
        # evidence that nothing is still arriving. A quiet bus therefore costs one round trip
        # instead of a fixed pause, and a bus that never goes quiet is REPORTED rather than
        # silently slept through and left for the next case to fail against.
        #
        # This also subsumes the liveness check it replaces: an unanswered probe cannot satisfy
        # the settle condition, so a plugin that has stopped serving expires the budget and is
        # named here, which is strictly more than the single getEnabled round trip established.
        #
        # NOT after the last case. There is no following case for the bus to be quiet for, so
        # settling here would only add the budget to the run's duration - up to SETTLE_TIMEOUT_S
        # of it if the device is busy shutting down - and report a warning nothing acts on.
        #
        # ONE WAIT PER GAP, and the guard is on settle_probe as well as on the index. A suite
        # that declares no settle probe has nothing to observe, and wait_for_settled would
        # return (True, 0.0, None) for it - so the guard keeps the log honest instead of
        # announcing a settle that was never measured. Repeating the wait would multiply both
        # the budget (SETTLE_TIMEOUT_S per extra call, over 32 gaps) and the round trips
        # (SETTLE_STABLE_READS per extra call on a quiet bus) while telling the reader nothing
        # the first wait had not already established.
        if settle_probe and index != last_index:
            settled, settle_elapsed, last_value = wait_for_settled(settle_probe)
            if settled:
                log_info(
                    f"Bus settled after {tc_name} in {settle_elapsed:.2f}s "
                    f"({settle_probe['result_key']}={last_value})"
                )
            else:
                log_warning(
                    f"{settle_probe['method']} did not report {SETTLE_STABLE_READS} consecutive "
                    f"equal readings within {SETTLE_TIMEOUT_S}s after {tc_name} "
                    f"(waited {settle_elapsed:.2f}s, last {settle_probe['result_key']}="
                    f"{last_value}); the cases that follow may run against a bus that is still "
                    "changing, or a plugin that is no longer serving"
                )

    log_info(f"\n{'='*60}")
    log_info(f"Suite Summary: {passed} passed, {failed} failed, {skipped} skipped")
    if failed_cases:
        log_error(f"Failed cases: {failed_cases}")
    if skipped_cases:
        log_error(f"Skipped cases: {skipped_cases}")
    if cleanup_failures:
        log_error(f"Cases whose cleanup failed: {cleanup_failures}")
    log_info(f"{'='*60}")
    # A skip is not a pass, and an unrestored device is not a clean run: both count against the
    # suite verdict, so the exit code cannot read green while either is outstanding.
    return failed == 0 and skipped == 0 and not cleanup_failures


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run HDMI CEC test suites")
    parser.add_argument("suite", help=f"Test suite name. Available: {list(SUITES.keys())}")
    parser.add_argument("-t", "--timing", action="store_true", help="Enable timing output for passed test cases")

    args = parser.parse_args()

    # Set environment variable for timing mode
    if args.timing:
        os.environ["HDMICEC_TIMING_ENABLED"] = "1"

    # Suite names are matched in normalized form, so "hdmicecsink", "hdmi_cec_sink" and
    # "HDMICECSINK" all select the same suite while an unknown name still fails loudly.
    suite_arg = normalize_suite_name(args.suite)
    matching = [k for k in SUITES if normalize_suite_name(k) == suite_arg]
    if not matching:
        log_error(f"Unknown suite '{args.suite}'. Available: {list(SUITES.keys())}")
        sys.exit(1)

    # The process exit code is the suite's only machine-readable signal: 0 only when every
    # registered case passed, 1 on any failure, on a failed activation, or on a failed
    # initialization. CI must be able to trust it, so nothing else may be returned here.
    ok = run_suite(matching[0])
    sys.exit(0 if ok else 1)
