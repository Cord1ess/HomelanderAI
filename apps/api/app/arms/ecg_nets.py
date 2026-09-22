"""The two networks behind the ECG arm, defined so their published weights load by name.

Both come from the same group (Ribeiro / Lima et al., UFMG and Uppsala) and are
residual networks over a 12-lead, 4096-sample tracing at 400 Hz:

- **Abnormality classifier** (Ribeiro et al., Nature Communications 2020).
  Published as a Keras/TensorFlow model. `EcgDx` is a PyTorch port; the two
  details that a port gets silently wrong — TensorFlow's asymmetric "same"
  padding and Keras's batch-norm epsilon of 1e-3 — are reproduced here, and
  `scripts/fetch_ecg_models.py` checks the converted weights against the
  authors' own predictions on their test set before writing them.
- **ECG age** (Lima et al., Nature Communications 2021). Published in PyTorch;
  `ResNet1d` and `ResBlock1d` below are the authors' own definitions from
  https://github.com/antonior92/ecg-age-prediction (MIT licence), kept
  verbatim apart from formatting so the checkpoint loads strictly.

Only torch is imported here, lazily by the caller: this module is imported
when the vision extra is installed.
"""

import math

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

# ── ECG age: ResNet1d, from the authors' resnet.py (MIT) ─────────────────────


def _padding(downsample: int, kernel_size: int) -> int:
    return max(0, int(np.floor((kernel_size - downsample + 1) / 2)))


def _downsample(n_samples_in: int, n_samples_out: int) -> int:
    downsample = int(n_samples_in // n_samples_out)
    if downsample < 1:
        raise ValueError("Number of samples should always decrease")
    if n_samples_in % n_samples_out != 0:
        raise ValueError(
            "Number of samples for two consecutive blocks should always decrease "
            "by an integer factor."
        )
    return downsample


class ResBlock1d(nn.Module):
    """Residual network unit for unidimensional signals."""

    def __init__(self, n_filters_in, n_filters_out, downsample, kernel_size, dropout_rate):
        if kernel_size % 2 == 0:
            raise ValueError(
                "The current implementation only support odd values for `kernel_size`."
            )
        super().__init__()
        padding = _padding(1, kernel_size)
        self.conv1 = nn.Conv1d(
            n_filters_in, n_filters_out, kernel_size, padding=padding, bias=False
        )
        self.bn1 = nn.BatchNorm1d(n_filters_out)
        self.relu = nn.ReLU()
        self.dropout1 = nn.Dropout(dropout_rate)
        padding = _padding(downsample, kernel_size)
        self.conv2 = nn.Conv1d(
            n_filters_out,
            n_filters_out,
            kernel_size,
            stride=downsample,
            padding=padding,
            bias=False,
        )
        self.bn2 = nn.BatchNorm1d(n_filters_out)
        self.dropout2 = nn.Dropout(dropout_rate)

        skip_connection_layers = []
        if downsample > 1:
            skip_connection_layers += [nn.MaxPool1d(downsample, stride=downsample)]
        if n_filters_in != n_filters_out:
            skip_connection_layers += [nn.Conv1d(n_filters_in, n_filters_out, 1, bias=False)]
        self.skip_connection = (
            nn.Sequential(*skip_connection_layers) if skip_connection_layers else None
        )

    def forward(self, x, y):
        if self.skip_connection is not None:
            y = self.skip_connection(y)
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.dropout1(x)
        x = self.conv2(x)
        x += y
        y = x
        x = self.bn2(x)
        x = self.relu(x)
        x = self.dropout2(x)
        return x, y


class ResNet1d(nn.Module):
    """Residual network for unidimensional signals (the authors' definition)."""

    def __init__(self, input_dim, blocks_dim, n_classes, kernel_size=17, dropout_rate=0.8):
        super().__init__()
        n_filters_in, n_filters_out = input_dim[0], blocks_dim[0][0]
        n_samples_in, n_samples_out = input_dim[1], blocks_dim[0][1]
        downsample = _downsample(n_samples_in, n_samples_out)
        padding = _padding(downsample, kernel_size)
        self.conv1 = nn.Conv1d(
            n_filters_in, n_filters_out, kernel_size, bias=False, stride=downsample, padding=padding
        )
        self.bn1 = nn.BatchNorm1d(n_filters_out)

        self.res_blocks = []
        for i, (n_filters, n_samples) in enumerate(blocks_dim):
            n_filters_in, n_filters_out = n_filters_out, n_filters
            n_samples_in, n_samples_out = n_samples_out, n_samples
            downsample = _downsample(n_samples_in, n_samples_out)
            resblk1d = ResBlock1d(
                n_filters_in, n_filters_out, downsample, kernel_size, dropout_rate
            )
            self.add_module(f"resblock1d_{i}", resblk1d)
            self.res_blocks += [resblk1d]

        n_filters_last, n_samples_last = blocks_dim[-1]
        self.lin = nn.Linear(n_filters_last * n_samples_last, n_classes)
        self.n_blk = len(blocks_dim)

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        y = x
        for blk in self.res_blocks:
            x, y = blk(x, y)
        x = x.view(x.size(0), -1)
        return self.lin(x)


def age_net(config: dict) -> ResNet1d:
    """The age model as the published `config.json` describes it."""
    return ResNet1d(
        input_dim=(12, config["seq_length"]),
        blocks_dim=list(zip(config["net_filter_size"], config["net_seq_lengh"], strict=True)),
        n_classes=1,
        kernel_size=config["kernel_size"],
        dropout_rate=config["dropout_rate"],
    )


# ── abnormality classifier: port of the Keras model ──────────────────────────

DX_CLASSES: tuple[str, ...] = ("1dAVb", "RBBB", "LBBB", "SB", "AF", "ST")


def _pad_same(x, kernel: int, stride: int):
    """TensorFlow's "same" padding: the total is split with the extra sample
    on the right, unlike PyTorch's symmetric padding."""
    n = x.shape[-1]
    out = math.ceil(n / stride)
    total = max((out - 1) * stride + kernel - n, 0)
    left = total // 2
    return F.pad(x, (left, total - left))


class _DxBlock(nn.Module):
    """The Keras ResidualUnit with preactivation and batch norm before ReLU."""

    def __init__(self, n_in: int, n_out: int, down: int, kernel: int = 16):
        super().__init__()
        self.kernel, self.down = kernel, down
        self.conv1 = nn.Conv1d(n_in, n_out, kernel, bias=False)
        self.bn1 = nn.BatchNorm1d(n_out, eps=1e-3)
        self.conv2 = nn.Conv1d(n_out, n_out, kernel, stride=down, bias=False)
        self.skip = nn.Conv1d(n_in, n_out, 1, bias=False)
        self.bn2 = nn.BatchNorm1d(n_out, eps=1e-3)

    def forward(self, x, y):
        # The skip path: max-pool by the downsample factor (no padding needed,
        # every length here divides exactly), then 1x1 to widen.
        y = self.skip(F.max_pool1d(y, self.down, self.down))
        x = self.conv1(_pad_same(x, self.kernel, 1))
        x = F.relu(self.bn1(x))
        x = self.conv2(_pad_same(x, self.kernel, self.down))
        x = x + y
        y = x
        x = F.relu(self.bn2(x))
        return x, y


class EcgDx(nn.Module):
    """Ribeiro 2020: six abnormality probabilities from (N, 12, 4096)."""

    def __init__(self):
        super().__init__()
        self.stem = nn.Conv1d(12, 64, 16, bias=False)
        self.stem_bn = nn.BatchNorm1d(64, eps=1e-3)
        self.block1 = _DxBlock(64, 128, 4)
        self.block2 = _DxBlock(128, 196, 4)
        self.block3 = _DxBlock(196, 256, 4)
        self.block4 = _DxBlock(256, 320, 4)
        self.head = nn.Linear(16 * 320, len(DX_CLASSES))

    def features(self, x):
        x = F.relu(self.stem_bn(self.stem(_pad_same(x, 16, 1))))
        x, y = self.block1(x, x)
        x, y = self.block2(x, y)
        x, y = self.block3(x, y)
        x, _ = self.block4(x, y)
        # Keras flattens channels-last, so the 16 time steps are the outer index.
        return x.transpose(1, 2).reshape(x.shape[0], -1)

    def forward(self, x):
        return torch.sigmoid(self.head(self.features(x)))


# Keras layer name -> our module, in the file's own numbering. The skip
# convolution is created first in each unit, so it takes the lowest number.
_KERAS_LAYOUT = {
    "stem": ("conv1d_1", None, None, "batch_normalization_1", None),
    "block1": (
        "conv1d_3",
        "conv1d_4",
        "conv1d_2",
        "batch_normalization_2",
        "batch_normalization_3",
    ),
    "block2": (
        "conv1d_6",
        "conv1d_7",
        "conv1d_5",
        "batch_normalization_4",
        "batch_normalization_5",
    ),
    "block3": (
        "conv1d_9",
        "conv1d_10",
        "conv1d_8",
        "batch_normalization_6",
        "batch_normalization_7",
    ),
    "block4": (
        "conv1d_12",
        "conv1d_13",
        "conv1d_11",
        "batch_normalization_8",
        "batch_normalization_9",
    ),
}


def dx_state_from_keras(arrays: dict[str, np.ndarray]) -> dict[str, torch.Tensor]:
    """A strict `EcgDx` state dict from the Keras HDF5 arrays, keyed
    `<layer>/<weight>` (kernel, gamma, beta, moving_mean, moving_variance).

    Keras stores a Conv1D kernel as (width, in, out) and a Dense kernel as
    (in, out); PyTorch wants (out, in, width) and (out, in).
    """

    def conv(name: str) -> torch.Tensor:
        return torch.from_numpy(np.ascontiguousarray(arrays[f"{name}/kernel"].transpose(2, 1, 0)))

    def bn(prefix: str, name: str) -> dict[str, torch.Tensor]:
        return {
            f"{prefix}.weight": torch.from_numpy(arrays[f"{name}/gamma"]),
            f"{prefix}.bias": torch.from_numpy(arrays[f"{name}/beta"]),
            f"{prefix}.running_mean": torch.from_numpy(arrays[f"{name}/moving_mean"]),
            f"{prefix}.running_var": torch.from_numpy(arrays[f"{name}/moving_variance"]),
            f"{prefix}.num_batches_tracked": torch.tensor(0, dtype=torch.long),
        }

    state: dict[str, torch.Tensor] = {"stem.weight": conv("conv1d_1")}
    state.update(bn("stem_bn", "batch_normalization_1"))
    for block, (c1, c2, skip, b1, b2) in _KERAS_LAYOUT.items():
        if block == "stem":
            continue
        state[f"{block}.conv1.weight"] = conv(c1)
        state[f"{block}.conv2.weight"] = conv(c2)
        state[f"{block}.skip.weight"] = conv(skip)
        state.update(bn(f"{block}.bn1", b1))
        state.update(bn(f"{block}.bn2", b2))
    # The file names these `dense_8/kernel_7` and `dense_8/bias_7`.
    dense = next(k for k in arrays if k.startswith("dense_") and "kernel" in k)
    bias = next(k for k in arrays if k.startswith("dense_") and "bias" in k)
    state["head.weight"] = torch.from_numpy(np.ascontiguousarray(arrays[dense].T))
    state["head.bias"] = torch.from_numpy(arrays[bias])
    return state
