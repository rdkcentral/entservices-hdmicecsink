---
applyTo: "**/*.config,**/*.conf.in"
---

### Plugin Configuration

### Requirement

- Each plugin must define a <PluginName>.conf.in file that includes the following mandatory properties:

  - **autostart**: Indicates whether the plugin should start automatically when the framework boots. This should be set to false by default either through the CMake variable or directly in the .conf.in file.

  - **callsign**: A unique identifier used to reference the plugin within the framework. Every callsign must start with the prefix `org.rdk`, followed by the name of the corresponding RDK (ENT) service written in PascalCase. For example: `org.rdk.PersistentStore`, `org.rdk.HdcpProfile`, `org.rdk.DisplaySettings`.

  - **Custom properties**: Any additional configuration parameters required by the plugin. These are passed during activation via PluginHost::IShell::ConfigLine(). The following structural configuration elements are commonly defined:
    - startuporder - Specifies the order in which plugins are started, relative to others.
    - precondition - If these preconditions aren't met, the plugin stays in the Preconditions state and activates automatically once they are satisfied. It is recommended to define the preconditions if the plugin depends on other subsystems being active.
    - mode - Defines the execution mode of the plugin.

### Plugin Mode Determination

If the plugin's mode is set to OFF, it is treated as in-process.

If no mode is specified, the plugin defaults to in-process.

If the mode is explicitly set to LOCAL, the plugin runs out-of-process.

The plugin mode is configured in the plugin's CMakeLists.txt file.

- **locator** - Update with the name of the library (.so) that contains the actual plugin Implementation code.

### Example

<PluginName>.conf.in

```
precondition = ["Platform"]
callsign = "org.rdk.HdcpProfile"
autostart = "@PLUGIN_HDCPPROFILE_AUTOSTART@"
startuporder = "@PLUGIN_HDCPPROFILE_STARTUPORDER@"

configuration = JSON()
rootobject = JSON()

rootobject.add("mode", "@PLUGIN_HDCPPROFILE_MODE@")
rootobject.add("locator", "lib@PLUGIN_IMPLEMENTATION@.so")

configuration.add("root", rootobject)
```
