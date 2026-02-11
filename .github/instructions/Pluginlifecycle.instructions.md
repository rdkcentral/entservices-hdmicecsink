---
description: Guidelines for C++ files and header files that share the same name as their parent folder.
applyTo: "**/*.cpp,**/*.h"
---


### Mandatory Lifecycle Methods

Every plugin must implement:

- Initialize(IShell* service) → Called when the plugin is activated.

- Deinitialize(IShell* service) → Called when the plugin is deactivated.

### Initialization

### Requirement

- Initialize() must handle all setup logic; constructors should remain minimal.
- It must validate inputs and acquire necessary references.

### Example

```cpp
const string HdcpProfile::Initialize(PluginHost::IShell* service) {
    .....
    if (_hdcpProfile != nullptr) {
        ...
        Exchange::IConfiguration* configure = _hdcpProfile->QueryInterface<Exchange::IConfiguration>();
        ...
    }
    ....
}
```

-  The plugin should register its listener object twice:

  - Framework Service (_service): Use _service->Register(listener) to receive general plugin state change notifications (like ACTIVATED/DEACTIVATED).

    Example: _service->Register(&_hdcpProfileNotification);

  - Target Plugin Interface (_hdcpProfile): Use _hdcpProfile->Register(listener) to receive the plugin's specific custom events (e.g., onProfileChanged).This registration serves as the internal bridge that captures C++ events from the implementation, allowing the plugin to translate and broadcast them as JSON-RPC notifications to external subscribers.

    Example: _hdcpProfile->Register(&_hdcpProfileNotification);

- It must return a non-empty error message string on failure.

**Example:**

```cpp
const string HdcpProfile::Initialize(PluginHost::IShell* service) {
    ...
    message = _T("HdcpProfile could not be configured");
    ...
    message = _T("HdcpProfile implementation did not provide a configuration interface");
    ...
    message = _T("HdcpProfile plugin could not be initialized");
    ...
}
```

- Threads or async tasks should be started here if needed, with proper tracking.

**Example:**

```cpp
Core::hresult NativeJSImplementation::Initialize(string waylandDisplay)
{   
    std::cout << "initialize called on nativejs implementation " << std::endl;
    mRenderThread = std::thread([=](std::string waylandDisplay) {
        mNativeJSRenderer = std::make_shared<NativeJSRenderer>(waylandDisplay);
        mNativeJSRenderer->run();    
        std::cout << "After launch application execution ... " << std::endl;
        mNativeJSRenderer.reset();
    }, waylandDisplay);
    return (Core::ERROR_NONE);
}
```

- Before executing Initialize(), ensure all private member variables are in a reset state (either initialized by the constructor or cleared by a prior Deinitialize()). Validate this by asserting their default values.

**Example:**

```cpp
const string HdcpProfile::Initialize(PluginHost::IShell *service)
{
    ASSERT(_server == nullptr);
    ASSERT(_impl == nullptr);
    ASSERT(_connectionId == 0);
}
```

- If a plugin needs to keep the `IShell` pointer beyond the scope of `Initialize()` (for example, by storing it in a member variable to access other plugins via COM-RPC or JSON-RPC throughout the plugin's lifecycle), then it **must** call `AddRef()` on the service instance before storing it, to increment its reference count. Conversely, if the plugin does not store the `service` pointer beyond `Initialize()`, do not call `AddRef()` on the `IShell` instance.

**Example:**

```cpp
const string HdcpProfile::Initialize(PluginHost::IShell *service)
{
    ...
    _service = service;
    _service->AddRef();
    // _service will be used to access other plugins via COM-RPC or JSON-RPC in later methods.
    ...
}
```

- Only one Initialize() method must exist — avoid overloads or split logic.

### Deinitialize and Cleanup

### Requirement

- Deinitialize() must clean up all resources acquired during Initialize(). It must release resources in reverse order of initialization.
- Every pointer or instance must be checked for nullptr before cleanup.

**Example:**

```cpp
void HdcpProfile::Deinitialize(PluginHost::IShell* service) {
    ...
    if (_service != nullptr) {
        _service->Release();
        _service = nullptr;
    }
    ...
}
```

- All acquired interfaces must be explicitly Released().

**Example:**

```cpp
void HdcpProfile::Deinitialize(PluginHost::IShell* service) {
    ...
    if (_hdcpProfile != nullptr) {
        ....
        // Release interface
        RPC::IRemoteConnection* connection = service->RemoteConnection(_connectionId);
        connection->Terminate();
        connection->Release();
        ....
    }
    ...
}
```

- Unregister your listener from both the Target Plugin interface and the Framework Shell before releasing the pointers.

**Example:**

```cpp
void HdcpProfile::Deinitialize(PluginHost::IShell* service) {
    ...
    // 1. Unregister from the Target Plugin (stops custom events)
    if (_hdcpProfile != nullptr) {
        _hdcpProfile->Unregister(&_hdcpProfileNotification);
    }
    // 2. Unregister from the Framework Shell (stops state change events)
    if (_service != nullptr) {
        _service->Unregister(&_hdcpProfileNotification);
    }
    ...
}
```

- Remote connections must be terminated after releasing plugin references.

**Example:**

```cpp
void HdcpProfile::Deinitialize(PluginHost::IShell* service) {
    ...
    if (_hdcpProfile != nullptr) {
        ....
        if (nullptr != connection) {
            // Trigger the cleanup sequence for out-of-process code,
            // which ensures that unresponsive processes are terminated
            // if they do not stop gracefully.
            connection->Terminate();
            connection->Release();
        }
        ....
    }
}
```

- Threads must be joined or safely terminated.

**Example:**

```cpp
Core::hresult NativeJSImplementation::Deinitialize() {
    LOGINFO("deinitializing NativeJS process");
    if (mNativeJSRenderer) {
        mNativeJSRenderer->terminate();
        if (mRenderThread.joinable()) {
            mRenderThread.join();
        }
    }
    return (Core::ERROR_NONE);
}
```

- Internal state (e.g., _connectionId, _service) and private members should be reset to their default state.

**Example:**

```cpp
void HdcpProfile::Deinitialize(PluginHost::IShell* service) {
    ...
    if (connection != nullptr) {
        connection->Terminate();
        connection->Release();
    }
    ...
    if (_service != nullptr) {
        _service->Release();
        _service = nullptr;
    }
}
```

- If AddRef() was called on the IShell instance in Initialize(), then it should call Release() on the IShell instance to decrement its reference count.

**Example:**

```cpp
void HdcpProfile::Deinitialize(PluginHost::IShell* service) {
    ...
    if (_service != nullptr) {
        _service->Release();
        _service = nullptr;
    }
    ...
}
```

- All cleanup steps should be logged for traceability.

**Example:**

```cpp
void HdcpProfile::Deinitialize(PluginHost::IShell* service) {
    ...
    SYSLOG(Logging::Shutdown, (_T("HdcpProfile de-initialized")));
    ...
}
```


### Deactivated

Each plugin should implement the Deactivated method. In Deactivated, check if the remote connection ID matches your plugin's connection ID. If it matches, the plugin should submit a deactivation job to handle the out-of-process failure gracefully.

### Example

```cpp
void XCast::Deactivated(RPC::IRemoteConnection *connection)
{
    if (connection->Id() == _connectionId)
    {
        ASSERT(nullptr != _service);
        Core::IWorkerPool::Instance().Submit(PluginHost::IShell::Job::Create(_service, PluginHost::IShell::DEACTIVATED, PluginHost::IShell::FAILURE));
    }
}
```

