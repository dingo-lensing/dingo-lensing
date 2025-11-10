# DINGO-lensing

**Dingo-lensing** is a python program building on top of [**Dingo**](https://github.com/dingo-gw/dingo) to discover lensed gravitational waves (GWs) with simulation-based inference. 
**Dingo-lensing** employs [**modwaveforms**](https://github.com/ezquiaga/modwaveforms) and will incooporate other lens model codes soon.

Main functionalities of **Dingo-lensing**:

* Generate training dataset with lensed waveform
* Perform fast and accurate inference of lensed GWs
* Compute the Gaussian distance away from non-lensing hypothesis
* Compute lensing Bayes factor with lensed and nonlensed network
* Background estimation for lensing
 


## Install Dingo-lensing
To install **Dingo-lensing** from source, first clone the **Dingo-lensing** directories:

```sh
git clone git@github.com:dingo-lensing/dingo-lensing.git
```
Note that we use version of dingo before correcting the window factor (<0.9).

Create a conda environment for **Dingo-lensing**:
```sh
conda env create dingo-lensing
conda activate dingo-lensing
```

Install **Dingo-lensing**:
```sh
cd dingo-lensing
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
