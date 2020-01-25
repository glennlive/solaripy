
if __name__ == '__main__':
    #df = pd.read_csv('../tests/data1.csv', names=['iset', 'v', 'i'])
    #plot_iv_curve(df, "Test Dataset 1", filename='../tests/data1a.png')
    dut = FakeLoad()
    ref = Array371X(serial.Serial('/dev/ttyUSB0', baudrate=9600), address=0)
    ref.max_current = 3
    ref.current = 0.003
    ref.enabled = 1
    d = collect_iv_data(dut, ref, 1.5, np.arange(0.001, 0.06, 0.005))
