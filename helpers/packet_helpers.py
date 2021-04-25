import logging
import numpy as np
from helpers import cfx_codecs
from construct import Container
import binascii
from decimal import *


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
        decoded_packet = decode_variable_description_packet(packet)
    elif packet_type == ":END":
        pass
    elif packet_type == ":IMG":
        logging.warning("Data type is Picture")
    elif packet_type == ":TXT":
        logging.warning("Data type is TXT (program)")
    elif packet_type == ":MEM":
        logging.warning("Data type is program backup")
    elif packet_type == ":FNC":
        logging.warning("Data type is Function (YData etc.)")
    elif packet_type == ":DD@":
        logging.warning("Looks like a screenshot!")
        decoded_packet = decode_screenshot_request_packet(packet)
    else:
        logging.warning("Not entirely sure what this is (packet type {}), treating as a value packet".format(packet_type))
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


def decode_variable_description_packet(packet):
    """

    :param packet:
    :return:
    """
    decoded_packet = cfx_codecs.variable_description_packet.parse(packet)
    return decoded_packet


def decode_screenshot_request_packet(packet):
    decoded_packet = cfx_codecs.screenshot_request_packet.parse(packet)
    return decoded_packet


def decode_screenshot_data_packet(packet):
    decoded_packet = cfx_codecs.screenshot_data_packet.parse(packet)
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


def encode_value_packet(data):
    processed_real_part = process_value(data.real)
    processed_imag_part = process_value(data.imag)

    value_packet_response = Container(row=b'\x00', col=b'\x00',
                                      real_int=binascii.unhexlify('0'+str(processed_real_part['int_part'])),
                                      real_frac=convertIntToBcdDigits(processed_real_part['frac_part']),
                                      real_signinfo=Container(
                                          isComplex=(False if data.imag is 0 else True),
                                          isNegative=processed_real_part['isNegative'],
                                          expSignIsPositive=processed_real_part['expIsPositive']
                                      ), real_exponent=binascii.unhexlify('0'+str(processed_real_part['exp_part'])),
                                      imag_int=binascii.unhexlify('0'+str(processed_imag_part['int_part'])),
                                      imag_frac=convertIntToBcdDigits(processed_imag_part['frac_part']),
                                      imag_signinfo=Container(
                                          isComplex=(False if data.imag is 0 else True),
                                          isNegative=processed_imag_part['isNegative'],
                                          expSignIsPositive=processed_imag_part['expIsPositive']
                                      ), imag_exponent=binascii.unhexlify('0'+str(processed_imag_part['exp_part'])))

    return value_packet_response


def process_value(raw_value):
    value = {}
    value['raw'] = '{0:.14E}'.format(Decimal(str(raw_value)))

    value['int_part'], value['frac_part'] = value['raw'].split('.')
    value['frac_part'], value['exp_part'] = value['frac_part'].split('E')

    value['int_part'] = int(value['int_part'])
    value['frac_part'] = int(value['frac_part'])
    value['exp_part'] = int(value['exp_part'])

    value['isNegative'] = value['int_part'] < 0
    value['int_part'] = abs(value['int_part'])

    value['expIsPositive'] = value['exp_part'] >= 0
    value['exp_part'] = abs(value['exp_part'])

    print(value)

    return value


def checksum_valid(packet):
    """
    Return true or false depending on if the packet's checksum is verified
    :param packet: The packet in binary string form
    :return: boolean (True or False)
    """

    calculated_checksum = (0x01 + (~(sum(packet[:-1]) - 0x3A))) & 0xFF
    logging.info("Checksum was {}, expecting {}".format(hex(calculated_checksum), hex(packet[-1])))
    logging.info(packet)
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


def convertIntToBcdDigits(data, pad_to_length=7):
    data = str(data)
    if data == '0':
        data = '00000000000000'

    if len(data) % 2 != 0:
        data += '0'

    # Pad this out to pad_to_length bytes
    padded_data = data.ljust(pad_to_length*2, '0')
    return binascii.unhexlify(padded_data)
