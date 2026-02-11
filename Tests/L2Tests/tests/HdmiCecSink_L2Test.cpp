/*
 * If not stated otherwise in this file or this component's LICENSE file the
 * following copyright and licenses apply:
 *
 * Copyright 2025 RDK Management
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#include "L2Tests.h"
#include "L2TestsMock.h"
#include <condition_variable>
#include <fstream>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <interfaces/IHdmiCecSink.h>
// Used to change the power state for onpowermodechanged event
#include <interfaces/IPowerManager.h>

#define EVNT_TIMEOUT (5000)
#define HDMICECSINK_CALLSIGN _T("org.rdk.HdmiCecSink.1")
#define HDMICECSINK_L2TEST_CALLSIGN _T("L2tests.1")

#define TEST_LOG(x, ...)                                                                                                                         \
    fprintf(stderr, "\033[1;32m[%s:%d](%s)<PID:%d><TID:%d>" x "\n\033[0m", __FILE__, __LINE__, __FUNCTION__, getpid(), gettid(), ##__VA_ARGS__); \
    fflush(stderr);

using ::testing::NiceMock;
using namespace WPEFramework;
using testing::StrictMock;
using HdmiCecSinkSuccess = WPEFramework::Exchange::IHdmiCecSink::HdmiCecSinkSuccess;
using HdmiCecSinkDevice = WPEFramework::Exchange::IHdmiCecSink::HdmiCecSinkDevices;
using HdmiCecSinkActivePath = WPEFramework::Exchange::IHdmiCecSink::HdmiCecSinkActivePath;
using IHdmiCecSinkDeviceListIterator = WPEFramework::Exchange::IHdmiCecSink::IHdmiCecSinkDeviceListIterator;
using IHdmiCecSinkActivePathIterator = WPEFramework::Exchange::IHdmiCecSink::IHdmiCecSinkActivePathIterator;
using PowerState = WPEFramework::Exchange::IPowerManager::PowerState;

namespace {
static void removeFile(const char* fileName)
{
    // Use sudo for protected files
    if (strcmp(fileName, "/etc/device.properties") == 0 || strcmp(fileName, "/opt/persistent/ds/cecData_2.json") == 0 || strcmp(fileName, "/opt/uimgr_settings.bin") == 0) {
        char cmd[256];
        snprintf(cmd, sizeof(cmd), "sudo rm -f %s", fileName);
        int ret = system(cmd);
        if (ret != 0) {
            printf("File %s failed to remove with sudo\n", fileName);
            perror("Error deleting file");
        } else {
            printf("File %s successfully deleted with sudo\n", fileName);
        }
    } else {
        if (std::remove(fileName) != 0) {
            printf("File %s failed to remove\n", fileName);
            perror("Error deleting file");
        } else {
            printf("File %s successfully deleted\n", fileName);
        }
    }
}

static void createFile(const char* fileName, const char* fileContent)
{
    std::ofstream fileContentStream(fileName);
    fileContentStream << fileContent;
    fileContentStream << "\n";
    fileContentStream.close();
}
}

// Event flags for different CEC events
typedef enum : uint32_t {
    ON_ACTIVE_SOURCE_CHANGE = 0x00000001,
    ON_DEVICE_ADDED = 0x00000002,
    ON_DEVICE_REMOVED = 0x00000004,
    ON_DEVICE_INFO_UPDATED = 0x00000008,
    ON_IMAGE_VIEW_ON = 0x00000010,
    ON_TEXT_VIEW_ON = 0x00000020,
    ON_INACTIVE_SOURCE = 0x00000040,
    ON_WAKEUP_FROM_STANDBY = 0x00000080,
    ARC_INITIATION_EVENT = 0x00000100,
    ARC_TERMINATION_EVENT = 0x00000200,
    REPORT_AUDIO_DEVICE_CONNECTED = 0x00000400,
    ON_REPORT_AUDIO_STATUS = 0x10000000, // Unique value to avoid overlap
    REPORT_FEATURE_ABORT = 0x20000000, // Unique value to avoid overlap
    REPORT_CEC_ENABLED = 0x40000000, // Unique value to avoid overlap
    ON_SET_SYSTEM_AUDIO_MODE = 0x80000000, // Unique value to avoid overlap
    SHORT_AUDIO_DESCRIPTOR = 0x00008000,
    STANDBY_MESSAGE_RECEIVED = 0x00010000,
    REPORT_AUDIO_DEVICE_POWER_STATUS = 0x00020000,
    HDMICECSINK_STATUS_INVALID = 0x00000000
} HdmiCecSinkL2test_async_events_t;

// Notification handler for HdmiCecSink events
class HdmiCecSinkNotificationHandler : public Exchange::IHdmiCecSink::INotification {
private:
    std::mutex m_mutex;
    std::condition_variable m_condition_variable;
    uint32_t m_event_signalled;

    BEGIN_INTERFACE_MAP(Notification)
    INTERFACE_ENTRY(Exchange::IHdmiCecSink::INotification)
    END_INTERFACE_MAP

public:
    HdmiCecSinkNotificationHandler() {}
    ~HdmiCecSinkNotificationHandler() {}

    // Event handlers with data storage for validation
    void ArcInitiationEvent(const string status) override
    {
        TEST_LOG("ArcInitiationEvent triggered with status: %s", status.c_str());
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ARC_INITIATION_EVENT;
        m_condition_variable.notify_one();
    }

    void ArcTerminationEvent(const string status) override
    {
        TEST_LOG("ArcTerminationEvent triggered with status: %s", status.c_str());
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ARC_TERMINATION_EVENT;
        m_condition_variable.notify_one();
    }

    void OnActiveSourceChange(const int logicalAddress, const string physicalAddress) override
    {
        TEST_LOG("OnActiveSourceChange event: logicalAddress=%d, physicalAddress=%s", logicalAddress, physicalAddress.c_str());
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ON_ACTIVE_SOURCE_CHANGE;
        m_condition_variable.notify_one();
    }

    void OnDeviceAdded(const int logicalAddress) override
    {
        TEST_LOG("OnDeviceAdded triggered - logicalAddress: %d", logicalAddress);
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ON_DEVICE_ADDED;
        m_condition_variable.notify_one();
    }

    void OnDeviceInfoUpdated(const int logicalAddress) override
    {
        TEST_LOG("OnDeviceInfoUpdated triggered - logicalAddress: %d", logicalAddress);
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ON_DEVICE_INFO_UPDATED;
        m_condition_variable.notify_one();
    }

    void OnDeviceRemoved(const int logicalAddress) override
    {
        TEST_LOG("OnDeviceRemoved triggered - logicalAddress: %d", logicalAddress);
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ON_DEVICE_REMOVED;
        m_condition_variable.notify_one();
    }

    void OnImageViewOnMsg(const int logicalAddress) override
    {
        TEST_LOG("OnImageViewOnMsg triggered - logicalAddress: %d", logicalAddress);
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ON_IMAGE_VIEW_ON;
        m_condition_variable.notify_one();
    }

    void OnInActiveSource(const int logicalAddress, const string physicalAddress) override
    {
        TEST_LOG("OnInActiveSource triggered - logicalAddress: %d, physicalAddress: %s",
            logicalAddress, physicalAddress.c_str());
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ON_INACTIVE_SOURCE;
        m_condition_variable.notify_one();
    }

    void OnTextViewOnMsg(const int logicalAddress) override
    {
        TEST_LOG("OnTextViewOnMsg triggered - logicalAddress: %d", logicalAddress);
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ON_TEXT_VIEW_ON;
        m_condition_variable.notify_one();
    }

    void OnWakeupFromStandby(const int logicalAddress) override
    {
        TEST_LOG("OnWakeupFromStandby triggered - logicalAddress: %d", logicalAddress);
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ON_WAKEUP_FROM_STANDBY;
        m_condition_variable.notify_one();
    }

    void ReportAudioDeviceConnectedStatus(const string status, const string audioDeviceConnected) override
    {
        TEST_LOG("ReportAudioDeviceConnectedStatus - status: %s, connected: %s",
            status.c_str(), audioDeviceConnected.c_str());
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= REPORT_AUDIO_DEVICE_CONNECTED;
        m_condition_variable.notify_one();
    }

    void ReportAudioStatusEvent(const int muteStatus, const int volumeLevel) override
    {
        TEST_LOG("ReportAudioStatusEvent - muteStatus: %d, volumeLevel: %d", muteStatus, volumeLevel);
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ON_REPORT_AUDIO_STATUS;
        m_condition_variable.notify_one();
    }

    void ReportFeatureAbortEvent(const int logicalAddress, const int opcode, const int FeatureAbortReason) override
    {
        TEST_LOG("ReportFeatureAbortEvent - logicalAddress: %d, opcode: %d, reason: %d",
            logicalAddress, opcode, FeatureAbortReason);
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= REPORT_FEATURE_ABORT;
        m_condition_variable.notify_one();
    }

    void ReportCecEnabledEvent(const string cecEnable) override
    {
        TEST_LOG("ReportCecEnabledEvent - cecEnable: %s", cecEnable.c_str());
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= REPORT_CEC_ENABLED;
        m_condition_variable.notify_one();
    }

    void SetSystemAudioModeEvent(const string audioMode) override
    {
        TEST_LOG("SetSystemAudioModeEvent - audioMode: %s", audioMode.c_str());
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= ON_SET_SYSTEM_AUDIO_MODE;
        m_condition_variable.notify_one();
    }

    void ShortAudiodescriptorEvent(const string& jsonresponse) override
    {
        TEST_LOG("ShortAudiodescriptorEvent - jsonResponse: %s", jsonresponse.c_str());
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= SHORT_AUDIO_DESCRIPTOR;
        m_condition_variable.notify_one();
    }

    void StandbyMessageReceived(const int logicalAddress) override
    {
        TEST_LOG("StandbyMessageReceived - logicalAddress: %d", logicalAddress);
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= STANDBY_MESSAGE_RECEIVED;
        m_condition_variable.notify_one();
    }

    void ReportAudioDevicePowerStatus(const int powerStatus) override
    {
        TEST_LOG("ReportAudioDevicePowerStatus - powerStatus: %d", powerStatus);
        std::unique_lock<std::mutex> lock(m_mutex);
        m_event_signalled |= REPORT_AUDIO_DEVICE_POWER_STATUS;
        m_condition_variable.notify_one();
    }

    uint32_t WaitForRequestStatus(uint32_t timeout_ms, HdmiCecSinkL2test_async_events_t expected_status)
    {
        std::unique_lock<std::mutex> lock(m_mutex);
        auto now = std::chrono::system_clock::now();
        std::chrono::milliseconds timeout(timeout_ms);
        uint32_t signalled = HDMICECSINK_STATUS_INVALID;

        while (!(expected_status & m_event_signalled)) {
            if (m_condition_variable.wait_until(lock, now + timeout) == std::cv_status::timeout) {
                TEST_LOG("Timeout waiting for request status event");
                break;
            }
        }
        signalled = m_event_signalled;
        return signalled;
    }
};

class AsyncHandlerMock_HdmiCecSink {
public:
    AsyncHandlerMock_HdmiCecSink()
    {
    }

    MOCK_METHOD(void, arcInitiationEvent, (const JsonObject& message));
    MOCK_METHOD(void, arcTerminationEvent, (const JsonObject& message));
    MOCK_METHOD(void, onActiveSourceChange, (const JsonObject& message));
    MOCK_METHOD(void, onDeviceAdded, (const JsonObject& message));
    MOCK_METHOD(void, onDeviceInfoUpdated, (const JsonObject& message));
    MOCK_METHOD(void, onDeviceRemoved, (const JsonObject& message));
    MOCK_METHOD(void, onImageViewOnMsg, (const JsonObject& message));
    MOCK_METHOD(void, onInActiveSource, (const JsonObject& message));
    MOCK_METHOD(void, onTextViewOnMsg, (const JsonObject& message));
    MOCK_METHOD(void, onWakeupFromStandby, (const JsonObject& message));
    MOCK_METHOD(void, reportAudioDeviceConnectedStatus, (const JsonObject& message));
    MOCK_METHOD(void, reportAudioStatusEvent, (const JsonObject& message));
    MOCK_METHOD(void, reportFeatureAbortEvent, (const JsonObject& message));
    MOCK_METHOD(void, reportCecEnabledEvent, (const JsonObject& message));
    MOCK_METHOD(void, setSystemAudioModeEvent, (const JsonObject& message));
    MOCK_METHOD(void, shortAudiodescriptorEvent, (const JsonObject& message));
    MOCK_METHOD(void, standbyMessageReceived, (const JsonObject& message));
    MOCK_METHOD(void, reportAudioDevicePowerStatus, (const JsonObject& message));
};

class HdmiCecSink_L2Test : public L2TestMocks {
protected:
    HdmiCecSink_L2Test();
    virtual ~HdmiCecSink_L2Test() override;

public:
    uint32_t CreateHdmiCecSinkInterfaceObject();
    uint32_t WaitForRequestStatus(uint32_t timeout_ms, HdmiCecSinkL2test_async_events_t expected_status);
    void arcInitiationEvent(const JsonObject& message);
    void arcTerminationEvent(const JsonObject& message);
    void onActiveSourceChange(const JsonObject& message);
    void onDeviceAdded(const JsonObject& message);
    void onDeviceInfoUpdated(const JsonObject& message);
    void onDeviceRemoved(const JsonObject& message);
    void onImageViewOnMsg(const JsonObject& message);
    void onInActiveSource(const JsonObject& message);
    void onTextViewOnMsg(const JsonObject& message);
    void reportAudioDeviceConnectedStatus(const JsonObject& message);
    void reportAudioStatusEvent(const JsonObject& message);
    void reportFeatureAbortEvent(const JsonObject& message);
    void reportCecEnabledEvent(const JsonObject& message);
    void setSystemAudioModeEvent(const JsonObject& message);
    void shortAudiodescriptorEvent(const JsonObject& message);
    void standbyMessageReceived(const JsonObject& message);
    void reportAudioDevicePowerStatus(const JsonObject& message);

protected:
    Exchange::IHdmiCecSink* m_cecSinkPlugin = nullptr;
    PluginHost::IShell* m_controller_cecSink = nullptr;
    Core::Sink<HdmiCecSinkNotificationHandler> m_notificationHandler;
    IARM_EventHandler_t dsHdmiEventHandler;
    IARM_EventHandler_t powerEventHandler = nullptr;
    FrameListener* registeredListener = nullptr;
    std::vector<FrameListener*> listeners;
    device::Host::IHdmiInEvents* g_registeredHdmiInListener = nullptr;

    Core::ProxyType<RPC::InvokeServerType<1, 0, 4>> HdmiCecSink_Engine;
    Core::ProxyType<RPC::CommunicatorClient> HdmiCecSink_Client;

private:
    std::mutex m_mutex;
    std::condition_variable m_condition_variable;
    uint32_t m_event_signalled = HDMICECSINK_STATUS_INVALID;
};

HdmiCecSink_L2Test::HdmiCecSink_L2Test()
    : L2TestMocks()
{
    uint32_t status = Core::ERROR_GENERAL;
    createFile("/etc/device.properties", "RDK_PROFILE=TV");
    createFile("/opt/persistent/ds/cecData_2.json", "0");
    createFile("/tmp/pwrmgr_restarted", "2");

    // Add sleep to ensure file is properly written to disk
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_DS_INIT())
        .WillOnce(::testing::Return(DEEPSLEEPMGR_SUCCESS));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_INIT())
        .WillRepeatedly(::testing::Return(PWRMGR_SUCCESS));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_API_SetWakeupSrc(::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return(PWRMGR_SUCCESS));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_API_GetPowerState(::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [](PWRMgr_PowerState_t* powerState) {
                *powerState = PWRMGR_POWERSTATE_ON; // Default to ON state
                return PWRMGR_SUCCESS;
            }));

    ON_CALL(*p_rfcApiImplMock, getRFCParameter(::testing::_, ::testing::_, ::testing::_))
        .WillByDefault(::testing::Invoke(
            [](char* pcCallerID, const char* pcParameterName, RFC_ParamData_t* pstParamData) {
                if (strcmp("RFC_DATA_ThermalProtection_POLL_INTERVAL", pcParameterName) == 0) {
                    strcpy(pstParamData->value, "2");
                    return WDMP_SUCCESS;
                } else if (strcmp("RFC_ENABLE_ThermalProtection", pcParameterName) == 0) {
                    strcpy(pstParamData->value, "true");
                    return WDMP_SUCCESS;
                } else if (strcmp("RFC_DATA_ThermalProtection_DEEPSLEEP_GRACE_INTERVAL", pcParameterName) == 0) {
                    strcpy(pstParamData->value, "6");
                    return WDMP_SUCCESS;
                } else if (strcmp("Device.DeviceInfo.X_RDKCENTRAL-COM_RFC.Feature.HdmiCecSink.CECVersion", pcParameterName) == 0) {
                    strncpy(pstParamData->value, "1.4", sizeof(pstParamData->value));
                    return WDMP_SUCCESS;
                } else {
                    /* The default threshold values will assign, if RFC call failed */
                    return WDMP_FAILURE;
                }
            }));

    EXPECT_CALL(*p_mfrMock, mfrSetTempThresholds(::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [](int high, int critical) {
                EXPECT_EQ(high, 100);
                EXPECT_EQ(critical, 110);
                return mfrERR_NONE;
            }));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_API_SetPowerState(::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [](PWRMgr_PowerState_t powerState) {
                // All tests are run without settings file
                // so default expected power state is ON
                return PWRMGR_SUCCESS;
            }));

    EXPECT_CALL(*p_mfrMock, mfrGetTemperature(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](mfrTemperatureState_t* curState, int* curTemperature, int* wifiTemperature) {
                *curTemperature = 90; // safe temperature
                *curState = (mfrTemperatureState_t)0;
                *wifiTemperature = 25;
                return mfrERR_NONE;
            }));

    ON_CALL(*p_connectionMock, poll(::testing::_, ::testing::_))
        .WillByDefault(::testing::Invoke(
            [&](const LogicalAddress& from, const Throw_e& doThrow) {
                throw CECNoAckException();
            }));

    EXPECT_CALL(*p_libCCECMock, getPhysicalAddress(::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](uint32_t* physAddress) {
                *physAddress = (uint32_t)0x12345678;
            }));

    ON_CALL(*p_messageEncoderMock, encode(::testing::Matcher<const DataBlock&>(::testing::_)))
        .WillByDefault(::testing::ReturnRef(CECFrame::getInstance()));
    ON_CALL(*p_messageEncoderMock, encode(::testing::Matcher<const UserControlPressed&>(::testing::_)))
        .WillByDefault(::testing::ReturnRef(CECFrame::getInstance()));

    ON_CALL(*p_iarmBusImplMock, IARM_Bus_RegisterEventHandler(::testing::_, ::testing::_, ::testing::_))
        .WillByDefault(::testing::Invoke(
            [&](const char* ownerName, IARM_EventId_t eventId, IARM_EventHandler_t handler) {
                if ((string(IARM_BUS_DSMGR_NAME) == string(ownerName)) && (eventId == IARM_BUS_DSMGR_EVENT_HDMI_IN_HOTPLUG)) {
                    EXPECT_TRUE(handler != nullptr);
                    dsHdmiEventHandler = handler;
                }
                return IARM_RESULT_SUCCESS;
            }));

    ON_CALL(*p_connectionMock, addFrameListener(::testing::_))
        .WillByDefault([this](FrameListener* listener) {
            printf("[TEST] addFrameListener called with address: %p\n", static_cast<void*>(listener));
            this->listeners.push_back(listener);
        });

    EXPECT_CALL(*p_hostImplMock, Register(::testing::A<device::Host::IHdmiInEvents*>()))
        .WillOnce(::testing::Invoke(
            [&](device::Host::IHdmiInEvents* listener) -> dsError_t {
                this->g_registeredHdmiInListener = listener;
                fprintf(stderr, "[TEST MOCK] Host::Register captured listener=%p\n", static_cast<void*>(listener));
                fflush(stderr);
                return static_cast<dsError_t>(0);
            }));

    ON_CALL(*p_connectionMock, open())
        .WillByDefault(::testing::Return());

    EXPECT_CALL(*p_hdmiInputImplMock, getNumberOfInputs())
        .WillRepeatedly(::testing::Return(3));

    ON_CALL(*p_hdmiInputImplMock, isPortConnected(::testing::_))
        .WillByDefault(::testing::Invoke(
            [](int8_t port) {
                return port == 1 ? true : false;
            }));

    EXPECT_CALL(*p_hdmiInputImplMock, getHDMIARCPortId(::testing::_))
        .Times(::testing::AtLeast(1))
        .WillRepeatedly(::testing::Invoke(
            [](int& portId) -> dsError_t {
                fprintf(stderr, "[TEST MOCK] getHDMIARCPortId called (expectation)\n");
                portId = 1;
                return static_cast<dsError_t>(0);
            }));

    /* Activate plugin in constructor */
    status = ActivateService("org.rdk.PowerManager");
    EXPECT_EQ(Core::ERROR_NONE, status);

    status = ActivateService("org.rdk.HdmiCecSink");
    EXPECT_EQ(Core::ERROR_NONE, status);
}

HdmiCecSink_L2Test::~HdmiCecSink_L2Test()
{
    uint32_t status = Core::ERROR_GENERAL;

    ON_CALL(*p_connectionMock, close())
        .WillByDefault(::testing::Return());

    sleep(5);

    // Deactivate services in reverse order
    status = DeactivateService("org.rdk.HdmiCecSink");
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_TERM())
        .WillOnce(::testing::Return(PWRMGR_SUCCESS));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_DS_TERM())
        .WillOnce(::testing::Return(DEEPSLEEPMGR_SUCCESS));

    status = DeactivateService("org.rdk.PowerManager");
    EXPECT_EQ(Core::ERROR_NONE, status);

    removeFile("/tmp/pwrmgr_restarted");
    removeFile("/opt/persistent/ds/cecData_2.json");
    removeFile("/opt/uimgr_settings.bin");
}

class HdmiCecSink_L2Test_STANDBY : public L2TestMocks {
protected:
    HdmiCecSink_L2Test_STANDBY();
    virtual ~HdmiCecSink_L2Test_STANDBY() override;

public:
    uint32_t CreateHdmiCecSinkInterfaceObject();
    uint32_t WaitForRequestStatus(uint32_t timeout_ms, HdmiCecSinkL2test_async_events_t expected_status);
    void onWakeupFromStandby(const JsonObject& message);

protected:
    Exchange::IHdmiCecSink* m_cecSinkPlugin = nullptr;
    PluginHost::IShell* m_controller_cecSink = nullptr;
    Core::Sink<HdmiCecSinkNotificationHandler> m_notificationHandler;
    IARM_EventHandler_t dsHdmiEventHandler;
    IARM_EventHandler_t powerEventHandler = nullptr;
    FrameListener* registeredListener = nullptr;
    std::vector<FrameListener*> listeners;

    Core::ProxyType<RPC::InvokeServerType<1, 0, 4>> HdmiCecSink_Engine;
    Core::ProxyType<RPC::CommunicatorClient> HdmiCecSink_Client;

private:
    std::mutex m_mutex;
    std::condition_variable m_condition_variable;
    uint32_t m_event_signalled = HDMICECSINK_STATUS_INVALID;
};

HdmiCecSink_L2Test_STANDBY::HdmiCecSink_L2Test_STANDBY()
    : L2TestMocks()
{
    uint32_t status = Core::ERROR_GENERAL;
    removeFile("/tmp/pwrmgr_restarted");
    createFile("/etc/device.properties", "RDK_PROFILE=TV");

    // Add sleep to ensure file is properly written to disk
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_DS_INIT())
        .WillOnce(::testing::Return(DEEPSLEEPMGR_SUCCESS));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_INIT())
        .WillRepeatedly(::testing::Return(PWRMGR_SUCCESS));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_API_SetWakeupSrc(::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return(PWRMGR_SUCCESS));

    ON_CALL(*p_rfcApiImplMock, getRFCParameter(::testing::_, ::testing::_, ::testing::_))
        .WillByDefault(::testing::Invoke(
            [](char* pcCallerID, const char* pcParameterName, RFC_ParamData_t* pstParamData) {
                if (strcmp("RFC_DATA_ThermalProtection_POLL_INTERVAL", pcParameterName) == 0) {
                    strcpy(pstParamData->value, "2");
                    return WDMP_SUCCESS;
                } else if (strcmp("RFC_ENABLE_ThermalProtection", pcParameterName) == 0) {
                    strcpy(pstParamData->value, "true");
                    return WDMP_SUCCESS;
                } else if (strcmp("RFC_DATA_ThermalProtection_DEEPSLEEP_GRACE_INTERVAL", pcParameterName) == 0) {
                    strcpy(pstParamData->value, "6");
                    return WDMP_SUCCESS;
                } else if (strcmp("Device.DeviceInfo.X_RDKCENTRAL-COM_RFC.Feature.HdmiCecSink.CECVersion", pcParameterName) == 0) {
                    strncpy(pstParamData->value, "1.4", sizeof(pstParamData->value));
                    return WDMP_SUCCESS;
                } else {
                    /* The default threshold values will assign, if RFC call failed */
                    return WDMP_FAILURE;
                }
            }));

    EXPECT_CALL(*p_mfrMock, mfrSetTempThresholds(::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [](int high, int critical) {
                EXPECT_EQ(high, 100);
                EXPECT_EQ(critical, 110);
                return mfrERR_NONE;
            }));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_API_GetPowerState(::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [](PWRMgr_PowerState_t* powerState) {
                *powerState = PWRMGR_POWERSTATE_OFF; // by default over boot up, return PowerState OFF
                return PWRMGR_SUCCESS;
            }));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_API_SetPowerState(::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [](PWRMgr_PowerState_t powerState) {
                // All tests are run without settings file
                // so default expected power state is ON
                return PWRMGR_SUCCESS;
            }));

    EXPECT_CALL(*p_mfrMock, mfrGetTemperature(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](mfrTemperatureState_t* curState, int* curTemperature, int* wifiTemperature) {
                *curTemperature = 90; // safe temperature
                *curState = (mfrTemperatureState_t)0;
                *wifiTemperature = 25;
                return mfrERR_NONE;
            }));

    ON_CALL(*p_connectionMock, poll(::testing::_, ::testing::_))
        .WillByDefault(::testing::Invoke(
            [&](const LogicalAddress& from, const Throw_e& doThrow) {
                throw CECNoAckException();
            }));

    EXPECT_CALL(*p_libCCECMock, getPhysicalAddress(::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](uint32_t* physAddress) {
                *physAddress = (uint32_t)0x12345678;
            }));

    ON_CALL(*p_messageEncoderMock, encode(::testing::Matcher<const DataBlock&>(::testing::_)))
        .WillByDefault(::testing::ReturnRef(CECFrame::getInstance()));
    ON_CALL(*p_messageEncoderMock, encode(::testing::Matcher<const UserControlPressed&>(::testing::_)))
        .WillByDefault(::testing::ReturnRef(CECFrame::getInstance()));

    ON_CALL(*p_iarmBusImplMock, IARM_Bus_RegisterEventHandler(::testing::_, ::testing::_, ::testing::_))
        .WillByDefault(::testing::Invoke(
            [&](const char* ownerName, IARM_EventId_t eventId, IARM_EventHandler_t handler) {
                if ((string(IARM_BUS_DSMGR_NAME) == string(ownerName)) && (eventId == IARM_BUS_DSMGR_EVENT_HDMI_IN_HOTPLUG)) {
                    EXPECT_TRUE(handler != nullptr);
                    dsHdmiEventHandler = handler;
                }
                return IARM_RESULT_SUCCESS;
            }));

    ON_CALL(*p_connectionMock, addFrameListener(::testing::_))
        .WillByDefault([this](FrameListener* listener) {
            printf("[TEST] addFrameListener called with address: %p\n", static_cast<void*>(listener));
            this->listeners.push_back(listener);
        });

    ON_CALL(*p_connectionMock, open())
        .WillByDefault(::testing::Return());

    EXPECT_CALL(*p_hdmiInputImplMock, getNumberOfInputs())
        .WillRepeatedly(::testing::Return(3));

    ON_CALL(*p_hdmiInputImplMock, isPortConnected(::testing::_))
        .WillByDefault(::testing::Invoke(
            [](int8_t port) {
                return port == 1 ? true : false;
            }));

    EXPECT_CALL(*p_hdmiInputImplMock, getHDMIARCPortId(::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [](int& portId) -> dsError_t {
                portId = 1;
                return static_cast<dsError_t>(0);
            }));

    /* Activate plugin in constructor */
    status = ActivateService("org.rdk.PowerManager");
    EXPECT_EQ(Core::ERROR_NONE, status);

    status = ActivateService("org.rdk.HdmiCecSink");
    EXPECT_EQ(Core::ERROR_NONE, status);
}

HdmiCecSink_L2Test_STANDBY::~HdmiCecSink_L2Test_STANDBY()
{
    uint32_t status = Core::ERROR_GENERAL;

    ON_CALL(*p_connectionMock, close())
        .WillByDefault(::testing::Return());

    sleep(5);

    // Deactivate services in reverse order
    status = DeactivateService("org.rdk.HdmiCecSink");
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_TERM())
        .WillOnce(::testing::Return(PWRMGR_SUCCESS));

    EXPECT_CALL(*p_powerManagerHalMock, PLAT_DS_TERM())
        .WillOnce(::testing::Return(DEEPSLEEPMGR_SUCCESS));

    status = DeactivateService("org.rdk.PowerManager");
    EXPECT_EQ(Core::ERROR_NONE, status);

    removeFile("/opt/uimgr_settings.bin");
}

void HdmiCecSink_L2Test::arcInitiationEvent(const JsonObject& message)
{
    TEST_LOG("arcInitiation event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("arcInitiation received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ARC_INITIATION_EVENT;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::arcTerminationEvent(const JsonObject& message)
{
    TEST_LOG("arcTermination event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("arcTermination received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ARC_TERMINATION_EVENT;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::onActiveSourceChange(const JsonObject& message)
{
    TEST_LOG("onActiveSourceChange event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("onActiveSourceChange received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ON_ACTIVE_SOURCE_CHANGE;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::onDeviceAdded(const JsonObject& message)
{
    TEST_LOG("onDeviceAdded event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("onDeviceAdded received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ON_DEVICE_ADDED;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::onDeviceInfoUpdated(const JsonObject& message)
{
    TEST_LOG("onDeviceInfoUpdated event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("onDeviceInfoUpdated received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ON_DEVICE_INFO_UPDATED;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::onDeviceRemoved(const JsonObject& message)
{
    TEST_LOG("onDeviceRemoved event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("onDeviceRemoved received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ON_DEVICE_REMOVED;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::onImageViewOnMsg(const JsonObject& message)
{
    TEST_LOG("onImageViewOnMsg event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("onImageViewOnMsg received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ON_IMAGE_VIEW_ON;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::onInActiveSource(const JsonObject& message)
{
    TEST_LOG("onInActiveSource event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("onInActiveSource received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ON_INACTIVE_SOURCE;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::onTextViewOnMsg(const JsonObject& message)
{
    TEST_LOG("onTextViewOnMsg event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("onTextViewOnMsg received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ON_TEXT_VIEW_ON;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test_STANDBY::onWakeupFromStandby(const JsonObject& message)
{
    TEST_LOG("onWakeupFromStandby event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("onWakeupFromStandby received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ON_WAKEUP_FROM_STANDBY;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::reportAudioDeviceConnectedStatus(const JsonObject& message)
{
    TEST_LOG("reportAudioDeviceConnectedStatus event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("reportAudioDeviceConnectedStatus received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= REPORT_AUDIO_DEVICE_CONNECTED;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::reportAudioStatusEvent(const JsonObject& message)
{
    TEST_LOG("reportAudioStatusEvent event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("reportAudioStatusEvent received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ON_REPORT_AUDIO_STATUS;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::reportFeatureAbortEvent(const JsonObject& message)
{
    TEST_LOG("reportFeatureAbortEvent event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("reportFeatureAbortEvent received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= REPORT_FEATURE_ABORT;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::reportCecEnabledEvent(const JsonObject& message)
{
    TEST_LOG("reportCecEnabledEvent event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("reportCecEnabledEvent received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= REPORT_CEC_ENABLED;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::setSystemAudioModeEvent(const JsonObject& message)
{
    TEST_LOG("setSystemAudioModeEvent event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("setSystemAudioModeEvent received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= ON_SET_SYSTEM_AUDIO_MODE;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::shortAudiodescriptorEvent(const JsonObject& message)
{
    TEST_LOG("shortAudiodescriptorEvent event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("shortAudiodescriptorEvent received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= SHORT_AUDIO_DESCRIPTOR;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::standbyMessageReceived(const JsonObject& message)
{
    TEST_LOG("standbyMessageReceived event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("standbyMessageReceived received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= STANDBY_MESSAGE_RECEIVED;
    m_condition_variable.notify_one();
}

void HdmiCecSink_L2Test::reportAudioDevicePowerStatus(const JsonObject& message)
{
    TEST_LOG("reportAudioDevicePowerStatus event triggered ***\n");
    std::unique_lock<std::mutex> lock(m_mutex);

    std::string str;
    message.ToString(str);

    TEST_LOG("reportAudioDevicePowerStatus received: %s\n", str.c_str());

    /* Notify the requester thread. */
    m_event_signalled |= REPORT_AUDIO_DEVICE_POWER_STATUS;
    m_condition_variable.notify_one();
}

uint32_t HdmiCecSink_L2Test::WaitForRequestStatus(uint32_t timeout_ms, HdmiCecSinkL2test_async_events_t expected_status)
{
    std::unique_lock<std::mutex> lock(m_mutex);
    auto now = std::chrono::system_clock::now();
    std::chrono::milliseconds timeout(timeout_ms);
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    while (!(expected_status & m_event_signalled)) {
        if (m_condition_variable.wait_until(lock, now + timeout) == std::cv_status::timeout) {
            TEST_LOG("Timeout waiting for request status event");
            break;
        }
    }
    signalled = m_event_signalled;
    return signalled;
}

uint32_t HdmiCecSink_L2Test_STANDBY::WaitForRequestStatus(uint32_t timeout_ms, HdmiCecSinkL2test_async_events_t expected_status)
{
    std::unique_lock<std::mutex> lock(m_mutex);
    auto now = std::chrono::system_clock::now();
    std::chrono::milliseconds timeout(timeout_ms);
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    while (!(expected_status & m_event_signalled)) {
        if (m_condition_variable.wait_until(lock, now + timeout) == std::cv_status::timeout) {
            TEST_LOG("Timeout waiting for request status event");
            break;
        }
    }
    signalled = m_event_signalled;
    return signalled;
}

MATCHER_P(MatchRequest, data, "")
{
    bool match = true;
    std::string expected;
    std::string actual;

    data.ToString(expected);
    arg.ToString(actual);
    TEST_LOG(" rec = %s, arg = %s", expected.c_str(), actual.c_str());
    EXPECT_STREQ(expected.c_str(), actual.c_str());

    return match;
}

uint32_t HdmiCecSink_L2Test::CreateHdmiCecSinkInterfaceObject()
{
    uint32_t return_value = Core::ERROR_GENERAL;

    TEST_LOG("Creating HdmiCecSink_Engine");
    HdmiCecSink_Engine = Core::ProxyType<RPC::InvokeServerType<1, 0, 4>>::Create();
    HdmiCecSink_Client = Core::ProxyType<RPC::CommunicatorClient>::Create(Core::NodeId("/tmp/communicator"), Core::ProxyType<Core::IIPCServer>(HdmiCecSink_Engine));

    TEST_LOG("Creating HdmiCecSink_Engine Announcements");
#if ((THUNDER_VERSION == 2) || ((THUNDER_VERSION == 4) && (THUNDER_VERSION_MINOR == 2)))
    HdmiCecSink_Engine->Announcements(mHdmiCecSink_Client->Announcement());
#endif
    if (!HdmiCecSink_Client.IsValid()) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        m_controller_cecSink = HdmiCecSink_Client->Open<PluginHost::IShell>(_T("org.rdk.HdmiCecSink"), ~0, 3000);
        if (m_controller_cecSink) {
            m_cecSinkPlugin = m_controller_cecSink->QueryInterface<Exchange::IHdmiCecSink>();
            return_value = Core::ERROR_NONE;
        }
    }
    return return_value;
}

// Test cases to validate Set and Get OSDName COMRPC
TEST_F(HdmiCecSink_L2Test, Set_And_Get_OSDName_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                string name = "TEST", osdname;
                bool success;
                status = m_cecSinkPlugin->SetOSDName(name, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                status = m_cecSinkPlugin->GetOSDName(osdname, success);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(success);
                EXPECT_EQ(osdname, "TEST");

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate Set and Get Enabled COMRPC
TEST_F(HdmiCecSink_L2Test, Set_And_Get_Enabled_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                bool success, enabled = false, response;
                status = m_cecSinkPlugin->SetEnabled(enabled, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                status = m_cecSinkPlugin->GetEnabled(response, success);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(success);
                EXPECT_FALSE(response);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate Set and Get VendorId COMRPC
TEST_F(HdmiCecSink_L2Test, Set_And_Get_VendorId_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                std::string vendorId = "0xAABBCC", getVendorId;
                bool success;

                status = m_cecSinkPlugin->SetVendorId(vendorId, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                status = m_cecSinkPlugin->GetVendorId(getVendorId, success);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(success);
                EXPECT_EQ(getVendorId, "aabbcc");

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate GetAudioDeviceConnectedStatus COMRPC
TEST_F(HdmiCecSink_L2Test, GetAudioDeviceConnectedStatus_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                bool connected, success;

                status = m_cecSinkPlugin->GetAudioDeviceConnectedStatus(connected, success);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_FALSE(connected);
                EXPECT_TRUE(success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate PrintDeviceList COMRPC
TEST_F(HdmiCecSink_L2Test, PrintDeviceList_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                bool printed, success;

                status = m_cecSinkPlugin->PrintDeviceList(printed, success);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(printed);
                EXPECT_TRUE(success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate RequestActiveSource COMRPC
TEST_F(HdmiCecSink_L2Test, RequestActiveSource_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;

                status = m_cecSinkPlugin->RequestActiveSource(result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate RequestShortAudioDescriptor COMRPC
TEST_F(HdmiCecSink_L2Test, RequestShortAudioDescriptor_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;

                status = m_cecSinkPlugin->RequestShortAudioDescriptor(result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SendAudioDevicePowerOnMessage COMRPC
TEST_F(HdmiCecSink_L2Test, SendAudioDevicePowerOnMessage_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;

                status = m_cecSinkPlugin->SendAudioDevicePowerOnMessage(result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SendGetAudioStatusMessage COMRPC
TEST_F(HdmiCecSink_L2Test, SendGetAudioStatusMessage_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;

                status = m_cecSinkPlugin->SendGetAudioStatusMessage(result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SendKeyPressEvent COMRPC
TEST_F(HdmiCecSink_L2Test, SendKeyPressEvent_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                uint32_t logicaladdr = 0x1, keycode = 0x41;

                status = m_cecSinkPlugin->SendKeyPressEvent(logicaladdr, keycode, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SendUserControlPressed COMRPC
TEST_F(HdmiCecSink_L2Test, SendUserControlPressed_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                uint32_t logicaladdr = 0x1, keycode = 0x41;

                status = m_cecSinkPlugin->SendUserControlPressed(logicaladdr, keycode, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SendUserControlReleased COMRPC
TEST_F(HdmiCecSink_L2Test, SendUserControlReleased_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                uint32_t logicaladdr = 0x1;

                status = m_cecSinkPlugin->SendUserControlReleased(logicaladdr, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SendStandbyMessage COMRPC
TEST_F(HdmiCecSink_L2Test, SendStandbyMessage_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;

                status = m_cecSinkPlugin->SendStandbyMessage(result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SetActivePath COMRPC
TEST_F(HdmiCecSink_L2Test, SetActivePath_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                string activepath = "2.0.0.0";

                status = m_cecSinkPlugin->SetActivePath(activepath, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SetActiveSource COMRPC
TEST_F(HdmiCecSink_L2Test, SetActiveSource_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;

                status = m_cecSinkPlugin->SetActiveSource(result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SetMenuLanguage COMRPC
TEST_F(HdmiCecSink_L2Test, SetMenuLanguage_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                string lang = "eng";

                EXPECT_CALL(*p_connectionMock, sendTo(::testing::_, ::testing::_, ::testing::_))
                    .WillRepeatedly(::testing::Invoke(
                        [&](const LogicalAddress& to, const CECFrame& frame, int timeout) {
                            EXPECT_LE(to.toInt(), LogicalAddress::BROADCAST);
                            EXPECT_GT(timeout, 0);
                        }));

                status = m_cecSinkPlugin->SetMenuLanguage(lang, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SetRoutingChange COMRPC
TEST_F(HdmiCecSink_L2Test, SetRoutingChange_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                string oldport = "HDMI0", newport = "HDMI1";

                std::this_thread::sleep_for(std::chrono::seconds(30));

                status = m_cecSinkPlugin->SetRoutingChange(oldport, newport, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SetupARCRouting COMRPC
TEST_F(HdmiCecSink_L2Test, SetupARCRouting_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                bool enabled = true;

                EXPECT_CALL(*p_connectionMock, sendTo(testing::_, testing::_, testing::_)).Times(testing::AtLeast(1));

                status = m_cecSinkPlugin->SetupARCRouting(enabled, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate SetLatencyInfo COMRPC
TEST_F(HdmiCecSink_L2Test, SetLatencyInfo_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;
                string videolatency = "2", lowLatencyMode = "1", audioOutputCompensated = "1", audioOutputDelay = "20";

                EXPECT_CALL(*p_connectionMock, sendTo(testing::_, testing::_, testing::_))
                    .Times(testing::AtLeast(1));

                status = m_cecSinkPlugin->SetLatencyInfo(videolatency, lowLatencyMode, audioOutputCompensated, audioOutputDelay, result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate RequestAudioDevicePowerStatus COMRPC
TEST_F(HdmiCecSink_L2Test, RequestAudioDevicePowerStatus_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                Core::hresult status = Core::ERROR_GENERAL;
                HdmiCecSinkSuccess result;

                status = m_cecSinkPlugin->RequestAudioDevicePowerStatus(result);
                EXPECT_EQ(status, Core::ERROR_NONE);
                if (status != Core::ERROR_NONE) {
                    std::string errorMsg = "COM-RPC returned error " + std::to_string(status) + " (" + std::string(Core::ErrorToString(status)) + ")";
                    TEST_LOG("Err: %s", errorMsg.c_str());
                }
                EXPECT_TRUE(result.success);

                m_cecSinkPlugin->Release();
            } else {
                TEST_LOG("m_cecSinkPlugin is NULL");
            }
            m_controller_cecSink->Release();
        } else {
            TEST_LOG("m_controller_cecSink is NULL");
        }
    }
}

// Test cases to validate GetActiveSource COMRPC
TEST_F(HdmiCecSink_L2Test, GetActiveSource_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                // Call GetActiveSource
                bool available;
                uint8_t logicalAddress;
                string physicalAddress, deviceType, cecVersion, osdname, vendID, powerStatus, port;
                bool success;

                auto result = m_cecSinkPlugin->GetActiveSource(available, logicalAddress,
                    physicalAddress, deviceType, cecVersion, osdname, vendID,
                    powerStatus, port, success);

                // Verify results
                EXPECT_EQ(result, Core::ERROR_NONE);
                EXPECT_TRUE(success);

                m_cecSinkPlugin->Release();
            }
            m_controller_cecSink->Release();
        }
    }
}

// Test cases to validate GetActiveRoute COMRPC
TEST_F(HdmiCecSink_L2Test, GetActiveRoute_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                // Call GetActiveRoute
                bool available, success;
                uint8_t length;
                IHdmiCecSinkActivePathIterator* list;
                string Activeroute;

                auto result = m_cecSinkPlugin->GetActiveRoute(available, length, list, Activeroute, success);

                // Verify results
                EXPECT_EQ(result, Core::ERROR_NONE);
                EXPECT_TRUE(success);
                EXPECT_FALSE(available);

                m_cecSinkPlugin->Release();
            }
            m_controller_cecSink->Release();
        }
    }
}

// Test cases to validate GetDeviceList COMRPC
TEST_F(HdmiCecSink_L2Test, GetDeviceList_COMRPC)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {

                // Call GetDeviceList
                bool success;
                uint32_t numberofdevices;
                IHdmiCecSinkDeviceListIterator* devicelist;

                auto result = m_cecSinkPlugin->GetDeviceList(numberofdevices, devicelist, success);

                // Verify results
                EXPECT_EQ(result, Core::ERROR_NONE);
                EXPECT_TRUE(success);

                m_cecSinkPlugin->Release();
            }
            m_controller_cecSink->Release();
        }
    }
}

// Test cases to validate Hdmihotplug COMRPC
TEST_F(HdmiCecSink_L2Test, Hdmihotplug_COMRPC_PlugIn_and_PlugOut)
{
    if (CreateHdmiCecSinkInterfaceObject() != Core::ERROR_NONE) {
        TEST_LOG("Invalid HdmiCecSink_Client");
    } else {
        EXPECT_TRUE(m_controller_cecSink != nullptr);
        if (m_controller_cecSink) {
            EXPECT_TRUE(m_cecSinkPlugin != nullptr);
            if (m_cecSinkPlugin) {
                ASSERT_NE(g_registeredHdmiInListener, nullptr);
                g_registeredHdmiInListener->OnHdmiInEventHotPlug(dsHDMI_IN_PORT_1, true);
                std::this_thread::sleep_for(std::chrono::seconds(2));
                g_registeredHdmiInListener->OnHdmiInEventHotPlug(dsHDMI_IN_PORT_1, false);
                m_cecSinkPlugin->Release();
            }
            m_controller_cecSink->Release();
        }
    }
}

// Test cases to validate Set and Get OSDName using JSONRPC
TEST_F(HdmiCecSink_L2Test, Set_And_Get_OSDName_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    // Test SetOSDName
    params["name"] = "TEST";
    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "setOSDName", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    // Verify with GetOSDName
    params.Clear();
    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "getOSDName", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("name"));
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
    EXPECT_STREQ("TEST", result["name"].String().c_str());
}

// Test cases to validate GetVendorId using JSONRPC
TEST_F(HdmiCecSink_L2Test, GetAudioDeviceConnectedStatus_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "getAudioDeviceConnectedStatus", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("connected"));
    EXPECT_FALSE(result["connected"].Boolean());
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate PrintDeviceList using JSONRPC
TEST_F(HdmiCecSink_L2Test, PrintDeviceList_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "printDeviceList", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("printed"));
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
    EXPECT_TRUE(result["printed"].Boolean());
}

// Test cases to validate PrintDeviceList using JSONRPC
TEST_F(HdmiCecSink_L2Test, RequestActiveSource_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    std::string message;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result, expected_status;

    /* Register for onDeviceAdded event. */
    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("onDeviceAdded"),
        &AsyncHandlerMock_HdmiCecSink::onDeviceAdded,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    message = "{\"logicalAddress\":1}";
    expected_status.FromString(message);
    EXPECT_CALL(async_handler, onDeviceAdded(testing::_))
        .WillRepeatedly(Invoke(this, &HdmiCecSink_L2Test::onDeviceAdded));

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "requestActiveSource", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_DEVICE_ADDED);
    EXPECT_TRUE(signalled & ON_DEVICE_ADDED);

    /*Unregister for event*/
    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("onDeviceAdded"));
}

// Test cases to validate RequestShortAudioDescriptor using JSONRPC
TEST_F(HdmiCecSink_L2Test, RequestShortAudioDescriptor_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "requestShortAudioDescriptor", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SendAudioDevicePowerOnMessage using JSONRPC
TEST_F(HdmiCecSink_L2Test, SendKeyPressEvent_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    params["logicalAddress"] = 4;
    params["keyCode"] = 65;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 0;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 1;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 2;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 3;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 4;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 9;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 13;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 32;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 33;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 34;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 35;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 36;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 37;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 38;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 39;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 40;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 41;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 66;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 67;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 101;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 102;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 108;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 109;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendKeyPressEvent", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SendUserControlPressed using JSONRPC
TEST_F(HdmiCecSink_L2Test, SendUserControlPressed_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    params["logicalAddress"] = 4;
    params["keyCode"] = 65;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 0;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 1;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 2;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 3;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 4;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 9;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 13;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 32;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 33;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 34;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 35;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 36;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 37;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 38;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 39;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 40;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 41;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 66;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 67;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 101;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 102;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 108;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    params.Clear();
    params["logicalAddress"] = 4;
    params["keyCode"] = 109;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlPressed", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SendUserControlReleased using JSONRPC
TEST_F(HdmiCecSink_L2Test, SendUserControlReleased_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    params["logicalAddress"] = 4;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendUserControlReleased", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SetActivePath using JSONRPC
TEST_F(HdmiCecSink_L2Test, SetActivePath_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    params["activePath"] = "2.0.0.0";

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "setActivePath", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
}

// Test cases to validate SetActiveSource using JSONRPC
TEST_F(HdmiCecSink_L2Test, SetActiveSource_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "setActiveSource", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SetActiveSource using JSONRPC
TEST_F(HdmiCecSink_L2Test, SetMenuLanguage_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    params["language"] = "chi";

    EXPECT_CALL(*p_connectionMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](const LogicalAddress& to, const CECFrame& frame, int timeout) {
                EXPECT_LE(to.toInt(), LogicalAddress::BROADCAST);
                EXPECT_GT(timeout, 0);
            }));

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "setMenuLanguage", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SetRoutingChange using JSONRPC
TEST_F(HdmiCecSink_L2Test, SetRoutingChange_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    params["oldPort"] = "HDMI0";
    params["newPort"] = "TV";

    std::this_thread::sleep_for(std::chrono::seconds(30));

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "setRoutingChange", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SetupARCRouting using JSONRPC
TEST_F(HdmiCecSink_L2Test, SetupARCRouting_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    params["enabled"] = true;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "setupARCRouting", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SetLatencyInfo using JSONRPC
TEST_F(HdmiCecSink_L2Test, SetLatencyInfo_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    params["videoLatency"] = "2";
    params["lowLatencyMode"] = "1";
    params["audioOutputCompensated"] = "1";
    params["audioOutputDelay"] = "20";

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "setLatencyInfo", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate RequestAudioDevicePowerStatus using JSONRPC
TEST_F(HdmiCecSink_L2Test, RequestAudioDevicePowerStatus_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "requestAudioDevicePowerStatus", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate GetActiveSource using JSONRPC
TEST_F(HdmiCecSink_L2Test, GetActiveSource_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "getActiveSource", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate GetActiveRoute using JSONRPC
TEST_F(HdmiCecSink_L2Test, GetActiveRoute_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "getActiveRoute", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate GetDeviceList using JSONRPC
TEST_F(HdmiCecSink_L2Test, GetDeviceList_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "getDeviceList", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SetVendorId and GetVendorId using JSONRPC
TEST_F(HdmiCecSink_L2Test, Set_And_Get_VendorId_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    // Test SetVendorId
    params["vendorid"] = "0xAABBCC";
    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "setVendorId", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    // Verify with GetVendorId
    params.Clear();
    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "getVendorId", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("vendorid"));
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
    EXPECT_STREQ("aabbcc", result["vendorid"].String().c_str());
}

// Test cases to validate SetEnabled and GetEnabled using JSONRPC
TEST_F(HdmiCecSink_L2Test, Set_And_Get_Enabled_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result, expected_status;
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    std::string message;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    /* Register for reportCecEnabledEvent event. */
    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("reportCecEnabledEvent"),
        &AsyncHandlerMock_HdmiCecSink::reportCecEnabledEvent,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    message = "{\"cecEnable\":false}";
    expected_status.FromString(message);
    EXPECT_CALL(async_handler, reportCecEnabledEvent(testing::_))
        .WillRepeatedly(Invoke(this, &HdmiCecSink_L2Test::reportCecEnabledEvent));

    // Test SetEnabled
    params["enabled"] = false;
    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "setEnabled", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    // Verify with GetEnabled
    params.Clear();
    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "getEnabled", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("enabled"));
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
    EXPECT_FALSE(result["enabled"].Boolean());

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, REPORT_CEC_ENABLED);
    EXPECT_TRUE(signalled & REPORT_CEC_ENABLED);

    /*Unregister for event*/
    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("reportCecEnabledEvent"));
}

// Test cases to validate SendAudioDevicePowerOnMessage using JSONRPC
TEST_F(HdmiCecSink_L2Test, SendAudioDevicePowerOnMessage_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    EXPECT_CALL(*p_connectionMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](const LogicalAddress& to, const CECFrame& frame, int timeout) {
                EXPECT_GT(timeout, 0);
            }));

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendAudioDevicePowerOnMessage", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SendGetAudioStatusMessage using JSONRPC
TEST_F(HdmiCecSink_L2Test, SendGetAudioStatusMessage_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    EXPECT_CALL(*p_connectionMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](const LogicalAddress& to, const CECFrame& frame, int timeout) {
                EXPECT_GT(timeout, 0);
            }));

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendGetAudioStatusMessage", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Test cases to validate SendStandbyMessage using JSONRPC
TEST_F(HdmiCecSink_L2Test, SendStandbyMessage_JSONRPC)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    uint32_t status = Core::ERROR_GENERAL;
    JsonObject params, result;

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "sendStandbyMessage", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());
}

// Inject CEC frames and verify onActiveSourceChange events
TEST_F(HdmiCecSink_L2Test, InjectActiveSourceFrameAndVerifyEvent)
{
    // Set up the JSON-RPC client and mock event handler
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    // Subscribe to the 'onActiveSourceChange' event and set an expectation
    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("onActiveSourceChange"),
        &AsyncHandlerMock_HdmiCecSink::onActiveSourceChange,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    // We expect this event to be fired with logicalAddress 1 and physicalAddress "1.0.0.0"
    EXPECT_CALL(async_handler, onActiveSourceChange(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::onActiveSourceChange));

    // Ensure the plugin has registered its listener
    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured. The plugin might not have initialized correctly.";

    // Create the fake CEC frame for <Active Source>
    // Header: From Playback Device 1 (LA=4) to Broadcast (LA=15)
    // Opcode: 0x82 (Active Source)
    // Operands: 0x10, 0x00 (Physical Address 1.0.0.0)
    uint8_t buffer[] = { 0x4F, 0x82, 0x10, 0x00 };
    CECFrame activeSourceFrame(buffer, sizeof(buffer));

    // Inject the frame by calling notify() on the captured listener(s)
    for (auto* listener : listeners) {
        if (listener) {
            // This call simulates the ccec library delivering a frame to the plugin
            listener->notify(activeSourceFrame);
        }
    }

    // Wait for the event to be signalled by the mock handler
    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_ACTIVE_SOURCE_CHANGE);
    EXPECT_TRUE(signalled & ON_ACTIVE_SOURCE_CHANGE);

    // Clean up the subscription
    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("onActiveSourceChange"));
}

// Inject InActiveSource frames and verify onInActiveSource events
TEST_F(HdmiCecSink_L2Test, InjectInactiveSourceFramesAndVerifyEvents)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("onInActiveSource"),
        &AsyncHandlerMock_HdmiCecSink::onInActiveSource,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, onInActiveSource(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::onInActiveSource));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured. The plugin might not have initialized correctly.";

    // Inject <Inactive Source>
    uint8_t inactiveSource[] = { 0x40, 0x9D, 0x10, 0x00 };
    CECFrame inactiveSourceFrame(inactiveSource, sizeof(inactiveSource));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(inactiveSourceFrame);
    }

    // Wait for both events
    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_INACTIVE_SOURCE);
    EXPECT_TRUE(signalled & ON_INACTIVE_SOURCE);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("onInActiveSource"));
}

// InActiveSource Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectInactiveSourceBroadcastIgnoreCase)
{
    // Inject <Inactive Source>
    uint8_t inactiveSource[] = { 0x4F, 0x9D, 0x10, 0x00 };
    CECFrame inactiveSourceFrame(inactiveSource, sizeof(inactiveSource));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(inactiveSourceFrame);
    }
}

// Inject ImageViewOn frame and verify onImageViewOnMsg event
// Disabled due to implementation issue.
TEST_F(HdmiCecSink_L2Test, DISABLED_InjectImageViewOnFrameAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("onImageViewOnMsg"),
        &AsyncHandlerMock_HdmiCecSink::onImageViewOnMsg,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, onImageViewOnMsg(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::onImageViewOnMsg));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured. The plugin might not have initialized correctly.";

    // Header: From Playback Device (4) to TV (0), Opcode: 0x04 (Image View On)
    uint8_t buffer[] = { 0x40, 0x04 };
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_IMAGE_VIEW_ON);
    EXPECT_TRUE(signalled & ON_IMAGE_VIEW_ON);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("onImageViewOnMsg"));
}

// Inject TextViewOn frame and verify onTextViewOnMsg event
TEST_F(HdmiCecSink_L2Test, InjectTextViewOnFrameAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("onTextViewOnMsg"),
        &AsyncHandlerMock_HdmiCecSink::onTextViewOnMsg,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, onTextViewOnMsg(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::onTextViewOnMsg));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured. The plugin might not have initialized correctly.";

    // Header: From TV (0) to Playback Device 1 (4), Opcode: 0x0D (Text View On)
    uint8_t buffer[] = { 0x40, 0x0D };
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_TEXT_VIEW_ON);
    EXPECT_TRUE(signalled & ON_TEXT_VIEW_ON);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("onTextViewOnMsg"));
}

// TextViewOn Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectTextViewOnFrameBroadcastIgnoreCase)
{
    uint8_t buffer[] = { 0x4F, 0x0D };
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }
}

// Inject DeviceAdded frame and verify onDeviceAdded event
TEST_F(HdmiCecSink_L2Test, InjectDeviceAddedFrameAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("onDeviceAdded"),
        &AsyncHandlerMock_HdmiCecSink::onDeviceAdded,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, onDeviceAdded(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::onDeviceAdded));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured.";

    // Report Physical Address - announces a new device
    // Header: From device 4 to broadcast, Opcode: 0x84 (Report Physical Address),
    // Physical Address: 0x20, 0x00, Device Type: 0x04 (Playback Device)
    uint8_t buffer[] = { 0x4F, 0x84, 0x20, 0x00, 0x04 };
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_DEVICE_ADDED);
    EXPECT_TRUE(signalled & ON_DEVICE_ADDED);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("onDeviceAdded"));
}

// Inject DeviceAdded frame and verify reportAudioDeviceConnectedStatus event
TEST_F(HdmiCecSink_L2Test, InjectDeviceAddedFrameAndVerifyEvent_ReportAudioDeviceConnectedStatus)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("reportAudioDeviceConnectedStatus"),
        &AsyncHandlerMock_HdmiCecSink::reportAudioDeviceConnectedStatus,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, reportAudioDeviceConnectedStatus(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::reportAudioDeviceConnectedStatus));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured.";

    // Report Physical Address - announces a new device
    // Header: From device 5 to broadcast, Opcode: 0x84 (Report Physical Address),
    // Physical Address: 0x20, 0x00, Device Type: 0x04 (Playback Device)
    uint8_t buffer[] = { 0x5F, 0x84, 0x20, 0x00, 0x04 };
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, REPORT_AUDIO_DEVICE_CONNECTED);
    EXPECT_TRUE(signalled & REPORT_AUDIO_DEVICE_CONNECTED);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("reportAudioDeviceConnectedStatus"));
}

// Report Audio Status
TEST_F(HdmiCecSink_L2Test, InjectReportAudioStatusAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("reportAudioStatusEvent"),
        &AsyncHandlerMock_HdmiCecSink::reportAudioStatusEvent,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, reportAudioStatusEvent(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::reportAudioStatusEvent));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured.";

    // Report Audio Status from Audio System (5) to TV (0)
    // Header: 0x50, Opcode: 0x7A (Report Audio Status), Status: 0x50 (Volume 80, not muted)
    uint8_t buffer[] = { 0x50, 0x7A, 0x50 };
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_REPORT_AUDIO_STATUS);
    EXPECT_TRUE(signalled & ON_REPORT_AUDIO_STATUS);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("reportAudioStatusEvent"));
}

// Report Audio Status Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectReportAudioStatusAndVerifyEventBroadcastIgnoreTest)
{
    // Header: 0x50, Opcode: 0x7A (Report Audio Status), Status: 0x50 (Volume 80, not muted)
    uint8_t buffer[] = { 0x5F, 0x7A, 0x50 };
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }
}

// Feature Abort Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectFeatureAbortFrameBroadcastIgnoreTest)
{
    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured.";
    // Feature Abort from device 4 to TV (0)
    // Header: 0x40, Opcode: 0x00 (Feature Abort), Rejected Opcode: 0x82, Reason: 0x04 (Refused)
    uint8_t buffer[] = { 0x4F, 0x00, 0x82, 0x04 };
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }
}

// Inject SetSystemAudioMode frame and verify setSystemAudioModeEvent event
TEST_F(HdmiCecSink_L2Test, InjectSetSystemAudioModeAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("setSystemAudioModeEvent"),
        &AsyncHandlerMock_HdmiCecSink::setSystemAudioModeEvent,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, setSystemAudioModeEvent(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::setSystemAudioModeEvent));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured.";

    // Set System Audio Mode from Audio System (5) to TV (0)
    // Header: 0x50, Opcode: 0x72 (Set System Audio Mode), Status: 0x01 (On)
    uint8_t buffer[] = { 0x50, 0x72, 0x01 };
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_SET_SYSTEM_AUDIO_MODE);
    EXPECT_TRUE(signalled & ON_SET_SYSTEM_AUDIO_MODE);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("setSystemAudioModeEvent"));
}

// Inject CECVersion frame and verify onDeviceInfoUpdated event
TEST_F(HdmiCecSink_L2Test, InjectCECVersionAndVerifyOnDeviceInfoUpdated)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;
    uint32_t status = Core::ERROR_GENERAL;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("onDeviceInfoUpdated"),
        &AsyncHandlerMock_HdmiCecSink::onDeviceInfoUpdated,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, onDeviceInfoUpdated(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::onDeviceInfoUpdated));

    ASSERT_FALSE(listeners.empty());

    // Simulate a CECVersion message from logical address 4 to us (0)
    uint8_t buffer[] = { 0x40, 0x9E, 0x05 }; // 0x05 = Version 1.4
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_DEVICE_INFO_UPDATED);
    EXPECT_TRUE(signalled & ON_DEVICE_INFO_UPDATED);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("onDeviceInfoUpdated"));
}

// RequestActiveSource (0x85)
TEST_F(HdmiCecSink_L2Test, InjectRequestActiveSourceFrame)
{
    uint8_t buffer[] = { 0x4F, 0x85 }; // From device 4 to broadcast
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// RequestActiveSource frame with direct message ingnored
TEST_F(HdmiCecSink_L2Test, InjectRequestActiveSourceFrameDirectMessageIgnoreTest)
{
    uint8_t buffer[] = { 0x40, 0x85 }; // From device 4 to TV
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GetCECVersion (0x9F)
TEST_F(HdmiCecSink_L2Test, InjectGetCECVersionFrame)
{
    uint8_t buffer[] = { 0x40, 0x9F }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GetCECVersion Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectGetCECVersionFrameroadcastIgnoreTest)
{
    uint8_t buffer[] = { 0x4F, 0x9F }; // From device 4 to broadcast
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GetCECVersion frame with exception in sendToAsync
TEST_F(HdmiCecSink_L2Test, InjectGetCECVersionFrameException)
{
    EXPECT_CALL(*p_connectionMock, sendToAsync(::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](const LogicalAddress& to, const CECFrame& frame) {
                throw Exception();
            }));

    uint8_t buffer[] = { 0x40, 0x9F }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GiveOSDName (0x46)
TEST_F(HdmiCecSink_L2Test, InjectGiveOSDNameFrame)
{
    uint8_t buffer[] = { 0x40, 0x46 }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GiveOSDName frame with exception in sendToAsync
TEST_F(HdmiCecSink_L2Test, InjectGiveOSDNameFrameException)
{
    uint8_t buffer[] = { 0x40, 0x46 }; // From device 4 to TV (0)

    EXPECT_CALL(*p_connectionMock, sendToAsync(::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](const LogicalAddress& to, const CECFrame& frame) {
                throw Exception();
            }));

    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GiveOSDName Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectGiveOSDNameFrameBroadcastIgnoreTest)
{
    uint8_t buffer[] = { 0x4F, 0x46 }; // From device 4 to broadcast
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GivePhysicalAddress (0x83)
TEST_F(HdmiCecSink_L2Test, InjectGivePhysicalAddressFrame)
{
    uint8_t buffer[] = { 0x40, 0x83 }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GivePhysicalAddress Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectGivePhysicalAddressFrameException)
{
    EXPECT_CALL(*p_connectionMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillOnce(::testing::Invoke(
            [&](const LogicalAddress&, const CECFrame&, int) {
                throw std::runtime_error("Simulated sendTo failure");
            }))
        .WillRepeatedly(::testing::Return());

    uint8_t buffer[] = { 0x40, 0x83 }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GiveDeviceVendorID (0x8C)
TEST_F(HdmiCecSink_L2Test, InjectGiveDeviceVendorIDFrame)
{
    uint8_t buffer[] = { 0x40, 0x8C }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GiveDeviceVendorID Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectGiveDeviceVendorIDFrameBroadcastIgnoreTest)
{
    uint8_t buffer[] = { 0x4F, 0x8C }; // From device 4 to broadcast
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GiveDeviceVendorID frame with exception in sendToAsync
TEST_F(HdmiCecSink_L2Test, InjectGiveDeviceVendorIDFrameBroadcastException)
{
    uint8_t buffer[] = { 0x40, 0x8C }; // From device 4 to TV (0)

    EXPECT_CALL(*p_connectionMock, sendToAsync(::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](const LogicalAddress& to, const CECFrame& frame) {
                throw Exception();
            }));

    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// SetOSDString (0x64)
TEST_F(HdmiCecSink_L2Test, InjectSetOSDStringFrame)
{
    uint8_t buffer[] = { 0x40, 0x64, 0x41, 0x42, 0x43 }; // From device 4 to TV (0), string "ABC"
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// SetOSDName (0x47)
TEST_F(HdmiCecSink_L2Test, InjectSetOSDNameFrame)
{
    uint8_t buffer[] = { 0x40, 0x47, 'T', 'E', 'S', 'T' }; // From device 4 to TV (0), name "TEST"
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// SetOSDName Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectSetOSDNameBroadcastIgnoreTest)
{
    uint8_t buffer[] = { 0x4F, 0x47, 'T', 'E', 'S', 'T' }; // From device 4 to broadcast, name "TEST"
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// RoutingChange (0x80)
TEST_F(HdmiCecSink_L2Test, InjectRoutingChangeFrame)
{
    uint8_t buffer[] = { 0x40, 0x80, 0x10, 0x00, 0x20, 0x00 }; // From device 4 to TV (0), old PA 1.0.0.0, new PA 2.0.0.0
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// RoutingInformation (0x81)
TEST_F(HdmiCecSink_L2Test, InjectRoutingInformationFrame)
{
    uint8_t buffer[] = { 0x40, 0x81, 0x20, 0x00 }; // From device 4 to TV (0), PA 2.0.0.0
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// SetStreamPath (0x86)
TEST_F(HdmiCecSink_L2Test, InjectSetStreamPathFrame)
{
    uint8_t buffer[] = { 0x4F, 0x86, 0x20, 0x00 }; // From device 4 to broadcast, PA 2.0.0.0
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GetMenuLanguage (0x91)
TEST_F(HdmiCecSink_L2Test, InjectGetMenuLanguageFrame)
{
    uint8_t buffer[] = { 0x40, 0x91 }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GetMenuLanguage Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectGetMenuLanguageFrameBroadcastIgnoreTest)
{
    uint8_t buffer[] = { 0x4F, 0x91 }; // From device 4 to broadcast
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GiveDevicePowerStatus (0x8F)
TEST_F(HdmiCecSink_L2Test, InjectGiveDevicePowerStatusFrame)
{
    uint8_t buffer[] = { 0x40, 0x8F }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GiveDevicePowerStatus Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectGiveDevicePowerStatusFrameBroadcastIgnoreTest)
{
    uint8_t buffer[] = { 0x4F, 0x8F }; // From device 4 to broadcast
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// GiveDevicePowerStatus frame with exception in sendTo
TEST_F(HdmiCecSink_L2Test, InjectGiveDevicePowerStatusFrameException)
{
    uint8_t buffer[] = { 0x40, 0x8F }; // From device 4 to TV (0)

    EXPECT_CALL(*p_connectionMock, sendTo(::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](const LogicalAddress& to, const CECFrame& frame) {
                throw Exception();
            }));

    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// InitiateArc (0xC0) TerminateArc (0xC5)
TEST_F(HdmiCecSink_L2Test, InjectInitiateAndTerminateArcFrameAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("arcInitiationEvent"),
        &AsyncHandlerMock_HdmiCecSink::arcInitiationEvent,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, arcInitiationEvent(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::arcInitiationEvent));

    ASSERT_FALSE(listeners.empty());

    // Inject Initiate ARC frame
    uint8_t initbuffer[] = { 0x50, 0xC0 }; // From Audio System (5) to TV (0)
    CECFrame initframe(initbuffer, sizeof(initbuffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(initframe);
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ARC_INITIATION_EVENT);
    EXPECT_TRUE(signalled & ARC_INITIATION_EVENT);

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("arcTerminationEvent"),
        &AsyncHandlerMock_HdmiCecSink::arcTerminationEvent,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, arcTerminationEvent(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::arcTerminationEvent));

    ASSERT_FALSE(listeners.empty());

    // Inject Terminate ARC frame
    uint8_t termbuffer[] = { 0x50, 0xC5 }; // From Audio System (5) to TV (0)
    CECFrame termframe(termbuffer, sizeof(termbuffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(termframe);
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ARC_TERMINATION_EVENT);
    EXPECT_TRUE(signalled & ARC_TERMINATION_EVENT);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("arcTerminationEvent"));

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("arcInitiationEvent"));
}

// Initiate & Terminate ARC frame
TEST_F(HdmiCecSink_L2Test, InjectInitiateArcFrameBroadcastIgnoreTest)
{
    uint8_t initbuffer[] = { 0x5F, 0xC0 }; // From Audio System (5) to TV (0)
    CECFrame initframe(initbuffer, sizeof(initbuffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(initframe);
    }

    uint8_t termbuffer[] = { 0x5F, 0xC5 }; // From Audio System (5) to TV (0)
    CECFrame termframe(termbuffer, sizeof(termbuffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(termframe);
    }
}

// GiveFeatures (0xA5)
TEST_F(HdmiCecSink_L2Test, InjectGiveFeaturesFrame)
{
    uint8_t buffer[] = { 0x40, 0xA5 }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// RequestCurrentLatency (0xA7)
TEST_F(HdmiCecSink_L2Test, InjectRequestCurrentLatencyFrame)
{
    uint8_t buffer[] = { 0x40, 0xA7, 0x10, 0x00 }; // From device 4 to TV (0), PA 1.0.0.0
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// ReportPhysicalAddress (0x84)
TEST_F(HdmiCecSink_L2Test, ReportPhysicalAddressBroadcastIgnoreCase)
{
    // Add a device on port 1 (logical address 4)
    uint8_t addBuffer[] = { 0x40, 0x84, 0x10, 0x00, 0x04 }; // From 4 to TV
    CECFrame addFrame(addBuffer, sizeof(addBuffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(addFrame);
    }
}

// Report Short Audio Descriptor (0xA3) and verify shortAudiodescriptorEvent event
TEST_F(HdmiCecSink_L2Test, InjectReportShortAudioDescriptorAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("shortAudiodescriptorEvent"),
        &AsyncHandlerMock_HdmiCecSink::shortAudiodescriptorEvent,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, shortAudiodescriptorEvent(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::shortAudiodescriptorEvent));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured.";

    // Report Short Audio Descriptor from Audio System (5) to TV (0)
    // Header: 0x50, Opcode: 0xA3 (Report Short Audio Descriptor)
    uint8_t buffer[] = { 0x50, 0xA3, 0x02, 0x0A }; // Example SAD bytes
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, SHORT_AUDIO_DESCRIPTOR);
    EXPECT_TRUE(signalled & SHORT_AUDIO_DESCRIPTOR);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("shortAudiodescriptorEvent"));
}

// Standby (0x36) and verify standbyMessageReceived event
TEST_F(HdmiCecSink_L2Test, InjectStandbyFrameAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("standbyMessageReceived"),
        &AsyncHandlerMock_HdmiCecSink::standbyMessageReceived,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, standbyMessageReceived(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::standbyMessageReceived));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured.";

    // Standby from device 4 to TV (0)
    uint8_t buffer[] = { 0x40, 0x36 };
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, STANDBY_MESSAGE_RECEIVED);
    EXPECT_TRUE(signalled & STANDBY_MESSAGE_RECEIVED);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("standbyMessageReceived"));
}

// Report Power Status (0x90) and verify reportAudioDevicePowerStatus event
TEST_F(HdmiCecSink_L2Test, InjectReportPowerStatusAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;
    JsonObject params, result;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("reportAudioDevicePowerStatus"),
        &AsyncHandlerMock_HdmiCecSink::reportAudioDevicePowerStatus,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, reportAudioDevicePowerStatus(::testing::_))
        .Times(2)
        .WillRepeatedly(Invoke(this, &HdmiCecSink_L2Test::reportAudioDevicePowerStatus));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured.";

    status = InvokeServiceMethod("org.rdk.HdmiCecSink", "requestAudioDevicePowerStatus", params, result);
    EXPECT_EQ(Core::ERROR_NONE, status);
    EXPECT_TRUE(result.HasLabel("success"));
    EXPECT_TRUE(result["success"].Boolean());

    // First, inject OFF status
    uint8_t buffer_off[] = { 0x50, 0x90, 0x01 }; // 0x01 = Standby
    CECFrame frame_off(buffer_off, sizeof(buffer_off));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame_off);
    }

    // Then, inject ON status (should trigger the event)
    uint8_t buffer_on[] = { 0x50, 0x90, 0x00 }; // 0x00 = ON
    CECFrame frame_on(buffer_on, sizeof(buffer_on));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame_on);
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, REPORT_AUDIO_DEVICE_POWER_STATUS);
    EXPECT_TRUE(signalled & REPORT_AUDIO_DEVICE_POWER_STATUS);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("reportAudioDevicePowerStatus"));
}

// Report Power Status (0x90) Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectReportPowerStatusBroadcastIgnoreTest)
{
    // Then, inject ON status (should trigger the event)
    uint8_t buffer_on[] = { 0x5F, 0x90, 0x00 }; // 0x00 = ON
    CECFrame frame_on(buffer_on, sizeof(buffer_on));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame_on);
    }
}

// SetMenuLanguage (0x32)
TEST_F(HdmiCecSink_L2Test, InjectSetMenuLanguageFrame)
{
    // Set Menu Language: opcode 0x32, language "eng"
    uint8_t buffer[] = { 0x40, 0x32, 'e', 'n', 'g' }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
    // Optionally: check plugin state or logs for language update
}

// DeviceVendorID (0x87) and verify onDeviceInfoUpdated event
TEST_F(HdmiCecSink_L2Test, InjectDeviceVendorIDFrameAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("onDeviceInfoUpdated"),
        &AsyncHandlerMock_HdmiCecSink::onDeviceInfoUpdated,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, onDeviceInfoUpdated(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test::onDeviceInfoUpdated));

    ASSERT_FALSE(listeners.empty());

    // Device Vendor ID: opcode 0x87, vendor ID 0x00 0x19 0xFB
    uint8_t buffer[] = { 0x4F, 0x87, 0x00, 0x19, 0xFB };
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_DEVICE_INFO_UPDATED);
    EXPECT_TRUE(signalled & ON_DEVICE_INFO_UPDATED);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("onDeviceInfoUpdated"));
}

// DeviceVendorID (0x87)
TEST_F(HdmiCecSink_L2Test, InjectDeviceVendorIDFrameBroadcastIgnoreTest)
{
    // Device Vendor ID: opcode 0x87, vendor ID 0x00 0x19 0xFB
    uint8_t buffer[] = { 0x40, 0x87, 0x00, 0x19, 0xFB };
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// Abort (0xFF)
TEST_F(HdmiCecSink_L2Test, InjectAbortFrame)
{
    // Abort: opcode 0xFF, sent as a direct message (not broadcast)
    uint8_t buffer[] = { 0x40, 0xFF }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// Abort (0xFF) Broadcast frame should be ignored
TEST_F(HdmiCecSink_L2Test, InjectAbortFrameBroadcastIgnoreCase)
{
    // Abort: opcode 0xFF, sent as a direct message (not broadcast)
    uint8_t buffer[] = { 0x4F, 0xFF }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// Polling: header only, no opcode
TEST_F(HdmiCecSink_L2Test, InjectPollingFrame)
{
    // Polling: header only, no opcode
    uint8_t buffer[] = { 0x40, 0x13 }; // From device 4 to TV (0)
    CECFrame frame(buffer, sizeof(buffer));
    for (auto* listener : listeners) {
        if (listener)
            listener->notify(frame);
    }
}

// Active Source (0x82) and verify onWakeupFromStandby event
TEST_F(HdmiCecSink_L2Test_STANDBY, InjectWakeupFromStandbyFrameAndVerifyEvent)
{
    JSONRPC::LinkType<Core::JSON::IElement> jsonrpc(HDMICECSINK_CALLSIGN, HDMICECSINK_L2TEST_CALLSIGN);
    StrictMock<AsyncHandlerMock_HdmiCecSink> async_handler;
    uint32_t status = Core::ERROR_GENERAL;
    uint32_t signalled = HDMICECSINK_STATUS_INVALID;

    status = jsonrpc.Subscribe<JsonObject>(EVNT_TIMEOUT,
        _T("onWakeupFromStandby"),
        &AsyncHandlerMock_HdmiCecSink::onWakeupFromStandby,
        &async_handler);
    EXPECT_EQ(Core::ERROR_NONE, status);

    EXPECT_CALL(async_handler, onWakeupFromStandby(::testing::_))
        .WillOnce(Invoke(this, &HdmiCecSink_L2Test_STANDBY::onWakeupFromStandby));

    ASSERT_FALSE(listeners.empty()) << "No FrameListener was captured.";

    // Simulate TV in standby, then send Active Source to wake it up
    uint8_t buffer[] = { 0x4F, 0x82, 0x10, 0x00 }; // Active Source from device 4 to broadcast
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }

    signalled = WaitForRequestStatus(EVNT_TIMEOUT, ON_WAKEUP_FROM_STANDBY);
    EXPECT_TRUE(signalled & ON_WAKEUP_FROM_STANDBY);

    jsonrpc.Unsubscribe(EVNT_TIMEOUT, _T("onWakeupFromStandby"));
}

TEST_F(HdmiCecSink_L2Test, ActiveSourceFrameBroadcastIgnoreTest)
{
    uint8_t buffer[] = { 0x40, 0x82, 0x10, 0x00 }; // Active Source from device 4 to broadcast
    CECFrame frame(buffer, sizeof(buffer));

    for (auto* listener : listeners) {
        if (listener) {
            listener->notify(frame);
        }
    }
}

// Power Mode Change to ON to verify onPowerModeChanged event
TEST_F(HdmiCecSink_L2Test_STANDBY, TriggerOnPowerModeChangeEvent_ON)
{
    Core::ProxyType<RPC::InvokeServerType<1, 0, 4>> mEngine_PowerManager;
    Core::ProxyType<RPC::CommunicatorClient> mClient_PowerManager;
    PluginHost::IShell* mController_PowerManager;

    TEST_LOG("Creating mEngine_PowerManager");
    mEngine_PowerManager = Core::ProxyType<RPC::InvokeServerType<1, 0, 4>>::Create();
    mClient_PowerManager = Core::ProxyType<RPC::CommunicatorClient>::Create(Core::NodeId("/tmp/communicator"), Core::ProxyType<Core::IIPCServer>(mEngine_PowerManager));

    TEST_LOG("Creating mEngine_PowerManager Announcements");
#if ((THUNDER_VERSION == 2) || ((THUNDER_VERSION == 4) && (THUNDER_VERSION_MINOR == 2)))
    mEngine_PowerManager->Announcements(mClient_PowerManager->Announcement());
#endif

    if (!mClient_PowerManager.IsValid()) {
        TEST_LOG("Invalid mClient_PowerManager");
    } else {
        mController_PowerManager = mClient_PowerManager->Open<PluginHost::IShell>(_T("org.rdk.PowerManager"), ~0, 3000);
        if (mController_PowerManager) {
            auto PowerManagerPlugin = mController_PowerManager->QueryInterface<Exchange::IPowerManager>();

            if (PowerManagerPlugin) {
                int keyCode = 0;

                uint32_t clientId = 0;
                uint32_t status = PowerManagerPlugin->AddPowerModePreChangeClient("l2-test-client", clientId);
                EXPECT_EQ(status, Core::ERROR_NONE);

                EXPECT_CALL(*p_powerManagerHalMock, PLAT_API_SetPowerState(::testing::_))
                    .WillOnce(::testing::Invoke(
                        [](PWRMgr_PowerState_t powerState) {
                            EXPECT_EQ(powerState, PWRMGR_POWERSTATE_ON);
                            return PWRMGR_SUCCESS;
                        }));

                status = PowerManagerPlugin->SetPowerState(keyCode, PowerState::POWER_STATE_ON, "l2-test");
                EXPECT_EQ(status, Core::ERROR_NONE);

                // some delay to destroy AckController after IModeChanged notification
                std::this_thread::sleep_for(std::chrono::milliseconds(1500));

                PowerManagerPlugin->Release();
            } else {
                TEST_LOG("PowerManagerPlugin is NULL");
            }
            mController_PowerManager->Release();
        } else {
            TEST_LOG("mController_PowerManager is NULL");
        }
    }
}

// Power Mode Change to OFF to verify onPowerModeChanged event
TEST_F(HdmiCecSink_L2Test, RaisePowerModeChangedEvent_OFF)
{
    Core::ProxyType<RPC::InvokeServerType<1, 0, 4>> mEngine_PowerManager;
    Core::ProxyType<RPC::CommunicatorClient> mClient_PowerManager;
    PluginHost::IShell* mController_PowerManager;

    TEST_LOG("Creating mEngine_PowerManager");
    mEngine_PowerManager = Core::ProxyType<RPC::InvokeServerType<1, 0, 4>>::Create();
    mClient_PowerManager = Core::ProxyType<RPC::CommunicatorClient>::Create(Core::NodeId("/tmp/communicator"), Core::ProxyType<Core::IIPCServer>(mEngine_PowerManager));

    TEST_LOG("Creating mEngine_PowerManager Announcements");
#if ((THUNDER_VERSION == 2) || ((THUNDER_VERSION == 4) && (THUNDER_VERSION_MINOR == 2)))
    mEngine_PowerManager->Announcements(mClient_PowerManager->Announcement());
#endif

    if (!mClient_PowerManager.IsValid()) {
        TEST_LOG("Invalid mClient_PowerManager");
    } else {
        mController_PowerManager = mClient_PowerManager->Open<PluginHost::IShell>(_T("org.rdk.PowerManager"), ~0, 3000);
        if (mController_PowerManager) {
            auto PowerManagerPlugin = mController_PowerManager->QueryInterface<Exchange::IPowerManager>();

            if (PowerManagerPlugin) {
                int keyCode = 0;

                uint32_t clientId = 0;
                uint32_t status = PowerManagerPlugin->AddPowerModePreChangeClient("l2-test-client", clientId);
                EXPECT_EQ(status, Core::ERROR_NONE);

                EXPECT_CALL(*p_powerManagerHalMock, PLAT_API_SetPowerState(::testing::_))
                    .WillOnce(::testing::Invoke(
                        [](PWRMgr_PowerState_t powerState) {
                            EXPECT_EQ(powerState, PWRMGR_POWERSTATE_OFF);
                            return PWRMGR_SUCCESS;
                        }));

                status = PowerManagerPlugin->SetPowerState(keyCode, PowerState::POWER_STATE_OFF, "l2-test");
                EXPECT_EQ(status, Core::ERROR_NONE);

                // some delay to destroy AckController after IModeChanged notification
                std::this_thread::sleep_for(std::chrono::milliseconds(1500));

                PowerManagerPlugin->Release();
            } else {
                TEST_LOG("PowerManagerPlugin is NULL");
            }
            mController_PowerManager->Release();
        } else {
            TEST_LOG("mController_PowerManager is NULL");
        }
    }
}
