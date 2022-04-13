# Analyzing the Effectiveness of K-FAC on Training MLP-Mixers for Image Classification
This repo is based on the Pytorch implementation of [K-FAC](https://arxiv.org/abs/1503.05671) from https://github.com/alecwangcq/KFAC-Pytorch.
<br>
The MLP-Mixer architecture implementation is from the repo https://github.com/lucidrains/mlp-mixer-pytorch.
<br>
The learning rate grafting implementation is adapted from https://github.com/optimetry/optimetry?fbclid=IwAR2H_ez5ZMQlD-cqe_38gD_9rHCXLnaaTcsB3yXvq4MUGE3gxCMBD21nVz0.

## Install
```
#Install Packages
pip install -r requirements.txt

#Install grafting library
git clone https://github.com/optimetry/optimetry
cd optimetry
pip install -e .
```

## How to run
```
# Example training command
python main.py --dataset <cifar10,cifar100> --optimizer <kfac,adam,sgd> --network <mlpS,mlpB,mlpB16_pretrain> --epoch 100 --milestone 40,80 --learning_rate 0.001 --damping 0.001 --weight_decay 0.0001

# Example command for grafting
python main.py --dataset <cifar10,cifar100> --optimizer graft --graftM kfac --graftD sgd --network <mlpS,mlpB,mlpB16_pretrain> --epoch 100 --milestone 40,80 --learning_rate 0.001 --damping 0.001 --weight_decay 0.0001

# To test on 224x224 images (instead of 32x32), use flag --large_res
```

## Others
Please consider cite the following papers for K-FAC:
```
@inproceedings{martens2015optimizing,
  title={Optimizing neural networks with kronecker-factored approximate curvature},
  author={Martens, James and Grosse, Roger},
  booktitle={International conference on machine learning},
  pages={2408--2417},
  year={2015}
}

@inproceedings{grosse2016kronecker,
  title={A kronecker-factored approximate fisher matrix for convolution layers},
  author={Grosse, Roger and Martens, James},
  booktitle={International Conference on Machine Learning},
  pages={573--582},
  year={2016}
}
```
