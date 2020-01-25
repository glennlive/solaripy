#!/usr/bin/env python

"""
Simple Solar Cell Tester
========================

Intended for use with two electronic loads and two solar cells.
The first provides a reference point for normalizing sunlight. The second
is load is connected to  the cell/string under test, which will be
swept over current.

"""
import serial
import logging
from time import sleep
import datetime
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

from Array371X import Array371X

# default collection settings
DEFAULT_DUT = {"port":"/dev/ttyUSB0", "baudrate":9600, "address":0}
DEFAULT_REF = {"port":"/dev/ttyUSB1", "baudrate":9600, "address":1}
DEFAULT_ISET_STEP = 0.01    # step size in amps
DEFAULT_IMAX_EST = 0.250    # current in amps at ~ PP
DEFAULT_ISET_RANGE = np.arange(0.0, 0.3, DEFAULT_ISET_STEP)
DEFAULT_SUN_REFERENCE = 1.50  # minimum voltage required

# configuration options
PLOT_XAXIS_ISET = True # use set current or measured current for x-axis


def plot_iv_curve(df, title=None, filename=None):
    """
    Params:
        df      pandas DataFrame with iset, v and i from data test
        title   optional title for graph
    """
    if not all([k in df for k in ['iset', 'i', 'v']]):
        logging.error("data did not contain proper columns")
        return

    if 'p' not in df:
        df['p'] = df.v * df.i

    ax = df.plot(x='iset' if PLOT_XAXIS_ISET else 'i', label='Voltage',
            y='v', marker='x', color='b', title=title, legend=False)
    ax1 = ax.twinx()
    df.plot(x='iset' if PLOT_XAXIS_ISET else 'i', label='Power',
            y='p', marker='x', color='r', ax=ax1, legend=False)
    ax.set_ylabel('Cell Voltage (Volts)')
    ax.yaxis.label.set_color('blue')
    ax.set_xlabel('Current (Amps)')
    ax1.set_ylabel('Power (Watts)')
    ax1.yaxis.label.set_color('red')

    pp = df.iloc[df.p.idxmax()]
    x = pp.iset if PLOT_XAXIS_ISET else pp.i
    ax.set_xlim([0, x*1.5])
    ax.set_ylim([0, df['v'].max()*1.5])
    ax.annotate('Peak Power Point:\n%0.3fV @ %0.3fA' % (pp.v, pp.i),
        xy=(x, pp.v), xytext=(x*0.6, pp.v*0.6),
        arrowprops=dict(facecolor='black', arrowstyle='->'))
    ax1.annotate('Max Power:\n%0.3fW' % (pp.p),
        xy=(x, pp.p), xytext=(x*1.2, pp.p*0.8),
        arrowprops=dict(facecolor='black', arrowstyle='->'))
    if filename:
        ax.get_figure().savefig(filename)
    plt.show()


def collect_iv_data(dut, ref, ref_min=1.5, iset_range=[], avg_cnt=1):
    """
    Collect I-V data from the DUT.
    
    Params:
        dut         electronic load connected to DUT string
        ref         electronic load instance connected to reference cell
        ref_min     min voltage required on reference cell (sunlight present)
        iset_range  range of currents
        avr_cnt     set highter to take more than one reading
    """
    avg_cnt = min(1, int(avg_cnt))
    ret = []
    for iset in iset_range:
        # check ref cell
        while ref.voltage < ref_min:
            print("...waiting for sunlight: %0.3fV < %0.3fV, %0.3fW" %
                  (ref.voltage, ref_min, ref.voltage*ref.current))
            sleep(1.0)
        print(ref.voltage)
        
        # setup next current reading
        dut.current = iset
        sleep(0.25)

        # average if requested
        i, v, r = 0, 0
        for _ in range(avg_cnt):
            i += dut.current
            v += dut.voltage
            r += ref.voltage
        print(iset, i, v, r)
        ret.append(dict(iset=iset, v=v/avg_cnt, i=i/avg_cnt, ref=r/avg_cnt))
    return ret


class FakeLoad:
    def __init__(self):
        self._current = 0.0
        self.voltage = 1.7
        self.enabled = True

    @property
    def current(self):
        self._current += 0.01
        return self._current

    @current.setter
    def current(self, value):
        self._current = value
        self.voltage -= 0.01 * value
        if value > 0.25:
            self.voltage *= 0.9


def main():
    from argparse import ArgumentParser
    parser = ArgumentParser(description="Sun-light Solar Cell Tester")
    parser.add_argument('--string_id', action='store',
                        default='test-cell-01',
                        help='descriptive name for cell and filename')
    parser.add_argument('--dut', action='store',
                        default=DEFAULT_DUT["port"],
                        help='serial port to electronic load for Device Under Test')
    parser.add_argument('--ref', action='store',
                        default=DEFAULT_REF["port"],
                        help='serial port to electronic load for reference cell')
    parser.add_argument('--sunlight', action='store',
                        default=DEFAULT_SUN_REFERENCE,
                        help='Sunlight voltage required on reference cell')
    parser.add_argument('--istep', action='store',
                        default=DEFAULT_ISET_STEP,
                        help='current step size')
    parser.add_argument('--estimated_imax', action='store',
                        default=DEFAULT_IMAX_EST,
                        help='approximate current value for peak-power')
    parser.add_argument('--samples_per_step', action='store',
                        default=1,
                        help='number of samples per step for averaging')

    args = parser.parse_args()
    print(args)

    filename = args.string_id + "." + datetime.datetime.utcnow().strftime("%Y-%m-%d-%H%M")
    iset_range = list(np.arange(0.0, args.estimated_imax*1.5, args.istep))
    iset_range += list(np.arange(args.estimated_imax*0.9,
                            args.estimated_imax*1.1,
                            args.estimated_imax*0.02))
    iset_range.sort()

    dut = Array371X(serial.Serial(args.dut, baudrate=DEFAULT_DUT['baudrate']),
                    address=DEFAULT_DUT['address'])
    dut = FakeLoad()
    ref = Array371X(serial.Serial(args.ref, baudrate=DEFAULT_REF['baudrate']),
                    address=DEFAULT_REF['address'])
    data = collect_iv_data(dut, ref, args.sunlight, iset_range, avg_cnt=args.samples_per_step)
    df = pd.DataFrame(data)
    df.to_csv(filename+'.csv')
    df.to_csv(filename+'.json')
    plot_iv_curve(df, args.string_id, filename+".png")

if __name__ == '__main__':
    main()
