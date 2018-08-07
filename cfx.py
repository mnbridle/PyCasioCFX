from transitions import Machine
import time
import serial
from helpers import packet_helpers, cfx_codecs
from construct import Container
import logging
from pprint import pprint, pformat
import numpy as np


class cfxStateMachine(object):
    def __init__(self, serial_port):
        self._initialiseLogging()

        self.serial_port = serial_port
        self.serial_connection = None
        self.transaction = None

        # Data store
        self.data_store = {
            'VARIABLE': {
                'A': np.complex(123456789, -5654256)
            },
            'PICTURE': {},
            'MATRIX': {},
            'LIST': {}
        }

        self._createStateMachine()
        self.initialise()
    
    def _initialiseLogging(self):
        logging.basicConfig(format='%(asctime)s.%(msecs)03d %(name)s %(levelname)s %(message)s', datefmt='%F %H:%M:%S',
                            level=logging.INFO)
        self.logger = logging.getLogger("cfx_interface")
        self.logger.info("Initialising the CFX interface object.")

    def _createStateMachine(self):
        states = ["wait_for_wakeup", "wait_for_transaction_request_packet",
                  "process_transaction"]

        transitions = [
            {'trigger': 'initialise', 'source': 'initial', 'dest': 'wait_for_wakeup',
             'prepare': 'create_serial_connection'},
            {'trigger': 'received_wakeup', 'source': 'wait_for_wakeup', 'dest': 'wait_for_transaction_request_packet',
             'prepare': '_ack_wakeup'},
            {'trigger': 'transaction_request_packet_rxed', 'source': 'wait_for_transaction_request_packet',
             'dest': 'process_transaction', 'prepare': '_send_acknowledgement'},
            {'trigger': 'transaction_processed', 'source': 'process_transaction', 'dest': 'wait_for_wakeup'},
        ]

        self.logger.debug('Creating state machine...')
        self.machine = Machine(self, states=states, transitions=transitions)
        self.machine.on_enter_wait_for_wakeup('_wait_for_wakeup')
        self.machine.on_enter_wait_for_transaction_request_packet('_wait_for_transaction_request_packet')
        self.machine.on_enter_process_transaction('_process_transaction')

    def create_serial_connection(self):
        self.logger.info('Setting up a serial connection on {}'.format(self.serial_port))
        ser = serial.Serial(port=self.serial_port, baudrate=9600, parity=serial.PARITY_NONE,
                            bytesize=8, stopbits=serial.STOPBITS_TWO, timeout=0.1)

        # Set DTR, unset RTS
        ser.dtr = True
        ser.rts = False
        self.serial_connection = ser

    def destroy_serial_connection(self):
        self.logger.info('Destroying serial connection')
        self.serial_connection.close()

    def _wait_for_wakeup(self):
        # Wait for "I am here" from calculator
        self.logger.info("Waiting for wakeup from calculator")
        self._wait_for_single_byte(wait_for_byte=b'\x15')
        self.received_wakeup()

    def _ack_wakeup(self):
        self.logger.info("Acknowledge wakeup")
        self.serial_connection.write(b'\x13')

    def _wait_for_transaction_request_packet(self):
        self.logger.info("Waiting for transaction request packet")
        serdata = self._wait_for_packet(packet_length=50)
        self.transaction = packet_helpers.decode_packet(packet=serdata)
        self.transaction_request_packet_rxed()

    def _send_acknowledgement(self):
        self.logger.info("Send acknowledgement")
        self.serial_connection.write(b'\x06')

    def _wait_for_acknowledgement(self):
        self.logger.debug("Waiting for acknowledgement")
        self._wait_for_single_byte(wait_for_byte=b'\x06')
        self.logger.info("Acknowledgement received")

    def _wait_for_single_byte(self, wait_for_byte=b'\x06'):
        succeeded = False
        while not succeeded:
            time.sleep(0.01)
            serdata = self.serial_connection.read(size=1)
            succeeded = (True if serdata == wait_for_byte else False)
        return succeeded

    def _wait_for_packet(self, packet_length=50):
        succeeded = False
        while not succeeded:
            time.sleep(0.1)
            serdata = self.serial_connection.read(size=packet_length)
            succeeded = True

        return serdata

    def _process_transaction(self):
        self.logger.info("Process transaction")

        if self.transaction["tag"] == b'REQ':
            self._send_transaction_data()
        elif self.transaction["tag"] == b'VAL':
            self._receive_transaction_data()
        elif self.transaction["tag"] == b'END':
            self.logger.debug("The calculator is prematurely ending the transaction - nothing to do?")
        else:
            self.logger.info("Not entirely sure what's going on here")

        self.logger.info("Transaction processed! Returning to waiting mode...")
        self.transaction_processed()

    def _receive_transaction_data(self):
        self.logger.info("Processing transaction - receiving data")

        if self.transaction["requested_variable_type"] == cfx_codecs.variableType.VARIABLE:
            number_of_data_items = 1
            transaction_data = None
        elif self.transaction["requested_variable_type"] == cfx_codecs.variableType.MATRIX:
            number_of_data_items = ord(self.transaction['rowsize']) * ord(self.transaction['colsize'])
            self.transaction["real_or_complex"] = cfx_codecs.realOrComplex.REAL
            transaction_data = [[0 for x in range(ord(self.transaction['colsize']))] for y in
                                range(ord(self.transaction['rowsize']))]
        else:
            self.logger.warning("Unsupported variable type requested! - {}".format(
                self.transaction["requested_variable_type"]
            ))
            return

        item_count = 0
        while item_count < number_of_data_items:
            serdata = self._wait_for_packet(packet_length=(16 if self.transaction["real_or_complex"] ==
                                                           cfx_codecs.realOrComplex.REAL else 26))

            self.logger.info("Received some data")

            data_item = packet_helpers.decode_value_packet(packet=serdata)
            if self.transaction["requested_variable_type"] == cfx_codecs.variableType.MATRIX:
                transaction_data[data_item['row']-1][data_item['col']-1] = data_item['value']
            else:
                transaction_data = data_item['value']

            self._send_acknowledgement()
            item_count += 1

        self._store_transaction_data(transaction=self.transaction, data=transaction_data)
        self.logger.info('Contents of data store: ' + pformat(self.data_store))

    def _send_transaction_data(self):
        self.logger.info("Processing transaction - transmitting data")
        self.logger.info(pformat(self.transaction))
        self._wait_for_acknowledgement()

        # See if we have the requested data already
        variable_type = str(self.transaction['requested_variable_type'])
        variable_name = self.transaction['variable_name'].strip(b'\xff').decode('ascii')

        try:
            retrieved_value = self.data_store[variable_type][variable_name]
        except KeyError:
            self.logger.warning("{} {} was not found, sending END packet...".format(variable_type, variable_name))
            self._send_end_packet()
            return

        self.logger.info("Send variable description packet")
        request_response = Container(requested_variable_type='VARIABLE',
                                     rowsize=b'\x01',
                                     colsize=b'\x01',
                                     variable_name=b"A\xFF\xFF\xFF\xFF\xFF\xFF\xFF",
                                     real_or_complex='COMPLEX')
        packet = packet_helpers.calculate_checksum(
                    cfx_codecs.variable_description_packet.build(request_response)
                )
        self.serial_connection.write(packet)
        self._wait_for_acknowledgement()

        self.logger.info("Send value packet")
        # Send value packet
        value_packet_response = packet_helpers.encode_value_packet(retrieved_value)
        packet_to_write = packet_helpers.calculate_checksum(
            cfx_codecs.complex_value_packet.build(
                value_packet_response
            )
        )

        self.logger.info("Packet to write: {}, len: {}".format(packet_to_write, len(packet_to_write)))
        self.serial_connection.write(
            packet_helpers.calculate_checksum(
                cfx_codecs.complex_value_packet.build(
                    value_packet_response
                )
            )
        )

        self._wait_for_acknowledgement()
        self._send_end_packet()

    def _store_transaction_data(self, transaction, data):
        self.logger.info("Store received transaction data")

        variable_name = transaction['variable_name'].strip(b'\xff').decode('ascii')
        variable_type = str(self.transaction['requested_variable_type'])
        self.data_store[variable_type][variable_name] = data
        self.logger.info("Data stored: type {}, name {}".format(variable_type, variable_name))

    def _send_end_packet(self):
        self.logger.info("Sending end packet!")
        self.serial_connection.write(
            packet_helpers.calculate_checksum(
                cfx_codecs.end_packet.build(
                    Container()
                )
            )
        )


stateMachine = cfxStateMachine(serial_port='COM1')
