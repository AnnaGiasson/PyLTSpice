# README #

PySpicer is a toolchain of python utilities design to interact with LTSpice Electronic Simulator.

## What is contained in this repository ##

* __LTSteps.py__
An utility that extracts from LTSpice output files data, and formats it for import in a spreadsheet,s uch like Excel or Calc.

* __LTSpice_RawRead.py__
A pure python class that serves to read raw files into a python class.

* __Histogram.py__
A python script that uses numpy and matplotlib to create an histogram and calculate the sigma deviations. This is useful for Monte-Carlo analysis.

* __Batch.py__
This is a script to launch LTSpice Simulations. This is useful because:

    - Can overcome the limitation of only stepping 3 parameters
    - Different types of simulations .TRAN .AC .NOISE can be run in a single batch
    - The RAW Files are smaller and easier to treat
    - When used with the LTSpiceRaw_Reader.py and LTSteps.py, validattion of the circuit can be done automatically.
    - Different models can be simulated in a single batch, by using the following instructions:
        - `set_element_model('D1', '1N4148') # Replaces the Diode D1 with the model 1N4148 `
        - `set_component_value('R2', '33k') # Replaces the value of R2 by 33k`
        - `set_parameters(run=1, TEMP=80) # Creates or updates the netlist to have .PARAM run=1 or .PARAM TEMP=80`
        - `add_instructions(".STEP run -1 1023 1", ".dc V1 -5 5") `
        - `remove_instruction(".STEP run -1 1023 1")  # Removes previously added instruction`
        - `reset_netlist() # Resets all edits done to the netlist.`

    Note: It was only tested with Windows based installations.

## How to Install ##
`pip install PyLTSpice `

### Updating PyLTSpice ###
 `pip install --upgrade PyLTSpice `

### Using GITHub ###

 `git clone https://github.com/nunobrum/PyLTSpice.git `

If using this method it would be good to add the path where you cloned the site to python path.

 `import sys `
 `sys.path.append(<path to PyLTSpice>) `

## How to use ##

Here follows a quick outlook on how to use each of the tools.

More comprehnsive documentation can be found in https://pyltspice.readthedocs.io/en/latest/

### LTSpice_RawRead.py ###
Include the following line on your scripts

 ```python
 from PyLTSpice.LTSpice_RawRead import LTSpiceRawRead

 from matplotlib import plot


 LTR = LTSpiceRawRead("Draft1.raw")

 print(LTR.get_trace_names())
 print(LTR.get_raw_property())

 IR1 = LTR.get_trace("I(R1)")
 x = LTR.get_trace('time') # Gets the time axis
 steps = LTR.get_steps()
 for step in range(len(steps)):
     # print(steps[step])
     plt.plot(x.get_time_axis(step), IR1.get_wave(step), label=steps[step])

 plt.legend() # order a legend
 plt.show()
 ```

### LTSpice_Batch ###
This module is used to launch LTSPice simulations. Results then can be processed with either the LTSpiceRawRead
or with the LTSteps module to read the log file which can contain .MEAS results.

The script will firstly invoke the LTSpice in command line to generate a netlist, and then this netlist can be
updated directly by the script, in order to change component values, parameters or simulation commands.

Here follows an example of operation.

```python
import os
from PyLTSpice.Batch import SimCommander

# get script absolute path
meAbsPath = os.path.dirname(os.path.realpath(__file__))
# select spice model
LTC = SimCommander(meAbsPath + "\\Batch_Test.asc")

LTC.set_parameters(res=0, cap=100e-6)  # Redefining parameters in the netlist
LTC.set_component_value('R2', '2k')  # Redefining component values
LTC.set_component_value('R1', '4k')

# define simulation
LTC.add_instructions(
    "; Simulation settings",
    ".param run = 0"  # Commands can be set directly with the .param command instad of the set_parameters(...)
)
def process_data(raw_file, log_file):
    """This function is called after the completion of every simulation"""
    print("Hint : use the LTRawRead to process the '%s'" % raw_file)
    print("Hint : use the LTSteps to process the '%s'" % log_file)

for opamp in ('AD712', 'AD820'):
    # Setting a model of the U1 Component. Note that subcircuits need the X prefix
    LTC.set_element_model('XU1', opamp)
    for supply_voltage in (5, 10, 15):
        LTC.set_component_value('V1', supply_voltage)  # Set a voltage source value
        LTC.set_component_value('V2', -supply_voltage)
        LTC.run(callback=process_data)  # Runs the simulation with the updated netlist
        # The run() returns the RAW filename and LOG filenames so that can be processed with
        # the LTSpice_ReadRaw and LTSteps modules.

LTC.reset_netlist()  # This resets all the changes done to the checklist
LTC.add_instructions(  # Changing the simulation file
    "; Simulation settings",
    ".ac dec 30 10 1Meg",
    ".meas AC Gain MAX mag(V(out)) ; find the peak response and call it ""Gain""",
    ".meas AC Fcut TRIG mag(V(out))=Gain/sqrt(2) FALL=last"
)

raw, log = LTC.run()
LTC.wait_completion()
```

### LTSteps.py ###
This module defines a class that can be used to parse LTSpice log files where the information about .STEP information is written.
There are two possible usages of this module, either programmatically by importing the module and then accessing data through the
class as exemplified here:

```python
from PyLTSpice.LTSteps import LTSpiceLogReader

data = LTSpiceLogReader("Batch_Test_AD820_15.log")

print("Number of steps  :", data.step_count)
step_names = data.get_step_vars()
meas_names = data.get_measure_names()

# Printing Headers
print(' '.join([f"{step:15s}" for step in step_names]), end='')  # Print steps names with no new line
print(' '.join([f"{name:15s}" for name in meas_names]), end='\n')
# Printing data
for i in range(data.step_count):
    print(' '.join([f"{data[step][i]:15}" for step in step_names]), end='')  # Print steps names with no new line
    print(' '.join([f"{data[name][i]:15}" for name in meas_names]), end='\n')  # Print Header

print("Total number of measures found :", data.measure_count)
```
The second possibility is to use the module directly on the command line
 `python -m PyLTSpice.LTSteps <filename> `
 The <filename> can be either be a log file (.log), a data export file (.txt) or a measurement output file (.meas)
 This will process all the data and export it automatically into a text file with the extension (tlog, tsv, tmeas)
 where the data read is formatted into a more convinient tab separated format.
 In case the <logfile> is not provided, the script will scan the directory and process the newest log, txt or out file found.

### Histogram.py ###
This module uses the data inside on the filename to produce an histogram image.
 ```
Usage: Histogram.py [options] LOG_FILE TRACE

Options:
  --version             show program's version number and exit
  -h, --help            show this help message and exit
  -s SIGMA, --sigma=SIGMA
                        Sigma to be used in the distribution fit. Default=3
  -n NBINS, --nbins=NBINS
                        Number of bins to be used in the histogram. Default=20
  -c FILTERS, --condition=FILTERS
                        Filter condition writen in python. More than one
                        expression can be added but each expression should be
                        preceded by -f. EXAMPLE: -c V(N001)>4 -c parameter==1
                        -c  I(V1)<0.5
  -f FORMAT, --format=FORMAT
                        Format string for the X axis. Example: -f %3.4f
  -t TITLE, --title=TITLE
                        Title to appear on the top of the histogram.
  -r RANGE, --range=RANGE
                        Range of the X axis to use for the histogram in the
                        form min:max. Example: -r -1:1
  -C, --clipboard       If the data from the clipboard is to be used.
  -i IMAGEFILE, --image=IMAGEFILE
                        Name of the image File. extension 'png'
 ```

### LTSpice_SemiDevOpReader.py ###
This module is used to read from LTSpice log files Semiconductor Devices Operating Point Information.
A more detailed documentation is directly included in the source file docstrings.

## To whom do I talk to? ##

* Tools website : [https://www.nunobrum.com/pyspicer.html](https://www.nunobrum.com/pyspicer.html)
* Repo owner : [me@nunobrum.com](me@nunobrum.com)
* Alternative contact : nuno.brum@gmail.com

## History ##
Version 1.4
Adding the LTSpice_SemiDevOpReader module
Re-enabling the Histogram functions which where disabled by mistake.

* Version 1.3
Bug fixes on the SpiceEditor Class

* Version 1.2
README.md:
Adding link to readthedocs documentation
All files:
Comprehensive documentation on how to use each module

* Version 1.1
README.md:
Updated the description
Batch.py:
Corrected the name of the returned raw file.
Added comments throughout the code and cleanup

* Version 1.0
Batch.py:
Implemented an new approach (NOT BACKWARDS COMPATIBLE), that avoids the usage of the sim_settings.inc file.
And allows to modify not only parameters, but also models and even the simulation commands.
LTSpice_RawRead.py:
Added the get_time_axis method to the RawRead class to avoid the problems with negative values on
time axis, when 2nd order compression is enabled in LTSpice.
LTSteps.py:
Modified the LTSteps so it can also read measurements on log files without any steps done.


* Version 0.6
Histogram.py now has an option to make the histogram directly from values stored in the clipboard

* Version 0.5
The LTSpice_RawReader.py now uses the struc.unpack function for a faster execution

* Version 0.4
Added Batch.py to the collection of tools

* Version 0.3
A version of LTSteps that can be imported to use in a higher level script

* Version 0.2
Adding LTSteps.py and Histogram.py

* Version 0.1
First commit to the bitbucket repository.
