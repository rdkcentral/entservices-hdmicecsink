To execute the cases inside qemu

cd /tmp

git clone git@github.com:rdkcentral/entservices-hdmicecsink.git

cd entservices-hdmicecsink/Tests/vDeviceTests

EXECUTION:
with time : python3 SuitManager.py -t hdmicecsink
without time: python3 SuitManager.py hdmicecsink

Default Actions:
Plugin activation is enabled by default and runs before suite execution:
- hdmicecsink -> Controller.1.activate(callsign=org.rdk.HdmiCecSink)
- Init_Devicelist_Populate runs once, before the first test case.

Disable default activation only if needed:
- export AUTO_ACTIVATE_PLUGINS=0


If the testcases fail with "connection refused", configure endpoint host/ports before running.

Defaults used by the tests:
- MW JSON-RPC: http://127.0.0.1:9998/jsonrpc
  composed from TARGET_HOST=127.0.0.1 and JSONRPC_PORT=9998
- vComponent API: http://127.0.0.1:8080/api/postKVP
  composed from TARGET_HOST=127.0.0.1 and VCOMPONENT_PORT=8080

Endpoint overrides, in precedence order. The highest source that holds a value wins outright.
A variable that is unset OR set to an empty string falls through to the next source, so
exporting an empty value behaves exactly as if the variable were absent rather than blanking
the endpoint.

MW JSON-RPC endpoint:
  1. WPEFRAMEWORK_JSONRPC_URL    full URL
  2. JSONRPC_URL                 full URL; accepted as a legacy alias for the key above and
                                 consulted only when that key is unset or empty
  3. TARGET_HOST + JSONRPC_PORT  composed into http://<host>:<port>/jsonrpc

vComponent API endpoint:
  1. VCOMPONENT_API_URL             full URL
  2. TARGET_HOST + VCOMPONENT_PORT  composed into http://<host>:<port>/api/postKVP

  There is deliberately no VCOMPONENT_URL alias. The alias exists on the JSON-RPC side only,
  so do not assume the two endpoints are symmetric.

TARGET_HOST applies to both endpoints and defaults to 127.0.0.1. JSONRPC_PORT defaults to
9998 and VCOMPONENT_PORT to 8080.

Whichever source wins is validated before any request is built: the scheme must be http or
https, the port must lie within 1-65535, and the host may contain only letters, digits, dot,
underscore, hyphen, colon and square brackets, so an IPv6 endpoint such as
http://[::1]:9998/jsonrpc remains usable. A URL that carries whitespace or shell
metacharacters, or that begins with "-", is refused - curl reads a leading "-" as an option,
and an endpoint must never be able to become one. An override that fails validation stops the
suite with an error naming the variable to fix; it is never silently replaced by the default.

The 1-65535 rule applies to the port however it is expressed, so JSONRPC_PORT=99999 and
WPEFRAMEWORK_JSONRPC_URL=http://host:99999/jsonrpc are both refused at import, and so is a
port of 0 in either form. Two accepted shapes are worth naming because they look odd and are
allowed on purpose: a zero-padded port such as JSONRPC_PORT=007 (decimal and inside the range,
so it is used as given), and a host containing a hyphen anywhere, including first, such as
TARGET_HOST=-evil. A host is never an argument on its own - what reaches curl is the composed
URL, which always begins "http" - so the leading-"-" prohibition is a rule about a whole
endpoint override, not about the host inside one.

Examples:

# when running directly inside QEMU guest (services on localhost)
python3 SuitManager.py hdmicecsink

# when running from host against QEMU target IP
export TARGET_HOST=192.168.1.50
export JSONRPC_PORT=9998
export VCOMPONENT_PORT=8080
python3 SuitManager.py hdmicecsink

# full URL override form
export WPEFRAMEWORK_JSONRPC_URL=http://192.168.1.50:9998/jsonrpc
export VCOMPONENT_API_URL=http://192.168.1.50:8080/api/postKVP
python3 SuitManager.py hdmicecsink

# legacy alias form, equivalent to WPEFRAMEWORK_JSONRPC_URL when that key is not exported
export JSONRPC_URL=http://192.168.1.50:9998/jsonrpc
python3 SuitManager.py hdmicecsink

# command documents deployed on the device instead of beside this suite
export HDMICEC_CMD_BASE=/etc/hdmicec/vcomponent_configurations/commands
python3 SuitManager.py hdmicecsink

# elapsed time appended to each case's PASS line (the only messages routed through
# utils.log_with_timing); every other log line is unchanged
export HDMICEC_TIMING_ENABLED=1
python3 SuitManager.py hdmicecsink


Command payload root, and what pointing it somewhere else means:

The vComponent YAML command documents are read from a directory resolved in this order:
  1. HDMICEC_CMD_BASE                                     used as given, when non-empty
  2. <this directory>/vcomponent_configurations/commands  when that directory exists
  3. /etc/hdmicec/vcomponent_configurations/commands      the on-device location

An empty HDMICEC_CMD_BASE falls through to the next source, as every other override does. A
non-empty one is taken verbatim: it is not tested for existence at import and "/tmp/../etc" is
not collapsed or rejected there, because the check that matters is the one applied to every
document actually posted, described next. A root that does not exist therefore costs a refusal
naming the document, not a startup error.

Path trust expectations. Every document posted to the vComponent API must resolve inside
either this suite's own vcomponent_configurations/ tree or the configured HDMICEC_CMD_BASE,
and the file is reached by walking the path one component at a time from that root with
O_NOFOLLOW. In practice that means:
- no component of the path may be a symbolic link, the file itself included;
- the target must be a regular file, established with fstat on the descriptor that is then
  read, rather than on the pathname - so the document that is posted is provably the document
  that was approved, with no interval in which the two could differ;
- the document must be no larger than 1 MiB;
- a path resolving outside both roots is refused, including one that tries to climb out with
  "..".
A refusal is reported as HTTP status 0 with the reason as the response body, so the calling
test case fails with that reason rather than skipping silently.

Overriding HDMICEC_CMD_BASE therefore extends trust: every regular file beneath the directory
you name becomes postable by this suite. Point it at a directory you control that holds only
vComponent command documents. Do not point it at a shared or world-writable location such as
/tmp, and do not point it at a tree whose contents another user can replace between runs.

Complete set of environment variables this suite CONFIGURES ITSELF FROM. Every one is
optional, and no other variable influences any decision this suite makes:
- AUTO_ACTIVATE_PLUGINS              default on; set to 0, false or no to skip activation
- TARGET_HOST                        default 127.0.0.1
- JSONRPC_PORT                       default 9998
- VCOMPONENT_PORT                    default 8080
- WPEFRAMEWORK_JSONRPC_URL           full JSON-RPC URL, highest precedence
- JSONRPC_URL                        legacy alias for the key above
- VCOMPONENT_API_URL                 full vComponent URL, highest precedence
- HDMICEC_CMD_BASE                   YAML command document root, as described above
- HDMICEC_TIMING_ENABLED             when set to any non-empty value, appends " time consumed:
                                     <elapsed>s" to the messages routed through
                                     utils.log_with_timing - each case's PASS line and the
                                     suite summary - and to nothing else. SuitManager.py's
                                     -t / --timing flag sets it for you. It affects logging
                                     only and takes no part in endpoint or path resolution
- Init_Devicelist_Populate_STRICT_MULTI   described under Initialization gates below
- Init_Devicelist_Populate_MIN_DEVICES    described under Initialization gates below

Four further variables are READ but configure nothing. PATH, HOME, LANG and LC_ALL form the
allow-list of names copied into the environment each curl child is started with: curl is run
with a minimal environment built from scratch rather than an inherited one, so that a proxy or
authentication variable in the caller's shell cannot silently retarget or decorate a request.
They are passed through unchanged when set, PATH falls back to /usr/bin:/bin when it is not,
and none of them takes any part in endpoint, path or gate resolution. PATH is also listed under
Prerequisites below, because python3 and curl have to be findable.

Troubleshooting:
- If you see connection errors, verify WPEFramework JSON-RPC and the vComponent API are reachable using the endpoint overrides above.
- If a test case reports "refused to post ...", the message names the exact path component at
  fault: the document sits outside the approved roots, a component is a symbolic link, the
  target is not a regular file, or it exceeds the 1 MiB cap. Correct the path or
  HDMICEC_CMD_BASE rather than relaxing the check.

Initialization gates:
Init_Devicelist_Populate runs once, before the first test case, and reads the two
environment variables below. Both are optional, and no other module in this suite reads
either of them. Both are VALIDATED: a value that is not recognised fails initialization and
names the variable, rather than being interpreted. That matters most for the strict gate -
reading an unrecognised value as "off" would silently select the lenient mode, so an operator
who believed strict checking was on would get a bootstrap-mode pass and nothing in the output
would say so.
- Init_Devicelist_Populate_STRICT_MULTI
  Accepted values, case-insensitive and surrounding whitespace ignored:
    on  -> 1, true, yes, on
    off -> 0, false, no, off, or unset, or empty (the default)
  When on: require every seeded peer to be present in the device list with its expected OSD
  name and a non-empty vendor ID, and require the device count to reach the number of seeded
  peers. Any shortfall fails initialization, and a failed initialization aborts the suite
  before the first test case runs.
  Any other value - "ture", "2", "enabled" - is a configuration error and fails.
- Init_Devicelist_Populate_MIN_DEVICES
  Minimum device count accepted in the default bootstrap mode. Default 1, and accepted only
  as a whole number within 1..<number of seeded peers>, which is 6. Below 1 the gate would
  assert nothing and an empty device list would pass; above the peer count it could never be
  satisfied, because this module seeds exactly that many peers. Either is a configuration
  error and fails.
  In bootstrap mode only the BOOTSTRAP PEER is mandatory - the YAMAHA audio system at CEC
  logical address 5, which Init_Devicelist_Populate seeds first and selects by address rather
  than by position, so reordering the seed table cannot silently move it. Every other shortfall
  is reported as a note rather than a failure. The audio system is the mandatory one because it
  is the peer the ARC, audio-status and short-audio-descriptor flows all address, and because
  it roots the sub-tree three of the other five peers hang from. In strict mode the minimum is
  the full peer count and this variable is not applied - but it is still validated, so a
  misspelling is reported where it was made instead of lying dormant until someone turns strict
  mode off.

Prerequisites:
- A QEMU target, or a real sink device, running WPEFramework with the org.rdk.HdmiCecSink
  plugin available for activation.
- A reachable WPEFramework JSON-RPC endpoint on port 9998.
- A reachable vComponent HTTP API on port 8080, with this suite's vcomponent_configurations/
  tree applied.
- python3 and curl on PATH.

The device under test is the sink: the television itself, which owns CEC logical address 0.
Every virtual CEC peer this suite configures is therefore a source-role device sitting
beneath that television. The six peers seeded before the first test case are a recording
device at 1 (DENON) and a second at 2 (LG), a tuner at 3 (SAMSUNG), a playback device at 4
(SONY), an audio system at 5 (YAMAHA) and a second playback device at 8 (PANASONIC). No
virtual television is created, and the device under test keeps its sink role throughout; it
is never reconfigured to stand in for a peer of its own.

Each peer's address is one its role can actually hold. CEC allots every device type a fixed
set of logical addresses - audio system 5; recording device 1, 2 and 9; tuner 3, 6, 7 and
10; playback device 4, 8 and 11 - so a peer declared as one role and announced at another
role's address describes a device that cannot exist, and strict verification could never be
satisfied by it. Those pools are also what fix each address: the emulator hands a device the
first free address in the pool for its declared type, so the tree in
vcomponent_configurations/commands/Device_Config_Add_Network.yaml determines all six
addresses and none of them is a choice this suite makes.

That tree is the single authoritative topology, and it declares SIX peers rather than one per
address:

  VTV (television, 0.0.0.0, three ports)
    HDMI input 0 -> SAMSUNG    Tuner            1.0.0.0   -> logical address 3
    HDMI input 1 -> YAMAHA     AudioSystem      2.0.0.0   -> logical address 5
                     port 1 -> DENON      RecordingDevice  2.1.0.0  -> 1
                     port 2 -> PANASONIC  PlaybackDevice   2.2.0.0  -> 8
                     port 3 -> LG         RecordingDevice  2.3.0.0  -> 2
                     port 4 -> reserved, left free for Device_Add.yaml
    HDMI input 2 -> SONY       PlaybackDevice   3.0.0.0   -> logical address 4  (active source)

Addresses 6, 7, 9, 10 and 11 are deliberately unoccupied, so a peer can be added without
removing one - which is what TCID27_Device_Add_Remove_Discovery_Flow relies on. Every peer's
three seed payload documents announce the address, physical address and device type this tree
produces for it, and Init_Devicelist_Populate.verify_topology_consistency() proves all three
sources still agree before the first frame is injected.

Status:
AUTHORED, NOT EXECUTED.

This suite is authored to full specification. It has not been run, on a device or anywhere
else, and no result from it is reported anywhere.

Static validation applied to the suite:
- python3 -m py_compile over every module in this directory and over every module under
  Testcases/.
- A suite-manager registration check of the tests list in SuitManager.py against the test
  case modules on disk under Testcases/, applied in both directions, so that neither a
  registered module missing from disk nor an unregistered module on disk goes unnoticed.
- SuitManager.load_test_cases(), which refuses a duplicate registration before importing
  anything - order is load-bearing here, and a case registered twice would run twice while
  restoring once - then imports every registered module, binds its run_test and refuses a
  non-callable cleanup, so a module that imports but publishes no entry point is a startup error
  rather than a silent skip. Run together with resolve_dependencies().
- A symbol-resolution sweep: every HdmiCECSink_Curl attribute and every name imported from
  utils by a test case is checked to exist in the module it is taken from. Python resolves a
  module attribute only when it is used, so an unresolvable name would otherwise survive import
  and surface as an AttributeError at device-execution time.
- YAML well-formedness parsing of every document under vcomponent_configurations/.
- The suite's own fixture-consistency validators, run directly. Five of them need no device, no
  emulator and no network - they read only files this suite owns - so they are the one part of
  this suite that IS executable here, and they are what catches a fixture set that has drifted
  out of agreement with itself before a device is ever booked:

    cd Tests/vDeviceTests
    python3 -c "import Init_Devicelist_Populate as i; \
      raise SystemExit(0 if (i.verify_seed_payload_consistency() \
                             and i.verify_topology_consistency()) else 1)"
    python3 -c "import sys; sys.path.insert(0, 'Testcases'); \
      from pathlib import Path; \
      import TCID33_Process_Yaml_Health_Check as t; \
      d = Path('vcomponent_configurations/commands').resolve(); \
      raise SystemExit(0 if (t._verify_fixture_inventory(d) \
                             and t._verify_device_fixture_inventory(d) \
                             and t._verify_response_table_opcodes(d)) else 1)"

  Both commands exit 0 on agreement and non-zero with the mismatch named. They are also reached
  from run_test() at Step 0a and at the head of the breadth sweep, but running them on their own
  is what makes them useful while L3 execution stays deferred: the drift they detect - a seed
  address that disagrees with its payload documents, a fixture with no declared status, an opcode
  the emulator cannot resolve - produces no symptom at run time. The frames register one address
  while the verification waits for another, or the exchange is accepted and never carried.

Prerequisites that were not available, and so were not used:
- A QEMU target.
- A WPEFramework JSON-RPC endpoint on port 9998.
- A vComponent API on port 8080.
- The Python RAFT packages (python_raft, ut-raft), which are deliberately not installed.

No service was started on port 9998 or on port 8080, no QEMU target was launched, and no
transport was stubbed in order to produce a result. Runtime validation of this suite is
deferred until a proper device or emulator environment is available.
