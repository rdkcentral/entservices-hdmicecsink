---
applyTo: "**/CMakeLists.txt"
---

### NAMESPACE Usage

### Requirement

All CMake targets, install paths, export sets, `find_package` and references must use the ${NAMESPACE} variable instead of hardcoded framework names (e.g., WPEFrameworkCore, WPEFrameworkPlugins).

### Correct Example

```cmake
set(MODULE_NAME ${NAMESPACE}${PLUGIN_NAME})

find_package(${NAMESPACE}Plugins REQUIRED)

find_package(${NAMESPACE}Definitions REQUIRED)

target_link_libraries(${MODULE_NAME} 
    PRIVATE
    CompileSettingsDebug::CompileSettingsDebug
    ${NAMESPACE}Plugins::${NAMESPACE}Plugins
    ${NAMESPACE}Definitions::${NAMESPACE}Definitions)
```


### Incorrect Example

```cmake
set(MODULE_NAME WPEFramework${PLUGIN_NAME})

find_package(WPEFrameworkPlugins REQUIRED)

find_package(WPEFrameworkDefinitions REQUIRED)

target_link_libraries(${MODULE_NAME} 
    PRIVATE
    CompileSettingsDebug::CompileSettingsDebug
    WPEFrameworkPlugins::WPEFrameworkPlugins
    WPEFrameworkDefinitions::WPEFrameworkDefinitions)
```

