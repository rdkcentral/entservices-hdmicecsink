---
applyTo: "**/**Implementation.cpp,**/**Implementation.h,**/**.cpp,**/**.h"
---

# Instruction Summary
  1. [Inter-Plugin Communication](#inter-plugin-communication)
  2. [On-Demand Plugin Interface Acquisition](#on-demand-plugin-interface-acquisition)

### Inter-Plugin Communication

### Requirement

Plugins should use COM-RPC (e.g., use QueryInterfaceByCallsign or QueryInterface) to access other plugins.

### Example

Telemetry Plugin accessing UserSettings(via COM-RPC) through the IShell Interface API **QueryInterfaceByCallsign()** exposed for each Plugin - (Refer https://github.com/rdkcentral/entservices-infra/blob/7988b8a719e594782f041309ce2d079cf6f52863/Telemetry/TelemetryImplementation.cpp#L160 )

```cpp
_userSettingsPlugin = _service->QueryInterfaceByCallsign<WPEFramework::Exchange::IUserSettings>(USERSETTINGS_CALLSIGN);
```

QueryInterface:

```cpp
_userSettingsPlugin = _service->QueryInterface<WPEFramework::Exchange::IUserSettings>();
```

Must not use JSON-RPC or LinkType for inter-plugin communication, as they introduce unnecessary overhead.

### Incorrect Example

LinkType:
```cpp
_telemetry = Core::ProxyType<JSONRPCLink>::Create(_T("org.rdk.telemetry"), _T(""), "token=" + token);
```

JSON-RPC:
```cpp
uint32_t ret = m_SystemPluginObj->Invoke<JsonObject, JsonObject>(THUNDER_RPC_TIMEOUT, _T("getFriendlyName"), params, Result);
```

Use COM-RPC for plugin event registration by passing a C++ callback interface pointer for low-latency communication. It is important to register for state change notifications to monitor the notifying plugin's lifecycle. This allows you to safely release the interface pointer upon deactivation and prevents accessing a non-existent service.

### Example

**1. Initialize the Listener and Start Monitoring**

```cpp
// Assuming you have a list of all target callsigns you want to monitor
const std::vector<std::string> MonitoredCallsigns = {
    "AudioTargetPlugin", 
    "NetworkTargetPlugin", 
    "InputTargetPlugin"
};

void Initialize(PluginHost::IShell* service) override {
    
    _service = service;
    _service->AddRef();
    
    // 1. Ask the framework to send state change notifications for all plugins to *this* object
    // This enables this plugin's StateChange() method to receive notifications about other plugins.

    // 2. Check if the target plugins are ALREADY running (First-Time check)
    for (const std::string& callsign : MonitoredCallsigns) {
        
        // Query the framework for the current instance of the target plugin
        PluginHost::IShell* target = _service->QueryInterfaceByCallsign<PluginHost::IShell>(callsign.c_str());
        
        if (target != nullptr) {
            // If the plugin is found and ACTIVATED, register immediately
            if (target->State() == PluginHost::IShell::ACTIVATED) {
                printf("LOG: Initial check found %s active. Registering events.\n", callsign.c_str());
                
                // Use the multi-target registration method
                RegisterWithTarget(callsign, target); 
            }
            
            // Release the IShell pointer obtained from QueryInterfaceByCallsign
            target->Release();
        }
    }
}
```

**2. Handle Activation (The Re-registration Step)**

Always use if (plugin->Callsign() == "YourTargetCallsign") as the initial gate in your state change method. This guarantees that all subsequent logs and re-registration/cleanup logic are executed only for the plugin you are actively monitoring.

```cpp
// StateChange() called when TargetPlugin comes online
void StateChange(PluginHost::IShell* plugin) override {

    const string& callsign = plugin->Callsign();
    
    // --- Step 1: Handle DEACTIVATED (Cleanup) ---
    if (plugin->State() == PluginHost::IShell::DEACTIVATED) {
        
        // Find if this specific callsign is in our map (if we were connected)
        auto it = _targetPlugins.find(callsign);
        
        if (it != _targetPlugins.end()) {
            printf("LOG: %s DEACTIVATED. Releasing interface.\n", callsign.c_str());
            
            // Unregister and Release the specific pointer for this callsign
            it->second->Unregister(this->QueryInterface<Exchange::IMyTargetPluginEvents>());
            it->second->Release();
            
            // Remove the entry from the map
            _targetPlugins.erase(it);
        }
    } 
    
    // --- Step 2: Handle ACTIVATED (Re-registration) ---
    else if (plugin->State() == PluginHost::IShell::ACTIVATED) {
        
        // Use a list/set of monitored callsigns (e.g., {"Audio", "Network", "Input"})
        // Assuming 'isMonitoredPlugin(callsign)' is a method that checks your watchlist
        if (isMonitoredPlugin(callsign)) {
            
            // Check if we are already connected (not found in the map)
            if (_targetPlugins.find(callsign) == _targetPlugins.end()) {
                
                printf("LOG: %s ACTIVATED. Establishing new COM-RPC link.\n", callsign.c_str());
                
                // Call the helper method to get the new pointer and register
                RegisterWithTarget(callsign, plugin);
            }
        }
    }
}
```

**3. COM-RPC Subscription**

```cpp
void RegisterWithTarget(const string& callsign, PluginHost::IShell* plugin) {

    // 1. Get the new, valid interface pointer
    Exchange::IMyTargetPlugin* newPtr = plugin->QueryInterface<Exchange::IMyTargetPlugin>();
    
    if (newPtr != nullptr) {
        // 2. Register the callback
        newPtr->Register(this->QueryInterface<Exchange::IMyTargetPluginEvents>());
        
        // 3. Store the new pointer in the map, indexed by callsign
        _targetPlugins[callsign] = newPtr; 
    }
}
```

If the notifying plugin supports only JSON-RPC, then use a specialized smart link type when subscribing to its events. This method allows the framework to efficiently handle plugin state change events.

### Example

```cpp
/**
 * @file Network.cpp
 * @brief Example implementation showing JSON-RPC SmartLinkType setup and event subscription.
 */

#define NETWORK_MANAGER_CALLSIGN "org.rdk.NetworkManager"

void Initialize(PluginHost::IShell* service) override {
    
    // ... other initialization code ...
    
    // This state check ensures the environment is ready for JSON-RPC access.
    if(PluginHost::IShell::state::ACTIVATED == state) 
    {
        Core::SystemInfo::SetEnvironment(_T("THUNDER_ACCESS"), (_T("127.0.0.1:9998")));
        
        // **SMART LINK TYPE INSTANTIATION:**
        // This creates an object that acts as a client proxy for the JSON-RPC-only service.
        // It handles sending JSON-RPC requests and receiving/deserializing JSON-RPC events.
        // The type arguments specify the JSON interface (org.rdk.Network) and the CallSign.
        m_networkmanager = make_shared<WPEFramework::JSONRPC::SmartLinkType<WPEFramework::Core::JSON::IElement> >(
            _T(NETWORK_MANAGER_CALLSIGN), 
            _T("org.rdk.Network"), 
            query
        );
        
        subscribeToEvents();
    }
}

void Network::subscribeToEvents(void) {
    uint32_t errCode = Core::ERROR_GENERAL;
    
    // Check if the smart link object was successfully created.
    if (m_networkmanager) {
        
        if (!m_subsIfaceStateChange) {
            
            // **SMART LINK EVENT SUBSCRIPTION:**
            // Using the SmartLinkType's Subscribe method, which internally constructs and 
            // sends the required JSON-RPC "Controller.1.subscribe" request to the target plugin.
            // It automatically registers the local C++ callback (&Network::onInterfaceStateChange) 
            // to receive and process the JSON event payload.
            errCode = m_networkmanager->Subscribe<JsonObject>(
                5000, 
                _T("onInterfaceStateChange"), 
                &Network::onInterfaceStateChange
            );
            
            if (Core::ERROR_NONE == errCode) {
                m_subsIfaceStateChange = true;
            } else {
                NMLOG_ERROR ("Subscribe to onInterfaceStateChange failed, errCode: %u", errCode);
            }
        }
    }
}
```

### On-Demand Plugin Interface Acquisition

### Requirement

When a Thunder plugin needs to communicate with another plugin (via JSON-RPC or COM-RPC), do not create and hold the other plugin's interface instance throughout the plugin lifecycle.
Instead, create the instance only when needed and release it immediately after use. If the other plugin gets deactivated, your stored interface becomes stale. Calling methods on a stale interface leads to undefined behavior, crashes, or deadlocks. Thunder does not automatically invalidate your pointer when the remote plugin goes down.

### Example

```cpp
void MyPlugin::setNumber() {
    ....
    WPEFramework::Exchange::IOtherPlugin* other = shell->QueryInterfaceByCallsign<WPEFramework::Exchange::IOtherPlugin>("org.rdk.OtherPlugin");

    if (other != nullptr) {
        other->PerformAction();
        other->Release(); // Release immediately after use
    }
}
```

### Incorrect Example

```cpp
void MyPlugin::Initialize() {
    _otherPlugin = shell->QueryInterfaceByCallsign<WPEFramework::Exchange::IOtherPlugin>();
}

void MyPlugin::Deinitialize() {
    if (_otherPlugin) {
        _otherPlugin->Release();
        _otherPlugin = nullptr;
    }
}

void MyPlugin::DoSomething() {
    _otherPlugin->PerformAction(); // Risky if other plugin is deactivated!
}
```
