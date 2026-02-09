/**
* If not stated otherwise in this file or this component's LICENSE
* file the following copyright and licenses apply:
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
**/

#pragma once

#include <stdint.h>
#include "ccec/FrameListener.hpp"
#include "ccec/Connection.hpp"

#include "libIARM.h"
#include "ccec/Assert.hpp"
#include "ccec/Messages.hpp"
#include "ccec/MessageDecoder.hpp"
#include "ccec/MessageProcessor.hpp"

#undef Assert // this define from Connection.hpp conflicts with WPEFramework

#include "Module.h"
#include "tptimer.h"
#include <thread>
#include <mutex>
#include <condition_variable>
#include <chrono>

#include "UtilsLogging.h"
#include <interfaces/IPowerManager.h>
#include <interfaces/IUserSettings.h>
#include "PowerManagerInterface.h"
#include <interfaces/IHdmiCecSink.h>
#include "host.hpp"

using namespace WPEFramework;
using PowerState = WPEFramework::Exchange::IPowerManager::PowerState;
using ThermalTemperature = WPEFramework::Exchange::IPowerManager::ThermalTemperature;


namespace WPEFramework {

    namespace Plugin {
        class HdmiCecSinkFrameListener : public FrameListener
        {
        public:
            HdmiCecSinkFrameListener(MessageProcessor &processor) : processor(processor) {}
            void notify(const CECFrame &in) const;
            ~HdmiCecSinkFrameListener() {}
        private:
            MessageProcessor &processor;
        };
        
        class HdmiCecSinkProcessor : public MessageProcessor
        {
        public:
            HdmiCecSinkProcessor(Connection &conn) : conn(conn) {}
                void process (const ActiveSource &msg, const Header &header);
            void process (const InActiveSource &msg, const Header &header);
            void process (const ImageViewOn &msg, const Header &header);
            void process (const TextViewOn &msg, const Header &header);
            void process (const RequestActiveSource &msg, const Header &header);
            void process (const Standby &msg, const Header &header);
            void process (const GetCECVersion &msg, const Header &header);
            void process (const CECVersion &msg, const Header &header);
            void process (const SetMenuLanguage &msg, const Header &header);
            void process (const GiveOSDName &msg, const Header &header);
            void process (const GivePhysicalAddress &msg, const Header &header);
            void process (const GiveDeviceVendorID &msg, const Header &header);
            void process (const SetOSDString &msg, const Header &header);
            void process (const SetOSDName &msg, const Header &header);
            void process (const RoutingChange &msg, const Header &header);
            void process (const RoutingInformation &msg, const Header &header);
            void process (const SetStreamPath &msg, const Header &header);
            void process (const GetMenuLanguage &msg, const Header &header);
            void process (const ReportPhysicalAddress &msg, const Header &header);
                void process (const DeviceVendorID &msg, const Header &header);
            void process (const GiveDevicePowerStatus &msg, const Header &header);
            void process (const ReportPowerStatus &msg, const Header &header);
            void process (const FeatureAbort &msg, const Header &header);
            void process (const Abort &msg, const Header &header);
            void process (const Polling &msg, const Header &header);
                void process (const InitiateArc &msg, const Header &header);
                void process (const TerminateArc &msg, const Header &header);
                void process (const ReportShortAudioDescriptor  &msg, const Header &header);
        void process (const SetSystemAudioMode &msg, const Header &header);
        void process (const ReportAudioStatus &msg, const Header &header);
        void process (const GiveFeatures &msg, const Header &header);
        void process (const RequestCurrentLatency &msg, const Header &header);
        private:
            Connection conn;
        };

        class CECDeviceParams {
            public:
                
            enum {
                REQUEST_NONE = 0,
                REQUEST_PHISICAL_ADDRESS = 1,
                REQUEST_CEC_VERSION,
                REQUEST_DEVICE_VENDOR_ID,
                REQUEST_POWER_STATUS,
                REQUEST_OSD_NAME,
            };

            enum {
                REQUEST_DONE = 0,
                REQUEST_NOT_DONE,
                REQUEST_TIME_ELAPSED,
            };
            
            DeviceType m_deviceType;
            LogicalAddress m_logicalAddress;
            PhysicalAddress m_physicalAddr;
            Version m_cecVersion;
            VendorID m_vendorID;
            OSDName m_osdName;
            PowerStatus m_powerStatus;
            bool m_isDevicePresent;
            bool m_isDeviceDisconnected;
            Language m_currentLanguage;
            bool m_isActiveSource;
            bool m_isDeviceTypeUpdated;
            bool m_isPAUpdated;
            bool m_isVersionUpdated;
            bool m_isOSDNameUpdated;
            bool m_isVendorIDUpdated;
            bool m_isPowerStatusUpdated;
            int  m_isRequested;
            int  m_isRequestRetry;
            std::chrono::steady_clock::time_point m_requestTime;
            std::vector<FeatureAbort> m_featureAborts;
            std::chrono::system_clock::time_point m_lastPowerUpdateTime;
            
            CECDeviceParams() 
            : m_deviceType(0), m_logicalAddress(0),m_physicalAddr(0x0f,0x0f,0x0f,0x0f),m_cecVersion(0),m_vendorID(0,0,0),m_osdName(""),m_powerStatus(0),m_currentLanguage("")
            {
                m_isDevicePresent = false;
                m_isActiveSource = false;
                m_isPAUpdated = false;
                m_isVersionUpdated = false;
                m_isOSDNameUpdated = false;
                m_isVendorIDUpdated = false;
                m_isPowerStatusUpdated = false;
                m_isDeviceDisconnected = false;
                m_isDeviceTypeUpdated = false;
                m_isRequestRetry = 0;
            }

            void clear( ) 
            {
                m_deviceType = 0;
                m_logicalAddress = 0;
                m_physicalAddr = PhysicalAddress(0x0f,0x0f,0x0f,0x0f);
                m_cecVersion = 0;
                m_vendorID = VendorID(0,0,0);
                m_osdName = "";
                m_powerStatus = 0;
                 m_currentLanguage = "";
                m_isDevicePresent = false;
                m_isActiveSource = false;
                m_isPAUpdated = false;
                m_isVersionUpdated = false;
                m_isOSDNameUpdated = false;
                m_isVendorIDUpdated = false;
                m_isPowerStatusUpdated = false;
                m_isDeviceDisconnected = false;
                m_isDeviceTypeUpdated = false;
            }

            void printVariable()
            {
                LOGINFO("Device LogicalAddress %s", m_logicalAddress.toString().c_str());
                LOGINFO("Device Type %s", m_deviceType.toString().c_str());
                LOGINFO("Device Present %d", m_isDevicePresent);
                LOGINFO("Active Source %d", m_isActiveSource);
                LOGINFO("PA Updated %d", m_isPAUpdated);
                LOGINFO("Version Updated %d", m_isVersionUpdated);
                LOGINFO("OSDName Updated %d", m_isOSDNameUpdated);
                LOGINFO("PowerStatus Updated %d", m_isPowerStatusUpdated);
                LOGINFO("VendorID Updated %d", m_isVendorIDUpdated);
                LOGINFO("CEC Version : %s", m_cecVersion.toString().c_str());
                LOGINFO("Vendor ID : %s", m_vendorID.toString().c_str());
                LOGINFO("PhysicalAddress : %s", m_physicalAddr.toString().c_str());
                LOGINFO("OSDName : %s", m_osdName.toString().c_str());
                LOGINFO("Power Status : %s", m_powerStatus.toString().c_str());
                LOGINFO("Language : %s", m_currentLanguage.toString().c_str());
            }

            bool isAllUpdated() {
                if( !m_isPAUpdated 
                    || !m_isVersionUpdated 
                    || !m_isOSDNameUpdated
                    || !m_isVendorIDUpdated 
                    || !m_isPowerStatusUpdated 
                    || !m_isDeviceTypeUpdated ){
                    return false;
                }
                return true;
            }

            void update( const DeviceType &deviceType ) {
                m_deviceType = deviceType;
                m_isDeviceTypeUpdated  = true;
            }

            void update( const PhysicalAddress &physical_addr ) {
                m_physicalAddr = physical_addr;
                m_isPAUpdated = true;
            }

            void update ( const VendorID &vendorId) {
                m_vendorID = vendorId;
                m_isVendorIDUpdated = true;
            }

            void update ( const Version &version ) {
                m_cecVersion = version;
                m_isVersionUpdated = true;
            }

            void update ( const OSDName    &osdName ) {
                m_osdName = osdName;
                m_isOSDNameUpdated = true;
            }

            void update ( const PowerStatus &status ) {
                m_powerStatus = status;
                m_isPowerStatusUpdated = true;
                m_lastPowerUpdateTime = std::chrono::system_clock::now();
            }
        };

        class DeviceNode {
            public:
            uint8_t m_childsLogicalAddr[LogicalAddress::UNREGISTERED];

            DeviceNode() {
                int i;
                for (i = 0; i < LogicalAddress::UNREGISTERED; i++ )
                {
                    m_childsLogicalAddr[i] = LogicalAddress::UNREGISTERED;
                }
            }
            
        } ;
            typedef struct sendKeyInfo
                {
                   int logicalAddr;
                   int keyCode;
           string UserControl;
                }SendKeyInfo;

        class HdmiPortMap {
            public:
            uint8_t m_portID;
            bool m_isConnected;
            LogicalAddress m_logicalAddr;
            PhysicalAddress m_physicalAddr;
            DeviceNode m_deviceChain[3];
            
            HdmiPortMap(uint8_t portID) : m_portID(portID),
                            m_logicalAddr(LogicalAddress::UNREGISTERED),
                            m_physicalAddr(portID+1,0,0,0)
            {
                m_isConnected = false;
            }

            void update(bool isConnected)
            {
                m_isConnected = isConnected;
            }

            void update( const LogicalAddress &addr )
            {
                m_logicalAddr = addr;
            }

            void addChild( const LogicalAddress &logical_addr, const PhysicalAddress &physical_addr )
            {
                LOGINFO(" logicalAddr = %d, phisicalAddr = %s", m_logicalAddr.toInt(), physical_addr.toString().c_str());
                
                if ( m_logicalAddr.toInt() != LogicalAddress::UNREGISTERED &&
                        m_logicalAddr.toInt() != logical_addr.toInt() )
                {
                    LOGINFO(" update own logicalAddr = %d, new devcie logicalAddress = %d", m_logicalAddr.toInt(), logical_addr.toInt() );
                    /* check matching with this port's physical address */
                    if( physical_addr.getByteValue(0) == m_physicalAddr.getByteValue(0) &&
                            physical_addr.getByteValue(1) != 0 )
                    {
                        if ( physical_addr.getByteValue(3) != 0 )
                        {
                            m_deviceChain[2].m_childsLogicalAddr[physical_addr.getByteValue(3) - 1] = logical_addr.toInt();
                        }
                        else if ( physical_addr.getByteValue(2) != 0 )
                        {
                            m_deviceChain[1].m_childsLogicalAddr[physical_addr.getByteValue(2) - 1] = logical_addr.toInt();
                        }
                        else if ( physical_addr.getByteValue(1) != 0 )
                        {
                            m_deviceChain[0].m_childsLogicalAddr[physical_addr.getByteValue(1) - 1] = logical_addr.toInt();
                        }
                    }
                }
                else if ( physical_addr == m_physicalAddr )
                {
                    update(logical_addr);
                    LOGINFO(" update own logicalAddr = %d", m_logicalAddr.toInt());
                }
            }

            void removeChild(    PhysicalAddress &physical_addr )
            {
                if ( m_logicalAddr.toInt() != LogicalAddress::UNREGISTERED )
                {
                    /* check matching with this port's physical address */
                    if( physical_addr.getByteValue(0) == m_physicalAddr.getByteValue(0) &&
                            physical_addr.getByteValue(1) != 0 )
                    {
                        if ( physical_addr.getByteValue(3) != 0 )
                        {
                            m_deviceChain[2].m_childsLogicalAddr[physical_addr.getByteValue(3) - 1] = LogicalAddress::UNREGISTERED;
                        }
                        else if ( physical_addr.getByteValue(2) != 0 )
                        {
                            m_deviceChain[1].m_childsLogicalAddr[physical_addr.getByteValue(2) - 1] = LogicalAddress::UNREGISTERED;
                        }
                        else if ( physical_addr.getByteValue(1) != 0 )
                        {
                            m_deviceChain[0].m_childsLogicalAddr[physical_addr.getByteValue(1) - 1] = LogicalAddress::UNREGISTERED;
                        }
                    }
                }
            }

            void getRoute(    PhysicalAddress &physical_addr, std::vector<uint8_t> &   route )
            {
                LOGINFO(" logicalAddr = %d, phsical = %s", m_logicalAddr.toInt(), physical_addr.toString().c_str());
                
                if ( m_logicalAddr.toInt() != LogicalAddress::UNREGISTERED )
                {
                    LOGINFO(" search for logicalAddr = %d", m_logicalAddr.toInt());
                    /* check matching with this port's physical address */
                    if( physical_addr.getByteValue(0) == m_physicalAddr.getByteValue(0) &&
                            physical_addr.getByteValue(1) != 0 )
                    {
                        if ( physical_addr.getByteValue(3) != 0 )
                        {
                            route.push_back(m_deviceChain[2].m_childsLogicalAddr[physical_addr.getByteValue(3) - 1]);
                        }
                        
                        if ( physical_addr.getByteValue(2) != 0 )
                        {
                            route.push_back(m_deviceChain[1].m_childsLogicalAddr[physical_addr.getByteValue(2) - 1]);
                        }
                        
                        if ( physical_addr.getByteValue(1) != 0 )
                        {
                            route.push_back(m_deviceChain[0].m_childsLogicalAddr[physical_addr.getByteValue(1) - 1]);
                        }

                        route.push_back(m_logicalAddr.toInt());
                    }
                    else
                    {
                        route.push_back(m_logicalAddr.toInt());
                        LOGINFO("logicalAddr = %d, physical = %s", m_logicalAddr.toInt(), m_physicalAddr.toString().c_str());    
                    }
                }
            }
        };

       class binary_semaphore {

     public:

    explicit binary_semaphore(int init_count = count_max)

      : count_(init_count) {}



    // P-operation / acquire

    void wait()

    {

        std::unique_lock<std::mutex> lk(m_);

        cv_.wait(lk, [=]{ return 0 < count_; });

        --count_;

    }

    bool try_wait()

    {

        std::lock_guard<std::mutex> lk(m_);

        if (0 < count_) {

            --count_;

            return true;

        } else {

            return false;

        }

    }

    // V-operation / release

    void signal()

    {

        std::lock_guard<std::mutex> lk(m_);

        if (count_ < count_max) {

            ++count_;

            cv_.notify_one();

        }

    }



    // Lockable requirements

    void acquire() { wait(); }

    bool try_lock() { return try_wait(); }

    void release() { signal(); }



private:

    static const int count_max = 1;

    int count_;

    std::mutex m_;

    std::condition_variable cv_;

};
        // This is a server for a JSONRPC communication channel. 
        // For a plugin to be capable to handle JSONRPC, inherit from PluginHost::JSONRPC.
        // By inheriting from this class, the plugin realizes the interface PluginHost::IDispatcher.
        // This realization of this interface implements, by default, the following methods on this plugin
        // - exists
        // - register
        // - unregister
        // Any other methood to be handled by this plugin  can be added can be added by using the
        // templated methods Register on the PluginHost::JSONRPC class.
        // As the registration/unregistration of notifications is realized by the class PluginHost::JSONRPC,
        // this class exposes a public method called, Notify(), using this methods, all subscribed clients
        // will receive a JSONRPC message as a notification, in case this method is called.
        class HdmiCecSinkImplementation : public Exchange::IHdmiCecSink, public device::Host::IHdmiInEvents {

        enum {
            POLL_THREAD_STATE_NONE,
            POLL_THREAD_STATE_IDLE,
            POLL_THREAD_STATE_POLL,    
            POLL_THREAD_STATE_PING,
            POLL_THREAD_STATE_INFO,
            POLL_THREAD_STATE_WAIT,
            POLL_THREAD_STATE_CLEAN,
            POLL_THREAD_STATE_UPDATE,
            POLL_THREAD_STATE_EXIT,
        };
                enum {
                        ARC_STATE_REQUEST_ARC_INITIATION,
                ARC_STATE_ARC_INITIATED,
                ARC_STATE_REQUEST_ARC_TERMINATION,
                ARC_STATE_ARC_TERMINATED,
            ARC_STATE_ARC_EXIT
             };
        enum {
                        VOLUME_UP     = 0x41,
            VOLUME_DOWN   = 0x42,
            MUTE          = 0x43,
                UP            = 0x01,
            DOWN          = 0x02,
            LEFT          = 0x03,
            RIGHT          = 0x04,
            SELECT          = 0x00,
            HOME          = 0x09,
            BACK          = 0x0D,
            NUMBER_0      = 0x20,
            NUMBER_1      = 0x21,
            NUMBER_2      = 0x22,
            NUMBER_3      = 0x23,
            NUMBER_4      = 0x24,
            NUMBER_5      = 0x25,
            NUMBER_6      = 0x26,
            NUMBER_7      = 0x27,
            NUMBER_8      = 0x28,
            NUMBER_9      = 0x29
              };
        
        public:
            HdmiCecSinkImplementation();
            virtual ~HdmiCecSinkImplementation();
            static HdmiCecSinkImplementation* _instance;
            CECDeviceParams deviceList[16];
            std::vector<HdmiPortMap> hdmiInputs;
			std::string mapToIso639_2(const string& lang_BCP47);
            int m_currentActiveSource;
            void updateInActiveSource(const int logical_address, const InActiveSource &source );
            void updateActiveSource(const int logical_address, const ActiveSource &source );
            void updateTextViewOn(const int logicalAddress);
            void updateImageViewOn(const int logicalAddress);
            void updateDeviceChain(const LogicalAddress &logicalAddress, const PhysicalAddress &phy_addr);
            void getActiveRoute(const LogicalAddress &logicalAddress, std::vector<uint8_t> &route);
            void removeDevice(const int logicalAddress);
            void addDevice(const int logicalAddress);
            void printDeviceList();
            void setStreamPath( const PhysicalAddress &physical_addr);
            void setRoutingChange(const std::string &from, const std::string &to);
            void sendStandbyMessage();
            void setCurrentLanguage(const Language &lang);
            void sendMenuLanguage();
            void setActiveSource(bool isResponse);
            void requestActiveSource();
                        void startArc();
                        void stopArc();
                        void Process_InitiateArc();
                        void Process_TerminateArc();
                        void updateArcState();
                        void requestShortaudioDescriptor();
                        void Send_ShortAudioDescriptor_Event(JsonArray audiodescriptor);
                void Process_ShortAudioDescriptor_msg(const ReportShortAudioDescriptor  &msg);
            void Process_SetSystemAudioMode_msg(const SetSystemAudioMode &msg);
            void sendDeviceUpdateInfo(const int logicalAddress);
            void sendFeatureAbort(const LogicalAddress logicalAddress, const OpCode feature, const AbortReason reason);
            void reportFeatureAbortEvent(const LogicalAddress logicalAddress, const OpCode feature, const AbortReason reason);
            void systemAudioModeRequest();
                        void SendStandbyMsgEvent(const int logicalAddress);
                        void reportAudioDevicePowerStatusInfo(const int logicalAddress, const int powerStatus);
            void updateCurrentLatency(int videoLatency, bool lowLatencyMode, int audioOutputCompensated, int audioOutputDelay);
            void setLatencyInfo();
            void Process_ReportAudioStatus_msg(const ReportAudioStatus msg);
            void sendKeyPressEvent(const int logicalAddress, int keyCode);
            void sendKeyReleaseEvent(const int logicalAddress);
            int  getUIKeyCode(int keyCode);
        void sendUserControlPressed(const int logicalAddress, int keyCode);
            void sendUserControlReleased(const int logicalAddress);
            void sendGiveAudioStatusMsg();
            void onPowerModeChanged(const PowerState &currentState, const PowerState &newState);
            void registerEventHandlers();
	    	void onPresentationLanguageChanged(const string& language);
            void getHdmiArcPortID();
            int m_numberOfDevices; /* Number of connected devices othethan own device */
            bool m_audioDevicePowerStatusRequested;

            BEGIN_INTERFACE_MAP(HdmiCecSinkImplementation)
                INTERFACE_ENTRY(Exchange::IHdmiCecSink)
            END_INTERFACE_MAP

        private:
            class PowerManagerNotification : public Exchange::IPowerManager::IModeChangedNotification {
                private:
                    PowerManagerNotification(const PowerManagerNotification&) = delete;
                    PowerManagerNotification& operator=(const PowerManagerNotification&) = delete;
                
                public:
                    explicit PowerManagerNotification(HdmiCecSinkImplementation& parent)
                        : _parent(parent)
                    {
                    }
                    ~PowerManagerNotification() override = default;
                
                public:
                    void OnPowerModeChanged(const PowerState currentState, const PowerState newState) override
                    {
                        _parent.onPowerModeChanged(currentState, newState);
                    }

                    template <typename T>
                    T* baseInterface()
                    {
                        static_assert(std::is_base_of<T, PowerManagerNotification>(), "base type mismatch");
                        return static_cast<T*>(this);
                    }

                    BEGIN_INTERFACE_MAP(PowerManagerNotification)
                    INTERFACE_ENTRY(Exchange::IPowerManager::IModeChangedNotification)
                    END_INTERFACE_MAP

                private:
                    HdmiCecSinkImplementation& _parent;
                
            };

	    class UserSettingsNotification : public Exchange::IUserSettings::INotification {
                private:
                    UserSettingsNotification(const UserSettingsNotification&) = delete;
                    UserSettingsNotification& operator=(const UserSettingsNotification&) = delete;

                public:
                    explicit UserSettingsNotification(HdmiCecSinkImplementation& parent)
                        : _parent(parent)
                    {
                    }
                    ~UserSettingsNotification() override = default;

                public:
                    void OnPresentationLanguageChanged(const string& language) override
                    {
                        _parent.onPresentationLanguageChanged(language);
                    }

                    BEGIN_INTERFACE_MAP(UserSettingsNotification)
                    INTERFACE_ENTRY(Exchange::IUserSettings::INotification)
                    END_INTERFACE_MAP

                private:
                    HdmiCecSinkImplementation& _parent;
           };

        // We do not allow this plugin to be copied !!
        HdmiCecSinkImplementation(const HdmiCecSinkImplementation&) = delete;
        HdmiCecSinkImplementation& operator=(const HdmiCecSinkImplementation&) = delete;
        //Begin methods
        void InitializePowerManager(PluginHost::IShell *service);
        //End methods
        std::string logicalAddressDeviceType;
        bool cecSettingEnabled;
        bool cecOTPSettingEnabled;
        bool cecEnableStatus;
        bool hdmiCecAudioDeviceConnected;
        bool m_isHdmiInConnected;
        int  m_numofHdmiInput;
        uint8_t m_deviceType;
        int m_logicalAddressAllocated;
        std::thread m_pollThread;
        uint32_t m_pollThreadState;
        uint32_t m_pollNextState;
        bool m_pollThreadExit;
        uint32_t m_sleepTime;
        std::mutex m_pollExitMutex;
        std::mutex m_enableMutex;
        /* Send Key event related */
        bool m_sendKeyEventThreadExit;
        bool m_sendKeyEventThreadRun;
        bool m_isAudioStatusInfoUpdated;
        bool m_audioStatusReceived;
        bool m_audioStatusTimerStarted;
        std::thread m_sendKeyEventThread;
        std::mutex m_sendKeyEventMutex;
        std::queue<SendKeyInfo> m_SendKeyQueue;
        std::condition_variable m_sendKeyCV;
        std::condition_variable m_ThreadExitCV;

            /* DALS - Latency Values */
        uint8_t m_video_latency;
        uint8_t m_latency_flags;
        uint8_t m_audio_output_delay;

        /* ARC related */
            std::thread m_arcRoutingThread;
        uint32_t m_currentArcRoutingState;
        std::mutex m_arcRoutingStateMutex;
        binary_semaphore m_semSignaltoArcRoutingThread;
        bool m_arcstarting;
        TpTimer m_arcStartStopTimer;
        TpTimer m_audioStatusDetectionTimer;

        Connection *smConnection;
        std::vector<uint8_t> m_connectedDevices;
        HdmiCecSinkProcessor *msgProcessor;
        HdmiCecSinkFrameListener *msgFrameListener;
		Exchange::IUserSettings *_userSettingsPlugin;
		Core::Sink<UserSettingsNotification> _userSettingsNotification;
        PowerManagerInterfaceRef _powerManagerPlugin;
        Core::Sink<PowerManagerNotification> _pwrMgrNotification;
        bool _registeredEventHandlers;
        void allocateLogicalAddress(int deviceType);
        void allocateLAforTV();
        void pingDevices(std::vector<int> &connected , std::vector<int> &disconnected);
        void CheckHdmiInState();
        void request(const int logicalAddress);
        int requestType(const int logicalAddress);
        int requestStatus(const int logicalAddress);
        static void threadRun();
        void cecMonitoringThread();
        void onHdmiHotPlug(int portId, int connectStatus);
        bool loadSettings();
        void persistSettings(bool enableStatus);
        void persistOTPSettings(bool enableStatus);
        void persistOSDName(const char *name);
        void persistVendorId(unsigned int vendorID);
        void setEnabled(bool enabled);
        bool getEnabled();
        bool getAudioDeviceConnectedStatus();
        void CECEnable(void);
        void CECDisable(void);
        void getPhysicalAddress();
        void getLogicalAddress();
        void cecAddressesChanged(int changeStatus);
            
        // Arc functions

        static void  threadSendKeyEvent();
        static void  threadArcRouting();
        void requestArcInitiation();
        void requestArcTermination();
        void Send_Request_Arc_Initiation_Message();
        void Send_Report_Arc_Initiated_Message();
        void Send_Request_Arc_Termination_Message();
        void Send_Report_Arc_Terminated_Message();
        void arcStartStopTimerFunction();
        void audioStatusTimerFunction();
        void getCecVersion();


    public:
        Core::hresult GetActiveRoute(bool &available, uint8_t &length, IHdmiCecSinkActivePathIterator*& pathList, string &ActiveRoute, bool &success) override;
        Core::hresult GetActiveSource(bool &available, uint8_t &logicalAddress, string &physicalAddress, string &deviceType, string &cecVersion, string &osdName, string &vendorID, string &powerStatus, string &port, bool &success) override;
        Core::hresult GetAudioDeviceConnectedStatus(bool &connected, bool &success) override;
        Core::hresult GetDeviceList(uint32_t &numberofdevices, IHdmiCecSinkDeviceListIterator*& deviceList, bool &success) override;
        Core::hresult GetEnabled(bool &enabled, bool &success) override;
        Core::hresult GetOSDName(string &name, bool &success) override;
        Core::hresult GetVendorId(string &vendorid, bool &success) override;
        Core::hresult PrintDeviceList(bool &printed, bool &success) override;
        Core::hresult RequestActiveSource(HdmiCecSinkSuccess &successResult) override;
        Core::hresult RequestShortAudioDescriptor(HdmiCecSinkSuccess &successResult) override;
        Core::hresult SendAudioDevicePowerOnMessage(HdmiCecSinkSuccess &successResult) override;
        Core::hresult SendGetAudioStatusMessage(HdmiCecSinkSuccess &successResult) override;
        Core::hresult SendKeyPressEvent(const uint32_t &logicalAddress, const uint32_t &keyCode, HdmiCecSinkSuccess &successResult) override;
        Core::hresult SendUserControlPressed(const uint32_t &logicalAddress, const uint32_t &keyCode, HdmiCecSinkSuccess &successResult) override;
        Core::hresult SendUserControlReleased(const uint32_t &logicalAddress, HdmiCecSinkSuccess &successResult) override;
        Core::hresult SendStandbyMessage(HdmiCecSinkSuccess &successResult) override;
        Core::hresult SetActivePath(const string &activePath, HdmiCecSinkSuccess &successResult) override;
        Core::hresult SetActiveSource(HdmiCecSinkSuccess &successResult) override;
        Core::hresult SetEnabled(const bool &enabled, HdmiCecSinkSuccess &successResult) override;
        Core::hresult SetOSDName(const string &name, HdmiCecSinkSuccess &successResult) override;
        Core::hresult SetRoutingChange(const string &oldPort, const string &newPort, HdmiCecSinkSuccess &successResult) override;
        Core::hresult SetupARCRouting(const bool &enabled, HdmiCecSinkSuccess &successResult) override;
        Core::hresult SetVendorId(const string &vendorId, HdmiCecSinkSuccess &successResult) override;
        Core::hresult SetLatencyInfo(const string &videoLatency, const string &lowLatencyMode, const string &audioOutputCompensated, const string &audioOutputDelay, HdmiCecSinkSuccess &successResult) override;
        Core::hresult Configure(PluginHost::IShell* service) override;
        Core::hresult Register(Exchange::IHdmiCecSink::INotification *notification) override;
        Core::hresult Unregister(Exchange::IHdmiCecSink::INotification *notification) override;
        Core::hresult SetMenuLanguage(const string &language, HdmiCecSinkSuccess &successResult)  override;
        Core::hresult RequestAudioDevicePowerStatus(HdmiCecSinkSuccess &successResult) override;

	 /*devicesetting APIs*/
        virtual void OnHdmiInEventHotPlug(dsHdmiInPort_t port, bool isConnected) override;

    private:
        template <typename T>
        T* baseInterface()
        {
            static_assert(std::is_base_of<T, HdmiCecSinkImplementation>(), "base type mismatch");
            return static_cast<T*>(this);
        }
        std::list<Exchange::IHdmiCecSink::INotification*> _hdmiCecSinkNotifications;
        mutable Core::CriticalSection _adminLock;
        };
    } // namespace Plugin
} // namespace WPEFramework
