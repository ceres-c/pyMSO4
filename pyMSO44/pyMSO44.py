import pyvisa

def init():
	rm = pyvisa.ResourceManager('@py')
	rm.list_resources()
	# ('USB0::0x1AB1::0x0588::DS1K00005888::INSTR')
	
	# inst = rm.open_resource('USB0::0x1AB1::0x0588::DS1K00005888::INSTR')
	
	# print(inst.query("*IDN?"))