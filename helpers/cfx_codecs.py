from construct import \
    Struct, Const, Padding, Int8ub, Bytes, BitStruct, Flag, BitsInteger, Enum, Byte

realOrComplex = Enum(Bytes(9), REAL=b'VariableR', COMPLEX=b'VariableC')
realOrComplex = Enum(Bytes(1), REAL=b'R', COMPLEX=b'C')
variableType = Enum(Bytes(2), VARIABLE=b'VM', LIST=b'LT', MATRIX=b'MT', IMAGE=b'PC', SCREENSHOT=b'DW')

# Checksum byte needs to be removed before the packet is parsed!

signinfobyte = BitStruct(
    "isComplex" / Flag,
    "isNegative" / Flag,
    Padding(1),
    "isNegative" / Flag,
    Padding(3),
    "expSignIsPositive" / Flag
)

real_value_packet = Struct(
    Const(b":"),
    Padding(1),
    "row" / Bytes(1),
    Padding(1),
    "col" / Bytes(1),
    "real_int" / Bytes(1),
    "real_frac" / Bytes(7),
    # signinfo should be a bitstruct
    "real_signinfo" / signinfobyte,
    "real_exponent" / Bytes(1)
)

complex_value_packet = Struct(
    Const(b":"),
    Padding(1),
    "row" / Bytes(1),
    Padding(1),
    "col" / Bytes(1),
    "real_int" / Bytes(1),
    "real_frac" / Bytes(7),
    "real_signinfo" / signinfobyte,
    "real_exponent" / Bytes(1),
    "imag_int" / Bytes(1),
    "imag_frac" / Bytes(7),
    "imag_signinfo" / signinfobyte,
    "imag_exponent" / Bytes(1)
)

variable_description_packet = Struct(
    Const(b':'),
    "tag" / Const(b'VAL'),
    Padding(1),
    "requested_variable_type" / variableType,
    Padding(1),
    # Doubles as rowsize for matrix data
    "rowsize" / Bytes(1),
    Padding(1),
    # Doubles as colsize for matrix data
    "colsize" / Bytes(1),
    "variable_name" / Bytes(8),
    Padding(8),
    "real_or_complex" / realOrComplex,
    Padding(1, pattern=b'\x0A'),
    Padding(20, pattern=b'\xff')
)

request_packet = Struct(
    Const(b':'),
    "tag" / Const(b'REQ'),
    Padding(1),
    "requested_variable_type" / variableType,
    Padding(4, pattern=b'\xff'),
    "variable_name" / Bytes(8),
    Padding(30, pattern=b'\xff')
)

end_packet = Struct(
    Const(b':'),
    "tag" / Const(b'END'),
    Padding(45, pattern=b'\xff')
)

screenshot_request_packet = Struct(
    Const(b':'),
    "tag" / Const(b'DD@'),
    Padding(2),
    "requested_variable_type" / variableType,
    Padding(1),
    "data" / Bytes(30)
)

screenshot_data_packet = Struct(
    Const(b':'),
    "data" / Bytes(1024)
)