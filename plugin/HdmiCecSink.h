/**
* If not stated otherwise in this file or this component's LICENSE
* file the following copyright and licenses apply:
*
* Copyright 2019 RDK Management
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
#include <mutex>
#include <condition_variable>

#include <thread>

#undef Assert // this define from Connection.hpp conflicts with WPEFramework

#include "Module.h"

#include "UtilsBIT.h"
#include "UtilsThreadRAII.h"

#include <interfaces/IHdmiCecSink.h>
#include <interfaces/json/JHdmiCecSink.h>
#include <interfaces/json/JsonData_HdmiCecSink.h>

using namespace WPEFramework;

namespace WPEFramework {

    namespace Plugin {
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
        class HdmiCecSink : public PluginHost::IPlugin, public PluginHost::JSONRPC {

            private:
                class Notification : public RPC::IRemoteConnection::INotification,
                                     public Exchange::IHdmiCecSink::INotification
                    {
                       private:
                           Notification() = delete;
                           Notification(const Notification&) = delete;
                           Notification& operator=(const Notification&) = delete;

                        public:
                            explicit Notification(HdmiCecSink* parent)
                                : _parent(*parent)
                                {
                                    ASSERT(parent != nullptr);
                                }

                                virtual ~Notification()
                                {
                                }

                                BEGIN_INTERFACE_MAP(Notification)
                                INTERFACE_ENTRY(Exchange::IHdmiCecSink::INotification)
                                INTERFACE_ENTRY(RPC::IRemoteConnection::INotification)
                                END_INTERFACE_MAP

                                void Activated(RPC::IRemoteConnection*) override
                                {
                                }

                                void Deactivated(RPC::IRemoteConnection *connection) override
                                {
                                   _parent.Deactivated(connection);
                                }

                                void ArcInitiationEvent(const string  success) override
                                {
                                    LOGINFO("ArcInitiationEvent");
                                    LOGINFO("success: %s", success.c_str());
                                    Exchange::JHdmiCecSink::Event::ArcInitiationEvent(_parent, success);
                                }

                                void ArcTerminationEvent(const string success) override
                                {
                                    LOGINFO("ArcTerminationEvent");
                                    LOGINFO("success: %s", success.c_str());
                                    Exchange::JHdmiCecSink::Event::ArcTerminationEvent(_parent, success);
                                }

                                void OnActiveSourceChange(const int logicalAddress, const string physicalAddress) override
                                {
                                    LOGINFO("OnActiveSourceChange");
                                    LOGINFO("logicalAddress: %d, physicalAddress: %s", logicalAddress, physicalAddress.c_str());
                                    Exchange::JHdmiCecSink::Event::OnActiveSourceChange(_parent, logicalAddress, physicalAddress);
                                }

                                void OnDeviceAdded(const int logicalAddress) override
                                {
                                    LOGINFO("OnDeviceAdded");
                                    LOGINFO("logicalAddress: %d", logicalAddress);
                                    Exchange::JHdmiCecSink::Event::OnDeviceAdded(_parent, logicalAddress);
                                }

                                void OnDeviceInfoUpdated(const int logicalAddress) override
                                {
                                    LOGINFO("OnDeviceInfoUpdated");
                                    LOGINFO("logicalAddress: %d", logicalAddress);
                                    Exchange::JHdmiCecSink::Event::OnDeviceInfoUpdated(_parent, logicalAddress);
                                }

                                void OnDeviceRemoved(const int logicalAddress) override
                                {
                                    LOGINFO("OnDeviceRemoved");
                                    LOGINFO("logicalAddress: %d", logicalAddress);
                                    Exchange::JHdmiCecSink::Event::OnDeviceRemoved(_parent, logicalAddress);
                                }

                                void OnImageViewOnMsg(const int logicalAddress) override
                                {
                                    LOGINFO("OnImageViewOnMsg");
                                    LOGINFO("logicalAddress: %d", logicalAddress);
                                    Exchange::JHdmiCecSink::Event::OnImageViewOnMsg(_parent, logicalAddress);
                                }

                                void OnInActiveSource(const int logicalAddress, const string physicalAddress) override
                                {
                                    LOGINFO("OnInActiveSource");
                                    LOGINFO("logicalAddress: %d, physicalAddress: %s", logicalAddress, physicalAddress.c_str());
                                    Exchange::JHdmiCecSink::Event::OnInActiveSource(_parent, logicalAddress, physicalAddress);
                                }

                                void OnTextViewOnMsg(const int logicalAddress) override
                                {
                                    LOGINFO("OnTextViewOnMsg");
                                    LOGINFO("logicalAddress: %d", logicalAddress);
                                    Exchange::JHdmiCecSink::Event::OnTextViewOnMsg(_parent, logicalAddress);
                                }

                                void OnWakeupFromStandby(const int logicalAddress) override
                                {
                                    LOGINFO("OnWakeupFromStandby");
                                    LOGINFO("logicalAddress: %d", logicalAddress);
                                    Exchange::JHdmiCecSink::Event::OnWakeupFromStandby(_parent, logicalAddress);
                                }

                                void ReportAudioDeviceConnectedStatus(const string status, const string audioDeviceConnected) override
                                {
                                    LOGINFO("ReportAudioDeviceConnectedStatus");
                                    LOGINFO("status: %s, audioDeviceConnected: %s", status.c_str(), audioDeviceConnected.c_str());
                                    Exchange::JHdmiCecSink::Event::ReportAudioDeviceConnectedStatus(_parent, status, audioDeviceConnected);
                                }

                                void ReportAudioStatusEvent(const int muteStatus, const int volumeLevel) override
                                {
                                    LOGINFO("ReportAudioStatusEvent");
                                    LOGINFO("muteStatus: %d, volumeLevel: %d", muteStatus, volumeLevel);
                                    Exchange::JHdmiCecSink::Event::ReportAudioStatusEvent(_parent, muteStatus, volumeLevel);
                                }

                                void ReportFeatureAbortEvent(const int logicalAddress, const int opcode, const int FeatureAbortReason) override
                                {
                                    LOGINFO("ReportFeatureAbortEvent");
                                    LOGINFO("logicalAddress: %d, opcode: %d, FeatureAbortReason: %d", logicalAddress, opcode, FeatureAbortReason);
                                    Exchange::JHdmiCecSink::Event::ReportFeatureAbortEvent(_parent, logicalAddress, opcode, FeatureAbortReason);
                                }

                                void ReportCecEnabledEvent(const string cecEnable) override
                                {
                                    LOGINFO("ReportCecEnabledEvent");
                                    LOGINFO("cecEnable: %s", cecEnable.c_str());
                                    Exchange::JHdmiCecSink::Event::ReportCecEnabledEvent(_parent, cecEnable);
                                }

                                void SetSystemAudioModeEvent(const string audioMode) override
                                {
                                    LOGINFO("SetSystemAudioModeEvent");
                                    LOGINFO("audioMode: %s", audioMode.c_str());
                                    Exchange::JHdmiCecSink::Event::SetSystemAudioModeEvent(_parent, audioMode);
                                }

                                void ShortAudiodescriptorEvent(const string& shortAudioDescriptor) override
                                {
                                    LOGINFO("ShortAudiodescriptorEvent");
                                    LOGINFO("ShortAudiodescriptor: %s", shortAudioDescriptor.c_str());
                                    Exchange::JHdmiCecSink::Event::ShortAudiodescriptorEvent(_parent, shortAudioDescriptor);
                                }

                                void StandbyMessageReceived(const int logicalAddress) override
                                {
                                    LOGINFO("StandbyMessageReceived");
                                    LOGINFO("logicalAddress: %d", logicalAddress);
                                    Exchange::JHdmiCecSink::Event::StandbyMessageReceived(_parent, logicalAddress);
                                }

                                void ReportAudioDevicePowerStatus(const int powerStatus) override
                                {
                                    LOGINFO("ReportAudioDevicePowerStatus");
                                    LOGINFO("powerStatus: %d", powerStatus);
                                    Exchange::JHdmiCecSink::Event::ReportAudioDevicePowerStatus(_parent, powerStatus);
                                }

                            private:
                                HdmiCecSink &_parent;

                    };

            public:
                // We do not allow this plugin to be copied !!
                HdmiCecSink(const HdmiCecSink&) = delete;
                HdmiCecSink& operator=(const HdmiCecSink&) = delete;

                HdmiCecSink()
                : PluginHost::IPlugin()
                , PluginHost::JSONRPC()
                , _service(nullptr)
                , _notification(this)
                , _hdmiCecSink(nullptr)
                , _connectionId(0)
                {

                }
                virtual ~HdmiCecSink()
                {

                }

                BEGIN_INTERFACE_MAP(HdmiCecSink)
                INTERFACE_ENTRY(PluginHost::IPlugin)
                INTERFACE_ENTRY(PluginHost::IDispatcher)
                INTERFACE_AGGREGATE(Exchange::IHdmiCecSink, _hdmiCecSink)
                END_INTERFACE_MAP

                //  IPlugin methods
                // -------------------------------------------------------------------------------------------------------
		        const string Initialize(PluginHost::IShell* service) override;
                void Deinitialize(PluginHost::IShell* service) override;
                string Information() const override;
                //Begin methods

            private:
                void Deactivated(RPC::IRemoteConnection* connection);

            private:
                PluginHost::IShell* _service{};
                Core::Sink<Notification> _notification;
                Exchange::IHdmiCecSink* _hdmiCecSink;
                uint32_t _connectionId;
        };
	} // namespace Plugin
} // namespace WPEFramework
