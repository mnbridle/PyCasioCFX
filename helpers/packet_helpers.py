import logging
import numpy as np
from helpers import cfx_codecs


def decode_packet(packet):
    """
    Decodes a packet.

    :param packet: The packet in binary string form
    :return: A dict containing all of the packet fields
    """

    decoded_packet = {}

    if not checksum_valid(packet):
        logging.error("Checksum was incorrect!")
        return {}

    packet = packet[:-1]

    packet_type = packet[0:4].decode('ascii')

    if packet_type == ":REQ":
        decoded_packet = decode_request_packet(packet)
    elif packet_type == ":VAL":
        decoded_packet = decode_value_description_packet(packet)
    elif packet_type == ":END":
        pass
    else:
        decoded_packet = decode_value_packet(packet)

    decoded_packet['packet_type'] = packet_type
    return decoded_packet


def decode_request_packet(packet):
    """

    :param packet:
    :return:
    """
    decoded_packet = cfx_codecs.request_packet.parse(packet)
    return decoded_packet


def decode_value_description_packet(packet):
    """

    :param packet:
    :return:
    """

    decoded_packet = cfx_codecs.variable_description_packet.parse(packet)
    return decoded_packet


def decode_value_packet(packet):
    """
    Decode a value packet. This will return a complex number if sent/stored, and its array position (if applicable.)
    :param packet:
    :return:
    """

    if len(packet) == 16:
        decoded_packet = cfx_codecs.real_value_packet.parse(packet)
    else:
        decoded_packet = cfx_codecs.complex_value_packet.parse(packet)

    real_int_part = convertBcdDigitsToInt(decoded_packet["real_int"])
    real_frac_part = convertBcdDigitsToInt(decoded_packet["real_frac"])
    real_exponent_mag = int(convertBcdDigitsToInt(bytes(decoded_packet["real_exponent"])))

    if decoded_packet["real_signinfo"]["expSignIsPositive"] is False:
        real_exponent_mag = -(100-real_exponent_mag)

    # Exponent is BCD!

    real_part = float("{}.{}".format(
        real_int_part,
        real_frac_part)) * (-1 if decoded_packet["real_signinfo"]["isNegative"] is True else 1) * \
        10**real_exponent_mag

    if decoded_packet["real_signinfo"]["isComplex"] is True:

        imag_int_part = convertBcdDigitsToInt(decoded_packet["imag_int"])
        imag_frac_part = convertBcdDigitsToInt(decoded_packet["imag_frac"])
        imag_exponent_mag = int(convertBcdDigitsToInt(bytes(decoded_packet["imag_exponent"])))

        if decoded_packet["imag_signinfo"]["expSignIsPositive"] is False:
            imag_exponent_mag = -(100 - imag_exponent_mag)

        imag_part = float("{}.{}".format(
            imag_int_part,
            imag_frac_part)) * (-1 if decoded_packet["imag_signinfo"]["isNegative"] is True else 1) * \
            10 ** imag_exponent_mag

    else:
        imag_part = 0

    return {'value': np.complex(real_part, imag_part), 'row': ord(decoded_packet["row"]),
            'col': ord(decoded_packet["col"])}


def checksum_valid(packet):
    """
    Return true or false depending on if the packet's checksum is verified
    :param packet: The packet in binary string form
    :return: boolean (True or False)
    """

    calculated_checksum = (0x01 + (~(sum(packet[:-1]) - 0x3A))) & 0xFF
    return calculated_checksum == packet[-1]


def calculate_checksum(packet):
    """
    Return packet with checksum appended to the end.
    :param packet:
    :return:
    """

    calculated_checksum = bytes([(0x01 + (~(sum(packet[0:]) - 0x3A))) & 0xFF])
    packet += calculated_checksum

    return packet


def convertBcdDigitsToInt(bcd_digits):
    result = []
    for digit in bcd_digits:
        result.extend([val for val in (digit >> 4, digit & 0xF)])

    return ''.join([str(x) for x in result])
