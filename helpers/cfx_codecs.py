from construct import \
    Struct, Const, Padding, Int8ub, Bytes, BitStruct, Flag, BitsInteger

signinfobyte = BitStruct(
    "isImaginary" / Flag,
    "isNegative" / Flag,
    Padding(5),
    "signIsPositive" / Flag
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
    "real_exponent" / Bytes(1),
    "checksum" / Bytes(1)
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
    "imag_exponent" / Bytes(1),
    "checksum" / Bytes(1)
)
