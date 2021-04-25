from construct import \
    Struct, Const, Padding, Int8ub, Bytes, BitStruct, Flag, BitsInteger, Enum, Byte, Int32ub, Int16ub

bmp_header = Struct(
    Const(b"BM"),
    "filesize" / Int32ub,
    "reserved" / Int32ub,
    "dataoffset" / Int32ub
)

bmp_info_header = Struct(
    "size" / Const(40, Int32ub),
    "width" / Int32ub,
    "height" / Int32ub,
    "planes" / Const(1, Int32ub),
    "bitsperpixel" / Int16ub,
    "compression" / Int32ub,
    "imagesize" / Int32ub,
    "xpixelsperm" / Int32ub,
    "ypixelsperm" / Int32ub,
    "colorsused" / Int32ub,
    "importantcolors" / Int32ub
)

bmp_color_table = Struct(
    "red" / Byte,
    "green" / Byte,
    "blue" / Byte,
    "reserved" / Const(Byte, 0)
)

pixel_data = Struct(

)