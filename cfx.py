from transitions import Machine
import time
import serial
from helpers import packet_helpers, cfx_codecs


class cfxStateMachine(object):
    def __init__(self, serial_port):
        self.serial_port = serial_port
        self.serial_connection = None

        # Put the current transaction here
        self.transaction = None

        # Data store
        self.data_store = {
            'VM': {},
            'PC': {},
            'MT': {},
            'LT': {}
        }

        states = ["WaitForWakeup", "WaitForTransactionRequestPacket",
                  "ProcessTransaction", "WaitForWakeup"]

        transitions = [
            {'trigger': 'initialise', 'source': 'initial', 'dest': 'WaitForWakeup',
             'prepare': 'create_serial_connection'},
            {'trigger': 'receivedWakeup', 'source': 'WaitForWakeup', 'dest': 'WaitForTransactionRequestPacket',
             'prepare': '_ackWakeup'},
            {'trigger': 'transactionRequestPacketRxed', 'source': 'WaitForTransactionRequestPacket',
             'dest': 'ProcessTransaction', 'prepare': '_ackTransactionRequest'},
            {'trigger': 'transactionProcessed', 'source': 'ProcessTransaction', 'dest': 'WaitForWakeup'},
        ]

        self.machine = Machine(self, states=states, transitions=transitions)
        self.machine.on_enter_WaitForWakeup('_waitForWakeup')
        self.machine.on_enter_WaitForTransactionRequestPacket('_waitForTransactionRequestPacket')
        self.machine.on_enter_ProcessTransaction('_processTransaction')

        self.initialise()

    def create_serial_connection(self):
        ser = serial.Serial(port=self.serial_port, baudrate=9600, parity=serial.PARITY_NONE,
                            bytesize=8, stopbits=serial.STOPBITS_ONE, timeout=0.1)

        # Set DTR, unset RTS
        ser.dtr = True
        ser.rts = False
        self.serial_connection = ser

    def destroy_serial_connection(self):
        self.serial_connection.close()

    def _waitForWakeup(self):
        # Wait for "I am here" from calculator
        succeeded = False
        while not succeeded:
            time.sleep(0.1)
            serdata = self.serial_connection.read(size=50)
            succeeded = True if serdata == b'\x15' else False

        self.receivedWakeup()

    def _ackWakeup(self):
        self.serial_connection.write(b'\x13')

    def _waitForTransactionRequestPacket(self):
        succeeded = False
        while not succeeded:
            time.sleep(0.1)
            serdata = self.serial_connection.read(size=50)
            succeeded = True

        # Decode request type and store the transaction
        self.transaction = packet_helpers.decode_packet(packet=serdata)
        self.transactionRequestPacketRxed()

    def _ackTransactionRequest(self):
        self.serial_connection.write(b'\x06')

    def _processTransaction(self):
        if self.transaction["packet_type"] == ":REQ":
            self._sendTransactionData()

        elif self.transaction["packet_type"] == ":VAL":
            self._receiveTransactionData()

        elif self.transaction["packet_type"] == ":END":
            print("The calculator is prematurely ending the transaction - nothing to do?")

        else:
            print("Not entirely sure what's going on here")

        return


    def _receiveTransactionData(self):
        # Receive some data from the calculator
        if self.transaction["requested_variable_type"] == "VM":
            number_of_data_items = 1
            transaction_data = None
        elif self.transaction["requested_variable_type"] == "MT":
            number_of_data_items = self.transaction['row'] * self.transaction['col']
            self.transaction["complex_or_real"] = "Real"
            transaction_data = [[0 for x in range(self.transaction['col'])] for y in range(self.transaction['row'])]
        else:
            return

        item_count = 0
        while item_count < number_of_data_items:
            succeeded = False
            while not succeeded:
                serdata = self.serial_connection.read(size=(16 if self.transaction["complex_or_real"] == "Real"
                                                            else 26))
                succeeded = True

            data_item = packet_helpers.decode_value_packet(packet=serdata)
            if self.transaction["requested_variable_type"] == "MT":
                transaction_data[data_item['row']-1][data_item['col']-1] = data_item['value']
            else:
                transaction_data = data_item['value']

            self._ackTransactionRequest()
            print(data_item['value'])
            item_count += 1

        print(transaction_data)

    def _sendTransactionData(self):
        # Send some data to the calculator
        pass


stateMachine = cfxStateMachine(serial_port='COM1')
