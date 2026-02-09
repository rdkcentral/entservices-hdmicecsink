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

#include "HdmiCecSink.h"

#include "UtilsJsonRpc.h"
#include "UtilssyncPersistFile.h"
#include "UtilsSearchRDKProfile.h"


#define TR181_HDMICECSINK_CEC_VERSION "Device.DeviceInfo.X_RDKCENTRAL-COM_RFC.Feature.HdmiCecSink.CECVersion"


#define API_VERSION_NUMBER_MAJOR 1
#define API_VERSION_NUMBER_MINOR 3
#define API_VERSION_NUMBER_PATCH 10

namespace WPEFramework
{
    namespace {

        static Plugin::Metadata<Plugin::HdmiCecSink> metadata(
            // Version (Major, Minor, Patch)
            API_VERSION_NUMBER_MAJOR, API_VERSION_NUMBER_MINOR, API_VERSION_NUMBER_PATCH,
            // Preconditions
            {},
            // Terminations
            {},
            // Controls
            {}
        );
    }

    namespace Plugin
    {
       SERVICE_REGISTRATION(HdmiCecSink, API_VERSION_NUMBER_MAJOR, API_VERSION_NUMBER_MINOR, API_VERSION_NUMBER_PATCH);

       const std::string HdmiCecSink::Initialize(PluginHost::IShell *service)
       {
           profileType = searchRdkProfile();

           if (profileType == STB || profileType == NOT_FOUND)
           {
               LOGINFO("Invalid profile type for TV \n");
               return (std::string("Not supported"));
           }

           string msg = "";

           ASSERT(nullptr != service);
           ASSERT(nullptr == _service);
           ASSERT(nullptr == _hdmiCecSink);
           ASSERT(0 == _connectionId);


           _service = service;
           _service->AddRef();
           _service->Register(&_notification);
           _hdmiCecSink = _service->Root<Exchange::IHdmiCecSink>(_connectionId, 5000, _T("HdmiCecSinkImplementation"));

           if(nullptr != _hdmiCecSink)
            {
                _hdmiCecSink->Configure(service);
                _hdmiCecSink->Register(&_notification);
                Exchange::JHdmiCecSink::Register(*this, _hdmiCecSink);
                LOGINFO("HdmiCecSink plugin is available. Successfully activated HdmiCecSink Plugin");
            }
            else
            {
                msg = "HdmiCecSink plugin is not available";
                LOGINFO("HdmiCecSink plugin is not available. Failed to activate HdmiCecSink Plugin");
            }

            if (0 != msg.length())
            {
                Deinitialize(service);
            }

           // On success return empty, to indicate there is no error text.
           return msg;
        }


       void HdmiCecSink::Deinitialize(PluginHost::IShell* /* service */)
       {

        profileType = searchRdkProfile();

        if (profileType == STB || profileType == NOT_FOUND)
        {
            LOGINFO("Invalid profile type for TV \n");
            return ;
        }

        if(nullptr != _hdmiCecSink)
        {
           bool enabled = false;
           bool ret = false;
           HdmiCecSink::_hdmiCecSink->GetEnabled(enabled,ret);

            if(ret && enabled)
            {
                    Exchange::IHdmiCecSink::HdmiCecSinkSuccess success;
                    HdmiCecSink::_hdmiCecSink->SetEnabled(false,success);
            }

             _hdmiCecSink->Unregister(&_notification);
             Exchange::JHdmiCecSink::Unregister(*this);
             _hdmiCecSink->Release();
             _hdmiCecSink = nullptr;

             RPC::IRemoteConnection* connection = _service->RemoteConnection(_connectionId);
             if (connection != nullptr)
             {
                try{
                    connection->Terminate();
                }
                catch(const std::exception& e)
                {
                    std::string errorMessage = "Failed to terminate connection: ";
                    errorMessage += e.what();
                    LOGWARN("%s",errorMessage.c_str());
                }

                connection->Release();
             }
           }

           _connectionId = 0;
           _service->Unregister(&_notification);
           _service->Release();
           _service = nullptr;
           LOGINFO("HdmiCecSink plugin is deactivated. Successfully deactivated HdmiCecSink Plugin");
        }

       string HdmiCecSink::Information() const
        {
            return("This HdmiCecSink PLugin Facilitates the HDMI CEC Sink Control");
        }

        void HdmiCecSink::Deactivated(RPC::IRemoteConnection* connection)
        {
            if (connection->Id() == _connectionId)
            {
                ASSERT(_service != nullptr);
                Core::IWorkerPool::Instance().Submit(PluginHost::IShell::Job::Create(_service, PluginHost::IShell::DEACTIVATED, PluginHost::IShell::FAILURE));
            }
        }

    } // namespace Plugin
} // namespace WPEFramework
