from transitions import Machine
from collections import deque
from threading import Thread
import time
from helpers import packet_helpers, statemachine_helpers, cfx_codecs
import serial
import logging
import coloredlogs
from construct import Container


class CFX(object):

    def __init__(self, serial_port):
        self._initialiseLogging()

        self.rx_message_queue = deque()
        self.tx_message_queue = deque()

        self.serial_port = serial_port
        self.serial_connection = None

        self.data_store = {
            'VARIABLE': {},
            'PICTURE': {},
            'MATRIX': {},
            'LIST': {}
        }

        states = []
        transitions = []

        initial_transitions = [
            {'trigger': 'initialised', 'source': 'init', 'dest': 'wait_for_wakeup'},
            {'trigger': 'input_received', 'conditions': statemachine_helpers.packet_is_type_wakeup,
             'source': 'wait_for_wakeup', 'dest': 'wait_for_request_packet'},
            {'trigger': 'input_received', 'conditions': statemachine_helpers.packet_is_type_receive_request,
             'source': 'wait_for_request_packet', 'dest': 'start_transaction_rx'},
            {'trigger': 'input_received', 'conditions': statemachine_helpers.packet_is_type_send_request,
             'source': 'wait_for_request_packet', 'dest': 'start_transaction_tx'}
            ]

        receive_transitions = [
            {'trigger': 'input_received', 'conditions': statemachine_helpers.packet_is_type_ack,
             'source': 'start_transaction_rx', 'dest': 'send_variable_description_packet'},
            {'trigger': 'input_received', 'conditions':  statemachine_helpers.packet_is_type_ack,
             'source': 'send_variable_description_packet', 'dest': 'send_value_packet'},
            {'trigger': 'input_received', 'conditions':  [statemachine_helpers.packet_is_type_ack,
                                                          self.no_values_left_to_send],
             'source': 'send_value_packet', 'dest': 'send_end_packet'},
            {'trigger': 'input_received', 'conditions':  statemachine_helpers.packet_is_type_wakeup,
             'source': 'send_end_packet', 'dest': 'wait_for_request_packet'}
        ]

        send_transitions = [
            {'trigger': 'input_received', 'conditions': [statemachine_helpers.packet_is_type_value,
                                                         self.values_left_to_receive],
             'source': 'start_transaction_tx', 'dest': 'receive_value_packet'},

            {'trigger': 'input_received', 'conditions': [statemachine_helpers.packet_is_type_value,
                                                         self.values_left_to_receive],
             'source': 'receive_value_packet', 'dest': 'receive_value_packet'},

            {'trigger': 'input_received', 'conditions': statemachine_helpers.packet_is_type_end_packet,
             'source': 'receive_value_packet', 'dest': 'wait_for_wakeup'}
        ]

        transitions.extend(initial_transitions)
        transitions.extend(receive_transitions)
        transitions.extend(send_transitions)

        initial_states = ['init', 'wait_for_wakeup', 'wait_for_request_packet']
        rx_transaction_states = ['start_transaction_rx', 'send_variable_description_packet',
                                 'send_value_packet', 'send_end_packet']
        tx_transaction_states = ['start_transaction_tx', 'receive_variable_description_packet',
                                 'receive_value_packet', 'receive_end_packet']

        states.extend(initial_states)
        states.extend(rx_transaction_states)
        states.extend(tx_transaction_states)

        self.fsm = Machine(states=states, transitions=transitions, initial='init')
        self.fsm.initialised()
        self.create_serial_connection()

        self.cfx_receiver = Thread(target=self.receive_data_from_port)
        self.cfx_receiver.start()

        self.process_requests_from_cfx()

    def _initialiseLogging(self):
        logging.basicConfig(format='%(asctime)s.%(msecs)03d %(name)s %(levelname)s %(message)s', datefmt='%F %H:%M:%S',
                            level=logging.INFO)
        self.logger = logging.getLogger("cfx_interface")
        coloredlogs.install(level='DEBUG', logger=self.logger)
        self.logger.info("Initialising the CFX interface object.")

    def receive_data_from_port(self):
        while True:
            try:
                packet_data = packet_helpers.wait_for_packet(ser=self.serial_connection)
                processed_packet = packet_helpers.decode_packet(packet=packet_data)
                self.rx_message_queue.append(processed_packet)
                time.sleep(0.01)

            except serial.SerialTimeoutException:
                time.sleep(0.01)

    def process_requests_from_cfx(self):
        while True:
            # if new messages are available in the buffer, trigger a transition attempt
            if len(self.rx_message_queue) == 0:
                time.sleep(0.01)
                continue

            packet = self.rx_message_queue.popleft()
            self.fsm.input_received(packet=packet)

            self.logger.info("Packet of type {} received".format(packet["packet_type"]))
            self.logger.info("State is {}".format(self.fsm.state))
            self.logger.info("Contents of memory store: {}".format(self.data_store))

            try:
                self.logger.info("Values left to receive: {}".format(self.values_left_to_receive(packet)))
                self.logger.info("Number: {}".format(self.transaction['values_left_to_receive']))
            except AttributeError:
                self.logger.info("No transaction currently in progress")
            except KeyError:
                pass

            # Tree of things to do when the appropriate state is reached
            if self.fsm.state == 'wait_for_request_packet':
                self._wait_for_request_packet()
            elif self.fsm.state == 'start_transaction_tx':
                self._start_transaction_tx(packet=packet)
            elif self.fsm.state == 'start_transaction_rx':
                self._start_transaction_rx(packet=packet)
            elif self.fsm.state == "send_variable_description_packet":
                self._send_variable_description_packet(packet=packet)
            elif self.fsm.state == "receive_variable_description_packet":
                self._receive_variable_description_packet(packet=packet)
            elif self.fsm.state == "send_value_packet":
                self._send_value_packet(packet=packet)
            elif self.fsm.state == "receive_value_packet":
                self._receive_value_packet(packet=packet)
            elif self.fsm.state == "send_end_packet":
                self._send_end_packet(packet=packet)
            elif self.fsm.state == "receive_end_packet":
                self._receive_end_packet(packet=packet)

            else:
                self.logger.info("State is {}".format(self.fsm.state))
            time.sleep(0.01)

    def values_left_to_send(self, packet=None):
        return self.transaction["values_left_to_send"] > 0

    def no_values_left_to_send(self, packet=None):
        return self.transaction["values_left_to_send"] == 0

    def values_left_to_receive(self, packet=None):
        return self.transaction["values_left_to_receive"] > 0

    def no_values_left_to_receive(self, packet=None):
        return self.transaction["values_left_to_receive"] == 0

    def create_serial_connection(self):
        self.logger.info('Setting up a serial connection on {}'.format(self.serial_port))
        ser = serial.Serial(port=self.serial_port, baudrate=9600, parity=serial.PARITY_NONE,
                            bytesize=8, stopbits=serial.STOPBITS_TWO, timeout=3, inter_byte_timeout=0.05)

        # Set DTR, unset RTS
        ser.dtr = True
        ser.rts = False
        self.serial_connection = ser

    def _wait_for_request_packet(self):
        self.logger.info("Wakeup received! Send acknowledgement")
        self.serial_connection.write(b'\x13')

    def _start_transaction_tx(self, packet):
        self.logger.debug("Start transaction to receive stuff from the calculator")
        self.transaction = packet

        if self.transaction["requested_variable_type"] == cfx_codecs.variableType.VARIABLE:
            self.transaction["values_left_to_receive"] = 1
            self.transaction["transaction_data"] = None

        elif self.transaction["requested_variable_type"] == cfx_codecs.variableType.MATRIX:
            self.transaction["values_left_to_receive"] = ord(self.transaction['rowsize']) * ord(
                self.transaction['colsize'])
            self.transaction["real_or_complex"] = cfx_codecs.realOrComplex.REAL
            self.transaction["transaction_data"] = \
                [[0 for x in range(ord(self.transaction['colsize']))] for y in range(ord(self.transaction['rowsize']))]

        else:
            self.logger.warning("Unsupported variable type requested! - {}".format(
                self.transaction["requested_variable_type"]
            ))
            return

        self.logger.info("Transaction data: {}".format(self.transaction))
        self.serial_connection.write(b'\x06')

    def _start_transaction_rx(self, packet):
        self.logger.info("Start transaction to send stuff to calculator")
        self.transaction = packet
        print(packet)

        self.serial_connection.write(b'\x06')

    def _send_variable_description_packet(self, packet):
        self.logger.info("Send variable description packet")

        # See if we have the requested data already
        variable_type = str(self.transaction['requested_variable_type'])
        variable_name = self.transaction['variable_name'].strip(b'\xff').decode('ascii')

        try:
            self.transaction["retrieved_value"] = self.data_store[variable_type][variable_name]
        except KeyError:
            self.logger.warning("{} {} was not found, send END packet?".format(variable_type, variable_name))
            # todo: fix!
            self.transaction["retrieved_value"] = {}
            self.transaction["retrieved_value"]["real_or_complex"] = "REAL"

        self.logger.info("Send variable description packet")
        request_response = Container(requested_variable_type=variable_type,
                                     rowsize=(b'\x01' if variable_type == cfx_codecs.variableType.VARIABLE else
                                              bytes(chr(self.transaction["retrieved_value"].shape[0]), "ascii")),
                                     colsize=(b'\x01' if variable_type == cfx_codecs.variableType.VARIABLE else
                                              bytes(chr(self.transaction["retrieved_value"].shape[1]), "ascii")),
                                     variable_name=b"A\xFF\xFF\xFF\xFF\xFF\xFF\xFF",
                                     real_or_complex=str(self.transaction["retrieved_value"]["real_or_complex"]))

        packet = packet_helpers.calculate_checksum(
                    cfx_codecs.variable_description_packet.build(request_response)
                )

        self.serial_connection.write(packet)

    def _receive_variable_description_packet(self, packet):
        self.logger.info("Receive variable description packet")

    def _send_value_packet(self, packet):
        self.logger.info("Send value packet")

    def _receive_value_packet(self, packet):
        self.logger.info("Receive value packet")

        if self.transaction["requested_variable_type"] == cfx_codecs.variableType.MATRIX:
            self.transaction["transaction_data"][packet['row']-1][packet['col']-1] = packet["value"]
        else:
            self.transaction["transaction_data"] = packet["value"]

        # todo: should this be done after end_packet has been received?

        variable_name = self.transaction['variable_name'].strip(b'\xff').decode('ascii')
        variable_type = str(self.transaction['requested_variable_type'])
        self.data_store[variable_type][variable_name] = {
            "value": self.transaction["transaction_data"],
            "real_or_complex": self.transaction["real_or_complex"]
        }
        self.logger.info("Data stored: type {}, name {}".format(variable_type, variable_name))

        self.transaction["values_left_to_receive"] -= 1
        self.serial_connection.write(b'\x06')

    def _send_end_packet(self):
        self.logger.info("Send end packet")
        self.serial_connection.write(
            packet_helpers.calculate_checksum(
                cfx_codecs.end_packet.build(
                    Container()
                )
            )
        )

    def _receive_end_packet(self):
        self.logger.info("Receive end packet")


testClass_inst = CFX(serial_port="COM1")
