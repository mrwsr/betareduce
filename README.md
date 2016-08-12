# `betareduce`
## Packaging a Python distribution for [AWS Lambda](https://aws.amazon.com/documentation/lambda/).

### What?
`betareduce` takes a list of requirements and puts them in a zip file suitable for use with AWS Lambda.

By default it will remove extension modules (`.so` files) and emit a warning.  This can be disabled.

### Why?

[chalice](https://github.com/awslabs/chalice) exists now, but it reaches into a virtual environment and attempts to extract your projects requirements.  `betareduce`, however, takes whatever arguments you'd pass to `pip`.

(It's named after [beta-reduction in the lambda calculus](https://en.wikipedia.org/wiki/Lambda_calculus#Beta_reduction), the reduction rule that applies arguments to a function.)

### How?

````
(betareduce) $ pip install git+https://github.com/mrwsr/betareduce.git
# ...installation happens...
(betareduce) $ ls /path/to/my/application/package
...
setup.py
...
(betareduce) $ betareduce mypackage.zip package.module.function /path/to/my/application/package -r /path/to/my/application/package/requirements.txt
INFO:betareduce._core:creating temporary directory '/var/folders/vx/9jzwzjds42z75rwj_2w7_4580000gp/T/tmpE1bmP6'
INFO:betareduce._core:command: ['pip', 'install', '-t', '/var/folders/vx/9jzwzjds42z75rwj_2w7_4580000gp/T/tmpE1bmP6', '/path/to/application/package', '-r', '/path/to/application/package/requirements.txt'], output:
Processing /path/to/application/package
Collecting some package....
...
Installing collected packages: foo, ...
Successfully installed foo, ...

INFO:betareduce._core:Detected extension module: /var/folders/vx/9jzwzjds42z75rwj_2w7_4580000gp/T/tmpE1bmP6/simplejson/_speedups.so
INFO:betareduce._core:FPQN for handler function package.module.function now accessible as lambda_entry.function
INFO:betareduce._core:removing temporary directory '/var/folders/vx/9jzwzjds42z75rwj_2w7_4580000gp/T/tmpE1bmP6'
(betareduce) $ file mypackage.zip
replication_lag_monitor.zip: Zip archive data, at least v2.0 to extract
(betareduce) $ unzip -l mypackage.zip
Archive:  replication_lag_monitor.zip
  Length     Date   Time    Name
 --------    ----   ----    ----
    15777  07-12-16 16:12   foo.py
...
--------                   -------
  4315432                   528 files
(betareduce) $
````

### Run the tests

All you need is `py.test`.  Branch coverage should be 100%.