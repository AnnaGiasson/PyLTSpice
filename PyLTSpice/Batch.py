#!/usr/bin/env python
# coding=utf-8

# -------------------------------------------------------------------------------
# Name:        Batch.py
# Purpose:     Tool used to launch LTSpice simulation in batch mode. Netlsts
#              can be updated by user instructions
#
# Author:      Nuno Brum (nuno.brum@gmail.com)
#
# Created:     23-12-2016
# Licence:     lGPL v3
# -------------------------------------------------------------------------------
"""
Allows to launch LTSpice simulations from a Python Script, thus allowing to
overcome the 3 dimensions STEP limitation on LTSpice, update resistor values,
or component models.

In the code snipped below will simulate a circuit with two different diode
models, setting the simulation temperature to 80 degrees and updates the values
of R1 and R2 to 3.3k. ::

    LTC = SimCommander("my_circuit.asc")
    LTC.set_parameters(temp=80)  # Sets the simulation temperature to be 80 degrees
    LTC.set_component_value('R2', '3.3k')
    for dmodel in ("BAT54", "BAT46WJ"):
        LTC.set_element_model("D1", model)  # Sets the Diode D1 model
        for res_value in range(2.2, 2,4, 0.2):
            LTC.set_component_value('R1', res_value)
            LTC.run()

    LTC.wait_completion()  # Waits for the LTSpice simulations to complete

    print("Total Simulations: {}".format(LTC.runno))
    print("Successful Simulations: {}".format(LTC.okSim))
    print("Failed Simulations: {}".format(LTC.failSim))

The first line will create an python class instance that represents the LTSpice
file or netlist that is to be simulated. This object implements methods that
are used to manipulate the spice netlist. For example, the method
set_parameters() will set or update existing parameters defined in the netlist.
The method set_component_value() is used to update existing component values or
models.

---------------
Multiprocessing
---------------

For making better use of today's computer capabilities, the SimCommander spawns
several LTSpice instances each executing in parallel a simulation. By default
the number of parallel simulations is 4, however the user can override this in
two ways. Either using the class constructor argument ``parallel_sims`` or by
forcing the allocation of more processes in the run() call by setting
``wait_resource=False``. ::

    LTC.run(wait_resource=False)

The recommended way is to set the parameter ``parallel_sims`` in the class
constructor. ::

    LTC=SimCommander("my_circuit.asc", parallel_sims=8)

The user then can launch a simulation with the updates done to the netlist by
calling the run() method. Since the processes are not executed right aways, but
rather just scheduled for simulation, the wait_completion() function is needed
if the user wants to execute code only after the completion of all scheduled
simulations.

The usage of wait_completion() is optional. Just note that the script will only
end when all the scheduled tasks are executed.

---------
Callbacks
---------

As seen above, the `wait_completion()` can be used to wait for all the
simulations to be finished. However, this is not efficient on a multiprocessor
point of view. Ideally, the post-processing should be also handled while other
simulations are still running. For this purpose, the user can use a function
call backs.

The callback function is called when the simulation has finished direclty by
the thread that has handling the simulation. A function callback receives two
arguments.
The RAW file and the LOG file names. Below is an example of a callback
function::

    def processing_data(raw_filename, log_filename):
        '''This is a call back function that just prints the filenames'''
        print(f"Simulation Raw file is {raw_filename}. log is {log_filename}")
        # Other code below either using LTSteps.py or LTSpice_RawRead.py
        log_info = LTSpiceLogReader(log_filename)
        log_info.read_measures()
        rise, measures = log_info.dataset["rise_time"]

The callback function is optional. if there no callback function is given then
thread is terminated just after the simulation is finished.
"""
__author__ = "Nuno Canto Brum <nuno.brum@gmail.com>"
__copyright__ = "Copyright 2020, Fribourg Switzerland"

import subprocess
import threading
import logging
from pathlib import Path
import time
from time import sleep
import sys
import traceback
from typing import Callable, Any, Iterable, Optional, Union
from PyLTSpice.SpiceEditor import SpiceEditor

__all__ = ('SimCommander', 'cmdline_switches', 'DEFAULT_EXE_PATH')

END_LINE_TERM = '\n'

logging.basicConfig(filename='Batch.log', level=logging.INFO)

if sys.platform == "linux":
    LTspice_arg = {'run': ['-b', '-Run']}
    DEFAULT_EXE_PATH = 'wine C:\\\\Program\\ Files\\\\LTC\\\\LTspiceXVII\\\\XVIIx64.exe'
elif sys.platform == "darwin":
    DEFAULT_EXE_PATH = Path('/Applications/LTspice.app/Contents/MacOS/LTspice')
    LTspice_arg = {'run': ['-b']}
else:  # Windows
    DEFAULT_EXE_PATH = Path(r"C:\Program Files\LTC\LTspiceXVII\XVIIx64.exe")
    LTspice_arg = {'netlist': ['-netlist'], 'run': ['-b', '-Run']}

# Legacy
LTspiceIV_exe = Path(r"C:\Program Files (x86)\LTC\LTspiceIV\scad3.exe")

cmdline_switches = []


def run_function(command: Iterable[str], timeout: Optional[int] = None) -> int:
    result = subprocess.run(command, timeout=timeout)
    return result.returncode


class RunTask(threading.Thread):
    """
    This is an internal Class and should not be used directly by the User.
    """

    def __init__(self, n_runs: int, netlist_file: Union[Path, str],
                 callback: Callable[[str, str], None], **kwargs) -> None:

        self.verbose = bool(kwargs.get('verbose', True))
        self.timeout = kwargs.get('timeout')
        self.exe_path = kwargs.get('exe_path', DEFAULT_EXE_PATH)

        threading.Thread.__init__(self)
        self.n_runs = int(n_runs)
        self.setName(f"sim{self.n_runs}")
        self.netlist_file = Path(netlist_file)
        self.callback = callback
        self.return_code = -1  # Signals an error by default

    @property
    def is_task_successful(self) -> bool:
        return (self.return_code == 0)

    def run(self) -> None:
        # Setting up
        logger = logging.getLogger(f"sim{self.n_runs}")
        logger.setLevel(logging.INFO)

        cmd_run = [str(self.exe_path), *LTspice_arg.get('run', []),
                   str(self.netlist_file), *cmdline_switches]

        # start execution
        self.start_time = time.process_time()
        if self.verbose:
            print(f"{time.asctime()}: Starting simulation {self.n_runs}")

        self.return_code = run_function(cmd_run, timeout=self.timeout)

        # clean up
        dt = time.process_time() - self.start_time
        sim_time = time.strftime("%H:%M:%S", time.gmtime(dt))

        self._cleanup_task(logger, sim_time)

    def _cleanup_task(self, logger: logging.Logger, sim_time: float) -> None:
        log_msg = (f"{time.asctime()}: Simulation "
                   f"{'Successful' if self.is_task_successful else 'Failed'}. "
                   f"Time elapsed: {sim_time}{END_LINE_TERM}")

        if self.verbose:
            print(log_msg)

        if self.is_task_successful:
            self._process_callback(logger)

        else:
            # simulation failed
            logger.warning(log_msg)

            log_file = self.netlist_file.with_suffix('.log')
            if log_file.exists():
                log_file.rename(log_file.with_suffix('.fail'))

    def _process_callback(self, logger: logging.Logger) -> None:

        if not self.callback:
            if self.verbose:
                print('No Callback')
            return None

        raw_file = self.netlist_file.with_suffix('.raw')
        log_file = self.netlist_file.with_suffix('.log')

        if raw_file.exists() and log_file.exists():
            if self.verbose:
                print("Calling the callback function")
            try:
                self.callback(raw_file, log_file)
            except Exception as err:
                error = traceback.format_tb(err)
                logger.error(error)
        else:
            logger.error("Simulation Raw/Log file not found")


class SimCommander(SpiceEditor):
    """
    The SimCommander class implements all the methods required for launching
    batches of LTSpice simulations.
    """
    def __init__(self, circuit_file: Union[Path, str], **kwargs) -> None:
        """
        Class Constructor. It serves to start batches of simulations.
        See Class documentation for more information.
        """
        self.exe_path = Path(kwargs.get('exe_path', DEFAULT_EXE_PATH))

        self.verbose = bool(kwargs.get("verbose", True))
        self.timeout = kwargs.get("timeout")

        file = Path(circuit_file)
        self.file_path = file.parent
        self.file_name = file.stem
        self.circuit_radic = file.with_suffix('')

        self.cmdline_switches = []
        self.parallel_sims = int(kwargs.get("parallel_sims", 4))
        self.threads = []

        # TODO: create the JSON or YAML file
        # master_log_filename = self.circuit_radic + '.masterlog'
        self.logger = logging.getLogger("SimCommander")
        self.logger.setLevel(logging.INFO)
        # TODO redirect this logger to a file.

        self.run_number = 0  # number of total runs
        self.failed_sim_count = 0  # number of failed simulations
        self.okSim = 0  # number of succesfull completed simulations
        # self.failParam = []  # collects for later user investigation of failed parameter sets
        self.netlist = []  # Netlist needs to be created in the __init__ for LINT purposes

        if file.suffix == '.asc':
            self.netlist_file = self.circuit_radic.with_suffix('.net')
            # prepare instructions, two stages used to enable edits on the netlist w/o open GUI
            # see: https://www.mikrocontroller.net/topic/480647?goto=5965300#5965300
            assert 'netlist' in LTspice_arg, "In this platform LTSpice doesn't have netlist generation capabilities "
            cmd_netlist = [str(self.exe_path),
                           *LTspice_arg.get('netlist', []),
                           str(file)]

            if self.verbose:
                print("Creating Netlist")
            retcode = run_function(cmd_netlist)
            if retcode == 0:
                if self.verbose:
                    print("The Netlist was successfully created")
                self.reset_netlist()

        else:   # Supposedly it is a net or similar net file
            self.netlist_file = circuit_file
            self.reset_netlist()

        if not self.netlist:
            self.logger.error("Unable to create Netlist")

    def __del__(self) -> None:
        """Class Destructor : Closes Everything"""
        self.logger.debug("Waiting for all spawned threads to finish.")
        self.wait_completion()  # TODO: Kill all pending simulations
        self.logger.debug("Exiting SimCommander")

    def add_LTspiceRunCmdLineSwitches(self, *args) -> None:
        """
        Used to add an extra command line argument such as -I<path> to add symbol search path or -FastAccess
        to convert the raw file into Fast Access.
        The arguments is a list of strings as is defined in the LTSpice command line documentation.

        :param args: list of strings
            A list of command line switches such as "-ascii" for generating a raw file in text format or "-alt" for
            setting the solver to alternate. See Command Line Switches information on LTSpice help file.
        :type args: list[str]
        :returns: Nothing
        """
        global cmdline_switches
        cmdline_switches = args

    def run(self, run_filename: str = None, wait_resource: bool = True,
            callback: Callable[[str, str], Any] = None) -> int:
        """
        Executes a simulation run with the conditions set by the user.
        Conditions are set by the set_parameter, set_component_value or
        add_instruction functions.

        :param run_filename:
            The name of the netlist can be optionally overridden if the user
            wants to have a better control of how the simulations files are
            generated.
        :type run_filename: str
        :param wait_resource:
            Setting this parameter to False, will force the simulation to start
            immediately, irrespective of the number of simulations already
            active. By default the SimCommander class uses only four
            processors. This number can then be overridden by setting the
            parameter ´parallel_sims´ to a different number. If there are more
            than ´parallel_sims´ simulations being done, the new one will be
            placed on hold till one of the other simulations are finished.
        :type wait_resource: bool
        :param callback:
            The user can optionally give a callback function for when the
            simulation finishes, so that a processing can be immediately done.
        :type: callback: function(raw_file, log_file)

        :returns: Nothing
        """
        # decide sim required
        if self.netlist is not None:
            # update number of simulation, using internal sim number in case a
            # run_id is not supplied
            self.run_number += 1

            # Write the new settings
            if run_filename is None:
                run_netlist_file = f"{self.circuit_radic}_{self.run_number}.net"
            else:
                run_netlist_file = run_filename

            self.write_netlist(run_netlist_file)

            while True:
                self.update_stats()  # purge ended tasks

                if (wait_resource is False) or (len(self.threads) < self.parallel_sims):
                    t = RunTask(self.run_number, run_netlist_file, callback,
                                timeout=self.timeout, verbose=self.verbose,
                                exe_path=self.exe_path)
                    self.threads.append(t)
                    t.start()
                    sleep(0.01)  # Give slack for the thread to start
                    break
                sleep(0.1)  # Give Time for other simulations to end

            return self.run_number  # Just returns the simulation number

        else:
            # no simulation required
            raise UserWarning(f'skipping simulation {self.run_number}')

    def update_stats(self) -> None:
        """
        This function updates the OK/Fail statistics and releases finished
        RunTask objects from memory.

        :returns: Nothing
        """
        i = 0
        while i < len(self.threads):
            if self.threads[i].is_alive():
                i += 1
                continue

            if self.threads[i].is_task_successful:
                self.okSim += 1
            else:
                self.failed_sim_count += 1
            del self.threads[i]

    def wait_completion(self) -> None:
        """
        This function will wait for the execution of all scheduled simulations
        to complete.

        :returns: Nothing
        """
        self.update_stats()
        while len(self.threads) > 0:
            sleep(0.5)
            self.update_stats()


if __name__ == "__main__":

    # get script absolute path
    root_path = Path(__file__).parent.parent.absolute()

    # select spice model
    LTC = SimCommander(root_path.joinpath("test_files", "testfile.asc"))
    LTC.set_parameters(res=1e-3, cap=100e-6)  # set default arguments

    # define simulation
    LTC.add_instructions(
        "; Simulation settings",
        # [".STEP PARAM Rmotor LIST 21 28"],
        ".TRAN 3m",
        # ".step param run 1 2 1"
    )

    # do parameter sweep
    for res in range(5):
        LTC.set_parameters(ANA=res)
        raw, log = LTC.run()
        print("Raw file '%s' | Log File '%s'" % (raw, log))

    # Sim Statistics
    print(f'Successful/Total Simulations: {LTC.okSim}/{LTC.run_number}')

    def callback_function(raw_file, log_file):
        print(f"Handling simulation data for {raw_file}, log file {log_file}")

    LTC = SimCommander(root_path.joinpath("test_files", "testfile.asc"),
                       parallel_sims=1)
    tstart = 0
    for tstop in (2, 5, 8, 10):
        tduration = tstop - tstart
        LTC.add_instruction(".tran {}".format(tduration),)
        bias_file = "sim_loadbias_%d.txt" % tstop

        if tstart != 0:
            LTC.add_instruction(".loadbias {}".format(bias_file))
            # Put here your parameter modifications
            LTC.set_parameters(param1=1, param2=2, param3=3)

        LTC.add_instruction(".savebias {} internal time={}".format(bias_file,
                                                                   tduration))
        tstart = tstop
        LTC.run(callback=callback_function)
