import torch.nn as nn
import numpy as np
import math
affine_par = True
import torch
import torch.nn.functional as F
#from torch.cuda.amp import autocast
import torch.utils.model_zoo as model_zoo
from models.sync_batchnorm.batchnorm import SynchronizedBatchNorm2d

def outS(i):
    i = int(i)
    i = (i + 1) / 2
    i = int(np.ceil((i + 1) / 2.0))
    i = (i + 1) / 2
    return i

def conv3x3(in_planes, out_planes, stride=1):
    "3x3 convolution with padding"
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride,
                     padding=1, bias=False)

class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super(BasicBlock, self).__init__()
        self.conv1 = conv3x3(inplanes, planes, stride)
        self.bn1 = nn.BatchNorm2d(planes, affine=affine_par)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = conv3x3(planes, planes)
        self.bn2 = nn.BatchNorm2d(planes, affine=affine_par)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out

class Bottleneck(nn.Module):
    expansion = 4

    def __init__(self, inplanes, planes, stride=1, dilation=1, downsample=None):
        super(Bottleneck, self).__init__()
        self.conv1 = nn.Conv2d(inplanes, planes, kernel_size=1, stride=stride, bias=False)  # change
        self.bn1 = nn.BatchNorm2d(planes, affine=affine_par)
        for i in self.bn1.parameters():
            i.requires_grad = False

        padding = dilation
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=1,  # change
                               padding=padding, bias=False, dilation=dilation)
        self.bn2 = nn.BatchNorm2d(planes, affine=affine_par)
        for i in self.bn2.parameters():
            i.requires_grad = False
        self.conv3 = nn.Conv2d(planes, planes * 4, kernel_size=1, bias=False)
        self.bn3 = nn.BatchNorm2d(planes * 4, affine=affine_par)
        for i in self.bn3.parameters():
            i.requires_grad = False
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)
        out = self.bn3(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out

class Classifier_Module(nn.Module):
    def __init__(self, inplanes, dilation_series, padding_series, num_classes):
        super(Classifier_Module, self).__init__()
        self.conv2d_list = nn.ModuleList()
        for dilation, padding in zip(dilation_series, padding_series):
            self.conv2d_list.append(
                nn.Conv2d(inplanes, num_classes, kernel_size=3, stride=1, padding=padding, dilation=dilation, bias=True))

        for m in self.conv2d_list:
            m.weight.data.normal_(0, 0.01)

    def forward(self, x):
        out = self.conv2d_list[0](x)
        feature = self.conv2d_list[0](x)
        for i in range(len(self.conv2d_list) - 1):
            feature = torch.cat((feature, self.conv2d_list[i + 1](x)), dim = 1)
            out += self.conv2d_list[i + 1](x)
        return out, feature

class ResNetPair5(nn.Module):
    def __init__(self, block, layers, num_classes, multiscale=False):
        self.inplanes = 64
        super(ResNetPair5, self).__init__()
        self.multiscale = multiscale
        self.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3,
                               bias=False)
        self.bn1 = nn.BatchNorm2d(64, affine=affine_par)
        self.target_conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3,
                               bias=False)
        self.target_bn1 = nn.BatchNorm2d(64, affine=affine_par)

        for i in self.bn1.parameters():
            i.requires_grad = False
        for i in self.target_bn1.parameters():
            i.requires_grad = False

        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1, ceil_mode=True)  # change
        #self.layer1 = self._make_layer(block, 64, layers[0], first=False)
        self.layer1 = self._make_layer(block, 64, layers[0], first=True)
        self.target_layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2)
        self.layer3 = self._make_layer(block, 256, layers[2], stride=1, dilation=2)
        self.layer4 = self._make_layer(block, 512, layers[3], stride=1, dilation=4)
        self.layer5 = self._make_pred_layer(Classifier_Module, 2048, [6, 12, 18, 24], [6, 12, 18, 24], num_classes)
        self.layer6 = self._make_pred_layer(Classifier_Module, 2048, [6, 12, 18, 24], [6, 12, 18, 24], num_classes)
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, 0.01)

    def _make_layer(self, block, planes, blocks, stride=1, dilation=1, first=False):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion or dilation == 2 or dilation == 4:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes * block.expansion,
                          kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(planes * block.expansion, affine=affine_par))
        for i in downsample._modules['1'].parameters():
            i.requires_grad = False

        layers = []
        layers.append(block(self.inplanes, planes, stride, dilation=dilation, downsample=downsample))
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes, dilation=dilation))
        if first:
            self.inplanes = 64
        return nn.Sequential(*layers)
        #return SublinearSequential(*list(layers.children()))

    def _make_pred_layer(self, block, inplanes, dilation_series, padding_series, num_classes):
        return block(inplanes, dilation_series, padding_series, num_classes)

    def forward(self, x, ssl=False, lbl=None, source=False):
        N, C, H, W = x.shape
        if source:
            x = self.conv1(x)
            x = self.bn1(x)
            x = self.relu(x)
            x = self.maxpool(x)
            x = self.layer1(x)
        else:
            x = self.target_conv1(x)
            x = self.target_bn1(x)
            x = self.relu(x)
            x = self.maxpool(x)
            #x = self.layer1(x)
            x = self.target_layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x1, feature = self.layer5(x)
        # x1 = F.interpolate(x1, (H, W), mode='bilinear', align_corners=True)
        out_dict = {}
        out_dict['feat'] = feature
        out_dict['out'] = x1
        # return x1, feature
        return out_dict

    # def get_1x_lr_params_NOscale(self):

    def get_1x_lr_params(self): ##!! renamed
        b = []
        b.append(self.conv1)
        b.append(self.target_conv1)
        b.append(self.bn1)
        b.append(self.target_bn1)
        b.append(self.layer1)
        b.append(self.target_layer1)
        b.append(self.layer2)
        b.append(self.layer3)
        b.append(self.layer4)
        for i in range(len(b)):
            for j in b[i].modules():
                jj = 0
                for k in j.parameters():
                    jj += 1
                    if k.requires_grad:
                        yield k

    def get_10x_lr_params(self):
        b = []
        b.append(self.layer5.parameters())
        b.append(self.layer6.parameters())

        for j in range(len(b)):
            for i in b[j]:
                yield i

    def optim_parameters(self, args):
        if isinstance(args, float):
            lr = args
        else:
            lr = args.learning_rate
        return [{'params': self.get_1x_lr_params_NOscale(), 'lr': lr},
               {'params': self.get_10x_lr_params(), 'lr':  10*lr}]
               #{'params': self.get_10x_lr_params(), 'lr':  lr}]
"""
class ResNetPair5(nn.Module):
    def __init__(self, block, layers, num_classes, multiscale=False):
        self.inplanes = 64
        super(ResNetPair5, self).__init__()
        self.multiscale = multiscale
        self.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3,
                               bias=False)
        self.bn1 = nn.BatchNorm2d(64, affine=affine_par)

        for i in self.bn1.parameters():
            i.requires_grad = False

        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1, ceil_mode=True)  # change
        self.layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2)
        self.layer3 = self._make_layer(block, 256, layers[2], stride=1, dilation=2)
        self.layer4 = self._make_layer(block, 512, layers[3], stride=1, dilation=4)
        self.layer5 = self._make_pred_layer(Classifier_Module, 2048, [6, 12, 18, 24], [6, 12, 18, 24], num_classes)
        self.layer6 = self._make_pred_layer(Classifier_Module, 2048, [6, 12, 18, 24], [6, 12, 18, 24], num_classes)
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, 0.01)

    def _make_layer(self, block, planes, blocks, stride=1, dilation=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion or dilation == 2 or dilation == 4:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes * block.expansion,
                          kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(planes * block.expansion, affine=affine_par))
        for i in downsample._modules['1'].parameters():
            i.requires_grad = False

        layers = []
        layers.append(block(self.inplanes, planes, stride, dilation=dilation, downsample=downsample))
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes, dilation=dilation))
        return nn.Sequential(*layers)
        #return SublinearSequential(*list(layers.children()))

    def _make_pred_layer(self, block, inplanes, dilation_series, padding_series, num_classes):
        return block(inplanes, dilation_series, padding_series, num_classes)

    def forward(self, x, source=False):
        N, C, H, W = x.shape
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x1, _ = self.layer5(x)
        x1 = F.interpolate(x1, (H, W), mode='bilinear', align_corners=True)

        return x1, _

    def get_1x_lr_params_NOscale(self):
        b = []
        b.append(self.conv1)
        b.append(self.bn1)
        b.append(self.layer1)
        b.append(self.layer2)
        b.append(self.layer3)
        b.append(self.layer4)
        for i in range(len(b)):
            for j in b[i].modules():
                jj = 0
                for k in j.parameters():
                    jj += 1
                    if k.requires_grad:
                        yield k

    def get_10x_lr_params(self):
        b = []
        b.append(self.layer5.parameters())
        b.append(self.layer6.parameters())

        for j in range(len(b)):
            for i in b[j]:
                yield i

    def optim_parameters(self, args):
        if isinstance(args, float):
            lr = args
        else:
            lr = args.learning_rate
        return [{'params': self.get_1x_lr_params_NOscale(), 'lr': lr},
               {'params': self.get_10x_lr_params(), 'lr':  10*lr}]
#                {'params': self.get_10x_lr_params(), 'lr':  lr}]
"""
def ResPair_Deeplab(num_classes=19, cfg=None):
    model = ResNetPair5(Bottleneck, [3, 4, 23, 3], num_classes, cfg)
    return model

################################################################
# changes for ProDA repo
def freeze_bn_func(m):
    if m.__class__.__name__.find('BatchNorm') != -1 or isinstance(m, SynchronizedBatchNorm2d)\
        or isinstance(m, nn.BatchNorm2d):
        m.weight.requires_grad = False
        m.bias.requires_grad = False

def Deeplab(BatchNorm, num_classes=21, freeze_bn=False, restore_from=None, initialization=None, bn_clr=False):
    model = ResNetPair5(Bottleneck, [3, 4, 23, 3], num_classes )#, BatchNorm, bn_clr=bn_clr)
    if freeze_bn:
        model.apply(freeze_bn_func)
    if initialization is None:
        pretrain_dict = model_zoo.load_url('https://download.pytorch.org/models/resnet101-5d3b4d8f.pth')
    else:
        pretrain_dict = torch.load(initialization)['state_dict']
        print("Loading pretrained model from {}".format(initialization))

    model_dict = {}
    state_dict = model.state_dict()
    for k, v in pretrain_dict.items():
        if k in state_dict:
            model_dict[k] = v
    state_dict.update(model_dict)
    model.load_state_dict(state_dict)

    if restore_from is not None: 
        checkpoint = torch.load(restore_from)
        model.load_state_dict(checkpoint)
        # model.load_state_dict(checkpoint['ResNet101']["model_state"])
        #model.load_state_dict(checkpoint['ema'])
    
    return model
