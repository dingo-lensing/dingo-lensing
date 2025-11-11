# DINGO-lensing

**Dingo-lensing** is a python program building on top of [**DINGO**](https://github.com/dingo-gw/dingo) to discover lensed gravitational waves (GWs) with simulation-based inference. 
**DINGO-lensing** employs [**modwaveforms**](https://github.com/ezquiaga/modwaveforms) and will incooporate other lens model codes soon.

Main functionalities of **DINGO-lensing**:

* Generate training dataset with lensed waveform
* Perform fast and accurate inference of lensed GWs
* Compute the Gaussian distance away from non-lensing hypothesis
* Compute lensing Bayes factor with lensed and nonlensed network
* Background estimation for lensing
 


## Install DINGO-lensing
To install **DINGO-lensing** from source, first clone the **DINGO-lensing** directories:

```sh
git clone git@github.com:dingo-lensing/dingo-lensing.git
```
Note that we use version of DINGO before correcting the window factor (<0.9).

Create a conda environment for **DINGO-lensing**:
```sh
conda env create dingo-lensing
conda activate dingo-lensing
```

Install **DINGO-lensing**:
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

**DINGO-lensing** is described in [Chan et al. 2025](https://arxiv.org/abs/2511.07186). If you use this code, we kindly ask you to cite this paper:
```sh
@article{Chan:2025pdf,
    author = "Chan, Juno C. L. and Maga{\~n}a Zertuche, Lorena and Ezquiaga, Jose Mar{\'\i}a and Lo, Rico K. L. and Vujeva, Luka and Bowman, Joey",
    title = "{Identification and characterization of distorted gravitational waves by lensing using deep learning}",
    eprint = "2511.07186",
    archivePrefix = "arXiv",
    primaryClass = "gr-qc",
    month = "11",
    year = "2025"
}
```
as well as the [**DINGO** papers](https://dingo-gw.readthedocs.io/en/latest/#references), including at least:
```sh
@article{Dax:2021tsq,
    author = {Dax, Maximilian and Green, Stephen R. and Gair, Jonathan and Macke, Jakob H. and Buonanno, Alessandra and Sch{\"o}lkopf, Bernhard},
    title = "{Real-Time Gravitational Wave Science with Neural Posterior Estimation}",
    eprint = "2106.12594",
    archivePrefix = "arXiv",
    primaryClass = "gr-qc",
    reportNumber = "LIGO-P2100223",
    doi = "10.1103/PhysRevLett.127.241103",
    journal = "Phys. Rev. Lett.",
    volume = "127",
    number = "24",
    pages = "241103",
    year = "2021"
}
```


## Contact 

For any question please contact
* [Juno Chan](chun.lung.chan@nbi.ku.dk)
* [Rico Lo](kalok.lo@nbi.ku.dk)
* [Jose María Ezquiaga](jose.ezquiaga@nbi.ku.dk)
