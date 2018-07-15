import logging
import numpy as np


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

    packet_type = packet[0:4].decode('ascii')

    if packet_type == ":REQ":
        decoded_packet = decode_request_packet(packet)
    elif packet_type == ":VAL":
        decoded_packet = decode_value_description_packet(packet)
    elif packet_type == ":END":
        # Do nothing exciting here - we've checksummed the packet, and there's no information in the END packet.
        # End transaction?
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
    requested_variable_type = packet[5:7].decode('ascii')

    if requested_variable_type == "MT":
        requested_variable_id = packet[11:16].decode('ascii')
    elif requested_variable_type == "VM":
        requested_variable_id = chr(packet[11])
    elif requested_variable_type == "PC":
        pass
    elif requested_variable_type == "LT":
        requested_variable_id = packet[11:17].decode('ascii')

    return dict(**locals())


def decode_value_description_packet(packet):
    """

    :param packet:
    :return:
    """

    requested_variable_type = packet[5:7].decode('ascii')

    if requested_variable_type == "MT":
        requested_variable_id = packet[11:16].decode('ascii')
        row = packet[8]
        col = packet[10]
    elif requested_variable_type == "VM":
        requested_variable_id = chr(packet[11])
        variable_used = bool(packet[8])
        complex_or_real = ("Complex" if packet[19:28] == b"VariableC" else "Real")
    elif requested_variable_type == "PC":
        pass
    elif requested_variable_type == "LT":
        requested_variable_id = packet[11:17].decode('ascii')

    else:
        pass

    return dict(**locals())


def decode_value_packet(packet):
    """
    Decode a value packet. This will return a complex number if sent/stored, and its array position (if applicable.)
    :param packet:
    :return:
    """

    # Exponent is BCD!

    row, col = (packet[2], packet[4])
    real_int_part = packet[5]
    real_frac_part = convertBcdDigitsToInt(packet[6:12])

    has_imaginary_part = bool((packet[13] >> 7) & 0x1)

    real_part_sign = (packet[13] >> 6) & 0x1
    real_exponent_sign = (packet[13] >> 0) & 0x1
    real_exponent_mag = int(convertBcdDigitsToInt(bytes([packet[14]])))
    if real_exponent_sign == 0x0:
        real_exponent_mag = -(100-real_exponent_mag)

    real_part = float("{}.{}".format(real_int_part, real_frac_part)) * (-1 if real_part_sign == 0x01 else 1) * \
        10**real_exponent_mag

    if has_imaginary_part is True:
        imag_int_part = packet[15]
        imag_frac_part = convertBcdDigitsToInt(packet[16:22])

        imag_part_sign = (packet[23] >> 6) & 0x1

        imag_exponent_sign = (packet[23] >> 0) & 0x1
        imag_exponent_mag = int(convertBcdDigitsToInt(bytes([packet[24]])))

        if imag_exponent_sign == 0x0:
            imag_exponent_mag = -(100 - imag_exponent_mag)

        imag_part = float("{}.{}".format(imag_int_part, imag_frac_part)) * (-1 if imag_part_sign == 0x01 else 1) * \
            10**imag_exponent_mag
    else:
        imag_part = 0

    return {'value': np.complex(real_part, imag_part), 'row': row, 'col': col}


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
