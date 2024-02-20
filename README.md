# pyMSO4
A python library for interfacing with the Tektronix MSO4 oscilloscopes (tested
with MSO44).

## Installation
```bash
pip install pyMSO4
```

## Usage
Connect the probe on channel 1 to the calibration square wave output, and press
the Autoset button, the following code will capture a trace of the signal as
seen on the oscilloscope screen:

```python
import pyMSO4
mso44 = pyMSO4.MSO4(trig_type=pyMSO4.MSO4EdgeTrigger)
mso44.con(ip="128.181.240.130") # Using p2p ethernet connection
mso44.ch_a_enable([True, False, False, False]) # Enable channel 1
mso44.acq.wfm_src = ['ch1'] # Set waveform source to channel 1
mso44.acq.wfm_start = 0
mso44.acq.wfm_stop = mso44.acq.horiz_record_length # Get all data points
wfm = mso44.sc.query_binary_values('CURVE?', datatype=mso44.acq.get_datatype(), is_big_endian=mso44.acq.is_big_endian)
mso44.dis()
```

Additional examples can be found in the [documentation][1].

## Documentation
Sphinx documentation is available [here][1].

## Got root?
If you're here because you think it's fun to get root on an oscilloscope, see
Appendix C of the
[report](https://github.com/ceres-c/pyMSO4/blob/master/report/report.pdf)
for the details.

[1]: https://ceres-c.it/pyMSO4/
