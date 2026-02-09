---
applyTo: "**/Module.cpp,**/Module.h"
---


### Module Name Convention

### Requirement

- Every plugin must define MODULE_NAME because Thunder uses MODULE_NAME to identify each plugin.
- Every plugin must also define the MODULE_NAME_DECLARATION() macro, which generates identifiers such as the module name string, SHA value, and version for the module, enabling the system to recognize and link it.
- The MODULE_NAME should always start with the prefix Plugin_.

### Example

1. In Module.h:

   ```cpp
   // Rest of the code
   #ifndef MODULE_NAME
   #define MODULE_NAME Plugin_IOController
   #endif
   // Rest of the code
   ```

2. In Module.cpp:

   ```cpp
   #include "Module.h"

   MODULE_NAME_DECLARATION(BUILD_REFERENCE)

   // Rest of the code
   ```