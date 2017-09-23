#pylint: disable=C,R,E1101
import math
import torch
from torch.nn.parameter import Parameter
from torch.nn.modules import Module

from s2cnn.nn.soft.gpu.s2_fft import S2_fft_real
from s2cnn.nn.soft.gpu.so3_fft import SO3_ifft_real
from s2cnn.ops.s2_localft import s2_local_ft
from s2cnn.ops.gpu.s2_mm import S2_mm

class S2Convolution(Module):
    def __init__(self, nfeature_in, nfeature_out, b_in, b_out, grid, weight_scale=1):
        super(S2Convolution, self).__init__()
        self.nfeature_in = nfeature_in
        self.nfeature_out = nfeature_out
        self.b_in = b_in
        self.b_out = b_out
        self.grid = grid
        self.weight_scale = weight_scale
        self.kernel = Parameter(torch.Tensor(nfeature_in, nfeature_out, len(grid)))
        self.bias = Parameter(torch.Tensor(1, nfeature_out, 1, 1, 1))
        self.reset_parameters()

    def reset_parameters(self):
        # stdv = 1 / len(self.grid)**0.5 / self.nfeature_in**0.5 / self.b_out**2 * self.b_in
        stdv = 1. / math.sqrt(len(self.grid) * self.nfeature_in * (self.b_out ** 4.) / (self.b_in ** 2.))
        stdv *= self.weight_scale

        self.kernel.data.normal_(0, stdv)
        self.bias.data[:] = 0

    def forward(self, x): #pylint: disable=W
        '''
        :x:      [batch, feature_in,  beta, alpha]
        :return: [batch, feature_out, beta, alpha, gamma]
        '''
        assert x.size(1) == self.nfeature_in
        assert x.size(2) == 2 * self.b_in
        assert x.size(3) == 2 * self.b_in
        x = S2_fft_real(b_out=self.b_out)(x) # [l * m, batch, feature_in, complex]
        y = s2_local_ft(self.kernel, self.b_out, self.grid) # [feature_in, feature_out, l * m, complex]
        y = y.transpose(0, 2) # [l * m, feature_out, feature_in, complex]
        y = y.transpose(1, 2) # [l * m, feature_in, feature_out, complex]
        y = y.contiguous()
        z = S2_mm()(x, y) # [l * m * n, batch, feature_out, complex]
        z = SO3_ifft_real()(z) # [batch, feature_out, beta, alpha, gamma]

        z.add_(self.bias.expand_as(z))

        return z
