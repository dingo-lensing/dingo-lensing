# DINGO-lensing

**Dingo-lensing** is a python program building on top of [**Dingo**](https://github.com/dingo-gw/dingo) to discover lensed gravitational waves (GWs) with simulation-based inference. 
The lens model is built on top of [**modwaveforms**](https://github.com/ezquiaga/modwaveforms) and will allow for other lens model codes soon.

Main functionalities of **Dingo-lensing**:

* Generate training dataset with lensed waveform
* Perform fast and accurate inference of lensed GWs
* Compute the Gaussian distance away from non-lensing hypothesis
* Compute lensing Bayes factor with lensed and nonlensed network
* Background estimation for lensing
 


## Install Dingo-lensing
To install **Dingo-lensing** from source, first clone the **Dingo**, **Dingo-lensing** and **modwaveforms** directories:

```sh
git clone --branch v0.8.7 --depth 1 https://github.com/dingo-gw/dingo.git
git clone git@github.com:dingo-lensing/dingo-lensing.git
git clone https://github.com/ezquiaga/modwaveforms.git

```
Note that we use v0.8.7 of dingo before correcting the window factor.

Create a conda environment for **Dingo-lensing**:
```sh
conda env create dingo-lensing
conda activate dingo-lensing
```
Install **Dingo**:
```sh
cd dingo
pip install .
cd ..
```

Install **Dingo-lensing**:
```sh
cd dingo-lensing
pip install .
cd ..
```

Install modwaveforms for lens model 
```sh
cd modwaveforms
pip install .
```

To allow edible version use:
```sh
pip install -e .
```
for the installation



## Reference 

## Contact 

For any question please contact
* [Juno Chan](chun.lung.chan@nbi.ku.dk)
* [Rico Lo](kalok.lo@nbi.ku.dk)
* [Jose María Ezquiaga](jose.ezquiaga@nbi.ku.dk)
