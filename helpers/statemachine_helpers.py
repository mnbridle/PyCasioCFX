def packet_is_type_receive_request(packet):
    print(packet["packet_type"])
    return packet["packet_type"] == "receive_request"


def packet_is_type_send_request(packet):
    return packet["packet_type"] == "send_request"


def packet_is_type_end_packet(packet):
    return packet["packet_type"] == "end_packet"


def packet_is_type_value(packet):
    return packet["packet_type"] == "value"


def packet_is_type_wakeup(packet):
    return packet["packet_type"] == "wakeup"


def packet_is_type_ack(packet):
    return packet["packet_type"] == "ack"


def packet_is_type_wakeup_response(packet):
    return packet["packet_type"] == "wakeup_ack"


def packet_is_type_unknown(packet):
    return packet["packet_type"] == "unknown"
