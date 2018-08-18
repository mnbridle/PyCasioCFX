from transitions import Machine
from collections import deque
import threading
import time
from helpers import packet_helpers, statemachine_helpers, cfx_codecs
import serial
import logging
import numpy as np
from construct import Container


class CFX(threading.Thread):

    def __init__(self, serial_port):
        super(CFX, self).__init__()

        self._rx_message_queue = deque()
        self._tx_message_queue = deque()

        self._serial_port = serial_port
        self._serial_connection = None

        self._data_store_lock = threading.Lock()
        self._data_store = {
            'VARIABLE': {},
            'PICTURE': {},
            'MATRIX': {},
            'LIST': {}
        }

        self._stop_event = threading.Event()

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
                                                          self._no_values_left_to_send],
             'source': 'send_value_packet', 'dest': 'send_end_packet'},
            {'trigger': 'input_received', 'conditions':  statemachine_helpers.packet_is_type_wakeup,
             'source': 'send_end_packet', 'dest': 'wait_for_request_packet'}
        ]

        send_transitions = [
            {'trigger': 'input_received', 'conditions': [statemachine_helpers.packet_is_type_value,
                                                         self._values_left_to_receive],
             'source': 'start_transaction_tx', 'dest': 'receive_value_packet'},

            {'trigger': 'input_received', 'conditions': [statemachine_helpers.packet_is_type_value,
                                                         self._values_left_to_receive],
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

        self._initialiseLogging()
        self._fsm = Machine(states=states, transitions=transitions, initial='init')
        self._fsm.initialised()
        self._create_serial_connection()

        self.cfx_receiver = threading.Thread(target=self._receive_data_from_port)
        self.cfx_receiver.start()

        self.packet_processor = threading.Thread(target=self._process_requests_from_cfx)
        self.packet_processor.start()

    def stop(self):
        self.logger.info("Stopping the CFX interface object...")
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def _initialiseLogging(self):
        logging.basicConfig(format='%(asctime)s.%(msecs)03d %(name)s %(levelname)s %(message)s', datefmt='%F %H:%M:%S',
                            level=logging.INFO)
        self.logger = logging.getLogger("cfx_interface")
        self.logger.info("Initialising the CFX interface object.")

    def _receive_data_from_port(self):
        while not self._stop_event.is_set() or self._values_left_to_send() or self._values_left_to_receive():
            try:
                packet_data = packet_helpers.wait_for_packet(ser=self._serial_connection)
                processed_packet = packet_helpers.decode_packet(packet=packet_data)
                self._rx_message_queue.append(processed_packet)
                time.sleep(0.01)

            except serial.SerialTimeoutException:
                time.sleep(0.01)

    def _process_requests_from_cfx(self):
        while not self._stop_event.is_set() or self._values_left_to_send() or self._values_left_to_receive():
            # if new messages are available in the buffer, trigger a transition attempt
            if len(self._rx_message_queue) == 0:
                time.sleep(0.01)
                continue

            packet = self._rx_message_queue.popleft()
            self._fsm.input_received(packet=packet)

            self.logger.debug("Packet of type {} received".format(packet["packet_type"]))
            self.logger.debug("State is {}".format(self._fsm.state))

            try:
                self.logger.info("Values left to receive: {}".format(self.transaction['_values_left_to_receive']))
                self.logger.info("Values left to send: {}".format(self.transaction['_values_left_to_send']))

            except (AttributeError, KeyError):
                self.logger.debug("No transaction currently in progress")

            # Tree of things to do when the appropriate state is reached
            if self._fsm.state == 'wait_for_request_packet':
                self._wait_for_request_packet()
            elif self._fsm.state == 'start_transaction_tx':
                self._start_transaction_tx(packet=packet)
            elif self._fsm.state == 'start_transaction_rx':
                self._start_transaction_rx(packet=packet)
            elif self._fsm.state == "send_variable_description_packet":
                self._send_variable_description_packet(packet=packet)
            elif self._fsm.state == "receive_variable_description_packet":
                self._receive_variable_description_packet(packet=packet)
            elif self._fsm.state == "send_value_packet":
                self._send_value_packet(packet=packet)
            elif self._fsm.state == "receive_value_packet":
                self._receive_value_packet(packet=packet)
            elif self._fsm.state == "send_end_packet":
                self._send_end_packet()
            elif self._fsm.state == "receive_end_packet":
                self._receive_end_packet()

            else:
                self.logger.debug("State is {}".format(self._fsm.state))
            time.sleep(0.01)

        self._serial_connection.close()

    def _values_left_to_send(self, packet=None):
        return len(self._tx_message_queue) > 0

    def _no_values_left_to_send(self, packet=None):
        return len(self._tx_message_queue) == 0

    def _values_left_to_receive(self, packet=None):
        try:
            return self.transaction["values_left_to_receive"] > 0
        except KeyError:
            return False

    def _no_values_left_to_receive(self, packet=None):
        try:
            return self.transaction["values_left_to_receive"] == 0
        except KeyError:
            return False

    def _create_serial_connection(self):
        self.logger.info('Setting up a serial connection on {}'.format(self._serial_port))
        ser = serial.Serial(port=self._serial_port, baudrate=9600, parity=serial.PARITY_NONE,
                            bytesize=8, stopbits=serial.STOPBITS_TWO, timeout=3, inter_byte_timeout=0.05)

        # Set DTR, unset RTS
        ser.dtr = True
        ser.rts = False
        self._serial_connection = ser

    def _wait_for_request_packet(self):
        self.logger.debug("Wakeup received! Send acknowledgement")
        self._serial_connection.write(b'\x13')

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

        self.logger.debug("Transaction data: {}".format(self.transaction))
        self._serial_connection.write(b'\x06')

    def _start_transaction_rx(self, packet):
        self.logger.debug("Start transaction to send stuff to calculator")
        self.transaction = packet

        self._serial_connection.write(b'\x06')

    def _send_variable_description_packet(self, packet):
        self.logger.debug("Send variable description packet")

        # See if we have the requested data already
        variable_type = str(self.transaction['requested_variable_type'])
        variable_name = self.transaction['variable_name'].strip(b'\xff').decode('ascii')

        retrieved_data = self.transaction["retrieved_data"] = {
            'real_or_complex': "REAL",
            'value': np.array([[0]])
        }

        try:
            retrieved_data = self.read_from_data_store(variable_type=variable_type, variable_name=variable_name)
        except KeyError:
            self.logger.warning("{} {} was not found, send END packet?".format(variable_type, variable_name))

        self.transaction["retrieved_data"]["real_or_complex"] = retrieved_data['real_or_complex']

        if variable_type == cfx_codecs.variableType.VARIABLE:
            self.transaction['retrieved_data']['value'] = np.array([[retrieved_data['value']]])
        elif variable_type == cfx_codecs.variableType.MATRIX:
            self.transaction['retrieved_data']['value'] = retrieved_data['value']
        else:
            self.logger.warning("Unsupported datatype {}".format(str(variable_type)))

        self.logger.debug("Send variable description packet")
        request_response = Container(requested_variable_type=variable_type,
                                     rowsize=(b'\x01' if variable_type == cfx_codecs.variableType.VARIABLE else
                                              bytes(chr(self.transaction["retrieved_data"]["value"].shape[0]), "ascii")),
                                     colsize=(b'\x01' if variable_type == cfx_codecs.variableType.VARIABLE else
                                              bytes(chr(self.transaction["retrieved_data"]["value"].shape[1]), "ascii")),
                                     variable_name=b"A\xFF\xFF\xFF\xFF\xFF\xFF\xFF",
                                     real_or_complex=str(self.transaction["retrieved_data"]["real_or_complex"]))

        packet = packet_helpers.calculate_checksum(
                    cfx_codecs.variable_description_packet.build(request_response)
                )

        # Store packets to be sent in the transaction queue
        for idx, data_row in enumerate(self.transaction['retrieved_data']['value']):
            for idy, data_value in enumerate(data_row):

                self._tx_message_queue.append({'row': idx + 1, 'col': idy + 1, 'data': data_value,
                                              'real_or_complex':
                                                  self.transaction["retrieved_data"]["real_or_complex"]})

        self.logger.info("Appended {} items to the send queue".format(len(self._tx_message_queue)))

        self._serial_connection.write(packet)

    def _receive_variable_description_packet(self, packet):
        # todo: Remove this?
        self.logger.debug("Receive variable description packet")

    def _send_value_packet(self, packet):
        self.logger.info("{} values left to transfer...".format(len(self._tx_message_queue)))
        value_to_send = self._tx_message_queue.popleft()
        value_packet_response = packet_helpers.encode_value_packet(data=value_to_send)

        if value_to_send["real_or_complex"] == cfx_codecs.realOrComplex.COMPLEX:
            packet_to_write = packet_helpers.calculate_checksum(
                cfx_codecs.complex_value_packet.build(
                    value_packet_response
                )
            )
        else:
            packet_to_write = packet_helpers.calculate_checksum(
                cfx_codecs.real_value_packet.build(
                    value_packet_response
                )
            )

        self.logger.debug("Packet to write: {}, len: {}".format(packet_to_write, len(packet_to_write)))
        self._serial_connection.write(
            packet_helpers.calculate_checksum(
                packet_to_write
            )
        )

    def _receive_value_packet(self, packet):
        self.logger.debug("Receive value packet")

        if self.transaction["requested_variable_type"] == cfx_codecs.variableType.MATRIX:
            self.transaction["transaction_data"][packet['row']-1][packet['col']-1] = packet["value"]
        else:
            self.transaction["transaction_data"] = packet["value"]

        # todo: should this be done after end_packet has been received?

        variable_name = self.transaction['variable_name'].strip(b'\xff').decode('ascii')
        variable_type = str(self.transaction['requested_variable_type'])

        self.write_to_data_store(variable_type=variable_type, variable_name=variable_name,
                                 value=np.array(self.transaction["transaction_data"]),
                                 real_or_complex=self.transaction["real_or_complex"])

        self.logger.info("Data stored: type {}, name {}".format(variable_type, variable_name))

        self.transaction["values_left_to_receive"] -= 1
        self._serial_connection.write(b'\x06')

    def _send_end_packet(self):
        self.logger.debug("Send end packet")
        self._serial_connection.write(
            packet_helpers.calculate_checksum(
                cfx_codecs.end_packet.build(
                    Container()
                )
            )
        )

    def _receive_end_packet(self):
        self.logger.debug("Receive end packet")

    def write_to_data_store(self, variable_type, variable_name, value, real_or_complex):
        """
        Write data to the interface layer's data storage area.

        :param variable_type: Type of variable to be stored (of type cfx_codecs.variableType)
        :param variable_name: Name of variable to be stored, as entered on the calculator.
        This is in the following format:
                              Variables: just the variable name (e.g. "A")
                              Matrices: "Mat A"
                              Lists (currently unsupported): "List 1"
                              Pictures: to be decided, currently unimplemented
        :param value: np.array containing np.complex values
        :param real_or_complex: either "REAL" or "COMPLEX"
        :return:
        """

        self._data_store_lock.acquire()
        try:
            self._data_store[variable_type][variable_name] = {
                "value": np.array(value),
                "real_or_complex": real_or_complex
            }
        finally:
            self._data_store_lock.release()

        self.logger.info("Data stored: type {}, name {}".format(variable_type, variable_name))

    def read_from_data_store(self, variable_type, variable_name):
        """
        Read data from the interface layer's data storage area.
        :param variable_type: Type of variable to be stored (of type cfx_codecs.variableType)
        :param variable_name: Name of variable to be stored, as entered on the calculator.
        This is in the following format:
                              Variables: just the variable name (e.g. "A")
                              Matrices: "Mat A"
                              Lists (currently unsupported): "List 1"
                              Pictures: to be decided, currently unimplemented
        :return: Returns the value inside a numpy array.
        """
        self._data_store_lock.acquire()
        try:
            retrieved_data = self._data_store[variable_type][variable_name]
        finally:
            self._data_store_lock.release()

        self.logger.debug("Data retrieved: type {}, name {}".format(variable_type, variable_name))

        return retrieved_data
