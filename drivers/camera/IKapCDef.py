#coding=utf-8

# Manager Parameters
ITKMANAGER_PRM_FIRST = 0
def ITKMANAGER_PRM(n, size):
    return ((((n) + ITKMANAGER_PRM_FIRST) << 16) | (size))

ITKMANAGER_COAXPRESS_12_SUPPORT                 = ITKMANAGER_PRM(0, 4)         # board width
ITKMANAGER_COAXPRESS_COMMUNICATION_TAG_SUPPORT  = ITKMANAGER_PRM(1, 4)        # board height
ITKMANAGER_COAXPRESS_CONTROL_PACKET_MAX_SIZE    = ITKMANAGER_PRM(2, 4)      # board offset x
ITKMANAGER_COAXPRESS_STREAM_PACKET_MAX_SIZE     = ITKMANAGER_PRM(3, 4)      # board offset y

# Board Parameters
ITKBOARD_PRM_FIRST = 0
def ITKBOARD_PRM(n, size):
    return ((((n) + ITKBOARD_PRM_FIRST) << 16) | (size))

ITKBOARD_PRM_WIDTH = ITKBOARD_PRM(0, 4)         # board width
ITKBOARD_PRM_HEIGHT = ITKBOARD_PRM(1, 4)        # board height
ITKBOARD_PRM_OFFSET_X = ITKBOARD_PRM(2, 4)      # board offset x
ITKBOARD_PRM_OFFSET_Y = ITKBOARD_PRM(3, 4)      # board offset y

# Device Parameters
ITKDEV_PRM_FIRST = 0
def ITKDEV_PRM(n,size):
    return ((((n) + ITKDEV_PRM_FIRST) << 16) | (size))

ITKDEV_PRM_HEARTBEAT_TIMEOUT = ITKDEV_PRM(0, 4)             # device heartbeat timeout
ITKDEV_PRM_INTERFACE_TYPE = ITKDEV_PRM(1, 4)                # device interface type           

# IKapC device access modes
ITKDEV_VAL_ACCESS_MODE_MONITOR = 0			                # access in monitor mode(read only)
ITKDEV_VAL_ACCESS_MODE_CONTROL = (1 << 0)                   # access in control mode(read/write only)
ITKDEV_VAL_ACCESS_MODE_STREAM = (1 << 1)                    # access in stream mode(read image date only)
ITKDEV_VAL_ACCESS_MODE_EXCLUSIVE = (1 << 2)                 # access in exclusive mode(only one process could control device)

# Device support event type
ITKDEV_VAL_EVENT_TYPE_DEV_REMOVE = 0x00010000               # Call the callback function after the device closed
ITKDEV_VAL_EVENT_YTPE_FEATURE_VALUE_CHANGED = 0x00020000    # Call the callback function after the device feature value changed
ITKDEV_VAL_EVENT_TYPE_FRAME_TRIGGER_IGNORE  = 0x00040000    # Call when frame trigger ignore happen
ITKDEV_VAL_EVENT_TYPE_LINE_TRIGGER_IGNORE   = 0x00080000    # Call when line trigger ignore happen
ITKDEV_VAL_EVENT_TYPE_FRAME_TRIGGER         = 0x00100000    # Call when frame trigger happen
ITKDEV_VAL_EVENT_TYPE_MASK = 0xffff0000

# Feature Parameters
# IKapC feature data types
ITKFEATURE_VAL_TYPE_UNDEFINED = 0               # feature type invalid
ITKFEATURE_VAL_TYPE_INT32 = 1                   # feature represents an 32bit integer-valued parameter
ITKFEATURE_VAL_TYPE_INT64 = 2                   # feature represents an 64bit integer-valued parameter
ITKFEATURE_VAL_TYPE_FLOAT = 3                   # feature represents a 32bit floating point-valued parameter
ITKFEATURE_VAL_TYPE_DOUBLE = 4                  # feature represents a 64bit floating point-valued parameter
ITKFEATURE_VAL_TYPE_BOOL = 5                    # Node represents a boolean (true/false) parameter
ITKFEATURE_VAL_TYPE_ENUM = 6                    # Node represents an 'enumeration entry' parameter
ITKFEATURE_VAL_TYPE_STRING = 7                  # Node represents a string-valued parameter
ITKFEATURE_VAL_TYPE_COMMAND = 8                 # Node can trigger a command
ITKFEATURE_VAL_TYPE_CATEGORY = 9                # Category include other features

# IKapC feature access mode
ITKFEATURE_VAL_ACCESS_MODE_UNDEFINED = 0        # Access mode invalid
ITKFEATURE_VAL_ACCESS_MODE_RW = 1               # Read and Write
ITKFEATURE_VAL_ACCESS_MODE_RO = 2               # Read Only
ITKFEATURE_VAL_ACCESS_MODE_WO = 3               # Write Only
ITKFEATURE_VAL_ACCESS_MODE_NI = 4               # Not implemented
ITKFEATURE_VAL_ACCESS_MODE_NA = 5               # Not available

# IKapC feature name space
ITKFEATURE_VAL_NAME_SPACE_UNDEFINED = 0         # Name space invalid
ITKFEATURE_VAL_NAME_SPACE_CUSTOM = 1            # Name resides in custom name space
ITKFEATURE_VAL_NAME_SPACE_STANDARD = 2          # Name resides in one of the standard name spaces

# IKapC feature representation
ITKFEATURE_VAL_REPRESENTATION_UNDEFINED = 0     # Undefined representation
ITKFEATURE_VAL_REPRESENTATION_LINEAR = 1        # The feature follows a linear scale	
ITKFEATURE_VAL_REPRESENTATION_LOGARITHMIC = 2   # The feature follows a logarithmic scale
ITKFEATURE_VAL_REPRESENTATION_BOOLEAN = 3       # The feature is a boolean (can have two values: zero or non-zero)
ITKFEATURE_VAL_REPRESENTATION_PURENUMBER = 4    # The feature using an edit box only with decimal display
ITKFEATURE_VAL_REPRESENTATION_HEXNUMBER = 5     # The feature using an edit box with hexadecimal display
ITKFEATURE_VAL_REPRESENTATION_IPV4ADDRESS = 6   # The feature showing like an IP address
ITKFEATURE_VAL_REPRESENTATION_MACADDRESS = 7    # The feature showing like a MAC address

# IKapC feature visibility
ITKFEATURE_VAL_VISIBILITY_UNDEFINED = 0         # Undefined visibility level
ITKFEATURE_VAL_VISIBILITY_BEGINNER = 1          # Specifies that the feature should be made visible to any user
ITKFEATURE_VAL_VISIBILITY_EXPERT = 2            # Specifies that the feature should be made visible to users with a certain level of expertise
ITKFEATURE_VAL_VISIBILITY_GURU = 3              # Specifies that the feature should be made visible to users with a high level of expertise
ITKFEATURE_VAL_VISIBILITY_INVISIBLE = 4         # Specifies that the feature should not be made visible to any user.This level of visibility is normally used on obsolete or internal features

# IKapC feature signed
ITKFEATURE_VAL_SIGN_UNDEFINED = 0               # Sign is undefined
ITKFEATURE_VAL_SIGN_SIGNED = 1                  # The feature is a signed integer of float
ITKEFATURE_VAL_SIGN_UNSIGNED = 2                # The feature is an unsigned integer of float


#  Event info Parameters
ITKEVENTINFO_PRM_FIRST = 0
def ITKEVENTINFO_PRM(n, size):
    return ((((n) + ITKDEV_PRM_FIRST) << 16) | (size))

ITKEVENTINFO_PRM_TYPE = ITKEVENTINFO_PRM(0, 4)              # Event info type  
ITKEVENTINFO_PRM_FEATURE_NAME = ITKEVENTINFO_PRM(1, 128)    # Event info of feature name
ITKEVENTINFO_PRM_HOST_TIME_STAMP = ITKEVENTINFO_PRM(2, 8)   # Host time stamp

# Buffer Parameters
ITKBUFFFER_PRM_FIRST = 0
def ITKBUFFER_PRM(n, size):
    return ((((n) + ITKBUFFFER_PRM_FIRST) << 16) | (size))

ITKBUFFER_PRM_FORMAT            =       ITKBUFFER_PRM(0, 4)					# Buffer pixel format
ITKBUFFER_PRM_DATA_BIT			=		ITKBUFFER_PRM(1, 4)					# Buffer pixel data size in byte
ITKBUFFER_PRM_PIXEL_DEPTH		=		ITKBUFFER_PRM(2, 4)					# Buffer pixel depth
ITKBUFFER_PRM_WIDTH				=		ITKBUFFER_PRM(3, 8)					# Buffer width
ITKBUFFER_PRM_HEIGHT			=		ITKBUFFER_PRM(4, 8)					# Buffer height
ITKBUFFER_PRM_ADDRESS			=		ITKBUFFER_PRM(5, 8)                 # Buffer address
ITKBUFFER_PRM_HOST_COUNTER_STAMP=		ITKBUFFER_PRM(6, 8)					# Buffer host counter stamp
ITKBUFFER_PRM_STATE				=		ITKBUFFER_PRM(7, 4)					# Buffer state
ITKBUFFER_PRM_SIGNED			=		ITKBUFFER_PRM(8, 4)					# Sign of buffer state
ITKBUFFER_PRM_SIZE				=		ITKBUFFER_PRM(9, 8)					# Buffer size, which is calculated with formult: size = width*height*data_bits/8
ITKBUFFER_PRM_BLOCK_ID          =       ITKBUFFER_PRM(10, 8)                # Buffer bloc id. For GigEVision Camera, the sequence number starts with 1 and wraps at 65535. The value 0 has a special meaning and indicates that this feature is not supported by the camera
ITKBUFFER_PRM_READY_LINES       =       ITKBUFFER_PRM(11, 8)                # Current ready lines in buffer
ITKBUFFER_PRM_ERROR_REASON      =       ITKBUFFER_PRM(12, 4)                # error reason of buffer, 0 means complete buffer other value means incomplete buffer
ITKBUFFER_PRM_RSND_PKT_COUNT    =       ITKBUFFER_PRM(13, 8)                # Current resend packet count in buffer
ITKBUFFER_PRM_LOST_PKT_COUNT    =       ITKBUFFER_PRM(14, 8)                # Current lost packet count in buffer
ITKBUFFER_PRM_FIND_LINE_RESULT  =       ITKBUFFER_PRM(15, 33 * 2 * 8)       # Current result of fine line in buffer
ITKBUFFER_PRM_EXCHANGE_WIDTH_HEIGHT =   ITKBUFFER_PRM(16, 4)                # Exchange Buffer's width and height
ITKBUFFER_PRM_BATCH_STATUS_ADDRESS  =   ITKBUFFER_PRM(17, 8)                # batch status address

# Buffer data format definitions 
# (32-bit format descriptor)
#
# Bits     Description
#
# 0-7:     Index(used by internal implementation as an index to function table)
# 8-15:    Number of bits per pixel
# 16-23:   Pixel depth
# 24:		Color (true if it's a color format)
# 25:		Sign (used by monochrome formats)
def ITKBUFFER_FORMAT(nDepth, nBits, index):
	return (((nDepth) << 16) | ((nBits) << 8) | index)

# Color: bit 24
ITKBUFFER_FORMAT_MONO					=	0x00000000                      # Buffer format is monochrome
ITKBUFFER_FORMAT_COLOR					=	0x01000000                      # Buffer format is color

# Sign: bit 25
ITKBUFFER_FORMAT_UNSIGNED				=	0x00000000                      # Buffer format is unsigned
ITKBUFFER_FORMAT_SIGNED					=	0x02000000                      # Buffer format is signed

# Monochrome data formats
ITKBUFFER_VAL_FORMAT_MONO8				=	(ITKBUFFER_FORMAT(8,  8,  0x01) | ITKBUFFER_FORMAT_MONO | ITKBUFFER_FORMAT_UNSIGNED)            # Indicates it's a monochrome 8 format	
ITKBUFFER_VAL_FORMAT_MONO10				=	(ITKBUFFER_FORMAT(10, 16, 0x02) | ITKBUFFER_FORMAT_MONO | ITKBUFFER_FORMAT_UNSIGNED)            # Indicates it's a monochrome 10 format
ITKBUFFER_VAL_FORMAT_MONO10PACKED       =   (ITKBUFFER_FORMAT(10, 12, 0x03) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a monochrome 10 packed format
ITKBUFFER_VAL_FORMAT_MONO12				=	(ITKBUFFER_FORMAT(12, 16, 0x04) | ITKBUFFER_FORMAT_MONO | ITKBUFFER_FORMAT_UNSIGNED)            # Indicates it's a monochrome 12 format
ITKBUFFER_VAL_FORMAT_MONO12PACKED		=	(ITKBUFFER_FORMAT(12, 12, 0x05) | ITKBUFFER_FORMAT_MONO | ITKBUFFER_FORMAT_UNSIGNED)            # Indicates it's a monochrome 12 packed format
ITKBUFFER_VAL_FORMAT_MONO14				=	(ITKBUFFER_FORMAT(14, 16, 0x06) | ITKBUFFER_FORMAT_MONO | ITKBUFFER_FORMAT_UNSIGNED)            # Indicates it's a monochroms 14 format
ITKBUFFER_VAL_FORMAT_MONO16				=	(ITKBUFFER_FORMAT(16, 16, 0x07) | ITKBUFFER_FORMAT_MONO | ITKBUFFER_FORMAT_UNSIGNED)            # Indicates it's a monochrome 16 format

ITKBUFFER_VAL_FORMAT_RGB888				=	(ITKBUFFER_FORMAT(8,  24, 0x08) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color RGB 8-8-8 format
ITKBUFFER_VAL_FORMAT_RGB101010			=	(ITKBUFFER_FORMAT(10, 48, 0x09) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color RGB 10-10-10 format
ITKBUFFER_VAL_FORMAT_RGB121212			=	(ITKBUFFER_FORMAT(12, 48, 0x0A) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color RGB 12-12-12 format
ITKBUFFER_VAL_FORMAT_RGB141414			=	(ITKBUFFER_FORMAT(14, 48, 0x0B) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color RGB 14-14-14 format
ITKBUFFER_VAL_FORMAT_RGB161616			=	(ITKBUFFER_FORMAT(16, 48, 0x0C) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color RGB 16-16-16 format

ITKBUFFER_VAL_FORMAT_BGR888				=	(ITKBUFFER_FORMAT(8,  24, 0x0D) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color BGR 8-8-8 format
ITKBUFFER_VAL_FORMAT_BGR101010			=	(ITKBUFFER_FORMAT(10, 48, 0x0E) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color BGR 10-10-10 format
ITKBUFFER_VAL_FORMAT_BGR121212			=	(ITKBUFFER_FORMAT(12, 48, 0x0F) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color BGR 12-12-12 format
ITKBUFFER_VAL_FORMAT_BGR141414			=	(ITKBUFFER_FORMAT(14, 48, 0x10) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color BGR 14-14-14 format
ITKBUFFER_VAL_FORMAT_BGR161616			=	(ITKBUFFER_FORMAT(16, 48, 0x11) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color BGR 16-16-16 format

ITKBUFFER_VAL_FORMAT_BAYER_GR8          =   (ITKBUFFER_FORMAT(8,  8,  0x12) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color bayer GR 8 format
ITKBUFFER_VAL_FORMAT_BAYER_RG8          =   (ITKBUFFER_FORMAT(8,  8,  0x13) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color bayer RG 8 format
ITKBUFFER_VAL_FORMAT_BAYER_GB8          =   (ITKBUFFER_FORMAT(8,  8,  0x14) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color bayer GB 8 format
ITKBUFFER_VAL_FORMAT_BAYER_BG8          =   (ITKBUFFER_FORMAT(8,  8,  0x15) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)           # Indicates it's a color bayer BG 8 format

ITKBUFFER_VAL_FORMAT_BAYER_GR10         =   (ITKBUFFER_FORMAT(10,  16,  0x16) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer GR 10 format
ITKBUFFER_VAL_FORMAT_BAYER_RG10         =   (ITKBUFFER_FORMAT(10,  16,  0x17) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer RG 10 format
ITKBUFFER_VAL_FORMAT_BAYER_GB10         =   (ITKBUFFER_FORMAT(10,  16,  0x18) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer GB 10 format
ITKBUFFER_VAL_FORMAT_BAYER_BG10         =   (ITKBUFFER_FORMAT(10,  16,  0x19) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer BG 10 format

ITKBUFFER_VAL_FORMAT_BAYER_GR10PACKED   =   (ITKBUFFER_FORMAT(10,  12,  0x1A) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer GR 10 pakced format
ITKBUFFER_VAL_FORMAT_BAYER_RG10PACKED   =   (ITKBUFFER_FORMAT(10,  12,  0x1B) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer RG 10 packed format
ITKBUFFER_VAL_FORMAT_BAYER_GB10PACKED   =   (ITKBUFFER_FORMAT(10,  12,  0x1C) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer GB 10 packed format
ITKBUFFER_VAL_FORMAT_BAYER_BG10PACKED   =   (ITKBUFFER_FORMAT(10,  12,  0x1D) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer BG 10 pakced format

ITKBUFFER_VAL_FORMAT_BAYER_GR12         =    (ITKBUFFER_FORMAT(12,  16,  0x1E) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)        # Indicates it's a color bayer GR 12 format
ITKBUFFER_VAL_FORMAT_BAYER_RG12         =    (ITKBUFFER_FORMAT(12,  16,  0x1F) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)        # Indicates it's a color bayer RG 12 format
ITKBUFFER_VAL_FORMAT_BAYER_GB12         =    (ITKBUFFER_FORMAT(12,  16,  0x20) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)        # Indicates it's a color bayer GB 12 format
ITKBUFFER_VAL_FORMAT_BAYER_BG12         =    (ITKBUFFER_FORMAT(12,  16,  0x21) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)        # Indicates it's a color bayer BG 12 format

ITKBUFFER_VAL_FORMAT_YUV422_8_YUYV      =    (ITKBUFFER_FORMAT(8,  16,  0x22) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's YUV 4:2:2 format(YUYV)
ITKBUFFER_VAL_FORMAT_YUV422_8_UYUV      =    (ITKBUFFER_FORMAT(8,  16,  0x23) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a YUV 4:2:2 format(UYUV)
ITKBUFFER_VAL_FORMAT_COORD3D_C16        =    (ITKBUFFER_FORMAT(16, 16,  0x24) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a coord3D_C16 format
ITKBUFFER_VAL_FORMAT_COORD3D_AC16       =    (ITKBUFFER_FORMAT(16, 32,  0x25) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a coord3D_AC16 format
ITKBUFFER_VAL_FORMAT_COORD3D_ACR16      =    (ITKBUFFER_FORMAT(16, 48,  0x26) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a coord3D_ACR16 format
ITKBUFFER_VAL_FORMAT_YUV422_8_UYVY      =    (ITKBUFFER_FORMAT(8,  16,  0x27) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's YUV 4:2:2 format(UYVY)

ITKBUFFER_VAL_FORMAT_MONO8PACKED        =    (ITKBUFFER_FORMAT(8, 8,    0x28) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color monochrome 8 packed format
ITKBUFFER_VAL_FORMAT_RGB888PACKED       =    (ITKBUFFER_FORMAT(8, 24,   0x29) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color RGB 8-8-8 packed format
ITKBUFFER_VAL_FORMAT_BGR888PACKED       =    (ITKBUFFER_FORMAT(8, 24,   0x2A) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color BGR 8-8-8 packed format
ITKBUFFER_VAL_FORMAT_PCD                =    (ITKBUFFER_FORMAT(32, 128, 0x2B) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color point cloud data format float(x)float(y)float(z)uint32(Luminance)
ITKBUFFER_VAL_FORMAT_BAYER_GR12PACKED   =    (ITKBUFFER_FORMAT(12, 12,  0x2C) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer GR 10 pakced format
ITKBUFFER_VAL_FORMAT_BAYER_RG12PACKED   =    (ITKBUFFER_FORMAT(12, 12,  0x2D) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer RG 10 pakced format
ITKBUFFER_VAL_FORMAT_BAYER_GB12PACKED   =    (ITKBUFFER_FORMAT(12, 12,  0x2E) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer GB 10 pakced format
ITKBUFFER_VAL_FORMAT_BAYER_BG12PACKED   =    (ITKBUFFER_FORMAT(12, 12,  0x2F) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED)         # Indicates it's a color bayer BG 10 pakced format

# U3V packed
ITKBUFFER_VAL_FORMAT_U3V_MONO10PACKED = (ITKBUFFER_FORMAT(10, 10, 0x30) | ITKBUFFER_FORMAT_MONO | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_U3V_BAYER_GR10PACKED = (ITKBUFFER_FORMAT(10, 10, 0x31) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_U3V_BAYER_RG10PACKED = (ITKBUFFER_FORMAT(10, 10, 0x32) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_U3V_BAYER_GB10PACKED = (ITKBUFFER_FORMAT(10, 10, 0x33) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_U3V_BAYER_BG10PACKED = (ITKBUFFER_FORMAT(10, 10, 0x34) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_U3V_MONO12PACKED = (ITKBUFFER_FORMAT(12, 12, 0x3D) | ITKBUFFER_FORMAT_MONO | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_U3V_BAYER_GR12PACKED = (ITKBUFFER_FORMAT(12, 12, 0x3E) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_U3V_BAYER_RG12PACKED = (ITKBUFFER_FORMAT(12, 12, 0x3F) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_U3V_BAYER_GB12PACKED = (ITKBUFFER_FORMAT(12, 12, 0x40) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_U3V_BAYER_BG12PACKED = (ITKBUFFER_FORMAT(12, 12, 0x41) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )

# YUV
ITKBUFFER_VAL_FORMAT_YUV422_8_YUYV = (ITKBUFFER_FORMAT(8, 16, 0x22) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_YUV422_8_UYUV = (ITKBUFFER_FORMAT(8, 16, 0x23) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )
ITKBUFFER_VAL_FORMAT_YUV422_8_UYVY = (ITKBUFFER_FORMAT(8, 16, 0x27) | ITKBUFFER_FORMAT_COLOR | ITKBUFFER_FORMAT_UNSIGNED )

# chunk模式
ITKBUFFER_VAL_IMAGE_PAYLOAD_TYPE = 0
ITKBUFFER_VAL_U3V_IMAGE_EXTENDED_CHUNK_PAYLOAD_TYPE = 1
ITKBUFFER_VAL_U3V_CHUNK_PAYLOAD_TYPE = 2
ITKBUFFER_VAL_GV_CHUNK_DATA_PAYLOAD_TYPE = 3

ITKBUFFER_VAL_CONVERT_OPTION_STRETCH = (1 << 30)
ITKBUFFER_VAL_CONVERT_OPTION_AUTO_FORMAT = (1 << 31)

# 3D
ITKBUFFER_VAL_FORMAT_COORD3D_CR32            = (ITKBUFFER_FORMAT(32,32,0x42)|ITKBUFFER_FORMAT_MONO|ITKBUFFER_FORMAT_UNSIGNED)
ITKBUFFER_VAL_FORMAT_CALIBRATED_COORD3D_AC32 = (ITKBUFFER_FORMAT(32,64,0x43)|ITKBUFFER_FORMAT_MONO|ITKBUFFER_FORMAT_UNSIGNED)
ITKBUFFER_VAL_FORMAT_CALIBRATED_COORD3D_C32  = (ITKBUFFER_FORMAT(32,32,0x44)|ITKBUFFER_FORMAT_MONO|ITKBUFFER_FORMAT_UNSIGNED)

ITKBUFFER_VAL_FORMAT_DATA_16_WITH_8U = (ITKBUFFER_FORMAT(24,24,0x49)|ITKBUFFER_FORMAT_MONO|ITKBUFFER_FORMAT_UNSIGNED)
ITKBUFFER_VAL_FORMAT_DATA_32_WITH_8U = (ITKBUFFER_FORMAT(40,40,0x50)|ITKBUFFER_FORMAT_MONO|ITKBUFFER_FORMAT_UNSIGNED)

# Macros to access bitfield information
def ITKBUFFER_FORMAT_INDEX(format):
    return ((format) & 0xFF)

def ITKBUFFER_FORMATL_DATA_BIT(format):
    return (((format) >> 8) & 0xFF)

def ITKBUFFER_FORMAT_PIXEL_DEPTH(format):
    return (((format) >> 16) & 0xFF)

def ITKBUFFER_FORMAT_IS_COLOR(format):
    if format & ITKBUFFER_FORMAT_COLOR:
        return 1
    return 0

def ITKBUFFER_FORMAT_IS_SIGNED(format):
    if format & ITKBUFFER_FORMAT_SIGNED:
        return 1
    return 0

# Buffer states 
ITKBUFFER_VAL_STATE_EMPTY				=	0x00000001
ITKBUFFER_VAL_STATE_FULL				=	0x00000002
ITKBUFFER_VAL_STATE_OVERFLOW			=	0x00000004
ITKBUFFER_VAL_STATE_UNCOMPLETED         =   0x00000008

# Buffer bayer convert alignment options 
ITKBUFFER_VAL_BAYER_BGGR				=	0x00000001
ITKBUFFER_VAL_BAYER_RGGB				=	0x00000002
ITKBUFFER_VAL_BAYER_GBRG				=	0x00000004
ITKBUFFER_VAL_BAYER_GRBG				=	0x00000008

#3D
ITKBUFFER_VAL_3D_SPLIT_INTO_BLOCK_AND_STRATIFIED =	0x00000001

# File format in buffer load or save
ITKBUFFER_VAL_BMP                       =   0
ITKBUFFER_VAL_TIFF                      =   1
ITKBUFFER_VAL_RAW                       =   2
ITKBUFFER_VAL_JPEG                      =   3
ITKBUFFER_VAL_PNG                       =   4
ITKBUFFER_VAL_PCD                       =   5

# Stream Parameters
ITKSTREAM_PRM_FIRST = 0
def ITKSTREAM_PRM(n, size):
    return ((((n) + ITKSTREAM_PRM_FIRST) << 16) | (size))

ITKSTREAM_PRM_STATUS					                = ITKSTREAM_PRM(0, 4)                                   # Stream status
ITKSTREAM_PRM_SUPPORT_EVENT_TYPE		                = ITKSTREAM_PRM(1, 4)                                   # Stream event type
ITKSTREAM_PRM_START_MODE				                = ITKSTREAM_PRM(2, 4)                                   # Stream start mode
ITKSTREAM_PRM_TRANSFER_MODE				                = ITKSTREAM_PRM(3, 4)                                   # Stream transfer mode
ITKSTREAM_PRM_AUTO_CLEAR				                = ITKSTREAM_PRM(4, 4)                                   # Stream auto clear enable
ITKSTREAM_PRM_TIME_OUT					                = ITKSTREAM_PRM(5, 4)                                   # Stream time out
ITKSTREAM_PRM_FRAME_RATE                                = ITKSTREAM_PRM(6, 4)                                   # Stream frame rate
ITKSTREAM_PRN_GV_PACKET_MAX_RESEND_COUNT                = ITKSTREAM_PRM(7, 4)                                   # GigeVision camera packet max resend times
ITKSTREAM_PRM_GV_PACKET_RESEND_TIMEOUT                  = ITKSTREAM_PRM(8, 4)                                   # GigeVision camera packet resend timeout
ITKSTREAM_PRM_GV_BLOCK_MAX_RESEND_PACKET_COUNT          = ITKSTREAM_PRM(9, 4)                                   # GigeVision camera block max resend packet count
ITKSTREAM_PRM_GV_BLOCK_MAX_WAIT_PACKET_COUNT            = ITKSTREAM_PRM(10, 4)                                  # GigeVision camera block max wait packet count
ITKSTREAM_PRM_GV_BLOCK_RESEND_WINODW_SIZE               = ITKSTREAM_PRM(11, 4)                                  # GigeVision camera block resend window size
ITKSTREAM_PRM_GV_PACKET_INTER_TIMEOUT                   = ITKSTREAM_PRM(12, 4)                                  # GigeVision camera packet inter timeout           
ITKSTREAM_PRM_GV_PACKET_POLLING_TIME                    = ITKSTREAM_PRM(13, 4)                                  # GigeVision camera packet polling time
ITKSTREAM_PRM_GV_KERNEL_BUFFER_COUNT                    = ITKSTREAM_PRM(14, 4)                                  # GigeVision kernel buffer count
ITKSTREAM_PRM_LINE_RATE                                 = ITKSTREAM_PRM(15, 4)                                  # Stream line rate
ITKSTREAM_PRM_CURRENT_BUFFER_HANDLE                     = ITKSTREAM_PRM(16, 4)                                  # Stream current buffer handle in end of frame callback   
ITKSTREAM_PRM_BURR_DECTION_IMAGE_SAVE_RATE              = ITKSTREAM_PRM(17, 4)                                  # burrDection Image saving rate   
ITKSTREAM_PRM_BURR_DECTION_IMAGE_SAVE_PATH              = ITKSTREAM_PRM(18, 4)                                  # burrDection Image saving path  
ITKSTREAM_PRM_BURR_DECTION_IMAGE_SAVE_BUFFER_COUNT      = ITKSTREAM_PRM(19, 4)                                  # burrDection Image saving BufferCount   
ITKSTREAM_PRM_BATCH_SIZE                                = ITKSTREAM_PRM(20, 4)                                  # Stream batch size  
ITKSTREAM_PRM_SELF_ADAPTION                             = ITKSTREAM_PRM(21, 4)                                  # Stream prm self adaption 1:enable, 0:disable   
ITKSTREAM_PRM_FRAME_FRAME_START_CORRESPOND_FRAME_END    = ITKSTREAM_PRM(22, 4)                                  # frameStart correspond to frameEnd 1:enable, 0:disable

# Stream status 
ITKSTREAM_VAL_STATUS_STOPPED					=		0x00000000                          # Stream stop
ITKSTREAM_VAL_STATUS_ACTIVE						=		0x00000001                          # Stream in progress
ITKSTREAM_VAL_STATUS_PENDING					=		0x00000002                          # Stream is pending	
ITKSTREAM_VAL_STATUS_ABORTED					=		0x00000003                          # Stream is aborted
ITKSTREAM_VAL_STATUS_TIMEOUT					=		0x00000004                          # Stream is time out

# Stream support event type
ITKSTREAM_VAL_EVENT_TYPE_START_OF_STREAM		=		0x00010000                          # Call the callback function at the start of stream
ITKSTREAM_VAL_EVENT_TYPE_END_OF_STREAM			=		0x00020000                          # Call the callback function at the end of stream
ITKSTREAM_VAL_EVENT_TYPE_START_OF_FRAME			=		0x00040000                          # Call the callback function at the end of frame
ITKSTREAM_VAL_EVENT_TYPE_END_OF_FRAME			=		0x00080000                          # Call the callback function at the end of frame
ITKSTREAM_VAL_EVENT_TYPE_TIME_OUT				=		0x00100000                          # Call the callback function at the time out of stream
ITKSTREAM_VAL_EVENT_TYPE_FRAME_LOST				=		0x00200000                          # Call the callback function at the frame lost
ITKSTREAM_VAL_EVENT_TYPE_IMAGE_DATA_ERROR       =       0x00400000                          # Call the callback function at image data error
ITKSTREAM_VAL_EVENT_TYPE_END_OF_LINE			=		0x01000000                          # Call the callback function at the end of line
ITKSTREAM_VAL_EVENT_TYPE_END_OF_BATCH           =       0x02000000                          # Call the callback function at the end of batch


ITKSTREAM_VAL_EVENT_TYPE_MASK					=		0xffff0000

# Stream start mode
ITKSTREAM_VAL_START_MODE_NON_BLOCK		   		=		0x00000000                          # Stream start in asynchronous mode
ITKSTREAM_VAL_START_MODE_BLOCK					=		0x00000001                          # Stream start in synchronous mode

# Stream transfer mode
ITKSTREAM_VAL_TRANSFER_MODE_ASYNCHRONOUS   		=		0x00000000                          # Stream transfer in asynchronous mode
ITKSTREAM_VAL_TRANSFER_MODE_SYNCHRONOUS			=		0x00000001                          # Stream transfer in synchronous mode
ITKSTREAM_VAL_TRANSFER_MODE_SYNCHRONOUS_WITH_PROTECT =  0x00000002                          # Stream transfer in synchronous with protect mode

# Stream auto clear 
ITKSTREAM_VAL_AUTO_CLEAR_DISABLE				=		0x00000000                          #  Disable stream auto clear
ITKSTREAM_VAL_AUTO_CLEAR_ENABLE					=		0x00000001                          #  Enable stream auto clear

# To start continuous stream
ITKSTREAM_CONTINUOUS							=       0xffffffff  						# Stream work in continuous mode

# View Parameters
ITKVIEW_PRM_FIRST = 0
def ITKVIEW_PRM(n, size):
    return ((((n) + ITKVIEW_PRM_FIRST) << 16) | (size))

ITKVIEW_PRM_FILP_X               = ITKVIEW_PRM(0, 4)                # Enable/disable X axis vertical flipping of the source image while the view is displayed
ITKVIEW_PRM_FILP_Y               = ITKVIEW_PRM(1, 4)                # Enable/disable Y axis horizontal flipping of the source image while the view is displayed
ITKVIEW_PRM_LSB                  = ITKVIEW_PRM(2, 4)                # Source image least significant bit
ITKVIEW_PRM_MSB	                 = ITKVIEW_PRM(3, 4)                # Source image most significant bit
ITKVIEW_PRM_BUFFER_ROI_HEIGHT    = ITKVIEW_PRM(4, 4)                # Height of the ROI of the buffer associated with the view
ITKVIEW_PRM_BUFFER_ROI_WIDTH     = ITKVIEW_PRM(5, 4)                # Width of the ROI of the buffer associated with the view
ITKVIEW_PRM_BUFFER_ROI_LEFT      = ITKVIEW_PRM(6, 4)                # Left of the ROI of the buffer associated with the view
ITKVIEW_PRM_BUFFER_ROI_TOP       = ITKVIEW_PRM(7, 4)                # Top of the ROI of the buffer associated with the view
ITKVIEW_PRM_ZOOM_METHOD          = ITKVIEW_PRM(8, 4)                # brief	Sets/Gets the zooming method		
ITKVIEW_PRM_ZOOM_MAX_RATIO       = ITKVIEW_PRM(9, 8)                # brief	Sets/Gets the zooming maximum ratio		
ITKVIEW_PRM_ZOOM_MIN_RATIO       = ITKVIEW_PRM(10, 8)               # brief	Sets/Gets the zooming minimum ratio
ITKVIEW_PRM_HWND                 = ITKVIEW_PRM(11, 8)               # brief	Window handle to be used as the destination view display surface
ITKVIEW_PRM_HWND_TITLE           = ITKVIEW_PRM(12, 128)             # Window title to be used as the destination view display surface
ITKVIEW_PRM_BAYER_MODE           = ITKVIEW_PRM(13, 4)               # brief	Show bayer image in windows
ITKVIEW_PRM_BUFFER_CURRENT_INDEX = ITKVIEW_PRM(14, 4)               # brief	Show Buffer Current Index

# View flip x
ITKVIEW_VAL_FLIP_X_DISABLE	=	0x00000000
ITKVIEW_VAL_FLIP_X_ENABLE	=	0x00000001

# View flip y
ITKVIEW_VAL_FLIP_Y_DISABLE	=	0x00000000
ITKVIEW_VAL_FLIP_Y_ENABLE	=	0x00000001

# View zoom method
ITKVIEW_VAL_ZOOM_NN			=	0x00000000                      # brief	Nearest neighbor zoom method	
ITKVIEW_VAL_ZOOM_LINEAR		=	0x00000001                      # brief	Linear zoom method
ITKVIEW_VAL_ZOOM_CUBIC		=	0x00000002                      # brief	Linear zoom method	
ITKVIEW_VAL_ZOOM_AREA		=	0x00000003                      # brief	Area zoom method	

# Bayer Mode
ITKVIEW_VAL_BAYER_MODE_NIL	=	0x00000000                      # brief	Bayer Mode NIL	
ITKVIEW_VAL_BAYER_MODE_BGGR	=	0x00000001                      # brief	Bayer Mode BGGR	
ITKVIEW_VAL_BAYER_MODE_RGGB	=	0x00000002                      # brief	Bayer Mode RGGB	
ITKVIEW_VAL_BAYER_MODE_GBRG	=	0x00000003                      # brief	Bayer Mode GBRG
ITKVIEW_VAL_BAYER_MODE_GRBG	=	0x00000004                      # brief	Bayer Mode GRBG	


# IKapCStat define
 # Status format location definitions
ITKSTATUS_MODULE_BIT_OFFSET	= 20
ITKSTATUS_LEVEL_BIT_OFFSET = 16
ITKSTATUS_STATUS_BIT_OFFSET	= 0

# Status format size definitions
ITKSTATUS_MODULE_BIT_MASK = 0x0f
ITKSTATUS_LEVEL_BIT_MASK = 0x0f
ITKSTATUS_STATUS_BIT_MASK = 0xffff

# module
def ITKSTATUS_MODULE(status):
    return (((status) >> ITKSTATUS_MODULE_BIT_OFFSET) & ITKSTATUS_MODULE_BIT_MASK)

ITKSTATUS_MODULE_DEVICE		= 0x01      # 1: Device module
ITKSTATUS_MODULE_BUFFER		= 0x02      # 2: Buffer module
ITKSTATUS_MODULE_LOG		= 0x03      # 3: Log module
ITKSTATUS_MODULE_MANAGER	= 0x04      # 4: API control module 
ITKSTATUS_MODULE_STREAM		= 0x05      # 5: Stream module
ITKSTATUS_MODULE_PARAM		= 0x06      # 6: Parameter module
ITKSTATUS_MODULE_SERIAL		= 0x07      # 7: Serial module
ITKSTATUS_MODULE_EVENTINFO	= 0x08      # 8: Event information module
ITKSTATUS_MODULE_FEATURE	= 0x09      # 9: Feature module
ITKSTATUS_MODULE_VIEW		= 0x0A      # 10: View module
ITKSTATUS_MODULE_BOARD      = 0x0B      # 11: Board module
ITKSTATUS_MODULE_FILE       = 0x0C      # 12: File module

# level
def ITKSTATUS_LEVEL(status):
    return (((status) >> ITKSTATUS_LEVEL_BIT_OFFSET) & ITKSTATUS_LEVEL_BIT_MASK)

ITKSTATUS_LEVEL_FAT	= 0      # fatal errors
ITKSTATUS_LEVEL_ERR	= 1      # general errors	
ITKSTATUS_LEVEL_WRN	= 2      # warnings			
ITKSTATUS_LEVEL_INF	= 3      # informations	

# id
def TKSTATUS_ID(status):
    return ((status) & ITKSTATUS_STATUS_BIT_MASK)

ITKSTATUS_OK									= 0x0000
ITKSTATUS_INVALID_HANDLE						= 0x0001	 
ITKSTATUS_INSUFFICIENT_RESOURCES				= 0x0002
ITKSTATUS_BUFFER_TOO_SMALL						= 0x0003
ITKSTATUS_MISSING_RESOURCE						= 0x0004
ITKSTATUS_UNINITIALIZE							= 0x0005
ITKSTATUS_DEVICE_ID_OUTOF_RANGE					= 0x0006
ITKSTATUS_SERAIL_PORT_NOT_AVAILABLE				= 0x0007
ITKSTATUS_XML_NOT_FOUND							= 0x0008
ITKSTATUS_DEVICE_NOT_ACCESSABLE					= 0x0009
ITKSTATUS_DEVICE_PERMISSION_DENY				= 0x000A
ITKSTATUS_REGISTRY_NOT_FOUND					= 0x000B
ITKSTATUS_XML_PARSE_ERROR						= 0x000C
ITKSTATUS_INVALID_ARG							= 0x000D
ITKSTATUS_INVALID_NAME							= 0x000E
ITKSTATUS_INCOMPATIBLE_FEATURE_TYPE				= 0x000F
ITKSTATUS_TIME_OUT								= 0x0010
ITKSTATUS_COMMAND_CRASH							= 0x0011
ITKSTATUS_COMMAND_PARAM_OUT_OF_RANGE			= 0x0012
ITKSTATUS_COMMAND_NOT_ALLOW						= 0x0013
ITKSTATUS_COMMAND_NOT_PRASE						= 0x0014
ITKSTATUS_COMMAND_PENDING						= 0x0015
ITKSTATUS_ARG_OUT_OF_RANGE						= 0x0016
ITKSTATUS_NOT_IMPLEMENT							= 0x0017
ITKSTATUS_NO_MEMORY								= 0x0018
ITKSTATUS_INCOMPATIBLE_ARG_TYPE					= 0x0019
ITKSTATUS_STREAM_IN_PROCESS						= 0x001A
ITKSTATUS_PRM_READ_ONLY							= 0x001B
ITKSTATUS_STREAM_IS_OPENED						= 0x001C
ITKSTATUS_SYSTEM_ERROR                          = 0x001D
ITKSTATUS_INVALID_ADDRESS                       = 0x001E
ITKSTATUS_BAD_ALIGNMENT                         = 0x001F
ITKSTATUS_DEVICE_BUSY                           = 0x0020
ITKSTATUS_DEVICE_IS_REMOVED                     = 0x0021
ITKSTATUS_DEVICE_NOT_FOUND                      = 0x0022
ITKSTATUS_BOARD_IS_OPENED                       = 0x0023
ITKSTATUS_BOARD_NO_OPENED                       = 0x0024
ITKSTATUS_PRM_WRITE_ONLY                        = 0x0025
ITKSTATUS_BOARD_CONNECTION_FAIL                 = 0x0026
ITKSTATUS_RUNTIME_ERROR                         = 0x0027
ITKSTATUS_IO_ERROR                              = 0x0028
ITKSTATUS_BUFFER_OVERFLOW                       = 0x0029
ITKSTATUS_COMMUNICATION_ERROR                   = 0x0030
ITKSTATUS_CXP_CONTROL_CRC_ERROR                 = 0x0031
ITKSTATUS_ACK_ID_NOT_COMPATIABLE                = 0x0032
ITKSTATUS_DEV_INVALID_HEADER                    = 0x0033
ITKSTATUS_DEV_DSI_ENDPOINT_HALTED               = 0x0034
ITKSTATUS_DEV_DEI_ENDPOINT_HALTED               = 0x0035
ITKSTATUS_DEV_DATA_DISCARDED                    = 0x0036
ITKSTATUS_DEV_DATA_OVERRUN                      = 0x0037
ITKSTATUS_STREAM_ABORTED                        = 0x0038
ITKSTATUS_DRIVER_NOT_MATCH                      = 0x0039
ITKSTATUS_DEVICE_WRONG_USB_PORT                 = 0x0040
ITKSTATUS_DEVICE_IS_FAULTY                      = 0x0041

# level first so that it be visible instantly
def ITKSTATUS_BUILD( level, id, module):
    return ((id) | (((level) & ITKSTATUS_LEVEL_BIT_MASK)<<ITKSTATUS_LEVEL_BIT_OFFSET) | (((module) & ITKSTATUS_MODULE_BIT_MASK)<<ITKSTATUS_MODULE_BIT_OFFSET))

# Macros for adding single fields to status
def ITKSTATUS_ADD_ID( status, id):
    return ((status) | ((id) & ITKSTATUS_STATUS_BIT_MASK))

def ITKSTATUS_ADD_LEVEL( status, level):
    return ((status) | (((level) & ITKSTATUS_LEVEL_BIT_MASK)<<ITKSTATUS_LEVEL_BIT_OFFSET))
    
def ITKSTATUS_ADD_MODULE( status, module):
    return ((status) | (((module) & ITKSTATUS_MODULE_BIT_MASK)<<ITKSTATUS_MODULE_BIT_OFFSET))

# Macros for adding module to status
def ITKSTATUS_DEVICE(status):
    return ITKSTATUS_ADD_MODULE(status, ITKSTATUS_MODULE_DEVICE)

def ITKSTATUS_BUFFER(status):
    return ITKSTATUS_ADD_MODULE(status, ITKSTATUS_MODULE_BUFFER)

def ITKSTATUS_LOG(status):
    return ITKSTATUS_ADD_MODULE(status, ITKSTATUS_MODULE_LOG)

def ITKSTATUS_MANAGER(status):
    return ITKSTATUS_ADD_MODULE(status, ITKSTATUS_MODULE_MANAGER)

def ITKSTATUS_STREAM(status):
    return ITKSTATUS_ADD_MODULE(status, ITKSTATUS_MODULE_STREAM)

def ITKSTATUS_PARAM(status):
    return ITKSTATUS_ADD_MODULE(status, ITKSTATUS_MODULE_PARAM)

def ITKSTATUS_SERIAL(status):
    return ITKSTATUS_ADD_MODULE(status, ITKSTATUS_MODULE_SERIAL)

def ITKSTATUS_EVENTINFO(status):
    return ITKSTATUS_ADD_MODULE(status, ITKSTATUS_MODULE_EVENTINFO)

def ITKSTATUS_FEATURE(status):
    return ITKSTATUS_ADD_MODULE(status, ITKSTATUS_MODULE_FEATURE)
