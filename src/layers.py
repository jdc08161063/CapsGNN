import torch
from torch.autograd import Variable

class ListModule(torch.nn.Module):
    """
    Abstract list layer class.
    """
    def __init__(self, *args):
        """
        Model initializing.
        """
        super(ListModule, self).__init__()
        idx = 0
        for module in args:
            self.add_module(str(idx), module)
            idx += 1

    def __getitem__(self, idx):
        """
        Getting the indexed layer.
        """
        if idx < 0 or idx >= len(self._modules):
            raise IndexError('index {} is out of range'.format(idx))
        it = iter(self._modules.values())
        for i in range(idx):
            next(it)
        return next(it)

    def __iter__(self):
        """
        Iterating on the layers.
        """
        return iter(self._modules.values())

    def __len__(self):
        """
        Number of layers.
        """
        return len(self._modules)

class PrimaryCapsuleLayer(torch.nn.Module):
    """
    https://github.com/timomernick/pytorch-capsule
    """
    def __init__(self, in_units, in_channels, num_units, capsule_dimensions):
        super(PrimaryCapsuleLayer, self).__init__()

        self.num_units = num_units
        self.units = []
        for i in range(self.num_units):
            unit = torch.nn.Conv2d(in_channels=in_channels, out_channels=capsule_dimensions, kernel_size=(1,in_units), stride=1, bias=True)
            self.add_module("unit_" + str(i), unit)
            self.units.append(unit)

    @staticmethod
    def squash(s):
        mag_sq = torch.sum(s**2, dim=2, keepdim=True)
        mag = torch.sqrt(mag_sq)
        s = (mag_sq / (1.0 + mag_sq)) * (s / mag)
        return s

    def forward(self, x):
        u = [self.units[i](x) for i in range(self.num_units)]
        u = torch.stack(u, dim=1)
        u = u.view(x.size(0), self.num_units, -1)
        return PrimaryCapsuleLayer.squash(u)


class SecondaryCapsuleLayer(torch.nn.Module):
    """
    https://github.com/timomernick/pytorch-capsule
    """

    def __init__(self, in_units, in_channels, num_units, unit_size):
        super(SecondaryCapsuleLayer, self).__init__()

        self.in_units = in_units
        self.in_channels = in_channels
        self.num_units = num_units
        self.W = torch.nn.Parameter(torch.randn(1, in_channels, num_units, unit_size, in_units))

    @staticmethod
    def squash(s):
        mag_sq = torch.sum(s**2, dim=2, keepdim=True)
        mag = torch.sqrt(mag_sq)
        s = (mag_sq / (1.0 + mag_sq)) * (s / mag)
        return s

    def forward(self, x):
        batch_size = x.size(0)
        x = x.transpose(1, 2)
        x = torch.stack([x] * self.num_units, dim=2).unsqueeze(4)
        W = torch.cat([self.W] * batch_size, dim=0)
        u_hat = torch.matmul(W, x)
        b_ij = Variable(torch.zeros(1, self.in_channels, self.num_units, 1))

        num_iterations = 3
        for iteration in range(num_iterations):
            c_ij = torch.nn.functional.softmax(b_ij,dim=0)
            c_ij = torch.cat([c_ij] * batch_size, dim=0).unsqueeze(4)
            s_j = (c_ij * u_hat).sum(dim=1, keepdim=True)
            v_j = SecondaryCapsuleLayer.squash(s_j)
            v_j1 = torch.cat([v_j] * self.in_channels, dim=1)
            u_vj1 = torch.matmul(u_hat.transpose(3, 4), v_j1).squeeze(4).mean(dim=0, keepdim=True)
            b_ij = b_ij + u_vj1

        return v_j.squeeze(1)



class Attention(torch.nn.Module):
    def __init__(self, attention_size_1, attention_size_2):
        super(Attention, self).__init__()
        self.attention_1 = torch.nn.Linear(attention_size_1, attention_size_2)
        self.attention_2 = torch.nn.Linear(attention_size_2, attention_size_1)

    def forward(self, x_in):
        attention_score_base = self.attention_1(x_in)
        attention_score_base = torch.nn.functional.relu(attention_score_base)
        attention_score = self.attention_2(attention_score_base)
        attention_score = torch.nn.functional.softmax(attention_score,dim=0)
        condensed_x = x_in *attention_score

        return condensed_x

def margin_loss(scores, target, loss_lambda):
    """
    https://github.com/timomernick/pytorch-capsule
    """
    batch_size = scores.size(0)
    v_mag = torch.sqrt((scores**2).sum(dim=2, keepdim=True))
    zero = Variable(torch.zeros(1))
    m_plus = 0.9
    m_minus = 0.1
    max_l = torch.max(m_plus - v_mag, zero).view(batch_size, -1)**2
    max_r = torch.max(v_mag - m_minus, zero).view(batch_size, -1)**2
    T_c = target
    L_c = T_c * max_l + loss_lambda * (1.0 - T_c) * max_r
    L_c = L_c.sum(dim=1)
    L_c = L_c.mean()
    return L_c


