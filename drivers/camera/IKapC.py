# _*_ coding: utf-8 -*_
from ctypes import *
import ctypes
import platform
import os
import importlib

# import library
if platform.system() == 'Windows':
    dll_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DLL/IKapC.dll')
    libIKapC = windll.LoadLibrary(dll_path)
else:
    libIKapC = cdll.LoadLibrary("libIKapC.so")

have_numpy = 1
try: 
    np = importlib.import_module("numpy")
except:
    have_numpy = 0
    print("Can't find numpy module.Disable ItkBufferToNumpy.")

# Device info 
class ITKDEV_INFO(Structure):
    _fields_ = [("FullName",c_char * 64),
                ("FriendlyName",c_char * 64),
                ("VendorName",c_char * 64),
                ("ModelName",c_char * 64),
                ("SerialNumber",c_char * 64),
                ("DeviceClass",c_char * 64),
                ("DeviceVersion",c_char * 64),
                ("UserDefinedName",c_char * 64)]

# GigEVision specific information
class ITKGIGEDEV_INFO(Structure):
    _fields_ = [("MAC",c_char * 32),
                ("Ip",c_char * 32),
                ("SubNetMask",c_char * 32),
                ("GateWay",c_char * 32),
                ("NICMac",c_char * 32),
                ("NICIp",c_char * 32),
                ("NICSubNetMask",c_char * 32),
                ("NICGateWay",c_char * 32),
                ("NICAdapterName",c_char * 260),
                ("NICDescription",c_char * 132),
                ("NICSpeed",c_uint),
                ("reserved",c_char * 124)]

# CameraLink specific information
class ITK_CL_DEV_INFO(Structure):
    _fields_ = [("HostInterface",c_uint),
                ("BoardIndex",c_uint),
                ("SerialPort",c_char * 32),
                ("Reserved",c_char * 224)]

# CoaXPress specific information
class ITK_CXP_DEV_INFO(Structure):
    _fields_ = [("BoardIndex",c_uint),
                ("MasterPort",c_uint),
                ("SlaveCount",c_uint),
                ("SlavePort",c_uint * 7),
                ("CameraId",c_uint),
                ("Topology", c_uint),
                ("Reserved",c_char * 248)]

# USB3Vision specific information
class ITK_U3V_DEV_INFO(Structure):
    _fields_ = [("VID",c_uint),
                ("PID",c_uint),
                ("USBVersion",c_uint),
                ("Reserved",c_char * 256)]      

# XGVB specific information
class ITK_GVB_DEV_INFO(Structure):
    _fields_ = [("BoardIndex",c_uint),
                ("MasterPort",c_uint),
                ("MAC",c_char * 32),
                ("Ip",c_char * 32),
                ("SubNetMask",c_char * 32),
                ("GateWay", c_char * 32),
                ("Reserved2",c_char * 160)]

# Board infomation
class ITKBOARD_INFO(Structure):
    _fields_ = [("Name",c_char * 64),
                ("Reserved",c_char * 256)]      

# BatchBuffer Status infomation
class ITKBATCH_BUFFER_STATUS(Structure):
    _fields_ = [("blockId",c_int64),
                ("ready_lines",c_int64),
                ("Reserved",c_char * 256)]  

# Buffer information
class ITK_BUFFER_INFO(Structure):
    _fields_ = [("State",c_uint8),     
                ("HasChunkData",c_uint8),
                ("NeedAutoConvert",c_char),
                ("Reserved8",c_char*5),
                ("BaseAddress",c_void_p),
                ("ImageAddress",c_void_p),
                ("ValidImageHeight",c_int64),
                ("ValidImageSize",c_int64),
                ("ImageWidth",c_int64),
                ("ImageHeight",c_int64),
                ("PixelFormat",c_int64),  
                ("ImagePixelDepth",c_int64),  
                ("ImageSize",c_int64),  
                ("TotalSize",c_int64),  
                ("BlockID",c_int64),  
                ("ErrorReason",c_int64),  
                ("TimestampNs",c_int64), 
                ("GevResendPacketCount",c_int64), 
                ("GevLostPacketCount",c_int64), 
                ("FrameStartTimestampFromCameraNs",c_int64), 
                ("Reserved64",c_int64 * 23)] 

# Feature base information
class ITK_FEATURE_BASE_INFO(Structure):
    _fields_ = [("IsStreamable",c_uint8),
               ("IsDeprecated",c_uint8),
               ("IsSelector",c_uint8),
               ("NameSpace",c_uint8),
               ("Type",c_uint8),
               ("Visibility",c_uint8),
               ("Representation",c_uint8),
               ("CachingMode",c_uint8),
               ("EnumCount",c_uint8),
               ("Reserved_8",c_uint8*31),
               ("Length",c_int64),
               ("PollingTime",c_int64),
               ("Unit",c_char*32),
               ("EventID",c_char*32),
               ("Name",c_char*64),
               ("Category",c_char*64),
               ("DisplayName",c_char*64),
               ("Tooltip",c_char*512),
               ("Description",c_char*512),
               ("Reserved_char",c_char*512)]

# feature enum entry
class ITK_FEATURE_ENUM_ENTRY_INFO(Structure):
    _fields_ = [("Value", c_int64),
                ("AccessMode",c_int64),
                ("ValueStr", c_char*64),
                ("DisplayName",c_char*64),
                ("Tooltip", c_char*512),
                ("Description", c_char*512)]

class ITK_DEVEVENT_INFO(Structure):
    _fields_ = [("eventName",c_char*128),
                ("eventSource",c_char*128),
                ("blockID",c_uint64),
                ("eventID",c_uint16),
                ("timestamp",c_uint64),
                ("eventData",c_void_p),
                ("eventDataLength",c_uint)]

ITKBUFFER_FORMAT_COLOR = 0x01000000

def ITKBUFFER_FORMAT_PIXEL_BITS(format_val):
    """
    @brief 单个像素深度 / Single pixel size
    @param format_val: 格式值
    @return: 像素位数
    """
    return (format_val >> 8) & 0xFF

def ITKBUFFER_FORMAT_CHANNEL_BITS(format_val):
    """
    @brief 单个通道深度 / Single channel size
    @param format_val: 格式值
    @return: 通道位数
    """
    return (format_val >> 16) & 0xFF

def ITKBUFFER_FORMAT_IS_COLOR(format_val):
    """
    @brief 像素格式是否为彩色 / Whether the pixel format is color
    @param format_val: 格式值
    @return: 1表示彩色，0表示非彩色
    """
    return 1 if (format_val & ITKBUFFER_FORMAT_COLOR) else 0

def ITKBUFFER_FORMAT_IMAGE_CHANNELS(format_val):
    """
    @brief 获取图像通道数 / Get the number of image channels
    @param format_val: 格式值
    @return: 通道数量
    """
    pixel_bits = ITKBUFFER_FORMAT_PIXEL_BITS(format_val)
    channel_bits = ITKBUFFER_FORMAT_CHANNEL_BITS(format_val)
    
    # 避免除零错误
    if channel_bits == 0:
        return 0
    
    channels = pixel_bits // channel_bits
    
    # 检查是否为彩色且通道数大于3
    is_color = ITKBUFFER_FORMAT_IS_COLOR(format_val)
    if channels > 3 and is_color:
        return 3
    else:
        return channels

# Initialize IKapC standard API
def ItkManInitialize():
    return libIKapC.ItkManInitialize()

# Terminate IKapC standard API
def ItkManTerminate():
    return libIKapC.ItkManTerminate()

# Get the number of available device
def ItkManGetDeviceCount():
    nDevCount = c_uint()
    res = libIKapC.ItkManGetDeviceCount(byref(nDevCount))
    return res,nDevCount.value

#  Get information about camera device identified by its index.
def ItkManGetDeviceInfo(nIndex):
    devInfo = ITKDEV_INFO()
    res = libIKapC.ItkManGetDeviceInfo(nIndex,byref(devInfo))
    return res,devInfo

# Get the number of available board
def ItkManGetBoardCount():
    nDevCount = c_uint()
    res = libIKapC.ItkManGetBoardCount(byref(nDevCount))
    return res,nDevCount.value

#  Get information about board device identified by its index.
def ItkManGetBoardInfo(nIndex):
    devInfo = ITKBOARD_INFO()
    res = libIKapC.ItkManGetBoardInfo(nIndex,byref(devInfo))
    return res,devInfo

#  Get information about gv camera device identified by its index.
def ItkManGetGigEDeviceInfo(nIndex):
    devInfo = ITKGIGEDEV_INFO()
    res = libIKapC.ItkManGetGigEDeviceInfo(nIndex,byref(devInfo))
    return res,devInfo

#  Get information about cl camera device identified by its index.
def ItkManGetCLDeviceInfo(nIndex):
    devInfo = ITK_CL_DEV_INFO()
    res = libIKapC.ItkManGetCLDeviceInfo(nIndex,byref(devInfo))
    return res,devInfo

#  Get information about cxp camera device identified by its index.
def ItkManGetCXPDeviceInfo(nIndex):
    devInfo = ITK_CXP_DEV_INFO()
    res = libIKapC.ItkManGetCXPDeviceInfo(nIndex,byref(devInfo))
    return res,devInfo

#  Get information about USB3Vision camera device identified by its index.
def ItkManGetU3VDeviceInfo(nIndex):
    devInfo = ITK_U3V_DEV_INFO()
    res = libIKapC.ItkManGetU3VDeviceInfo(nIndex,byref(devInfo))
    return res,devInfo
    
    #  Get information about cxp camera device identified by its index.
def ItkManGetGVBDeviceInfo(nIndex):
    devInfo = ITK_GVB_DEV_INFO()
    res = libIKapC.ItkManGetGVBDeviceInfo(nIndex,byref(devInfo))
    return res,devInfo

# get manager parameter value
def ItkManGetPrm(prm,prmValue):
    res = libIKapC.ItkManGetPrm(prm,byref(prmValue))
    return res,prm.value

# Set manager parameter value
def ItkManSetPrm(hDev,prm,prmValue):
    return libIKapC.ItkManSetPrm(prm,ctypes.pointer(prmValue))

# Open a device
def ItkDevOpen(nIndex,nAccessMode):
    hDev = c_void_p()
    res = libIKapC.ItkDevOpen(nIndex,nAccessMode,byref(hDev))
    return res,hDev

# Close a device
def ItkDevClose(hDev):
    return libIKapC.ItkDevClose(hDev)

# Import the device configuration file
def ItkDevLoadConfigurationFromFile(hDev,strFileName):
    return libIKapC.ItkDevLoadConfigurationFromFile(hDev,strFileName)

# Save the device configuration file
def ItkDevSaveConfigurationToFile(hDev,strFileName):
    return libIKapC.ItkDevSaveConfigurationToFile(hDev,strFileName)

# Get the number of features supported by the device
def ItkDevGetFeatureCount(hDev):
    nFeatureCount = c_uint()
    res = libIKapC.ItkDevGetFeatureCount(hDev,byref(nFeatureCount))
    return res,nFeatureCount.value

# Get the name of a feature associated with a specified index
def ItkDevGetFeatureName(hDev,index):
    name = create_string_buffer(128)
    nameLen = c_int32()
    nameLen.value = 128
    res = libIKapC.ItkDevGetFeatureName(hDev,index,byref(name),byref(nameLen))
    return res,name.value

# Get the number of streams supported by the device
def ItkDevGetStreamCount(hDev):
    nStreamCount = c_int32()
    res = libIKapC.ItkDevGetStreamCount(hDev,byref(nStreamCount))
    return res,nStreamCount.value

# Creates an stream object
def ItkDevAllocStreamEx(hDev,index,count):
    hStream = c_void_p()
    res = libIKapC.ItkDevAllocStreamEx(hDev,index,count,byref(hStream))
    return res,hStream

# Get buffer
def ItkStreamGetBuffer(hStream,index):
    hBuffer = c_void_p()
    res = libIKapC.ItkStreamGetBuffer(hStream,index,byref(hBuffer))
    return res,hBuffer

# Get current buffer
def ItkStreamGetCurrentBuffer(hStream):
    hBuffer = c_void_p()
    res = libIKapC.ItkStreamGetCurrentBuffer(hStream,byref(hBuffer))
    return res,hBuffer

# Destroys a stream object
def ItkDevFreeStream(hStream):
    return libIKapC.ItkDevFreeStream(hStream)

# Returns the number of events supported by the device
def ItkDevGetEventCount(hDev):
    nEventCount = c_int32()
    res = libIKapC.ItkDevGetEventCount(hDev,nEventCount)
    return res,nEventCount.value

# Returns the name of an event associated with a specified index
def ItkDevGetEventName(hDev,index):
    name = create_string_buffer(128)
    nameLen = c_int32()
    nameLen.value = 128
    res = libIKapC.ItkDevGetEventName(hDev,index,byref(name),byref(nameLen))
    return res,name.value

# Returns whether or not an event is supported by the device
def ItkDevIsEventAvailable(hDev,name):
    bAvailable = c_bool()
    res = libIKapC.ItkDevIsEventAvailable(hDev,name,byref(bAvailable))
    return res,bAvailable.value

#  Registers a callback function on the event associated with a specified name
def ItkDevRegisterCallback(hDev,pEventName,callback,pContext):
    return libIKapC.ItkDevRegisterCallback(hDev,pEventName,callback,pContext)

# Unregisters a callback function on the event associated with a specified name
def ItkDevUnregisterCallback(hDev,pEventName):
    return libIKapC.ItkDevUnregisterCallback(hDev,pEventName)

# Get device parameter value from a device object
def ItkDevGetPrm(hDev,prm,prmValue):
    res = libIKapC.ItkDevGetPrm(hDev,prm,byref(prmValue))
    return res,prm.value

# Set device parameter value from a device object
def ItkDevSetPrm(hDev,prm,prmValue):
    return libIKapC.ItkDevSetPrm(hDev,prm,ctypes.pointer(prmValue))

# Perform a raw read on the standard "Device"-node port
def ItkDevPortRead(hDev,buffer,address,length):
    return libIKapC.ItkDevPortRead(hDev,buffer,address,length)

# Perform a raw write on the standard "Device"-node port
def ItkDevPortWrite(hDev,buffer,address,length):
    return libIKapC.ItkDevPortWrite(hDev,buffer,address,length)

# Perform a raw read on the standard "Device"-node serial port
def ItkDevSerialPortRead(hDev,buffer,length,timeout):
    return libIKapC.ItkDevSerialPortRead(hDev,buffer,length,timeout)

# Perform a raw write on the standard "Device"-node serial port
def ItkDevSerialPortWrite(hDev,pBuffer,length,timeout):
    return libIKapC.ItkDevSerialPortWrite(hDev,pBuffer,length,timeout)

# 'Force' a static IP address configuration into a device identified by its MAC Address
def ItkGigEDevForceIp(macAddress,ipAddress,subnetMask,defaultGateway):
    return libIKapC.ItkGigEDevForceIp(macAddress,ipAddress,subnetMask,defaultGateway)

# Reads the persistent IP address from the device
def ItkGigEDevGetPersistentIpAddress(hDev, ipAddress, ipAddressLen, subnetMask, subnetMaskLen, defaultGateway, defaultGatewayLen):
    return libIKapC.ItkGigEDevGetPersistentIpAddress(hDev, ipAddress, ipAddressLen, subnetMask, subnetMaskLen, defaultGateway, defaultGatewayLen)

# Writes the persistent IP address to the device
def ItkGigEDevSetPersistentIpAddress(hDev, ipAddress, subnetMask, defaultGateway):
    return libIKapC.ItkGigEDevSetPersistentIpAddress(hDev, ipAddress, subnetMask, defaultGateway)

# Get Event info
def ItkEventGetInfo(hEventInfo):
    info = ITK_DEVEVENT_INFO()
    res = libIKapC.ItkEventGetInfo(hEventInfo,byref(info))
    return res,info

# Query feature for allowed access modes
def ItkFeatureGetAccessMode(hFeature):
    accessMode = c_uint32()
    res = libIKapC.ItkFeatureGetAccessMode(hFeature,byref(accessMode))
    return res,accessMode.value

# Represents the category of features the current feature belongs to.
# All the features are divided into categories to simplify the presentation of features coming from a large feature set
def ItkFeatureGetCategory(hFeature):
    buffer = create_string_buffer(128)
    bufferSize = c_uint32()
    bufferSize = 128
    res = libIKapC.ItkFeatureGetCategory(hFeature,byref(buffer),byref(bufferSize))
    return res,buffer.value

# Get feature display name
def ItkFeatureGetDisplayName(hFeature):
    buffer = create_string_buffer(128)
    bufferSize = c_uint32()
    bufferSize = 128
    res = libIKapC.ItkFeatureGetDisplayName(hFeature,byref(buffer),byref(bufferSize))
    return res,buffer.value

# Get feature tool tip name
def ItkFeatureGetTooltip(hFeature):
    buffer = create_string_buffer(128)
    bufferSize = c_uint32()
    bufferSize = 128
    res = libIKapC.ItkFeatureGetTooltip(hFeature,byref(buffer),byref(bufferSize))
    return res,buffer.value

# Return a feature's description text
def ItkFeatureGetDescription(hFeature):
    buffer = create_string_buffer(128)
    bufferSize = c_uint32()
    bufferSize = 128
    res = libIKapC.ItkFeatureGetDescription(hFeature,byref(buffer),byref(bufferSize))
    return res,buffer.value

# Return a feature's name space
def ItkFeatureGetNameSpace(hFeature):
    nameSpace = c_uint32()
    res = libIKapC.ItkFeatureGetNameSpace(hFeature,byref(nameSpace))
    return res,nameSpace.value

# Get feature visibility
def ItkFeatureGetVisibility(hFeature):
    visibility = c_uint32()
    res = libIKapC.ItkFeatureGetVisibility(hFeature,byref(visibility))
    return res,visibility.value

# Get feature representation
def ItkFeatureGetRepresentation(hFeature):
    representation = c_uint32()
    res = libIKapC.ItkFeatureGetRepresentation(hFeature,byref(representation))
    return res,representation.value

# Return an integer feature's minimum value
def ItkFeatureGetInt64Min(hFeature):
    featureValue = c_int64()
    res = libIKapC.ItkFeatureGetInt64Min(hFeature,byref(featureValue))
    return res,featureValue.value

# Return an integer feature's maximum value
def ItkFeatureGetInt64Max(hFeature):
    featureValue = c_int64()
    res = libIKapC.ItkFeatureGetInt64Max(hFeature,byref(featureValue))
    return res,featureValue.value

# Return an integer feature's increment value
def ItkFeatureGetInt64Inc(hFeature):
    featureValue = c_int64()
    res = libIKapC.ItkFeatureGetInt64Inc(hFeature,byref(featureValue))
    return res,featureValue.value

# Return an integer feature's value
def ItkFeatureGetInt64(hFeature):
    featureValue = c_int64()
    res = libIKapC.ItkFeatureGetInt64(hFeature,byref(featureValue))
    return res,featureValue.value

# Set an integer feature's value
def ItkFeatureSetInt64(hFeature,featureValue):
    return libIKapC.ItkFeatureSetInt64(hFeature,ctypes.c_longlong(featureValue))

# Return an 64bit floating feature's minimum value
def ItkFeatureGetDoubleMin(hFeature):
    featureValue = c_double()
    res = libIKapC.ItkFeatureGetDoubleMin(hFeature,byref(featureValue))
    return res,featureValue.value

# Return an 64bit floating feature's maximum value
def ItkFeatureGetDoubleMax(hFeature):
    featureValue = c_double()
    res = libIKapC.ItkFeatureGetDoubleMax(hFeature,byref(featureValue))
    return featureValue.value

# Return an 64bit floating feature's increment value
def ItkFeatureGetDoubleInc(hFeature):
    featureValue = c_double()
    res = libIKapC.ItkFeatureGetDoubleInc(hFeature,byref(featureValue))
    return res,featureValue.value

# Return an 64bit floating feature's value
def ItkFeatureGetDouble(hFeature):
    featureValue = c_double()
    res = libIKapC.ItkFeatureGetDouble(hFeature,byref(featureValue))
    return res,featureValue.value

# Set an 64bit floating feature's value
def ItkFeatureSetDouble(hFeature,featureValue):
    return libIKapC.ItkFeatureSetDouble(hFeature,ctypes.c_double(featureValue))

# Return a bool feature's value
def ItkFeatureGetBool(hFeature):
    featureValue = c_bool()
    res = libIKapC.ItkFeatureGetBool(hFeature,byref(featureValue))
    return res,featureValue.value

# Set a bool feature's value
def ItkFeatureSetBool(hFeature,featureValue):
    return libIKapC.ItkFeatureSetBool(hFeature,ctypes.c_bool(featureValue))

# Get a string feature value
def ItkFeatureToString(hFeature,featureValue):
    buffer = create_string_buffer(128)
    bufferSize = c_uint32()
    bufferSize.value = 128
    res = libIKapC.ItkFeatureToString(hFeature,featureValue,byref(buffer),byref(bufferSize))
    return res,buffer.value

# Returns the number of items in an enumeration
def ItkFeatureGetEnumCount(hFeature):
    enumCount = c_uint32()
    res = libIKapC.ItkFeatureGetEnumCount(hFeature,byref(enumCount))
    return res,enumCount.value

# Returns the enumeration string corresponding to a specified index
def ItkFeatureGetEnumString(hFeature,index):
    enumString = create_string_buffer(128)
    enumStringSize = c_uint32()
    enumStringSize = 128
    res = libIKapC.ItkFeatureGetEnumString(hFeature,index,byref(enumString),byref(enumStringSize))
    return res,enumString.value

# Returns whether or not the enumeration item corresponding to a specified index is available
def ItkFeatureGetEnumIsAvailable(hFeature,enumString):
    bAvailable = c_bool()
    res = libIKapC.ItkFeatureGetEnumIsAvailable(hFeature,enumString,byref(bAvailable))
    return res,bAvailable.value

# Execute a command
def ItkFeatureExecuteCommand(hFeature):
    return libIKapC.ItkFeatureExecuteCommand(hFeature)

# Indicates if that node is a selector
def ItkFeatureIsSelector(hFeature):
    bSelector = c_bool()
    res = libIKapC.ItkFeatureIsSelector(hFeature,byref(bSelector))
    return res,bSelector.value

# Return the number of selected nodes
def ItkFeatureGetSelectedFeatureCounts(hFeature):
    selectedCount = c_uint32()
    res = libIKapC.ItkFeatureGetSelectedFeatureCounts(hFeature,byref(selectedCount))
    return res,selectedCount.value

# Get a selected feature name by its index
def ItkFeatureGetSelectedFeatureName(hFeature,index):
    featureName = create_string_buffer(128)
    featureNameSize = c_uint32()
    featureNameSize = 128
    res = libIKapC.ItkFeatureGetSelectedFeatureName(hFeature,index,byref(featureName),byref(featureNameSize))
    return res,featureName.value

# Get the interval of time between two consecutive feature updates
def ItkFeatureGetPollingTime(hFeature):
    pollingTime = c_uint32()
    res = libIKapC.ItkFeatureGetPollingTime(hFeature,byref(pollingTime))
    return res,pollingTime.value

# Query feature for allowed access modes
def ItkDevGetAccessMode(hDev,featureName):
    accessMode = c_uint32()
    res = libIKapC.ItkDevGetAccessMode(hDev,featureName,byref(accessMode))
    return res,accessMode.value

# Represents the category of features the current feature belongs to.
# All the features are divided into categories to simplify the presentation of features coming from a large feature set
def ItkDevGetCategory(hDev,featureName):
    buffer = create_string_buffer(128)
    bufferSize = c_uint32()
    bufferSize = 128
    res = libIKapC.ItkDevGetCategory(hDev,featureName,byref(buffer),byref(bufferSize))
    return res,buffer.value

# Get feature display name
def ItkDevGetDisplayName(hDev,featureName):
    buffer = create_string_buffer(128)
    bufferSize = c_uint32()
    bufferSize = 128
    res = libIKapC.ItkDevGetDisplayName(hDev,featureName,byref(buffer),byref(bufferSize))
    return res,buffer.value

# Get feature tool tip name
def ItkDevGetTooltip(hDev,featureName):
    buffer = create_string_buffer(128)
    bufferSize = c_uint32()
    bufferSize = 128
    res = libIKapC.ItkDevGetTooltip(hDev,featureName,byref(buffer),byref(bufferSize))
    return res,buffer.value

# Return a feature's description text
def ItkDevGetDescription(hDev,featureName):
    buffer = create_string_buffer(128)
    bufferSize = c_uint32()
    bufferSize = 128
    res = libIKapC.ItkDevGetDescription(hDev,featureName,byref(buffer),byref(bufferSize))
    return res,buffer.value

# Return a feature's name space
def ItkDevGetNameSpace(hDev,featureName):
    nameSpace = c_uint32()
    res = libIKapC.ItkDevGetNameSpace(hDev,featureName,byref(nameSpace))
    return res,nameSpace.value

# Get feature visibility
def ItkDevGetVisibility(hDev,featureName):
    visibility = c_uint32()
    res = libIKapC.ItkDevGetVisibility(hDev,featureName,byref(visibility))
    return res,visibility.value

# Get feature representation
def ItkDevGetRepresentation(hDev,featureName):
    representation = c_uint32()
    res = libIKapC.ItkDevGetRepresentation(hDev,featureName,byref(representation))
    return res,representation.value

# Return an integer feature's minimum value
def ItkDevGetInt64Min(hDev,featureName):
    featureValue = c_int64()
    res = libIKapC.ItkDevGetInt64Min(hDev,featureName,byref(featureValue))
    return res,featureValue.value

# Return an integer feature's maximum value
def ItkDevGetInt64Max(hDev,featureName):
    featureValue = c_int64()
    res = libIKapC.ItkDevGetInt64Max(hDev,featureName,byref(featureValue))
    return res,featureValue.value

# Return an integer feature's increment value
def ItkDevGetInt64Inc(hDev,featureName):
    featureValue = c_int64()
    res = libIKapC.ItkDevGetInt64Inc(hDev,featureName,byref(featureValue))
    return res,featureValue.value

# Return an integer feature's value
def ItkDevGetInt64(hDev,featureName):
    featureValue = c_int64()
    res = libIKapC.ItkDevGetInt64(hDev,featureName,byref(featureValue))
    return res,featureValue.value

# Set an integer feature's value
def ItkDevSetInt64(hDev,featureName,featureValue):
    return libIKapC.ItkDevSetInt64(hDev,featureName,ctypes.c_longlong(featureValue))

# Return an 64bit floating feature's minimum value
def ItkDevGetDoubleMin(hDev,featureName):
    featureValue = c_double()
    res = libIKapC.ItkDevGetDoubleMin(hDev,featureName,byref(featureValue))
    return res,featureValue.value

# Return an 64bit floating feature's maximum value
def ItkDevGetDoubleMax(hDev,featureName):
    featureValue = c_double()
    res = libIKapC.ItkDevGetDoubleMax(hDev,featureName,byref(featureValue))
    return res,featureValue.value

# Return an 64bit floating feature's increment value
def ItkDevGetDoubleInc(hDev,featureName):
    featureValue = c_double()
    res = libIKapC.ItkDevGetDoubleInc(hDev,featureName,byref(featureValue))
    return res,featureValue.value

# Return an 64bit floating feature's value
def ItkDevGetDouble(hDev,featureName):
    featureValue = c_double()
    res = libIKapC.ItkDevGetDouble(hDev,featureName,byref(featureValue))
    return res,featureValue.value

# Set an 64bit floating feature's value
def ItkDevSetDouble(hDev,featureName,featureValue):
    return libIKapC.ItkDevSetDouble(hDev,featureName,ctypes.c_double(featureValue))

# Return a bool feature's value
def ItkDevGetBool(hDev,featureName):
    featureValue = c_bool()
    res = libIKapC.ItkDevGetBool(hDev,featureName,byref(featureValue))
    return res,featureValue.value

# Set a bool feature's value
def ItkDevSetBool(hDev,featureName,featureValue):
    return libIKapC.ItkDevSetBool(hDev,featureName,ctypes.c_bool(featureValue))

# Get a string feature value
def ItkDevToString(hDev,featureName):
    featureValue = create_string_buffer(128)
    featureValueSize = c_uint32()
    featureValueSize.value = 128
    res = libIKapC.ItkDevToString(hDev,featureName,byref(featureValue),byref(featureValueSize))
    return res,featureValue.value

# Set a feature's value from a string
def ItkDevFromString(hDev,featureName,featureValue):
    res = libIKapC.ItkDevFromString(hDev,featureName,featureValue)
    return res

# Get base information of a feature with a specific name 
def ItkDevGetFeatureInfo(hDev, name):
    featureInfo = ITK_FEATURE_BASE_INFO()
    res = libIKapC.ItkDevGetFeatureInfo(hDev, name, byref(featureInfo))
    return res,featureInfo

# Returns the enumeration entry corresponding to a specified index
def ItkDevGetEnumEntryFeatureInfo(hDev, featureName, enumIndex):
    entryInfo = ITK_FEATURE_ENUM_ENTRY_INFO()
    res = libIKapC.ItkDevGetEnumEntryFeatureInfo(hDev, featureName, enumIndex, byref(entryInfo))
    return res,entryInfo

# Returns whether or not the enumeration item corresponding to a specified index is available
def ItkDevGetEnumIsAvailable(hDev,featureName,enumString):
    bAvailable = c_bool()
    res = libIKapC.ItkDevGetEnumIsAvailable(hDev,featureName,enumString,byref(bAvailable))
    return res,bAvailable.value

# Execute a command
def ItkDevExecuteCommand(hDev,featureName):
    return libIKapC.ItkDevExecuteCommand(hDev,featureName)

# Indicates if that node is a selector
def ItkDevIsSelector(hDev,featureName):
    bSelector = c_bool()
    res = libIKapC.ItkDevIsSelector(hDev,featureName,byref(bSelector))
    return res,bSelector.value

# Return the number of selected nodes
def ItkDevGetSelectedFeatureCounts(hDev,featureName):
    selectedCount = c_uint32()
    res = libIKapC.ItkDevGetSelectedFeatureCounts(hDev,featureName,byref(selectedCount))
    return res,selectedCount.value

# Get a selected feature name by its index
def ItkDevGetSelectedFeatureName(hDev,featureName,index):
    featureName = create_string_buffer(128)
    featureNameSize = c_uint32()
    featureNameSize = 128
    res = libIKapC.ItkDevGetSelectedFeatureName(hDev,featureName,index,byref(featureName),byref(featureNameSize))
    return res,featureName.value

# Get the interval of time between two consecutive feature updates
def ItkDevGetPollingTime(hDev,featureName):
    pollingTime = c_uint32()
    res = libIKapC.ItkDevGetPollingTime(hDev,featureName,byref(pollingTime))
    return res,pollingTime.value

# Stop stream transfer asynchronously for a stream resource
def ItkStreamAbort(hStream):
    return libIKapC.ItkStreamAbort(hStream)

# Append buffer to the tail of stream destination
def ItkStreamAddBuffer(hStream,hBuffer):
    return libIKapC.ItkStreamAddBuffer(hStream,hBuffer)

# Remove buffer from stream buffer list
def ItkStreamRemoveBuffer(hStream,hBuffer):
    return libIKapC.ItkStreamRemoveBuffer(hStream,hBuffer)

# Clear buffer status
def ItkStreamClearBuffer(hStream,hBuffer):
    return libIKapC.ItkStreamClearBuffer(hStream,hBuffer)

# Get stream parameter value from a stream resource
def ItkStreamGetPrm(hStream,prm,prmValue):
    res = libIKapC.ItkStreamGetPrm(hStream,prm,byref(prmValue))
    return res,prmValue.value

# Set stream parameter value from a stream resource
def ItkStreamSetPrm(hStream,prm,prmValue):
    return libIKapC.ItkStreamSetPrm(hStream,prm,ctypes.pointer(prmValue))

# Start stream image for a transfer resource
def ItkStreamStart(hStream,nCount):
    return libIKapC.ItkStreamStart(hStream,nCount)

# Stop stream image for a transfer resource
def ItkStreamStop(hStream):
    return libIKapC.ItkStreamStop(hStream)

# Wait stream image for a transfer resource
def ItkStreamWait(hStream):
    return libIKapC.ItkStreamWait(hStream)

# Register callback function for a stream resource
def ItkStreamRegisterCallback(hStream, eventType, callback, context):
    return libIKapC.ItkStreamRegisterCallback(hStream, eventType, callback, context)

# Unregister callback function for a stream resource
def ItkStreamUnregisterCallback(hStream, eventType):
    return libIKapC.ItkStreamUnregisterCallback(hStream, eventType)

# Create a new buffer resource
def ItkBufferNew(width,height,format):
    hBuffer = c_void_p()
    res = libIKapC.ItkBufferNew(width,height,format,byref(hBuffer))
    return res,hBuffer

# Free a buffer resource
def ItkBufferFree(hBuffer):
    return libIKapC.ItkBufferFree(hBuffer)

# Gets buffer info from a buffer resource
def ItkBufferGetInfo(hBuffer):
    bufferInfo = ITK_BUFFER_INFO()
    res = libIKapC.ItkBufferGetInfo(hBuffer,byref(bufferInfo))
    return res,bufferInfo

#  Set a simple buffer parameter of a buffer resource
def ItkBufferSetPrm(hBuffer,prm,prmValue):
    return libIKapC.ItkBufferSetPrm(hBuffer,prm,ctypes.pointer(prmValue))

# Read a series of elements from a buffer resource
def ItkBufferRead(hBuffer,offset,bufferData,size):
    return libIKapC.ItkBufferRead(hBuffer,offset,byref(bufferData),size)

# Read a series of elements from a buffer resource
def ItkBufferReadElement(hBuffer,posX,posY,element,size):
    return libIKapC.ItkBufferReadElement(hBuffer,posX,posY,element,size)

# Read a set of linearly positioned elements from a buffer resource
def ItkBufferReadLine(hBuffer,startX,startY,endX,endY,uElements,bufferData,size):
    return libIKapC.ItkBufferReadLine(hBuffer,startX,startY,endX,endY,uElements,bufferData,size)

# Read a set of elements forming a rectangular area from a buffer resource
def ItkBufferReadRect(hBuffer,offsetX,offsetY,width,height,bufferData,size):
    return libIKapC.ItkBufferReadRect(hBuffer,offsetX,offsetY,width,height,bufferData,size)

# Write a series of elements to a buffer resource
def ItkBufferWrite(hBuffer, offset, data, size):
    return libIKapC.ItkBufferWrite(hBuffer, offset, data, size)

# Write an element to a buffer resource
def ItkBufferWriteElement(hBuffer, posX, posY, element, size):
    return libIKapC.ItkBufferWriteElement(hBuffer, posX, posY, element, size)

# Write a set of linearly positioned elements to a buffer resource
def ItkBufferWriteLine(hBuffer, startX, startY, endX, endY, uElements, data, size):
    return libIKapC.ItkBufferWriteLine(hBuffer, startX, startY, endX, endY, uElements, data, size)

# Write a set of elements forming a rectangular area to a buffer resource
def ItkBufferWriteRect(hBuffer, offsetX, offsetY, width, height, data, size):
    return libIKapC.ItkBufferWriteRect(hBuffer, offsetX, offsetY, width, height, data, size) 

# Converts a Bayer-encoded image to an RGB image
def ItkBufferBayerConvert(hSrcBuffer, hDstBuffer, options):
    return libIKapC.ItkBufferBayerConvert(hSrcBuffer, hDstBuffer, options)

# Clears contents of a buffer resource by writing a color value to all buffer elements
def ItkBufferClear(hBuffer,  pValue, size):
    return libIKapC.ItkBufferClear(hBuffer,  pValue, size)

# Clears buffer resource contents to the corresponding black color
def ItkBufferClearBlack(hBuffer):
    return libIKapC.ItkBufferClearBlack(hBuffer)

#  Copies the source buffer to location (dstOffsetX, dstOffsetY) of the destination buffer
def ItkBufferCopy(hSrcBuffer, dstOffsetX, dstOffsetY, hDstBuffer):
    return libIKapC.ItkBufferCopy(hSrcBuffer, dstOffsetX, dstOffsetY, hDstBuffer)

# Copies a rectangular area of the source buffer, defined by (srcOffsetX, srcOffsetY, width, height), 
# to the location (dstOffsetX, dstOffsetY) in the destination buffer
def ItkBufferCopyRect(hSrcBuffer, srcOffsetX, srcOffsetY, width, height, hDstBuffer, dstOffsetX, dstOffsetY):
    return libIKapC.ItkBufferCopyRect(hSrcBuffer, srcOffsetX, srcOffsetY, width, height, hDstBuffer, dstOffsetX, dstOffsetY)

# Saves the content of a buffer resource to a file
def ItkBufferSave(hBuffer, filename, options):
    return libIKapC.ItkBufferSave(hBuffer, filename, options)

# Load an image from a file into a buffer resource
def ItkBufferLoad(hBuffer, filename, options):
    return libIKapC.ItkBufferLoad(hBuffer, filename, options)

# Denoise a image by GIMP algothrim
def ItkBufferDenoise(hSrc, hDst, threshold):
    return libIKapC.ItkBufferDenoise(hSrc, hDst, threshold)

def ItkBufferToNumPy(hBuffer):
    if have_numpy == 0:
        msg = ("Need install numpy to use ItkBufferToNumpy. ")
        raise TypeError(msg)
    res,bufferInfo = ItkBufferGetInfo(hBuffer)
    #if res != IKapCDef.ITKSTATUS_OK:
    if res != 0:
        return res,np.zeros(0)
    
    bufferWidth = bufferInfo.ImageWidth
    bufferHeight = bufferInfo.ImageHeight
    bufferAddress = bufferInfo.ImageAddress
    channels = ITKBUFFER_FORMAT_IMAGE_CHANNELS(bufferInfo.PixelFormat)
    bufferDepth = bufferInfo.ImagePixelDepth/channels
    if bufferDepth > 8:		
        ctypes_pntr = ctypes.cast(bufferAddress, ctypes.POINTER(ctypes.c_uint16))		
        arr_noowner = np.ctypeslib.as_array(ctypes_pntr, shape=(bufferHeight,bufferWidth,int(bufferInfo.ImagePixelDepth/16)))		
        return res,arr_noowner		
    else:		
        ctypes_pntr = ctypes.cast(bufferAddress, ctypes.POINTER(ctypes.c_ubyte))		
        arr_noowner = np.ctypeslib.as_array(ctypes_pntr, shape=(bufferHeight,bufferWidth,int(bufferInfo.ImagePixelDepth/8)))
        return res,arr_noowner

# ItkBuffer3DSplit
def ItkBuffer3DSplit(hBuffer, splitOutBuffer, options1,options2):
    return libIKapC.ItkBuffer3DSplit(hBuffer, splitOutBuffer, options1,options2)

def ItkBufferNeedAutoConvert(hBuffer):
    isNeedAutoConvert = ctypes.c_bool(False)
    res = libIKapC.ItkBufferNeedAutoConvert(hBuffer, byref(isNeedAutoConvert))
    return res,isNeedAutoConvert

def ItkBufferConvert(hsrc,hdst,dstFormat,option):
    res = libIKapC.ItkBufferConvert(hsrc,hdst,dstFormat,option)
    return res

# Get Event info
def ItkEventGetInfo(hEventInfo):
    info = ITK_DEVEVENT_INFO()
    res = libIKapC.ItkEventGetInfo(hEventInfo,byref(info))
    return res,info