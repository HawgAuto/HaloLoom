# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""CPU dispatch/embedding regressions; no GPU or distributed group required."""

import pytest
import torch
import torch.nn.functional as F

from vllm.model_executor.layers.linear import ReplicatedLinear, UnquantizedLinearMethod
from vllm.model_executor.layers.quantization.quark.quark import QuarkConfig
from vllm.model_executor.layers.vocab_parallel_embedding import (
    ParallelLMHead,
    UnquantizedEmbeddingMethod,
    VocabParallelEmbedding,
)


def bare_layer(cls):
    # Dispatch uses the layer type, not its distributed initialization. Real
    # weights exercise the returned method instead of mocking an embedding op.
    layer = cls.__new__(cls)
    torch.nn.Module.__init__(layer)
    layer.weight = torch.nn.Parameter(torch.arange(32, dtype=torch.float32).reshape(8, 4), requires_grad=False)
    return layer


@pytest.mark.parametrize('cls,prefix', [
    (VocabParallelEmbedding, 'model.embed_tokens'),
    (ParallelLMHead, 'lm_head'),
])
def test_excluded_embedding_uses_embedding_method(cls, prefix):
    layer = bare_layer(cls)
    method = QuarkConfig({'exclude': [prefix]}).get_quant_method(layer, prefix)
    assert isinstance(method, UnquantizedEmbeddingMethod)
    tokens = torch.tensor([0, 3, 7])
    torch.testing.assert_close(method.embedding(layer, tokens), F.embedding(tokens, layer.weight), rtol=0, atol=0)


def test_excluded_linear_dispatch_is_unchanged():
    layer = bare_layer(ReplicatedLinear)
    method = QuarkConfig({'exclude': ['model.layers.0.mlp.down_proj']}).get_quant_method(layer, 'model.layers.0.mlp.down_proj')
    assert isinstance(method, UnquantizedLinearMethod)


def test_unlisted_embedding_still_uses_native_default():
    layer = bare_layer(VocabParallelEmbedding)
    assert QuarkConfig({'exclude': []}).get_quant_method(layer, 'model.embed_tokens') is None


def test_nonmatching_exclusion_keeps_native_default():
    layer = bare_layer(VocabParallelEmbedding)
    method = QuarkConfig({'exclude': ['some.other.layer']}).get_quant_method(layer, 'model.embed_tokens')
    assert method is None
