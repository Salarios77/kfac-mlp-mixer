'''Train CIFAR10/CIFAR100 with PyTorch.'''
import argparse
import os
from optimizers import (KFACOptimizer, EKFACOptimizer)
import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim.lr_scheduler import MultiStepLR

from tqdm import tqdm
from tensorboardX import SummaryWriter
from utils.network_utils import get_network
from utils.data_utils import get_dataloader
import numpy as np

from mlp_mixer_pytorch import MLPMixer
import time

from pretrain_models.model import MlpMixer as MlpMixer_pretrain
from pretrain_models.model import CONFIGS

from optimetry import Graft

# fetch args
parser = argparse.ArgumentParser()


parser.add_argument('--network', default='vgg16_bn', type=str)
parser.add_argument('--depth', default=19, type=int)
parser.add_argument('--dataset', default='cifar10', type=str)

# densenet
parser.add_argument('--growthRate', default=12, type=int)
parser.add_argument('--compressionRate', default=2, type=int)

# wrn, densenet
parser.add_argument('--widen_factor', default=1, type=int)
parser.add_argument('--dropRate', default=0.0, type=float)


parser.add_argument('--device', default='cuda', type=str)
parser.add_argument('--resume', '-r', action='store_true')
parser.add_argument('--load_path', default='', type=str)
parser.add_argument('--log_dir', default='runs/pretrain', type=str)


parser.add_argument('--optimizer', default='kfac', type=str)
parser.add_argument('--batch_size', default=64, type=int)
parser.add_argument('--epoch', default=100, type=int)
parser.add_argument('--milestone', default=None, type=str)
parser.add_argument('--learning_rate', default=1e-3, type=float) #0.01
parser.add_argument('--momentum', default=0.9, type=float)
parser.add_argument('--stat_decay', default=0.95, type=float)
parser.add_argument('--damping', default=1e-3, type=float)
parser.add_argument('--kl_clip', default=1e-2, type=float)
parser.add_argument('--weight_decay', default=5e-5, type=float) #3e-3
parser.add_argument('--TCov', default=10, type=int)
parser.add_argument('--TScal', default=10, type=int)
parser.add_argument('--TInv', default=100, type=int)

parser.add_argument('--num_workers', default=2, type=int)
parser.add_argument('--pretrain', default=None, type=str)

parser.add_argument('--prefix', default=None, type=str)

parser.add_argument('--large_res', action='store_true')

parser.add_argument('--graftM', default='sgd', type=str)
parser.add_argument('--graftD', default='kfac', type=str)

args = parser.parse_args()

# init model
nc = {
    'cifar10': 10,
    'cifar100': 100
}
num_classes = nc[args.dataset]

print('Network:', args.network)

if not args.large_res:
    im_size = 32
    assert not args.network == 'mlpB16_pretrain'
else:
    im_size = 224

print('Image size:', im_size)

if args.network == 'mlpB16_pretrain':
    print('using pretrained network')
    config = CONFIGS['Mixer-B_16'] #pretrained on imagenet1k
    net = MlpMixer_pretrain(config, 224, num_classes=num_classes, patch_size=16, zero_head=True)
    net.load_from(np.load(args.pretrain))
    args.large_res = True
elif args.network == 'mlpB':
    if args.large_res:
        config = CONFIGS['Mixer-B_16'] 
        patch_size = 16
    else:
        config = CONFIGS['Mixer-B_4'] 
        patch_size = 4
    net = MlpMixer_pretrain(config, im_size, num_classes=num_classes, patch_size=patch_size, zero_head=True)
elif args.network == 'mlpS':
    if args.large_res:
        config = CONFIGS['Mixer-S_16'] 
        patch_size = 16
    else:
        config = CONFIGS['Mixer-S_4'] 
        patch_size = 4
    net = MlpMixer_pretrain(config, im_size, num_classes=num_classes, patch_size=patch_size, zero_head=True)

# elif args.network == 'mlpL16':
#     #([64, 3, 32, 32]
#     #mlp size: img = torch.randn(1, 3, 256, 256)
#     net = MLPMixer(
#         image_size = ((32,32)), #256,
#         channels = 3,
#         patch_size = 16, #16,
#         dim = 1024,
#         depth = 24,
#         num_classes = num_classes
#     )
# elif args.network == 'mlpB16':
#     #mlp size: img = torch.randn(1, 3, 256, 256)
#     net = MLPMixer(
#         image_size = ((32,32)), #256,
#         #image_size = ((224,224)), #256,
#         channels = 3,
#         patch_size = 16, #16,
#         dim = 768,
#         depth = 12,
#         num_classes = num_classes
#     )   

# elif args.network == 'mlpS16':
#     #mlp size: img = torch.randn(1, 3, 256, 256)
#     net = MLPMixer(
#         image_size = ((32,32)), #256,
#         channels = 3,
#         patch_size = 16, #16,
#         dim = 512,
#         depth = 8,
#         num_classes = num_classes
#     )    
 
# elif args.network == 'mlpnano':
#     net = MLPMixer(
#         image_size = ((32,32)), #256,
#         channels = 3,
#         patch_size = 4, #16,
#         dim = 512,
#         depth = 8,
#         num_classes = num_classes
#     )
else:
    net = get_network(args.network,
                    depth=args.depth,
                    num_classes=num_classes,
                    growthRate=args.growthRate,
                    compressionRate=args.compressionRate,
                    widen_factor=args.widen_factor,
                    dropRate=args.dropRate)

net = net.to(args.device)

# init dataloader
trainloader, testloader = get_dataloader(dataset=args.dataset,
                                         train_batch_size=args.batch_size,
                                         test_batch_size=256,
                                         num_workers=args.num_workers,
                                         large_res=args.large_res)

# init optimizer and lr scheduler
optim_name = args.optimizer.lower()
tag = optim_name
if optim_name == 'sgd':
    optimizer = optim.SGD(net.parameters(),
                          lr=args.learning_rate,
                          momentum=args.momentum,
                          weight_decay=args.weight_decay)
elif optim_name == 'adam':
    optimizer = optim.Adam(net.parameters(),
                          lr=args.learning_rate,
                          weight_decay=args.weight_decay)
elif optim_name == 'kfac':
    optimizer = KFACOptimizer(net,
                              lr=args.learning_rate,
                              momentum=args.momentum,
                              stat_decay=args.stat_decay,
                              damping=args.damping,
                              kl_clip=args.kl_clip,
                              weight_decay=args.weight_decay,
                              TCov=args.TCov,
                              TInv=args.TInv)
elif optim_name == 'ekfac':
    optimizer = EKFACOptimizer(net,
                               lr=args.learning_rate,
                               momentum=args.momentum,
                               stat_decay=args.stat_decay,
                               damping=args.damping,
                               kl_clip=args.kl_clip,
                               weight_decay=args.weight_decay,
                               TCov=args.TCov,
                               TScal=args.TScal,
                               TInv=args.TInv)
elif optim_name == 'graft':
    print('Using Graft optimizer with M={} and D={}'.format(args.graftM, args.graftD))

    if args.graftM == 'sgd':
        M_optim = optim.SGD(net.parameters(),
                          lr=args.learning_rate,
                          momentum=args.momentum,
                          weight_decay=args.weight_decay)
    elif args.graftM == 'kfac':
        M_optim = KFACOptimizer(net,
                              lr=args.learning_rate,
                              momentum=args.momentum,
                              stat_decay=args.stat_decay,
                              damping=args.damping,
                              kl_clip=args.kl_clip,
                              weight_decay=args.weight_decay,
                              TCov=args.TCov,
                              TInv=args.TInv)
    else:
        raise NotImplementedError
    
    if args.graftD == 'sgd':
        D_optim = optim.SGD(net.parameters(),
                          lr=args.learning_rate,
                          momentum=args.momentum,
                          weight_decay=args.weight_decay)
    elif args.graftD == 'kfac':
        D_optim = KFACOptimizer(net,
                              lr=args.learning_rate,
                              momentum=args.momentum,
                              stat_decay=args.stat_decay,
                              damping=args.damping,
                              kl_clip=args.kl_clip,
                              weight_decay=args.weight_decay,
                              TCov=args.TCov,
                              TInv=args.TInv)
    else:
        raise NotImplementedError

    optimizer = Graft(net.parameters(), M_optim, D_optim)

    # Rename args.optimizer for logging purposes
    args.optimizer = 'graft_{}_{}'.format(args.graftM, args.graftD)
    
else:
    raise NotImplementedError

if args.milestone is None:
    lr_scheduler = MultiStepLR(optimizer, milestones=[int(args.epoch*0.5), int(args.epoch*0.75)], gamma=0.1)
else:
    milestone = [int(_) for _ in args.milestone.split(',')]
    lr_scheduler = MultiStepLR(optimizer, milestones=milestone, gamma=0.1)

# init criterion
criterion = nn.CrossEntropyLoss()

start_epoch = 0
best_acc = 0
if args.resume:
    print('==> Resuming from checkpoint..')
    assert os.path.isfile(args.load_path), 'Error: no checkpoint directory found!'
    checkpoint = torch.load(args.load_path)
    net.load_state_dict(checkpoint['net'])
    best_acc = checkpoint['acc']
    start_epoch = checkpoint['epoch']
    print('==> Loaded checkpoint at epoch: %d, acc: %.2f%%' % (start_epoch, best_acc))

# init summary writter

log_dir = os.path.join(args.log_dir, args.dataset, args.network, args.optimizer,
                       'lr%.3f_wd%.4f_damping%.4f' %
                       (args.learning_rate, args.weight_decay, args.damping))
if not os.path.isdir(log_dir):
    os.makedirs(log_dir)
writer = SummaryWriter(log_dir)


def train(epoch, model=None):
    print('\nEpoch: %d' % epoch)
    net.train()
    train_loss = 0
    correct = 0
    total = 0

    desc = ('[%s][LR=%s] Loss: %.3f | Acc: %.3f%% (%d/%d)' %
            (tag, lr_scheduler.get_last_lr()[0], 0, 0, correct, total))

    writer.add_scalar('train/lr', lr_scheduler.get_last_lr()[0], epoch)

    prog_bar = tqdm(enumerate(trainloader), total=len(trainloader), desc=desc, leave=True)
    for batch_idx, (inputs, targets) in prog_bar:
        inputs, targets = inputs.to(args.device), targets.to(args.device)
        optimizer.zero_grad()
        graft_kfac = False

        if model=='mlpB16_pretrain':
            outputs, loss = net(inputs, targets)
        else:
            outputs = net(inputs)
            loss = criterion(outputs, targets)

        if optim_name == 'graft' and args.graftM == 'kfac':
            kfac_optimizer = M_optim
            graft_kfac = True
        elif optim_name == 'graft' and args.graftD == 'kfac':
            kfac_optimizer = D_optim
            graft_kfac = True
        else:
            kfac_optimizer = optimizer

        if (graft_kfac or optim_name in ['kfac', 'ekfac']) and kfac_optimizer.steps % kfac_optimizer.TCov == 0:
            # compute true fisher
            kfac_optimizer.acc_stats = True
            with torch.no_grad():
                sampled_y = torch.multinomial(torch.nn.functional.softmax(outputs.cpu().data, dim=1),
                                              1).squeeze().cuda()
            loss_sample = criterion(outputs, sampled_y)
            loss_sample.backward(retain_graph=True)  # kfac has a backward hook invoking _save_grad_output
            kfac_optimizer.acc_stats = False
            kfac_optimizer.zero_grad()  # clear the gradient for computing true-fisher.
        loss.backward()
        optimizer.step()

        train_loss += loss.item()
        _, predicted = outputs.max(1)
        total += targets.size(0)
        correct += predicted.eq(targets).sum().item()

        desc = ('[%s][LR=%s] Loss: %.3f | Acc: %.3f%% (%d/%d)' %
                (tag, lr_scheduler.get_last_lr()[0], train_loss / (batch_idx + 1), 100. * correct / total, correct, total))
        prog_bar.set_description(desc, refresh=True)

    lr_scheduler.step()

    writer.add_scalar('train/loss', train_loss/(batch_idx + 1), epoch)
    writer.add_scalar('train/acc', 100. * correct / total, epoch)


def test(epoch):
    global best_acc
    net.eval()
    test_loss = 0
    correct = 0
    total = 0
    desc = ('[%s][LR=%s] Loss: %.3f | Acc: %.3f%% (%d/%d)'
            % (tag,lr_scheduler.get_last_lr()[0], test_loss/(0+1), 0, correct, total))

    prog_bar = tqdm(enumerate(testloader), total=len(testloader), desc=desc, leave=True)
    with torch.no_grad():
        for batch_idx, (inputs, targets) in prog_bar:
            inputs, targets = inputs.to(args.device), targets.to(args.device)
            outputs = net(inputs)
            loss = criterion(outputs, targets)

            test_loss += loss.item()
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()

            desc = ('[%s][LR=%s] Loss: %.3f | Acc: %.3f%% (%d/%d)'
                    % (tag, lr_scheduler.get_last_lr()[0], test_loss / (batch_idx + 1), 100. * correct / total, correct, total))
            prog_bar.set_description(desc, refresh=True)

    # Save checkpoint.
    acc = 100.*correct/total

    writer.add_scalar('test/loss', test_loss / (batch_idx + 1), epoch)
    writer.add_scalar('test/acc', 100. * correct / total, epoch)

    if acc > best_acc:
        print('Saving..')
        state = {
            'net': net.state_dict(),
            'acc': acc,
            'epoch': epoch,
            'loss': test_loss,
            'args': args
        }

        torch.save(state, '%s/%s_%s_%s%s_best.t7' % (log_dir,
                                                     args.optimizer,
                                                     args.dataset,
                                                     args.network,
                                                     args.depth))
        best_acc = acc


def main():
    for epoch in range(start_epoch, args.epoch):
        start = time.time()
        train(epoch, args.network)
        print('Train Epoch completed in {:.2f} s'.format(time.time()-start))
        test(epoch)
    return best_acc


if __name__ == '__main__':
    main()


