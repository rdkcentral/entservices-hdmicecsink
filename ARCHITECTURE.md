# HDMI CEC Sink Plugin Architecture

## Overview

The HDMI CEC Sink plugin is a WPEFramework (Thunder) plugin that implements HDMI Consumer Electronics Control (CEC) protocol for TV/display devices. It enables the device to act as a CEC sink, allowing it to receive and respond to CEC commands from connected source devices like set-top boxes, media players, and gaming consoles.

## System Architecture

### Component Structure

```
┌─────────────────────────────────────────────────────────────┐
│                    WPEFramework Core                         │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
┌───────▼────────┐    ┌──────────▼───────────┐
│  HdmiCecSink   │    │  JSONRPC Interface   │
│  Plugin Shell  │◄───┤  (JHdmiCecSink)      │
└───────┬────────┘    └──────────────────────┘
        │
        │ RPC Communication
        │
┌───────▼─────────────────────────────────────────────────────┐
│         HdmiCecSinkImplementation (Out-of-Process)           │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌──────────────────┐  ┌─────────────┐  │
│  │ CEC Message    │  │ Device Manager   │  │ ARC Handler │  │
│  │ Processor      │  │                  │  │             │  │
│  └───────┬────────┘  └────────┬─────────┘  └──────┬──────┘  │
│          │                    │                   │          │
│  ┌───────▼────────────────────▼───────────────────▼──────┐  │
│  │         CEC Connection & Frame Listener               │  │
│  └───────────────────────────┬───────────────────────────┘  │
└──────────────────────────────┼──────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────────┐
        │                      │                          │
┌───────▼──────┐    ┌─────────▼─────────┐    ┌──────────▼────────┐
│  IARM Bus    │    │  Device Settings  │    │  CEC Hardware     │
│  (IPC)       │    │  (DS HAL)         │    │  Driver (libCEC)  │
└──────────────┘    └───────────────────┘    └───────────────────┘
```

## Core Components

### 1. Plugin Shell (HdmiCecSink)

- **Purpose**: Provides the WPEFramework plugin interface and JSONRPC communication endpoint
- **Key Responsibilities**:
  - Plugin lifecycle management (Initialize/Deinitialize)
  - JSONRPC method registration and dispatching
  - Event notification to subscribed clients
  - RPC connection management to out-of-process implementation
- **Location**: `plugin/HdmiCecSink.cpp`, `plugin/HdmiCecSink.h`

### 2. Implementation Layer (HdmiCecSinkImplementation)

- **Purpose**: Core business logic for CEC protocol handling (runs out-of-process for stability)
- **Key Responsibilities**:
  - CEC message encoding/decoding
  - Device discovery and tracking
  - Active source management
  - Audio Return Channel (ARC) control
  - System Audio Mode handling
  - Power state management
- **Location**: `plugin/HdmiCecSinkImplementation.cpp`, `plugin/HdmiCecSinkImplementation.h`

### 3. CEC Message Processing

#### HdmiCecSinkProcessor
Handles incoming CEC commands and generates appropriate responses:
- **Active Source Management**: Tracks which device is the active video source
- **Device Discovery**: Processes ReportPhysicalAddress, SetOSDName, CECVersion messages
- **Power Control**: Handles Standby and power status queries
- **OSD Management**: Responds to OSD name and language requests
- **Feature Negotiation**: Manages CEC version negotiation and feature support

#### HdmiCecSinkFrameListener
Low-level CEC frame reception:
- Receives raw CEC frames from hardware
- Passes frames to MessageDecoder for parsing
- Provides detailed frame logging for debugging

### 4. Device Management

**CECDeviceParams Class**: Maintains state for each connected CEC device:
- Device type (TV, Player, Recorder, Audio System, etc.)
- Physical and logical addresses
- CEC version support
- Vendor ID and OSD name
- Power status
- Active source status
- Feature support and limitations

**Device Tracking Features**:
- Automatic device discovery via broadcast messages
- Periodic device polling to detect disconnections
- Request retry mechanism with timeout handling
- Device chain management for HDMI topology

## Data Flow

### 1. Incoming CEC Command Flow

```
Hardware → libCEC Driver → Connection → FrameListener → 
MessageDecoder → Processor → Device Update → Event Notification → 
JSONRPC Event → Subscribed Clients
```

### 2. Outgoing CEC Command Flow

```
JSONRPC API Call → Plugin Shell → RPC → Implementation → 
MessageEncoder → Connection → libCEC Driver → Hardware
```

### 3. ARC (Audio Return Channel) Flow

```
Audio Device InitiateArc → Processor → ARC Port Validation → 
DS HAL (Audio Port Control) → Hardware Configuration → 
Event Notification (arcInitiationEvent)
```

## Key Interfaces and Dependencies

### External Dependencies

1. **WPEFramework Core**
   - Plugin infrastructure and lifecycle
   - JSONRPC communication framework
   - RPC for out-of-process execution

2. **Device Settings (DS HAL)**
   - HDMI port management
   - Audio output control
   - Display configuration
   - Used for: Physical address retrieval, ARC port control

3. **IARM Bus**
   - Inter-process communication
   - Power state notifications
   - System event handling

4. **libCEC (Hardware Abstraction)**
   - CEC frame transmission/reception
   - Hardware-level CEC protocol handling
   - Logical address allocation

### Internal Utilities (helpers/)

- **UtilsIarm.h**: IARM bus communication helpers
- **UtilsJsonRpc.h**: JSONRPC utility functions
- **UtilsLogging.h**: Logging macros and functions
- **UtilssyncPersistFile.h**: Persistent storage for settings
- **UtilsSearchRDKProfile.h**: Platform profile detection
- **UtilsgetRFCConfig.h**: RFC (Remote Feature Control) configuration
- **UtilsBIT.h**: Bit manipulation utilities
- **UtilsThreadRAII.h**: Thread management helpers

## Threading Model

- **Main Thread**: JSONRPC request handling and event dispatching
- **CEC Receiver Thread**: Monitors incoming CEC frames via FrameListener
- **Worker Threads**: Periodic device polling, power status updates, ARC state management
- **Thread Safety**: Mutex-protected device list and shared state

## Persistent Storage

The plugin maintains persistent settings in `/opt/persistent/ds/cecData_2.json`:
- CEC enabled/disabled state
- OSD name configuration
- Vendor ID
- One-time programming (OTP) enabled flag

## Integration Points

### Power Management Integration
- Subscribes to system power state changes via IPowerManager interface
- Sends CEC Standby commands on system power down
- Updates device power status on wake

### User Settings Integration
- Reads audio output settings (e.g., audio device connected status)
- Coordinates with user preferences for CEC behavior

### HDMI Input Integration
- Monitors HDMI input port changes
- Triggers active source updates on port switching
- Validates physical addresses against port topology

## Error Handling and Recovery

- **Request Retry Mechanism**: Up to 3 retries with 2-second timeout for critical requests
- **Feature Abort Handling**: Gracefully handles unsupported features with appropriate responses
- **Connection Recovery**: Monitors CEC bus connection and attempts reconnection on failure
- **Device Timeout**: Removes stale devices after prolonged non-responsiveness
- **Exception Safety**: Try-catch blocks around all CEC transmission to prevent crashes

## Performance Characteristics

- **Response Time**: Typical CEC command response < 100ms
- **Device Discovery**: Full device enumeration within 5-10 seconds of bus connection
- **Memory Footprint**: ~2-3 MB for implementation process
- **CPU Usage**: Minimal (<1%) during idle, brief spikes during CEC activity
- **Event Latency**: JSONRPC events dispatched within 50ms of CEC frame reception
