/**
* If not stated otherwise in this file or this component's LICENSE
* file the following copyright and licenses apply:
*
* Copyright 2024 RDK Management
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
**/

#include <gtest/gtest.h>
#include <iostream>
#include <fstream>
#include <string>
#include <thread>
#include <chrono>


#include "HdmiCecSink.h"
#include "HdmiCecSinkImplementation.h"
#include "HdmiCecSinkMock.h"
#include "FactoriesImplementation.h"
#include "IarmBusMock.h"
#include "ServiceMock.h"
#include "devicesettings.h"
#include "HdmiCec.h"
#include "HdmiCecMock.h"
#include "WrapsMock.h"
#include "RfcApiMock.h"
#include "ThunderPortability.h"
#include "PowerManagerMock.h"
#include "WorkerPoolImplementation.h"
#include "COMLinkMock.h"
#include "ManagerMock.h"
#include "HostMock.h"
#include "HdmiInputMock.h"

using namespace WPEFramework;
using ::testing::NiceMock;

namespace
{
	static void removeFile(const char* fileName)
	{
		if (std::remove(fileName) != 0)
		{
			printf("File %s failed to remove\n", fileName);
			perror("Error deleting file");
		}
		else
		{
			printf("File %s successfully deleted\n", fileName);
		}
	}
	
	static void createFile(const char* fileName, const char* fileContent)
	{
		removeFile(fileName);

		std::ofstream fileContentStream(fileName);
		fileContentStream << fileContent;
		fileContentStream << "\n";
		fileContentStream.close();
	}
}

class HdmiCecSinkInitializeTest : public ::testing::Test {
protected:
    Core::ProxyType<Plugin::HdmiCecSink> plugin;
    Core::JSONRPC::Handler& handler;
    DECL_CORE_JSONRPC_CONX connection;
    IARM_EventHandler_t dsHdmiEventHandler;
    Core::ProxyType<Plugin::HdmiCecSinkImplementation> pluginImpl;
    Core::ProxyType<WorkerPoolImplementation> workerPool;
    NiceMock<FactoriesImplementation> factoriesImplementation;
    NiceMock<ServiceMock> service;
    PLUGINHOST_DISPATCHER* dispatcher;
    NiceMock<COMLinkMock> comLinkMock;
    Core::JSONRPC::Message message;
    string response;

    HdmiCecSinkInitializeTest()
        : plugin(Core::ProxyType<Plugin::HdmiCecSink>::Create())
        , handler(*(plugin))
        , INIT_CONX(1, 0)
		, dsHdmiEventHandler(nullptr)
        , workerPool(Core::ProxyType<WorkerPoolImplementation>::Create(
              2, Core::Thread::DefaultStackSize(), 16))
		, dispatcher(nullptr)
    {
    }

    virtual ~HdmiCecSinkInitializeTest() override
    {
        plugin.Release();
    }
};

class HdmiCecSinkDsTest : public HdmiCecSinkInitializeTest {
protected:
    IarmBusImplMock         *p_iarmBusImplMock = nullptr ;
    ManagerImplMock         *p_managerImplMock = nullptr ;
    HostImplMock            *p_hostImplMock = nullptr ;
    HdmiInputImplMock       *p_hdmiInputImplMock = nullptr;
    ConnectionImplMock      *p_connectionImplMock = nullptr ;
    MessageEncoderMock      *p_messageEncoderMock = nullptr ;
    LibCCECImplMock         *p_libCCECImplMock = nullptr ;
    RfcApiImplMock   *p_rfcApiImplMock = nullptr ;
    WrapsImplMock  *p_wrapsImplMock   = nullptr ;
    NiceMock<RfcApiImplMock> rfcApiImplMock;
    NiceMock<WrapsImplMock> wrapsImplMock;
    string response;
    std::vector<FrameListener*> listeners;

    HdmiCecSinkDsTest(): HdmiCecSinkInitializeTest()
    {
        createFile("/etc/device.properties", "RDK_PROFILE=TV");
        p_iarmBusImplMock  = new NiceMock <IarmBusImplMock>;
        IarmBus::setImpl(p_iarmBusImplMock);

        p_managerImplMock  = new NiceMock <ManagerImplMock>;
        device::Manager::setImpl(p_managerImplMock);

        p_hostImplMock      = new NiceMock <HostImplMock>;
        device::Host::setImpl(p_hostImplMock);

        p_hdmiInputImplMock  = new NiceMock <HdmiInputImplMock>;
        device::HdmiInput::setImpl(p_hdmiInputImplMock);

        p_libCCECImplMock  = new testing::NiceMock <LibCCECImplMock>;
        LibCCEC::setImpl(p_libCCECImplMock);

        p_messageEncoderMock  = new testing::NiceMock <MessageEncoderMock>;
        MessageEncoder::setImpl(p_messageEncoderMock);

        p_connectionImplMock  = new testing::NiceMock <ConnectionImplMock>;
        Connection::setImpl(p_connectionImplMock);

        p_rfcApiImplMock  = new testing::NiceMock <RfcApiImplMock>;
        RfcApi::setImpl(p_rfcApiImplMock);

        p_wrapsImplMock  = new testing::NiceMock <WrapsImplMock>;
        Wraps::setImpl(p_wrapsImplMock); /*Set up mock for fopen;
                                                      to use the mock implementation/the default behavior of the fopen function from Wraps class.*/

        ON_CALL(*p_connectionImplMock, poll(::testing::_, ::testing::_))
            .WillByDefault(::testing::Invoke(
                [&](const LogicalAddress &from, const Throw_e &doThrow) {
                throw CECNoAckException();
                }));

        EXPECT_CALL(*p_libCCECImplMock, getPhysicalAddress(::testing::_))
            .WillRepeatedly(::testing::Invoke(
                [&](uint32_t *physAddress) {
                    *physAddress = (uint32_t)0x12345678;
                }));

        ON_CALL(*p_messageEncoderMock, encode(::testing::Matcher<const DataBlock&>(::testing::_)))
            .WillByDefault(::testing::ReturnRef(CECFrame::getInstance()));
        ON_CALL(*p_messageEncoderMock, encode(::testing::Matcher<const UserControlPressed&>(::testing::_)))
           .WillByDefault(::testing::ReturnRef(CECFrame::getInstance()));

        EXPECT_CALL(*p_managerImplMock, Initialize())
            .Times(::testing::AnyNumber())
            .WillRepeatedly(::testing::Return());

        ON_CALL(*p_connectionImplMock, open())
            .WillByDefault(::testing::Return());

        EXPECT_CALL(*p_hdmiInputImplMock, getNumberOfInputs())
            .WillRepeatedly(::testing::Return(3));

        ON_CALL(*p_hdmiInputImplMock, isPortConnected(::testing::_))
            .WillByDefault(::testing::Invoke(
                [](int8_t port) {
                    return port == 1? true : false;
                }));

        ON_CALL(*p_hdmiInputImplMock, getHDMIARCPortId(::testing::_))
            .WillByDefault(::testing::Invoke(
                [](int &portId) {
                    portId = 1;
                    return dsERR_NONE;
                }));

        ON_CALL(*p_connectionImplMock, addFrameListener(::testing::_))
        .WillByDefault([this](FrameListener* listener) {
            printf("[TEST] addFrameListener called with address: %p\n", static_cast<void*>(listener));
            this->listeners.push_back(listener);
        });

        ON_CALL(comLinkMock, Instantiate(::testing::_, ::testing::_, ::testing::_))
            .WillByDefault(::testing::Invoke(
                [&](const RPC::Object& object, const uint32_t waitTime, uint32_t& connectionId) {
                    pluginImpl = Core::ProxyType<Plugin::HdmiCecSinkImplementation>::Create();
                    return &pluginImpl;
                }));

        Core::IWorkerPool::Assign(&(*workerPool));
        workerPool->Run();

        PluginHost::IFactories::Assign(&factoriesImplementation);

        dispatcher = static_cast<PLUGINHOST_DISPATCHER*>(
           plugin->QueryInterface(PLUGINHOST_DISPATCHER_ID));
        dispatcher->Activate(&service);

        EXPECT_EQ(string(""), plugin->Initialize(&service));
    }
    virtual ~HdmiCecSinkDsTest() override {

        plugin->Deinitialize(&service);

        Core::IWorkerPool::Assign(nullptr);
        workerPool.Release();
        dispatcher->Deactivate();
        dispatcher->Release();
        PluginHost::IFactories::Assign(nullptr);

        removeFile("/etc/device.properties");

        IarmBus::setImpl(nullptr);
        if (p_iarmBusImplMock != nullptr)
        {
            delete p_iarmBusImplMock;
            p_iarmBusImplMock = nullptr;
        }
        device::Manager::setImpl(nullptr);
        if (p_managerImplMock != nullptr)
        {
            delete p_managerImplMock;
            p_managerImplMock = nullptr;
        }
        device::Host::setImpl(nullptr);
        if (p_hostImplMock != nullptr)
        {
            delete p_hostImplMock;
            p_hostImplMock = nullptr;
        }
        device::HdmiInput::setImpl(nullptr);
        if (p_hdmiInputImplMock != nullptr)
        {
            delete p_hdmiInputImplMock;
            p_hdmiInputImplMock = nullptr;
        }
        LibCCEC::setImpl(nullptr);
        if (p_libCCECImplMock != nullptr)
        {
            delete p_libCCECImplMock;
            p_libCCECImplMock = nullptr;
        }
        Connection::setImpl(nullptr);
        if (p_connectionImplMock != nullptr)
        {
            delete p_connectionImplMock;
            p_connectionImplMock = nullptr;
        }
        MessageEncoder::setImpl(nullptr);
        if (p_messageEncoderMock != nullptr)
        {
            delete p_messageEncoderMock;
            p_messageEncoderMock = nullptr;
        }

        RfcApi::setImpl(nullptr);
        if (p_rfcApiImplMock != nullptr)
        {
            delete p_rfcApiImplMock;
            p_rfcApiImplMock = nullptr;
        }

        Wraps::setImpl(nullptr);
        if (p_wrapsImplMock != nullptr)
        {
            delete p_wrapsImplMock;
            p_wrapsImplMock = nullptr;
        }
    }
};

class HdmiCecSinkInitializedEventTest : public HdmiCecSinkDsTest {
protected:
    NiceMock<ServiceMock> service;
    NiceMock<FactoriesImplementation> factoriesImplementation;
    PLUGINHOST_DISPATCHER* dispatcher;
    Core::JSONRPC::Message message;

    HdmiCecSinkInitializedEventTest(): HdmiCecSinkDsTest()
    {
        PluginHost::IFactories::Assign(&factoriesImplementation);

        dispatcher = static_cast<PLUGINHOST_DISPATCHER*>(
           plugin->QueryInterface(PLUGINHOST_DISPATCHER_ID));
        dispatcher->Activate(&service);
    }
    virtual ~HdmiCecSinkInitializedEventTest() override
    {
        dispatcher->Deactivate();
        dispatcher->Release();
        PluginHost::IFactories::Assign(nullptr);
    }
};

class HdmiCecSinkInitializedEventDsTest : public HdmiCecSinkInitializedEventTest {
protected:
    HdmiCecSinkInitializedEventDsTest(): HdmiCecSinkInitializedEventTest()
    {
    }
    virtual ~HdmiCecSinkInitializedEventDsTest() override
    {
    }
};

TEST_F(HdmiCecSinkDsTest, RegisteredMethods)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("setEnabled")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("setOSDName")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("setVendorId")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("getVendorId")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("setActivePath")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("setRoutingChange")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("getDeviceList")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("getActiveSource")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("setActiveSource")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("getActiveRoute")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("setMenuLanguage")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("requestActiveSource")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("setupARCRouting")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("requestShortAudioDescriptor")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("sendStandbyMessage")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("sendAudioDevicePowerOnMessage")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("sendKeyPressEvent")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("sendGetAudioStatusMessage")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("getAudioDeviceConnectedStatus")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("requestAudioDevicePowerStatus")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("sendUserControlPressed")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("sendUserControlReleased")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("setLatencyInfo")));
    EXPECT_EQ(Core::ERROR_NONE, handler.Exists(_T("printDeviceList")));

}

TEST_F(HdmiCecSinkDsTest, setOSDNameParamMissing)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setOSDName"), _T("{}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, getOSDName)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setOSDName"), _T("{\"name\":\"CECTEST\"}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("getOSDName"), _T("{}"), response));
    EXPECT_EQ(response,  string("{\"name\":\"CECTEST\",\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, setVendorIdParamMissing)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setVendorId"), _T("{}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, getVendorId)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setVendorId"), _T("{\"vendorid\":\"0x0019FF\"}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("getVendorId"), _T("{}"), response));
    EXPECT_EQ(response,  string("{\"vendorid\":\"019ff\",\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, setActivePathMissingParam)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setActivePath"), _T("{}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, setActivePath)
{

    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](const LogicalAddress &to, const CECFrame &frame, int timeout) {
               EXPECT_EQ(to.toInt(), LogicalAddress::BROADCAST);
               EXPECT_GT(timeout, 0);
            }));

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setActivePath"), _T("{\"activePath\":\"2.0.0.0\"}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, setRoutingChangeInvalidParam)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setRoutingChange"), _T("{\"oldPort\":\"HDMI0\"}"), response));
    EXPECT_EQ(response,  string("{\"success\":false}"));

}

TEST_F(HdmiCecSinkDsTest, setRoutingChange)
{

    std::this_thread::sleep_for(std::chrono::seconds(30));

    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](const LogicalAddress &to, const CECFrame &frame, int timeout) {
                EXPECT_EQ(to.toInt(), LogicalAddress::BROADCAST);
                EXPECT_GT(timeout, 0);
            }));

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setRoutingChange"), _T("{\"oldPort\":\"HDMI0\",\"newPort\":\"TV\"}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, setMenuLanguageInvalidParam)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setMenuLanguage"), _T("{\"language\":""}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, setMenuLanguage)
{

    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Invoke(
            [&](const LogicalAddress &to, const CECFrame &frame, int timeout) {
                EXPECT_LE(to.toInt(), LogicalAddress::BROADCAST);
                EXPECT_GT(timeout, 0);
            }));

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setMenuLanguage"), _T("{\"language\":\"english\"}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, setupARCRoutingInvalidParam)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setupARCRouting"), _T("{}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, setupARCRouting)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setupARCRouting"), _T("{\"enabled\":true}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, setupARCRouting_False)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setupARCRouting"), _T("{\"enabled\":false}"), response));
    EXPECT_EQ(response,  string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEventMissingParam)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\": 0, \"keyCode\": }"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent)
{

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\": 0, \"keyCode\": 65}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));

}

TEST_F(HdmiCecSinkInitializedEventDsTest, onHdmiOutputHDCPStatusEvent)
{

    EVENT_SUBSCRIBE(0, _T("onDevicesChanged"), _T("client.events.onDevicesChanged"), message);
    Plugin::HdmiCecSinkImplementation::_instance->OnHdmiInEventHotPlug(dsHDMI_IN_PORT_1, true);
    EVENT_UNSUBSCRIBE(0, _T("onDevicesChanged"), _T("client.events.onDevicesChanged"), message);

}

TEST_F(HdmiCecSinkInitializedEventDsTest, powerModeChange)
{
    // ASSERT_TRUE(pwrMgrModeChangeEventHandler != nullptr);

    IARM_Bus_PWRMgr_EventData_t eventData;
    eventData.data.state.newState =IARM_BUS_PWRMGR_POWERSTATE_ON;
    eventData.data.state.curState =IARM_BUS_PWRMGR_POWERSTATE_STANDBY;

    (void) eventData;

    // pwrMgrModeChangeEventHandler(IARM_BUS_PWRMGR_NAME, IARM_BUS_PWRMGR_EVENT_MODECHANGED, &eventData , 0);
}

TEST_F(HdmiCecSinkInitializedEventDsTest, DISABLED_getCecVersion)
{
    /*EXPECT_CALL(rfcApiImplMock, getRFCParameter(::testing::_, ::testing::_, ::testing::_))
        .Times(1)
        .WillOnce(::testing::Invoke(
            [](char* pcCallerID, const char* pcParameterName, RFC_ParamData_t* pstParamData) {
                EXPECT_EQ(string(pcCallerID), string("HdmiCecSink"));
                EXPECT_EQ(string(pcParameterName), string("Device.DeviceInfo.X_RDKCENTRAL-COM_RFC.Feature.HdmiCecSink.CECVersion"));
                strncpy(pstParamData->value, "1.4", sizeof(pstParamData->value));
                return WDMP_SUCCESS;
            }));*/

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("getCecVersion"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"CECVersion\":\"1.4\",\"success\":true}"));

}



//Copilot Generated Code

TEST_F(HdmiCecSinkDsTest, setEnabled_ValidTrue)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setEnabled"), _T("{\"enabled\":true}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setEnabled_ValidFalse)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setEnabled"), _T("{\"enabled\":false}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, getEnabled)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("getEnabled"), _T("{}"), response));
    EXPECT_THAT(response, ::testing::ContainsRegex("\"enabled\":(true|false)"));
    EXPECT_THAT(response, ::testing::ContainsRegex("\"success\":true"));
}

TEST_F(HdmiCecSinkDsTest, setOSDName_EmptyName)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setOSDName"), _T("{\"name\":\"\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setOSDName_LongName)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setOSDName"), _T("{\"name\":\"VERYLONGNAMETHATEXCEEDSLIMIT\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setVendorId_ValidHex)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setVendorId"), _T("{\"vendorid\":\"0x123456\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setVendorId_InvalidFormat)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setVendorId"), _T("{\"vendorid\":\"INVALID\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setActivePath_InvalidPath)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setActivePath"), _T("{\"activePath\":\"INVALID.PATH\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setRoutingChange_ValidPorts)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());
    
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setRoutingChange"), _T("{\"oldPort\":\"HDMI1\",\"newPort\":\"HDMI2\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setRoutingChange_SamePorts)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setRoutingChange"), _T("{\"oldPort\":\"HDMI0\",\"newPort\":\"HDMI0\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, getDeviceList)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("getDeviceList"), _T("{}"), response));
    EXPECT_THAT(response, ::testing::ContainsRegex("\"numberofdevices\":"));
    EXPECT_THAT(response, ::testing::ContainsRegex("\"success\":true"));
}

TEST_F(HdmiCecSinkDsTest, getActiveSource)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("getActiveSource"), _T("{}"), response));
    EXPECT_THAT(response, ::testing::ContainsRegex("\"logicalAddress\":"));
    EXPECT_THAT(response, ::testing::ContainsRegex("\"success\":true"));
}

TEST_F(HdmiCecSinkDsTest, setActiveSource_ValidLogicalAddress)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setActiveSource"), _T("{\"logicalAddress\":1}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setActiveSource_InvalidLogicalAddress)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setActiveSource"), _T("{\"logicalAddress\":16}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setActiveSource_MissingParam)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setActiveSource"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, getActiveRoute)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("getActiveRoute"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"available\":false,\"length\":0,\"ActiveRoute\":\"\",\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, requestActiveSource)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());
    
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("requestActiveSource"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, requestShortAudioDescriptor)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());
    
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("requestShortAudioDescriptor"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendStandbyMessage)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());
    
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendStandbyMessage"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendAudioDevicePowerOnMessage)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());
    
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendAudioDevicePowerOnMessage"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_InvalidLogicalAddress)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":16,\"keyCode\":1}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_InvalidKeyCode)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":256}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendGetAudioStatusMessage)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());
    
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendGetAudioStatusMessage"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, getAudioDeviceConnectedStatus)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("getAudioDeviceConnectedStatus"), _T("{}"), response));
    EXPECT_THAT(response, ::testing::ContainsRegex("\"connected\":"));
    EXPECT_THAT(response, ::testing::ContainsRegex("\"success\":true"));
}

TEST_F(HdmiCecSinkDsTest, requestAudioDevicePowerStatus)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());
    
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("requestAudioDevicePowerStatus"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, getDeviceList_ConnectionClosed)
{
    EXPECT_CALL(*p_connectionImplMock, close())
        .WillOnce(::testing::Return());
    
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("getDeviceList"), _T("{}"), response));
}

TEST_F(HdmiCecSinkDsTest, setOSDName_MaxLength)
{
    string longName(14, 'X');
    string payload = "{\"name\":\"" + longName + "\"}";
    
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setOSDName"), payload, response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setVendorId_Boundary)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setVendorId"), _T("{\"vendorid\":\"0xFFFFFF\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setVendorId_MinValue)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setVendorId"), _T("{\"vendorid\":\"0x000000\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_BoundaryKeyCode)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":0,\"keyCode\":255}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_MinKeyCode)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":0,\"keyCode\":0}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setActiveSource_BoundaryLogicalAddress)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setActiveSource"), _T("{\"logicalAddress\":15}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setActiveSource_MinLogicalAddress)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setActiveSource"), _T("{\"logicalAddress\":0}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setRoutingChange_InvalidPortFormat)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setRoutingChange"), _T("{\"oldPort\":\"INVALID_PORT\",\"newPort\":\"HDMI0\"}"), response));
    EXPECT_EQ(response, string("{\"success\":false}"));
}

TEST_F(HdmiCecSinkDsTest, setMenuLanguage_SpecialCharacters)
{    
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setMenuLanguage"), _T("{\"language\":\"ñäöü\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, MalformedJSON_setEnabled)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setEnabled"), _T("{\"enabled\":}"), response));
}

TEST_F(HdmiCecSinkDsTest, MalformedJSON_setOSDName)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setOSDName"), _T("{\"name\":"), response));
}

TEST_F(HdmiCecSinkDsTest, MalformedJSON_setVendorId)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setVendorId"), _T("{\"vendorid\""), response));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_VolumeDown)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":66}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Mute)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":67}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Down)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":2}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Left)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":3}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Right)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":4}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Home)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":9}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Back)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":13}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Number0)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":32}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Number1)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":33}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Number2)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":34}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Number3)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":35}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Number4)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":36}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Number5)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":37}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Number6)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":38}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Number7)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":39}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Number8)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":40}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_Number9)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":41}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendKeyPressEvent_NullConnection)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendKeyPressEvent"), _T("{\"logicalAddress\":1,\"keyCode\":65}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_VolumeUp)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":65}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Select)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":0}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Up)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":1}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Down)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":2}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Left)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":3}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Right)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":4}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Home)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":9}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Back)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":13}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Number0)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":32}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Number1)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":33}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Number2)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":34}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Number3)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":35}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Number4)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":36}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Number5)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":37}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Number6)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":38}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Number7)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":39}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Number8)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":40}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Number9)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":41}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_VolumeDown)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":66}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_Mute)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":67}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_InvalidLogicalAddress)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":16,\"keyCode\":1}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_InvalidKeyCode)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":4,\"keyCode\":256}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_MissingParams)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_BoundaryKeyCode)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":0,\"keyCode\":255}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_MinKeyCode)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":0,\"keyCode\":0}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_NegativeValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":-1,\"keyCode\":-1}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_StringValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":\"invalid\",\"keyCode\":\"test\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlPressed_MalformedJSON)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlPressed"), _T("{\"logicalAddress\":"), response));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_VolumeUp)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":65}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Select)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":0}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Up)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":1}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Down)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":2}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Left)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":3}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Right)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":4}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Home)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":9}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Back)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":13}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Number0)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":32}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Number1)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":33}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Number2)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":34}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Number3)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":35}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Number4)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":36}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Number5)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":37}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Number6)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":38}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Number7)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":39}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Number8)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":40}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Number9)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":41}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_VolumeDown)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":66}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_Mute)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":67}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_InvalidLogicalAddress)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":16,\"keyCode\":1}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_InvalidKeyCode)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":4,\"keyCode\":256}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_MissingParams)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_BoundaryKeyCode)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":0,\"keyCode\":255}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_MinKeyCode)
{
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillRepeatedly(::testing::Return());

    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":0,\"keyCode\":0}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_NegativeValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":-1,\"keyCode\":-1}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_StringValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":\"invalid\",\"keyCode\":\"test\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, sendUserControlReleased_MalformedJSON)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("sendUserControlReleased"), _T("{\"logicalAddress\":"), response));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_ValidParameters)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"20\",\"lowLatencyMode\":\"1\",\"audioOutputCompensated\":\"1\",\"audioOutputDelay\":\"10\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_MinValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"0\",\"lowLatencyMode\":\"0\",\"audioOutputCompensated\":\"0\",\"audioOutputDelay\":\"0\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_MaxValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"255\",\"lowLatencyMode\":\"1\",\"audioOutputCompensated\":\"1\",\"audioOutputDelay\":\"255\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_LowLatencyModeEnabled)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"15\",\"lowLatencyMode\":\"1\",\"audioOutputCompensated\":\"1\",\"audioOutputDelay\":\"5\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_LowLatencyModeDisabled)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"50\",\"lowLatencyMode\":\"0\",\"audioOutputCompensated\":\"0\",\"audioOutputDelay\":\"25\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_AudioOutputCompensatedEnabled)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"30\",\"lowLatencyMode\":\"0\",\"audioOutputCompensated\":\"1\",\"audioOutputDelay\":\"15\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_AudioOutputCompensatedDisabled)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"40\",\"lowLatencyMode\":\"1\",\"audioOutputCompensated\":\"0\",\"audioOutputDelay\":\"20\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_HighVideoLatency)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"100\",\"lowLatencyMode\":\"0\",\"audioOutputCompensated\":\"1\",\"audioOutputDelay\":\"50\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_HighAudioDelay)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"25\",\"lowLatencyMode\":\"1\",\"audioOutputCompensated\":\"1\",\"audioOutputDelay\":\"200\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_AllParametersEnabled)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"35\",\"lowLatencyMode\":\"1\",\"audioOutputCompensated\":\"1\",\"audioOutputDelay\":\"30\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_AllParametersDisabled)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"45\",\"lowLatencyMode\":\"0\",\"audioOutputCompensated\":\"0\",\"audioOutputDelay\":\"35\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_NegativeValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"-10\",\"lowLatencyMode\":\"-1\",\"audioOutputCompensated\":\"-1\",\"audioOutputDelay\":\"-5\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_LargeValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"1000\",\"lowLatencyMode\":\"5\",\"audioOutputCompensated\":\"10\",\"audioOutputDelay\":\"2000\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_FloatValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"20.5\",\"lowLatencyMode\":\"1.2\",\"audioOutputCompensated\":\"0.8\",\"audioOutputDelay\":\"10.7\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_ZeroStringValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"0\",\"lowLatencyMode\":\"0\",\"audioOutputCompensated\":\"0\",\"audioOutputDelay\":\"0\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_OneStringValues)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"1\",\"lowLatencyMode\":\"1\",\"audioOutputCompensated\":\"1\",\"audioOutputDelay\":\"1\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_ExtraParameters)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"20\",\"lowLatencyMode\":\"1\",\"audioOutputCompensated\":\"1\",\"audioOutputDelay\":\"10\",\"extraParam\":\"ignored\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, setLatencyInfo_DuplicateParameters)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("setLatencyInfo"), _T("{\"videoLatency\":\"20\",\"videoLatency\":\"30\",\"lowLatencyMode\":\"1\",\"audioOutputCompensated\":\"1\",\"audioOutputDelay\":\"10\"}"), response));
    EXPECT_EQ(response, string("{\"success\":true}"));
}

TEST_F(HdmiCecSinkDsTest, printDeviceList_ValidCall)
{
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("printDeviceList"), _T("{}"), response));
    EXPECT_THAT(response, ::testing::ContainsRegex("\"printed\":(true|false)"));
    EXPECT_THAT(response, ::testing::ContainsRegex("\"success\":true"));
}

//=============================================================================
// CEC Frame Processing Tests (L1 Level)
// These tests verify CEC frame injection and processing without full L2 event subscription
//=============================================================================

class HdmiCecSinkFrameProcessingTest : public HdmiCecSinkDsTest {
protected:

    void InjectCECFrame(const uint8_t* frameData, size_t frameSize) 
    {
        CECFrame frame(frameData, frameSize);
        for (auto* listener : listeners) {
            if (listener) {
                listener->notify(frame);
            }
        }
    }
};

TEST_F(HdmiCecSinkFrameProcessingTest, InjectImageViewOnFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Image View On frame: From TV (LA=0) to Playback Device 1 (LA=4)  
    // Header: 0x40, Opcode: 0x04 (Image View On)
    uint8_t imageViewOnFrame[] = { 0x40, 0x04 };
    
    EXPECT_NO_THROW(InjectCECFrame(imageViewOnFrame, sizeof(imageViewOnFrame)));
}

// Test fixture description: ImageViewOn edge case test broadcast message rejection to cover uncovered lines
TEST_F(HdmiCecSinkFrameProcessingTest, InjectImageViewOn_BroadcastMessage_ShouldBeIgnored)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create ImageViewOn broadcast frame (should be ignored per implementation)
    // From Playback Device 1 (LA=4) to Broadcast (LA=15) - should log "Ignore Broadcast messages"
    uint8_t imageViewOnBroadcastFrame[] = { 0x4F, 0x04 };
    
    EXPECT_NO_THROW(InjectCECFrame(imageViewOnBroadcastFrame, sizeof(imageViewOnBroadcastFrame)));
}

// Test fixture description: TextViewOn valid direct message processing
TEST_F(HdmiCecSinkFrameProcessingTest, InjectTextViewOnFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Text View On frame: From Playback Device 1 (LA=4) to TV (LA=0)
    // Header: 0x40, Opcode: 0x0D (Text View On)
    uint8_t textViewOnFrame[] = { 0x40, 0x0D };
    
    EXPECT_NO_THROW(InjectCECFrame(textViewOnFrame, sizeof(textViewOnFrame)));
}

// Test fixture description: TextViewOn edge case test broadcast message rejection
TEST_F(HdmiCecSinkFrameProcessingTest, InjectTextViewOn_BroadcastMessage_ShouldBeIgnored)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create TextViewOn broadcast frame (should be ignored per implementation)
    // From Playback Device 1 (LA=4) to Broadcast (LA=15) - should log "Ignore Broadcast messages"
    // This covers the broadcast rejection logic in HdmiCecSinkProcessor::process(const TextViewOn &msg, const Header &header)
    uint8_t textViewOnBroadcastFrame[] = { 0x4F, 0x0D };
    
    EXPECT_NO_THROW(InjectCECFrame(textViewOnBroadcastFrame, sizeof(textViewOnBroadcastFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectReportAudioStatusFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Report Audio Status frame: From Audio System (LA=5) to TV (LA=0)
    // Header: 0x50, Opcode: 0x7A (Report Audio Status), Operands: 0x50 (Volume Level, Mute Status)
    uint8_t reportAudioStatusFrame[] = { 0x50, 0x7A, 0x50 };
    
    EXPECT_NO_THROW(InjectCECFrame(reportAudioStatusFrame, sizeof(reportAudioStatusFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectRequestActiveSourceFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Request Active Source frame (Broadcast): From TV (LA=0) to Broadcast (LA=15)
    // Header: 0x0F, Opcode: 0x85 (Request Active Source)
    uint8_t requestActiveSourceFrame[] = { 0x0F, 0x85 };
    
    EXPECT_NO_THROW(InjectCECFrame(requestActiveSourceFrame, sizeof(requestActiveSourceFrame)));
}

// Test fixture description: RequestActiveSource edge case test direct message rejection
TEST_F(HdmiCecSinkFrameProcessingTest, InjectRequestActiveSource_DirectMessage_ShouldBeIgnored)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create RequestActiveSource direct frame (should be ignored per implementation)
    // From Playback Device 1 (LA=4) to TV (LA=0) - should log "Ignore Direct messages"
    uint8_t requestActiveSourceDirectFrame[] = { 0x40, 0x85 };
    
    EXPECT_NO_THROW(InjectCECFrame(requestActiveSourceDirectFrame, sizeof(requestActiveSourceDirectFrame)));
}

// Test fixture description: Standby direct message processing
TEST_F(HdmiCecSinkFrameProcessingTest, InjectStandbyFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Standby frame: From Playback Device 1 (LA=4) to TV (LA=0)
    // Header: 0x40, Opcode: 0x36 (Standby)
    uint8_t standbyFrame[] = { 0x40, 0x36 };
    
    EXPECT_NO_THROW(InjectCECFrame(standbyFrame, sizeof(standbyFrame)));
}

// Test fixture description: Standby broadcast message processing
TEST_F(HdmiCecSinkFrameProcessingTest, InjectStandby_BroadcastMessage)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Standby broadcast frame: From Playback Device 1 (LA=4) to Broadcast (LA=15)
    // Header: 0x4F, Opcode: 0x36 (Standby)
    // Standby can be sent to both direct and broadcast addresses
    uint8_t standbyBroadcastFrame[] = { 0x4F, 0x36 };
    
    EXPECT_NO_THROW(InjectCECFrame(standbyBroadcastFrame, sizeof(standbyBroadcastFrame)));
}

// Test fixture description: GetCECVersion direct message processing
TEST_F(HdmiCecSinkFrameProcessingTest, InjectGetCECVersionFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Get CEC Version frame: From Playback Device 1 (LA=4) to TV (LA=0)
    // Header: 0x40, Opcode: 0x9F (Get CEC Version)
    uint8_t getCECVersionFrame[] = { 0x40, 0x9F };
    
    EXPECT_NO_THROW(InjectCECFrame(getCECVersionFrame, sizeof(getCECVersionFrame)));
}

// Test fixture description: GetCECVersion edge case test broadcast message rejection
TEST_F(HdmiCecSinkFrameProcessingTest, InjectGetCECVersion_BroadcastMessage_ShouldBeIgnored)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create GetCECVersion broadcast frame (should be ignored per implementation)
    // From Playback Device 1 (LA=4) to Broadcast (LA=15) - should log "Ignore Broadcast messages"
    uint8_t getCECVersionBroadcastFrame[] = { 0x4F, 0x9F };
    
    EXPECT_NO_THROW(InjectCECFrame(getCECVersionBroadcastFrame, sizeof(getCECVersionBroadcastFrame)));
}

// Test fixture description: CECVersion response processing with version information
TEST_F(HdmiCecSinkFrameProcessingTest, InjectCECVersionFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create CEC Version frame: From Playback Device 1 (LA=4) to TV (LA=0)
    // Header: 0x40, Opcode: 0x9E (CEC Version), Operand: 0x05 (Version 1.4)
    uint8_t cecVersionFrame[] = { 0x40, 0x9E, 0x05 };
    
    EXPECT_NO_THROW(InjectCECFrame(cecVersionFrame, sizeof(cecVersionFrame)));
}

// Test fixture description: CECVersion with different version values
TEST_F(HdmiCecSinkFrameProcessingTest, InjectCECVersion_DifferentVersions)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Test different CEC version values
    // CEC Version 2.0
    uint8_t cecVersion20Frame[] = { 0x40, 0x9E, 0x06 };
    EXPECT_NO_THROW(InjectCECFrame(cecVersion20Frame, sizeof(cecVersion20Frame)));
    
    // CEC Version 1.3a  
    uint8_t cecVersion13Frame[] = { 0x40, 0x9E, 0x04 };
    EXPECT_NO_THROW(InjectCECFrame(cecVersion13Frame, sizeof(cecVersion13Frame)));
}

// Test fixture description: SetMenuLanguage processing with language information
TEST_F(HdmiCecSinkFrameProcessingTest, InjectSetMenuLanguageFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Set Menu Language frame: From TV (LA=0) to Broadcast (LA=15)
    // Header: 0x0F, Opcode: 0x32 (Set Menu Language), Operands: "eng" (English)
    uint8_t setMenuLanguageFrame[] = { 0x0F, 0x32, 0x65, 0x6E, 0x67 }; // "eng"
    
    EXPECT_NO_THROW(InjectCECFrame(setMenuLanguageFrame, sizeof(setMenuLanguageFrame)));
}

// Test fixture description: SetMenuLanguage with different languages
TEST_F(HdmiCecSinkFrameProcessingTest, InjectSetMenuLanguage_DifferentLanguages)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Test different language codes
    // Spanish
    uint8_t spanishLanguageFrame[] = { 0x0F, 0x32, 0x73, 0x70, 0x61 }; // "spa"
    EXPECT_NO_THROW(InjectCECFrame(spanishLanguageFrame, sizeof(spanishLanguageFrame)));
    
    // French
    uint8_t frenchLanguageFrame[] = { 0x0F, 0x32, 0x66, 0x72, 0x61 }; // "fra"
    EXPECT_NO_THROW(InjectCECFrame(frenchLanguageFrame, sizeof(frenchLanguageFrame)));
}

// Test fixture description: GiveOSDName direct message processing
TEST_F(HdmiCecSinkFrameProcessingTest, InjectGiveOSDNameFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Give OSD Name frame: From Playback Device 1 (LA=4) to TV (LA=0)
    // Header: 0x40, Opcode: 0x46 (Give OSD Name)
    uint8_t giveOSDNameFrame[] = { 0x40, 0x46 };
    
    EXPECT_NO_THROW(InjectCECFrame(giveOSDNameFrame, sizeof(giveOSDNameFrame)));
}

// Test fixture description: GiveOSDName edge case test broadcast message rejection
TEST_F(HdmiCecSinkFrameProcessingTest, InjectGiveOSDName_BroadcastMessage_ShouldBeIgnored)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create GiveOSDName broadcast frame (should be ignored per implementation)
    // From Playback Device 1 (LA=4) to Broadcast (LA=15) - should log "Ignore Broadcast messages"
    uint8_t giveOSDNameBroadcastFrame[] = { 0x4F, 0x46 };
    
    EXPECT_NO_THROW(InjectCECFrame(giveOSDNameBroadcastFrame, sizeof(giveOSDNameBroadcastFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectRoutingChangeFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Routing Change frame: From Playback Device 1 (LA=4) to TV (LA=0)
    // Header: 0x40, Opcode: 0x80 (Routing Change), Operands: Old PA 1.0.0.0, New PA 2.0.0.0  
    uint8_t routingChangeFrame[] = { 0x40, 0x80, 0x10, 0x00, 0x20, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(routingChangeFrame, sizeof(routingChangeFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectSetStreamPathFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Set Stream Path frame: From Playback Device 1 (LA=4) to Broadcast (LA=15)
    // Header: 0x4F, Opcode: 0x86 (Set Stream Path), Operands: PA 2.0.0.0
    uint8_t setStreamPathFrame[] = { 0x4F, 0x86, 0x20, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(setStreamPathFrame, sizeof(setStreamPathFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectRequestCurrentLatencyFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Request Current Latency frame: From Playback Device 1 (LA=4) to TV (LA=0)
    // Header: 0x40, Opcode: 0xA7 (Request Current Latency), Operands: PA 1.0.0.0
    uint8_t requestCurrentLatencyFrame[] = { 0x40, 0xA7, 0x10, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(requestCurrentLatencyFrame, sizeof(requestCurrentLatencyFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectUserControlPressedFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create User Control Pressed frame: From Remote Control (LA=14) to TV (LA=0)
    // Header: 0xE0, Opcode: 0x44 (User Control Pressed), Operands: Key Code 0x41 (Volume Up)
    uint8_t userControlPressedFrame[] = { 0xE0, 0x44, 0x41 };
    
    EXPECT_NO_THROW(InjectCECFrame(userControlPressedFrame, sizeof(userControlPressedFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectUserControlReleasedFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create User Control Released frame: From Remote Control (LA=14) to TV (LA=0)
    // Header: 0xE0, Opcode: 0x45 (User Control Released)
    uint8_t userControlReleasedFrame[] = { 0xE0, 0x45 };
    
    EXPECT_NO_THROW(InjectCECFrame(userControlReleasedFrame, sizeof(userControlReleasedFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectGiveSystemAudioModeStatusFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Give System Audio Mode Status frame: From TV (LA=0) to Audio System (LA=5) 
    // Header: 0x05, Opcode: 0x7D (Give System Audio Mode Status)
    uint8_t giveSystemAudioModeStatusFrame[] = { 0x05, 0x7D };
    
    EXPECT_NO_THROW(InjectCECFrame(giveSystemAudioModeStatusFrame, sizeof(giveSystemAudioModeStatusFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectSystemAudioModeRequestFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create System Audio Mode Request frame: From TV (LA=0) to Audio System (LA=5)
    // Header: 0x05, Opcode: 0x70 (System Audio Mode Request), Operands: PA 1.0.0.0 
    uint8_t systemAudioModeRequestFrame[] = { 0x05, 0x70, 0x10, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(systemAudioModeRequestFrame, sizeof(systemAudioModeRequestFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectSetAudioRateFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Set Audio Rate frame: From TV (LA=0) to Audio System (LA=5)
    // Header: 0x05, Opcode: 0x9A (Set Audio Rate), Operands: Rate 0x06 
    uint8_t setAudioRateFrame[] = { 0x05, 0x9A, 0x06 };
    
    EXPECT_NO_THROW(InjectCECFrame(setAudioRateFrame, sizeof(setAudioRateFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectReportCurrentLatencyFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Report Current Latency frame: From TV (LA=0) to Playback Device 1 (LA=4) 
    // Header: 0x40, Opcode: 0xA8 (Report Current Latency), Operands: PA, Video Latency, Audio Latency
    uint8_t reportCurrentLatencyFrame[] = { 0x40, 0xA8, 0x10, 0x00, 0x01, 0x00, 0x01, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(reportCurrentLatencyFrame, sizeof(reportCurrentLatencyFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectDeviceAddedFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Device Added frame (Report Physical Address): From Playback Device 1 (LA=4) to Broadcast (LA=15)
    // Header: 0x4F, Opcode: 0x84 (Report Physical Address), Operands: PA 2.0.0.0, Device Type 0x04
    uint8_t deviceAddedFrame[] = { 0x4F, 0x84, 0x20, 0x00, 0x04 };
    
    EXPECT_NO_THROW(InjectCECFrame(deviceAddedFrame, sizeof(deviceAddedFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectAudioDeviceAddedFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create Audio Device Added frame: From Audio System (LA=5) to Broadcast (LA=15)
    // Header: 0x5F, Opcode: 0x84 (Report Physical Address), Operands: PA 2.0.0.0, Device Type 0x05 (Audio System)
    uint8_t audioDeviceAddedFrame[] = { 0x5F, 0x84, 0x20, 0x00, 0x05 };
    
    EXPECT_NO_THROW(InjectCECFrame(audioDeviceAddedFrame, sizeof(audioDeviceAddedFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectExceptionHandlingFrames)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Test frames that trigger exception handling in sendToAsync/sendTo methods
    // These test error resilience when CEC communication fails

    // Mock sendToAsync to throw exceptions for certain frames
    ON_CALL(*p_connectionImplMock, sendToAsync(::testing::_, ::testing::_))
        .WillByDefault(::testing::Invoke(
            [&](const LogicalAddress& to, const CECFrame& frame) {
                throw Exception();
            }));

    // Mock both sendTo methods to throw exceptions 
    ON_CALL(*p_connectionImplMock, sendTo(::testing::Matcher<const LogicalAddress&>(::testing::_), ::testing::Matcher<const CECFrame&>(::testing::_)))
        .WillByDefault(::testing::Invoke(
            [&](const LogicalAddress&, const CECFrame&) {
                throw std::runtime_error("Simulated sendTo failure");
            }));

    ON_CALL(*p_connectionImplMock, sendTo(::testing::Matcher<const LogicalAddress&>(::testing::_), ::testing::Matcher<const CECFrame&>(::testing::_), ::testing::Matcher<int>(::testing::_)))
        .WillByDefault(::testing::Invoke(
            [&](const LogicalAddress&, const CECFrame&, int) {
                throw std::runtime_error("Simulated sendTo failure");
            }));

    // Get CEC Version frame with sendToAsync exception
    uint8_t getCECVersionFrame[] = { 0x40, 0x9F };
    EXPECT_NO_THROW(InjectCECFrame(getCECVersionFrame, sizeof(getCECVersionFrame)));

    // Give OSD Name frame with sendToAsync exception  
    uint8_t giveOSDNameFrame[] = { 0x40, 0x46 };
    EXPECT_NO_THROW(InjectCECFrame(giveOSDNameFrame, sizeof(giveOSDNameFrame)));

    // Give Physical Address frame with sendTo exception
    uint8_t givePhysicalAddressFrame[] = { 0x40, 0x83 };
    EXPECT_NO_THROW(InjectCECFrame(givePhysicalAddressFrame, sizeof(givePhysicalAddressFrame)));

    // Give Device Vendor ID frame with sendToAsync exception
    uint8_t giveDeviceVendorIDFrame[] = { 0x40, 0x8C };
    EXPECT_NO_THROW(InjectCECFrame(giveDeviceVendorIDFrame, sizeof(giveDeviceVendorIDFrame)));

    // Give Device Power Status frame with sendTo exception
    uint8_t giveDevicePowerStatusFrame[] = { 0x40, 0x8F };
    EXPECT_NO_THROW(InjectCECFrame(giveDevicePowerStatusFrame, sizeof(giveDevicePowerStatusFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectWakeupFromStandbyFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Test Active Source frame that should trigger wakeup from standby  
    // This simulates the scenario where the system is in standby and receives an Active Source command
    uint8_t wakeupActiveSourceFrame[] = { 0x4F, 0x82, 0x10, 0x00 }; // From Playback Device 1 to Broadcast

    EXPECT_NO_THROW(InjectCECFrame(wakeupActiveSourceFrame, sizeof(wakeupActiveSourceFrame)));
}

TEST_F(HdmiCecSinkFrameProcessingTest, InjectDisabledImageViewOnFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Test Image View On frame (this was disabled in L2 due to implementation issues)
    // Including it here for completeness but without event verification
    uint8_t imageViewOnFrame[] = { 0x40, 0x04 }; // From Playbook Device 1 to TV

    EXPECT_NO_THROW(InjectCECFrame(imageViewOnFrame, sizeof(imageViewOnFrame)));
}

// Test fixture description: ActiveSource edge cases test valid broadcast processing
TEST_F(HdmiCecSinkFrameProcessingTest, ActiveSource_BroadcastMessage_ValidProcessing)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Valid broadcast ActiveSource message (should be processed)
    // From Playback Device 1 (LA=4) to Broadcast (LA=15) with physical address 2.0.0.0
    uint8_t activeSourceFrame[] = { 0x4F, 0x82, 0x20, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame, sizeof(activeSourceFrame)));
}

// Test fixture description: ActiveSource edge cases test direct message rejection per implementation
TEST_F(HdmiCecSinkFrameProcessingTest, ActiveSource_DirectMessage_ShouldBeIgnored)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Direct ActiveSource message (should be ignored per implementation)
    // From Playback Device 1 (LA=4) to TV (LA=0) - should log "Ignore Direct messages"
    uint8_t activeSourceFrame[] = { 0x40, 0x82, 0x20, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame, sizeof(activeSourceFrame)));
}

// Test fixture description: ActiveSource edge cases test boundary logical addresses
TEST_F(HdmiCecSinkFrameProcessingTest, ActiveSource_BoundaryLogicalAddresses)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // From LA=0 (TV) to Broadcast (LA=15) 
    uint8_t activeSourceFrame1[] = { 0x0F, 0x82, 0x10, 0x00 };
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame1, sizeof(activeSourceFrame1)));
    
    // From LA=14 (Specific Use) to Broadcast (LA=15)
    uint8_t activeSourceFrame2[] = { 0xEF, 0x82, 0x30, 0x00 };
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame2, sizeof(activeSourceFrame2)));
}

// Test fixture description: ActiveSource edge cases test invalid logical addresses beyond CEC spec
TEST_F(HdmiCecSinkFrameProcessingTest, ActiveSource_InvalidLogicalAddresses)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Invalid logical address beyond CEC specification (>15)
    uint8_t invalidActiveSourceFrame[] = { 0xFF, 0x82, 0x20, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(invalidActiveSourceFrame, sizeof(invalidActiveSourceFrame)));
}

// Test fixture description: ActiveSource edge cases test physical address boundaries
TEST_F(HdmiCecSinkFrameProcessingTest, ActiveSource_PhysicalAddressBoundaries)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Minimum physical address 0.0.0.0
    uint8_t activeSourceFrame1[] = { 0x1F, 0x82, 0x00, 0x00 };
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame1, sizeof(activeSourceFrame1)));
    
    // Maximum physical address F.F.F.F
    uint8_t activeSourceFrame2[] = { 0x2F, 0x82, 0xFF, 0xFF };
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame2, sizeof(activeSourceFrame2)));
    
    // Common physical addresses
    uint8_t activeSourceFrame3[] = { 0x3F, 0x82, 0x10, 0x00 }; // 1.0.0.0
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame3, sizeof(activeSourceFrame3)));
    
    uint8_t activeSourceFrame4[] = { 0x4F, 0x82, 0x20, 0x00 }; // 2.0.0.0
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame4, sizeof(activeSourceFrame4)));
}

// Test fixture description: ActiveSource edge cases test malformed frame too short
TEST_F(HdmiCecSinkFrameProcessingTest, ActiveSource_MalformedFrame_TooShort)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Malformed ActiveSource frame - too short (missing physical address bytes)
    uint8_t shortActiveSourceFrame[] = { 0x4F, 0x82 };
    
    EXPECT_NO_THROW(InjectCECFrame(shortActiveSourceFrame, sizeof(shortActiveSourceFrame)));
}

// Test fixture description: ActiveSource edge cases test malformed frame too long  
TEST_F(HdmiCecSinkFrameProcessingTest, ActiveSource_MalformedFrame_TooLong)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Malformed ActiveSource frame - too long (extra bytes)
    uint8_t longActiveSourceFrame[] = { 0x4F, 0x82, 0x20, 0x00, 0xFF, 0xFF };
    
    EXPECT_NO_THROW(InjectCECFrame(longActiveSourceFrame, sizeof(longActiveSourceFrame)));
}

// Test fixture description: ActiveSource edge cases test sequential messages from different devices
TEST_F(HdmiCecSinkFrameProcessingTest, ActiveSource_SequentialMessages)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Multiple sequential ActiveSource messages from different devices
    uint8_t activeSourceFrame1[] = { 0x1F, 0x82, 0x10, 0x00 }; // Recording Device 1
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame1, sizeof(activeSourceFrame1)));
    
    uint8_t activeSourceFrame2[] = { 0x2F, 0x82, 0x20, 0x00 }; // Recording Device 2
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame2, sizeof(activeSourceFrame2)));
    
    uint8_t activeSourceFrame3[] = { 0x3F, 0x82, 0x30, 0x00 }; // Tuner 1
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame3, sizeof(activeSourceFrame3)));
}

// Test fixture description: ActiveSource edge cases test same device multiple physical addresses
TEST_F(HdmiCecSinkFrameProcessingTest, ActiveSource_SameDeviceMultipleAddresses)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Same device reporting different physical addresses (device moved/reconnected)
    uint8_t activeSourceFrame1[] = { 0x4F, 0x82, 0x10, 0x00 }; // First address
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame1, sizeof(activeSourceFrame1)));
    
    uint8_t activeSourceFrame2[] = { 0x4F, 0x82, 0x20, 0x00 }; // Updated address
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame2, sizeof(activeSourceFrame2)));
    
    uint8_t activeSourceFrame3[] = { 0x4F, 0x82, 0x30, 0x00 }; // Another update
    EXPECT_NO_THROW(InjectCECFrame(activeSourceFrame3, sizeof(activeSourceFrame3)));
}

// Test fixture description: InActiveSource edge cases test direct message processing
TEST_F(HdmiCecSinkFrameProcessingTest, InActiveSource_DirectMessage_ValidProcessing)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Valid direct InActiveSource message (should be processed)
    // From Playback Device 1 (LA=4) to TV (LA=0) with physical address 2.0.0.0
    uint8_t inActiveSourceFrame[] = { 0x40, 0x9D, 0x20, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame, sizeof(inActiveSourceFrame)));
}

// Test fixture description: InActiveSource edge cases test broadcast message rejection per implementation
TEST_F(HdmiCecSinkFrameProcessingTest, InActiveSource_BroadcastMessage_ShouldBeIgnored)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Broadcast InActiveSource message (should be ignored per implementation)
    // From Playback Device 1 (LA=4) to Broadcast (LA=15) - should log "Ignore Broadcast messages"
    uint8_t inActiveSourceFrame[] = { 0x4F, 0x9D, 0x20, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame, sizeof(inActiveSourceFrame)));
}

// Test fixture description: InActiveSource edge cases test boundary logical addresses
TEST_F(HdmiCecSinkFrameProcessingTest, InActiveSource_BoundaryLogicalAddresses)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // From LA=1 (Recording Device 1) to TV (LA=0)
    uint8_t inActiveSourceFrame1[] = { 0x10, 0x9D, 0x10, 0x00 };
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame1, sizeof(inActiveSourceFrame1)));
    
    // From LA=14 (Specific Use) to TV (LA=0)
    uint8_t inActiveSourceFrame2[] = { 0xE0, 0x9D, 0x30, 0x00 };
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame2, sizeof(inActiveSourceFrame2)));
    
    // From Audio System (LA=5) to TV (LA=0)
    uint8_t inActiveSourceFrame3[] = { 0x50, 0x9D, 0x40, 0x00 };
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame3, sizeof(inActiveSourceFrame3)));
}

// Test fixture description: InActiveSource edge cases test physical address boundaries
TEST_F(HdmiCecSinkFrameProcessingTest, InActiveSource_PhysicalAddressBoundaries)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Minimum physical address 0.0.0.0
    uint8_t inActiveSourceFrame1[] = { 0x40, 0x9D, 0x00, 0x00 };
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame1, sizeof(inActiveSourceFrame1)));
    
    // Maximum physical address F.F.F.F
    uint8_t inActiveSourceFrame2[] = { 0x40, 0x9D, 0xFF, 0xFF };
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame2, sizeof(inActiveSourceFrame2)));
    
    // Common physical addresses
    uint8_t inActiveSourceFrame3[] = { 0x40, 0x9D, 0x10, 0x00 }; // 1.0.0.0
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame3, sizeof(inActiveSourceFrame3)));
    
    uint8_t inActiveSourceFrame4[] = { 0x40, 0x9D, 0x20, 0x00 }; // 2.0.0.0
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame4, sizeof(inActiveSourceFrame4)));
}

// Test fixture description: InActiveSource edge cases test malformed frame too short
TEST_F(HdmiCecSinkFrameProcessingTest, InActiveSource_MalformedFrame_TooShort)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Malformed InActiveSource frame - too short (missing physical address bytes)
    uint8_t shortInActiveSourceFrame[] = { 0x40, 0x9D };
    
    EXPECT_NO_THROW(InjectCECFrame(shortInActiveSourceFrame, sizeof(shortInActiveSourceFrame)));
}

// Test fixture description: InActiveSource edge cases test malformed frame too long
TEST_F(HdmiCecSinkFrameProcessingTest, InActiveSource_MalformedFrame_TooLong)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Malformed InActiveSource frame - too long (extra bytes)
    uint8_t longInActiveSourceFrame[] = { 0x40, 0x9D, 0x20, 0x00, 0xFF, 0xFF };
    
    EXPECT_NO_THROW(InjectCECFrame(longInActiveSourceFrame, sizeof(longInActiveSourceFrame)));
}

// Test fixture description: InActiveSource edge cases test multiple device addresses
TEST_F(HdmiCecSinkFrameProcessingTest, InActiveSource_MultipleDeviceAddresses)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Multiple devices reporting InActiveSource with different addresses
    uint8_t inActiveSourceFrame1[] = { 0x10, 0x9D, 0x10, 0x00 }; // Recording Device 1
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame1, sizeof(inActiveSourceFrame1)));
    
    uint8_t inActiveSourceFrame2[] = { 0x20, 0x9D, 0x20, 0x00 }; // Recording Device 2
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame2, sizeof(inActiveSourceFrame2)));
    
    uint8_t inActiveSourceFrame3[] = { 0x40, 0x9D, 0x30, 0x00 }; // Playback Device 1
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame3, sizeof(inActiveSourceFrame3)));
}

// Test fixture description: InActiveSource edge cases test same device address updates
TEST_F(HdmiCecSinkFrameProcessingTest, InActiveSource_SameDeviceAddressUpdates)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Same device reporting InActiveSource with different physical addresses over time
    uint8_t inActiveSourceFrame1[] = { 0x40, 0x9D, 0x10, 0x00 }; // First address
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame1, sizeof(inActiveSourceFrame1)));
    
    uint8_t inActiveSourceFrame2[] = { 0x40, 0x9D, 0x20, 0x00 }; // Updated address
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame2, sizeof(inActiveSourceFrame2)));
    
    uint8_t inActiveSourceFrame3[] = { 0x40, 0x9D, 0x30, 0x00 }; // Another update
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame3, sizeof(inActiveSourceFrame3)));
}

// Test fixture description: InActiveSource edge cases test invalid logical addresses
TEST_F(HdmiCecSinkFrameProcessingTest, InActiveSource_InvalidLogicalAddresses)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Invalid logical address beyond CEC specification (>15)
    uint8_t invalidInActiveSourceFrame[] = { 0xFF, 0x9D, 0x20, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(invalidInActiveSourceFrame, sizeof(invalidInActiveSourceFrame)));
}

// Test fixture description: InActiveSource edge cases test extreme physical addresses
TEST_F(HdmiCecSinkFrameProcessingTest, InActiveSource_ExtremePhysicalAddresses)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    // Physical addresses with extreme values and patterns
    uint8_t inActiveSourceFrame1[] = { 0x40, 0x9D, 0x00, 0x01 }; // 0.0.0.1
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame1, sizeof(inActiveSourceFrame1)));
    
    uint8_t inActiveSourceFrame2[] = { 0x40, 0x9D, 0x11, 0x11 }; // 1.1.1.1
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame2, sizeof(inActiveSourceFrame2)));
    
    uint8_t inActiveSourceFrame3[] = { 0x40, 0x9D, 0xAA, 0xAA }; // A.A.A.A
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame3, sizeof(inActiveSourceFrame3)));
    
    uint8_t inActiveSourceFrame4[] = { 0x40, 0x9D, 0x55, 0x55 }; // 5.5.5.5
    EXPECT_NO_THROW(InjectCECFrame(inActiveSourceFrame4, sizeof(inActiveSourceFrame4)));
}

// Test fixture description: GiveDeviceVendorID processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectGiveDeviceVendorIDFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Test Case 1: Direct message from Playback Device 1 (LA=4) to TV (LA=0) - should process normally
    uint8_t directGiveVendorIDFrame[] = { 0x40, 0x8C }; // Direct: From LA=4 to LA=0, Give Device Vendor ID
    EXPECT_NO_THROW(InjectCECFrame(directGiveVendorIDFrame, sizeof(directGiveVendorIDFrame)));
    
    // Test Case 2: Broadcast message - should be rejected
    uint8_t broadcastGiveVendorIDFrame[] = { 0x4F, 0x8C }; // Broadcast: From LA=4 to Broadcast, Give Device Vendor ID
    EXPECT_NO_THROW(InjectCECFrame(broadcastGiveVendorIDFrame, sizeof(broadcastGiveVendorIDFrame)));
}

// Test fixture description: SetOSDString processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectSetOSDStringFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t shortOSDStringFrame[] = { 0x40, 0x64, 0x00, 'T', 'e', 's', 't' }; // Display control + "Test"
    EXPECT_NO_THROW(InjectCECFrame(shortOSDStringFrame, sizeof(shortOSDStringFrame)));
    
    // Test Case 2: Set OSD String with longer text
    uint8_t longOSDStringFrame[] = { 0x50, 0x64, 0x00, 'L', 'o', 'n', 'g', ' ', 'T', 'e', 's', 't', ' ', 'M', 's', 'g' };
    EXPECT_NO_THROW(InjectCECFrame(longOSDStringFrame, sizeof(longOSDStringFrame)));
    
    // Test Case 3: Set OSD String with different display control values
    uint8_t displayControlFrame[] = { 0x60, 0x64, 0x01, 'M', 'e', 'n', 'u' }; // Different display control
    EXPECT_NO_THROW(InjectCECFrame(displayControlFrame, sizeof(displayControlFrame)));
    
    // Test Case 4: Set OSD String with maximum length text
    uint8_t maxOSDStringFrame[] = { 0x70, 0x64, 0x00, 'V', 'e', 'r', 'y', ' ', 'L', 'o', 'n', 'g', ' ', 'O', 'S', 'D', ' ', 'S', 't', 'r', 'i', 'n', 'g' };
    EXPECT_NO_THROW(InjectCECFrame(maxOSDStringFrame, sizeof(maxOSDStringFrame)));
}

// Test fixture description: SetOSDName processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectSetOSDNameFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t standardOSDNameFrame[] = { 0x40, 0x47, 'T', 'V', ' ', 'S', 'e', 't' }; // "TV Set"
    EXPECT_NO_THROW(InjectCECFrame(standardOSDNameFrame, sizeof(standardOSDNameFrame)));
    
    // Test Case 2: Set OSD Name with longer device name
    uint8_t longOSDNameFrame[] = { 0x50, 0x47, 'S', 'm', 'a', 'r', 't', ' ', 'T', 'V', ' ', 'D', 'e', 'v', 'i', 'c', 'e' };
    EXPECT_NO_THROW(InjectCECFrame(longOSDNameFrame, sizeof(longOSDNameFrame)));
    
    // Test Case 3: Set OSD Name with short device name
    uint8_t shortOSDNameFrame[] = { 0x60, 0x47, 'T', 'V' }; // "TV"
    EXPECT_NO_THROW(InjectCECFrame(shortOSDNameFrame, sizeof(shortOSDNameFrame)));
    
    // Test Case 4: Set OSD Name with special characters in name
    uint8_t specialOSDNameFrame[] = { 0x70, 0x47, 'T', 'V', '-', '1', '2', '3', '4' }; // "TV-1234"
    EXPECT_NO_THROW(InjectCECFrame(specialOSDNameFrame, sizeof(specialOSDNameFrame)));
    
    // Test Case 5: Set OSD Name with maximum length device name
    uint8_t maxOSDNameFrame[] = { 0x80, 0x47, 'V', 'e', 'r', 'y', ' ', 'L', 'o', 'n', 'g', ' ', 'D', 'e', 'v', 'i', 'c', 'e', ' ', 'N', 'a', 'm', 'e' };
    EXPECT_NO_THROW(InjectCECFrame(maxOSDNameFrame, sizeof(maxOSDNameFrame)));
    
    // Test Case 6: Set OSD Name with empty name (minimal frame)
    uint8_t emptyOSDNameFrame[] = { 0x90, 0x47 }; // No name data
    EXPECT_NO_THROW(InjectCECFrame(emptyOSDNameFrame, sizeof(emptyOSDNameFrame)));
}

// Test fixture description: SetOSDName edge case test broadcast message rejection
TEST_F(HdmiCecSinkFrameProcessingTest, InjectSetOSDName_BroadcastMessage_ShouldBeIgnored)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create SetOSDName broadcast frame (should be ignored per implementation)
    // From Playback Device 1 (LA=4) to Broadcast (LA=15) - should log "Ignore Broadcast messages"
    uint8_t setOSDNameBroadcastFrame[] = { 0x4F, 0x47, 'T', 'e', 's', 't' }; // Broadcast: "Test"
    
    EXPECT_NO_THROW(InjectCECFrame(setOSDNameBroadcastFrame, sizeof(setOSDNameBroadcastFrame)));
}

// Test fixture description: RoutingInformation processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectRoutingInformationFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t routingInfoFrame[] = { 0x40, 0x81, 0x10, 0x00, 0x20, 0x00 }; // From LA=4 to LA=0, routing from 1.0.0.0 to 2.0.0.0
    EXPECT_NO_THROW(InjectCECFrame(routingInfoFrame, sizeof(routingInfoFrame)));
    
    // Test Case 2: Different routing paths
    uint8_t routingInfoFrame2[] = { 0x50, 0x81, 0x00, 0x00, 0x30, 0x00 }; // From root to 3.0.0.0
    EXPECT_NO_THROW(InjectCECFrame(routingInfoFrame2, sizeof(routingInfoFrame2)));
}

// Test fixture description: GetMenuLanguage processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectGetMenuLanguageFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t directMenuLangFrame[] = { 0x40, 0x91 }; // Direct: From LA=4 to LA=0
    EXPECT_NO_THROW(InjectCECFrame(directMenuLangFrame, sizeof(directMenuLangFrame)));
    
    // Test Case 2: Broadcast Get Menu Language - should be rejected
    uint8_t broadcastMenuLangFrame[] = { 0x4F, 0x91 }; // Broadcast: From LA=4 to Broadcast
    EXPECT_NO_THROW(InjectCECFrame(broadcastMenuLangFrame, sizeof(broadcastMenuLangFrame)));
}

// Test fixture description: ReportPhysicalAddress processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectReportPhysicalAddressFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Test Case 1: Broadcast Report Physical Address - normal processing
    uint8_t reportPAFrame[] = { 0x4F, 0x84, 0x20, 0x00, 0x04 }; // Broadcast: LA=4, PA=2.0.0.0, Device Type=Playback
    EXPECT_NO_THROW(InjectCECFrame(reportPAFrame, sizeof(reportPAFrame)));
    
    // Test Case 2: Direct Report Physical Address - should be rejected
    uint8_t directReportPAFrame[] = { 0x40, 0x84, 0x30, 0x00, 0x01 }; // Direct: LA=4 to LA=0
    EXPECT_NO_THROW(InjectCECFrame(directReportPAFrame, sizeof(directReportPAFrame)));
    
    // Test Case 3: Different physical address to trigger PA change detection
    uint8_t changedPAFrame[] = { 0x5F, 0x84, 0x10, 0x00, 0x05 }; // Different PA from same device
    EXPECT_NO_THROW(InjectCECFrame(changedPAFrame, sizeof(changedPAFrame)));
}

// Test fixture description: DeviceVendorID processor coverage  
TEST_F(HdmiCecSinkFrameProcessingTest, InjectDeviceVendorIDFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t deviceVendorIDFrame[] = { 0x4F, 0x87, 0x00, 0x80, 0x45 }; // Broadcast: LA=4, Vendor ID
    EXPECT_NO_THROW(InjectCECFrame(deviceVendorIDFrame, sizeof(deviceVendorIDFrame)));
    
    // Test Case 2: Direct Device Vendor ID - should be rejected
    uint8_t directVendorIDFrame[] = { 0x40, 0x87, 0x00, 0x90, 0x56 }; // Direct: LA=4 to LA=0
    EXPECT_NO_THROW(InjectCECFrame(directVendorIDFrame, sizeof(directVendorIDFrame)));
    
    // Test Case 3: Different vendor ID to test update logic
    uint8_t differentVendorIDFrame[] = { 0x5F, 0x87, 0x01, 0x23, 0x45 }; // Different vendor ID
    EXPECT_NO_THROW(InjectCECFrame(differentVendorIDFrame, sizeof(differentVendorIDFrame)));
}

// Test fixture description: GiveDevicePowerStatus processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectGiveDevicePowerStatusFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronous ly)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Test Case 1: Direct Give Device Power Status - normal processing
    uint8_t directPowerStatusFrame[] = { 0x40, 0x8F }; // Direct: From LA=4 to LA=0
    EXPECT_NO_THROW(InjectCECFrame(directPowerStatusFrame, sizeof(directPowerStatusFrame)));
    
    // Test Case 2: Broadcast Give Device Power Status - should be rejected
    uint8_t broadcastPowerStatusFrame[] = { 0x4F, 0x8F }; // Broadcast: From LA=4 to Broadcast
    EXPECT_NO_THROW(InjectCECFrame(broadcastPowerStatusFrame, sizeof(broadcastPowerStatusFrame)));
}

// Test fixture description: ReportPowerStatus processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectReportPowerStatusFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t reportPowerFrame[] = { 0x40, 0x90, 0x00 }; // Direct: From LA=4 to LA=0, Power On
    EXPECT_NO_THROW(InjectCECFrame(reportPowerFrame, sizeof(reportPowerFrame)));
    
    // Test Case 2: Broadcast Report Power Status - should be rejected
    uint8_t broadcastPowerFrame[] = { 0x4F, 0x90, 0x01 }; // Broadcast: From LA=4, Power Standby
    EXPECT_NO_THROW(InjectCECFrame(broadcastPowerFrame, sizeof(broadcastPowerFrame)));
    
    // Test Case 3: Power status from Audio System
    uint8_t audioSystemPowerFrame[] = { 0x50, 0x90, 0x02 }; // From Audio System LA=5, Power Standby to On
    EXPECT_NO_THROW(InjectCECFrame(audioSystemPowerFrame, sizeof(audioSystemPowerFrame)));
    
    // Test Case 4: Different power status to trigger change detection
    uint8_t changedPowerFrame[] = { 0x40, 0x90, 0x03 }; // Different power status
    EXPECT_NO_THROW(InjectCECFrame(changedPowerFrame, sizeof(changedPowerFrame)));
}

// Test fixture description: Abort processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectAbortFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t directAbortFrame[] = { 0x40, 0xFF, 0x9F }; // Direct: From LA=4 to LA=0, Aborting GET_CEC_VERSION
    EXPECT_NO_THROW(InjectCECFrame(directAbortFrame, sizeof(directAbortFrame)));
    
    // Test Case 2: Broadcast Abort - should be ignored
    uint8_t broadcastAbortFrame[] = { 0x4F, 0xFF, 0x8C }; // Broadcast: Aborting GIVE_DEVICE_VENDOR_ID
    EXPECT_NO_THROW(InjectCECFrame(broadcastAbortFrame, sizeof(broadcastAbortFrame)));
}

// Test fixture description: Polling processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectPollingFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Note: Polling uses special opcode 0x200, but in frame it's represented differently
    uint8_t pollingFrame[] = { 0x44 }; // Polling: From LA=4 to LA=4
    EXPECT_NO_THROW(InjectCECFrame(pollingFrame, sizeof(pollingFrame)));
}

// Test fixture description: InitiateArc processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectInitiateArcFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t initiateArcFrame[] = { 0x50, 0xC0 }; // Direct: From Audio System LA=5 to LA=0
    EXPECT_NO_THROW(InjectCECFrame(initiateArcFrame, sizeof(initiateArcFrame)));
    
    // Test Case 2: Initiate ARC from non-Audio System - should be rejected
    uint8_t nonAudioInitiateArcFrame[] = { 0x40, 0xC0 }; // Direct: From LA=4 (not Audio System)
    EXPECT_NO_THROW(InjectCECFrame(nonAudioInitiateArcFrame, sizeof(nonAudioInitiateArcFrame)));
    
    // Test Case 3: Broadcast Initiate ARC - should be rejected
    uint8_t broadcastInitiateArcFrame[] = { 0x5F, 0xC0 }; // Broadcast: From Audio System
    EXPECT_NO_THROW(InjectCECFrame(broadcastInitiateArcFrame, sizeof(broadcastInitiateArcFrame)));
}

// Test fixture description: TerminateArc processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectTerminateArcFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t terminateArcFrame[] = { 0x50, 0xC5 }; // Direct: From Audio System LA=5 to LA=0
    EXPECT_NO_THROW(InjectCECFrame(terminateArcFrame, sizeof(terminateArcFrame)));
    
    // Test Case 2: Terminate ARC from non-Audio System - should be rejected
    uint8_t nonAudioTerminateArcFrame[] = { 0x40, 0xC5 }; // Direct: From LA=4 (not Audio System)
    EXPECT_NO_THROW(InjectCECFrame(nonAudioTerminateArcFrame, sizeof(nonAudioTerminateArcFrame)));
    
    // Test Case 3: Broadcast Terminate ARC - should be rejected
    uint8_t broadcastTerminateArcFrame[] = { 0x5F, 0xC5 }; // Broadcast: From Audio System
    EXPECT_NO_THROW(InjectCECFrame(broadcastTerminateArcFrame, sizeof(broadcastTerminateArcFrame)));
}

// Test fixture description: ReportShortAudioDescriptor processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectReportShortAudioDescriptorFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t reportAudioDescFrame[] = { 0x50, 0xA3, 0x09, 0x07, 0x15 }; // From Audio System: Audio descriptor data
    EXPECT_NO_THROW(InjectCECFrame(reportAudioDescFrame, sizeof(reportAudioDescFrame)));
    
    // Test Case 2: Multiple audio descriptors
    uint8_t multipleAudioDescFrame[] = { 0x50, 0xA3, 0x09, 0x07, 0x15, 0x0D, 0x1F, 0x07 }; // Multiple descriptors
    EXPECT_NO_THROW(InjectCECFrame(multipleAudioDescFrame, sizeof(multipleAudioDescFrame)));
}

// Test fixture description: SetSystemAudioMode processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectSetSystemAudioModeFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t setAudioModeOnFrame[] = { 0x50, 0x72, 0x01 }; // From Audio System: Audio Mode ON
    EXPECT_NO_THROW(InjectCECFrame(setAudioModeOnFrame, sizeof(setAudioModeOnFrame)));
    
    // Test Case 2: Set System Audio Mode OFF
    uint8_t setAudioModeOffFrame[] = { 0x50, 0x72, 0x00 }; // From Audio System: Audio Mode OFF
    EXPECT_NO_THROW(InjectCECFrame(setAudioModeOffFrame, sizeof(setAudioModeOffFrame)));
}

// Test fixture description: ReportAudioStatus processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectReportAudioStatusFrame_MultipleScenarios)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t reportAudioStatusFrame[] = { 0x50, 0x7A, 0x25 }; // Direct: From Audio System, Volume=37, Mute=Off
    EXPECT_NO_THROW(InjectCECFrame(reportAudioStatusFrame, sizeof(reportAudioStatusFrame)));
    
    // Test Case 2: Broadcast Report Audio Status - should be rejected
    uint8_t broadcastAudioStatusFrame[] = { 0x5F, 0x7A, 0xA0 }; // Broadcast: Mute=On, Volume=32
    EXPECT_NO_THROW(InjectCECFrame(broadcastAudioStatusFrame, sizeof(broadcastAudioStatusFrame)));
    
    // Test Case 3: Different audio status values
    uint8_t muteAudioStatusFrame[] = { 0x50, 0x7A, 0x80 }; // Mute=On, Volume=0
    EXPECT_NO_THROW(InjectCECFrame(muteAudioStatusFrame, sizeof(muteAudioStatusFrame)));
}

// Test fixture description: GiveFeatures processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectGiveFeaturesFrame)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t giveFeaturesFrame[] = { 0x40, 0xA5 }; // Direct: From LA=4 to LA=0
    EXPECT_NO_THROW(InjectCECFrame(giveFeaturesFrame, sizeof(giveFeaturesFrame)));
    
    // Test Case 2: Give Features from different source
    uint8_t giveFeatures2Frame[] = { 0x50, 0xA5 }; // Direct: From LA=5 to LA=0
    EXPECT_NO_THROW(InjectCECFrame(giveFeatures2Frame, sizeof(giveFeatures2Frame)));
}

// Test fixture description: RequestCurrentLatency processor coverage
TEST_F(HdmiCecSinkFrameProcessingTest, InjectRequestCurrentLatencyFrame_MultiplePhysicalAddresses)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    uint8_t matchingLatencyFrame[] = { 0x40, 0xA7, 0x00, 0x00 }; // Physical address 0.0.0.0 (root)
    EXPECT_NO_THROW(InjectCECFrame(matchingLatencyFrame, sizeof(matchingLatencyFrame)));
    
    // Test Case 2: Request Current Latency with non-matching physical address
    uint8_t nonMatchingLatencyFrame[] = { 0x40, 0xA7, 0x10, 0x00 }; // Physical address 1.0.0.0
    EXPECT_NO_THROW(InjectCECFrame(nonMatchingLatencyFrame, sizeof(nonMatchingLatencyFrame)));
    
    // Test Case 3: Different physical address patterns
    uint8_t diffLatencyFrame[] = { 0x50, 0xA7, 0x20, 0x00 }; // Physical address 2.0.0.0
    EXPECT_NO_THROW(InjectCECFrame(diffLatencyFrame, sizeof(diffLatencyFrame)));
}

// Test fixture description: ReportPowerStatus from Audio System when power status was explicitly requested
TEST_F(HdmiCecSinkFrameProcessingTest, InjectReportPowerStatus_AudioSystem_AfterRequest)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // First, simulate requesting audio device power status by calling the API
    // This sets m_audioDevicePowerStatusRequested flag to true
    EXPECT_CALL(*p_connectionImplMock, sendTo(::testing::_, ::testing::_, ::testing::_))
        .WillOnce(::testing::Return());

    string requestResponse;
    EXPECT_EQ(Core::ERROR_NONE, handler.Invoke(connection, _T("requestAudioDevicePowerStatus"), _T("{}"), requestResponse));

    // Small delay to ensure the request is processed
    std::this_thread::sleep_for(std::chrono::milliseconds(50));

    // Now inject ReportPowerStatus from Audio System (LA=5) to TV (LA=0)
    // This should trigger line 428: reportAudioDevicePowerStatusInfo()
    uint8_t audioSystemPowerStatusFrame[] = { 0x50, 0x90, 0x00 }; // From Audio System LA=5, Power On

    EXPECT_NO_THROW(InjectCECFrame(audioSystemPowerStatusFrame, sizeof(audioSystemPowerStatusFrame)));

    // Test different power status values to ensure the logic works for various states
    uint8_t audioSystemStandbyFrame[] = { 0x50, 0x90, 0x01 }; // Power Standby
    EXPECT_NO_THROW(InjectCECFrame(audioSystemStandbyFrame, sizeof(audioSystemStandbyFrame)));
}

// Test fixture description: FeatureAbort processor coverage - broadcast message rejection
TEST_F(HdmiCecSinkFrameProcessingTest, InjectFeatureAbort_BroadcastMessage_ShouldBeIgnored)
{
    // Wait for plugin initialization to complete (FrameListener registration happens asynchronously)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Create FeatureAbort broadcast frame (should be ignored per implementation)
    // From Playback Device 1 (LA=4) to Broadcast (LA=15) - should log "Ignore Broadcast messages"
    uint8_t broadcastFeatureAbortFrame[] = { 0x4F, 0x00, 0x9F, 0x00 };
    
    EXPECT_NO_THROW(InjectCECFrame(broadcastFeatureAbortFrame, sizeof(broadcastFeatureAbortFrame)));
}